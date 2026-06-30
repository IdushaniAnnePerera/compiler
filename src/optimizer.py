"""
Phase 5: Code Optimization
Machine-independent optimizations from Lecture 9 (COSC 44283).

Analysis structures (new)
--------------------------
CFGNode / build_cfg          Control Flow Graph: one node per basic block,
                             edges = control-flow successors / predecessors.

DAGNode / build_dag          Directed Acyclic Graph for a single basic block:
                             detects common subexpressions (CSE) within the block.

liveness_analysis            Backward data-flow: computes live-in / live-out
                             sets per block using CFG successor edges.

Optimization passes (existing)
-------------------------------
1. Basic Block Identification   — leader algorithm
2. Constant Folding & Propagation
3. Algebraic Simplification
4. Strength Reduction           — x*2^n -> x<<n
5. Loop-Invariant Code Motion   — hoist invariant instr. before loop header
6. Induction Variable Detection — report variables incremented by a constant step
7. Partial Redundancy Elim.     — pre-compute exprs common to both branches
8. Dead-Code Elimination        — unreachable code + unused assignments
9. Dead-Copy Elimination        — unused temporaries

Public API
----------
identify_basic_blocks(code)         -> list[list[Quad]]
build_cfg(blocks)                   -> list[CFGNode]
build_dag(block)                    -> (list[DAGNode], cse_count)
liveness_analysis(blocks, cfg=None) -> (live_in, live_out)  each list[set[str]]
optimize(code)                      -> (optimized_code, report_lines)
"""

import math
from ir_gen import Quad

ARITH        = {"+", "-", "*", "/"}
BINARY_OPS   = {"+", "-", "*", "/", "<", ">", "<=", ">=", "==", "!=", "&&", "||",
                "shl"}
SIDE_EFFECTS = {"goto", "ifFalse", "label", "print", "alloc_arr", "store_arr"}

# Ops where the 'result' field holds a value *consumed* (not produced).
_RESULT_IS_CONSUMED = {"store_arr"}


# ── helpers ──────────────────────────────────────────────────────────────────

def _count_uses(code):
    """Count how many times each name is used as an operand."""
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
        if v.startswith('"') or v in ("true", "false"):
            return True   # string literal or boolean literal
        try:
            float(v)
            return True
        except (ValueError, TypeError):
            return False
    return False


def _num(v):
    if isinstance(v, (int, float)):
        return v
    if isinstance(v, str) and (v in ("true", "false") or v.startswith('"')):
        return v   # boolean / string literals: keep as-is, not numeric
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


# ── 1. Basic Block Identification ─────────────────────────────────────────────

