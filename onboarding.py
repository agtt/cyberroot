"""Read-only diagnostics and explicit first-run configuration; no model calls."""
import argparse
import json
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import subprocess
import sys
from urllib.parse import urlsplit

from quota import jsonc
from toolkit import install_plan


def model_rows(here):
    source = here / "models.txt"
    if not source.is_file():
        source = here / "models.example.txt"
    return [fields[:2] for line in source.read_text().splitlines()
            if (fields := line.split()) and not fields[0].startswith("#") and len(fields) >= 2]


def atomic_write(path, text):
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, "w") as output:
            output.write(text)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()  # only this call's temporary file


def add_provider(here, name, base, alias, model):
    for value in (name, alias):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", value):
            raise ValueError("Provider and shortcut names must use letters, numbers, dots, dashes or underscores.")
    url = urlsplit(base)
    if url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError("Use an HTTPS OpenAI-compatible API base URL without credentials or query values.")
    if not model or re.search(r"[\s\x00-\x1f]", model):
        raise ValueError("Enter a non-empty upstream model ID without whitespace.")
    path = here / "opencode.jsonc"
    config = jsonc(path.read_text())
    providers = config.setdefault("providers", {})
    if name in providers or any(row[0] == alias for row in model_rows(here)):
        raise ValueError("Provider or shortcut already exists; existing configuration was kept. Choose an existing model or a different name.")
    providers[name] = {"name": name, "package": "@opencode/ai/providers/openai-compatible",
        "settings": {"baseURL": base, "apiKey": f"{{file:/home/agent/.secrets/{name}-api-key}}"},
        "models": {alias: {"modelID": model, "name": model}}}
    # Preserve every existing setting; JSONC is serialized as valid, formatted JSON.
    atomic_write(path, json.dumps(config, indent=2) + "\n")
    with (here / "models.txt").open("a") as output:
        output.write(f"\n{alias} {name}/{alias}\n")
    return f"{name}/{alias}"


def capture(command):
    return subprocess.run(command, capture_output=True, text=True, timeout=8, check=True).stdout


