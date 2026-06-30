"""
SimpleLang Compiler - main driver
Runs the full 6-phase pipeline:
  1. Lexical Analysis        (FA-based DFA scanner)
  2. Syntax Analysis         (Recursive-Descent Parser + Panic-Mode recovery)
  3. Semantic Analysis       (Scope/Type/Bounds checks; HashTable symbol table)
  4. Intermediate Code Gen   (Three-Address Code / Quadruples)
  5. Optimization            (Basic blocks, CFG, DAG, Liveness, + 9 passes)
  6. Target Code Gen         (Register-based assembly + AddressDescriptors + AR)

Usage:
    python compiler.py <source_file> [--phase N] [-o output_file]

    --phase N   Show output for phase N only (1-6).
                Each phase still runs all prior phases internally,
                but only phase N's output is printed.
                Omit to run and show all six phases.
"""

import sys
import os
import io

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lexer    import Lexer
from parser   import Parser, SyntaxError_
from semantic import SemanticAnalyzer
from ir_gen   import IRGenerator
from optimizer import (optimize, identify_basic_blocks,
                       build_cfg, build_dag, liveness_analysis)
from codegen  import generate_target


LINE = "=" * 64


def banner(title, sink):
    sink.write("\n" + LINE + "\n")
    sink.write(title + "\n")
    sink.write(LINE + "\n")


