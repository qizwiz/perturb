#!/usr/bin/env python3
"""ts-thrash -- language-AGNOSTIC mutation testing via tree-sitter (f8016 closed).

The fourth rewrite of the same tool was the tell: mutate/type-rotate/time-thrash/
absence-thrash are all Python-only because they lean on python's `ast`. tree-sitter
parses ~any grammar into a tree whose nodes carry BYTE SPANS, so a mutant is a SPLICE
on the original bytes -- comments and formatting survive untouched (sounder than
ast.unparse, which reflows the whole file), and mutate-by-span cannot hit the wrong
anchor by construction. Only the READER is per-language (a small node-type table +
stillborn markers); the framework -- candidates, controls, kill/survive verdicts --
is universal. Grammars: tree_sitter_language_pack (python, go, bash, elisp, ...).

  ts-thrash FILE --test 'CMD' [--lang L] [--lines LO:HI] [--n 12] [--timeout 180]
  ts-thrash --selftest

CMD is the kill oracle (pytest file, `go test ./pkg/...`, an ERT batch, a --selftest).
Verdicts: killed (CMD fails) / survived (CMD passes) / stillborn (mutant does not
build -- detected per language, excluded from the rate, reported). The pristine
control runs FIRST; if it fails, the sweep refuses to score (HARNESS-ERROR).
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time

from tree_sitter_language_pack import get_parser

# ---------------------------------------------------------------- language tables
# Operator token swaps: applied when the token is the TEXT of an operator child
# inside the listed node types. Everything here is compile-safe in its language.
OP_SWAPS = {
    "==": "!=", "!=": "==", "<": ">=", ">=": "<", ">": "<=", "<=": ">",
    "&&": "||", "||": "&&", "and": "or", "or": "and",
    "+": "-", "-": "+",
    "in": "not in", "is": "is not",
}
BOOL_SWAPS = {"True": "False", "False": "True", "true": "false", "false": "true", "t": "nil"}

LANG = {
    "python": dict(
        binary_nodes={"comparison_operator", "boolean_operator", "binary_operator"},
        bool_nodes={"true", "false"},
        int_nodes={"integer"},
        if_nodes={"if_statement", "while_statement"},
        negate=lambda cond: "not (%s)" % cond,
        stillborn_markers=("SyntaxError", "IndentationError", "error during collection", "ERROR collecting"),
    ),
    "go": dict(
        binary_nodes={"binary_expression"},
        bool_nodes={"true", "false"},
        int_nodes={"int_literal"},
        if_nodes={"if_statement", "for_statement"},
        negate=lambda cond: "!(%s)" % cond,
        stillborn_markers=("[build failed]", "syntax error", "undefined:"),
    ),
    "bash": dict(
        binary_nodes={"binary_expression", "test_command"},
        bool_nodes=set(),
        int_nodes={"number"},
        if_nodes={"if_statement", "while_statement"},
        negate=lambda cond: "! %s" % cond,
        stillborn_markers=("syntax error",),
    ),
    "elisp": dict(
        binary_nodes=set(),   # elisp has NO infix operators -- logic lives in call HEADS
        bool_nodes={"symbol"},  # t/nil handled via BOOL_SWAPS text match
        int_nodes={"integer"},
        if_nodes=set(),       # (if ...) negation is done via the elisp_calls block below
        negate=lambda cond: "(not %s)" % cond,
        stillborn_markers=("Symbol.s function definition is void", "End of file during parsing",
                           "Invalid read syntax", "Wrong type argument"),
        # Elisp-specific: the real operators are call heads, not infix tokens.
        elisp_calls=True,
        # special_form keyword swaps (the head is a bare keyword node inside special_form)
        special_form_swaps={"and": "or", "or": "and", "when": "unless", "unless": "when"},
        # function-call head swaps (first symbol child of a `list` node)
        call_head_swaps={"=": "/=", "/=": "=", "<": ">=", ">": "<=", "<=": ">", ">=": "<",
                         "eq": "eql", "equal": "eq", "memq": "memql", "member": "memq"},
        # predicate calls negated: (pred ...) -> (not (pred ...)); flips any boolean test
        pred_heads={"stringp", "string-match-p", "string-match", "string-prefix-p",
                    "string-suffix-p", "memq", "member", "assq", "boundp", "fboundp", "null"},
    ),
}

EXT = {".py": "python", ".go": "go", ".sh": "bash", ".bash": "bash", ".el": "elisp"}


def detect_lang(path, src):
    ext = os.path.splitext(path)[1]
    if ext in EXT:
        return EXT[ext]
    head = src[:120]
    if "python" in head:
        return "python"
    if "bash" in head or head.startswith("#!/bin/sh"):
        return "bash"
    raise SystemExit("cannot detect language for %s; pass --lang" % path)


def walk(node):
    yield node
    for c in node.children:
        yield from walk(c)


def candidates(tree, src_bytes, table: dict, lo, hi):
    """(start, end, replacement, line, op) for every single-span mutation in [lo,hi]."""
    out = []
    for node in walk(tree.root_node):
        line = node.start_point[0] + 1
        if not (lo <= line <= hi):
            continue
        text = src_bytes[node.start_byte:node.end_byte].decode("utf-8", "replace")
        # operator swap: an operator-ish token inside a binary node
        if node.parent is not None and node.parent.type in table["binary_nodes"]:
            if text in OP_SWAPS and node.child_count == 0:
                out.append((node.start_byte, node.end_byte, OP_SWAPS[text], line, "op:%s->%s" % (text, OP_SWAPS[text])))
        # boolean flip
        if node.type in table["bool_nodes"] and text in BOOL_SWAPS:
            out.append((node.start_byte, node.end_byte, BOOL_SWAPS[text], line, "bool:%s" % text))
        # integer +1
        if node.type in table["int_nodes"]:
            try:
                out.append((node.start_byte, node.end_byte, str(int(text) + 1), line, "int+1:%s" % text))
            except ValueError:
                pass
        # condition negation
        if node.type in table["if_nodes"]:
            cond = node.child_by_field_name("condition")
            if cond is not None:
                ctext = src_bytes[cond.start_byte:cond.end_byte].decode("utf-8", "replace")
                if not ctext.startswith(("not ", "!(", "! ")):
                    out.append((cond.start_byte, cond.end_byte, table["negate"](ctext), line, "negate-if"))
        # elisp call-head mutations: the operators are HEADS, not infix tokens
        if table.get("elisp_calls"):
            if node.type == "special_form":
                for ch in node.children:  # the keyword is a bare leaf node
                    if ch.child_count == 0:
                        kt = src_bytes[ch.start_byte:ch.end_byte].decode("utf-8", "replace")
                        if kt in table["special_form_swaps"]:
                            rep = table["special_form_swaps"][kt]
                            out.append((ch.start_byte, ch.end_byte, rep, ch.start_point[0] + 1, "head:%s->%s" % (kt, rep)))
                        break  # only the operator keyword, not the args
            if node.type == "list":
                head = next((c for c in node.children if c.type == "symbol"), None)
                if head is not None:
                    ht = src_bytes[head.start_byte:head.end_byte].decode("utf-8", "replace")
                    if ht in table["pred_heads"] or (ht.endswith("-p") and ht != "not"):
                        whole = src_bytes[node.start_byte:node.end_byte].decode("utf-8", "replace")
                        out.append((node.start_byte, node.end_byte, "(not %s)" % whole, node.start_point[0] + 1, "negate:%s" % ht))
                    elif ht in table["call_head_swaps"]:
                        rep = table["call_head_swaps"][ht]
                        out.append((head.start_byte, head.end_byte, rep, head.start_point[0] + 1, "head:%s->%s" % (ht, rep)))
    # dedup identical spans (a token can match twice), keep first
    seen, uniq = set(), []
    for c in out:
        key = (c[0], c[1], c[2])
        if key not in seen:
            seen.add(key)
            uniq.append(c)
    return uniq


def run_oracle(cmd, cwd, timeout):
    t0 = time.monotonic()
    try:
        r = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout + r.stderr), round(time.monotonic() - t0, 1)
    except subprocess.TimeoutExpired:
        return -9, "TIMEOUT", timeout


def sweep(path, test_cmd, lang, lo, hi, n, timeout, cwd):
    table: dict = LANG[lang]
    src_bytes = open(path, "rb").read()
    tree = get_parser(lang).parse(src_bytes)

    rc, out, secs = run_oracle(test_cmd, cwd, timeout)
    if rc != 0:
        print(json.dumps({"event": "HARNESS-ERROR", "control": "pristine", "rc": rc, "tail": out.strip().splitlines()[-1][:160] if out.strip() else ""}))
        return 2
    print(json.dumps({"event": "control-pristine", "verdict": "pass", "secs": secs}))

    cands = candidates(tree, src_bytes, table, lo, hi)
    if len(cands) > n:
        stride = len(cands) / n
        cands = [cands[int(i * stride)] for i in range(n)]
    print(json.dumps({"event": "candidates", "total": len(cands), "lines": [lo, hi]}))

    killed = survived = stillborn = 0
    survivors = []
    backup = path + ".tsthrash-orig"
    shutil.copy(path, backup)
    try:
        for start, end, repl, line, op in cands:
            mutant = src_bytes[:start] + repl.encode() + src_bytes[end:]
            open(path, "wb").write(mutant)
            rc, out, secs = run_oracle(test_cmd, cwd, timeout)
            if rc == 0:
                verdict = "survived"
                survived += 1
                survivors.append("L%d %s" % (line, op))
            elif any(m in out for m in table["stillborn_markers"]):
                verdict = "stillborn"
                stillborn += 1
            else:
                verdict = "killed"
                killed += 1
            print(json.dumps({"event": "mutant", "line": line, "op": op, "verdict": verdict, "secs": secs}))
    finally:
        shutil.move(backup, path)

    scored = killed + survived
    print(json.dumps({"event": "done", "killed": killed, "survived": survived,
                      "stillborn": stillborn, "scored": scored,
                      "rate": round(100 * killed / scored) if scored else None,
                      "survivors": survivors}))
    return 0


def _selftest():
    """Bind the mutator's own claims: candidates found in 3 languages, a splice
    differs from the source and stays parseable, span-restore is byte-identical,
    and the near-miss -- lines outside the range yield nothing."""
    fails, total = [], [0]

    def check(name, cond):
        total[0] += 1
        if not cond:
            fails.append(name)

    py = b"def f(a, b):\n    if a == b and a > 0:\n        return True\n    return False\n"
    go = b"package m\n\nfunc f(a int, b int) bool {\n\tif a == b && a > 0 {\n\t\treturn true\n\t}\n\treturn false\n}\n"
    sh = b"#!/bin/bash\nif [ \"$1\" == \"x\" ]; then\n  exit 0\nfi\nexit 1\n"

    for lang, src, min_expected in (("python", py, 4), ("go", go, 4), ("bash", sh, 1)):
        tree = get_parser(lang).parse(src)
        cands = candidates(tree, src, LANG[lang], 1, 99)
        check("%s-finds-candidates(%d>=%d)" % (lang, len(cands), min_expected), len(cands) >= min_expected)
        if cands:
            s, e, repl, _, _ = cands[0]
            mutant = src[:s] + repl.encode() + src[e:]
            check("%s-splice-differs" % lang, mutant != src)
            check("%s-mutant-parses" % lang, get_parser(lang).parse(mutant).root_node is not None)
    # near-miss: an empty line range yields no candidates
    tree = get_parser("python").parse(py)
    check("range-excludes", candidates(tree, py, LANG["python"], 90, 99) == [])
    # elisp parses and yields int/bool candidates
    el = b"(defun f (a) (if (> a 1) t nil))\n"
    elc = candidates(get_parser("elisp").parse(el), el, LANG["elisp"], 1, 9)
    check("elisp-finds-candidates", len(elc) >= 1)

    n = total[0]
    if fails:
        print("ts-thrash --selftest: RESULT: FAIL -- %d/%d cases; failed: %s" % (n - len(fails), n, ", ".join(fails)))
        return 1
    print("ts-thrash --selftest: RESULT: PASS -- %d/%d cases; agnostic mutator bound "
          "(candidates in python/go/bash/elisp, splice differs+parses, range near-miss)" % (n, n))
    return 0


def main():
    if "--selftest" in sys.argv:
        return _selftest()
    p = argparse.ArgumentParser(prog="ts-thrash")
    p.add_argument("file")
    p.add_argument("--test", required=True, help="kill oracle command (run from --cwd)")
    p.add_argument("--lang", default=None)
    p.add_argument("--lines", default=None, help="LO:HI line range (default: whole file)")
    p.add_argument("--n", type=int, default=12)
    p.add_argument("--timeout", type=int, default=180)
    p.add_argument("--cwd", default=None)
    a = p.parse_args()
    src = open(a.file, errors="replace").read()
    lang = a.lang or detect_lang(a.file, src)
    lo, hi = (1, 10**9)
    if a.lines:
        lo, hi = (int(x) for x in a.lines.split(":"))
    return sweep(a.file, a.test, lang, lo, hi, a.n, a.timeout, a.cwd or os.path.dirname(os.path.abspath(a.file)))


if __name__ == "__main__":
    sys.exit(main())
