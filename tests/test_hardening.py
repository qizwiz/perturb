"""Hardening regressions: each test pins a real bug found by attacking the engine, and failed
before its fix. Unit cases import perturb_cli / ts_thrash directly; end-to-end cases drive the
`perturb` / `ts-thrash` shims through a subprocess, as the other tests here do."""
import json
import os
import subprocess
import sys
import tempfile
import time

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

import perturb_cli as P  # noqa: E402
import ts_thrash as T  # noqa: E402
from tree_sitter_language_pack import get_parser  # noqa: E402

PRISTINE = "def total():\n    return 2 * 3 + 1\n"
CHECK = "from m import total\nassert total() == 7\n"


def _cands(src, lang, fams):
    return P.candidates(src, get_parser(lang).parse(src), lang, fams, 1, 10**9)


def _workdir(d, pristine=PRISTINE, check=CHECK):
    with open(os.path.join(d, "m.py"), "w") as f:
        f.write(pristine)
    with open(os.path.join(d, "check.py"), "w") as f:
        f.write(check)


def _perturb(d, *args, target="m.py"):
    return subprocess.run(
        [sys.executable, os.path.join(REPO, "perturb"), target, "--lang", "python", *args],
        cwd=d, capture_output=True, text=True,
    )


def _events(out, name):
    return [json.loads(ln) for ln in out.splitlines()
            if ln.startswith("{") and json.loads(ln).get("event") == name]


# ---- 1. CA higher-order mutants spliced OVERLAPPING edits into a corrupt program ---------------
def test_ca_sites_never_overlap_and_hom_builds():
    # `if a < b:` yields negate-if over [a < b] AND op:< inside it. _one_per_site deduped by start
    # byte only, so both were kept and _apply_multi produced `if not (a < b)b:`.
    src = b"def f(a, b):\n    if a < b:\n        return 0\n    return 1\n"
    sites = P._one_per_site(_cands(src, "python", ["code"]))
    spans = sorted((c[0], c[1]) for c in sites)
    for (s1, e1), (s2, e2) in zip(spans, spans[1:]):
        assert e1 <= s2, "overlapping CA sites %r and %r" % ((s1, e1), (s2, e2))
    hom = P._apply_multi(src, [(c[0], c[1], c[2]) for c in sites])
    compile(hom, "<hom>", "exec")  # raises SyntaxError on the corrupt splice
    assert b">=" in hom, "the operator site must survive the de-overlap"


def test_apply_multi_rejects_overlap():
    with pytest.raises(ValueError):
        P._apply_multi(b"abcdef", [(1, 4, "X"), (2, 3, "Y")])


# ---- 2. shrink emitted EQUIVALENT mutants (guaranteed false survivors) -------------------------
def test_shrink_skips_comments_and_noop_edits():
    src = b"def f():\n    x = 1\n    # note\n    return x\n\ndef g():\n    pass\n"
    cands = _cands(src, "python", ["shrink"])
    assert not [c for c in cands if "del-comment" in c[4]], "deleting a comment is an equivalent mutant"
    noops = [c for c in cands if src[c[0]:c[1]].decode() == c[2]]
    assert not noops, "no-op (identical) mutants: %r" % [c[4] for c in noops]


def test_shrink_single_statement_beside_comment_becomes_pass():
    # a comment is not a statement: a block of [comment, stmt] has ONE statement to empty
    src = b"def f():\n    # why\n    return 1\n"
    cands = [c for c in _cands(src, "python", ["shrink"]) if "return_statement" in c[4]]
    assert cands and cands[0][2] == "pass"


# ---- 3. the "type-aware" freeze froze *_ns clocks (int) as a float ------------------------------
@pytest.mark.parametrize("clock", ["time_ns", "monotonic_ns", "perf_counter_ns"])
def test_ns_clocks_freeze_to_int(clock):
    src = ("import time\nx = time.%s() & 0xFF\n" % clock).encode()
    (c,) = _cands(src, "python", ["time"])
    mutant = src[:c[0]] + c[2].encode() + src[c[1]:]
    exec(compile(mutant, "<m>", "exec"), {})  # TypeError: float & int, before the fix
    assert isinstance(eval(c[2]), int)


# ---- 4. a timed-out oracle left its process tree RUNNING --------------------------------------
def test_timeout_kills_the_whole_oracle_tree():
    with tempfile.TemporaryDirectory() as d:
        # the outer shell forks a grandchild; killing only the shell orphans it, and the orphan
        # keeps running (and writing) underneath every later mutant's oracle.
        cmd = "%s -c \"import time; time.sleep(2); open('marker', 'w')\"; true" % sys.executable
        rc, out, _ = P.run_oracle(cmd, d, 1)
        assert (rc, out) == (-9, "TIMEOUT")
        time.sleep(2.5)
        assert not os.path.exists(os.path.join(d, "marker")), "orphaned oracle kept running"


