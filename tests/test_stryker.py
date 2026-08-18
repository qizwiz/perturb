"""The --stryker output validates against the REAL Stryker mutation-testing-report-schema
(bundled alongside this test), so perturb's results load in the Stryker HTML report and the
hosted dashboard. jsonschema is optional; where it is absent the test skips rather than lying."""
import json
import os
import subprocess
import sys
import tempfile

import pytest

jsonschema = pytest.importorskip("jsonschema")

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA = os.path.join(os.path.dirname(__file__), "stryker_report_schema.json")
_STATUSES = {"Killed", "Survived", "NoCoverage", "CompileError", "RuntimeError",
             "Timeout", "Ignored", "Pending"}


def test_stryker_output_validates_against_real_schema():
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "m.py"), "w") as f:
            f.write("def total():\n    return 2 * 3 + 1\n")
        with open(os.path.join(d, "check.py"), "w") as f:
            f.write("from m import total\nassert total() == 7\n")
        out = os.path.join(d, "stryker.json")
        subprocess.run(
            [sys.executable, os.path.join(REPO, "perturb"), "m.py", "--lang", "python",
             "--test", "%s check.py" % sys.executable, "--stryker", out],
            cwd=d, capture_output=True, text=True,
        )
        doc = json.load(open(out))
        jsonschema.validate(doc, json.load(open(SCHEMA)))  # raises if non-conformant
        f = doc["files"]["m.py"]
        assert f["source"].startswith("def total"), "full source not embedded"
        assert f["mutants"], "no mutants"
        for m in f["mutants"]:
            assert m["status"] in _STATUSES, "status outside the Stryker enum: " + m["status"]
            loc = m["location"]["start"]
            assert loc["line"] >= 1 and loc["column"] >= 1, "line/column must be 1-based"
