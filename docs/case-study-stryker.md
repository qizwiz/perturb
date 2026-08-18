# Case study: perturb on Stryker (the mutation-tester, mutation-tested)

[Stryker](https://github.com/stryker-mutator/stryker-js) is the leading JavaScript/TypeScript
mutation-testing framework. Pointing perturb at it is the sharpest test there is: a mutation tester
mutation-testing the mutation tester. It's also real, well-tested, external TypeScript.

## Setup

Stryker is a pnpm workspace monorepo with a codegen step:

```sh
git clone https://github.com/stryker-mutator/stryker-js && cd stryker-js
pnpm install && pnpm run build          # generate + tsc -b (the whole workspace)
pnpm --filter @stryker-mutator/util run test:unit   # control: 120 passing
```

Then perturb, with a rebuild-then-test oracle (Stryker's tests run against built `.js`):

```sh
perturb packages/util/src/deep-merge.ts --lang typescript --cwd . \
  --test 'npx tsc -b packages/util/tsconfig.test.json >/dev/null 2>&1 && cd packages/util && npm run test:unit'
```

## Result

```
20 mutants, 13 killed, 7 survived  ->  65% mutation score
```

Every mutant is a **derived** operator swap — perturb was never hand-tabled for TypeScript; it reads
the operators off the grammar (`===`, `!==`, `||`, …) and thrashes each to every class sibling.

## The survivors, honestly triaged

| line | mutation | verdict |
|---|---|---|
| L18 | `defaultValue === undefined` → `== undefined` | **real gap** — `== undefined` also matches `null`; no test covers a null default |
| L18, L19 | `A || B` → `A && B` (the merge-guard) | **real gap** — flips the short-circuit; no test hits the one-condition-true case |
| L12, L16, L19, L20 | `!==` → `!=` on `typeof …` / string keys | **likely equivalent** — no coercion difference on those operands |

No bug is claimed against Stryker, and none was reported. A survivor is a *candidate for the
maintainer's judgment* -- and here the `||→&&` and `=== undefined` ones are concrete, actionable
test-adequacy gaps in a mature, well-tested framework. The strict-equality mutations (`===`/`!==`)
that surface them exist only because perturb derives its TypeScript operators from the grammar.

## Takeaway

perturb runs on real, well-tested external TypeScript -- Stryker's own -- produces a meaningful score,
and pinpoints exact lines its suite leaves unpinned, using operator mutation it derives with no hand
table for the language.
