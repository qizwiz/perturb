#!/usr/bin/env python3
"""perturb -- ONE perturbation engine, many families. A perturbation is a DECLARATION:

    perturb(artifact, SITE, TRANSFORM) -> ORACLE -> a SURVIVING perturbation is the finding.

Extracted 2026-08-12 ("keep generalizing"). Every existing thrasher is one
FAMILY of this shape; perturb runs them over one tree-sitter engine, so a survivor is a finding
whether the perturbation was a code-operator swap, a frozen clock, or an emptied input.

WHY THIS AND NOT ts-thrash: ts-thrash mutates only CODE (operators) -- the cell mewt also owns.
perturb's genuine add is the ENVIRONMENT families that mewt has no equivalent for, because their
value is universal but their MECHANISM is idiom-coupled:
  code     swap an operator for another of its grammatical class     (reuses ts-thrash -- ONE source)
  time     freeze the clock, TYPE-AWARE: time.time()->float epoch,    (timing-assumption bugs; the
           datetime.utcnow()/timezone.now()->a datetime LITERAL        typed value is why utcnow does
           (a float would be a type-error stillborn, not a freeze)     not become a stillborn)
  absence  make an external input return NOTHING and demand the        (absence-vs-health bugs, the
           suite notice: subprocess/os -> empty                        substrate's #1 recurring shape)

Sites are ASKED of the target where possible (ts-thrash mines operator classes from the grammar);
the idiom lists for time/absence are the extensible seam (add datetime/ORM idioms per ecosystem).
The honest boundary, unchanged: EFFECTS are not askable in an effect-untyped language, and no
family invents an ORACLE -- a survivor only means something against a real test command.

  perturb FILE --test 'CMD' [--families code,time,absence] [--lang L] [--lines LO:HI] [--n N]
  perturb FILE --test 'CMD' --ca [--ca-lattice tape|tree|ndim] [--ca-dims N] [--generations G]
  perturb --selftest

Verdicts per family: killed (CMD fails) / survived (CMD passes -> the artifact is not pinned there)
/ stillborn (mutant does not build -- excluded from the rate, reported). The pristine control runs
FIRST; if it fails, perturb refuses to score (a broken harness scores nothing).

--ca is HIGHER-ORDER mutation via a CELLULAR AUTOMATON over the operator sites (JH's Prize-3 CA
turned into a mutant generator): a rule evolved from a single seed selects which sites mutate
SIMULTANEOUSLY, so a SURVIVING higher-order mutant is a COUPLED coverage gap a first-order sweep
cannot express. A CA is just a rule over a NEIGHBOURHOOD, so the lattice is a DATA choice, not an
architecture -- 1-D, n-D and the graph are the same parity engine over different neighbourhoods:
  tape  a 1-D traversal tape under an elementary rule (default Rule 30)   -- JH's own CA
  ndim  n QUANTIZED structural axes (depth, sibling-rank, subtree-size, block-nesting, op-class);
        sites are neighbours within Chebyshev-1 in all n -> structurally-similar sites co-mutate
  tree  the syntax tree AS the lattice (dimension-free -- the answer to "why not more than 2-D":
        the object is a GRAPH, so the CA lives on it and a co-mutated set is a connected subtree)
"""

import argparse
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import time

from tree_sitter_language_pack import get_parser

# Reuse ts-thrash for the CODE family -- ONE source of operator classes, no second table to drift.
import ts_thrash as _TT

FROZEN_FLOAT = "1754400000.0"
FROZEN_DT = "__import__('datetime').datetime(2025, 8, 5, 12, 0, 0)"

# ---- family: TIME (typed clock freeze) -----------------------------------------------------------
FLOAT_CLOCKS = {
    "time",
    "time_ns",
    "monotonic",
    "perf_counter",
    "monotonic_ns",
    "perf_counter_ns",
}
DATETIME_CLOCKS = {"utcnow", "now", "today", "utcfromtimestamp"}


def _call_name(node, src):
    fn = node.child_by_field_name("function")
    if fn is None:
        return None, 0
    name = src[fn.start_byte : fn.end_byte].decode("utf-8", "replace").split(".")[-1]
    args = node.child_by_field_name("arguments")
    argc = sum(1 for c in args.children if c.is_named) if args else 0
    return name, argc


def fam_time(node, src, lang):
    if lang != "python" or node.type != "call":
        return None
    name, argc = _call_name(node, src)
    if name in FLOAT_CLOCKS and argc == 0:
        return (node.start_byte, node.end_byte, FROZEN_FLOAT, "freeze-float:%s" % name)
    if name in DATETIME_CLOCKS and argc == 0:
        return (node.start_byte, node.end_byte, FROZEN_DT, "freeze-datetime:%s" % name)
    return None


# ---- family: ABSENCE (external input returns nothing) --------------------------------------------
# (call-name -> replacement expression). Idiom-coupled by design; extend per ecosystem.
ABSENCE = {
    "run": "__import__('types').SimpleNamespace(returncode=0, stdout='', stderr='')",
    "check_output": "b''",
    "listdir": "[]",
    "exists": "False",
    "isfile": "False",
    "read": "''",
}


def fam_absence(node, src, lang):
    if lang != "python" or node.type != "call":
        return None
    name, _ = _call_name(node, src)
    if name in ABSENCE:
        return (node.start_byte, node.end_byte, ABSENCE[name], "absent:%s" % name)
    return None


FAMILIES = {
    "time": fam_time,
    "absence": fam_absence,
}  # "code" handled via ts-thrash / universal

# ---- family: STRUCTURAL (tree/graph moves, 2026-08-18) --------------------------------------
# The AST is a GRAPH; these mutate its SHAPE (reorder siblings, delete a subtree) -- the moves an
# operator-swap cannot express, where the coverage signal for STRUCTURAL fixes lives.
_REORDER_TYPES = {"block", "module", "argument_list", "expression_list", "parameters"}
_COMMUTES = {"keyword_argument", "pair"}  # commute -> reorder = equivalent mutant


