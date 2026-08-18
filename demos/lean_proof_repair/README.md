# Demo: Lean proof-repair

Most mutation tools only *break* code. perturb can run the loop **backwards**: with `--search`, the
pristine artifact is expected to FAIL, and a surviving mutant is a **repair**. Point it at a broken
Lean proof with the Lean **kernel** as the oracle, and a survivor is a proof the kernel accepts.

`broken.lean` has one wrong token -- `h.mpr hp` where `h.mp hp` is needed (`Iff.mpr : (p↔q)→q→p`, but
`hp : p` and the goal is `q`, a type mismatch). Run `./run.sh` (needs **Lean 4** on PATH +
`pip install tree-sitter-language-pack`):

```
1. pristine  -> lean REJECTS (application type mismatch)
2. --search  -> REPAIR: lean:mpr->mp
3. repair    -> h.mp hp ; lean ACCEPTS (rc=0)
```

perturb proposes the token swap; the **Lean kernel decides** whether it is a real proof -- perturb
never certifies anything itself, the oracle is the truth. This is the CEGIS / proof-repair shape
(propose → an unfakeable checker adjudicates), and it is the one thing no operator-only mutation tool
does. The swappable Lean tokens are direction/projection pairs LLMs commonly invert: `mp/mpr`,
`inl/inr`, `left/right`, `fst/snd`, `le/lt`.
