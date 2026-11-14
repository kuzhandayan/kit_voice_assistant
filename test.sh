#!/bin/sh
# Runs every check against the running Docker setup.
#   docker compose up -d --build     (first)
#   ./test.sh                        lint + unit + API tests (no keys, no network)
#   ./test.sh --e2e                  also the real browser + microphone test (needs keys)
set -e

echo "== Backend: lint + tests (rules, permissions, confirm flow, voice, history, fallbacks)"
docker compose exec -T backend sh -c "ruff check app tests && pytest -q"

echo "== Frontend: types + tests"
docker compose exec -T frontend sh -c "npx tsc -b && npx vitest run"

if [ "$1" = "--e2e" ]; then
  echo "== End-to-end: real browser + microphone"
  python3 e2e/run_e2e.py --base http://localhost:5173
fi

echo "All checks passed."
