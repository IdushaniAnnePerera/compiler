"""
Phase 5: Code Optimization
Machine-independent optimizations from Lecture 9 (COSC 44283).

Existing passes (kept):
    - Constant Folding & Constant Propagation
    - Algebraic Simplification  (x*1, x+0, x*0)
    - Dead-Copy Elimination

New Lecture-9 passes:
    1. Basic Block Identification   — Lec 9 (leader algorithm)
    2. Dead-Code Elimination        — Lec 9 slide 19
    3. Strength Reduction           — Lec 9 slide 18
    4. Loop-Invariant Code Motion   — Lec 9 slide 17
    5. Induction Variable Detection — Lec 9 slide 17
    6. Partial Redundancy Elimination — Lec 9 slides 20, 23-26

Public API
----------
    optimize(code)            -> (optimized_code, report_lines)
    identify_basic_blocks(code) -> list[list[Quad]]
"""

import math
from ir_gen import Quad

ARITH        = {"+", "-", "*", "/"}
BINARY_OPS   = {"+", "-", "*", "/", "<", ">", "<=", ">=", "==", "!=", "&&", "||"}
SIDE_EFFECTS = {"goto", "ifFalse", "label", "print", "alloc_arr", "store_arr"}

# Ops where the 'result' field is a value *consumed* (not produced).
# These must be counted as uses in liveness analysis.
_RESULT_IS_CONSUMED = {"store_arr"}


# ── helpers ──────────────────────────────────────────────────────────────────

def _count_uses(code):
    """Count how many times each name is used as an operand across all quads.
    For store_arr, also counts the result field because it holds the value
    being consumed (not a value being defined)."""
    uses = {}
    for q in code:
        for a in (q.arg1, q.arg2):
            if isinstance(a, str):
                uses[a] = uses.get(a, 0) + 1
        if q.op in _RESULT_IS_CONSUMED and isinstance(q.result, str):
            uses[q.result] = uses.get(q.result, 0) + 1
    return uses


def _is_const(v):
    if isinstance(v, (int, float)):
        return True
    if isinstance(v, str):
        try:
            float(v)
            return True
        except (ValueError, TypeError):
            return False
    return False


def _num(v):
    if isinstance(v, (int, float)):
        return v
    f = float(v)
    return int(f) if f.is_integer() else f


def _is_power_of_two(n):
    return isinstance(n, int) and n > 0 and (n & (n - 1)) == 0


def _label_index(code, name):
    for i, q in enumerate(code):
        if q.op == "label" and q.result == name:
            return i
    return -1


def _build_label_map(code):
    return {q.result: i for i, q in enumerate(code) if q.op == "label"}


# ── public API ────────────────────────────────────────────────────────────────

def optimize(code):
    """
    Run all optimization passes in order.
    Returns (optimized_code, report_lines).
    """
    report = []

    # --- existing passes ---
    code = _constant_fold_and_propagate(code, report)
    code = _algebraic_simplify(code, report)

    # --- Lec 9 new passes ---
    code = strength_reduction(code, report)           # slide 18
    code = loop_invariant_motion(code, report)        # slide 17
    detect_induction_variables(code, report)          # slide 17  (report only)
    code = partial_redundancy_elimination(code, report)  # slides 20,23-26
    code = dead_code_elimination(code, report)        # slide 19

    # --- final cleanup ---
    code = _eliminate_dead_copies(code, report)

    return code, report


# ── 1. Basic Block Identification ─────────────────────────────────────────────

def identify_basic_blocks(code):
    """
    Lec 9: Standard leader algorithm.

    A statement is a *leader* if it is:
      (a) the first statement in the program,
      (b) the target of any branch (goto / ifFalse), or
      (c) the statement immediately following a branch.

    Returns a list of basic blocks; each block is a list of Quad objects.
    """
    if not code:
        return []

    leaders = {0}
    for i, q in enumerate(code):
        if q.op in ("goto", "ifFalse"):
            if i + 1 < len(code):
                leaders.add(i + 1)
            j = _label_index(code, q.result)
            if j >= 0:
                leaders.add(j)

    sorted_leaders = sorted(leaders)
    blocks = []
    for k, start in enumerate(sorted_leaders):
        end = sorted_leaders[k + 1] if k + 1 < len(sorted_leaders) else len(code)
        blocks.append(list(code[start:end]))
    return blocks


# ── 2. Dead-Code Elimination ──────────────────────────────────────────────────

