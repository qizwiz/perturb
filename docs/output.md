# perturb output: streaming events and the JSON report

perturb writes one JSON object per line to stdout as it runs (a stream you can `grep` or pipe),
and -- with `--report FILE` -- one structured report at the end.

## Streaming events (stdout, one JSON object per line)

| event | when | key fields |
|---|---|---|
| `control-pristine` | before mutating | `verdict` -- the oracle must PASS on the unmutated file, else the run aborts |
| `candidates` | after site discovery | `total`, `by_family` |
| `mutant` | per mutant | `family`, `label`, `verdict` (`killed`/`survived`/`stillborn`), `secs` |
| `done` | at the end | `by_family`, `killed`, `scored`, `rate`, `survivors` |
| `report` | only with `--report` | `path`, `mutants` (count written) |

```json
{"event": "candidates", "total": 14, "by_family": {"code": 14}}
{"event": "mutant", "family": "code", "label": "code L10 op:*->+", "verdict": "killed", "secs": 0.1}
{"event": "done", "killed": 11, "scored": 14, "rate": 79, "survivors": ["code L6 int+1:0"]}
```

## The `--report` JSON

`perturb FILE --test 'CMD' --report mutation.json` writes a single document:

| field | meaning |
|---|---|
| `schema` | `perturb-mutation-report/1` |
| `target` / `language` / `oracle` | the file mutated, its language, the `--test` command |
| `totals` | `scored`, `killed`, `survived`, `stillborn`, `rate` (%) |
| `by_family` | the same, split per family |
| `mutants[]` | one record per scored mutant (below) |

Each `mutants[]` record:

| field | meaning |
|---|---|
| `id` | SHA-1 of `file:start:end:replacement`, truncated -- **content-derived and stable** across runs/machines |
| `family` | `code`, `reorder`, `shrink`, `time`, `absence` (with detail for structural families) |
| `file` / `line` / `span` | where the mutation is (`span` is a byte range) |
| `original` / `replacement` | the exact bytes swapped |
| `status` | `killed` / `survived` / `stillborn` |
| `oracle_seconds` | wall-clock of the oracle for this mutant |
| `diff` | a one-line unified hunk (`@@ Ln @@` / `-` / `+`) |
| `reproduction` | a perturb command that re-runs this mutant alone |

The mutation SET (`id`/`span`/`status`) is **reproducible**: `id` is content-derived, keys are
sorted, and there is no timestamp, so two runs on the same input produce identical records.
`oracle_seconds` is wall-clock and the one field that varies -- strip it before diffing two
reports (`tests/test_report.py` does exactly this).

### Sample

```json
{
  "by_family": {
    "code": {
      "killed": 11,
      "rate": 79,
      "stillborn": 0,
      "survived": 3
    }
  },
  "language": "python",
  "mutants": [
    {
      "diff": "@@ L6 @@\n-     if pct < 0:\n+     if not (pct < 0):",
      "family": "code",
      "file": "discount.py",
      "id": "907db3fe3555",
      "label": "code L6 negate-if",
      "line": 6,
      "oracle_seconds": 0.1,
      "original": "pct < 0",
      "replacement": "not (pct < 0)",
      "reproduction": "perturb discount.py --lang python --lines 6:6 --families code --test 'pytest test_strong.py -q'",
      "span": {
        "end": 193,
        "start": 186
      },
      "status": "killed"
    },
    {
      "diff": "@@ L6 @@\n-     if pct < 0:\n+     if pct < 1:",
      "family": "code",
      "file": "discount.py",
      "id": "944afeb29311",
      "label": "code L6 int+1:0",
      "line": 6,
      "oracle_seconds": 0.1,
      "original": "0",
      "replacement": "1",
      "reproduction": "perturb discount.py --lang python --lines 6:6 --families code --test 'pytest test_strong.py -q'",
      "span": {
        "end": 193,
        "start": 192
      },
      "status": "survived"
    }
  ],
  "oracle": "pytest test_strong.py -q",
  "schema": "perturb-mutation-report/1",
  "target": "discount.py",
  "totals": {
    "killed": 11,
    "rate": 79,
    "scored": 14,
    "stillborn": 0,
    "survived": 3
  }
}
```

## Stryker-compatible export

`perturb FILE --test 'CMD' --stryker report.json` writes the [Stryker `mutation-testing-elements`](https://stryker-mutator.io/docs/mutation-testing-elements/) schema (schemaVersion 1), so perturb's results render in the Stryker HTML report and the hosted [dashboard](https://dashboard.stryker-mutator.io) -- interop, not a second ecosystem. The output is validated against the real schema in CI (`tests/test_stryker.py`, schema bundled at `tests/stryker_report_schema.json`).

- status maps: `killed -> Killed`, `survived -> Survived`, `stillborn -> CompileError`
- locations are 1-based line/column; each file entry carries its full `source`

```sh
perturb discount.py --lang python --test 'pytest test_strong.py -q' --stryker report.json
```

## Reproducing a single mutant

Every record carries a `reproduction` command, so a survivor is a one-command re-check:

```sh
perturb discount.py --lang python --lines 6:6 --families code --test 'pytest test_strong.py -q'
```

The `id` is the stable handle: it does not change as long as the mutation (file, span,
replacement) is the same, so a survivor can be tracked, referenced, or suppressed across runs.
