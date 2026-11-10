"""Offline quota and host-adapter regressions. No provider requests or VM startup."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import quota
from test_cli import function

HERE = Path(__file__).resolve().parent


class QuotaTests(unittest.TestCase):
    def test_balances_are_not_confused_with_key_limits(self):
        self.assertEqual(quota.summarize({"limit_remaining": 0, "usage_daily": 2},
                                        {"total_credits": 10, "total_usage": 3}),
                         "account $7.00 · key $0.00 left · today $2.00")
        self.assertEqual(quota.summarize({"limit": None}, None), "key uncapped")
        self.assertIn("unknown", quota.summarize({}, {}))
        self.assertIn("unknown", quota.summarize({"limit_remaining": True}, {}))

    def test_jsonc_preserves_strings_and_urls(self):
        self.assertEqual(quota.jsonc('{/*x*/"url":"https://a//b", "value":",}",//x\n}'),
                         {"url": "https://a//b", "value": ",}"})

    def test_refresh_is_cached_and_persists_no_key_or_provider_metadata(self):
        with tempfile.TemporaryDirectory(dir=HERE) as directory:
            root = Path(directory)
            config, cache = root / "config", root / "cache"
            config.write_text(json.dumps({"providers": {"fixture": {"settings": {
                "baseURL": "https://openrouter.ai/api/v1",
                "apiKey": "fixture-private-key"}}}}))
            with patch.object(quota, "request", return_value={"limit_remaining": 5, "label": "never-store-me"}) as fetch:
                quota.refresh(config, root, cache)
                quota.refresh(config, root, cache)
                self.assertEqual(fetch.call_count, 2)
            self.assertNotIn("fixture-private-key", cache.read_text())
            self.assertNotIn("never-store-me", cache.read_text())
            self.assertEqual(cache.stat().st_mode & 0o777, 0o600)
            self.assertIn("key $5.00 left", quota.label("fixture/model", cache, root / "limited"))
            with patch.object(quota, "request", side_effect=OSError("offline")):
                quota.refresh(config, root, cache, force=True)
            self.assertIn("unknown", quota.label("fixture/model", cache, root / "limited"))

    def test_unknown_provider_never_receives_credentials(self):
        for base in ("https://example.com/api/v1", "http://openrouter.ai/api/v1",
                     "https://openrouter.ai/api/v1?redirect=elsewhere"):
            self.assertIsNone(quota.provider({"baseURL": base, "apiKey": "private"}, HERE))

    def test_cooldown_and_stale_data_are_explicit(self):
        with tempfile.TemporaryDirectory(dir=HERE) as directory:
            root = Path(directory)
            cache, limited = root / "cache", root / "limited"
            cache.write_text(json.dumps({"at": 100, "providers": {"fixture": "account $2.00"}}))
            limited.write_text("100 fixture/model\n")
            label = quota.label("fixture/model", cache, limited, now=300)
            self.assertIn("stale 3m", label)
            self.assertIn("cooldown 27m (local retry, not quota reset)", label)
            self.assertNotIn("cooldown", quota.label("fixture/model", cache, limited, now=1901))
            self.assertIn("unknown", quota.label("opencode/free", cache, limited, now=300))

    def test_platform_driver_and_headless_open(self):
        script = '''source ./platform.sh
uname() { case "$1" in -s) echo Linux;; -m) echo x86_64;; -r) echo microsoft-standard-WSL2;; esac; }
host_platform
local_vm_driver
wslview() { printf '%s\\n' "$1"; }
DISPLAY= WAYLAND_DISPLAY= open_output /fixture/results
'''
        # Do not launch a real desktop app in this test.
        result = subprocess.run(["bash", "-c", script], cwd=HERE, capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), ["wsl2", "qemu", "/fixture/results"])

    def test_automatic_checks_default_off(self):
        with tempfile.TemporaryDirectory(dir=HERE) as directory:
            script = 'HERE="$TEST_HERE"\nquota_data() { echo called >> "$HERE/calls"; }\n' + function("quota_auto_refresh") + '\nquota_auto_refresh'
            import os
            environment = {**os.environ, "TEST_HERE": directory}
            result = subprocess.run(["bash", "-c", script], env=environment, capture_output=True, timeout=5)
            self.assertEqual(result.returncode, 0)
            self.assertFalse((Path(directory) / "calls").exists())
            (Path(directory) / "quota-mode").write_text("on\n")
            result = subprocess.run(["bash", "-c", script], env=environment, capture_output=True, timeout=5)
            self.assertEqual(result.returncode, 0)
            self.assertEqual((Path(directory) / "calls").read_text(), "called\n")


if __name__ == "__main__":
    unittest.main()
