"""Regression guard for the .pyc-staleness bug perturb found by thrashing itself.

Python stores a source file's mtime at ONE-SECOND resolution in the .pyc header, and
perturb rewrites the target + reruns the oracle many times per second. Before the fix,
mutants written in the same second reused a stale cached bytecode, so an import-based
oracle silently tested the WRONG program -- killable mutants were scored "survived",
non-deterministically. `_write_mutant` now forces a distinct, increasing whole-second
mtime, and the oracle runs with PYTHONDONTWRITEBYTECODE=1.
"""
import json
import os
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _score(workdir):
    out = subprocess.run(
        [sys.executable, os.path.join(REPO, "perturb"), "m.py",
         "--lang", "python", "--test", "%s check.py" % sys.executable],
        cwd=workdir, capture_output=True, text=True,
    ).stdout
    done = [json.loads(ln) for ln in out.splitlines() if '"event": "done"' in ln]
    assert done, "no done event:\n" + out
    return done[0]["killed"], done[0]["scored"]


def test_import_tested_mutant_scored_correctly_and_deterministically():
    with tempfile.TemporaryDirectory() as d:
        # A module with killable arithmetic, exercised THROUGH an import (the .pyc path).
        # total() == 7; every operator/int mutation (* -> +, + -> -, 2->3, ...) breaks it.
        with open(os.path.join(d, "m.py"), "w") as f:
            f.write("def total():\n    return 2 * 3 + 1\n")
        with open(os.path.join(d, "check.py"), "w") as f:
            f.write("from m import total\nassert total() == 7\n")

        scores = [_score(d) for _ in range(3)]

        # Deterministic: identical killed-count across identical runs.
        killed_counts = {k for k, _ in scores}
        assert len(killed_counts) == 1, "non-deterministic score: %r" % (scores,)

        # Correct: the killable mutants ARE killed (0 would mean the oracle never saw them).
        assert scores[0][0] >= 1, "killable mutant scored survived: %r" % (scores,)
