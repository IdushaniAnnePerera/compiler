"""
SimpleLang Compiler - main driver
Runs the full 6-phase pipeline:
  1. Lexical Analysis        (FA-based DFA scanner)
  2. Syntax Analysis         (Recursive-Descent Parser + Panic-Mode recovery)
  3. Semantic Analysis       (Scope/Type/Bounds checks; HashTable symbol table)
  4. Intermediate Code Gen   (Three-Address Code / Quadruples)
  5. Optimization            (Basic blocks, CFG, DAG, Liveness, + 7 passes)
  6. Target Code Gen         (Register-based assembly + AddressDescriptors + AR)

Usage:
    python compiler.py <source_file> [--phase N] [-o output_file]

    --phase N   Run only up to phase N (1-6) then stop.
                Omit to run all six phases.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lexer   import Lexer
from parser  import Parser, SyntaxError_
from semantic import SemanticAnalyzer
from ir_gen  import IRGenerator
from optimizer import (optimize, identify_basic_blocks,
                       build_cfg, build_dag, liveness_analysis)
from codegen import generate_target


LINE = "=" * 64


def banner(title, sink):
    sink.write("\n" + LINE + "\n")
    sink.write(title + "\n")
    sink.write(LINE + "\n")


def compile_source(src, sink, stop_at=6):
    # ── Phase 1: Lexical Analysis ─────────────────────────────────────────────
    banner("PHASE 1: LEXICAL ANALYSIS  (FA-based DFA Scanner)", sink)
    lexer = Lexer(src)
    tokens, lex_errors = lexer.tokenize()

    sink.write(f"{'TYPE':<12}{'VALUE':<22}{'LINE':<6}{'COL'}\n")
    sink.write("-" * 48 + "\n")
    for t in tokens:
        if t.type == "EOF":
            continue
        sink.write(f"{t.type:<12}{str(t.value):<22}{t.line:<6}{t.col}\n")

    if lex_errors:
        sink.write("\nLexical Errors:\n")
        for e in lex_errors:
            sink.write("  " + e + "\n")
        sink.write("\nCompilation stopped at lexical phase.\n")
        return False

    if stop_at == 1:
        return True

    # ── Phase 2: Syntax Analysis ──────────────────────────────────────────────
    banner("PHASE 2: SYNTAX ANALYSIS  (Recursive-Descent Parser)", sink)
    parser = Parser(tokens)
    program, syn_errors = parser.parse()

    if syn_errors:
        sink.write("Syntax errors (parser used panic-mode recovery):\n")
        for e in syn_errors:
            sink.write(("  " + e if not e.lstrip().startswith("-->") else e) + "\n")
        sink.write("\nParsing recovered and continued; AST built from valid statements:\n")
        _dump_ast(program, sink)
        sink.write("\nCompilation stopped after syntax phase due to errors above.\n")
        return False

    sink.write("Parsing successful. No syntax errors. AST built.\n")
    _dump_ast(program, sink)

    if stop_at == 2:
        return True

    # ── Phase 3: Semantic Analysis ────────────────────────────────────────────
    banner("PHASE 3: SEMANTIC ANALYSIS  (Scope / Type / Array-Bounds)", sink)
    analyzer = SemanticAnalyzer()
    table, sem_errors = analyzer.analyze(program)

    sink.write("Symbol Table  (backed by hand-coded HashTable, DJB2 hash):\n")
    sink.write(f"  {'NAME':<14}{'TYPE':<14}{'SIZE(B)':<10}{'OFFSET(B)'}\n")
    sink.write("  " + "-" * 46 + "\n")
    for name, entry in table.symbols.items():
        sink.write(
            f"  {name:<14}{entry.type_str:<14}{entry.size:<10}{entry.offset}\n"
        )
    sink.write(f"\n  Total activation-record size: {table.total_size} bytes\n")

    if sem_errors:
        sink.write("\nSemantic Errors:\n")
        for e in sem_errors:
            sink.write("  " + e + "\n")
        sink.write("\nCompilation stopped at semantic phase.\n")
        return False
    sink.write("\nNo semantic errors.\n")

    if stop_at == 3:
        return True

    # ── Phase 4: Intermediate Code Generation ─────────────────────────────────
    banner("PHASE 4: INTERMEDIATE CODE  (Three-Address Code / Quadruples)", sink)
    ir = IRGenerator()
    code = ir.generate(program)
    for i, q in enumerate(code):
        sink.write(f"  {i:>3}: {q}\n")

    if stop_at == 4:
        return True

    # ── Phase 5: Optimization ─────────────────────────────────────────────────
    banner("PHASE 5: OPTIMIZATION  (Lecture 9)", sink)

    # 5a — Basic blocks of unoptimized TAC
    blocks = identify_basic_blocks(code)
    sink.write(f"\nBasic Blocks ({len(blocks)} total):\n")
    for k, blk in enumerate(blocks):
        sink.write(f"  Block {k}:\n")
        for q in blk:
            sink.write(f"    {q}\n")

    # 5b — Control Flow Graph
    cfg_nodes = build_cfg(blocks)
    sink.write(f"\nControl Flow Graph ({len(cfg_nodes)} nodes):\n")
    for node in cfg_nodes:
        lbl = ""
        if node.quads and node.quads[0].op == "label":
            lbl = f"  [{node.quads[0].result}]"
        pred_str = str(node.predecessors) if node.predecessors else "entry"
        succ_str = str(node.successors)   if node.successors   else "exit"
        sink.write(
            f"  Block {node.block_id}{lbl:<12}  "
            f"pred={pred_str:<14}  succ={succ_str}\n"
        )

    # 5c — DAG analysis per basic block
    sink.write(f"\nDAG Analysis per Basic Block:\n")
    total_cse = 0
    for k, blk in enumerate(blocks):
        dag_nodes, cse = build_dag(blk)
        total_cse += cse
        leaves  = [n for n in dag_nodes if n.op == "leaf"]
        ops     = [n for n in dag_nodes if n.op != "leaf"]
        sink.write(f"  Block {k} ({len(blk)} quad(s)):\n")
        if leaves:
            sink.write(
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
                sink.write(f"    #{n.uid}{lbl} = {l_str} {n.op} {r_str}\n")
            else:
                sink.write(f"    #{n.uid}{lbl} = {n.op}({l_str})\n")
        if cse:
            sink.write(f"    *** {cse} common subexpression(s) detected ***\n")
        if not leaves and not ops:
            sink.write("    (no arithmetic expressions — control/memory ops only)\n")

    if total_cse:
        sink.write(f"\n  Total CSE savings possible: {total_cse} expression(s)\n")

    # 5d — Liveness analysis
    live_in, live_out = liveness_analysis(blocks, cfg_nodes)
    sink.write(f"\nLiveness Analysis:\n")
    for k in range(len(blocks)):
        li = "{" + ", ".join(sorted(live_in[k]))  + "}" if live_in[k]  else "{}"
        lo = "{" + ", ".join(sorted(live_out[k])) + "}" if live_out[k] else "{}"
        sink.write(f"  Block {k}: live_in={li:<30} live_out={lo}\n")

    # 5e — Run all optimization passes
    opt, report = optimize(code)

    sink.write(f"\nOptimization Report ({len(report)} action(s)):\n")
    if report:
        for line in report:
            sink.write(f"  {line}\n")
    else:
        sink.write("  (no optimizations applied)\n")

    sink.write(f"\nOptimized TAC:\n")
    for i, q in enumerate(opt):
        sink.write(f"  {i:>3}: {q}\n")
    sink.write(f"\nInstructions before: {len(code)}, after: {len(opt)}\n")

    if stop_at == 5:
        return True

    # ── Phase 6: Target Code Generation ──────────────────────────────────────
    banner("PHASE 6: TARGET CODE  (Register-Based Assembly + Activation Record)", sink)

    asm, ad_dump = generate_target(opt, table.symbols)

    for line in asm:
        indent = "" if line.startswith("LABEL") else "    "
        sink.write(indent + line + "\n")

    # Address Descriptor snapshot
    if ad_dump:
        sink.write("\nAddress Descriptors (final state):\n")
        sink.write(f"  {'NAME':<14}LOCATIONS\n")
        sink.write("  " + "-" * 34 + "\n")
        for name, locs in ad_dump.items():
            if name.startswith("_acc"):
                continue    # skip internal scratch registers
            sink.write(f"  {name:<14}{{{', '.join(locs)}}}\n")

    banner("COMPILATION SUCCESSFUL", sink)
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

    stop_at = 6
    if "--phase" in sys.argv:
        idx = sys.argv.index("--phase")
        try:
            stop_at = int(sys.argv[idx + 1])
            if stop_at not in range(1, 7):
                raise ValueError
        except (IndexError, ValueError):
            print("Error: --phase requires a number between 1 and 6")
            sys.exit(1)

    out_path = None
    if "-o" in sys.argv:
        out_path = sys.argv[sys.argv.index("-o") + 1]

    with open(src_path, "r") as f:
        src = f.read()

    import io
    buf = io.StringIO()
    buf.write(f"SimpleLang Compiler — compiling: {src_path}\n")
    if stop_at < 6:
        buf.write(f"(running up to Phase {stop_at} only)\n")
    ok = compile_source(src, buf, stop_at)
    result = buf.getvalue()

    print(result)
    if out_path:
        with open(out_path, "w") as f:
            f.write(result)
        print(f"\n[Output written to {out_path}]")

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