def fam_reorder(node, src, lang):
    if node.type not in _REORDER_TYPES:
        return
    kids = [c for c in node.children if c.is_named]
    for i in range(len(kids) - 1):
        a, b = kids[i], kids[i + 1]
        if a.type == "comment" or b.type == "comment":
            continue
        if a.type in _COMMUTES and b.type in _COMMUTES:
            continue
        between = src[a.end_byte:b.start_byte]
        repl = (src[b.start_byte:b.end_byte] + between + src[a.start_byte:a.end_byte]).decode("utf-8", "replace")
        yield (a.start_byte, b.end_byte, repl, "reorder:%s<->%s" % (a.type, b.type))


def fam_shrink(node, src, lang):
    if node.type not in ("block", "module"):
        return
    kids = [c for c in node.children if c.is_named]
    for i, k in enumerate(kids):
        if len(kids) == 1:
            yield (k.start_byte, k.end_byte, "pass", "shrink:del-%s" % k.type)
        elif i + 1 < len(kids):
            yield (k.start_byte, kids[i + 1].start_byte, "", "shrink:del-%s" % k.type)
        else:
            yield (k.start_byte, k.end_byte, "", "shrink:del-%s" % k.type)


STRUCT_FAMILIES = {"reorder": fam_reorder, "shrink": fam_shrink}


# ---- family: CODE, GRAMMAR-AGNOSTIC ------------------------------------------------------------
# For any language WITHOUT a ts-thrash table (Rust, C, JS, Java, ...): mutate operator GLYPHS.
# The insight that makes this need no per-language table -- operator glyphs are shared across the
# whole C-family + Python, and tree-sitter emits them as UNNAMED tokens sitting BETWEEN two named
# operands. So "an operator in binary position" is a purely structural query, and the swap targets
# are a universal glyph algebra. (Tabled langs keep ts-thrash's richer mutators -- ONE source.)
SWAP_GLYPH = {
    "==": ["!="],
    "!=": ["=="],
    "===": ["!=="],
    "!==": ["==="],  # JS/TS strict equality -- adversarially found missing (the loose
    #                                  == was mutated, the STANDARD === was skipped, so "any tree-sitter
    #                                  language" was Potemkin for JS/TS until this line).
    "<": [">", "<="],
    ">": ["<", ">="],
    "<=": [">=", "<"],
    ">=": ["<=", ">"],
    "&&": ["||"],
    "||": ["&&"],
    "and": ["or"],
    "or": ["and"],
    "+": ["-"],
    "-": ["+"],
    "*": ["/"],
    "/": ["*"],
    "%": ["*"],
}


def fam_code_universal(node, src, lang):
    """Yield (start, end, repl, label) for each operator token of `node` that sits in BINARY
    position (a named sibling on each side -- so never a unary minus, never a type/generic '<').
    """
    kids = node.children
    for i, c in enumerate(kids):
        if c.is_named:
            continue
        glyph = src[c.start_byte : c.end_byte].decode("utf-8", "replace")
        if glyph not in SWAP_GLYPH:
            continue
        prev_named = any(k.is_named for k in kids[:i])
        next_named = any(k.is_named for k in kids[i + 1 :])
        if not (prev_named and next_named):
            continue
        for repl in SWAP_GLYPH[glyph]:
            yield (c.start_byte, c.end_byte, repl, "op:%s->%s" % (glyph, repl))


LEAN_PROOF_SWAPS = {
    "mp": "mpr",
    "mpr": "mp",  # Iff direction (h.mp <-> h.mpr) -- the commonest LLM proof error
    "inl": "inr",
    "inr": "inl",  # Or.inl / Or.inr
    "left": "right",
    "right": "left",  # And / conjunction projections
    "fst": "snd",
    "snd": "fst",  # product projections
    "le": "lt",
    "lt": "le",  # order predicates the LLM confuses (<= vs <)
}


def fam_lean_proof(node, src, lang):
    """Yield (start, end, repl, label) for Lean PROOF-token swaps -- direction/projection tokens the
    LLM commonly gets backwards (Iff .mp/.mpr, Or .inl/.inr, .left/.right, .fst/.snd, le/lt). These
    are NAMED identifier leaves (fam_code_universal sees only UNNAMED glyphs), so they need this
    branch. For proof-SEARCH the kernel is the filter, so the swap is unconditional on the token.
    """
    if lang != "lean" or node.child_count != 0 or not node.is_named:
        return
    text = src[node.start_byte : node.end_byte].decode("utf-8", "replace")
    # the lean grammar tokenizes a projection like `h.mpr` as ONE dotted identifier, so the
    # swappable token is the segment AFTER the last dot -- mutate just that segment's byte span.
    tail = text.rsplit(".", 1)[-1]
    if tail in LEAN_PROOF_SWAPS:
        rep = LEAN_PROOF_SWAPS[tail]
        off = node.end_byte - len(tail.encode())
        yield (off, node.end_byte, rep, "lean:%s->%s" % (tail, rep))


def _parses_clean(src_bytes, lang):
    """Language-agnostic 'does it build' proxy: the mutant re-parses with no ERROR/MISSING node.
    (For python the engine also has compile(); for Rust/Go/etc this is the portable gate.)
    """
    root = get_parser(lang).parse(src_bytes).root_node
    for n in _walk(root):
        if n.type == "ERROR" or n.is_missing:
            return False
    return True


def _walk(node):
    yield node
    for c in node.children:
        yield from _walk(c)


def candidates(src_bytes, tree, lang, families, lo, hi):
    out = []
    table = _TT.LANG.get(lang, {})
    if "code" in families and table:
        for c in _TT.candidates(tree, src_bytes, table, lo, hi):
            out.append((c[0], c[1], c[2], "code", "%s L%d %s" % ("code", c[3], c[4])))
    elif "code" in families:  # untabled language -> universal glyph mutation
        for node in _walk(tree.root_node):
            ln = node.start_point[0] + 1
            if not (lo <= ln <= hi):
                continue
            for start, end, repl, lab in fam_code_universal(node, src_bytes, lang):
                out.append((start, end, repl, "code", "code L%d %s" % (ln, lab)))
            for start, end, repl, lab in fam_lean_proof(node, src_bytes, lang):
                out.append((start, end, repl, "code", "code L%d %s" % (ln, lab)))
    envfams = [(f, FAMILIES[f]) for f in families if f in FAMILIES]
    if envfams:
        for node in _walk(tree.root_node):
            ln = node.start_point[0] + 1
            if not (lo <= ln <= hi):
                continue
            for fam, fn in envfams:
                r = fn(node, src_bytes, lang)
                if r:
                    out.append((r[0], r[1], r[2], fam, "%s L%d %s" % (fam, ln, r[3])))
    structfams = [(f, STRUCT_FAMILIES[f]) for f in families if f in STRUCT_FAMILIES]
    if structfams:
        for node in _walk(tree.root_node):
            ln = node.start_point[0] + 1
            if not (lo <= ln <= hi):
                continue
            for fam, fn in structfams:
                for r in (fn(node, src_bytes, lang) or []):
                    if not _parses_clean(src_bytes[:r[0]] + r[2].encode() + src_bytes[r[1]:], lang):
                        continue
                    out.append((r[0], r[1], r[2], fam, "%s L%d %s" % (fam, ln, r[3])))
    seen, uniq = set(), []
    for c in out:
        k = (c[0], c[1], c[2])
        if k not in seen:
            seen.add(k)
            uniq.append(c)
    return uniq