def identify_basic_blocks(code):
    """
    Standard leader algorithm (Lecture 9).

    A statement is a *leader* if it is:
      (a) the first statement in the program,
      (b) the target of any branch (goto / ifFalse), or
      (c) the statement immediately following a branch.
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


# ── Control Flow Graph ────────────────────────────────────────────────────────

class CFGNode:
    """One node in the Control Flow Graph — corresponds to one basic block."""

    def __init__(self, block_id, quads):
        self.block_id     = block_id
        self.quads        = quads
        self.successors   = []   # list of block indices
        self.predecessors = []   # list of block indices

    def __repr__(self):
        return (f"CFGNode(id={self.block_id}, "
                f"succ={self.successors}, pred={self.predecessors})")


def build_cfg(blocks):
    """
    Build a Control Flow Graph from a list of basic blocks.

    Edges are determined by the last instruction of each block:
      goto L      -> one edge to the block starting with label L
      ifFalse L   -> two edges: fall-through (block i+1) and jump (label L)
      other       -> one edge to the next block (sequential fall-through)
    """
    if not blocks:
        return []

    nodes = [CFGNode(i, blk) for i, blk in enumerate(blocks)]

    # Map label name -> block index (the block whose first quad is that label)
    label_to_block = {}
    for i, blk in enumerate(blocks):
        if blk and blk[0].op == "label":
            label_to_block[blk[0].result] = i

    for i, node in enumerate(nodes):
        if not node.quads:
            if i + 1 < len(nodes):
                _add_edge(nodes, i, i + 1)
            continue

        last = node.quads[-1]

        if last.op == "goto":
            target = label_to_block.get(last.result)
            if target is not None:
                _add_edge(nodes, i, target)

        elif last.op == "ifFalse":
            # Fall-through to next block
            if i + 1 < len(nodes):
                _add_edge(nodes, i, i + 1)
            # Conditional jump to label target
            target = label_to_block.get(last.result)
            if target is not None:
                _add_edge(nodes, i, target)

        else:
            # Sequential fall-through
            if i + 1 < len(nodes):
                _add_edge(nodes, i, i + 1)

    return nodes


def _add_edge(nodes, src, dst):
    if dst not in nodes[src].successors:
        nodes[src].successors.append(dst)
    if src not in nodes[dst].predecessors:
        nodes[dst].predecessors.append(src)


# ── DAG (Directed Acyclic Graph) per basic block ──────────────────────────────

class DAGNode:
    """
    One node in a basic-block DAG.

    Leaf nodes  : op="leaf", value = variable name or constant.
    Op nodes    : op = operator string, left/right = child DAGNode.
    labels      : list of variable names that currently hold this node's value
                  (a shared node means those names alias the same computation).
    """

    def __init__(self, op, left=None, right=None, value=None):
        self.op     = op
        self.left   = left    # left child (None for leaves)
        self.right  = right   # right child (None for unary/leaves)
        self.value  = value   # leaf: the name/constant it represents
        self.labels = []      # variable names attached to this value
        self.uid    = 0       # assigned by build_dag


def build_dag(block):
    """
    Build a DAG for a single basic block to detect common subexpressions.

    Returns (dag_nodes, cse_count) where:
      dag_nodes : list of all DAGNode objects (leaves + op nodes)
      cse_count : number of operations that reused an existing node
                  (each reuse is a potential CSE saving)

    Implementation
    --------------
    node_of      maps  str(val) -> DAGNode  for the current value of each name
    expr_key_map maps  (op, left_uid, right_uid) -> DAGNode  for op nodes
    When we see  t = a OP b :
      1. Look up (or create) leaf nodes for a and b.
      2. Form key = (op, left.uid, right.uid).
      3. If key already in expr_key_map => CSE found, reuse that node.
      4. Otherwise create a new op node and record it.
      5. Bind t to the resulting node.
    """
    uid_ctr = [0]

    def _make(op, left=None, right=None, value=None):
        uid_ctr[0] += 1
        n     = DAGNode(op, left, right, value)
        n.uid = uid_ctr[0]
        return n

    node_of      = {}   # str(name_or_const) -> DAGNode
    expr_key_map = {}   # (op, left_uid, right_uid) -> DAGNode
    all_nodes    = []
    cse_count    = 0

    def leaf(val):
        k = str(val)
        if k not in node_of:
            n = _make("leaf", value=val)
            node_of[k] = n
            all_nodes.append(n)
        return node_of[k]

    for q in block:
        # Skip control-flow and memory ops (memory aliasing makes DAG unsafe)
        if q.op in ("label", "goto", "ifFalse", "print",
                    "alloc_arr", "load_arr", "store_arr",
                    "uminus", "not"):
            continue

        if q.result is None:
            continue

        if q.op == "=" and q.arg2 is None:
            # Copy: result aliases arg1's node
            src = leaf(q.arg1)
            node_of[str(q.result)] = src
            if q.result not in src.labels:
                src.labels.append(q.result)
            continue

        if q.op in BINARY_OPS:
            n_left  = leaf(q.arg1)
            n_right = leaf(q.arg2) if q.arg2 is not None else _make("leaf", value=None)
            r_uid   = n_right.uid if n_right else -1
            key = (q.op, n_left.uid, r_uid)

            if key in expr_key_map:
                n = expr_key_map[key]
                cse_count += 1
            else:
                n = _make(q.op, left=n_left, right=n_right)
                expr_key_map[key] = n
                all_nodes.append(n)

            node_of[str(q.result)] = n
            if q.result not in n.labels:
                n.labels.append(q.result)

    return all_nodes, cse_count


# ── Liveness Analysis ─────────────────────────────────────────────────────────

def liveness_analysis(blocks, cfg_nodes=None):
    """
    Backward data-flow liveness analysis.

    For each basic block b:
        use[b]  = variables used in b before any definition in b
        def[b]  = variables defined in b

    Equations (iterated to fixed point):
        live_out[b] = union of live_in[s] for all successors s of b
        live_in[b]  = use[b] ∪ (live_out[b] − def[b])

    If cfg_nodes is provided, successor sets come from the CFG (correct for
    loops and branches).  Otherwise a simple linear-order fallback is used.

    Returns (live_in, live_out) as lists of sets, one per block.
    """
    n = len(blocks)
    if n == 0:
        return [], []

    # Ops whose result field is a label name, not a variable definition
    _NO_DEF_OPS = {"goto", "ifFalse", "label"}

    use_b = []
    def_b = []

    for blk in blocks:
        b_use, b_def = set(), set()
        for q in blk:
            # alloc_arr: arg1 is the array being created — a definition, not a use
            if q.op == "alloc_arr":
                if isinstance(q.arg1, str):
                    b_def.add(q.arg1)
                continue

            # Uses: arg1, arg2
            for a in (q.arg1, q.arg2):
                if isinstance(a, str) and not _is_const(a) and a not in b_def:
                    b_use.add(a)

            # For store_arr the result field is also a consumed value (not a def)
            if (q.op in _RESULT_IS_CONSUMED
                    and isinstance(q.result, str)
                    and q.result not in b_def):
                b_use.add(q.result)

            # Definitions
            if (q.result is not None
                    and isinstance(q.result, str)
                    and q.op not in _NO_DEF_OPS
                    and q.op not in _RESULT_IS_CONSUMED):
                b_def.add(q.result)

        use_b.append(b_use)
        def_b.append(b_def)

    live_in  = [set() for _ in range(n)]
    live_out = [set() for _ in range(n)]

    # Fixed-point iteration (backward)
    changed = True
    while changed:
        changed = False
        for i in range(n - 1, -1, -1):
            # live_out[i] = union of live_in[s] for each successor s
            new_out = set()
            if cfg_nodes and i < len(cfg_nodes):
                for s in cfg_nodes[i].successors:
                    if 0 <= s < n:
                        new_out |= live_in[s]
            else:
                if i + 1 < n:
                    new_out |= live_in[i + 1]

            new_in = use_b[i] | (new_out - def_b[i])

            if new_in != live_in[i] or new_out != live_out[i]:
                live_in[i]  = new_in
                live_out[i] = new_out
                changed = True

    return live_in, live_out


# ── Public optimize() entry point ─────────────────────────────────────────────

def optimize(code):
    """Run all optimization passes in order.  Returns (optimized_code, report)."""
    report = []

    code = _constant_fold_and_propagate(code, report)
    code = _algebraic_simplify(code, report)
    code = strength_reduction(code, report)
    code = loop_invariant_motion(code, report)
    detect_induction_variables(code, report)
    code = partial_redundancy_elimination(code, report)
    code = dead_code_elimination(code, report)
    code = _eliminate_dead_copies(code, report)

    return code, report


# ── 2. Dead-Code Elimination ──────────────────────────────────────────────────

def dead_code_elimination(code, report):
    """
    Pass A — unreachable code after unconditional goto.
    Pass B — dead assignments (iterative; result never used as operand).
    """
    # Pass A
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

    # Pass B
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
    """Replace  t = x * 2^n  with  t = x << n."""
    out = []
    for q in code:
        replaced = False
        if q.op == "*":
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
    """Hoist loop-invariant instructions to before the loop header."""
    changed_outer = True
    while changed_outer:
        changed_outer = False
        label_pos = _build_label_map(code)

        back_edges = []
        for idx, q in enumerate(code):
            if q.op == "goto" and q.result in label_pos:
                hdr = label_pos[q.result]
                if hdr <= idx:
                    back_edges.append((q.result, hdr, idx))

        for lbl, hdr, go_idx in back_edges:
            body = list(code[hdr + 1: go_idx])

            modified = {
                bq.result
                for bq in body
                if bq.op not in SIDE_EFFECTS
                and bq.result is not None
                and isinstance(bq.result, str)
            }

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
                            f"[Loop-Invariant Motion] hoisted {bq} out of loop {lbl}"
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
                break

    return code


# ── 5. Induction Variable Detection ──────────────────────────────────────────

def detect_induction_variables(code, report):
    """Detect variables incremented by a constant step inside a loop (report only)."""
    label_pos = _build_label_map(code)

    for idx, q in enumerate(code):
        if q.op != "goto" or q.result not in label_pos:
            continue
        hdr = label_pos[q.result]
        if hdr > idx:
            continue
        body = code[hdr + 1: idx]

        reported = set()
        for j, bq in enumerate(body):
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
    Detect expressions computed in both branches of an if/else and
    pre-compute them once before the branch.
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
            else_start = label_pos[else_label]

            if else_start < 1 or code[else_start - 1].op != "goto":
                continue
            goto_idx  = else_start - 1
            end_label = code[goto_idx].result
            if end_label not in label_pos:
                continue
            end_start = label_pos[end_label]

            if end_start <= else_start:
                continue

            then_block = code[i + 1: goto_idx]
            else_block = code[else_start + 1: end_start]

            def _exprs(block):
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

            key        = next(iter(common))
            op, s1, s2 = key
            src_q      = _exprs(then_block)[key]

            _pre_count[0] += 1
            pre_temp = f"tP{_pre_count[0]}"
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


# ── Existing passes ───────────────────────────────────────────────────────────

def _constant_fold_and_propagate(code, report):
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
    out = []
    for q in code:
        if q.op == "*" and (q.arg2 == 0 or q.arg1 == 0):
            report.append(f"[Algebraic Simplification] {q} => {q.result} = 0")
            out.append(Quad("=", 0, None, q.result))
        elif q.op == "*" and q.arg2 == 1:
            report.append(f"[Algebraic Simplification] {q} => {q.result} = {q.arg1}")
            out.append(Quad("=", q.arg1, None, q.result))
        elif q.op == "*" and q.arg1 == 1:
            report.append(f"[Algebraic Simplification] {q} => {q.result} = {q.arg2}")
            out.append(Quad("=", q.arg2, None, q.result))
        elif q.op == "+" and q.arg2 == 0:
            report.append(f"[Algebraic Simplification] {q} => {q.result} = {q.arg1}")
            out.append(Quad("=", q.arg1, None, q.result))
        elif q.op == "+" and q.arg1 == 0:
            report.append(f"[Algebraic Simplification] {q} => {q.result} = {q.arg2}")
            out.append(Quad("=", q.arg2, None, q.result))
        else:
            out.append(q)
    return out


def _eliminate_dead_copies(code, report):
    uses = _count_uses(code)
    out = []
    for q in code:
        if (q.op == "=" and isinstance(q.result, str)
                and q.result.startswith("t")
                and uses.get(q.result, 0) == 0):
            report.append(f"[Dead Copy Elimination] removed unused temp: {q}")
            continue
        out.append(q)
    return out
