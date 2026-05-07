"""
Logger d'interaccions amb l'API. Mode debug.

Cada crida queda registrada en un fitxer .jsonl (un objecte JSON per línia)
dins el directori `logs/`. El fitxer es crea per dia.

Format de cada línia (un JSON object):
{
  "ts": "2026-05-07T18:36:00.123",        # timestamp ISO
  "session_id": "abc123",                  # id de sessió Streamlit
  "function": "judge_progress",            # quina crida del llm.py
  "model": "gemini-2.5-pro",
  "attempt": 1,                            # número d'intent (per retries)
  "ok": true,                              # ha tingut èxit?
  "elapsed_s": 4.2,                        # temps en segons
  "input": {...},                          # paràmetres de la crida
  "output": {...} | null,                  # resposta (si OK)
  "error": "503 UNAVAILABLE" | null        # missatge d'error (si KO)
}
"""

import json
import os
from datetime import datetime
from pathlib import Path
from threading import Lock

LOG_DIR = Path(os.environ.get("TUTOR_LOG_DIR", "logs"))
_lock = Lock()


def _ensure_dir():
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def _logfile_path() -> Path:
    today = datetime.now().strftime("%Y-%m-%d")
    return LOG_DIR / f"api_calls_{today}.jsonl"


def log_call(session_id: str, function: str, model: str,
             attempt: int, ok: bool, elapsed_s: float,
             input_data: dict, output_data=None, error: str = None):
    """Escriu una entrada al log. Thread-safe (Streamlit pot ser concurrent)."""
    _ensure_dir()
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
        "error": error,
    }
    line = json.dumps(entry, ensure_ascii=False)
    with _lock:
        with open(_logfile_path(), "a", encoding="utf-8") as f:
            f.write(line + "\n")


def get_log_path() -> Path:
    return _logfile_path()
