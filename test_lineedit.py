"""Offline checks for the interface line editor; drives it through a pseudo-terminal."""
import os
from pathlib import Path
import pty
import select
import sys
import tempfile
import time
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lineedit  # noqa: E402

CMDS = "/model     pick a model\n/models    list shortcuts\n/setup     setup\n/sessions  switch session\n/status    status\n/quit      quit"


class SuggestTests(unittest.TestCase):
    def names(self, text):
        return [n for n, _ in lineedit.suggest(text, lineedit.parse_commands(CMDS))]

    def test_ranking(self):
        self.assertEqual(self.names("/model"), ["/model", "/models"])
        self.assertEqual(self.names("/se")[:2], ["/setup", "/sessions"])
        self.assertEqual(self.names("/ss"), ["/sessions", "/status"])
        self.assertEqual(len(self.names("/")), 6)
        self.assertEqual(lineedit.suggest("/s", lineedit.parse_commands(CMDS), {"/s": "/sessions"})[0][0], "/sessions")

    def test_no_list_for_tasks_or_arguments(self):
        self.assertEqual(self.names("scan this"), [])
        self.assertEqual(self.names("/model fast"), [])
        self.assertEqual(self.names("/zzz"), [])


class TerminalTests(unittest.TestCase):
    def type_keys(self, keys, history=""):
        with tempfile.TemporaryDirectory() as tmp:
            out, hist = Path(tmp, "out"), Path(tmp, "hist")
            hist.write_text(history)
            pid, fd = pty.fork()
            if pid == 0:
                os.dup2(os.open(out, os.O_WRONLY | os.O_CREAT), 1)
                env = {**os.environ, "CYBER_CMDS": CMDS, "CYBER_CMD_ALIASES": "/s=/sessions /m=/model"}
                os.execve(sys.executable, [sys.executable, "-I", "-B", str(HERE / "lineedit.py"), "> ", str(hist)], env)
            time.sleep(0.3)
            for k in keys:
                os.write(fd, k.encode())
                time.sleep(0.1)
            deadline = time.time() + 5
            while time.time() < deadline:
                if select.select([fd], [], [], 0.1)[0]:
                    try:
                        os.read(fd, 4096)
                    except OSError:
                        break
                if os.waitpid(pid, os.WNOHANG)[0]:
                    break
            else:
                os.kill(pid, 9)
                self.fail("editor did not exit")
            os.close(fd)
            return out.read_text()

    def test_enter_runs_highlighted_command(self):
        self.assertEqual(self.type_keys(["/mo", "\r"]), "/model")
        self.assertEqual(self.type_keys(["/mo", "\x1b[B", "\r"]), "/models")

    def test_tab_completes_and_aliases_stay(self):
        self.assertEqual(self.type_keys(["/sta", "\t", "x", "\r"]), "/status x")
        self.assertEqual(self.type_keys(["/s", "\r"]), "/s")
        self.assertEqual(self.type_keys(["/s", "\x1b[B", "\r"]), "/setup")

    def test_tasks_and_history(self):
        self.assertEqual(self.type_keys(["hello", "\x1b[D", "X", "\r"]), "hellXo")
        self.assertEqual(self.type_keys(["\x1b[A", "\r"], history="/models\nold task\n"), "old task")
        self.assertEqual(self.type_keys(["\x1b[A", "\x1b[A", "\r"], history="/models\nold task\n"), "/models")


if __name__ == "__main__":
    unittest.main()