def diagnose(here, secrets, target, vm="ai-lab", live=False):
    checks = []
    def check(name, status, detail):
        checks.append({"name": name, "status": status, "detail": detail})
    mode, _, host = target.partition(" ")
    remote = mode == "vps" and bool(host)
    for command in ("bash", "git", "perl", "python3", "curl", "ssh"):
        check(command, "ok" if shutil.which(command) else "error", "available" if shutil.which(command) else "missing host prerequisite")
    check("fzf", "ok" if shutil.which("fzf") else "warn", "optional picker available" if shutil.which("fzf") else "optional; numbered menus still work")
    if not remote and (platform.system() == "Linux" or platform.machine() == "x86_64"):
        binary = "qemu-system-aarch64" if platform.machine() in ("aarch64", "arm64") else "qemu-system-x86_64"
        check("QEMU", "ok" if shutil.which(binary) else "error", "available" if shutil.which(binary) else "required for this local VM driver; install it or choose SSH")
        if platform.system() == "Linux" and not os.access("/dev/kvm", os.R_OK | os.W_OK):
            check("KVM", "warn", "hardware acceleration unavailable; local QEMU may be slow/unavailable, especially in WSL2; SSH is an alternative")
    running = False
    prefix = []
    if remote:
        check("target", "ok", "SSH target configured; no connection without --live")
        if live:
            prefix = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=4", host, "--"]
            try:
                capture([*prefix, "true"])
                running = True
                check("SSH", "ok", "reachable")
            except (OSError, subprocess.SubprocessError):
                check("SSH", "error", "unreachable or authentication required")
    elif not shutil.which("limactl"):
        check("Lima", "error", "required for local VM; install Lima or choose an SSH target")
    else:
        try:
            state = json.loads(capture(["limactl", "list", "--json", vm]))
            running = state.get("status") == "Running"
            check("VM", "ok" if running else "warn", "running" if running else "stopped; doctor did not start it")
            prefix = ["limactl", "shell", "--workdir", "/", vm]
        except (OSError, ValueError, subprocess.SubprocessError):
            check("VM", "warn", "not created or not available; run cyber setup/up when ready")
    tools = {name: {"optional": True, "installed": None} for name in ("engine", "kali", "strix", "shannon")}
    if running:
        def guest(arguments):
            return capture([*prefix, shlex.join(arguments)] if remote else [*prefix, *arguments])
        try:
            table = "ailab_agent" if remote else "ailab"
            firewall = guest(["sudo", "-n", "nft", "list", "table", "inet", table])
            valid = "drop" in firewall and ("skuid" in firewall if remote else "@blocked4" in firewall)
            check("guest firewall", "ok" if valid else "error", "loaded" if valid else "expected rules missing")
        except (OSError, subprocess.SubprocessError):
            check("guest firewall", "error", "could not verify rules; check guest setup before running a task")
        try:
            result = json.loads(guest(["sudo", "-n", "-u", "agent", "-H", "python3", "-B",
                "/home/agent/.local/share/cyber-tools/helpers/toolkit.py", "status", "--json"]))
            if not isinstance(result, dict):
                raise ValueError("Invalid tool status")
            for name in tools:
                value = result.get(name)
                installed = value.get("installed") if isinstance(value, dict) else None
                tools[name]["installed"] = installed if type(installed) is bool else None
            check("optional tools", "ok", "installation state checked; no downloads")
        except (OSError, ValueError, subprocess.SubprocessError):
            check("optional tools", "warn", "guest helpers unavailable; run cyber sync")
    else:
        check("optional tools", "warn", "not checked while target is stopped or offline; all remain optional")
    try:
        rows = model_rows(here)
        check("models", "ok" if rows else "error", f"{len(rows)} configured shortcuts")
        config_path = here / "opencode.jsonc"
        if not config_path.is_file():
            config_path = here / "opencode.example.jsonc"
            check("local settings", "warn", "using shipped templates; run cyber setup to configure, no files created")
        config = jsonc(config_path.read_text())
        providers = config.get("providers", {})
        ready = 0
        for provider in providers.values():
            settings = provider.get("settings", {})
            reference = settings.get("apiKey", "")
            match = re.fullmatch(r"\{file:/home/agent/\.secrets/([A-Za-z0-9._-]+)\}", reference)
            if match:
                path = secrets / match[1]
                present = path.is_file() and path.stat().st_size > 0
            elif reference.startswith("{env:") and reference.endswith("}"):
                present = bool(os.environ.get(reference[5:-1]))
            else:
                present = bool(reference and not reference.startswith("{"))
            ready += bool(present and settings.get("baseURL", "").startswith("https://"))
        check("API providers", "ok" if ready else "warn", f"{ready} configured with credentials present; no key values displayed or authenticated" if ready else "none ready; free OpenCode models can still be used, optional AI tools need your own API provider")
    except (OSError, ValueError, TypeError, AttributeError):
        check("model configuration", "error", "invalid or missing local configuration; check cyber config")
    return {"ok": not any(item["status"] == "error" for item in checks),
            "target": "ssh" if remote else "local", "target_running": running,
            "checks": checks, "tools": tools, "model_requests": 0, "installations": 0}


def prompt(text, default=""):
    return input(f"{text}" + (f" [{default}]" if default else "") + ": ").strip() or default


def offer_cyber_command(here, ask, home=None, shell=None):
    """Offer the short `cyber` command: one alias line in the shell rc file, asked first and never duplicated."""
    home = Path(home or Path.home())
    shell = Path(os.environ.get("SHELL", "") if shell is None else shell).name
    rc = home / (".zshrc" if shell == "zsh" else ".bashrc")
    line = f"alias cyber={shlex.quote(str(Path(here).resolve() / 'ailab'))}"
    try:
        text = rc.read_text(encoding="utf-8")
    except OSError:
        text = ""
    if re.search(r"^\s*alias\s+cyber=", text, re.M):
        print("\nStart it any time with: cyber")
        return False
    if ask and prompt(f"Add a short `cyber` command to ~/{rc.name}? Y/n", "y").lower() in ("y", "yes"):
        with open(rc, "a", encoding="utf-8") as f:
            f.write(("\n" if text and not text.endswith("\n") else "") + "\n# CyberRoot\n" + line + "\n")
        print(f"Added. Open a new terminal (or run: source ~/{rc.name}), then just type: cyber")
        return True
    print(f"\nTip: for the short `cyber` command, add this line to ~/{rc.name}:\n  {line}\nUntil then use ./ailab")
    return False


