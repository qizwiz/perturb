#!/usr/bin/env bash
# The "green AI test suite" demo. An AI-style suite with 100% line coverage but
# type-only asserts cannot kill a single mutant; a targeted suite (same coverage) can.
set -euo pipefail
cd "$(dirname "$0")"
REPO="$(git rev-parse --show-toplevel)"
python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q "$REPO" pytest pytest-cov
PY="$PWD/.venv/bin/python"; PERTURB="$PWD/.venv/bin/perturb"

echo "### 1. The AI-style suite is GREEN at 100% line coverage:"
"$PY" -m pytest test_weak.py --cov=discount --cov-report=term-missing -q | grep -E 'discount.py|passed'
echo
echo "### 2. perturb vs that suite -- every mutant SURVIVES (0% mutation score):"
"$PERTURB" discount.py --lang python --test "$PY -m pytest test_weak.py -q" | grep '"event": "done"'
echo
echo "### 3. A targeted suite (same 100% coverage, real VALUE asserts) kills the logic mutants:"
"$PERTURB" discount.py --lang python --test "$PY -m pytest test_strong.py -q" | grep '"event": "done"'
echo
echo ">>> coverage said 100%. mutation said 0%. that gap is what perturb measures."
