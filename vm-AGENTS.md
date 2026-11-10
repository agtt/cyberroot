# CyberRoot VM rules

- Reply in the language of the user's latest message, regardless of the language of these rules or the files. Keep code, commands, file names and `CYBER_DONE` unchanged.

- Keep project files (downloads, decompiled output, notes, reports) under `/home/agent/work/<project>/`. Optional integrations are managed separately under `~/.local/share/cyber-tools/` only after an explicit installation choice.
  Never write to `/tmp` or elsewhere: `/tmp` is RAM-backed and the user only sees `~/work` on their own machine.
- Write findings to `~/work/<project>/REPORT.md`, at the top level of the project; each finding needs a file path and line as evidence.
  Only files up to 3 levels deep and under 10 MB are copied to the user's machine, so keep reports and key evidence shallow and small.
- Do not send requests to target systems (APIs, servers) unless the user explicitly asks; static analysis only.

## Tools already installed (do not re-download or reinstall)

- APK: `jadx`, `apktool`, `unzip`, `strings`, `java` (OpenJDK 21). Web/network: `nmap`, `sqlmap`, `ffuf`, `gobuster`, `nikto`, `whatweb`, `hydra`, `curl`, `jq`, `rg`.
- Files downloaded or decompiled earlier stay under `~/work/<project>/`; look there first and reuse them.
- jadx memory: `JAVA_OPTS=-Xmx6g jadx -j 4 ...`. For large or protected APKs feed one dex at a time
  (`unzip app.apk 'classes*.dex'`, then `jadx classesN.dex`); when memory runs out jadx silently leaves partial output, so grep its log for OutOfMemoryError.
- If a tool is missing, install it under `~/tools/` (there is no sudo) and tell the user.
- When a project is finished, delete large intermediate output you no longer need (decompiled trees, extracted archives) to keep the disk small.

## Keep working

- Optional integrations: `~/.local/bin/cyber-tool status` reports availability and `~/.local/bin/cyber-tool plan strix --json` describes the host-side install commands in dependency order. Kali, Strix, Shannon and the guest rootless Docker engine are not installed by default. Never install them merely because these rules mention them; install only after the user chooses them through `cyber tools install <name>`. If guest administrator prerequisites are missing, report that host-side plan; do not try to acquire sudo or connect to the computer's Docker socket.
- Installed tools can be invoked with `~/.local/bin/cyber-tool run strix --model provider/model -- --target <authorized-target>` or `run shannon --model provider/model -- start -u <authorized-url> -r <guest-repository>`. They reuse that provider's configured API key without writing it into reports. OpenCode free models and host Claude sessions cannot supply transferable credentials.
- `~/.local/bin/cyber-tool run kali -- <command>` is network-off by default. Add `--network` before the command separator only when the user explicitly authorizes network testing. Work files live at `/work` in Kali, mapped from this VM's `~/work`, never from the physical host.

- Do not ask the user questions, wait for approval, or end with "I can do X if you want". If there are several ways forward, pick the most sensible one and continue.
- If a tool fails (web search, download, memory), try another route; do not get stuck on the same error.
- When the whole task is really finished (report written and checked), write only `CYBER_DONE` on the last line of your final message (exactly, untranslated). Do not write it if the task is not finished.
- For simple questions or chat, do not invent work: answer, then end with `CYBER_DONE`.

## Spend tokens carefully

- Never print large files or command output into the conversation. Search first (`rg -n`, `grep -c`), then read only the lines you need (`sed -n 'A,Bp'`, `head`, `cut -c1-200`); cap listings (`| head -40`).
- Send long output to a file under the project and read just the relevant part; do not re-read files or re-run commands whose result you already have.
- Batch related shell commands into one call. Keep thinking and replies short: results and next step, no restating the task or narrating each step.
