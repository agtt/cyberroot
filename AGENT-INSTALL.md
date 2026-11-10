# Agent installation guide

Use the checked-in CLI directly. Shell aliases are optional for humans and are not available in most agent subprocesses. Run commands from the repository root unless a step says otherwise.

## 1. Inspect without installing

```bash
./ailab help
./ailab --version
./ailab doctor --json
./ailab tools plan --json
```

These commands do not boot a VM, install optional packages, create local configuration, download images or call a model. They use shipped templates when settings do not exist. Default diagnostics do not connect to SSH targets; use `doctor --live` only when the user asks to check that target. Setup and normal operation initialize ignored configuration from the examples when needed. Never reset existing `models.txt`, `opencode.jsonc`, `target`, API key files or user work to template defaults.

Check the host prerequisites in README before booting: Bash, Git, Perl, Python 3, curl and standard Unix tools; Lima for a local VM, or SSH access to a configured Debian/Ubuntu target. Optional `fzf` only improves pickers. On WSL2 use its Linux shell; a working QEMU/KVM environment or an SSH target is needed. Report missing host prerequisites; do not install them without the user's authorization.

## 2. Prepare the base CLI

After the user requests base installation:

```bash
./ailab up
./ailab list
./ailab tools
```

`up` provisions the base guest and syncs launchers. It does not install Kali, Strix, Shannon or their Docker/Node/Bun dependencies. All optional installations run inside the chosen guest. Host Claude entries deliberately run outside the sandbox and are a separate user choice.

For a human-guided setup use `./ailab setup`: choose local VM/SSH, an existing/free/API model and optional integrations (none selected by default). It saves preferences, shows the command plan and asks before starting or provisioning. The new-provider path preserves existing settings but reformats JSONC comments; API keys are entered separately with `./ailab key <provider>`. Agents should prefer explicit commands and JSON plans over scripting terminal prompts.

## 3. Plan only the integration the user selected

Example: if the user explicitly requests Strix, inspect its plan:

```bash
./ailab tools plan strix --json
```

The JSON `commands` field is an array of argument arrays in dependency order. An empty selection produces no install commands. `automatic_install` remains false. Do not install the entire catalog, start a scan or infer paid-model consent from permission to install a tool.

For an explicitly authorized Strix installation, the plan is:

```bash
./ailab tools install engine --yes
./ailab tools install strix --yes
./ailab strix --version
./ailab strix --help
```

Use `kali` or `shannon` in the plan for those integrations. The rootless engine is shared; the Kali/Strix/Shannon packages are independent. Strix/Shannon worker images can download on first real use. Downloads and caches may use hundreds of MB or more. The host launcher handles guest administrative prerequisites; sandbox agents do not receive sudo or access to the host's Docker socket.

## 4. Select an API model

For Strix/Shannon, reuse a configured OpenAI-compatible provider and its upstream model ID. OpenCode free model IDs and host Claude sessions have no transferable API key.

```bash
./ailab list
./ailab sync
./ailab strix --model <existing-shortcut> -- --help
./ailab shannon --model <existing-shortcut> -- help start
```

Help/version commands require no API key or running Docker. If a new provider is needed, follow `opencode.example.jsonc`, add only that provider and shortcut, and let the user enter their key through `./ailab key <provider>`'s hidden prompt. Never read keys into the conversation, put them in argv/logs, commit configuration or copy credentials between unrelated providers. Then run `./ailab sync`.

Only when the user authorizes testing a specific target, invoke the selected tool with that target. The `--model` switch must precede `--`; arguments after `--` go to the upstream CLI unchanged. Source paths are guest paths, not host paths. See README for runtime examples and validation limits.

## 5. Sandbox agents

Inside an already prepared guest, use:

```bash
~/.local/bin/cyber-tool status
~/.local/bin/cyber-tool run strix --model provider/model -- --help
~/.local/bin/cyber-tool run shannon --model provider/model -- help start
~/.local/bin/cyber-tool run kali -- bash -lc 'command -v nmap'
```

If an integration or its system prerequisites are missing, report the matching host-side plan. A sandbox agent cannot perform the host administrator's setup step. It can use an installed tool without recreating a virtual environment or downloading another copy.

## 6. Finish without deleting user data

Keep reports in the guest's `~/work/<project>/`, pull the deliverables and stop a local VM started just for the task when no user work remains active. Remove only temporary test artifacts created by the current session; confirm before deleting existing installations, images, reports or user data. Never use global Docker prune. Report which commands passed and distinguish CLI startup checks from a real, authorized pentest.
