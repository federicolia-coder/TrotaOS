# Shared helpers for the in-VM checks. Each check prints exactly one line:
#   RESULT <name> PASS|FAIL|SKIP <note>
result() { printf 'RESULT %s %s %s\n' "$1" "$2" "${3:-}"; }
check() {  # check <name> <command...>: PASS if the command succeeds
    local name="$1"; shift
    local out
    if out="$("$@" 2>&1)"; then result "$name" PASS "$(echo "$out" | tail -1 | cut -c1-150)"
    else result "$name" FAIL "$(echo "$out" | tail -1 | cut -c1-150)"; fi
}
wait_for() {  # wait_for <seconds> <command...>
    local t="$1"; shift
    local end=$((SECONDS + t))
    until "$@" >/dev/null 2>&1; do
        [ $SECONDS -ge $end ] && return 1
        sleep 5
    done
}
section() { printf '\n===== %s =====\n' "$*"; }