# A distinct, strictly-increasing WHOLE-SECOND mtime per mutant. Python stores the source
# mtime at one-second resolution in the .pyc header, so two mutants written in the SAME
# second reuse a stale cached bytecode and an import-based oracle silently scores the WRONG
# program -- non-deterministic, under-counted survivors. perturb found this by thrashing itself.
_MUTANT_TICK = 0


def _write_mutant(path, data):
    global _MUTANT_TICK
    with open(path, "wb") as f:
        f.write(data)
    _MUTANT_TICK += 2
    mt = int(time.time()) + _MUTANT_TICK
    os.utime(path, (mt, mt))


# Belt-and-suspenders: stop the oracle writing new .pyc so a later run cannot trust one either.
_ORACLE_ENV = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}


def run_oracle(cmd, cwd, timeout):
    t0 = time.monotonic()
    try:
        r = subprocess.run(
            cmd, shell=True, cwd=cwd, capture_output=True, text=True,
            timeout=timeout, env=_ORACLE_ENV,
        )
        return r.returncode, (r.stdout + r.stderr), round(time.monotonic() - t0, 1)
    except subprocess.TimeoutExpired:
        return -9, "TIMEOUT", timeout


def classify_verdict(rc, out, stillborn_marks):
    """The pure oracle-verdict decision, extracted from the I/O sweeps so it is unit-testable and
    SHARED by sweep + ca_sweep: rc==0 -> survived; a build-failure marker in the output -> stillborn
    (excluded from the rate); otherwise the test failed -> killed."""
    if rc == 0:
        return "survived"
    if any(m in out for m in stillborn_marks):
        return "stillborn"
    return "killed"


# ---- CA mode: HIGHER-ORDER mutants generated by an elementary cellular automaton over the ----
# operator tape. The mutable sites (in traversal order) are the CA's 1-D lattice; an elementary
# rule (default 30 -- JH's Prize-3 CA, and a bona-fide PRNG) evolved from a single-cell seed emits,
# per generation, a mask that selects which sites mutate SIMULTANEOUSLY. gen 0 = a 1-site (FOM)
# mutant; the order grows with each generation. A SURVIVING higher-order mutant is a coupled
# coverage gap -- k operator sites that, changed together, the suite does not catch -- which a
# first-order sweep cannot express. Deterministic + reproducible from (rule, seed), unlike random HOM.
def elementary_ca(rule, row, gens):
    """Yield `gens` successive rows of elementary CA `rule` over `row` (wrapped lattice)."""
    length = len(row)
    cur = list(row)
    for _ in range(gens):
        yield list(cur)
        cur = [
            (
                rule
                >> (
                    (cur[(i - 1) % length] << 2) | (cur[i] << 1) | cur[(i + 1) % length]
                )
            )
            & 1
            for i in range(length)
        ]


def _one_per_site(cands):
    """One canonical swap per operator site (dedupe by start byte, keep the first replacement)."""
    seen, out = set(), []
    for c in sorted(cands, key=lambda x: x[0]):
        if c[0] not in seen:
            seen.add(c[0])
            out.append(c)
    return out


def _apply_multi(src, edits):
    """Splice several non-overlapping (start, end, repl) edits into one mutant. Descending order
    keeps earlier byte offsets valid as later ones are replaced."""
    for start, end, repl in sorted(edits, key=lambda e: e[0], reverse=True):
        src = src[:start] + repl.encode() + src[end:]
    return src


def _tree_graph(root):
    """The syntax tree AS a graph: nodes keyed by (start, end, type) (tree-sitter node objects are
    transient, so identity must be by span+type); adjacency = parent<->child edges. This is the
    dimension-free lattice -- the answer to 'why not more than 2-D': the object is a GRAPH, so the
    CA lives on it directly rather than on any fixed-D projection of it."""
    ids: dict = {}
    adj: dict = {}
    order: list = []

    def reg(n):
        k = (n.start_byte, n.end_byte, n.type)
        if k not in ids:
            ids[k] = len(order)
            order.append(k)
            adj[ids[k]] = set()
        return ids[k]

    stack = [root]
    reg(root)
    while stack:
        n = stack.pop()
        ni = reg(n)
        for c in n.children:
            ci = reg(c)
            adj[ni].add(ci)
            adj[ci].add(ni)
            stack.append(c)
    return order, adj, ids


def _node_id_at(root, ids, start, end):
    """id of the DEEPEST node whose span contains [start, end) -- the site's cell in the tree graph."""
    node, key = root, (root.start_byte, root.end_byte, root.type)
    changed = True
    while changed:
        changed = False
        for c in node.children:
            if c.start_byte <= start and c.end_byte >= end:
                node, key, changed = c, (c.start_byte, c.end_byte, c.type), True
                break
    return ids.get(key)


def ca_graph_parity(adj, seed_ids, gens):
    """PARITY rule on the tree graph: a node lives next iff an ODD number of its tree-neighbours
    (parent + children) is live. Totalistic, so it handles arbitrary arity = arbitrary local
    dimension; additive, so it is deterministic and seed-reproducible like the 1-D/2-D additive rules.
    """
    cur = set(seed_ids)
    for _ in range(gens):
        yield set(cur)
        cnt: dict = {}
        for nid in cur:
            for m in adj.get(nid, ()):
                cnt[m] = cnt.get(m, 0) + 1
        cur = {nid for nid, c in cnt.items() if c & 1}


