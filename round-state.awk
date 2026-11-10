# Bounded state from one round of ANSI-free output. No full transcript in memory.
BEGIN { ask = ENVIRON["CYBER_ASK_RE"]; tool = ENVIRON["CYBER_TOOL_RE"] }
{
  line = $0
  sub(/^[[:space:]]+/, "", line)
  sub(/[[:space:]]+$/, "", line)
  if (line != "") last = line
  recent[NR % 4] = tolower($0)
  if ($0 ~ tool) used_tools = 1
  if (line ~ /^Error:/) {
    error = 1
    # Whole words: "generate" and "corporate" are not rate-limit errors.
    if (tolower(line) ~ /(^|[^[:alnum:]_])(limit(ed|s)?|quota|rate[ -]?limit(ed|ing)?|429|overloaded|unavailable|credits?|subscribe)([^[:alnum:]_]|$)/)
      limited = 1
  }
}
END {
  done = (last == "CYBER_DONE")
  needs_continue = used_tools
  for (i in recent) if (recent[i] ~ ask) needs_continue = 1
  print done + 0, error + 0, limited + 0, needs_continue + 0
}
