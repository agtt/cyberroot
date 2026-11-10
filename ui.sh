# cyber interface: opens when `cyber` is typed alone. Sourced by ailab (bash 3.2 compatible).
# Type a task -> runs with the selected model in the selected session. "/" -> live command suggestions (lineedit.py).

UI_HIST="$HERE/.history"
UI_SESS="$OUT/.sessions"       # cached session list (id \t title \t date), newest first
CUR_MODEL=""; CUR_SESS=""; CUR_TITLE=""; UI_INT=0

ui_kind()  { [[ "$1" == claude/* ]] && echo host || echo sandbox; }
ui_short() { local k; k="$(short_of "$1")"; echo "${k:-$1}"; }
ui_plain() { sed -E $'s/\x1b\\[[0-9;]*m//g'; }

# Pick one line with fzf (numbered list without it). stdin: lines, $1: title. Prints the chosen line.
ui_pick() {
  local title="$1"; shift
  if command -v fzf >/dev/null; then
    fzf --height=60% --min-height=8 --reverse --border=rounded --border-label=" $title " --prompt='❯ ' --pointer='▶' \
        --info=inline-right --no-multi --ansi --color="$FZF_COLORS" "$@"
  else
    local lines=() l i=1 n
    while IFS= read -r l; do lines+=("$l"); printf '%s%3d%s  %s\n' "$C_C" "$i" "$C_0" "$l" >&2; i=$((i + 1)); done
    printf '%s (number, empty = cancel): ' "$title" >&2; read -r n </dev/tty || return 1
    [[ "$n" =~ ^[0-9]+$ ]] && (( n >= 1 && n <= ${#lines[@]} )) && printf '%s\n' "${lines[$((n - 1))]}"
  fi
}

ui_vm_line() {
  if [[ $MODE == vps ]]; then echo "${C_C}●${C_0} vps $HOST"; return; fi
  case "$(state)" in
    Running) echo "${C_G}●${C_0} running ${C_D}· $HOST_LABEL and private network blocked · internet open${C_0}" ;;
    "")      echo "${C_Y}○${C_0} not created ${C_D}· built on the first task${C_0}" ;;
    *)       echo "${C_Y}○${C_0} stopped ${C_D}· starts on the first task${C_0}" ;;
  esac
}

# Refresh the session cache from the VM (failed/empty "Untitled" sessions are hidden).
ui_sessions_refresh() {
  [[ "$(state)" == Running ]] || return 0
  mkdir -p "$OUT"
  agent opencode --standalone session list 2>/dev/null </dev/null | tr -d '\r' \
    | awk -F'\t' 'NF >= 2 && $2 != "Untitled session"' > "$UI_SESS.tmp" && mv "$UI_SESS.tmp" "$UI_SESS"
}

ui_header() {
  local kind; kind="$(ui_kind "$CUR_MODEL")"
  local badge="${C_G}sandbox${C_0}"; [[ $kind == host ]] && badge="${C_Y}host · outside the sandbox${C_0}"
  say
  banner "${C_D}v$(cat "$HERE/VERSION")${C_0}" "${C_T}isolated workspace for AI security agents${C_0}"
  say "  ${C_M}│${C_0}"
  say "  ${C_M}│${C_0} ${C_D}sandbox${C_0}  $(ui_vm_line)"
  say "  ${C_M}│${C_0} ${C_D}model  ${C_0}  ${C_T}${C_B}$(ui_short "$CUR_MODEL")${C_0} ${C_D}$CUR_MODEL${C_0} · $badge"
  say "  ${C_M}│${C_0} ${C_D}quota  ${C_0}  $(quota_data --model "$CUR_MODEL")"
  say "  ${C_M}│${C_0} ${C_D}session${C_0}  ${C_T}${CUR_TITLE:-new}${C_0}${CUR_SESS:+ ${C_D}$CUR_SESS${C_0}}"
  say "  ${C_M}╰${C_0} ${C_D}type a task · ${C_0}${C_C}/${C_0}${C_D} commands · ${C_0}${C_C}/s${C_0}${C_D} sessions · ${C_0}${C_C}/model${C_0}${C_D} · Ctrl-D quit${C_0}"
  say
}

UI_CMDS="/model     pick a model (becomes the default)
/setup     guided target/model setup (optional tools unselected)
/doctor    check dependencies, runtime and model configuration without model calls
/sessions  switch session (/s; /sessions rm deletes one)
/recent    list recent sessions; /1-/9 jumps to one
/new       start a new session
/add       add a model (pick from the catalog or type provider/model)
/rm        remove a model shortcut
/models    list shortcuts
/quota     fetch balances once (/quota on|off = automatic checks)
/tools     optional tools: status / install engine|kali|strix|shannon
/kali      run an installed Kali CLI (--network explicitly enables internet)
/strix     run optional Strix with the selected model
/shannon   run optional Shannon with the selected model
/fallback  fallback order (used on limit/error)
/rounds    auto-continue round limit (0 = unlimited)
/claude    open Claude Code on the host (outside the sandbox)
/tui       open opencode's TUI in the VM (with this session)
/sh        shell inside the VM
/status    VM, firewall, memory, disk, model
/clean     disk usage; pick what to delete
/pull      copy results from the VM now (/pull all = everything)
/out       open the output folder (or print its path on a headless host)
/cve       recent CVEs (/cve nginx, /cve CVE-ID, /cve --kev)
/theme     colour theme (root, matrix, mono)
/log       show the latest log (/log N opens the Nth, see /logs)
/logs      recent run logs
/key       save a provider API key
/config    edit provider config (opencode.jsonc)
/down      stop the VM
/clear     clear the screen
/help      this list
/quit      quit"

UI_ALIASES="/m=/model /s=/sessions /resume=/sessions /r=/recent /n=/new /list=/models /st=/status /h=/help /?=/help /q=/quit /exit=/quit"

# Read one prompt line into UI_LINE. 0 = line, 1 = EOF, 130 = Ctrl-C.
# lineedit.py shows matching commands while "/..." is typed; plain readline is the fallback.
ui_read() {
  local rc
  if [[ -z "${CYBER_PLAIN_INPUT:-}" && -t 0 && -t 1 ]] && command -v python3 >/dev/null; then
    UI_LINE="$(CYBER_CMDS="$UI_CMDS" CYBER_CMD_ALIASES="$UI_ALIASES" python3 -I -B "$HERE/lineedit.py" "$1" "$UI_HIST")"; rc=$?
    case $rc in 0) return 0 ;; 3) return 1 ;; 130) return 130 ;; esac
  fi
  UI_INT=0
  IFS= read -r -e -p "$1" UI_LINE && return 0
  echo; (( UI_INT )) && return 130
  return 1
}

ui_theme() {
  local t="${1:-}" sel
  if [[ -z "$t" ]]; then
    sel="$(for t in $THEMES; do printf '%s %-7s %s\n' "$([[ $t == "$THEME" ]] && echo "●" || echo " ")" "$t" "$(theme_info "$t")"; done \
      | ui_pick "theme")" || return 0
    t="$(awk '{print ($1=="●") ? $2 : $1}' <<<"$sel")"
  fi
  [[ -n "$t" ]] || return 0
  theme_command "$t" && { printf '\033[2J\033[H'; ui_header; }
}

ui_models_table() {
  quota_auto_refresh
  quota_data | awk -F'\t' -v d="$CUR_MODEL" -v g="$C_G" -v y="$C_Y" -v b="$C_B" -v m="$C_D" -v z="$C_0" 'NF>=2 {
    kind = ($2 ~ /^claude\//) ? y "host   " z : g "sandbox" z
    printf "%s %s%-10s%s %s  %s%s%s · %s\n", ($2==d ? "●" : " "), b, $1, z, kind, m, $2, z, $3 }'
}

ui_quota() {
  case "${1:-}" in
    on)  echo on > "$HERE/quota-mode"; say 'Automatic quota checks enabled (2 minute cache).'; quota_data --refresh --force >/dev/null ;;
    off) echo off > "$HERE/quota-mode"; say 'Automatic quota checks disabled. /quota still checks once.'; return 0 ;;
    ""|refresh) quota_data --refresh --force >/dev/null ;;
    *) say 'Usage: /quota [on|off|refresh]'; return 0 ;;
  esac
  quota_data | awk -F'\t' '{printf "  %-10s %s\n", $1, $3}' >&2
  say 'Balances and key limits are shared by models using the same provider/key.'
}

ui_model() {
  quota_auto_refresh
  local sel k m
  if [[ -n "${1:-}" ]]; then k="$1"; else
    sel="$(ui_models_table | ui_pick "pick a model")" || return 0
    k="$(ui_plain <<<"$sel" | awk '{print ($1=="●") ? $2 : $1}')"
  fi
  [[ -n "$k" ]] || return 0
  m="$(resolve "$k")"; [[ -n "$m" ]] || { say "${C_R}unknown model: $k${C_0}"; return 0; }
  CUR_MODEL="$m"; echo "$m" > "$DEFAULT"
  say "${C_G}✔${C_0} model: ${C_B}$(ui_short "$m")${C_0} ${C_D}$m · $(ui_kind "$m")${C_0}"
  say "${C_D}  quota: $(quota_data --model "$m")${C_0}"
}

ui_up() { # bring the VM up; never kill the interface on failure
  ( ensure_up ) || { say "${C_R}✗ sandbox is not ready${C_0}"; return 1; }
}

ui_set_session() { CUR_SESS="$1"; CUR_TITLE="$2"; say "${C_G}✔${C_0} session: ${C_B}$CUR_TITLE${C_0} ${C_D}$CUR_SESS${C_0}"; }

ui_recent() {
  [[ -s "$UI_SESS" ]] || { say "${C_D}no sessions yet${C_0}"; return 0; }
  awk -F'\t' -v c="$C_C" -v d="$C_D" -v z="$C_0" 'NR <= 9 {printf "  %s/%d%s %-50.50s %s%s%s\n", c, NR, z, $2, d, $3, z}' "$UI_SESS" >&2
}

ui_session_n() { # /1../9
  local row; row="$(sed -n "${1}p" "$UI_SESS" 2>/dev/null)"
  [[ -n "$row" ]] || { say "${C_R}no recent session #$1${C_0} ${C_D}(/s for the full list)${C_0}"; return 0; }
  ui_set_session "$(cut -f1 <<<"$row")" "$(cut -f2 <<<"$row")"
}

ui_sessions() {
  ui_up || return 0
  ui_sessions_refresh
  [[ -s "$UI_SESS" ]] || { say "${C_D}no sessions yet${C_0}"; return 0; }
  local sel id
  if [[ "${1:-}" == rm ]]; then
    sel="$(awk -F'\t' '{printf "%s\t%-56.56s  %s\n", $1, $2, $3}' "$UI_SESS" | ui_pick "session to DELETE" --delimiter=$'\t' --with-nth=2)" || return 0
    id="${sel%%$'\t'*}"; local a
    read -r -p "Delete session: $(cut -f2 <<<"$sel" | sed 's/ *$//') [y/N] " a
    [[ "$a" == y ]] || return 0
    agent opencode --standalone session delete "$id" </dev/null >/dev/null 2>&1 && say "${C_G}✔${C_0} deleted"
    [[ "$id" == "$CUR_SESS" ]] && { CUR_SESS=""; CUR_TITLE=""; }
    ui_sessions_refresh
    return 0
  fi
  sel="$(awk -F'\t' -v cur="$CUR_SESS" '{printf "%s\t%s %-56.56s  %s\n", $1, ($1==cur ? "●" : " "), $2, $3}' "$UI_SESS" | ui_pick "switch session (type to search)" --delimiter=$'\t' --with-nth=2)" || return 0
  id="${sel%%$'\t'*}"
  ui_set_session "$id" "$(awk -F'\t' -v i="$id" '$1==i {print $2; exit}' "$UI_SESS")"
}

# Add an entry to a provider's "models" block in opencode.jsonc (if missing). $1 provider $2 alias $3 upstream id $4 name $5 context
ui_jsonc_add() {
  python3 - "$CONFIG" "$@" <<'EOF'
import sys, re, json
path, prov, alias, mid, name, ctx = sys.argv[1:7]
s = open(path).read()
p = s.find('"%s"' % prov)
if p < 0: sys.exit("provider not in config: %s (cyber config)" % prov)
m = re.compile(r'"models"\s*:\s*\{').search(s, p)
if not m: sys.exit("models block not found: %s" % prov)
end = s.find('\n    }', m.end())
if ('"%s"' % alias) in s[m.end(): end if end > 0 else len(s)]: sys.exit(0)
entry = {"modelID": mid, "name": name}
if ctx.isdigit() and int(ctx) > 0: entry["limit"] = {"context": int(ctx)}
ins = '\n        %s: %s,' % (json.dumps(alias), json.dumps(entry, ensure_ascii=False))
open(path, 'w').write(s[:m.end()] + ins + s[m.end():])
EOF
}

# Providers in opencode.jsonc that have a baseURL (OpenAI-compatible): "name<TAB>baseURL" per line.
ui_providers() {
  python3 - "$CONFIG" <<'EOF'
import sys, re, json
s = open(sys.argv[1]).read()
s = re.sub(r'(^|\s)//[^\n]*', r'\1', s)          # line comments (not the // inside URLs)
s = re.sub(r',(\s*[}\]])', r'\1', s)             # trailing commas
try: cfg = json.loads(s)
except Exception: sys.exit(0)
for name, p in (cfg.get("providers") or {}).items():
    base = ((p or {}).get("settings") or {}).get("baseURL")
    if base: print("%s\t%s" % (name, base.rstrip("/")))
EOF
}

ui_add() {
  local k="${1:-}" m="${2:-}" sel
  if [[ -z "$m" ]]; then
    ui_up || return 0
    say "${C_D}loading catalog...${C_0}"
    # rows: kind \t provider \t id \t name \t context \t display
    local rows="" prov base part
    while IFS=$'\t' read -r prov base; do
      [[ -n "$prov" ]] || continue
      # each provider's /models (OpenAI format; name/context/pricing are used when present, as on OpenRouter-style APIs)
      part="$(agent bash -c 'k="$(cat ~/.secrets/"$1"-api-key 2>/dev/null)"; curl -fsS -m 15 "$2/models" ${k:+-H "Authorization: Bearer $k"} 2>/dev/null \
        | jq -r --arg p "$1" ".data[] | [\"cat\", \$p, .id, (.name // .id), ((.context_length // 0) | tostring), (((.pricing.prompt // \"0\") | tonumber) * 1000000 | tostring)] | @tsv" 2>/dev/null' _ "$prov" "$base" </dev/null | tr -d '\r')" || true
      [[ -n "$part" ]] && rows+="$(awk -F'\t' '{printf "%s\t%s\t%s\t%s\t%s\t%-58.58s %8s ctx  $%.3f/M  %s catalog\n", $1, $2, $3, $4, $5, $2 ":" $3, $5, $6, $2}' <<<"$part")"$'\n'
    done < <(ui_providers)
    rows+="$(agent opencode --standalone models 2>/dev/null </dev/null | tr -d '\r' | awk 'NF {printf "known\t\t%s\t\t\t%-58.58s configured\n", $1, $1}')"
    sel="$(sed '/^$/d' <<<"$rows" | ui_pick "model to add (type to search)" --delimiter=$'\t' --with-nth=6)" || return 0
    if [[ "$(cut -f1 <<<"$sel")" == cat ]]; then
      local mid alias
      prov="$(cut -f2 <<<"$sel")"; mid="$(cut -f3 <<<"$sel")"
      alias="$(tr -c 'A-Za-z0-9._\n-' '-' <<<"${mid##*/}")"
      ui_jsonc_add "$prov" "$alias" "$mid" "$(cut -f4 <<<"$sel")" "$(cut -f5 <<<"$sel")" || return 0
      m="$prov/$alias"
      sync_cfg >/dev/null 2>&1 && say "${C_D}config sent to the VM${C_0}"
    else
      m="$(cut -f3 <<<"$sel")"
    fi
  fi
  [[ "$m" == */* ]] || { say "${C_R}model must look like provider/model${C_0}"; return 0; }
  if [[ -z "$k" ]]; then
    local def; def="$(tr 'A-Z' 'a-z' <<<"${m##*/}" | sed -E 's/[^a-z0-9]+/-/g; s/^-|-$//g' | cut -c1-14)"
    read -r -e -p "shortcut name [$def]: " k; k="${k:-$def}"
  fi
  [[ "$k" =~ ^[A-Za-z0-9._-]+$ ]] || { say "${C_R}invalid shortcut${C_0}"; return 0; }
  [[ -z "$(shortcut "$k")" ]] || { say "${C_R}shortcut already exists: $k -> $(shortcut "$k")${C_0}"; return 0; }
  printf '%-9s %s\n' "$k" "$m" >> "$MODELS"
  say "${C_G}✔${C_0} added: ${C_B}$k${C_0} ${C_D}$m${C_0}"
  local a; read -r -p "switch to it now? [Y/n] " a; [[ "$a" == n ]] || ui_model "$k"
}

ui_rm() {
  local k="${1:-}" sel a
  if [[ -z "$k" ]]; then
    sel="$(ui_models_table | ui_pick "shortcut to REMOVE")" || return 0
    k="$(ui_plain <<<"$sel" | awk '{print ($1=="●") ? $2 : $1}')"
  fi
  local m; m="$(shortcut "$k")"; [[ -n "$m" ]] || { say "${C_R}no such shortcut: $k${C_0}"; return 0; }
  read -r -p "Remove shortcut: $k -> $m [y/N] " a; [[ "$a" == y ]] || return 0
  awk -v k="$k" '!($1==k)' "$MODELS" > "$MODELS.tmp" && mv "$MODELS.tmp" "$MODELS"
  say "${C_G}✔${C_0} removed: $k ${C_D}(provider config is kept: /config)${C_0}"
  [[ "$m" == "$CUR_MODEL" ]] && { rm -f "$DEFAULT"; CUR_MODEL="$(default_model)"; say "${C_D}model: $CUR_MODEL${C_0}"; }
  return 0
}

ui_status() {
  say "  ${C_D}target  ${C_0} $MODE${HOST:+ $HOST}"
  say "  ${C_D}sandbox ${C_0} $(ui_vm_line)"
  if [[ "$(state)" == Running ]]; then
    lsh sudo sh -c 'printf "  \033[2mcpu/mem \033[0m %s cores · %s\n" "$(nproc)" "$(free -h | awk "/^Mem/{print \$3\" / \"\$2}")"
      printf "  \033[2mvm disk \033[0m %s\n" "$(df -h / | awk "NR==2{print \$3\" / \"\$2}")"
      nft list table inet ailab 2>/dev/null | grep -q "@blocked4.*drop" && printf "  \033[2mfirewall\033[0m \033[32m✓ loaded\033[0m\n" || printf "  \033[2mfirewall\033[0m \033[31m✗ MISSING\033[0m\n"
      printf "  \033[2mrunning \033[0m %s task(s)\n" "$(pgrep -u agent -fc "opencode run" || true)"' >&2 </dev/null || true
  fi
  [[ $MODE == local ]] && say "  ${C_D}on host ${C_0} VM image $(du -sh "$HOME/.lima/$VM" 2>/dev/null | cut -f1) · results $(du -sh "$OUT" 2>/dev/null | cut -f1) ${C_D}(/clean)${C_0}"
  say "  ${C_D}model   ${C_0} $(ui_short "$CUR_MODEL") ${C_D}$CUR_MODEL${C_0}"
  say "  ${C_D}quota   ${C_0} $(quota_data --model "$CUR_MODEL")"
  say "  ${C_D}fallback${C_0} $(fallbacks | tr '\n' ' ')"
  say "  ${C_D}rounds  ${C_0} ${AILAB_ROUNDS:-12} ${C_D}(0 = unlimited)${C_0}"
}

# Disk usage + pick what to delete (always asks). Deleting inside the VM also shrinks the VM image on the Mac (trim).
ui_clean() {
  set +e
  command -v fzf >/dev/null || { say "cyber clean needs fzf (brew install fzf)"; return 0; }
  local rows="" up=0 sel a kind name
  if [[ "$(state)" == Running ]]; then
    up=1
    rows="$(lsh sudo sh -c 'cd /home/agent/work 2>/dev/null && for d in */; do [ -d "$d" ] && printf "vm\t%s\t%s\n" "${d%/}" "$(du -sm -- "$d" | cut -f1)"; done' </dev/null | tr -d '\r')"
  else
    say "${C_D}VM is stopped: showing host-side data only (cyber up, then clean, to see VM projects)${C_0}"
  fi
  local d
  for d in "$OUT"/work/*/; do
    [[ -d "$d" ]] || continue
    rows+=$'\n'"mac"$'\t'"$(basename "$d")"$'\t'"$(du -sm "$d" | cut -f1)"
  done
  local oldmb; oldmb="$(find "$OUT/logs" -type f -mtime +14 -exec du -sk {} + 2>/dev/null | awk '{s+=$1} END {printf "%d", s/1024}')"
  local oldn; oldn="$(find "$OUT/logs" -type f -mtime +14 2>/dev/null | wc -l | tr -d ' ')"
  (( oldn > 0 )) && rows+=$'\n'"logs"$'\t'"$oldn logs older than 14 days"$'\t'"$oldmb"
  rows="$(sed '/^$/d' <<<"$rows")"
  [[ $MODE == local ]] && say "  ${C_D}on host: VM image $(du -sh "$HOME/.lima/$VM" 2>/dev/null | cut -f1) · results $(du -sh "$OUT" 2>/dev/null | cut -f1)${C_0}"
  [[ -n "$rows" ]] || { say "${C_G}✔${C_0} nothing to clean"; return 0; }
  sel="$(sort -t$'\t' -k3,3nr <<<"$rows" | awk -F'\t' '{
      where = ($1=="vm") ? "VM   work/" $2 : ($1=="mac") ? "Host out/work/" $2 : "Host " $2
      printf "%s\t%s\t%-52.52s %7d MB\n", $1, $2, where, $3 }' \
    | fzf --multi --height=60% --min-height=8 --reverse --border=rounded --border-label=" delete what? Tab = select, Enter = confirm, Esc = cancel " \
          --prompt='❯ ' --pointer='▶' --marker='✗' --delimiter=$'\t' --with-nth=3 --color="$FZF_COLORS,marker:red")" || return 0
  [[ -n "$sel" ]] || return 0
  say "${C_Y}Will delete:${C_0}"; cut -f3 <<<"$sel" | sed 's/^/  /' >&2
  read -r -p "Delete these permanently? [y/N] " a; [[ "$a" == y ]] || { say "cancelled"; return 0; }
  while IFS=$'\t' read -r kind name _; do
    case "$kind" in
      vm)   [[ -n "$name" && "$name" != */* && "$name" != . && "$name" != .. ]] && lsh sudo rm -r -- "/home/agent/work/$name" </dev/null ;;
      mac)  [[ -n "$name" && "$name" != */* && "$name" != . && "$name" != .. ]] && rm -r -- "$OUT/work/$name" ;;
      logs) find "$OUT/logs" -type f -mtime +14 -delete ;;
    esac
  done <<<"$sel"
  if (( up )); then lsh sudo sh -c 'apt-get clean >/dev/null 2>&1; fstrim / 2>/dev/null; df -h / | awk "NR==2{print \"  VM disk now: \"\$3\" / \"\$2}"' >&2 </dev/null || true; fi
  say "${C_G}✔${C_0} cleaned"
}

ui_task() {
  local task="$1"
  if [[ "$CUR_MODEL" == claude/* ]]; then run_host "$CUR_MODEL" "$task"; return 0; fi
  ui_up || return 0
  if [[ -z "$CUR_SESS" ]]; then CUR_SESS="ses_cyber$(date +%s)x$$"; CUR_TITLE="$(cut -c1-48 <<<"$task")"; fi
  AILAB_SESSION_ID="$CUR_SESS" run_logged "$CUR_MODEL" "$task" || true
  ( ui_sessions_refresh >/dev/null 2>&1 & )   # keep /1-/9 and the picker current without making the prompt wait
}

ui_optional_tool() {
  local tool="$1" text="$2" argument
  local arguments=()
  # Parse quotes without shell eval; target URLs/paths remain individual arguments.
  local encoded
  encoded="$(python3 -c 'import shlex,sys,json; print(json.dumps(shlex.split(sys.argv[1])))' "$text")" || return 0
  while IFS= read -r -d '' argument; do arguments+=("$argument"); done < <(
    python3 -c 'import json,sys; [sys.stdout.buffer.write(s.encode()+b"\0") for s in json.loads(sys.argv[1])]' "$encoded")
  if [[ "$tool" == tools ]]; then tools_command "${arguments[@]+"${arguments[@]}"}" || true
  else CYBER_TOOL_MODEL="$CUR_MODEL" tool_run "$tool" "${arguments[@]+"${arguments[@]}"}" || true; fi
}

ui_cmd() {
  local line="$1" c rest
  c="${line%% *}"; rest=""; [[ "$line" == *" "* ]] && rest="${line#* }"
  if [[ "$c" == "/" ]]; then
    c="$(ui_pick "commands" <<<"$UI_CMDS" | awk '{print $1}')" || return 0
    [[ -n "$c" ]] || return 0
  fi
  # shellcheck disable=SC2086
  case "$c" in
    /doctor)       onboarding_command doctor || true ;;
    /setup)        if onboarding_command setup; then CUR_MODEL="$(default_model)"; CUR_SESS=""; CUR_TITLE=""; ui_header; fi ;;
    /[1-9])        ui_session_n "${c#/}" ;;
    /recent|/r)    ui_recent ;;
    /model|/m)     ui_model $rest ;;
    /sessions|/s|/resume) ui_sessions $rest ;;
    /new|/n)       CUR_SESS=""; CUR_TITLE=""; say "${C_G}✔${C_0} new session" ;;
    /add)          ui_add $rest ;;
    /rm)           ui_rm $rest ;;
    /models|/list) ui_models_table >&2 ;;
    /quota)        ui_quota "$rest" ;;
    /tools|/kali|/strix|/shannon) ui_optional_tool "${c#/}" "$rest" ;;
    /fallback)     if [[ -n "$rest" ]]; then echo "$rest" > "$HERE/fallback"; fi; say "fallback order: $(fallbacks | tr '\n' ' ')" ;;
    /rounds)       [[ "$rest" =~ ^[0-9]+$ ]] && export AILAB_ROUNDS="$rest"; say "round limit: ${AILAB_ROUNDS:-12}" ;;
    /claude)       run_host "claude/" $rest ;;
    /tui)          ui_up && { if [[ -n "$CUR_SESS" ]]; then oc --session "$CUR_SESS"; else oc; fi; pull; } ;;
    /sh)           ui_up && { agent bash -l; pull; } ;;
    /status|/st)   ui_status ;;
    /clean)        ui_clean ;;
    /pull)         ui_up && { pull $rest; say "${C_G}✔${C_0} ${OUT/#$HOME/~}/work"; } ;;
    /out)          mkdir -p "$OUT"; open_output "$OUT" ;;
    /log)          logs_command "${rest:-1}" ;;
    /logs)         logs_command ;;
    /cve)          cve_command $rest ;;
    /theme)        ui_theme $rest ;;
    /key)          if [[ -n "$rest" ]]; then "$HERE/ailab" key $rest; else say "usage: /key <provider>"; fi ;;
    /config)       "$HERE/ailab" config ;;
    /down)         "$HERE/ailab" down ;;
    /clear)        printf '\033[2J\033[H'; ui_header ;;
    /help|/h|/\?)  say "$UI_CMDS"; say "${C_D}!command  run one command inside the VM${C_0}" ;;
    /quit|/q|/exit) return 9 ;;
    *)             say "${C_R}unknown command: $c${C_0} ${C_D}(type / and pick from the list)${C_0}" ;;
  esac
  return 0
}

ui_main() {
  set +e
  if [[ ! -f "$DEFAULT" && -t 0 && -t 1 ]]; then onboarding_command setup || return 1; fi
  CUR_MODEL="$(default_model)"
  quota_auto_refresh
  history -r "$UI_HIST" 2>/dev/null
  ( ui_sessions_refresh >/dev/null 2>&1 & )
  ui_header
  [[ "${1:-}" == resume ]] && ui_sessions
  local line p rc
  while :; do
    trap 'UI_INT=1' INT
    p=$'\001'"$C_L1"$'\002'"cyber"$'\001'"$C_0$C_D"$'\002'" $(ui_short "$CUR_MODEL")${CUR_TITLE:+ · $(cut -c1-24 <<<"$CUR_TITLE")}"$'\001'"$C_0$C_C"$'\002'" ❯ "$'\001'"$C_0"$'\002'
    ui_read "$p"; rc=$?
    (( rc == 130 )) && continue
    (( rc )) && break
    line="$UI_LINE"
    line="${line#"${line%%[![:space:]]*}"}"; line="${line%"${line##*[![:space:]]}"}"
    [[ -n "$line" ]] || continue
    history -s "$line"; history -w "$UI_HIST" 2>/dev/null
    case "$line" in
      exit|quit|q) break ;;
      clear|help)  ui_cmd "/$line" ;;
      /*) ui_cmd "$line"; [[ $? -eq 9 ]] && break ;;
      !*) ui_up && { agent bash -lc "${line#!}" </dev/null; pull; } ;;
      *)  ui_task "$line" ;;
    esac
  done
  trap - INT
  say "${C_D}bye${C_0}"
}
