#!/usr/bin/env bash
# Run a command; on failure put the end of its output in a GitHub annotation so the cause is visible
# on the run summary without opening the raw log.
name="$1"; shift
log="$(mktemp)"
if "$@" 2>&1 | tee "$log"; [ "${PIPESTATUS[0]}" -ne 0 ]; then
  tail_text="$(tail -n 25 "$log" | tr '\n' '|' | cut -c1-1800)"
  echo "::error title=${name} failed::${tail_text}"
  exit 1
fi
