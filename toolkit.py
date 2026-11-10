"""Optional tools, executed as agent inside the VM/SSH target. No host Docker access."""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
from urllib.parse import urlsplit

from quota import jsonc

TOOLS = ("engine", "kali", "strix", "shannon")
STRIX_VERSION = "1.7.0"
SHANNON_VERSION = "3.5.0"
STRIX_HASHES = {
    "aarch64": "9f4a826c5d1e76b5c503e3299807af8549acca2e03734b6603611be275917ede",
    "x86_64": "b8cd7e84d63cbeff6726301a9e08fddedf40fc6a4edcdb4edda8a853b3312de6",
}
KALI_IMAGE = "cyberhutch-kali:1"


def install_plan(selected=None):
    """Machine-readable, offline plan; never installs or starts a target."""
    catalog = {
        "engine": {"optional": True, "version": "upstream rootless Docker", "runtime_requires": []},
        "kali": {"optional": True, "version": KALI_IMAGE, "runtime_requires": ["engine"]},
        "strix": {"optional": True, "version": STRIX_VERSION, "runtime_requires": ["engine"]},
        "shannon": {"optional": True, "version": SHANNON_VERSION, "runtime_requires": ["engine"]},
    }
    choices = [] if selected is None else [*catalog[selected]["runtime_requires"], selected]
    return {"selected": selected, "automatic_install": False, "execution_location": "guest VM or SSH target",
            "tools": catalog, "commands": [["./ailab", "tools", "install", name, "--yes"] for name in choices],
            "api_model_required": selected in ("strix", "shannon"),
            "note": "Execute install commands only after the user explicitly selects this integration. No target scans or paid model calls are part of installation."}


def root():
    return Path(os.environ.get("CYBER_TOOLS_HOME", str(Path.home() / ".local/share/cyber-tools")))


def status_report():
    environment = runtime_env()
    engine_present = bool(shutil.which("docker", path=environment["PATH"]) and
                          shutil.which("dockerd-rootless-setuptool.sh", path=environment["PATH"]))
    image_present = None
    if engine_present and Path(environment["XDG_RUNTIME_DIR"], "docker.sock").is_socket():
        try:
            image_present = bool(run(["docker", "images", "--quiet", KALI_IMAGE],
                                     capture_output=True, text=True, timeout=3).stdout.strip())
        except (OSError, subprocess.SubprocessError):
            pass
    return {name: {"optional": True, "installed": installed} for name, installed in (
        ("engine", engine_present), ("kali", image_present), ("strix", (root() / "strix/strix").is_file()),
        ("shannon", (root() / "shannon/node_modules/.bin/shannon").is_file()))}


