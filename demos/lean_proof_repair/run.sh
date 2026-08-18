#!/usr/bin/env bash
# Lean proof-repair. perturb --search inverts the gate: the pristine proof FAILS, and a surviving
# mutant is a REPAIR the Lean KERNEL certifies. Needs Lean 4 (`lean` on PATH) + perturb's deps
# (pip install tree-sitter-language-pack).
set -euo pipefail
cd "$(dirname "$0")"
REPO="$(cd ../.. && pwd)"
command -v lean >/dev/null || { echo "this demo needs Lean 4 on PATH -- https://lean-lang.org"; exit 1; }
work="$(mktemp -d)"; cp broken.lean "$work/proof.lean"

echo "### 1. pristine proof -- the Lean kernel REJECTS it (wrong Iff direction):"
lean "$work/proof.lean" 2>&1 | grep -i 'error' | head -1 || true
echo
echo "### 2. perturb --search: a surviving mutant is a repair (the kernel is the oracle):"
python3 "$REPO/perturb" "$work/proof.lean" --lang lean --search --families code --test "lean $work/proof.lean" \
  | grep -E '"REPAIR"|"done"'
echo
echo "### 3. the repair, re-checked by lean INDEPENDENTLY:"
r="$work/proof.lean.repair.1"
echo "    repaired term: $(grep 'h\.mp' "$r" | tr -s ' ')"
lean "$r" && echo ">>> lean ACCEPTS the repair (rc=0) -- certified by the KERNEL, not by perturb."
rm -rf "$work"
