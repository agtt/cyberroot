# CyberHutch

Sandboxed AI agents for security research, operated through the `cyber` CLI.

**Early preview.** A personal workflow tool, open for feedback and contributions. The local macOS workflow has been exercised; Linux/WSL2 adapters currently have offline tests only. This project has not had an independent security audit. Review the security model and host-mode exceptions before using it with sensitive data.

A small CLI that runs AI coding/security agents ([opencode](https://opencode.ai)) inside a locked-down
[Lima](https://lima-vm.io) VM, with a terminal interface for switching models and sessions.

The agent gets a full Linux box with open internet, but it cannot read your files, reach your Mac's
localhost, or touch your home network. You get live output, automatic "keep going", model fallback,
and results copied back to a folder on the host.

```
  ◆ CYBER ai-lab
  │ sandbox  ● running · Mac and home network blocked · internet open
  │ model    glm-free opencode/glm-5.3-flash-free · sandbox
  │ session  new
  ╰ type a task · / commands · /s sessions · /model · Ctrl-D quit

cyber glm-free ❯
```

> **Use it only on systems you own or are explicitly authorised to test.** The sandbox protects *your*
> machine; it does not make scanning or attacking someone else's systems legal. The bundled agent rules
> default to static analysis and tell the model not to send requests to targets unless you ask.

## Requirements

- macOS, Linux, or Windows through WSL2 (run the CLI in the WSL Linux shell). Apple Silicon uses Lima's `vz` driver; Intel macOS/Linux/WSL2 select `qemu` for new local VMs. Existing VMs are unchanged. Linux/WSL2 adapters have offline tests; a real Linux/WSL2 VM has not yet been validated.
- On Linux/WSL2, install Bash, Perl, Python 3, curl, OpenSSH and the standard Unix tools. For local VMs also install Lima 2.0+ and QEMU. Fast local QEMU requires usable hardware acceleration (`/dev/kvm` on Linux); if WSL2 cannot expose it, use an SSH target instead of nesting a slow VM. See [Lima's QEMU requirements](https://lima-vm.io/docs/config/vmtype/qemu/).
- [Lima](https://lima-vm.io) 2.0+ (`brew install lima`)
- `fzf` for the pickers (`brew install fzf`; falls back to numbered lists without it)
- Optional: `opencode` on the host (only used to pin the same version in the VM; otherwise the latest is installed), `claude` (Claude Code) for host-side models

## Install

```bash
git clone https://github.com/agtt/cyberhutch.git ~/cyber-cli
echo 'alias cyber="$HOME/cyber-cli/ailab"' >> ~/.zshrc && source ~/.zshrc
cyber up        # first run builds the VM (a few minutes)
cyber           # open the interface
```

For Bash on Linux/WSL2, add the same alias to `~/.bashrc` and reload that file instead of `~/.zshrc`.

`cyber` works from any directory. On first use it creates your local `models.txt` and `opencode.jsonc`
from the `*.example` files; both are git-ignored.

## Using it

Type a task and press Enter. It runs with the selected model in the current session, so follow-up
messages keep their context. Everything else is a slash command (type `/` for a searchable menu):

| Command | What it does |
|---|---|
| `/model` | pick a model (becomes the default) |
| `/s`, `/sessions` | switch session; `/recent` lists the latest, `/1`–`/9` jump to one; `/sessions rm` deletes |
| `/new` | start a new session |
| `/add`, `/rm` | add a model from your providers' catalogs (or `provider/model`), remove a shortcut |
| `/fallback a b c` | models to switch to, in order, when one hits a limit or errors |
| `/rounds N` | auto-continue limit (0 = unlimited) |
| `/quota` | check supported providers' balances once |
| `/quota on`, `/quota off` | enable/disable automatic quota checks (default off) |
| `/tools` | optional Kali, Strix, Shannon and guest rootless engine availability |
| `/tools install <name>` | explicitly install one optional tool |
| `/kali`, `/strix`, `/shannon` | run an installed tool; the AI tools use the selected API model |
| `/claude` | open Claude Code on the host (outside the sandbox) |
| `/tui`, `/sh` | opencode's own TUI / a shell, inside the VM |
| `/status`, `/clean` | VM, firewall, memory, disk / pick what to delete |
| `!cmd` | run one command inside the VM |

Without the interface:

```bash
cyber "task"                  # default model
cyber glm-free "task"         # a shortcut from models.txt
cyber openrouter/x "task"     # any provider/model
cyber -c "keep going"         # continue the last session
cat notes.txt | cyber "summarise this"
cyber help                    # everything else
```

### Never stopping early

A run does not end just because the model paused. If a round used tools or ended with a question or an
offer ("I can do X if you want"), `continue` is sent automatically in the same session until the model
writes `CYBER_DONE` as its last non-empty line or the round limit is reached (`AILAB_ROUNDS`, default 12, `0` = unlimited). Errors take precedence over the completion marker. Reaching the round limit exits with status 2, so an unfinished run is not reported as successful. If a
model hits a rate/usage limit, the run switches to the next model in the fallback list and skips the
limited one for 30 minutes. Only explicit error lines are checked for quota/availability signals; ordinary words such as “generate” do not trigger fallback. The Mac is kept awake while a task runs, and the keep-awake process stops when the task ends.

### Models

Quota status appears in the opening header and model picker. Network checks are **optional and off by default**: `/quota` (or `cyber quota`) checks once; `/quota on` enables checks on opening the interface or model list. `/quota off` disables automatic checks again. Checks share a two-minute cache across models and make only read-only account requests, never inference calls or VM startup. Each request has a short timeout; quota failures do not stop tasks. The helper uses Python's standard library and curl; no additional packages or virtual environment are installed.

Use any provider you configure; model selection does not depend on quota support. The optional quota reader currently understands the [OpenRouter account API](https://openrouter.ai/docs/api/api-reference/api-keys/get-current-key), showing account balance, API-key spending allowance and today's usage when those fields are available. An uncapped key does not mean unlimited account credit. Models using the same provider/key share those balances. Unsupported quota APIs, OpenCode free models and host Claude entries show `remaining unknown`; host Claude usage can be checked in Claude's `/usage`. Cached readings show their age; old readings are labelled stale. The local 30-minute retry cooldown is shown separately and is **not** a provider quota reset time.

`models.txt` maps shortcuts to `provider/model`. Three kinds:

- **opencode Zen** models (`opencode/...`) work without a key.
- **Your own providers**: any OpenAI-compatible API. `cyber key <name>` stores the key, `cyber config`
  opens `opencode.jsonc` (see the commented block in `opencode.example.jsonc`), then `/add` lists that
  provider's `/models` and writes the entry for you.
- **`claude/<model>`** entries run Claude Code **on the host, outside the sandbox**, in `CYBER_HOST_DIR`
  (or the directory in `./hostdir`, or where you ran `cyber`). They are marked `host` everywhere.

## Security model

| | |
|---|---|
| Host files | not shared (`mounts: []`, `plain: true`) |
| Host localhost, LAN, Tailscale/CGNAT, link-local, IPv6 | blocked by nftables inside the VM; `cyber` refuses to run if the rules are not loaded |
| Internet | open; traffic leaves from your IP (or the VPS's) |
| Privileges | the agent is user `agent` with no sudo, so it cannot change the firewall |
| Permissions inside the VM | everything allowed: the VM is the boundary |

Know the limits:

- **API keys you sync into the VM are readable by the agent.** Use scoped or low-limit keys.
- The agent has unrestricted internet. It can send anything it can read inside the VM anywhere.
- Prompt injection from analysed content is contained by the VM, not prevented.
- `claude/...` models are *not* sandboxed.

## Disk and performance

- VM: 6 CPUs, 10 GB RAM, 30 GB sparse disk (`lima.yaml`; change with `limactl edit ai-lab --cpus N --memory N`). It shuts down after `AILAB_IDLE_MIN` idle minutes (default 60) and boots in a few seconds.
- Only reports and small files (≤3 levels deep, <10 MB) are copied to `out/work/` on the host; big intermediate output stays in the VM. `cyber pull all` copies everything.
- Failed copies show a warning and keep the previous sync timestamp so `cyber pull` can retry the missed files.
- Logs go to `out/logs/`; anything older than a day is gzipped.
- `cyber clean` shows what uses space (VM projects, host copies, old logs) and deletes only what you select and confirm. Space freed in the VM is returned to the host (trim).

## Optional security tools

**All integrations are opt-in.** Normal startup, model selection and `cyber up` do not download Kali, Strix, Shannon, Bun, Node or Docker. Small launcher helpers are copied during configuration sync. Install only the components you want, inside the selected VM/SSH target:

```bash
cyber tools                         # availability; does not wake a stopped target
cyber tools install engine          # optional guest rootless Docker, shared by these tools
cyber tools install kali            # optional compact Kali image and selected CLI utilities
cyber tools install strix           # optional pinned Strix CLI
cyber tools install shannon         # optional pinned Shannon CLI, Bun and Node prerequisites
```

Each install asks first (`--yes` is available for explicitly approved automation). Installers never mount the computer's Docker socket or grant the agent access to a rootful engine. Docker runs rootless inside the guest; existing host Docker settings are ignored. Downloads, images and package caches can occupy hundreds of MB or more. Strix/Shannon download their own worker images when first used, after you explicitly choose the optional tool. No upstream pentest or paid model request is run during installation.

Use an installed integration from the terminal or the matching slash command:

```bash
cyber kali -- nmap -sT -h                         # offline by default
cyber kali --network -- curl https://example.com # only for an authorized network task
cyber strix --help
cyber strix --model my-model -- --target https://your-authorized-app.example
cyber shannon --model my-model -- start -u https://your-authorized-app.example -r ./project
```

All paths are inside the guest. Kali maps the guest's `~/work` to `/work`, with a read-only root, dropped capabilities, no network by default and a 2 GiB memory limit. Enable network explicitly with `--network`; use TCP-connect scans (`nmap -sT`) rather than raw-socket scans. Strix/Shannon manage their own worker containers; the outer VM remains the host isolation boundary. Their engines, network activity, resource requirements, exit codes and findings follow the upstream tools, not CyberHutch's OpenCode auto-continue/fallback loop.

The selected **configured OpenAI-compatible API provider** supplies the endpoint, upstream model ID and key. The API key is passed through the child environment, never argv or generated model files. Shannon gets a temporary Chat Completions model definition and follows the scan until completion. Credentials are read inside the guest; run `cyber sync` after changing configuration. OpenCode's free models and host Claude sessions do not provide reusable API credentials, so select your own configured API model for these tools. Model capability/tool-calling support and provider account access still depend on the model you choose. For native tool configuration, use `cyber sh` and the installed executable under `~/.local/share/cyber-tools/`.

Agents inside the guest can use `~/.local/bin/cyber-tool status` and `~/.local/bin/cyber-tool run strix --model provider/model -- --target <authorized-target>` (or `run shannon ...`). Agents are instructed not to install these tools unless the user explicitly chooses them. `cyber down` stops the local VM and its tool services; installed optional packages remain available for later use.

Upstream projects are downloaded separately under their own licenses, not bundled into this MIT repository: [Strix](https://github.com/usestrix/strix) (Apache-2.0), [Shannon](https://github.com/KeygraphHQ/shannon) (AGPL-3.0), [Kali images](https://www.kali.org/docs/containers/official-kalilinux-docker-images/). Installation follows [rootless Docker](https://docs.docker.com/engine/security/rootless/); model routing follows [Strix configuration](https://github.com/usestrix/strix/blob/main/docs/advanced/configuration.mdx) and [Shannon providers](https://keygraph.io/docs/how-to/ai-providers/).

## VPS target

The SSH target is also the practical option for WSL2 hosts without working nested virtualization. Run Cyber inside your WSL2 distro, keep the checkout in its Linux filesystem, then use the commands below. The WSL2 distro itself is not treated as the agent sandbox; the agent still runs in the separate Lima VM or SSH target. `/out` uses `wslview` when installed, otherwise prints the folder path on a headless shell. No desktop-opening utility is required for tasks.

```bash
cyber target vps my-ssh-host   # any host from ~/.ssh/config, Debian/Ubuntu, root or passwordless sudo
cyber up                       # provisions tools, the agent user and the egress firewall
cyber target local             # switch back; one-off: AILAB_TARGET="vps my-ssh-host" cyber "task"
```

On a VPS the firewall only restricts the `agent` user (private ranges and cloud metadata), so your own
SSH access is unaffected.

## Files

| | |
|---|---|
| `ailab` | the CLI |
| `ui.sh` | the interactive interface |
| `livelog.pl` | colours live output and writes the log |
| `round-state.awk` | reads each round once to detect errors, completion and continuation with bounded memory |
| `quota.py` | optional account quota reads and small local cache |
| `platform.sh` | macOS/Linux/WSL2 VM driver and folder-opening adapters |
| `lima.yaml` | VM definition and firewall |
| `vm-setup.sh`, `vps-setup.sh` | provisioning (opencode, tools, idle shutdown / VPS firewall) |
| `vm-AGENTS.md` | rules given to agents inside the VM |
| `*.example*` | templates for your local `models.txt` and `opencode.jsonc` |

## Environment

`AILAB_ROUNDS`, `AILAB_THINKING=0`, `AILAB_IDLE_MIN`, `AILAB_TARGET`, `AILAB_SSH_OPTS`, `OPENCODE_VERSION`,
`CYBER_SECRETS` (key directory), `CYBER_HOST_DIR`, `NO_COLOR`.

## Offline checks

```bash
bash -n ailab ui.sh platform.sh tools.sh tool-deps.sh vm-setup.sh vps-setup.sh
python3 -B -m unittest test_cli test_quota test_tools
```

The regression checks use mocked commands and temporary files inside the repository; they do not start a VM or call model APIs. Runs still use `--standalone` to avoid the known background-service hang.

Optional integration validation: 19 focused checks passed inside a Linux guest. The actual Linux arm64 Strix 1.7.0 and Shannon 3.5.0 installers and `version`/`help` entry points were exercised without credentials or model calls. A temporary Kali image was checked with network disabled, capabilities dropped and a read-only root. Temporary binaries, Node/Bun/package caches and the test image were removed afterwards. A complete rootless-engine installation, the custom Kali image build, upstream worker startup and paid-model pentest runs have not been exercised end to end; they still depend on upstream runtime requirements and the selected provider/model.

## License

MIT
