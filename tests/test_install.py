import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts" / "install.py"
SPEC = importlib.util.spec_from_file_location("rsi_install", INSTALLER)
INSTALL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INSTALL)


class RSIInstallTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.home = self.base / "home"
        self.project = self.base / "project"

    def tearDown(self):
        self.temporary.cleanup()

    def run_main(self, arguments, environment=None):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = INSTALL.main(arguments, home=self.home, environment=environment or {})
        return code, stdout.getvalue(), stderr.getvalue()

    def test_documented_user_destinations(self):
        self.assertEqual(self.home / ".agents/skills/rsi", INSTALL.destination_for("codex", "user", self.home, environment={}))
        self.assertEqual(self.home / ".claude/skills/rsi", INSTALL.destination_for("claude-code", "user", self.home, environment={}))
        self.assertEqual(self.home / ".openclaw/skills/rsi", INSTALL.destination_for("openclaw", "user", self.home, environment={}))

    def test_documented_project_destinations(self):
        self.assertEqual(self.project / ".agents/skills/rsi", INSTALL.destination_for("codex", "project", self.home, self.project, {}))
        self.assertEqual(self.project / ".claude/skills/rsi", INSTALL.destination_for("claude-code", "project", self.home, self.project, {}))
        self.assertEqual(self.project / "skills/rsi", INSTALL.destination_for("openclaw", "project", self.home, self.project, {}))

    def test_dry_run_does_not_write(self):
        code, output, _error = self.run_main(["--agent", "all", "--scope", "user", "--dry-run"])
        self.assertEqual(0, code)
        self.assertEqual(3, output.count("dry-run"))
        self.assertFalse(self.home.exists())

    def test_link_install_and_idempotence(self):
        arguments = ["--agent", "codex", "--scope", "user", "--mode", "link"]
        self.assertEqual(0, self.run_main(arguments)[0])
        destination = self.home / ".agents/skills/rsi"
        self.assertTrue(destination.is_symlink())
        code, output, _error = self.run_main(arguments)
        self.assertEqual(0, code)
        self.assertIn("already-installed", output)

    def test_existing_destination_is_not_overwritten(self):
        destination = self.home / ".claude/skills/rsi"
        destination.mkdir(parents=True)
        marker = destination / "keep.txt"
        marker.write_text("user data", encoding="utf-8")
        code, _output, error = self.run_main(["--agent", "claude-code"])
        self.assertEqual(2, code)
        self.assertIn("refusing to overwrite", error)
        self.assertEqual("user data", marker.read_text(encoding="utf-8"))

    def test_openclaw_project_auto_uses_copy(self):
        code, output, _error = self.run_main(
            ["--agent", "openclaw", "--scope", "project", "--project-dir", str(self.project)]
        )
        self.assertEqual(0, code)
        destination = self.project / "skills/rsi"
        self.assertTrue((destination / "SKILL.md").is_file())
        self.assertFalse(destination.is_symlink())
        self.assertIn("(copy, project)", output)
        self.assertFalse((destination / ".git").exists())

    def test_openclaw_project_external_link_is_rejected(self):
        code, _output, error = self.run_main(
            [
                "--agent",
                "openclaw",
                "--scope",
                "project",
                "--project-dir",
                str(self.project),
                "--mode",
                "link",
            ]
        )
        self.assertEqual(2, code)
        self.assertIn("allowSymlinkTargets", error)

    def test_openclaw_state_directory_override(self):
        state = self.base / "state"
        destination = INSTALL.destination_for(
            "openclaw", "user", self.home, environment={"OPENCLAW_STATE_DIR": str(state)}
        )
        self.assertEqual(state / "skills/rsi", destination)


if __name__ == "__main__":
    unittest.main()
