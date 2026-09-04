import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "rsi.py"
SPEC = importlib.util.spec_from_file_location("rsi", CLI)
RSI = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RSI)


def candidate(index=1, **updates):
    value = {
        "kind": "procedure",
        "title": "Preserve identifier formatting %d" % index,
        "lesson": "Read identifier-like CSV columns as text before schema inference.",
        "scope": "workspace",
        "task_types": ["csv-import"],
        "applicability": ["CSV files contain numeric-looking identifiers"],
        "evidence": "The leading-zero regression test passed after this change.",
        "confidence": 0.93,
        "tags": ["csv", "schema", "leading-zero", "identifier-%d" % index],
        "avoid": "Casting identifier columns to integers.",
        "source_task": "fixture-%d" % index,
    }
    value.update(updates)
    return value


class RSICLITest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.store = self.base / ".rsi"

    def tearDown(self):
        self.temporary.cleanup()

    def input_file(self, value, name="input.json"):
        path = self.base / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def run_main(self, arguments):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = RSI.main(["--store", str(self.store)] + arguments)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_preview_is_read_only(self):
        path = self.input_file(candidate())
        code, output, _error = self.run_main(["preview-experience", "--input", str(path)])
        self.assertEqual(0, code)
        self.assertIn("E1 · experience", output)
        self.assertFalse(self.store.exists())

    def test_visualize_empty_store_is_read_only(self):
        code, output, _error = self.run_main(["visualize", "--format", "markdown"])
        self.assertEqual(0, code)
        self.assertIn("active=0", output)
        self.assertIn("No matching experience", output)
        self.assertFalse(self.store.exists())

    def test_unapproved_experience_write_is_rejected_without_store(self):
        path = self.input_file(candidate())
        code, _output, error = self.run_main(["save-experience", "--input", str(path)])
        self.assertEqual(2, code)
        self.assertIn("write refused", error)
        self.assertFalse(self.store.exists())

    def test_unapproved_memory_and_init_are_rejected(self):
        path = self.input_file(
            {"statement": "Prefer short completion summaries with test evidence.", "scope": "global", "evidence": "Explicit request."}
        )
        for arguments in (["save-memory", "--input", str(path)], ["init"]):
            code, _output, error = self.run_main(arguments)
            self.assertEqual(2, code)
            self.assertIn("write refused", error)
        self.assertFalse(self.store.exists())

    def test_save_query_doctor_and_stats(self):
        path = self.input_file(candidate())
        code, output, _error = self.run_main(["save-experience", "--approved", "--input", str(path)])
        self.assertEqual(0, code)
        self.assertIn("Saved xp-", output)

        code, output, _error = self.run_main(["query", "CSV leading zeros", "--limit", "1"])
        self.assertEqual(0, code)
        self.assertIn("Preserve identifier formatting", output)

        code, output, _error = self.run_main(["doctor"])
        self.assertEqual(0, code)
        self.assertIn("store OK: 1", output)

        code, output, _error = self.run_main(["stats", "--json"])
        self.assertEqual(0, code)
        self.assertEqual(1, json.loads(output)["records"])

    def test_visualize_and_exact_recall(self):
        value = candidate(title="Escape <script> in dashboard")
        path = self.input_file(value)
        self.run_main(["save-experience", "--approved", "--input", str(path)])
        identifier = next((self.store / "experiences").glob("*.json")).stem

        code, output, _error = self.run_main(["visualize", "--format", "markdown"])
        self.assertEqual(0, code)
        self.assertIn("| R1 |", output)
        self.assertIn(identifier, output)

        code, output, _error = self.run_main(["recall", identifier])
        self.assertEqual(0, code)
        self.assertIn("Escape <script> in dashboard", output)

        dashboard = self.base / "dashboard.html"
        code, output, _error = self.run_main(
            ["visualize", "--format", "html", "--status", "all", "--output", str(dashboard)]
        )
        self.assertEqual(0, code)
        self.assertIn("Wrote read-only", output)
        html = dashboard.read_text(encoding="utf-8")
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("<strong>Escape <script>", html)

    def test_delete_to_trash_and_restore_are_approval_gated(self):
        path = self.input_file(candidate())
        self.run_main(["save-experience", "--approved", "--input", str(path)])
        experience_path = next((self.store / "experiences").glob("*.json"))
        identifier = experience_path.stem

        code, _output, error = self.run_main(["delete", identifier])
        self.assertEqual(2, code)
        self.assertIn("write refused", error)
        self.assertTrue(experience_path.exists())

        code, output, _error = self.run_main(["delete", "--approved", identifier])
        self.assertEqual(0, code)
        self.assertIn("recoverable", output)
        self.assertFalse(experience_path.exists())
        trash_path = self.store / "trash" / (identifier + ".json")
        self.assertTrue(trash_path.exists())

        code, _output, error = self.run_main(["recall", identifier])
        self.assertEqual(2, code)
        self.assertIn("in trash", error)
        code, output, _error = self.run_main(["visualize", "--status", "trashed"])
        self.assertEqual(0, code)
        self.assertIn("trashed", output)
        self.assertIn(identifier, output)
        self.assertEqual(0, self.run_main(["doctor"])[0])

        code, _output, error = self.run_main(["restore", identifier])
        self.assertEqual(2, code)
        self.assertIn("write refused", error)
        code, output, _error = self.run_main(["restore", "--approved", identifier])
        self.assertEqual(0, code)
        self.assertIn("status=active", output)
        self.assertTrue(experience_path.exists())
        self.assertFalse(trash_path.exists())
        self.assertEqual(0, self.run_main(["recall", identifier])[0])

    def test_restore_preserves_archived_status(self):
        path = self.input_file(candidate())
        self.run_main(["save-experience", "--approved", "--input", str(path)])
        experience_path = next((self.store / "experiences").glob("*.json"))
        identifier = experience_path.stem
        self.assertEqual(0, self.run_main(["archive", "--approved", identifier])[0])
        self.assertEqual(0, self.run_main(["delete", "--approved", identifier])[0])
        self.assertEqual(0, self.run_main(["restore", "--approved", identifier])[0])
        record = json.loads(experience_path.read_text(encoding="utf-8"))
        self.assertEqual("archived", record["status"])
        self.assertEqual(2, self.run_main(["recall", identifier])[0])
        self.assertEqual(0, self.run_main(["recall", "--include-archived", identifier])[0])

    def test_duplicate_save_is_rejected(self):
        path = self.input_file(candidate())
        self.assertEqual(0, self.run_main(["save-experience", "--approved", "--input", str(path)])[0])
        code, _output, error = self.run_main(["save-experience", "--approved", "--input", str(path)])
        self.assertEqual(2, code)
        self.assertIn("duplicate experience", error)
        self.assertEqual(1, len(list((self.store / "experiences").glob("*.json"))))

    def test_secret_is_rejected_before_store_creation(self):
        path = self.input_file(candidate(lesson="Use password=correct-horse-battery-staple for the service."))
        code, _output, error = self.run_main(["save-experience", "--approved", "--input", str(path)])
        self.assertEqual(2, code)
        self.assertIn("assigned secret", error)
        self.assertFalse(self.store.exists())

    def test_memory_deduplicates(self):
        value = {
            "statement": "Prefer concise completion summaries with test evidence.",
            "scope": "global",
            "evidence": "The user explicitly requested this format.",
        }
        path = self.input_file(value)
        for expected in (1, 0):
            code, output, _error = self.run_main(["save-memory", "--approved", "--input", str(path)])
            self.assertEqual(0, code)
            self.assertIn("Saved %d memory item" % expected, output)
        memory = (self.store / "memory.md").read_text(encoding="utf-8")
        self.assertEqual(1, memory.count(value["statement"]))

    def test_feedback_and_archive_require_approval(self):
        path = self.input_file(candidate())
        self.run_main(["save-experience", "--approved", "--input", str(path)])
        identifier = next((self.store / "experiences").glob("*.json")).stem

        code, _output, error = self.run_main(["feedback", identifier, "success"])
        self.assertEqual(2, code)
        self.assertIn("write refused", error)

        self.assertEqual(0, self.run_main(["feedback", "--approved", identifier, "success"])[0])
        self.assertEqual(0, self.run_main(["archive", "--approved", identifier])[0])
        code, output, _error = self.run_main(["query", "CSV leading zeros"])
        self.assertEqual(0, code)
        self.assertIn("No relevant", output)

    def test_chinese_query_retrieves_chinese_record(self):
        value = candidate(
            title="保留表格中的前导零",
            lesson="读取编号列时使用字符串类型，避免前导零在类型推断时丢失。",
            task_types=["表格导入"],
            applicability=["导入包含编号列的中文表格"],
            evidence="回归测试确认编号格式被完整保留。",
            tags=["表格", "编号", "前导零"],
        )
        path = self.input_file(value)
        self.run_main(["save-experience", "--approved", "--input", str(path)])
        code, output, _error = self.run_main(["query", "导入表格时保留编号前导零"])
        self.assertEqual(0, code)
        self.assertIn("保留表格中的前导零", output)

    def test_parallel_writers_preserve_all_records(self):
        processes = []
        for index in range(8):
            path = self.input_file(candidate(index), "input-%d.json" % index)
            processes.append(
                subprocess.Popen(
                    [sys.executable, str(CLI), "--store", str(self.store), "save-experience", "--approved", "--input", str(path)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
            )
        failures = []
        for process in processes:
            stdout, stderr = process.communicate(timeout=15)
            if process.returncode != 0:
                failures.append((process.returncode, stdout, stderr))
        self.assertEqual([], failures)
        self.assertEqual(8, len(list((self.store / "experiences").glob("*.json"))))
        self.assertEqual(0, self.run_main(["doctor"])[0])


if __name__ == "__main__":
    unittest.main()
