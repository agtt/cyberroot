#!/usr/bin/env python3
"""Prompt line editor for the cyber interface (stdlib only).

Typing "/" shows matching commands under the prompt while you type; Up/Down pick,
Tab completes, Enter runs the highlighted command, Esc hides the list.
Without a list: Up/Down browse history, usual readline-style editing keys work.

Usage: lineedit.py PROMPT [HISTORY_FILE]
  CYBER_CMDS         "/name  description" lines (the /help text)
  CYBER_CMD_ALIASES  "/s=/sessions ..." short names submitted as typed; their command is listed first
Ctrl-C clears the line; on an empty line it asks once more, then exits. Ctrl-D on an empty
line exits. Ctrl-Z suspends (fg resumes).
Prints the entered line on stdout. Exit: 0 line, 3 quit; anything else means
"use the plain readline prompt instead".
"""
import codecs
import os
import re
import select
import signal
import sys
import termios
import time
import tty
import unicodedata

ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|[\x01\x02]")
MAX_ITEMS = 8
# Theme colours from ailab (CYBER_C_*): selected item, other commands, descriptions, typed text.
if os.environ.get("NO_COLOR"):
    C_SEL = C_CMD = C_DIM = C_TXT = C_0 = ""
else:
    env = os.environ.get
    C_SEL, C_CMD, C_DIM, C_TXT, C_0 = (env("CYBER_C_SEL", "\x1b[1;36m"), env("CYBER_C_CMD", ""),
                                       env("CYBER_C_DIM", "\x1b[2m"), env("CYBER_C_TXT", ""), "\x1b[0m")


def width(s):
    return sum(0 if unicodedata.combining(ch) else 2 if unicodedata.east_asian_width(ch) in "WF" else 1
               for ch in ANSI.sub("", s))


def clip(s, n):
    out, w = "", 0
    for ch in s:
        cw = width(ch)
        if w + cw > n:
            return out[:-1] + "…" if out else ""
        out, w = out + ch, w + cw
    return out


def parse_commands(text):
    return [(m[1], m[2].strip()) for m in re.finditer(r"^(/\S+)[ \t]*(.*)$", text, re.M)]


def suggest(text, commands, aliases=None):
    """Commands for a "/..." word: alias target, exact, prefix, substring, then subsequence matches."""
    if not text.startswith("/") or any(c.isspace() for c in text):
        return []
    target = (aliases or {}).get(text)
    q = text[1:].lower()

    def subseq(name):
        it = iter(name)
        return all(ch in it for ch in q)

    tiers = ([], [], [], [])
    for cmd in commands:
        name = cmd[0][1:].lower()
        if name == q or cmd[0] == target:
            tiers[0].append(cmd)
        elif name.startswith(q):
            tiers[1].append(cmd)
        elif q in name:
            tiers[2].append(cmd)
        elif subseq(name):
            tiers[3].append(cmd)
    return [c for tier in tiers for c in tier]