def _depth_at(root, start, end):
    """Depth of the DEEPEST tree node whose byte span contains [start, end) -- the site's y in the
    tree's natural 2-D embedding (y = nesting depth, x = reading position)."""
    node, depth, changed = root, 0, True
    while changed:
        changed = False
        for c in node.children:
            if c.start_byte <= start and c.end_byte >= end:
                node, depth, changed = c, depth + 1, True
                break
    return depth


def _masks_1d(sites, rule, gens, seed_index):
    """A traversal-order tape (lossy: DFS-adjacent, not structure-adjacent) under elementary `rule`."""
    length = len(sites)
    seed = [0] * length
    seed[seed_index if seed_index is not None else length // 2] = 1
    for row in elementary_ca(rule, seed, gens):
        yield [i for i in range(length) if row[i]]


def _find_node(root, start, end):
    node, changed = root, True
    while changed:
        changed = False
        for c in node.children:
            if c.start_byte <= start and c.end_byte >= end:
                node, changed = c, True
                break
    return node


BLOCK_TYPES = {
    "function_definition",
    "function_declaration",
    "function_item",
    "if_statement",
    "for_statement",
    "while_statement",
    "block",
    "if_expression",
    "match_expression",
    "method_declaration",
    "func_literal",
    "closure_expression",
    "match_arm",
}


def _op_class(label):
    if "op:" in label:
        op = label.split("op:")[1].split("->")[0]
        if op in ("==", "!=", "<", ">", "<=", ">="):
            return 0
        if op in ("&&", "||", "and", "or"):
            return 1
        return 2
    return 3


def _site_features(sites, root):
    """Per-site QUANTIZED structural axes -- small-range so many sites SHARE cells (a raw position
    rank is unique per site and would defeat clustering). Axes: nesting depth, sibling rank, log2
    subtree-size, block-nesting (fn/if/for ancestors), operator class. n-D = take the first n.
    """
    feats = []
    for c in sites:
        node = _find_node(root, c[0], c[1])
        depth, sib, blocks = 0, 0, 0
        n = node
        while n.parent is not None:
            depth += 1
            n = n.parent
        p = node.parent
        if p is not None:
            for r, ch in enumerate(p.children):
                if (ch.start_byte, ch.end_byte, ch.type) == (
                    node.start_byte,
                    node.end_byte,
                    node.type,
                ):
                    sib = r
                    break
        n = node
        while n is not None:
            if n.type in BLOCK_TYPES:
                blocks += 1
            n = n.parent
        sub = (node.end_byte - node.start_byte).bit_length()
        feats.append(
            (depth, min(sib, 12), min(sub, 14), min(blocks, 12), _op_class(c[4]))
        )
    return feats


def _masks_ndim(sites, root, dims, gens, seed_index):
    """n-D structural lattice: sites are neighbours iff within Chebyshev-1 in ALL `dims` feature
    axes. Same parity engine as the tree graph -- dimension is a DATA choice, not an architecture.
    """
    feats = [f[:dims] for f in _site_features(sites, root)]
    adj: dict = {i: set() for i in range(len(sites))}
    for i in range(len(sites)):
        for j in range(i + 1, len(sites)):
            if all(abs(a - b) <= 1 for a, b in zip(feats[i], feats[j])):
                adj[i].add(j)
                adj[j].add(i)
    seed = seed_index if seed_index is not None else len(sites) // 2
    for live in ca_graph_parity(adj, {seed}, gens):
        yield sorted(live)


def _masks_tree(sites, root, gens, seed_index):
    """The syntax tree AS the lattice (dimension-free): parity propagates along parent<->child edges
    over ALL nodes; a site co-mutates when its node is live -> a connected-subtree HOM.
    """
    order, adj, ids = _tree_graph(root)
    site_node = [_node_id_at(root, ids, c[0], c[1]) for c in sites]
    node2site = {nid: i for i, nid in enumerate(site_node) if nid is not None}
    seed = site_node[seed_index if seed_index is not None else len(sites) // 2]
    seeds = {seed} if seed is not None else set()
    for live in ca_graph_parity(adj, seeds, gens):
        yield [node2site[nid] for nid in live if nid in node2site]


def _control_gate(test_cmd, cwd, timeout, search):
    """Run the pristine control. Normal (mutation-testing) mode: the pristine MUST pass or abort
    (a failing baseline makes every 'kill' meaningless). SEARCH (proof-repair) mode INVERTS the
    premise: the pristine is EXPECTED to fail, and a surviving mutant (test PASSes) is a REPAIR;
    an already-passing pristine means there is nothing to search. Returns (proceed, early_rc).
    """
    rc, out, secs = run_oracle(test_cmd, cwd, timeout)
    if search:
        if rc == 0:
            print(
                json.dumps(
                    {
                        "event": "control-pristine",
                        "verdict": "pass",
                        "note": "SEARCH: pristine already passes -- nothing to repair",
                    }
                )
            )
            return False, 0
        print(
            json.dumps(
                {
                    "event": "control-pristine",
                    "verdict": "fail",
                    "secs": secs,
                    "note": "SEARCH: failing pristine is the premise; a survivor is a REPAIR",
                }
            )
        )
        return True, None
    if rc != 0:
        print(
            json.dumps(
                {
                    "event": "HARNESS-ERROR",
                    "control": "pristine",
                    "tail": out.strip().splitlines()[-1][:160] if out.strip() else "",
                }
            )
        )
        return False, 2
    print(json.dumps({"event": "control-pristine", "verdict": "pass", "secs": secs}))
    return True, None


def ca_sweep(
    path,
    test_cmd,
    lang,
    lattice,
    dims,
    rule,
    gens,
    seed_index,
    timeout,
    cwd,
    search=False,
):
    src = open(path, "rb").read()
    tree = get_parser(lang).parse(src)
    stillborn_marks = tuple(_TT.LANG.get(lang, {}).get("stillborn_markers", ()))
    proceed, early = _control_gate(test_cmd, cwd, timeout, search)
    if not proceed:
        return early

    sites = _one_per_site(candidates(src, tree, lang, ["code"], 1, 10**9))
    if not sites:
        print(json.dumps({"event": "ca-no-sites"}))
        return 0
    if lattice == "tape":
        masks, mode = (
            list(_masks_1d(sites, rule, gens, seed_index)),
            "tape-rule%d" % rule,
        )
    elif lattice == "tree":
        masks, mode = (
            list(_masks_tree(sites, tree.root_node, gens, seed_index)),
            "tree-parity",
        )
    else:  # ndim
        masks = list(_masks_ndim(sites, tree.root_node, dims, gens, seed_index))
        mode = "ndim%d-parity" % dims
    print(
        json.dumps(
            {
                "event": "ca-start",
                "lattice": mode,
                "generations": gens,
                "sites": len(sites),
            }
        )
    )

    results = []
    backup = path + ".perturb-orig"
    shutil.copy(path, backup)
    try:
        for g, idxs in enumerate(masks):
            chosen = [sites[i] for i in idxs]
            if not chosen:
                continue
            _write_mutant(
                path, _apply_multi(src, [(c[0], c[1], c[2]) for c in chosen])
            )
            rc, out, secs = run_oracle(test_cmd, cwd, timeout)

            verdict = classify_verdict(rc, out, stillborn_marks)
            labels = [c[4] for c in chosen]
            results.append((g, len(chosen), verdict, labels))
            if verdict == "survived" and search:
                # RE-VERIFY (survivor = candidate; the oracle can be transiently STALE). A TRUE
                # repair survives a second check -- `path` still holds this mutant.
                rc2, _o2, _s2 = run_oracle(test_cmd, cwd, timeout)
                if rc2 != 0:
                    results[-1] = (g, len(chosen), "killed", labels)
                    print(json.dumps({"event": "REPAIR-REJECTED", "gen": g}))
                else:
                    rp = "%s.repair.g%d" % (path, g)
                    open(rp, "wb").write(
                        _apply_multi(src, [(c[0], c[1], c[2]) for c in chosen])
                    )
                    print(json.dumps({"event": "REPAIR", "gen": g, "saved": rp}))
            print(
                json.dumps(
                    {
                        "event": "ca-mutant",
                        "gen": g,
                        "order": len(chosen),
                        "verdict": verdict,
                        "secs": secs,
                        "sites": labels[:8],
                    }
                )
            )
    finally:
        shutil.move(backup, path)

    surviving = [(g, o, ls) for g, o, v, ls in results if v == "survived"]
    print(
        json.dumps(
            {
                "event": "ca-done",
                "lattice": mode,
                "sites": len(sites),
                "mutants": len(results),
                "killed": sum(1 for r in results if r[2] == "killed"),
                "survived": len(surviving),
                "stillborn": sum(1 for r in results if r[2] == "stillborn"),
                "surviving_hom": [
                    {"gen": g, "order": o, "sites": ls[:6]} for g, o, ls in surviving
                ],
            }
        )
    )
    return 0


def _mutant_record(path, lang, test_cmd, src, start, end, repl, fam, label, verdict, secs):
    """One mutant as a stable, reproducible record. The id is content-derived (file+span+
    replacement), so the SAME mutant gets the SAME id across runs and machines."""
    mid = hashlib.sha1(("%s:%d:%d:%s" % (path, start, end, repl)).encode()).hexdigest()[:12]
    line_no = src[:start].count(b"\n") + 1
    ls = src.rfind(b"\n", 0, start) + 1
    le = src.find(b"\n", end)
    le = len(src) if le == -1 else le
    oline = src[ls:le].decode("utf-8", "replace")
    mline = (src[ls:start] + repl.encode() + src[end:le]).decode("utf-8", "replace")
    repro = "perturb %s --lang %s --lines %d:%d --families %s --test %s" % (
        path, lang, line_no, line_no, fam.split(":")[0], shlex.quote(test_cmd))
    return {
        "id": mid,
        "family": fam,
        "file": path,
        "span": {"start": start, "end": end},
        "line": line_no,
        "original": src[start:end].decode("utf-8", "replace"),
        "replacement": repl,
        "label": label,
        "status": verdict,
        "oracle_seconds": secs,
        "diff": "@@ L%d @@\n- %s\n+ %s" % (line_no, oline, mline),
        "reproduction": repro,
    }


def _write_report(path_out, target, lang, test_cmd, fam_stats, killed, scored, records):
    """Stable content-derived ids + sorted keys: the mutation SET (id/span/status) is
    reproducible across runs and machines. `oracle_seconds` is wall-clock -- the one field that
    legitimately varies -- so strip it before diffing two reports. Survivors are the findings."""
    doc = {
        "schema": "perturb-mutation-report/1",
        "target": target,
        "language": lang,
        "oracle": test_cmd,
        "totals": {
            "scored": scored,
            "killed": killed,
            "survived": scored - killed,
            "stillborn": sum(s["stillborn"] for s in fam_stats.values()),
            "rate": round(100 * killed / scored) if scored else None,
        },
        "by_family": fam_stats,
        "mutants": records,
    }
    with open(path_out, "w") as f:
        json.dump(doc, f, indent=2, sort_keys=True)
    print(json.dumps({"event": "report", "path": path_out, "mutants": len(records)}))


def _linecol(src, off):
    """1-based line and column (both start at 1, per the Stryker schema). Column is measured in
    DECODED characters so it aligns with the `source` string the viewer renders."""
    line = src.count(b"\n", 0, off) + 1
    nl = src.rfind(b"\n", 0, off)
    col = len(src[nl + 1:off].decode("utf-8", "replace")) + 1
    return {"line": line, "column": col}


_STRYKER_STATUS = {"killed": "Killed", "survived": "Survived", "stillborn": "CompileError"}


def _write_stryker(path_out, target, lang, src, records):
    """Export to the Stryker mutation-testing-elements schema (schemaVersion 1) so perturb's
    results render in the Stryker HTML report and hosted dashboard -- interop, not a 2nd ecosystem."""
    mutants = [
        {
            "id": r["id"],
            "mutatorName": r["family"],
            "replacement": r["replacement"],
            "location": {
                "start": _linecol(src, r["span"]["start"]),
                "end": _linecol(src, r["span"]["end"]),
            },
            "status": _STRYKER_STATUS.get(r["status"], "Survived"),
        }
        for r in records
    ]
    doc = {
        "schemaVersion": "1",
        "thresholds": {"high": 80, "low": 60},
        "files": {
            target: {
                "language": lang,
                "source": src.decode("utf-8", "replace"),
                "mutants": mutants,
            }
        },
    }
    with open(path_out, "w") as f:
        json.dump(doc, f, indent=2, sort_keys=True)
    print(json.dumps({"event": "stryker-report", "path": path_out, "mutants": len(mutants)}))


def sweep(path, test_cmd, lang, families, lo, hi, n, timeout, cwd, search=False, report=None, stryker=None):
    src = open(path, "rb").read()
    tree = get_parser(lang).parse(src)
    stillborn_marks = tuple(_TT.LANG.get(lang, {}).get("stillborn_markers", ()))

    proceed, early = _control_gate(test_cmd, cwd, timeout, search)
    if not proceed:
        return early

    cands = candidates(src, tree, lang, families, lo, hi)
    if len(cands) > n:
        stride = len(cands) / n
        cands = [cands[int(i * stride)] for i in range(n)]
    print(
        json.dumps(
            {
                "event": "candidates",
                "total": len(cands),
                "by_family": {
                    f: sum(1 for c in cands if c[3] == f)
                    for f in sorted({c[3] for c in cands})
                },
            }
        )
    )

    fam_stats: dict = {}
    survivors = []
    records = []
    backup = path + ".perturb-orig"
    shutil.copy(path, backup)
    try:
        for start, end, repl, fam, label in cands:
            _write_mutant(path, src[:start] + repl.encode() + src[end:])
            rc, out, secs = run_oracle(test_cmd, cwd, timeout)
            st = fam_stats.setdefault(fam, {"killed": 0, "survived": 0, "stillborn": 0})
            verdict = classify_verdict(rc, out, stillborn_marks)
            st[verdict] += 1
            if report is not None or stryker is not None:
                records.append(
                    _mutant_record(path, lang, test_cmd, src, start, end, repl, fam, label, verdict, secs)
                )
            if verdict == "survived":
                if not search:
                    survivors.append(label)
                else:
                    # RE-VERIFY: a survivor is a CANDIDATE, not a confirmed repair. The oracle can be
                    # transiently STALE (e.g. meta-lean's shared box path); a TRUE repair survives a
                    # second independent check. `path` still holds this mutant, so re-run the test.
                    rc2, _o2, _s2 = run_oracle(test_cmd, cwd, timeout)
                    if rc2 != 0:
                        print(json.dumps({"event": "REPAIR-REJECTED", "label": label}))
                    else:
                        survivors.append(label)
                        rp = "%s.repair.%d" % (path, len(survivors))
                        open(rp, "wb").write(src[:start] + repl.encode() + src[end:])
                        print(
                            json.dumps({"event": "REPAIR", "label": label, "saved": rp})
                        )
            print(
                json.dumps(
                    {
                        "event": "mutant",
                        "family": fam,
                        "label": label,
                        "verdict": verdict,
                        "secs": secs,
                    }
                )
            )
    finally:
        shutil.move(backup, path)

    for fam, st in fam_stats.items():
        scored = st["killed"] + st["survived"]
        st["rate"] = round(100 * st["killed"] / scored) if scored else None
    total_k = sum(s["killed"] for s in fam_stats.values())
    total_scored = sum(s["killed"] + s["survived"] for s in fam_stats.values())
    print(
        json.dumps(
            {
                "event": "done",
                "by_family": fam_stats,
                "killed": total_k,
                "scored": total_scored,
                "rate": round(100 * total_k / total_scored) if total_scored else None,
                "survivors": survivors,
            }
        )
    )
    if report is not None:
        _write_report(report, path, lang, test_cmd, fam_stats, total_k, total_scored, records)
    if stryker is not None:
        _write_stryker(stryker, path, lang, src, records)
    return 0


def _selftest():
    """Every family produces a VALID, type-correct mutant that still parses -- and the CODE family
    agrees with ts-thrash (one source). Anti-Potemkin: a family that fires must compile its mutant.
    """
    fails, total = [], [0]

    def check(name, cond):
        total[0] += 1
        if not cond:
            fails.append(name)

    py = (
        b"import time, datetime, subprocess\n"
        b"def f(a, b):\n"
        b"    t = time.time()\n"
        b"    now = datetime.datetime.utcnow()\n"
        b"    r = subprocess.run(['x'])\n"
        b"    return a == b and t > 0 and now\n"
    )
    tree = get_parser("python").parse(py)

    for fam, minexp in (("code", 1), ("time", 2), ("absence", 1)):
        cands = candidates(py, tree, "python", [fam], 1, 99)
        check("%s-fires(%d>=%d)" % (fam, len(cands), minexp), len(cands) >= minexp)
        for s, e, repl, f, _lab in cands:
            mutant = py[:s] + repl.encode() + py[e:]
            try:
                compile(mutant, "<m>", "exec")
            except SyntaxError:
                check("%s-mutant-compiles" % fam, False)
                break
        else:
            check("%s-mutant-compiles" % fam, True)

    # the TYPED freeze: datetime.utcnow() must become a datetime literal, NOT the float
    tc = [
        c for c in candidates(py, tree, "python", ["time"], 1, 99) if "datetime" in c[4]
    ]
    check(
        "typed-datetime-freeze",
        bool(tc) and ".datetime(" in tc[0][2] and "import" in tc[0][2],
    )
    tf = [c for c in candidates(py, tree, "python", ["time"], 1, 99) if "float" in c[4]]
    check("typed-float-freeze", bool(tf) and tf[0][2] == FROZEN_FLOAT)

    # code family AGREES with ts-thrash's own candidates (one source, no drift)
    mine = {(c[0], c[1]) for c in candidates(py, tree, "python", ["code"], 1, 99)}
    tt = {(c[0], c[1]) for c in _TT.candidates(tree, py, _TT.LANG["python"], 1, 99)}
    check("code-family-equals-ts-thrash", mine == tt)

    sp = b"def g():\n    a = 1\n    b = 2\n    return a\n"
    stree = get_parser("python").parse(sp)
    rc = candidates(sp, stree, "python", ["reorder"], 1, 99)
    check("reorder-fires", len(rc) >= 1)
    check("reorder-parses", all(_parses_clean(sp[:s2] + r.encode() + sp[e2:], "python") for s2, e2, r, f2, _l in rc))
    sc = candidates(sp, stree, "python", ["shrink"], 1, 99)
    check("shrink-fires", len(sc) >= 2)
    check("shrink-parses", all(_parses_clean(sp[:s2] + r.encode() + sp[e2:], "python") for s2, e2, r, f2, _l in sc))
    kw = b"def h():\n    return foo(x=1, y=2)\n"
    krc = [c for c in candidates(kw, get_parser("python").parse(kw), "python", ["reorder"], 1, 99) if "keyword_argument<->keyword_argument" in c[4]]
    check("reorder-skips-commutative-kwargs", len(krc) == 0)
    cm = b"def j():\n    a = 1\n    # note\n    b = 2\n"
    cmc = [c for c in candidates(cm, get_parser("python").parse(cm), "python", ["reorder"], 1, 99) if "comment" in c[4]]
    check("reorder-skips-comments", len(cmc) == 0)

    # GRAMMAR-AGNOSTIC code family: an UNTABLED language (Rust) still mutates, and every mutant
    # re-parses clean (the portable 'builds' gate). This is what lets perturb run on mewt.
    rs = (
        b"fn cmp<T: Ord>(a: i32, b: i32) -> bool {\n"
        b"    let v: Vec<i32> = Vec::new();\n"  # the generic '<' here must NOT be mutated
        b"    a == b && a < b && a + b > 0\n"
        b"}\n"
    )
    rtree = get_parser("rust").parse(rs)
    rc = candidates(rs, rtree, "rust", ["code"], 1, 99)
    check("rust-code-fires(%d>=4)" % len(rc), len(rc) >= 4)
    rlabels = " ".join(c[4] for c in rc)
    check(
        "rust-swaps-==,&&,<,+", all(g in rlabels for g in ("==->!=", "&&->||", "+->-"))
    )
    for s, e, repl, _f, _lab in rc:
        if not _parses_clean(rs[:s] + repl.encode() + rs[e:], "rust"):
            check("rust-mutant-parses-clean", False)
            break
    else:
        check("rust-mutant-parses-clean", True)
    # near-miss: the generic Vec<i32> '<' and '>' are NOT in binary position -> never mutated
    genlt = rs.index(b"Vec<i32>") + 3
    check("rust-generic-lt-untouched", not any(c[0] == genlt for c in rc))

    # grammar-agnostic reaches JS/TS STRICT equality (=== !==), not just C-family == (adversarial fix)
    js = b"function f(a, b) { return a === b && a !== b; }\n"
    jtree = get_parser("javascript").parse(js)
    jc = candidates(js, jtree, "javascript", ["code"], 1, 99)
    jlabels = " ".join(c[4] for c in jc)
    check("js-strict-eq-mutated", "===->!==" in jlabels and "!==->===" in jlabels)
    for s, e, repl, _f, _lab in jc:
        if not _parses_clean(js[:s] + repl.encode() + js[e:], "javascript"):
            check("js-mutant-parses-clean", False)
            break
    else:
        check("js-mutant-parses-clean", True)

    # CA mode: Rule 30 from a central seed reproduces the KNOWN elementary-CA pattern (not a
    # hand-typed fixture -- computed and checked against Wolfram's published rows).
    rows = list(elementary_ca(30, [0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0], 3))
    check("ca-rule30-gen1", [i for i, b in enumerate(rows[1]) if b] == [4, 5, 6])
    check("ca-rule30-gen2", [i for i, b in enumerate(rows[2]) if b] == [3, 4, 7])
    # a higher-order (2-site) mutant applies BOTH edits and still compiles (the HOM builds gate)
    sites = _one_per_site(candidates(py, tree, "python", ["code"], 1, 99))
    check("ca-has-multiple-sites", len(sites) >= 2)
    if len(sites) >= 2:
        hom = _apply_multi(py, [(c[0], c[1], c[2]) for c in sites[:2]])
        try:
            compile(hom, "<hom>", "exec")
            ok = True
        except SyntaxError:
            ok = False
        check(
            "ca-hom-2site-compiles-and-differs",
            ok
            and hom != py
            and sum(a != b for a, b in zip(hom, py)) + abs(len(hom) - len(py)) >= 2,
        )

    # CA graph parity (the one engine for tree + ndim): on a path 0-1-2-3-4 seeded at 2, gen1 is the
    # odd-neighbour set {1,3} -- checked against the rule, not a hand-typed fixture.
    padj = {0: {1}, 1: {0, 2}, 2: {1, 3}, 3: {2, 4}, 4: {3}}
    pg = list(ca_graph_parity(padj, {2}, 2))
    check("ca-graph-seed", pg[0] == {2})
    check("ca-graph-gen1-odd-neighbours", pg[1] == {1, 3})
    # n-D structural lattice on a clustered sample: sibling comparisons share depth/block/op-class,
    # so the feature lattice genuinely CONNECTS them and a higher-order (>=2) mutant fires.
    cy = b"def g(a, b, c, d):\n    return a == b and c == d and a < c and b > d\n"
    ctree = get_parser("python").parse(cy)
    csites = _one_per_site(candidates(cy, ctree, "python", ["code"], 1, 99))
    feats = _site_features(csites, ctree.root_node)
    adjn = sum(
        1
        for i in range(len(feats))
        for j in range(i + 1, len(feats))
        if all(abs(a - b) <= 1 for a, b in zip(feats[i][:4], feats[j][:4]))
    )
    check("ndim-lattice-connects-sites", adjn >= 1)
    check(
        "ndim-fires-hom-order>=2",
        any(len(m) >= 2 for m in _masks_ndim(csites, ctree.root_node, 4, 8, None)),
    )
    # tree lattice (dimension-free) also produces mutants on the same input
    check(
        "tree-lattice-fires",
        any(len(m) >= 1 for m in _masks_tree(csites, ctree.root_node, 8, None)),
    )
    # the structural embedding is real: a nested operator sits deeper than the function root
    check(
        "site-depth-nonzero",
        max(_depth_at(ctree.root_node, c[0], c[1]) for c in csites) >= 2,
    )

    # Lean proof-token family fires on a DOTTED identifier and swaps only the tail. Regression:
    # the grammar tokenizes `h.mpr` as ONE identifier, so a whole-token match never fired.
    lp = b"theorem t : q := h.mpr hp\n"
    lc = candidates(lp, get_parser("lean").parse(lp), "lean", ["code"], 1, 99)
    lhit = [c for c in lc if "lean:mpr->mp" in c[4]]
    check("lean-proof-fires-on-dotted-id", len(lhit) == 1)
    if lhit:
        m = lp[: lhit[0][0]] + lhit[0][2].encode() + lp[lhit[0][1] :]
        check("lean-proof-swaps-tail-only", b"h.mp hp" in m and b"h.mpr" not in m)

    # classify_verdict: the pure oracle-verdict decision shared by sweep + ca_sweep
    check("verdict-survived", classify_verdict(0, "ok", ("error[",)) == "survived")
    check(
        "verdict-stillborn",
        classify_verdict(1, "error[E0308]: mismatched types", ("error[",))
        == "stillborn",
    )
    check(
        "verdict-killed",
        classify_verdict(1, "assertion failed: left == right", ("error[",)) == "killed",
    )
    # near-miss: with NO stillborn markers (e.g. an untabled lang) a build failure counts as killed
    check(
        "verdict-killed-when-no-marks",
        classify_verdict(1, "error[E0308]", ()) == "killed",
    )

    # near-miss: an empty family set yields nothing
    check("no-family-no-candidates", candidates(py, tree, "python", [], 1, 99) == [])

    # --search INVERTS the pristine gate: normal mode aborts on a FAILING pristine (a failing
    # baseline makes every kill meaningless); search (proof-repair) mode PROCEEDS on a failing
    # pristine (that is the premise) and stops on a passing one. `true`/`false` = rc 0/1.
    import contextlib as _cl
    import io as _io
    import shutil as _sh
    import tempfile as _tf

    _gd = _tf.mkdtemp(prefix="perturb-gate-")
    with _cl.redirect_stdout(_io.StringIO()):
        _g1 = _control_gate("true", _gd, 5, False)
        _g2 = _control_gate("false", _gd, 5, False)
        _g3 = _control_gate("false", _gd, 5, True)
        _g4 = _control_gate("true", _gd, 5, True)
    _sh.rmtree(_gd, ignore_errors=True)
    check("gate-normal-pass-proceeds", _g1 == (True, None))
    check("gate-normal-fail-aborts", _g2 == (False, 2))
    check("gate-search-fail-proceeds", _g3 == (True, None))
    check("gate-search-pass-stops", _g4 == (False, 0))

    # lean-proof family: NAMED direction tokens (.mp/.mpr etc.) the LLM gets backwards -- named
    # identifier leaves, invisible to fam_code_universal's unnamed-glyph swaps.
    _lps = b"theorem t : a := (h).mp y\n"
    _lpc = [
        c
        for c in candidates(
            _lps, get_parser("lean").parse(_lps), "lean", ["code"], 1, 99
        )
        if "mp->mpr" in c[4]
    ]
    check("lean-proof-mp-fires", len(_lpc) == 1)

    n = total[0]
    if fails:
        print(
            "RESULT: FAIL -- %d/%d cases; perturb; failed: %s"
            % (n - len(fails), n, ", ".join(fails))
        )
        return 1
    print(
        "RESULT: PASS -- %d/%d cases; perturb families fire + compile (code agrees with "
        "ts-thrash, typed time-freeze float-vs-datetime, absence, near-miss)" % (n, n)
    )
    return 0


def main():
    if "--selftest" in sys.argv:
        return _selftest()
    p = argparse.ArgumentParser(prog="perturb")
    p.add_argument("file")
    p.add_argument("--test", required=True)
    p.add_argument("--families", default="code,time,absence")
    p.add_argument("--lang", default=None)
    p.add_argument("--lines", default=None)
    p.add_argument("--n", type=int, default=20)
    p.add_argument("--timeout", type=int, default=180)
    p.add_argument("--cwd", default=None)
    p.add_argument("--report", default=None, help="write a JSON mutation report to this path")
    p.add_argument("--stryker", default=None, help="write a Stryker-schema report to this path")
    p.add_argument(
        "--ca",
        action="store_true",
        help="CELLULAR-AUTOMATON mode: higher-order mutants from a CA over the operator sites",
    )
    p.add_argument(
        "--ca-lattice",
        default="tree",
        choices=("tape", "tree", "ndim"),
        help="tape=1-D elementary rule; tree=syntax graph (dimension-free); ndim=n structural features",
    )
    p.add_argument(
        "--ca-dims",
        type=int,
        default=4,
        help="feature axes for --ca-lattice ndim (1..5)",
    )
    p.add_argument(
        "--ca-rule",
        type=int,
        default=30,
        help="elementary rule for --ca-lattice tape (default 30)",
    )
    p.add_argument("--generations", type=int, default=10)
    p.add_argument("--seed-index", type=int, default=None)
    p.add_argument(
        "--search",
        action="store_true",
        help="PROOF-SEARCH mode: the pristine is EXPECTED to FAIL; report survivors "
        "(test-PASSing mutants) as REPAIR hits and save each to <file>.repair.*",
    )
    a = p.parse_args()
    # A pipeline's exit code is its LAST command's, so `test | tail` reports tail's rc=0 even when the
    # test FAILS -- masking every kill as a survival (cost me 45 min + a false "all survived" on mewt).
    if "|" in a.test.replace("||", ""):
        print(
            "perturb WARNING: --test contains a pipe. A pipeline's exit status is its LAST command's,"
            " so a FAILING test can read as rc=0 and every kill is masked as 'survived'. Drop the pipe"
            " (perturb already captures output) or use 'set -o pipefail'.",
            file=sys.stderr,
        )
    src = open(a.file, errors="replace").read()
    lang = a.lang or _TT.detect_lang(a.file, src)
    cwd = a.cwd or os.path.dirname(os.path.abspath(a.file))
    if a.ca:
        return ca_sweep(
            a.file,
            a.test,
            lang,
            a.ca_lattice,
            a.ca_dims,
            a.ca_rule,
            a.generations,
            a.seed_index,
            a.timeout,
            cwd,
            a.search,
        )
    lo, hi = (1, 10**9)
    if a.lines:
        lo, hi = (int(x) for x in a.lines.split(":"))
    fams = [f for f in a.families.split(",") if f]
    return sweep(a.file, a.test, lang, fams, lo, hi, a.n, a.timeout, cwd, a.search, a.report, a.stryker)




if __name__ == "__main__":
    sys.exit(main())