# ---- 5. a stale backup from a killed run was OVERWRITTEN, destroying the only original ---------
def test_stale_backup_is_never_overwritten():
    with tempfile.TemporaryDirectory() as d:
        _workdir(d, pristine="def total():\n    return 2 * 3 - 1\n")  # left mutated by a crash
        bk = os.path.join(d, "m.py.perturb-orig")
        with open(bk, "w") as f:
            f.write(PRISTINE)  # the real original, only copy
        r = _perturb(d, "--test", "true")
        assert r.returncode != 0, "must refuse to run over a stale backup"
        assert open(bk).read() == PRISTINE, "stale backup (the original) was destroyed"
        r = _perturb(d, "--test", "true", "--ca")
        assert r.returncode != 0 and open(bk).read() == PRISTINE


# ---- 6. restoring a SYMLINKED target replaced the link and left the real file mutated ----------
def test_symlinked_target_is_restored_through_the_link():
    with tempfile.TemporaryDirectory() as d:
        _workdir(d)
        real = os.path.join(d, "real.py")
        os.rename(os.path.join(d, "m.py"), real)
        os.symlink("real.py", os.path.join(d, "m.py"))
        _perturb(d, "--test", "%s check.py" % sys.executable)
        assert os.path.islink(os.path.join(d, "m.py")), "symlink replaced by a regular file"
        assert open(real).read() == PRISTINE, "link target left holding the last mutant"


# ---- 7. --search: a REJECTED repair was still counted as a survivor ---------------------------
def test_search_rejected_repair_is_not_counted_survived():
    with tempfile.TemporaryDirectory() as d:
        # oracle: run #0 (pristine) fails, run #1 (first mutant) passes, every re-check fails --
        # the transiently-stale oracle the re-verify exists for.
        flaky = ("import os\nn = int(open('n').read()) if os.path.exists('n') else 0\n"
                 "open('n', 'w').write(str(n + 1))\nraise SystemExit(0 if n == 1 else 1)\n")
        _workdir(d, check=flaky)
        rep = os.path.join(d, "r.json")
        r = _perturb(d, "--test", "%s check.py" % sys.executable, "--search", "--n", "1",
                     "--families", "code", "--report", rep)
        assert _events(r.stdout, "REPAIR-REJECTED"), r.stdout
        (done,) = _events(r.stdout, "done")
        assert done["by_family"]["code"]["survived"] == 0, done
        doc = json.load(open(rep))
        assert doc["totals"]["survived"] == 0
        assert [m["status"] for m in doc["mutants"]] == ["killed"]
        assert not [f for f in os.listdir(d) if ".repair." in f]


# ---- 8. ts-thrash still had the .pyc-staleness bug perturb had fixed --------------------------
def test_ts_thrash_scores_import_tested_mutants():
    with tempfile.TemporaryDirectory() as d:
        _workdir(d)
        # Pin m.py's mtime inside the oracle: that is the same-second write that makes a cached
        # .pyc look fresh, made deterministic. Every mutant here is same-size and breaks total().
        oracle = ("%s -c \"import os; os.utime('m.py', (1700000000, 1700000000))\" && %s check.py"
                  % (sys.executable, sys.executable))
        out = subprocess.run(
            [sys.executable, os.path.join(REPO, "ts-thrash"), "m.py", "--lang", "python",
             "--test", oracle], cwd=d, capture_output=True, text=True,
        ).stdout
        (done,) = _events(out, "done")
        assert done["scored"] >= 3 and done["survived"] == 0, done


def test_ts_thrash_refuses_stale_backup():
    with tempfile.TemporaryDirectory() as d:
        _workdir(d)
        bk = os.path.join(d, "m.py.tsthrash-orig")
        with open(bk, "w") as f:
            f.write("ORIGINAL")
        r = subprocess.run(
            [sys.executable, os.path.join(REPO, "ts-thrash"), "m.py", "--lang", "python",
             "--test", "true"], cwd=d, capture_output=True, text=True,
        )
        assert r.returncode != 0 and open(bk).read() == "ORIGINAL"


def test_ts_thrash_timeout_kills_the_whole_oracle_tree():
    with tempfile.TemporaryDirectory() as d:
        cmd = "%s -c \"import time; time.sleep(2); open('marker', 'w')\"; true" % sys.executable
        assert T.run_oracle(cmd, d, 1)[:2] == (-9, "TIMEOUT")
        time.sleep(2.5)
        assert not os.path.exists(os.path.join(d, "marker"))


# ---- 9. the restored original was OLDER than the last mutant (mtime-driven builds go stale) ----
def test_restored_file_is_newer_than_every_mutant():
    with tempfile.TemporaryDirectory() as d:
        _workdir(d)
        log = ("%s -c \"import os; open('mt', 'a').write('%%d\\n' %% os.stat('m.py').st_mtime)\""
               % sys.executable)
        _perturb(d, "--test", "%s && %s check.py" % (log, sys.executable))
        seen = [int(x) for x in open(os.path.join(d, "mt")).read().split()]
        assert len(seen) >= 2
        # `make` et al. rebuild only if the source is newer than the artifact built from the last
        # mutant; an older restored source leaves that MUTANT build in place after the run.
        assert os.stat(os.path.join(d, "m.py")).st_mtime > max(seen)


# ---- 10. --n 0 crashed with ZeroDivisionError ------------------------------------------------
def test_n_must_be_positive():
    with tempfile.TemporaryDirectory() as d:
        _workdir(d)
        r = _perturb(d, "--test", "true", "--n", "0")
        assert r.returncode == 2 and "Traceback" not in r.stderr, r.stderr
