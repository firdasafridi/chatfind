#!/usr/bin/env bash
# Everything CI runs, in the same order. The pre-push hook calls this; run it by hand any time.
#   scripts/check.sh          full gate
#   SKIP_E2E=1 scripts/check.sh   skip the browser tests
set -euo pipefail
cd "$(dirname "$0")/.."

# Use the repo venv when it exists (local), otherwise whatever python is on PATH (CI).
PY=${PYTHON:-$PWD/.venv/bin/python}
[ -x "$PY" ] || PY=python3

echo "==> backend: pytest (coverage >= 90%)"
(cd app && "$PY" -m pytest -p no:cacheprovider)

echo "==> web: lint + typecheck"
(cd app/web && pnpm run --silent check)

echo "==> web: unit tests (coverage >= 90%)"
(cd app/web && pnpm run --silent coverage)

if [ "${SKIP_E2E:-0}" != "1" ]; then
  echo "==> web: playwright e2e"
  (cd app/web && pnpm run --silent e2e)
fi

echo "==> all checks passed"
