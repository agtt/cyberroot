"""Optional, read-only account quota display. Never invokes a model."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import time
from urllib.parse import urlsplit

TTL = 120
HOSTS = {"openrouter.ai": "/api/v1"}


def jsonc(text):
    # Preserve strings (URLs and quoted comments included) while stripping comments.
    text = re.sub(r'("(?:\\.|[^"\\])*")|//[^\n]*|/\*[\s\S]*?\*/',
                  lambda m: m[1] if m[1] else " ", text)
    text = re.sub(r'("(?:\\.|[^"\\])*")|,(\s*[}\]])',
                  lambda m: m[1] if m[1] else m[2], text)
    return json.loads(text)


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def summarize(key, credits):
    """Only whitelisted numeric fields are retained, never account/key metadata."""
    parts = []
    if isinstance(credits, dict):
        total, used = credits.get("total_credits"), credits.get("total_usage")
        if number(total) and number(used):
            parts.append(f"account ${total - used:.2f}")
    if isinstance(key, dict):
        remaining = key.get("limit_remaining")
        if number(remaining):
            parts.append(f"key ${remaining:.2f} left")
        elif "limit" in key and key["limit"] is None:
            parts.append("key uncapped")
        daily = key.get("usage_daily")
        if number(daily):
            parts.append(f"today ${daily:.2f}")
    return " · ".join(parts) or "remaining unknown (quota unavailable)"


def request(url, secret):
    # Header via stdin, not argv/process listings. No redirects or model calls.
    if not secret or any(ord(c) < 32 for c in secret):
        return None
    escaped = secret.replace("\\", "\\\\").replace('"', '\\"')
    result = subprocess.run(["curl", "-q", "--silent", "--fail", "--proto", "=https",
                             "--max-time", "3", "--max-filesize", "65536", "--config", "-", url],
                            input=f'header = "Authorization: Bearer {escaped}"\n',
                            capture_output=True, text=True, timeout=4)
    if result.returncode:
        return None
    reply = json.loads(result.stdout)
    data = reply.get("data") if isinstance(reply, dict) else None
    return data if isinstance(data, dict) else None


def provider(settings, secrets):
    base = settings.get("baseURL", "").rstrip("/")
    parsed = urlsplit(base)
    # Only documented provider endpoints; custom hosts are never probed speculatively.
    if (parsed.scheme != "https" or parsed.hostname not in HOSTS or parsed.username or
            parsed.password or parsed.query or parsed.fragment or parsed.port not in (None, 443) or
            parsed.path != HOSTS[parsed.hostname]):
        return None
    reference = settings.get("apiKey", "")
    match = re.fullmatch(r"\{file:/home/agent/\.secrets/([A-Za-z0-9._-]+)\}", reference)
    if match:
        secret = (secrets / match[1]).read_text().strip()
    elif isinstance(reference, str) and reference and not reference.startswith("{"):
        secret = reference
    else:
        return None
    return base, secret


def refresh(config, secrets, cache, force=False):
    stamp = hashlib.sha256(config.read_bytes()).hexdigest()
    try:
        old = json.loads(cache.read_text())
        if not force and old.get("config") == stamp and 0 <= time.time() - old["at"] < TTL:
            return
    except (OSError, ValueError, KeyError, TypeError):
        pass
    providers = jsonc(config.read_text()).get("providers", {})
    jobs = {}
    # One pair of reads per account/provider, shared by all its model shortcuts.
    with ThreadPoolExecutor(max_workers=4) as pool:
        for name, value in providers.items():
            try:
                connection = provider(value.get("settings", {}), secrets)
                if connection:
                    base, secret = connection
                    jobs[name] = [pool.submit(request, base + path, secret) for path in ("/key", "/credits")]
            except (OSError, ValueError, TypeError):
                continue
        rows = {}
        for name, futures in jobs.items():
            replies = []
            for future in futures:
                try:
                    replies.append(future.result())
                except (OSError, ValueError, subprocess.SubprocessError):
                    replies.append(None)
            rows[name] = summarize(*replies)
    cache.parent.mkdir(parents=True, exist_ok=True)
    temporary = cache.with_name(cache.name + f".{os.getpid()}.tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as out:
        json.dump({"config": stamp, "at": int(time.time()), "providers": rows}, out)
    temporary.replace(cache)


def label(model, cache, limited, now=None):
    now = int(time.time()) if now is None else now
    provider_name = model.split("/", 1)[0]
    text = "remaining unknown"
    if provider_name == "opencode":
        text += " (provider console)"
    elif provider_name == "claude":
        text += " (Claude /usage)"
    try:
        saved = json.loads(cache.read_text())
        value = saved["providers"].get(provider_name)
        if value:
            age = max(0, now - saved["at"])
            text = value + (f" · stale {age // 60}m" if age >= TTL else f" · checked {age}s ago")
    except (OSError, ValueError, KeyError, TypeError):
        pass
    retry = 0
    try:
        for line in limited.read_text().splitlines():
            fields = line.split()
            if len(fields) == 2 and fields[1] == model and fields[0].isdigit():
                retry = max(retry, int(fields[0]) + 1800 - now)
    except OSError:
        pass
    if retry > 0:
        text += f" · cooldown {math.ceil(retry / 60)}m (local retry, not quota reset)"
    return text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--secrets", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--models", type=Path, required=True)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--model")
    args = parser.parse_args()
    cache = args.out / ".quota.json"
    if args.refresh:
        try:
            refresh(args.config, args.secrets, cache, args.force)
        except (OSError, ValueError, TypeError, AttributeError):
            pass  # optional display must never block CLI operation
    if args.model:
        print(label(args.model, cache, args.out / ".limited"))
    else:
        for line in args.models.read_text().splitlines():
            fields = line.split()
            if len(fields) >= 2 and not fields[0].startswith("#"):
                print(fields[0], fields[1], label(fields[1], cache, args.out / ".limited"), sep="\t")


if __name__ == "__main__":
    main()
