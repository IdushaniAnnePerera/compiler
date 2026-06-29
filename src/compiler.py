"""
SimpleLang Compiler - main driver
Runs the full pipeline:
  1. Lexical Analysis
  2. Syntax Analysis
  3. Semantic Analysis
  4. Intermediate Code Generation (TAC)
  5. Optimization
  6. Target Code Generation

Usage:
    python compiler.py <source_file> [-o output_file]
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lexer import Lexer
from parser import Parser, SyntaxError_
from semantic import SemanticAnalyzer
from ir_gen import IRGenerator
from optimizer import optimize, identify_basic_blocks
from codegen import generate_target


LINE = "=" * 64


def banner(title, sink):
    sink.write("\n" + LINE + "\n")
    sink.write(title + "\n")
    sink.write(LINE + "\n")


def compile_source(src, sink):
    # ---------- Phase 1: Lexical ----------
    banner("PHASE 1: LEXICAL ANALYSIS (Tokens)", sink)
    lexer = Lexer(src)
    tokens, lex_errors = lexer.tokenize()
    sink.write(f"{'TYPE':<10}{'VALUE':<20}{'LINE':<6}\n")
    sink.write("-" * 36 + "\n")
    for t in tokens:
        if t.type == "EOF":
            continue
        sink.write(f"{t.type:<10}{str(t.value):<20}{t.line:<6}\n")
    if lex_errors:
        sink.write("\nLexical Errors:\n")
        for e in lex_errors:
            sink.write("  " + e + "\n")
        sink.write("\nCompilation stopped at lexical phase.\n")
        return False

    # ---------- Phase 2: Syntax ----------
    banner("PHASE 2: SYNTAX ANALYSIS (Parse Tree / AST)", sink)
    parser = Parser(tokens)
    program, syn_errors = parser.parse()
    if syn_errors:
        sink.write("Syntax errors detected (parser used panic-mode recovery):\n")
        for e in syn_errors:
            sink.write(("  " + e if not e.lstrip().startswith("-->") else e) + "\n")
        sink.write("\nParsing recovered and continued; AST built from the "
                   "valid statements:\n")
        _dump_ast(program, sink)
        sink.write("\nCompilation stopped after syntax phase due to errors above.\n")
        return False
    sink.write("Parsing successful. No syntax errors. AST built.\n")
    _dump_ast(program, sink)

    # ---------- Phase 3: Semantic ----------
    banner("PHASE 3: SEMANTIC ANALYSIS (Symbol Table & Type Checks)", sink)
    analyzer = SemanticAnalyzer()
    table, sem_errors = analyzer.analyze(program)
    sink.write("Symbol Table:\n")
    sink.write(f"  {'NAME':<14}{'TYPE':<10}\n")
    for name, typ in table.symbols.items():
        sink.write(f"  {name:<14}{typ:<10}\n")
    if sem_errors:
        sink.write("\nSemantic Errors:\n")
        for e in sem_errors:
            sink.write("  " + e + "\n")
        sink.write("\nCompilation stopped at semantic phase.\n")
        return False
    sink.write("\nNo semantic errors.\n")

    # ---------- Phase 4: Intermediate Code ----------
    banner("PHASE 4: INTERMEDIATE CODE (Three-Address Code)", sink)
    ir = IRGenerator()
    code = ir.generate(program)
    for i, q in enumerate(code):
        sink.write(f"  {i:>3}: {q}\n")

    # ---------- Phase 5: Optimization ----------
    banner("PHASE 5: OPTIMIZATION (Lecture 9)", sink)

    # 5a — Basic blocks of the unoptimized TAC
    blocks = identify_basic_blocks(code)
    sink.write(f"\nBasic Blocks ({len(blocks)} total, on unoptimized TAC):\n")
    for k, blk in enumerate(blocks):
        sink.write(f"  Block {k + 1}:\n")
        for q in blk:
            sink.write(f"    {q}\n")

    # 5b — Run all optimization passes
    opt, report = optimize(code)

    sink.write(f"\nOptimization Report ({len(report)} actions):\n")
    if report:
        for line in report:
            sink.write(f"  {line}\n")
    else:
        sink.write("  (no optimizations applied)\n")

    # 5c — Final optimized TAC
    sink.write(f"\nOptimized TAC:\n")
    for i, q in enumerate(opt):
        sink.write(f"  {i:>3}: {q}\n")
    sink.write(f"\nInstructions before: {len(code)}, after: {len(opt)}\n")

    # ---------- Phase 6: Target Code ----------
    banner("PHASE 6: TARGET CODE (Register-Based Assembly)", sink)
    asm = generate_target(opt)
    for line in asm:
        indent = "" if line.startswith("LABEL") else "    "
        sink.write(indent + line + "\n")

    banner("COMPILATION SUCCESSFUL", sink)
    return True


def _dump_ast(node, sink, indent=1):
    from ast_nodes import (Program, VarDecl, Assign, Print, If, While,
                           BinOp, UnaryOp, Num, Bool, Str, Var)
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
        _dump_ast(node.left, sink, indent + 1)
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


def main():
    if len(sys.argv) < 2:
        print("Usage: python compiler.py <source_file> [-o output_file]")
        sys.exit(1)

    src_path = sys.argv[1]
    out_path = None
    if "-o" in sys.argv:
        out_path = sys.argv[sys.argv.index("-o") + 1]

    with open(src_path, "r") as f:
        src = f.read()

    import io
    buf = io.StringIO()
    buf.write(f"SimpleLang Compiler - compiling: {src_path}\n")
    compile_source(src, buf)
    result = buf.getvalue()

    print(result)
    if out_path:
        with open(out_path, "w") as f:
            f.write(result)
        print(f"\n[Output written to {out_path}]")


if __name__ == "__main__":
    main()
