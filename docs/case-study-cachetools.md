# Case study: perturb on cachetools

[cachetools](https://github.com/tkem/cachetools) is a widely-used pure-Python caching library with
a **312-test suite**. This is perturb run against real, well-tested external code -- not a toy.

## Setup

```sh
git clone https://github.com/tkem/cachetools && cd cachetools
pip install -e . pytest
perturb src/cachetools/__init__.py --lang python --cwd . \
        --test 'python -m pytest -q -x' --families code --n 40 \
        --report report.json --stryker stryker.json
```

## Result

The suite passes on the unmutated file (the control), then:

```
40 mutants, 39 killed, 1 survived  ->  98% mutation score
```

cachetools is **well-tested** -- perturb confirms it and pinpoints the one line the suite does not
distinguish.

## The survivor, honestly triaged

```
L274  curr = LFUCache._Link(link.count + 1)   ->   link.count - 1
```

The 312 tests do not tell `+ 1` from `- 1` here. A real gap, or an *equivalent mutant*? I tried to
construct an LFU scenario where the two evict different keys and could not in several attempts -- the
`count` acts as a frequency *label* while eviction follows the linked-list order, so the mutation is
**plausibly equivalent**. That is the honest reality of mutation testing: a survivor is a *candidate
for the maintainer's judgment*, not a proven bug. perturb's job is to hand you the exact line; yours
is to decide. (No bug is claimed here, and none was reported to cachetools.)

## Interop on real code

The same run emitted a **Stryker-schema report** (`stryker.json`, ~40 KB) for the 789-line module,
and it **validates against the upstream `mutation-testing-elements` schema** -- so a real OSS run
drops straight into the Stryker HTML report and dashboard, not just the bundled demo.

## Takeaway

perturb runs cleanly on real, well-tested OSS, produces a meaningful score (98% on a 40-mutant sample
of the core module), integrates with the existing dashboard ecosystem, and surfaces the precise lines
a suite leaves unpinned. It does not manufacture bugs -- a survivor is an honest question, not an answer.
