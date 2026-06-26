"""
Phase 5: Code Optimization
Applies simple machine-independent optimizations to the TAC:
  - Constant folding   (t = 3 + 4  ->  t = 7)
  - Constant propagation
  - Algebraic simplification (x*1, x+0, x*0)
  - Dead-temp elimination (copies never used)
"""

from ir_gen import Quad

ARITH = {"+", "-", "*", "/"}


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


def optimize(code):
    code = _constant_fold_and_propagate(code)
    code = _algebraic_simplify(code)
    code = _eliminate_dead_copies(code)
    return code


def _constant_fold_and_propagate(code):
    consts = {}          # var/temp -> constant value
    out = []
    for q in code:
        # Labels and jumps end a basic block. A value known to be constant
        # before a jump target may differ when reached via a back-edge
        # (e.g. a loop counter), so we conservatively forget all constants.
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
            consts[q.result] = val
            out.append(Quad("=", val, None, q.result))
            continue

        if q.op == "=" and _is_const(a1):
            consts[q.result] = _num(a1)
            out.append(Quad("=", _num(a1), None, q.result))
            continue

        # result is being redefined non-constantly: drop any old const
        if q.result in consts and q.op != "label":
            del consts[q.result]
        out.append(Quad(q.op, a1, a2, q.result))
    return out


def _algebraic_simplify(code):
    out = []
    for q in code:
        if q.op == "*" and (q.arg2 == 0 or q.arg1 == 0):
            out.append(Quad("=", 0, None, q.result)); continue
        if q.op == "*" and q.arg2 == 1:
            out.append(Quad("=", q.arg1, None, q.result)); continue
        if q.op == "*" and q.arg1 == 1:
            out.append(Quad("=", q.arg2, None, q.result)); continue
        if q.op == "+" and q.arg2 == 0:
            out.append(Quad("=", q.arg1, None, q.result)); continue
        if q.op == "+" and q.arg1 == 0:
            out.append(Quad("=", q.arg2, None, q.result)); continue
        out.append(q)
    return out


def _eliminate_dead_copies(code):
    # count how often each name is used as an argument
    uses = {}
    for q in code:
        for a in (q.arg1, q.arg2):
            if isinstance(a, str):
                uses[a] = uses.get(a, 0) + 1
    out = []
    for q in code:
        # remove temp copies that are never used anywhere
        if (q.op == "=" and isinstance(q.result, str)
                and q.result.startswith("t")
                and uses.get(q.result, 0) == 0):
            continue
        out.append(q)
    return out
