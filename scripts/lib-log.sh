# Shared logging block per AGENTS.md. Source, do not execute.

log() {
  printf '[ INFO ] %s\n' "$*"
}
ok() {
  printf '[  OK  ] %s\n' "$*"
}
warn() {
  printf '[ WARN ] %s\n' "$*"
}
err() {
  printf '[ ERR  ] %s\n' "$*"
}