def dead_code_elimination(code, report):
    """
    Lec 9 slide 19.

    Pass A — unreachable code: any instruction after an unconditional 'goto'
              that is not preceded by a label is unreachable and removed.
    Pass B — dead assignments: iteratively remove instructions whose result
              is never used as an operand anywhere in the program.
    """
    # Pass A: unreachable code after unconditional goto
    out, i = [], 0
    while i < len(code):
        q = code[i]
        out.append(q)
        if q.op == "goto":
            i += 1
            while i < len(code) and code[i].op != "label":
                report.append(
                    f"[Dead Code Elimination] removed unreachable: {code[i]}"
                )
                i += 1
            continue
        i += 1
    code = out

    # Pass B: iterative dead-assignment removal
    changed = True
    while changed:
        changed = False
        uses = _count_uses(code)

        new_code = []
        for q in code:
            if q.op in SIDE_EFFECTS:
                new_code.append(q)
                continue
            if (q.result is not None
                    and isinstance(q.result, str)
                    and uses.get(q.result, 0) == 0):
                report.append(f"[Dead Code Elimination] removed unused: {q}")
                changed = True
                continue
            new_code.append(q)
        code = new_code

    return code


# ── 3. Strength Reduction ─────────────────────────────────────────────────────

def strength_reduction(code, report):
    """
    Lec 9 slide 18.

    Replace  t = x * 2^n  with  t = x << n  (a cheaper left-shift).
    Introduces the 'shl' Quad operator; codegen.py emits SHL for it.
    Handles both  x * k  and  k * x  forms.
    """
    out = []
    for q in code:
        replaced = False
        if q.op == "*":
            # Try (arg2 is the power-of-two constant, arg1 is the variable)
            # then (arg1 is the power-of-two constant, arg2 is the variable)
            for const_arg, var_arg in [(q.arg2, q.arg1), (q.arg1, q.arg2)]:
                if _is_const(const_arg):
                    n = _num(const_arg)
                    if _is_power_of_two(n):
                        shift = int(math.log2(n))
                        new_q = Quad("shl", var_arg, shift, q.result)
                        report.append(
                            f"[Strength Reduction] replaced {q} with {new_q}"
                        )
                        out.append(new_q)
                        replaced = True
                        break
        if not replaced:
            out.append(q)
    return out


# ── 4. Loop-Invariant Code Motion ─────────────────────────────────────────────

def loop_invariant_motion(code, report):
    """
    Lec 9 slide 17.

    For each loop identified by a back-edge (goto L targeting an earlier label L):
      1. Compute the set of variables/temps *modified* in the loop body.
      2. An instruction is loop-invariant if none of its operands is in
         the modified set.
      3. Hoist invariant instructions to just before the loop header label.
      4. Iterate until no more instructions can be hoisted (handles cascades:
         after hoisting  t = b+a,  inv = t  may become invariant too).
    """
    changed_outer = True
    while changed_outer:
        changed_outer = False
        label_pos = _build_label_map(code)

        # Find all back-edges: goto L where label L is at an earlier index.
        back_edges = []
        for idx, q in enumerate(code):
            if q.op == "goto" and q.result in label_pos:
                hdr = label_pos[q.result]
                if hdr <= idx:
                    back_edges.append((q.result, hdr, idx))

        for lbl, hdr, go_idx in back_edges:
            body = list(code[hdr + 1: go_idx])

            # All variables/temps assigned anywhere in the loop body
            modified = {
                bq.result
                for bq in body
                if bq.op not in SIDE_EFFECTS
                and bq.result is not None
                and isinstance(bq.result, str)
            }

            # Iteratively hoist instructions whose operands are all invariant
            hoisted = []
            changed_inner = True
            while changed_inner:
                changed_inner = False
                remaining = []
                for bq in body:
                    if bq.op in SIDE_EFFECTS:
                        remaining.append(bq)
                        continue
                    inv = all(
                        not (isinstance(a, str) and a in modified)
                        for a in (bq.arg1, bq.arg2)
                    )
                    if inv and bq.result is not None:
                        hoisted.append(bq)
                        modified.discard(bq.result)
                        report.append(
                            f"[Loop-Invariant Motion] hoisted {bq} "
                            f"out of loop {lbl}"
                        )
                        changed_inner = True
                    else:
                        remaining.append(bq)
                body = remaining

            if hoisted:
                code = (code[:hdr] + hoisted +
                        [code[hdr]] + body + [code[go_idx]] +
                        code[go_idx + 1:])
                changed_outer = True
                break   # rebuild label map and restart

    return code