def runtime_env():
    env = os.environ.copy()
    # The host launcher changes to the unprivileged guest user. Some upstream
    # CLIs reject leftover sudo metadata even though the effective UID is non-root.
    for key in list(env):
        if key.startswith("SUDO_"):
            env.pop(key)
    env["PATH"] = f'{root() / "bun/bin"}:{Path.home() / "bin"}:' + env.get("PATH", "/usr/bin:/bin")
    env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    env.setdefault("DBUS_SESSION_BUS_ADDRESS", f'unix:path={env["XDG_RUNTIME_DIR"]}/bus')
    # Never inherit a host, rootful, or remote Docker endpoint/context.
    for key in ("DOCKER_CONTEXT", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH"):
        env.pop(key, None)
    env["DOCKER_HOST"] = f'unix://{env["XDG_RUNTIME_DIR"]}/docker.sock'
    return env


def run(command, **kwargs):
    return subprocess.run(command, check=True, env=runtime_env(), **kwargs)


def engine():
    try:
        output = run(["docker", "info", "--format", "{{json .SecurityOptions}}"],
                     capture_output=True, text=True, timeout=15).stdout
    except (OSError, subprocess.SubprocessError) as error:
        raise ValueError("Guest rootless Docker is unavailable; run: cyber tools install engine") from error
    if "name=rootless" not in json.loads(output):
        raise ValueError("A rootless Docker engine inside the target is required; run: cyber tools install engine")


def download(url, destination):
    run(["curl", "-q", "--fail", "--silent", "--show-error", "--location", "--proto", "=https",
         "--proto-redir", "=https", "--max-time", "180", "--output", str(destination), url])


def install(name):
    home = root()
    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    if name == "engine":
        if shutil.which("dockerd-rootless-setuptool.sh", path=runtime_env()["PATH"]):
            run(["dockerd-rootless-setuptool.sh", "install"])
        else:
            with tempfile.TemporaryDirectory(prefix="engine-install-", dir=home) as temporary:
                script = Path(temporary) / "install.sh"
                download("https://get.docker.com/rootless", script)
                run(["sh", str(script)])
        engine()
    elif name == "strix":
        if (home / "strix/strix").is_file():
            print("Strix already installed; no download.")
            return
        arch = platform.machine()
        if arch not in STRIX_HASHES:
            raise ValueError("Strix release supports Linux arm64/x86_64 only.")
        release_arch = "arm64" if arch == "aarch64" else "x86_64"
        with tempfile.TemporaryDirectory(prefix="strix-install-", dir=home) as temporary:
            archive = Path(temporary) / "release.tar.gz"
            download(f"https://github.com/usestrix/strix/releases/download/v{STRIX_VERSION}/strix-{STRIX_VERSION}-linux-{release_arch}.tar.gz", archive)
            digest = hashlib.sha256()
            with archive.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            if digest.hexdigest() != STRIX_HASHES[arch]:
                raise ValueError("Strix release checksum mismatch.")
            staging = Path(temporary) / "unpacked"
            with tarfile.open(archive) as package:
                package.extractall(staging, filter="data")
            executable = staging / f"strix-{STRIX_VERSION}-linux-{release_arch}"
            if not executable.is_file() or not os.access(executable, os.X_OK):
                raise ValueError("Unexpected Strix release layout.")
            (home / "strix").mkdir()
            executable.rename(home / "strix/strix")
        run([str(home / "strix/strix"), "--version"])
    elif name == "shannon":
        executable = home / "shannon/node_modules/.bin/shannon"
        if executable.is_file():
            print("Shannon already installed; no download.")
            return
        bun = home / "bun/bin/bun"
        if not bun.is_file():
            with tempfile.TemporaryDirectory(prefix="bun-install-", dir=home) as temporary:
                script = Path(temporary) / "install.sh"
                download("https://bun.sh/install", script)
                subprocess.run(["bash", str(script)], check=True,
                               env={**runtime_env(), "BUN_INSTALL": str(home / "bun")})
        target = home / "shannon"
        target.mkdir(exist_ok=True)
        run([str(bun), "add", "--cwd", str(target), "--exact", f"@keygraph/shannon@{SHANNON_VERSION}"])
        run([str(executable), "--version"])
    else:
        engine()
        with (Path(__file__).parent / "tool-kali.Dockerfile").open("rb") as dockerfile:
            run(["docker", "build", "--tag", KALI_IMAGE, "-"], stdin=dockerfile)


def selected_model(model, config, secrets):
    provider, separator, alias = model.partition("/")
    if not separator:
        raise ValueError("Select a configured provider/model, or pass --model <shortcut>.")
    settings = jsonc(config.read_text()).get("providers", {}).get(provider)
    if not isinstance(settings, dict):
        raise ValueError("This model has no transferable API configuration. Configure your own API provider with cyber config/key; OpenCode free models and host Claude sessions cannot be reused by these tools.")
    options = settings.get("settings", {})
    base = options.get("baseURL", "")
    url = urlsplit(base)
    if url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError("Tool models require an HTTPS API baseURL in the provider configuration.")
    reference = options.get("apiKey", "")
    if reference.startswith("{file:/home/agent/.secrets/") and reference.endswith("}"):
        filename = reference[len("{file:/home/agent/.secrets/"):-1]
        if not filename or Path(filename).name != filename or filename in (".", ".."):
            raise ValueError("Invalid API key file reference.")
        secret = (secrets / filename).read_text().strip()
    elif reference.startswith("{env:") and reference.endswith("}"):
        secret = os.environ.get(reference[5:-1], "")
    elif reference.startswith("{"):
        raise ValueError("Unsupported key reference; use a provider API key file.")
    else:
        secret = reference
    if not secret:
        raise ValueError("Provider API key missing; use cyber key <provider> and cyber sync.")
    entry = settings.get("models", {}).get(alias, {})
    return {"id": entry.get("modelID", alias), "base": base, "key": secret}


@contextmanager
def model_command(name, args, model, config, secrets):
    env = runtime_env()
    # Native variables must not override the model/key chosen in CyberHutch.
    for key in list(env):
        if key.startswith(("SHANNON_AI_", "STRIX_LLM")) or key in (
                "LLM_API_KEY", "LLM_API_BASE", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "XAI_API_KEY",
                "SHANNON_USE_PI_AUTH", "OPENAI_BASE_URL", "ANTHROPIC_BASE_URL"):
            env.pop(key)
    executable = root() / ("strix/strix" if name == "strix" else "shannon/node_modules/.bin/shannon")
    if not executable.is_file():
        raise ValueError(f"Optional tool not installed. Run: cyber tools install {name}")
    if informational(args) or (
            name == "shannon" and args and args[0] in ("status", "logs", "scans", "stop")):
        yield [str(executable), *args], env
        return
    connection = selected_model(model, config, secrets)
    if name == "strix":
        env.update(STRIX_LLM="openai/" + connection["id"], LLM_API_BASE=connection["base"], LLM_API_KEY=connection["key"])
        yield [str(executable), *args], env
    else:
        # Only model metadata goes to disk; the credential is environment-only.
        env.update(SHANNON_AI_MODEL="cyber:" + connection["id"], SHANNON_AI_API_KEY=connection["key"])
        with tempfile.TemporaryDirectory(prefix="model-", dir=root()) as temporary:
            metadata = Path(temporary) / "models.json"
            metadata.write_text(json.dumps({"providers": {"cyber": {"baseUrl": connection["base"],
                "api": "openai-completions", "apiKey": "YOUR_API_KEY", "models": [{"id": connection["id"]}]}}}))
            extra = []
            if args and args[0] == "start":
                if "--models-config" in args:
                    raise ValueError("Remove --models-config to use the selected CyberHutch model; native tool configuration is available through cyber sh.")
                extra = ["--models-config", str(metadata)]
                if "--follow" not in args and "-f" not in args:
                    extra.append("--follow")  # keep metadata alive until the worker finishes
            yield [str(executable), *args, *extra], env


def informational(args):
    return any(flag in args for flag in ("--help", "-h", "--version", "-v")) or bool(args and args[0] in ("help", "version"))


def kali_command(args):
    network = "none"
    if args and args[0] == "--network":
        network = "bridge"
        args = args[1:]
    if args[:1] == ["--"]:
        args = args[1:]
    work = Path.home() / "work"
    return ["docker", "run", "--rm", "--init", "--pull=never", "--read-only", "--cap-drop=ALL",
            "--security-opt=no-new-privileges", "--pids-limit=128", "--memory=2g", "--memory-swap=2g",
            "--cpus=2", "--network", network, "--tmpfs", "/tmp:rw,nosuid,nodev,size=128m",
            "--mount", f"type=bind,src={work},dst=/work", "--workdir", "/work",
            *(["-it"] if sys.stdin.isatty() else ["-i"]), KALI_IMAGE, *(args or ["bash"])]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("plan", "status", "install", "run"))
    parser.add_argument("tool", nargs="?", choices=TOOLS)
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--model", default="")
    parser.add_argument("--json", action="store_true")
    options, args = parser.parse_known_args()
    args = args[1:] if args[:1] == ["--"] else args
    if options.action == "plan":
        if args:
            parser.error("unexpected plan arguments")
        plan = install_plan(options.tool)
        if options.json:
            print(json.dumps(plan))
        else:
            print(plan["note"])
            for command in plan["commands"]:
                print(" ".join(command))
            if not options.tool:
                print("Choose a tool: cyber tools plan engine|kali|strix|shannon [--json]")
        return
    if os.geteuid() == 0:
        raise ValueError("Optional tools must run as the unprivileged guest agent, never root.")
    if options.action == "status":
        report = status_report()
        if options.json:
            print(json.dumps(report))
        else:
            for name, value in report.items():
                state = value["installed"]
                print(f'{name}: {"installed" if state else "not installed" if state is False else "not checked (engine stopped)"} (optional)')
    elif not options.tool:
        parser.error("choose engine, kali, strix or shannon")
    elif options.action == "install":
        if not options.yes:
            parser.error("installation is opt-in; explicitly pass --yes")
        install(options.tool)
    elif options.tool == "engine":
        parser.error("engine is a dependency, not an agent")
    elif options.tool == "kali":
        run(["systemctl", "--user", "start", "docker"])
        engine()
        run(kali_command(args))
    else:
        if not informational(args):
            run(["systemctl", "--user", "start", "docker"])
            engine()
        with model_command(options.tool, args, options.model,
                           Path.home() / ".config/opencode/opencode.jsonc", Path.home() / ".secrets") as (command, env):
            subprocess.run(command, env=env, check=True)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        # Do not echo subprocess argv/environment or provider exception bodies.
        print(str(error) if isinstance(error, ValueError) else "Optional tool failed; check installation and runtime availability.", file=sys.stderr)
        sys.exit(1)
