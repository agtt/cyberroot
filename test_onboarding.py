"""No installs, provider requests or real target startup in onboarding checks."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import onboarding

HERE = Path(__file__).resolve().parent


class OnboardingTests(unittest.TestCase):
    def fixture(self, directory):
        root = Path(directory)
        (root / "models.txt").write_text("research example/research\nfree opencode/free\n")
        (root / "opencode.jsonc").write_text(json.dumps({"websearch": {"provider": "random"},
            "providers": {"example": {"settings": {"baseURL": "https://api.example.com/v1",
                "apiKey": "{file:/home/agent/.secrets/example-api-key}"}}}}))
        (root / "example-api-key").write_text("fixture-private-value")
        return root

    def test_doctor_does_not_start_target_or_read_secret_files(self):
        with tempfile.TemporaryDirectory(dir=HERE) as directory:
            root = self.fixture(directory)
            original = Path.read_text
            def read(path, *args, **kwargs):
                if path.name.endswith("-api-key"):
                    raise AssertionError("doctor must not read the API key")
                return original(path, *args, **kwargs)
            with patch.object(onboarding.shutil, "which", return_value="/fixture/bin"), \
                 patch.object(onboarding, "capture", return_value='{"status":"Stopped"}') as commands, \
                 patch.object(Path, "read_text", read):
                report = onboarding.diagnose(root, root, "local")
            self.assertTrue(report["ok"])
            self.assertFalse(report["target_running"])
            self.assertEqual(report["model_requests"], 0)
            self.assertEqual(report["installations"], 0)
            self.assertNotIn("fixture-private-value", json.dumps(report))
            self.assertEqual(commands.call_count, 1)
            self.assertNotIn("start", commands.call_args.args[0])

    def test_remote_diagnostics_require_explicit_live_flag(self):
        with tempfile.TemporaryDirectory(dir=HERE) as directory:
            root = self.fixture(directory)
            with patch.object(onboarding.shutil, "which", return_value="/fixture/bin"), \
                 patch.object(onboarding, "capture", side_effect=AssertionError("no network")):
                report = onboarding.diagnose(root, root, "vps fixture-host")
            self.assertTrue(report["ok"])
            self.assertFalse(report["target_running"])

    def test_fresh_doctor_uses_templates_without_creating_settings(self):
        with tempfile.TemporaryDirectory(dir=HERE) as directory:
            root = self.fixture(directory)
            (root / "models.txt").rename(root / "models.example.txt")
            (root / "opencode.jsonc").rename(root / "opencode.example.jsonc")
            with patch.object(onboarding.shutil, "which", return_value="/fixture/bin"), \
                 patch.object(onboarding, "capture", return_value='{"status":"Stopped"}'):
                report = onboarding.diagnose(root, root, "local")
            self.assertTrue(report["ok"])
            self.assertFalse((root / "models.txt").exists())
            self.assertFalse((root / "opencode.jsonc").exists())
            self.assertTrue(any(row["name"] == "local settings" for row in report["checks"]))

    def test_configure_only_keeps_config_and_selects_no_optional_tools(self):
        with tempfile.TemporaryDirectory(dir=HERE) as directory:
            root = self.fixture(directory)
            before = (root / "opencode.jsonc").read_text()
            output = io.StringIO()
            with patch("builtins.input", side_effect=["1", "1", "1", "none", "n"]), \
                 patch.object(onboarding.subprocess, "run", side_effect=AssertionError("no installs/startup")), redirect_stdout(output):
                onboarding.setup(root, "local")
            self.assertEqual((root / "opencode.jsonc").read_text(), before)
            self.assertEqual((root / "default").read_text(), "example/research\n")
            self.assertEqual((root / "target").read_text(), "local\n")
            self.assertIn("Optional integrations: none", output.getvalue())
            self.assertIn("Nothing downloaded or started", output.getvalue())

    def test_new_provider_preserves_settings_and_never_overwrites_existing_provider(self):
        with tempfile.TemporaryDirectory(dir=HERE) as directory:
            root = self.fixture(directory)
            chosen = onboarding.add_provider(root, "gateway", "https://gateway.example/v1", "new", "upstream/model")
            self.assertEqual(chosen, "gateway/new")
            config = json.loads((root / "opencode.jsonc").read_text())
            self.assertEqual(config["websearch"], {"provider": "random"})
            self.assertIn("example", config["providers"])
            self.assertEqual(config["providers"]["gateway"]["settings"]["apiKey"], "{file:/home/agent/.secrets/gateway-api-key}")
            before = (root / "opencode.jsonc").read_text()
            with self.assertRaisesRegex(ValueError, "already exists"):
                onboarding.add_provider(root, "gateway", "https://other.example/v1", "other", "model")
            self.assertEqual((root / "opencode.jsonc").read_text(), before)
            self.assertFalse((root / "gateway-api-key").exists())


if __name__ == "__main__":
    unittest.main()