# ── 5. Induction Variable Detection ──────────────────────────────────────────

def detect_induction_variables(code, report):
    """
    Lec 9 slide 17.

    An *induction variable* v satisfies the pattern inside some loop body:
        t  = v + c     (or v - c),  c is a constant
        v  = t
    This means v is incremented (or decremented) by c in every iteration.
    Reports detected induction variables; does NOT modify the code.
    """
    label_pos = _build_label_map(code)

    for idx, q in enumerate(code):
        if q.op != "goto" or q.result not in label_pos:
            continue
        hdr = label_pos[q.result]
        if hdr > idx:
            continue   # forward jump — not a loop back-edge
        body = code[hdr + 1: idx]

        reported = set()
        for j, bq in enumerate(body):
            # Pattern:  t = v +/- c   (v is a non-constant identifier)
            if (bq.op in ("+", "-")
                    and isinstance(bq.arg1, str) and not _is_const(bq.arg1)
                    and _is_const(bq.arg2)):
                t_name   = bq.result
                var_name = bq.arg1
                step     = _num(bq.arg2) * (-1 if bq.op == "-" else 1)
                for kq in body[j + 1:]:
                    if kq.op == "=" and kq.arg1 == t_name and kq.result == var_name:
                        key = (var_name, q.result)
                        if key not in reported:
                            reported.add(key)
                            sign = "+" if step >= 0 else ""
                            report.append(
                                f"[Induction Variable] '{var_name}' incremented by "
                                f"{sign}{step:g} each iteration of loop {q.result}"
                            )
                        break
            # Commutative form:  t = c + v
            elif (bq.op == "+"
                    and _is_const(bq.arg1)
                    and isinstance(bq.arg2, str) and not _is_const(bq.arg2)):
                t_name   = bq.result
                var_name = bq.arg2
                step     = _num(bq.arg1)
                for kq in body[j + 1:]:
                    if kq.op == "=" and kq.arg1 == t_name and kq.result == var_name:
                        key = (var_name, q.result)
                        if key not in reported:
                            reported.add(key)
                            report.append(
                                f"[Induction Variable] '{var_name}' incremented by "
                                f"+{step:g} each iteration of loop {q.result}"
                            )
                        break


# ── 6. Partial Redundancy Elimination ────────────────────────────────────────

_pre_count = [0]

def partial_redundancy_elimination(code, report):
    """
    Lec 9 slides 20, 23-26.

    Detects the if/else pattern in the TAC:
        ifFalse cond  Lelse
        <then-block>            <- contains  t1 = y OP z
        goto Lend
    Lelse:
        <else-block>            <- contains  t2 = y OP z  (same expression)
    Lend:

    The expression  y OP z  is *partially redundant*: it is computed on both
    branches but could be computed once before the branch.  Following the
    lecture's code-motion insertion pattern, we:
      1. Insert  pre = y OP z  immediately before the ifFalse.
      2. Replace  t1 = y OP z  and  t2 = y OP z  with  t1 = pre  / t2 = pre.
    This makes the computation fully redundant in both branches; a later DCE
    pass can clean up any now-dead temporaries.
    """
    changed = True
    while changed:
        changed = False
        label_pos = _build_label_map(code)

        for i, q in enumerate(code):
            if q.op != "ifFalse":
                continue

            else_label = q.result
            if else_label not in label_pos:
                continue
            else_start = label_pos[else_label]    # index of  label Lelse

            # The instruction immediately before Lelse must be an unconditional goto
            if else_start < 1 or code[else_start - 1].op != "goto":
                continue
            goto_idx  = else_start - 1
            end_label = code[goto_idx].result
            if end_label not in label_pos:
                continue
            end_start = label_pos[end_label]      # index of  label Lend

            # Sanity: end_start must be after else_start (guards against while-loops)
            if end_start <= else_start:
                continue

            then_block = code[i + 1: goto_idx]
            else_block = code[else_start + 1: end_start]

            def _exprs(block):
                """Map (op, str(arg1), str(arg2)) -> first matching Quad."""
                seen = {}
                for bq in block:
                    if bq.op in BINARY_OPS and bq.result is not None:
                        key = (bq.op, str(bq.arg1), str(bq.arg2))
                        if key not in seen:
                            seen[key] = bq
                return seen

            common = set(_exprs(then_block)) & set(_exprs(else_block))
            if not common:
                continue

            # Process one expression per restart
            key        = next(iter(common))
            op, s1, s2 = key
            src_q      = _exprs(then_block)[key]   # use original-typed args

            _pre_count[0] += 1
            pre_temp = f"tP{_pre_count[0]}"   # starts with 't' so codegen treats it as a register temp
            pre_quad = Quad(op, src_q.arg1, src_q.arg2, pre_temp)

            report.append(
                f"[Partial Redundancy Elimination] pre-computed "
                f"'{src_q}' before branch as '{pre_temp} = {s1} {op} {s2}'; "
                f"replaced in both branches"
            )

            def _replace(block, key, pre_temp):
                out = []
                for bq in block:
                    if (bq.op in BINARY_OPS and bq.result is not None
                            and (bq.op, str(bq.arg1), str(bq.arg2)) == key):
                        out.append(Quad("=", pre_temp, None, bq.result))
                    else:
                        out.append(bq)
                return out

            new_then = _replace(then_block, key, pre_temp)
            new_else = _replace(else_block, key, pre_temp)

            code = (code[:i] +
                    [pre_quad, q] +
                    new_then +
                    [code[goto_idx], code[else_start]] +
                    new_else +
                    code[end_start:])
            changed = True
            break

    return code


