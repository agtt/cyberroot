"""Render a lightweight, explicitly scripted 25-second README walkthrough."""
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRAMES = [
    ("cyber doctor", ["OK    host prerequisites available", "WARN  VM stopped — not started by doctor",
                      "INFO  optional tools stay optional", "      No installs. No model requests."]),
    ("cyber tools plan strix --json", ['"automatic_install": false', '"commands": [engine, strix]',
                                          "Kali and Shannon are not selected.", "Inspect a plan before installing anything."]),
    ("/model research", ["Selected: research · example/research-model", "Use your own compatible API provider.",
                         "Switch models and resume sessions in the terminal."]),
    ("cyber strix --model research -- --help", ["usage: strix [-h] [-v] ...", "Optional Strix CLI; configured API model reused for scans.",
                                                   "Help/version do not call the model."]),
    ("cyber pull", ["Copy small deliverables to out/work/ when ready.", "Large intermediate files stay in the guest.",
                     "OpenCode + optional Kali, Strix and Shannon.", "Your models. Your workspace."]),
]


def main():
    output = ROOT / "docs"
    output.mkdir(exist_ok=True)
    parts = ['''<svg xmlns="http://www.w3.org/2000/svg" width="960" height="350" viewBox="0 0 960 350" role="img" aria-labelledby="title desc">
<title id="title">CyberRoot terminal walkthrough</title>
<desc id="desc">A scripted 25-second preview of diagnostics, optional install plans, model selection, tool help and report sync. No live scan or model result is shown.</desc>
<style>text{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:17px;fill:#b9c7d9}.heading{font-size:13px;fill:#90a3bb}.command{fill:#81e6c2;font-size:19px}.note{font-size:12px;fill:#8a9bb0}@media(prefers-reduced-motion:reduce){.scene{display:none}.scene-0{display:block;opacity:1!important}}</style>
<rect width="960" height="350" rx="16" fill="#101821"/>
<path d="M0 44H960" stroke="#263443"/>
<circle cx="25" cy="23" r="6" fill="#f07e78"/><circle cx="46" cy="23" r="6" fill="#e9c16a"/><circle cx="67" cy="23" r="6" fill="#79c7a7"/>
<text x="95" y="28" class="heading">CyberRoot / isolated AI security workspace</text>
<text x="931" y="28" text-anchor="end" class="heading">EARLY PREVIEW</text>''']
    events = [{"version": 2, "width": 106, "height": 18, "title": "CyberRoot — scripted walkthrough (no live scan)", "env": {"TERM": "xterm-256color"}}]
    for index, (command, lines) in enumerate(FRAMES):
        values = ";".join("1" if frame == index else "0" for frame in range(5))
        parts.append(f'<g class="scene scene-{index}" opacity="{1 if index == 0 else 0}"><animate attributeName="opacity" calcMode="discrete" values="{values}" keyTimes="0;0.2;0.4;0.6;0.8" dur="25s" repeatCount="indefinite"/>')
        parts.append(f'<text x="30" y="92" class="command">$ {html.escape(command)}</text>')
        for line_index, line in enumerate(lines):
            parts.append(f'<text x="30" y="{138 + line_index * 32}">{html.escape(line)}</text>')
        parts.append("</g>")
        terminal = "\x1b[2J\x1b[H\x1b[2mCyberRoot — scripted preview / no live scan\x1b[0m\r\n\r\n"
        terminal += "\x1b[32m$ " + command + "\x1b[0m\r\n\r\n" + "\r\n".join(lines) + "\r\n"
        events.append([index * 5.0, "o", terminal])
    parts.append('<path d="M30 293H930" stroke="#263443"/><text x="30" y="321" class="note">SCRIPTED WALKTHROUGH · 25 SEC · NO LIVE SCANS, CREDENTIALS OR MODEL RESULTS</text></svg>')
    events.append([25.0, "o", "\r\n\x1b[2mEnd of scripted preview.\x1b[0m\r\n"])
    (output / "demo.svg").write_text("\n".join(parts) + "\n")
    (output / "demo.cast").write_text("\n".join(json.dumps(event, ensure_ascii=False) for event in events) + "\n")


if __name__ == "__main__":
    main()
