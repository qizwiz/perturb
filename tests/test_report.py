"""The --report JSON is well-formed, content-addressed, and REPRODUCIBLE: the mutation set
(id/span/status) is identical across runs. `oracle_seconds` is wall-clock and the only field
that varies, so it is stripped before comparison -- otherwise this test would pass vacuously
whenever the oracle is fast enough to round to the same time."""
import json
import os
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run(workdir, out):
    subprocess.run(
        [sys.executable, os.path.join(REPO, "perturb"), "m.py", "--lang", "python",
         "--test", "%s check.py" % sys.executable, "--report", out],
        cwd=workdir, capture_output=True, text=True,
    )


def _content(path):
    doc = json.load(open(path))
    for m in doc["mutants"]:
        m.pop("oracle_seconds", None)
    return doc


def test_report_is_wellformed_and_content_reproducible():
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "m.py"), "w") as f:
            f.write("def total():\n    return 2 * 3 + 1\n")
        with open(os.path.join(d, "check.py"), "w") as f:
            f.write("from m import total\nassert total() == 7\n")
        a, b = os.path.join(d, "a.json"), os.path.join(d, "b.json")
        _run(d, a)
        _run(d, b)
        assert _content(a) == _content(b), "mutation set is not reproducible across runs"
        doc = _content(a)
        assert doc["schema"].startswith("perturb-mutation-report/")
        assert doc["mutants"], "no mutants recorded"
        for k in ("id", "family", "file", "span", "original", "replacement", "status",
                  "diff", "reproduction"):
            assert k in doc["mutants"][0], "missing field: " + k
        ids = [m["id"] for m in doc["mutants"]]
        assert len(set(ids)) == len(ids), "mutation ids are not unique"