# ── Existing passes (updated to carry the report list) ────────────────────────

def _constant_fold_and_propagate(code, report):
    """
    Constant folding and safe constant propagation.
    The constants map is reset at every label / branch to avoid propagating
    values across loop back-edges.
    """
    consts = {}
    out = []
    for q in code:
        if q.op in ("label", "goto"):
            consts = {}
            out.append(q)
            continue
        if q.op == "ifFalse":
            arg = q.arg1
            if isinstance(arg, str) and arg in consts:
                arg = consts[arg]
            out.append(Quad("ifFalse", arg, None, q.result))
            consts = {}
            continue

        a1, a2 = q.arg1, q.arg2
        if isinstance(a1, str) and a1 in consts:
            a1 = consts[a1]
        if isinstance(a2, str) and a2 in consts:
            a2 = consts[a2]

        if q.op in ARITH and _is_const(a1) and _is_const(a2):
            x, y = _num(a1), _num(a2)
            val = {"+": x + y, "-": x - y, "*": x * y,
                   "/": (x / y if y else 0)}[q.op]
            if isinstance(x, int) and isinstance(y, int) and q.op != "/":
                val = int(val)
            old_repr = repr(Quad(q.op, a1, a2, q.result))
            consts[q.result] = val
            out.append(Quad("=", val, None, q.result))
            report.append(f"[Constant Folding] {old_repr} => {q.result} = {val}")
            continue

        if q.op == "=" and _is_const(a1):
            consts[q.result] = _num(a1)
            out.append(Quad("=", _num(a1), None, q.result))
            continue

        if q.result in consts and q.op != "label":
            del consts[q.result]
        out.append(Quad(q.op, a1, a2, q.result))
    return out


def _algebraic_simplify(code, report):
    """Algebraic identities: x*0=0, x*1=x, x+0=x."""
    out = []
    for q in code:
        if q.op == "*" and (q.arg2 == 0 or q.arg1 == 0):
            report.append(f"[Algebraic Simplification] {q} => {q.result} = 0")
            out.append(Quad("=", 0, None, q.result))
        elif q.op == "*" and q.arg2 == 1:
            report.append(
                f"[Algebraic Simplification] {q} => {q.result} = {q.arg1}"
            )
            out.append(Quad("=", q.arg1, None, q.result))
        elif q.op == "*" and q.arg1 == 1:
            report.append(
                f"[Algebraic Simplification] {q} => {q.result} = {q.arg2}"
            )
            out.append(Quad("=", q.arg2, None, q.result))
        elif q.op == "+" and q.arg2 == 0:
            report.append(
                f"[Algebraic Simplification] {q} => {q.result} = {q.arg1}"
            )
            out.append(Quad("=", q.arg1, None, q.result))
        elif q.op == "+" and q.arg1 == 0:
            report.append(
                f"[Algebraic Simplification] {q} => {q.result} = {q.arg2}"
            )
            out.append(Quad("=", q.arg2, None, q.result))
        else:
            out.append(q)
    return out


def _eliminate_dead_copies(code, report):
    """Remove temporaries (t…) assigned but never used as an operand."""
    uses = _count_uses(code)
    out = []
    for q in code:
        if (q.op == "=" and isinstance(q.result, str)
                and q.result.startswith("t")
                and uses.get(q.result, 0) == 0):
            report.append(
                f"[Dead Copy Elimination] removed unused temp: {q}"
            )
            continue
        out.append(q)
    return out