def load_history(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = [l.rstrip("\n") for l in f if l.strip() and not re.match(r"#\d+$", l.strip())]
    except OSError:
        return []
    out = []
    for l in lines[-1000:]:
        if not out or out[-1] != l:
            out.append(l)
    return out


class Editor:
    def __init__(self, fd, prompt, commands, aliases, history, saved=None):
        self.fd, self.commands, self.aliases, self.hist, self.saved = fd, commands, aliases, history, saved
        self.notice, self.ctrl_c = "", 0.0
        self.known = {n for n, _ in commands} | set(aliases) | {f"/{i}" for i in range(1, 10)}
        self.prompt = prompt.replace("\x01", "").replace("\x02", "")
        self.pw = width(self.prompt)
        self.buf, self.pos, self.row = [], 0, 0
        self.hidx, self.draft, self.paste = len(history), "", False
        self.changed()

    @property
    def text(self):
        return "".join(self.buf)

    def changed(self, hidden=False):
        self.sel, self.top, self.moved, self.hidden = 0, 0, False, hidden

    def set_text(self, s, hidden=False):
        self.buf, self.pos = list(s), len(s)
        self.changed(hidden)

    def items(self):
        return [] if self.hidden else suggest(self.text, self.commands, self.aliases)

    def write(self, s):
        os.write(self.fd, s.encode("utf-8", "replace"))

    def render(self, menu=True):
        try:
            cols = max(20, os.get_terminal_size(self.fd).columns)
        except OSError:
            cols = 80
        out = [f"\x1b[{self.row}A" if self.row else "", "\r\x1b[J", self.prompt, C_TXT + self.text + C_0]
        total = self.pw + width(self.text)
        if total and total % cols == 0:
            out.append(" \r")  # leave the pending-wrap state so rows stay predictable
        cur = total // cols
        items = self.items() if menu else []
        if items:
            self.sel = min(self.sel, len(items) - 1)
            self.top = min(max(self.top, self.sel - MAX_ITEMS + 1), self.sel)
            nw = max(width(n) for n, _ in self.commands)
            for i in range(self.top, min(len(items), self.top + MAX_ITEMS)):
                name, desc = items[i]
                mark, color = ("❯ ", C_SEL) if i == self.sel else ("  ", C_CMD)
                left = mark + name.ljust(nw) + "  "
                out.append("\r\n" + color + left + C_0 + C_DIM + clip(desc, cols - 1 - width(left)) + C_0)
                cur += 1
            if len(items) > MAX_ITEMS:
                out.append(f"\r\n{C_DIM}  {self.sel + 1}/{len(items)} · ↑↓ pick · Tab complete · Esc hide{C_0}")
                cur += 1
        if menu and not items and self.notice:
            out.append(f"\r\n{C_DIM}  {self.notice}{C_0}")
            cur += 1
        trow, tcol = divmod(self.pw + width("".join(self.buf[:self.pos])), cols)
        out.append((f"\x1b[{cur - trow}A" if cur > trow else "") + "\r" + (f"\x1b[{tcol}C" if tcol else ""))
        self.row = trow
        self.write("".join(out))

    def suspend(self):
        """Ctrl-Z: give the terminal back, stop the whole job like a shell would, redraw after fg."""
        self.render(menu=False)
        self.write("\r\n\x1b[?2004l")
        if self.saved:
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self.saved)
        os.killpg(os.getpgrp(), signal.SIGTSTP)
        tty.setraw(self.fd)
        self.write("\x1b[?2004h")
        self.row = 0

    def finish(self, suffix=""):
        self.pos = len(self.buf)
        self.render(menu=False)
        self.write(suffix + "\r\n")

    def keys(self):
        dec = codecs.getincrementaldecoder("utf-8")("replace")

        def ready(t=0.03):
            return select.select([self.fd], [], [], t)[0]

        while True:
            b = os.read(self.fd, 1)
            if not b:
                return
            if b == b"\x1b":
                seq = b
                if ready():
                    c = os.read(self.fd, 1)
                    seq += c
                    if c in (b"[", b"O"):
                        while ready(0.05):
                            c = os.read(self.fd, 1)
                            seq += c
                            if 0x40 <= c[0] <= 0x7E:
                                break
                yield seq.decode("latin-1")
                continue
            ch = dec.decode(b)
            if ch:
                yield ch

    def word_left(self):
        p = self.pos
        while p and not self.buf[p - 1].isalnum():
            p -= 1
        while p and self.buf[p - 1].isalnum():
            p -= 1
        return p

    def word_right(self):
        p, n = self.pos, len(self.buf)
        while p < n and not self.buf[p].isalnum():
            p += 1
        while p < n and self.buf[p].isalnum():
            p += 1
        return p

    def history(self, step):
        if not self.hist:
            return
        if self.hidx == len(self.hist):
            self.draft = self.text
        self.hidx = max(0, min(len(self.hist), self.hidx + step))
        # Recalled lines keep the list hidden so Up/Down keep walking history.
        self.set_text(self.hist[self.hidx] if self.hidx < len(self.hist) else self.draft, hidden=True)

    def run(self):
        self.render()
        for k in self.keys():
            items = self.items()
            if k != "\x03":
                self.notice = ""
            if self.paste and k in ("\r", "\n", "\t"):
                k = " "
            if k == "\x1b[200~":
                self.paste = True
            elif k == "\x1b[201~":
                self.paste = False
            elif k in ("\r", "\n"):
                text = self.text
                if items and (self.moved or text not in self.known):
                    text = items[self.sel][0]
                self.set_text(text)
                self.finish()
                return 0, text
            elif k == "\x03":
                if self.buf:
                    self.set_text("")
                elif time.monotonic() - self.ctrl_c < 2:
                    self.finish()
                    return 3, ""
                else:
                    self.ctrl_c, self.notice = time.monotonic(), "press Ctrl-C again to exit"
            elif k == "\x1a":
                self.suspend()
            elif k == "\x04" and not self.buf:
                self.finish()
                return 3, ""
            elif k in ("\x04", "\x1b[3~"):
                if self.pos < len(self.buf):
                    del self.buf[self.pos]
                    self.changed()
            elif k in ("\x7f", "\x08"):
                if self.pos:
                    self.pos -= 1
                    del self.buf[self.pos]
                    self.changed()
            elif k == "\t":
                if items:
                    self.set_text(items[self.sel][0] + " ")
            elif k in ("\x1b[A", "\x10", "\x1b[Z"):
                if items:
                    self.sel, self.moved = (self.sel - 1) % len(items), True
                elif k != "\x1b[Z":
                    self.history(-1)
            elif k in ("\x1b[B", "\x0e"):
                if items:
                    self.sel, self.moved = (self.sel + 1) % len(items), True
                else:
                    self.history(1)
            elif k == "\x1b":
                self.hidden = True
            elif k in ("\x1b[D", "\x02"):
                self.pos = max(0, self.pos - 1)
            elif k in ("\x1b[C", "\x06"):
                self.pos = min(len(self.buf), self.pos + 1)
            elif k in ("\x1b[H", "\x1bOH", "\x1b[1~", "\x01"):
                self.pos = 0
            elif k in ("\x1b[F", "\x1bOF", "\x1b[4~", "\x05"):
                self.pos = len(self.buf)
            elif k in ("\x1bb", "\x1b[1;3D", "\x1b[1;5D", "\x1b[1;9D"):
                self.pos = self.word_left()
            elif k in ("\x1bf", "\x1b[1;3C", "\x1b[1;5C", "\x1b[1;9C"):
                self.pos = self.word_right()
            elif k == "\x15":
                del self.buf[:self.pos]
                self.pos = 0
                self.changed()
            elif k == "\x0b":
                del self.buf[self.pos:]
                self.changed()
            elif k in ("\x17", "\x1b\x7f"):
                p = self.word_left()
                del self.buf[p:self.pos]
                self.pos = p
                self.changed()
            elif k == "\x0c":
                self.write("\x1b[2J\x1b[H")
                self.row = 0
            elif len(k) == 1 and k >= " " and k != "\x7f":
                self.buf.insert(self.pos, k)
                self.pos += 1
                self.changed()
            self.render()
        self.finish()
        return 3, ""


def main():
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    prompt = sys.argv[1] if len(sys.argv) > 1 else "> "
    commands = parse_commands(os.environ.get("CYBER_CMDS", ""))
    aliases = dict(a.split("=", 1) for a in os.environ.get("CYBER_CMD_ALIASES", "").split() if "=" in a)
    history = load_history(sys.argv[2]) if len(sys.argv) > 2 else []
    try:
        fd = os.open("/dev/tty", os.O_RDWR)
        old = termios.tcgetattr(fd)
    except (OSError, termios.error):
        return 2
    try:
        tty.setraw(fd)
        os.write(fd, b"\x1b[?2004h")
        code, line = Editor(fd, prompt, commands, aliases, history, old).run()
    finally:
        os.write(fd, b"\x1b[?2004l")
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    sys.stdout.write(line)
    return code


if __name__ == "__main__":
    sys.exit(main())
