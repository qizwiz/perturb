# perturb

A language-agnostic **mutation-testing engine** built on [tree-sitter](https://tree-sitter.github.io/).
One perturbation is a declaration — `perturb(artifact, SITE, TRANSFORM) → ORACLE` — and a *surviving*
mutant is a finding: a place your test suite can't tell the mutated program from the original.

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

## Install

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

## It passes its own mutation test

`./perturb --selftest` runs 41 discrimination cases: every family fires and compiles a valid mutant,
the `code` family agrees with ts-thrash, the typed time-freeze is type-correct, and the structural
families skip equivalent (commutative) mutants. perturb has also been pointed at its *own* source with
its *own* selftest as the oracle — a self-hosting mutation test.

## Design

A perturbation is a byte-span splice — `(start, end, replacement, label)` — validated by re-parsing
(a malformed mutant is stillborn, not counted). Adding a language means adding operator classes;
adding a *kind* of mutation means adding a family (one generator function). The honest boundary: **no
family invents an oracle** — a survivor only means something against a real test command.

## License

MIT © Jonathan Hill
