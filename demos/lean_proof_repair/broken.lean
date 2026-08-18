-- A proof with ONE wrong token: `.mpr` where `.mp` is needed.
-- Iff.mpr : (p ↔ q) → q → p, but hp : p and the goal is q -- a type mismatch.
-- `perturb --search` finds the single token swap the Lean kernel accepts.
variable {p q : Prop}

theorem forward (h : p ↔ q) (hp : p) : q :=
  h.mpr hp
