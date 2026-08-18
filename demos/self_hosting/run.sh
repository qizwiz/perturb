#!/usr/bin/env bash
# perturb thrashing its OWN engine: mutate perturb_cli.py, oracle = perturb's own --selftest.
# A survivor is a place perturb's 41-case selftest does not pin down its own behavior.
set -euo pipefail
cd "$(dirname "$0")/../.."   # repo root, from this script's own location
echo "### perturb mutation-testing perturb (oracle = perturb --selftest):"
python3 perturb perturb_cli.py --lang python --test 'python3 perturb --selftest' --n 12 \
  | grep -E '"event": "done"'
echo
echo ">>> deterministic + honest. Survivors are real gaps in perturb's own selftest --"
echo ">>> and pointing perturb at itself is how the .pyc-staleness scoring bug was found."
