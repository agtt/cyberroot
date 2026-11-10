# Optional tool entry points. Sourced by ailab; none runs until explicitly selected.
sync_tool_helpers() {
  local file
  lsh sudo -u agent mkdir -p /home/agent/.local/share/cyber-tools/helpers /home/agent/.local/bin || return 1
  for file in toolkit.py quota.py tool-kali.Dockerfile; do
    lsh sudo -u agent sh -c 'cat > "$1"' _ "/home/agent/.local/share/cyber-tools/helpers/$file" < "$HERE/$file" || return 1
  done
  lsh sudo -u agent sh -c 'cat > /home/agent/.local/bin/cyber-tool; chmod 755 /home/agent/.local/bin/cyber-tool' <<'EOF'
#!/bin/sh
exec python3 -B "$HOME/.local/share/cyber-tools/helpers/toolkit.py" "$@"
EOF
}

tool_run() {
  local tool="$1"; shift
  local chosen="${CYBER_TOOL_MODEL:-$(default_model)}" model rc=0
  if [[ "${1:-}" == --model ]]; then
    [[ -n "${2:-}" ]] || { say 'Usage: --model <shortcut or provider/model>'; return 2; }
    chosen="$2"; shift 2
  fi
  [[ "${1:-}" != -- ]] || shift
  model="$(resolve "$chosen")"
  [[ -n "$model" ]] || { say "Unknown model: $chosen"; return 2; }
  ( ensure_up ) || return 1
  sync_tool_helpers || return 1
  if ! lsh test -f /home/agent/.config/opencode/opencode.jsonc; then
    say 'Run cyber sync to copy your provider configuration before using optional AI tools.'
    return 1
  fi
  if agent python3 -B /home/agent/.local/share/cyber-tools/helpers/toolkit.py run "$tool" --model "$model" -- "$@"; then rc=0; else rc=$?; fi
  pull
  return "$rc"
}

tools_command() {
  local action="${1:-status}" tool="${2:-}" answer
  case "$action" in
    status|list)
      if [[ "$(state)" != Running ]]; then
        say 'Kali, Strix, Shannon and the guest rootless engine are optional. Target stopped; installations not checked.'
        say 'Install only what you need: cyber tools install engine|kali|strix|shannon'
        return 0
      fi
      sync_tool_helpers || return 1
      agent python3 -B /home/agent/.local/share/cyber-tools/helpers/toolkit.py status
      ;;
    install)
      case "$tool" in engine|kali|strix|shannon) ;; *) say 'Choose engine, kali, strix or shannon.'; return 2 ;; esac
      say "Optional install: $tool inside the selected VM/SSH target. Downloads may use hundreds of MB or more; nothing is installed on the host."
      if [[ "${3:-}" != --yes ]]; then
        read -r -p 'Install this optional tool? [y/N] ' answer || return 1
        [[ "$answer" == y ]] || return 1
      fi
      ( ensure_up ) || return 1
      sync_tool_helpers || return 1
      lsh sudo bash -s "$tool" < "$HERE/tool-deps.sh" || return 1
      agent python3 -B /home/agent/.local/share/cyber-tools/helpers/toolkit.py install "$tool" --yes
      ;;
    *) say 'Usage: cyber tools [status | install engine|kali|strix|shannon [--yes]]'; return 2 ;;
  esac
}
