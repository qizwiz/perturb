# perturb

A **program-perturbation kernel** built on [tree-sitter](https://tree-sitter.github.io/): it generates
code, structural, and environment faults, delegates truth to an external oracle, and can invert the
mutation loop into constrained proof/program repair. One perturbation is a declaration —
`perturb(artifact, SITE, TRANSFORM) → ORACLE` — and a *surviving* mutant is a finding: a place your
test suite can't tell the mutated program from the original.

The architecture is **language-general** — tree-sitter parses everything — but the *coverage is not
uniform*, and this README won't pretend otherwise (see [Language support](#language-support)). Generic
operator mutation and the structural families (`reorder`/`shrink`) work on any grammar; the `time` and
`absence` families are Python-specific today.

Where most mutation tools only swap operators, perturb treats the AST as a **graph** and mutates its
*shape*, and it can perturb the **environment**, not just the code:

| family | what it does |
|---|---|
| `code` | swap an operator for another of its grammatical class (`==`→`!=`, `and`→`or`, `+`→`-`, …) |
| `reorder` | permute sibling statements / positional args (skips commutative kwargs & dict pairs) — *structural* |
| `shrink` | delete a statement / empty a block — *structural* |
| `time` | freeze the clock, **type-aware** (`time.time()`→a float epoch; `datetime.utcnow()`→a datetime literal) |
| `absence` | make an external input (`subprocess.run`, a file read) return nothing |

The `code` family reuses [ts-thrash](./ts-thrash)'s operator classes (bundled here) so there is one
source of truth and no drift. It also has a **cellular-automaton mode** (`--ca`) for higher-order
(coupled) mutants over the mutation sites, and a **proof-repair search mode** (`--search`) that
inverts the gate: with a *failing* pristine and a kernel oracle (e.g. a Lean/type checker), a
*surviving* mutant is a **repair**.

## Language support

`language-general` means the *pipeline* (parse → find sites → splice → reparse) runs on any grammar
[`tree-sitter-language-pack`](https://github.com/Goldziher/tree-sitter-language-pack) ships. It does
**not** mean every family is meaningful everywhere. What is actually exercised:

| Language | parse | generic `code` | rich operator table | `reorder`/`shrink` | `time`/`absence` | proof tokens | gate shipped |
|---|:---:|:---:|:---:|:---:|:---:|:---:|---|
| Python | ✓ | ✓ | ✓ | ✓ | ✓ | — | reparse |
| Lean | ✓ | ✓ | — | ✓ | — | ✓ (`.mp`/`.mpr`, `.inl`/`.inr`, …) | external (kernel via `--test`) |
| any other grammar | ✓ | ✓ (glyph heuristic) | — | ✓ | — | — | reparse |

`✓` = exercised by `--selftest`. The last row is *architecturally supported but unmeasured*: the generic
glyph mutator and the structural families apply, but there is no per-language operator table or benchmark
yet, so treat coverage there as a starting point, not a guarantee.

The only oracle perturb **ships** is the reparse (a malformed mutant is stillborn, not counted).
Compile-gating, type-gating, or kernel-gating is whatever command you hand to `--test` — that is the
point: truth lives in the oracle, not in perturb.

## Install

```sh
pipx install git+https://github.com/qizwiz/perturb.git   # gives you the `perturb` command
```

or from a checkout — `./perturb` works without installing:

```sh
pip install tree-sitter-language-pack
git clone https://github.com/qizwiz/perturb && cd perturb
```

## Usage

```sh
./perturb FILE --test 'CMD' [--families code,reorder,shrink,time,absence] [--lang LANG] [--lines LO:HI] [--n N]
```

`--test` is the **oracle**: a shell command that exits non-zero when a mutant is *killed* (e.g. your
test suite). A mutant the command still passes is a **survivor** — a coverage gap. Example:

```sh
./perturb mymodule.py --test 'pytest tests/test_mymodule.py -q' --families code,reorder,shrink
```

Higher-order / structural search over the mutation graph:

```sh
./perturb mymodule.py --test 'pytest -q' --ca --ca-lattice ndim
```

A structured, reproducible report -- stable content-derived ids, spans, a diff and a
reproduction command per mutant (see [docs/output.md](docs/output.md)):

```sh
./perturb mymodule.py --test 'pytest -q' --report mutation.json
```

Or a **Stryker-compatible** report -- it validates against the real `mutation-testing-elements`
schema (checked in CI), so it loads in the [Stryker dashboard](https://dashboard.stryker-mutator.io):

```sh
./perturb mymodule.py --test 'pytest -q' --stryker report.json
```

## It passes its own mutation test

`./perturb --selftest` runs 41 discrimination cases: every family fires and compiles a valid mutant,
the `code` family agrees with ts-thrash, the typed time-freeze is type-correct, and the structural
families skip equivalent (commutative) mutants.

perturb is also pointed at its *own* source with its *own* selftest as the oracle (a self-hosting
mutation test — see [`demos/self_hosting`](demos/self_hosting)). That is not a slogan: it found a real
scoring bug. Python stores a source file's mtime at one-second resolution in the `.pyc` header, so
mutants written in the same second reused stale bytecode and killable mutants were scored *survived*,
non-deterministically. `tests/test_determinism.py` guards the fix.

## Demos

- [`demos/green_ai_suite`](demos/green_ai_suite) — an AI-style test suite with **100% line coverage**
  but a **0% mutation score**, next to a targeted suite (same coverage) that kills the mutants. The gap
  coverage can't see. `./demos/green_ai_suite/run.sh`.
- [`demos/self_hosting`](demos/self_hosting) — perturb mutation-testing its own engine.
  `./demos/self_hosting/run.sh`.

## Design

A perturbation is a byte-span splice — `(start, end, replacement, label)` — validated by re-parsing
(a malformed mutant is stillborn, not counted). Adding a language means adding operator classes;
adding a *kind* of mutation means adding a family (one generator function). The honest boundary: **no
family invents an oracle** — a survivor only means something against a real test command.

## License

MIT © Jonathan Hill
