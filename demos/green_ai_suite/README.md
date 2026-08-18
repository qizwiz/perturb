# Demo: the green AI test suite

An AI coding agent will happily produce a test suite with **100% line coverage** that
asserts nothing about behavior. Coverage says healthy; the suite is hollow. Mutation
testing is the check that catches it.

`test_weak.py` executes every line and branch of `discount.py` but asserts only *types*
(`isinstance(..., float)`) — the AI-slop pattern. `test_strong.py` has the **same
coverage** but asserts *values*.

Run `./run.sh`. You'll see:

| suite | line coverage | perturb mutation score |
|---|---|---|
| `test_weak.py`   | 100% | **0 / 14 killed (0%)** |
| `test_strong.py` | 100% | **11 / 14 killed (79%)** |

Same coverage, opposite mutation score. The three mutants the strong suite still leaves
are genuine clamp-boundary equivalents (e.g. `pct < 0` → `pct < 1`, indistinguishable
without a fractional-percent test) — which is exactly the next test to add. That
add-a-test-kill-a-mutant loop is the workflow; coverage can't show it to you.
