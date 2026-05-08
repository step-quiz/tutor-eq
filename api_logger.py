"""
Logger d'interaccions amb l'API + tracking de cost.

Cada crida queda registrada en un fitxer .jsonl (un objecte JSON per línia)
dins el directori `logs/`. El fitxer es crea per dia.

Format de cada línia:
{
  "ts": "2026-05-07T18:36:00.123",        # timestamp ISO
  "session_id": "abc123",                  # id de sessió (procés Python)
  "function": "classify_error",            # quina crida del llm.py
  "model": "gemini-2.5-pro",
  "attempt": 1,                            # número d'intent (per retries)
  "ok": true,                              # ha tingut èxit?
  "elapsed_s": 4.2,                        # temps en segons
  "input": {...},                          # paràmetres de la crida
  "output": {...} | null,                  # resposta (si OK)
  "tokens": {                              # null si la crida ha fallat
      "input": 1234,                       # prompt_token_count
      "output": 56,                        # candidates_token_count
      "thoughts": 234,                     # thoughts_token_count (només thinking models)
      "total": 1524
  },
  "cost_usd": 0.00234,                     # estimació de cost (null si KO)
  "error": "503 UNAVAILABLE" | null
}
"""

import json
import os
from datetime import datetime
from pathlib import Path
from threading import Lock

LOG_DIR = Path(os.environ.get("TUTOR_LOG_DIR", "logs"))
_lock = Lock()


# Preus en USD per 1 milió de tokens. Comprova periòdicament a
# https://ai.google.dev/pricing o https://cloud.google.com/vertex-ai/generative-ai/pricing
# (els preus poden canviar; especialment hi ha rates diferents per a
# contextos > 200k tokens, però aquí assumim contextos curts <5k tokens).
# Per a thinking models (gemini-2.5-pro), els thoughts_tokens es facturen
# com a output_tokens — la suma surt al cost.
# Última verificació: 2025-Q4.
MODEL_PRICING_USD_PER_M = {
    "gemini-2.5-pro":        {"input": 1.25, "output": 10.00},
    "gemini-2.5-flash":      {"input": 0.30, "output":  2.50},
    "gemini-2.5-flash-lite": {"input": 0.10, "output":  0.40},
}
# Fallback conservador (preu de pro) per a models no llistats.
_FALLBACK_PRICING = {"input": 1.25, "output": 10.00}


def estimate_cost_usd(model: str, tokens_in: int, tokens_out: int) -> float:
    """
    Cost d'una crida en USD a partir dels comptes de tokens. Per al thinking
    model gemini-2.5-pro, el cridador ha de passar la suma
    candidates_tokens + thoughts_tokens com a tokens_out.
    """
    rates = MODEL_PRICING_USD_PER_M.get(model, _FALLBACK_PRICING)
    return (tokens_in * rates["input"] + tokens_out * rates["output"]) / 1_000_000


def _ensure_dir():
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def _logfile_path() -> Path:
    today = datetime.now().strftime("%Y-%m-%d")
    return LOG_DIR / f"api_calls_{today}.jsonl"


def log_call(session_id: str, function: str, model: str,
             attempt: int, ok: bool, elapsed_s: float,
             input_data: dict, output_data=None, error: str = None,
             tokens: dict = None):
    """
    Escriu una entrada al log. Thread-safe.

    `tokens`: dict opcional {"input", "output", "thoughts", "total"}.
    Si està present i la crida ha tingut èxit, calcula també el cost USD.
    """
    _ensure_dir()
    cost_usd = None
    if tokens is not None and ok:
        # Per al càlcul de cost, els thinking tokens es facturen com a
        # output (és la regla actual de Gemini 2.5 Pro).
        out_total = (tokens.get("output", 0) or 0) + (tokens.get("thoughts", 0) or 0)
        in_total = tokens.get("input", 0) or 0
        cost_usd = round(estimate_cost_usd(model, in_total, out_total), 6)
    entry = {
        "ts": datetime.now().isoformat(timespec="milliseconds"),
        "session_id": session_id,
        "function": function,
        "model": model,
        "attempt": attempt,
        "ok": ok,
        "elapsed_s": round(elapsed_s, 3),
        "input": input_data,
        "output": output_data,
        "tokens": tokens,
        "cost_usd": cost_usd,
        "error": error,
    }
    line = json.dumps(entry, ensure_ascii=False)
    with _lock:
        with open(_logfile_path(), "a", encoding="utf-8") as f:
            f.write(line + "\n")


def get_log_path() -> Path:
    return _logfile_path()


def summarize_session(session_id: str = None, log_path: Path = None) -> dict:
    """
    Agrega estadístiques de totes les crides d'una sessió (o de TOTES les
    sessions, si session_id és None). Si log_path no s'especifica, s'usen
    tots els fitxers .jsonl del directori de logs.

    Retorna:
      {
        "session_id": str | None,
        "calls_total": int,
        "calls_ok": int,
        "calls_failed": int,
        "by_function": {nom: comptador},
        "tokens_input": int,
        "tokens_output": int,    # inclou thoughts (com a la facturació)
        "tokens_total": int,
        "cost_usd": float,       # estimació
        "elapsed_s_total": float,
      }

    Útil per a:
      - Mostrar el cost a l'usuari durant la sessió en curs
      - Auditar el cost del pilot al final del dia (session_id=None →
        suma de tot)
      - Detectar funcions amb consum desproporcionat
    """
    files = [log_path] if log_path else sorted(LOG_DIR.glob("api_calls_*.jsonl"))
    summary = {
        "session_id": session_id,
        "calls_total": 0,
        "calls_ok": 0,
        "calls_failed": 0,
        "by_function": {},
        "tokens_input": 0,
        "tokens_output": 0,
        "tokens_total": 0,
        "cost_usd": 0.0,
        "elapsed_s_total": 0.0,
    }
    for f in files:
        if not f or not f.exists():
            continue
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                try:
                    entry = json.loads(line)
                except Exception:
                    continue
                if session_id is not None and entry.get("session_id") != session_id:
                    continue
                summary["calls_total"] += 1
                if entry.get("ok"):
                    summary["calls_ok"] += 1
                else:
                    summary["calls_failed"] += 1
                fn = entry.get("function", "unknown")
                summary["by_function"][fn] = summary["by_function"].get(fn, 0) + 1
                summary["elapsed_s_total"] += entry.get("elapsed_s", 0) or 0
                tk = entry.get("tokens") or {}
                summary["tokens_input"] += tk.get("input", 0) or 0
                summary["tokens_output"] += ((tk.get("output", 0) or 0)
                                             + (tk.get("thoughts", 0) or 0))
                summary["tokens_total"] += tk.get("total", 0) or 0
                if entry.get("cost_usd") is not None:
                    summary["cost_usd"] += entry["cost_usd"]
    summary["cost_usd"] = round(summary["cost_usd"], 6)
    summary["elapsed_s_total"] = round(summary["elapsed_s_total"], 2)
    return summary