def setup(here, target):
    print("CyberRoot setup — existing settings are kept; optional tools start unselected.\n")
    choice = prompt("Target: 1 local Lima VM, 2 SSH server", "2" if target.startswith("vps ") else "1")
    if choice not in ("1", "2"):
        raise ValueError("Choose 1 or 2.")
    selected_target = "local"
    if choice == "2":
        host = prompt("SSH config alias / user@host", target[4:] if target.startswith("vps ") else "")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._@-]{0,200}", host):
            raise ValueError("Enter a valid SSH host or config alias.")
        selected_target = "vps " + host
    model_choice = prompt("Model: 1 existing shortcut, 2 free OpenCode model, 3 new compatible API provider", "1")
    rows = model_rows(here)
    if model_choice == "3":
        print("This adds one provider and preserves existing settings; JSONC comments are reformatted.")
        name = prompt("Provider name")
        base = prompt("HTTPS OpenAI-compatible base URL")
        upstream = prompt("Upstream model ID")
        alias = prompt("Shortcut name", "research")
        selected_model = add_provider(here, name, base, alias, upstream)
        print(f"Provider added. Enter its key privately with: ./ailab key {name}")
        print("No key is requested or printed by this wizard.")
    else:
        if model_choice == "2":
            rows = [row for row in rows if row[1].startswith("opencode/")]
        elif model_choice != "1":
            raise ValueError("Choose 1, 2 or 3.")
        if not rows:
            raise ValueError("No matching shortcuts. Add a model with cyber add or rerun setup to add a provider.")
        for index, (alias, _) in enumerate(rows, 1):
            print(f"  {index}. {alias}")
        selected = prompt("Model number", "1")
        if not selected.isdigit() or not 1 <= int(selected) <= len(rows):
            raise ValueError("Choose a displayed model number.")
        selected_model = rows[int(selected) - 1][1]
    picked = prompt("Optional integrations (comma-separated kali,strix,shannon; leave empty for none)")
    optional = [] if picked.lower() in ("none", "no", "0") else list(dict.fromkeys(part.strip() for part in picked.split(",") if part.strip()))
    if any(name not in ("kali", "strix", "shannon") for name in optional):
        raise ValueError("Unknown integration; choose kali, strix, shannon or none.")
    if optional and selected_model.startswith(("opencode/", "claude/")) and any(name != "kali" for name in optional):
        print("Strix/Shannon will need a configured API model before scanning; this model's credentials cannot be transferred.")
    atomic_write(here / "target", selected_target + "\n")
    atomic_write(here / "default", selected_model + "\n")
    commands = [["./ailab", "up"]]
    for name in optional:
        for command in install_plan(name)["commands"]:
            if command not in commands:
                commands.append(command)
    print(f"\nSaved target and model. Optional integrations: {', '.join(optional) or 'none'}.")
    print("Planned commands:")
    for command in commands:
        print("  " + shlex.join(command))
    if prompt("Start/provision the target and install only these selected components now? y/N", "n").lower() == "y":
        for command in commands:
            subprocess.run([str(here / "ailab"), *command[1:]], cwd=here, check=True)
    else:
        print("Configuration saved. Nothing downloaded or started; run the commands above when ready.")
    offer_cyber_command(here, ask=sys.stdin.isatty())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("doctor", "setup"))
    parser.add_argument("--here", type=Path, required=True)
    parser.add_argument("--secrets", type=Path, required=True)
    parser.add_argument("--target", default="local")
    parser.add_argument("--vm", default="ai-lab")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--live", action="store_true", help="also check the configured SSH target (no model calls)")
    args = parser.parse_args()
    if args.command == "setup":
        setup(args.here, args.target)
        return
    report = diagnose(args.here, args.secrets, args.target, args.vm, args.live)
    if args.json:
        print(json.dumps(report))
    else:
        print("CyberRoot doctor — read-only; no installs, VM startup or model requests\n")
        for item in report["checks"]:
            print(f'{item["status"].upper():5} {item["name"]}: {item["detail"]}')
        for name, state in report["tools"].items():
            installed = state.get("installed")
            print(f'      {name}: {"installed" if installed else "not installed" if installed is False else "not checked"} (optional)')
    sys.exit(0 if report["ok"] else 1)


if __name__ == "__main__":
    try:
        main()
    except (EOFError, KeyboardInterrupt):
        print("\nSetup cancelled.", file=sys.stderr)
        sys.exit(130)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
    except (OSError, subprocess.SubprocessError):
        print("Setup/diagnostics could not finish. Check the entered values and local prerequisites; no credential values are displayed.", file=sys.stderr)
        sys.exit(1)
