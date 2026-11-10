# Contributing to CyberRoot

Small, focused changes are welcome: installation fixes, host adapters, optional tool integrations, diagnostics, model compatibility and documentation.

## Start here

1. Read README and [AGENT-INSTALL.md](AGENT-INSTALL.md).
2. Run `./ailab doctor --json` and `./ailab tools plan --json`. Neither installs tools or calls a model; SSH diagnostics need an explicit `--live`.
3. Use temporary fixtures for changes. A VM or API key is not needed for the offline checks below.

```bash
bash -n ailab ui.sh platform.sh tools.sh tool-deps.sh vm-setup.sh vps-setup.sh
python3 -B -m unittest test_cli test_quota test_tools test_onboarding test_lineedit test_cve
git diff --check
```

If ShellCheck is already installed, run `shellcheck -s bash -S warning ailab ui.sh platform.sh tools.sh tool-deps.sh vm-setup.sh vps-setup.sh`. No package installation or broad test matrix is required for a small change.

## Keep the defaults small

- Kali, Strix, Shannon, their rootless engine and quota network checks stay opt-in.
- Diagnostic and planning commands must not boot targets, download packages, scan targets or call paid models.
- Preserve existing user models, configuration, keys, reports and VM data. No silent reset, global Docker prune or host Docker socket sharing.
- API credentials never belong in argv, screenshots, demo artifacts, reports, issues or commits. Local settings and output remain ignored.
- The sandbox agent remains unprivileged. Guest administrator prerequisites belong in the explicit host-side installation workflow.
- Keep documentation and commit messages in English. The interface can respond to a user's language without adding personal configuration to the repository.
- Describe verification honestly: a CLI help check, a container startup check and a real authorized pentest are different checks.

## Pull requests and issues

Explain the problem, resulting behavior and focused verification. Include host OS, target type (Lima or SSH), CLI version and a redacted error when reporting a bug. Never attach API keys or raw private project/model logs. Keep feature requests specific to an existing workflow.

Use conventional commit messages such as `fix: preserve quoted tool arguments` or `feat: add an optional tool adapter`. Changes should remain compatible with Bash 3.2 on the host and the Python version shipped by the documented guest.

## Demo and releases

The README animation and terminal cast are explicitly scripted examples, not evidence of a completed pentest. Regenerate them with `python3 -B scripts/render-demo.py`; it creates only `docs/demo.svg` and `docs/demo.cast` and requires no external packages.

Preview releases use a `v` tag matching `VERSION`, an entry in CHANGELOG and truthful validation notes. Do not publish a release or run a live target/model test without the maintainer's authorization. Upstream Strix/Shannon/Kali distributions keep their own licenses; integrations do not vendor their source.