def compile_source(src, sink, phase_only=None):
    """
    Compile src through all required phases.

    phase_only=None  → write every phase's output to sink (full pipeline).
    phase_only=N     → write only phase N's output to sink.
                       Earlier phases still run (each needs the previous
                       phase's result) but their output is discarded.
                       If compilation fails before reaching phase N,
                       the failing phase's error output is shown instead.
    """

    # One buffer per phase; we decide at each exit which one(s) to flush.
    b = [None] + [io.StringIO() for _ in range(6)]   # b[1] … b[6]

    def emit(reached):
        """Flush the right buffer(s) to sink."""
        if phase_only is None:
            for i in range(1, reached + 1):
                sink.write(b[i].getvalue())
        elif phase_only <= reached:
            # Requested phase was reached successfully — show it alone.
            sink.write(b[phase_only].getvalue())
        else:
            # Compilation failed before the requested phase — show the error.
            sink.write(b[reached].getvalue())

    # ── Phase 1: Lexical Analysis ─────────────────────────────────────────────
    banner("PHASE 1: LEXICAL ANALYSIS  (FA-based DFA Scanner)", b[1])
    lexer = Lexer(src)
    tokens, lex_errors = lexer.tokenize()

    b[1].write(f"{'TYPE':<12}{'VALUE':<22}{'LINE':<6}{'COL'}\n")
    b[1].write("-" * 48 + "\n")
    for t in tokens:
        if t.type == "EOF":
            continue
        b[1].write(f"{t.type:<12}{str(t.value):<22}{t.line:<6}{t.col}\n")

    if lex_errors:
        b[1].write("\nLexical Errors:\n")
        for e in lex_errors:
            b[1].write("  " + e + "\n")
        b[1].write("\nCompilation stopped at lexical phase.\n")
        emit(1)
        return False

    if phase_only == 1:
        emit(1)
        return True

    # ── Phase 2: Syntax Analysis ──────────────────────────────────────────────
    banner("PHASE 2: SYNTAX ANALYSIS  (Recursive-Descent Parser)", b[2])
    parser = Parser(tokens)
    program, syn_errors = parser.parse()

    if syn_errors:
        b[2].write("Syntax errors (parser used panic-mode recovery):\n")
        for e in syn_errors:
            b[2].write(("  " + e if not e.lstrip().startswith("-->") else e) + "\n")
        b[2].write("\nParsing recovered and continued; AST built from valid statements:\n")
        _dump_ast(program, b[2])
        b[2].write("\nCompilation stopped after syntax phase due to errors above.\n")
        emit(2)
        return False

    b[2].write("Parsing successful. No syntax errors. AST built.\n")
    _dump_ast(program, b[2])

    if phase_only == 2:
        emit(2)
        return True

    # ── Phase 3: Semantic Analysis ────────────────────────────────────────────
    banner("PHASE 3: SEMANTIC ANALYSIS  (Scope / Type / Array-Bounds)", b[3])
    analyzer = SemanticAnalyzer()
    table, sem_errors = analyzer.analyze(program)

    b[3].write("Symbol Table  (backed by hand-coded HashTable, DJB2 hash):\n")
    b[3].write(f"  {'NAME':<14}{'TYPE':<14}{'SIZE(B)':<10}{'OFFSET(B)'}\n")
    b[3].write("  " + "-" * 46 + "\n")
    for name, entry in table.symbols.items():
        b[3].write(
            f"  {name:<14}{entry.type_str:<14}{entry.size:<10}{entry.offset}\n"
        )
    b[3].write(f"\n  Total activation-record size: {table.total_size} bytes\n")

    if sem_errors:
        b[3].write("\nSemantic Errors:\n")
        for e in sem_errors:
            b[3].write("  " + e + "\n")
        b[3].write("\nCompilation stopped at semantic phase.\n")
        emit(3)
        return False

    b[3].write("\nNo semantic errors.\n")

    if phase_only == 3:
        emit(3)
        return True

    # ── Phase 4: Intermediate Code Generation ─────────────────────────────────
    banner("PHASE 4: INTERMEDIATE CODE  (Three-Address Code / Quadruples)", b[4])
    ir = IRGenerator()
    code = ir.generate(program)
    for i, q in enumerate(code):
        b[4].write(f"  {i:>3}: {q}\n")

    if phase_only == 4:
        emit(4)
        return True

    # ── Phase 5: Optimization ─────────────────────────────────────────────────
    banner("PHASE 5: OPTIMIZATION  (Lecture 9)", b[5])

    blocks = identify_basic_blocks(code)
    b[5].write(f"\nBasic Blocks ({len(blocks)} total):\n")
    for k, blk in enumerate(blocks):
        b[5].write(f"  Block {k}:\n")
        for q in blk:
            b[5].write(f"    {q}\n")

    cfg_nodes = build_cfg(blocks)
    b[5].write(f"\nControl Flow Graph ({len(cfg_nodes)} nodes):\n")
    for node in cfg_nodes:
        lbl = ""
        if node.quads and node.quads[0].op == "label":
            lbl = f"  [{node.quads[0].result}]"
        pred_str = str(node.predecessors) if node.predecessors else "entry"
        succ_str = str(node.successors)   if node.successors   else "exit"
        b[5].write(
            f"  Block {node.block_id}{lbl:<12}  "
            f"pred={pred_str:<14}  succ={succ_str}\n"
        )

    b[5].write(f"\nDAG Analysis per Basic Block:\n")
    total_cse = 0
    for k, blk in enumerate(blocks):
        dag_nodes, cse = build_dag(blk)
        total_cse += cse
        leaves = [n for n in dag_nodes if n.op == "leaf"]
        ops    = [n for n in dag_nodes if n.op != "leaf"]
        b[5].write(f"  Block {k} ({len(blk)} quad(s)):\n")
        if leaves:
            b[5].write(
                "    Leaf nodes : " +
                ", ".join(str(n.value) for n in leaves) + "\n"
            )
        for n in ops:
            lbl   = "[" + ",".join(n.labels) + "]" if n.labels else ""
            l_str = (str(n.left.value)  if n.left  and n.left.op  == "leaf"
                     else f"#{n.left.uid}"  if n.left  else "?")
            r_str = (str(n.right.value) if n.right and n.right.op == "leaf"
                     else f"#{n.right.uid}" if n.right else "")
            if r_str:
                b[5].write(f"    #{n.uid}{lbl} = {l_str} {n.op} {r_str}\n")
            else:
                b[5].write(f"    #{n.uid}{lbl} = {n.op}({l_str})\n")
        if cse:
            b[5].write(f"    *** {cse} common subexpression(s) detected ***\n")
        if not leaves and not ops:
            b[5].write("    (no arithmetic expressions — control/memory ops only)\n")

    if total_cse:
        b[5].write(f"\n  Total CSE savings possible: {total_cse} expression(s)\n")

    live_in, live_out = liveness_analysis(blocks, cfg_nodes)
    b[5].write(f"\nLiveness Analysis:\n")
    for k in range(len(blocks)):
        li = "{" + ", ".join(sorted(live_in[k]))  + "}" if live_in[k]  else "{}"
        lo = "{" + ", ".join(sorted(live_out[k])) + "}" if live_out[k] else "{}"
        b[5].write(f"  Block {k}: live_in={li:<30} live_out={lo}\n")

    opt, report = optimize(code)

    b[5].write(f"\nOptimization Report ({len(report)} action(s)):\n")
    if report:
        for line in report:
            b[5].write(f"  {line}\n")
    else:
        b[5].write("  (no optimizations applied)\n")

    b[5].write(f"\nOptimized TAC:\n")
    for i, q in enumerate(opt):
        b[5].write(f"  {i:>3}: {q}\n")
    b[5].write(f"\nInstructions before: {len(code)}, after: {len(opt)}\n")

    if phase_only == 5:
        emit(5)
        return True

    # ── Phase 6: Target Code Generation ──────────────────────────────────────
    banner("PHASE 6: TARGET CODE  (Register-Based Assembly + Activation Record)", b[6])

    asm, ad_dump = generate_target(opt, table.symbols)

    for line in asm:
        indent = "" if line.startswith("LABEL") else "    "
        b[6].write(indent + line + "\n")

    if ad_dump:
        b[6].write("\nAddress Descriptors (final state):\n")
        b[6].write(f"  {'NAME':<14}LOCATIONS\n")
        b[6].write("  " + "-" * 34 + "\n")
        for name, locs in ad_dump.items():
            if name.startswith("_acc"):
                continue
            b[6].write(f"  {name:<14}{{{', '.join(locs)}}}\n")

    banner("COMPILATION SUCCESSFUL", b[6])

    emit(6)
    return True


