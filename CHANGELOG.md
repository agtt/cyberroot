# Changelog

## Unreleased

- Project renamed from CyberHutch to CyberRoot (repository `agtt/cyberroot`, Kali image `cyberroot-kali:1`). The `ailab` script, `cyber` alias, VM instance name and `AILAB_*` variables are unchanged so existing VMs keep working.
- Grouped `cyber help` with a CyberRoot banner (also in the interface header).
- `cyber sessions` lists sessions; `cyber logs [N | -f]` lists, opens or follows run logs (`/logs`, `/log N` in the interface).
- `cyber cve` / `/cve`: recent NVD CVEs with CISA KEV marks, keyword/severity filters, CVE details and JSON output.
- Themes (`cyber theme`, `/theme`): `root` (default), `matrix`, `mono`; the logo stays green.
- Prompt: Ctrl-C clears the line and twice on an empty line exits; Ctrl-Z suspends.
- Interface prompt suggests matching `/` commands while typing; Tab completes, arrows pick.

## 0.1.0 — 2026-11-10 (preview)

Initial public preview.

- Isolated OpenCode workflow through a Lima VM or configured SSH target.
- Model shortcuts, session selection, bounded auto-continue, model fallback and live logs.
- Small-file/report synchronization, idle shutdown and confirmed cleanup.
- Optional quota checks; unsupported quota APIs remain unknown.
- Opt-in Kali, Strix and Shannon integrations with a guest rootless Docker engine.
- Agent installation guide and offline JSON dependency plans.
- First-run target/model wizard; optional tools begin unselected.
- Read-only `doctor`, JSON diagnostics and optional live SSH checks.
- Scripted 25-second terminal walkthrough and contribution guidance.

### Validation limits

macOS Apple Silicon is the exercised host workflow. Linux/WSL2 host adapters have offline tests. Linux arm64 Strix/Shannon installation and help/version entry points were checked; temporary downloads were removed. Kali's read-only root, dropped capabilities and offline networking were checked with a temporary official image. Full rootless engine installation, custom Kali image building and a complete paid-model pentest/worker run remain unverified end to end. This preview has not had an independent security audit.
