#!/usr/bin/env bash
# One command that checks the whole project (Mac / Linux). Run from the repo root:
#   bash scripts/check.sh            # everything
#   bash scripts/check.sh --quick    # skip the production build (faster)
# Stop `npm run dev` first: the build and the dev server share the .next folder.
set -u
cd "$(dirname "$0")/.."

quick=0
[ "${1:-}" = "--quick" ] && quick=1
results=()
fail=0

step() {
  local name="$1"; shift
  echo
  echo "=== $name ==="
  if "$@"; then results+=("PASS  $name"); else results+=("FAIL  $name"); fail=1; fi
}

# Pick Python: an activated environment first, then services/.venv, then python3.
if [ -n "${VIRTUAL_ENV:-}" ]; then PY=python
elif [ -x services/.venv/bin/python ]; then PY="$PWD/services/.venv/bin/python"
else PY=python3; fi

[ -d node_modules ] || step "npm ci (first run)" npm ci
step "Web lint" npm run lint
if [ "$quick" = 0 ]; then step "Web build + TypeScript" npm run build; fi
step "Python tests" bash -c "cd services && '$PY' -m pytest -q"
step "Swing JSON contract (sample)" "$PY" scripts/check_swing.py data/samples/swing_sample.json
step "Python service starts" "$PY" -c "import sys; sys.path.insert(0, 'services'); from pipeline.server import app; print('pipeline.server imports OK:', app.title)"

echo
echo "=== Summary ==="
printf '%s\n' "${results[@]}"
[ "$fail" = 0 ] && echo "All checks passed." || echo "Some checks failed: scroll up to the first FAIL."
exit "$fail"
