"""Small offline checks for opt-in installs, model routing and isolated Kali commands."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import toolkit

HERE = Path(__file__).resolve().parent


class ToolTests(unittest.TestCase):
    def test_agent_plan_selects_only_requested_tool_and_dependency(self):
        self.assertEqual(toolkit.install_plan()["commands"], [])
        plan = toolkit.install_plan("strix")
        self.assertFalse(plan["automatic_install"])
        self.assertEqual([command[-2] for command in plan["commands"]], ["engine", "strix"])
        self.assertTrue(all(tool["optional"] for tool in plan["tools"].values()))
        result = subprocess.run(["bash", "ailab", "tools", "plan", "strix", "--json"], cwd=HERE,
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), plan)

    def fixture(self, directory):
        root = Path(directory)
        (root / "strix").mkdir()
        (root / "strix/strix").touch()
        (root / "shannon/node_modules/.bin").mkdir(parents=True)
        (root / "shannon/node_modules/.bin/shannon").touch()
        config = root / "config.jsonc"
        config.write_text(json.dumps({"providers": {"example": {"settings": {
            "baseURL": "https://api.example.com/v1", "apiKey": "{file:/home/agent/.secrets/example-api-key}"},
            "models": {"short": {"modelID": "upstream/model"}}}}}))
        (root / "example-api-key").write_text("fixture-key")
        return root, config

    def test_transfers_model_alias_and_secret_only_to_environment(self):
        with tempfile.TemporaryDirectory(dir=HERE) as directory, patch.dict(os.environ, {"CYBER_TOOLS_HOME": directory}):
            root, config = self.fixture(directory)
            with toolkit.model_command("strix", ["--target", "https://example.com"], "example/short", config, root) as (command, env):
                self.assertEqual(env["STRIX_LLM"], "openai/upstream/model")
                self.assertEqual(env["LLM_API_KEY"], "fixture-key")
                self.assertEqual(env["LLM_API_BASE"], "https://api.example.com/v1")
                self.assertNotIn("fixture-key", " ".join(command))
            with toolkit.model_command("shannon", ["start", "-u", "https://example.com", "-r", "repo with spaces"], "example/short", config, root) as (command, env):
                metadata = Path(command[command.index("--models-config") + 1])
                self.assertNotIn("fixture-key", metadata.read_text())
                self.assertEqual(env["SHANNON_AI_MODEL"], "cyber:upstream/model")
                self.assertIn("--follow", command)
                self.assertIn("repo with spaces", command)
                self.assertEqual(json.loads(metadata.read_text())["providers"]["cyber"]["api"], "openai-completions")
            self.assertFalse(metadata.exists())

    def test_cannot_reuse_builtin_free_model_credentials(self):
        with tempfile.TemporaryDirectory(dir=HERE) as directory:
            root, config = self.fixture(directory)
            with self.assertRaisesRegex(ValueError, "no transferable API"):
                toolkit.selected_model("opencode/free", config, root)
            with self.assertRaisesRegex(ValueError, "no transferable API"):
                toolkit.selected_model("claude/host", config, root)

    def test_version_is_available_without_model_key_or_engine(self):
        with tempfile.TemporaryDirectory(dir=HERE) as directory, patch.dict(os.environ, {"CYBER_TOOLS_HOME": directory}):
            root, _ = self.fixture(directory)
            with patch.object(toolkit, "selected_model", side_effect=AssertionError("must not read credentials")):
                with toolkit.model_command("strix", ["--version"], "", root / "missing", root) as (command, _):
                    self.assertEqual(command[-1], "--version")
                with toolkit.model_command("shannon", ["help", "start"], "", root / "missing", root) as (command, _):
                    self.assertEqual(command[-2:], ["help", "start"])

    def test_kali_offline_by_default_and_bounded(self):
        command = toolkit.kali_command(["--", "printf", "one argument"])
        self.assertEqual(command[command.index("--network") + 1], "none")
        self.assertEqual(command[-1], "one argument")
        for flag in ("--read-only", "--cap-drop=ALL", "--pids-limit=128", "--memory=2g", "--pull=never"):
            self.assertIn(flag, command)
        self.assertFalse(any("docker.sock" in part for part in command))
        self.assertEqual(toolkit.kali_command(["--network", "--", "curl", "https://example.com"])[-3:],
                         [toolkit.KALI_IMAGE, "curl", "https://example.com"])

    def test_refuses_rootful_engine_and_overrides_remote_endpoint(self):
        with patch.dict(os.environ, {"DOCKER_HOST": "tcp://remote:2375", "DOCKER_CONTEXT": "remote", "SUDO_USER": "fixture"}):
            self.assertNotIn("DOCKER_CONTEXT", toolkit.runtime_env())
            self.assertNotIn("SUDO_USER", toolkit.runtime_env())
            self.assertTrue(toolkit.runtime_env()["DOCKER_HOST"].startswith("unix:///"))
        with patch.object(toolkit, "run", return_value=subprocess.CompletedProcess([], 0, stdout='["name=seccomp"]')):
            with self.assertRaisesRegex(ValueError, "rootless"):
                toolkit.engine()

    def test_install_requires_opt_in_without_downloading(self):
        result = subprocess.run(["python3", "-B", "toolkit.py", "install", "strix"], cwd=HERE,
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 2)
        self.assertIn("explicitly pass --yes", result.stderr)


if __name__ == "__main__":
    unittest.main()