# ── AST dump helper ───────────────────────────────────────────────────────────

def _dump_ast(node, sink, indent=1):
    from ast_nodes import (Program, VarDecl, Assign, Print, If, While,
                           BinOp, UnaryOp, Num, Bool, Str, Var,
                           ArrayDecl, ArrayAccess, ArrayAssign)
    pad = "  " * indent
    if isinstance(node, Program):
        sink.write("Program\n")
        for s in node.statements:
            _dump_ast(s, sink, indent + 1)
    elif isinstance(node, VarDecl):
        sink.write(f"{pad}VarDecl {node.var_type} {node.name}\n")
        if node.init:
            _dump_ast(node.init, sink, indent + 1)
    elif isinstance(node, Assign):
        sink.write(f"{pad}Assign {node.name}\n")
        _dump_ast(node.expr, sink, indent + 1)
    elif isinstance(node, Print):
        sink.write(f"{pad}Print\n")
        _dump_ast(node.expr, sink, indent + 1)
    elif isinstance(node, If):
        sink.write(f"{pad}If\n{pad}  cond:\n")
        _dump_ast(node.cond, sink, indent + 2)
        sink.write(f"{pad}  then:\n")
        for s in node.then_body:
            _dump_ast(s, sink, indent + 2)
        if node.else_body:
            sink.write(f"{pad}  else:\n")
            for s in node.else_body:
                _dump_ast(s, sink, indent + 2)
    elif isinstance(node, While):
        sink.write(f"{pad}While\n{pad}  cond:\n")
        _dump_ast(node.cond, sink, indent + 2)
        sink.write(f"{pad}  body:\n")
        for s in node.body:
            _dump_ast(s, sink, indent + 2)
    elif isinstance(node, BinOp):
        sink.write(f"{pad}BinOp '{node.op}'\n")
        _dump_ast(node.left,  sink, indent + 1)
        _dump_ast(node.right, sink, indent + 1)
    elif isinstance(node, UnaryOp):
        sink.write(f"{pad}UnaryOp '{node.op}'\n")
        _dump_ast(node.operand, sink, indent + 1)
    elif isinstance(node, Num):
        sink.write(f"{pad}Num {node.value}\n")
    elif isinstance(node, Bool):
        sink.write(f"{pad}Bool {node.value}\n")
    elif isinstance(node, Str):
        sink.write(f'{pad}Str "{node.value}"\n')
    elif isinstance(node, Var):
        sink.write(f"{pad}Var {node.name}\n")
    elif isinstance(node, ArrayDecl):
        sink.write(f"{pad}ArrayDecl {node.var_type} {node.name}[{node.size}]\n")
    elif isinstance(node, ArrayAccess):
        sink.write(f"{pad}ArrayAccess {node.name}[\n")
        _dump_ast(node.index, sink, indent + 1)
        sink.write(f"{pad}]\n")
    elif isinstance(node, ArrayAssign):
        sink.write(f"{pad}ArrayAssign {node.name}[\n")
        _dump_ast(node.index, sink, indent + 1)
        sink.write(f"{pad}] =\n")
        _dump_ast(node.expr, sink, indent + 1)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("Usage: python compiler.py <source_file> [--phase N] [-o output_file]")
        sys.exit(1)

    src_path = sys.argv[1]

    phase_only = None
    if "--phase" in sys.argv:
        idx = sys.argv.index("--phase")
        try:
            phase_only = int(sys.argv[idx + 1])
            if phase_only not in range(1, 7):
                raise ValueError
        except (IndexError, ValueError):
            print("Error: --phase requires a number between 1 and 6")
            sys.exit(1)

    out_path = None
    if "-o" in sys.argv:
        out_path = sys.argv[sys.argv.index("-o") + 1]

    with open(src_path, "r") as f:
        src = f.read()

    buf = io.StringIO()
    buf.write(f"SimpleLang Compiler — compiling: {src_path}\n")
    if phase_only:
        buf.write(f"(showing Phase {phase_only} output only)\n")
    ok = compile_source(src, buf, phase_only)
    result = buf.getvalue()

    print(result)
    if out_path:
        with open(out_path, "w") as f:
            f.write(result)
        print(f"\n[Output written to {out_path}]")

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
