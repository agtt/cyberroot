"""Offline regression checks; no VM, model calls, or owner configuration changes."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
SOURCE = (HERE / "ailab").read_text()


def function(name):
    return re.search(r"^" + name + r"\(\) \{.*?^\}", SOURCE, re.M | re.S)[0]


class CliTests(unittest.TestCase):
    def run_shell(self, body, **env):
        return subprocess.run(["bash", "-c", body], cwd=HERE,
                              env={**os.environ, **env}, capture_output=True,
                              text=True, timeout=10)

    def state(self, text):
        assignments = "\n".join(line for line in SOURCE.splitlines()
                                if line.startswith(("ASK_RE=", "TOOL_RE=")))
        result = subprocess.run(["bash", "-c", assignments + '\nexport CYBER_ASK_RE="$ASK_RE" CYBER_TOOL_RE="$TOOL_RE"\nawk -f round-state.awk'],
                                cwd=HERE, input=text, text=True,
                                capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        return tuple(map(int, result.stdout.split()))

    def test_error_classification_and_completion(self):
        self.assertEqual(self.state("Error: could not generate response\n"), (0, 1, 0, 0))
        self.assertEqual(self.state("Error: rate limit exceeded (429)\n"), (0, 1, 1, 0))
        self.assertEqual(self.state("Error: corporate endpoint failed\nquota discussed below\n"), (0, 1, 0, 0))
        self.assertEqual(self.state("Example: CYBER_DONE; still working\n")[0], 0)
        self.assertEqual(self.state("CYBER_DONE\nmore work remains\n")[0], 0)
        self.assertEqual(self.state("CYBER_DONE\n\n")[0], 1)
        self.assertEqual(self.state("Error: failure\nCYBER_DONE\n")[:2], (1, 1))
        self.assertEqual(self.state("$ inspect\noutput\n")[3], 1)
        self.assertEqual(self.state("Would you like me to continue?\n")[3], 1)
        self.assertEqual(self.state("Changes completed.\n")[3], 0)

    def test_logs_lists_newest_first_and_opens_by_number(self):
        with tempfile.TemporaryDirectory() as directory:
            logs = Path(directory, "logs")
            logs.mkdir()
            Path(logs, "20261109-080000-old-model.log").write_text("old\n")
            Path(logs, "20261110-090000-4242-provider-model.log").write_text("new\n")
            harness = 'OUT="$TEST_OUT"; C_C=; C_B=; C_D=; C_0=\nsay() { printf "%s\\n" "$*" >&2; }\n' + function("logs_command")
            listed = self.run_shell(harness + "\nlogs_command", TEST_OUT=directory)
            self.assertEqual(listed.returncode, 0, listed.stderr)
            rows = listed.stderr.splitlines()
            self.assertIn("2026-11-10 09:00  provider-model", rows[0])
            self.assertIn("2026-11-09 08:00  old-model", rows[1])
            opened = self.run_shell(harness + "\nlogs_command 2", TEST_OUT=directory)
            self.assertEqual(opened.stdout, "old\n")
            self.assertEqual(self.run_shell(harness + "\nlogs_command 9", TEST_OUT=directory).returncode, 2)

    def test_pull_only_advances_after_success(self):
        with tempfile.TemporaryDirectory(dir=HERE) as directory:
            out = Path(directory)
            (out / "work").mkdir()
            marker = out / ".lastpull"
            marker.write_text("100\n")
            harness = 'set -eo pipefail\nOUT="$TEST_OUT"\n' + function("pull") + '''
lsh() { if [[ "$1" == date ]]; then echo 200; else return 1; fi; }
pull
'''
            result = self.run_shell(harness, TEST_OUT=directory)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("result copy failed", result.stderr)
            self.assertEqual(marker.read_text(), "100\n")
            harness += '''
lsh() { if [[ "$1" == date ]]; then echo 200; else tar -cf - -T /dev/null; fi; }
pull
'''
            result = self.run_shell(harness, TEST_OUT=directory)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(marker.read_text(), "200\n")

    def logged(self, output, rounds="1", logger=None):
        with tempfile.TemporaryDirectory(dir=HERE) as directory:
            out = Path(directory)
            # Mock caffeinate records its PID; no host sleep settings are changed.
            executable = out / "caffeinate"
            executable.write_text('#!/bin/bash\necho $$ > "$TEST_OUT/awake.pid"\nexec /bin/sleep 30\n')
            executable.chmod(0o755)
            here = HERE
            if logger is not None:
                here = out
                (out / "livelog.pl").write_text(logger)
                (out / "livelog.pl").chmod(0o755)
            assignments = "\n".join(line for line in SOURCE.splitlines()
                                    if line.startswith(("ASK_RE=", "TOOL_RE=", "CONT_MSG=", "DONE_MARK=")))
            harness = '''set -uo pipefail
HERE="$TEST_HERE"; OUT="$TEST_OUT"; MODE=local; HOST=""
C_B=; C_D=; C_R=; C_G=; C_Y=; C_M=; C_C=; C_0=
say() { printf '%s\\n' "$*" >&2; }
short_of() { echo fixture; }
fdur() { echo "$1"; }
fallbacks() { :; }
pull() { :; }
sleep() { :; }
oc_run() { printf '%s\\n' "$TEST_OUTPUT"; }
''' + assignments + "\n" + function("run_logged") + '\nrun_logged fixture/model task'
            result = self.run_shell(harness, TEST_HERE=str(here), TEST_OUT=directory,
                                    TEST_OUTPUT=output, AILAB_ROUNDS=rounds,
                                    PATH=str(out) + os.pathsep + os.environ["PATH"])
            pid_file = out / "awake.pid"
            if pid_file.exists():
                with self.assertRaises(ProcessLookupError):
                    os.kill(int(pid_file.read_text()), 0)
            return result

    def test_success_releases_keep_awake(self):
        result = self.logged("CYBER_DONE")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("done", result.stderr)

    def test_round_limit_is_not_success(self):
        result = self.logged("$ inspect\noutput")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("round limit reached", result.stderr)
        self.assertNotIn("✔ done", result.stderr)

    def test_generation_error_is_retried_without_false_success_or_cooldown(self):
        result = self.logged("Error: could not generate response\nCYBER_DONE", rounds="12")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("4 errors in a row", result.stderr)
        self.assertNotIn("all limited", result.stderr)
        self.assertNotIn("✔ done", result.stderr)

    def test_logger_failure_is_not_success(self):
        result = self.logged("CYBER_DONE", logger="#!/bin/bash\ncat >/dev/null\nexit 1\n")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("log output failed", result.stderr)


if __name__ == "__main__":
    unittest.main()
