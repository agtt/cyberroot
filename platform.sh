# Host adapters. WSL2 runs this CLI in its Linux shell, not PowerShell.
host_platform() {
  case "$(uname -s)" in
    Darwin) echo macos ;;
    Linux) if uname -r | grep -qi microsoft; then echo wsl2; else echo linux; fi ;;
    *) echo unsupported ;;
  esac
}

local_vm_driver() {
  case "$(uname -s):$(uname -m)" in
    Darwin:arm64) echo vz ;;
    Darwin:*|Linux:*) echo qemu ;;
    *) echo 'Local VM requires macOS, Linux or WSL2. Use: cyber target vps <ssh-host>' >&2; return 1 ;;
  esac
}

open_output() {
  if [[ "$(host_platform)" == macos ]]; then open "$1"
  elif [[ "$(host_platform)" == wsl2 ]] && command -v wslview >/dev/null; then wslview "$1"
  elif command -v xdg-open >/dev/null && [[ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]]; then xdg-open "$1"
  else printf '%s\n' "$1"; fi
}

# Used by the sourced ui.sh.
# shellcheck disable=SC2034
case "$(host_platform)" in
  macos) HOST_LABEL=Mac ;;
  wsl2) HOST_LABEL='Windows host' ;;
  *) HOST_LABEL=host ;;
esac
