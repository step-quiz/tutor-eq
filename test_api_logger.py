"""
Tests de api_logger: assegurar que student_id es persisteix al log i que
summarize_session filtra correctament per session_id i student_id.

Executar amb: python -m unittest test_api_logger -v
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import api_logger as A


class TestStudentIdInLog(unittest.TestCase):
    """Verifica que log_call inclou student_id a l'entry escrita."""

    def test_log_call_writes_student_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(A, "LOG_DIR", Path(tmp)):
                A.log_call(
                    session_id="sess1",
                    student_id="S001",
                    function="judge_progress",
                    model="gemini-2.5-flash",
                    attempt=1,
                    ok=True,
                    elapsed_s=0.5,
                    input_data={"user": "x = 5"},
                    output_data={"text_preview": "ok"},
                    tokens={"input": 100, "output": 20, "total": 120},
                )
                # Llegir el fitxer escrit
                files = list(Path(tmp).glob("api_calls_*.jsonl"))
                self.assertEqual(len(files), 1)
                lines = files[0].read_text(encoding="utf-8").splitlines()
                self.assertEqual(len(lines), 1)
                entry = json.loads(lines[0])
                self.assertEqual(entry["student_id"], "S001")
                self.assertEqual(entry["session_id"], "sess1")

    def test_log_call_without_student_id_writes_none(self):
        # Compatibilitat enrere: la crida sense student_id ha de funcionar
        # i deixar el camp com a None (no fallar).
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(A, "LOG_DIR", Path(tmp)):
                A.log_call(
                    session_id="sess1",
                    function="judge_progress",
                    model="gemini-2.5-flash",
                    attempt=1, ok=True, elapsed_s=0.1,
                    input_data={}, output_data={},
                    tokens={"input": 10, "output": 5, "total": 15},
                )
                files = list(Path(tmp).glob("api_calls_*.jsonl"))
                entry = json.loads(files[0].read_text(encoding="utf-8"))
                self.assertIsNone(entry["student_id"])


class TestSummarizeSessionFilters(unittest.TestCase):
    """Verifica que summarize_session filtra correctament."""

    def _write_entries(self, tmp_dir: Path, entries: list):
        path = tmp_dir / "api_calls_test.jsonl"
        with open(path, "w", encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")
        return path

    def _entry(self, **overrides):
        base = {
            "ts": "2026-05-09T12:00:00.000",
            "session_id": "default_sess",
            "student_id": "anon",
            "function": "judge_progress",
            "model": "gemini-2.5-flash",
            "attempt": 1,
            "ok": True,
            "elapsed_s": 0.5,
            "input": {},
            "output": {},
            "tokens": {"input": 100, "output": 20, "thoughts": 0, "total": 120},
            "cost_usd": 0.0001,
            "error": None,
        }
        base.update(overrides)
        return base

    def test_filter_by_student_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_entries(Path(tmp), [
                self._entry(student_id="S001", session_id="A"),
                self._entry(student_id="S001", session_id="B"),
                self._entry(student_id="S002", session_id="C"),
                self._entry(student_id=None, session_id="D"),
            ])
            r = A.summarize_session(student_id="S001", log_path=path)
            self.assertEqual(r["calls_total"], 2)
            self.assertEqual(r["student_id"], "S001")

    def test_filter_by_session_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_entries(Path(tmp), [
                self._entry(student_id="S001", session_id="A"),
                self._entry(student_id="S001", session_id="A"),
                self._entry(student_id="S002", session_id="B"),
            ])
            r = A.summarize_session(session_id="A", log_path=path)
            self.assertEqual(r["calls_total"], 2)

    def test_filter_by_both_id_and_student(self):
        # student_id="S001" + session_id="A" → només la primera entrada
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_entries(Path(tmp), [
                self._entry(student_id="S001", session_id="A"),
                self._entry(student_id="S001", session_id="B"),
                self._entry(student_id="S002", session_id="A"),
            ])
            r = A.summarize_session(session_id="A",
                                    student_id="S001", log_path=path)
            self.assertEqual(r["calls_total"], 1)

    def test_no_filter_returns_all(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_entries(Path(tmp), [
                self._entry(student_id="S001"),
                self._entry(student_id="S002"),
                self._entry(student_id=None),
            ])
            r = A.summarize_session(log_path=path)
            self.assertEqual(r["calls_total"], 3)

    def test_filter_excludes_old_logs_without_student_id(self):
        # Logs antics no tenen student_id (camp absent). Si filtrem per
        # un student_id concret, NO s'han d'incloure (entry.get retorna
        # None i None != "S001").
        with tempfile.TemporaryDirectory() as tmp:
            old_entry = self._entry()
            del old_entry["student_id"]  # simular log antic
            path = self._write_entries(Path(tmp), [
                old_entry,
                self._entry(student_id="S001"),
            ])
            r = A.summarize_session(student_id="S001", log_path=path)
            self.assertEqual(r["calls_total"], 1)

    def test_aggregates_tokens_and_cost(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_entries(Path(tmp), [
                self._entry(student_id="S001",
                            tokens={"input": 100, "output": 20,
                                    "thoughts": 0, "total": 120},
                            cost_usd=0.001),
                self._entry(student_id="S001",
                            tokens={"input": 50, "output": 10,
                                    "thoughts": 0, "total": 60},
                            cost_usd=0.0005),
            ])
            r = A.summarize_session(student_id="S001", log_path=path)
            self.assertEqual(r["tokens_input"], 150)
            self.assertEqual(r["tokens_output"], 30)
            self.assertAlmostEqual(r["cost_usd"], 0.0015, places=6)


if __name__ == "__main__":
    unittest.main()
