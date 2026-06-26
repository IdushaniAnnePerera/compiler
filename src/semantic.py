"""
Phase 3: Semantic Analyzer
Walks the AST, builds a symbol table, and checks:
  - variables declared before use
  - no duplicate declarations
  - type compatibility in assignments and operations
  - conditions in if/while must be boolean
Annotates expression nodes with an inferred .vtype for later phases.
"""

from ast_nodes import (
    Program, VarDecl, Assign, Print, If, While,
    BinOp, UnaryOp, Num, Bool, Str, Var
)


class SemanticError(Exception):
    pass


class SymbolTable:
    def __init__(self):
        self.symbols = {}   # name -> type

    def declare(self, name, type_, line):
        if name in self.symbols:
            raise SemanticError(
                f"Semantic Error (line {line}): variable '{name}' already declared"
            )
        self.symbols[name] = type_

    def lookup(self, name, line):
        if name not in self.symbols:
            raise SemanticError(
                f"Semantic Error (line {line}): variable '{name}' used before declaration"
            )
        return self.symbols[name]


class SemanticAnalyzer:
    def __init__(self):
        self.table = SymbolTable()
        self.errors = []

    def analyze(self, program):
        for stmt in program.statements:
            self._stmt(stmt)
        return self.table, self.errors

    def _stmt(self, node):
        try:
            if isinstance(node, VarDecl):
                self.table.declare(node.name, node.var_type, node.line)
                if node.init is not None:
                    t = self._expr(node.init)
                    self._check_assignable(node.var_type, t, node.name, node.line)
            elif isinstance(node, Assign):
                declared = self.table.lookup(node.name, node.line)
                t = self._expr(node.expr)
                self._check_assignable(declared, t, node.name, node.line)
            elif isinstance(node, Print):
                self._expr(node.expr)
            elif isinstance(node, If):
                ct = self._expr(node.cond)
                if ct != "bool":
                    self.errors.append(
                        f"Semantic Error (line {node.line}): if-condition must be bool, got {ct}")
                for s in node.then_body:
                    self._stmt(s)
                if node.else_body:
                    for s in node.else_body:
                        self._stmt(s)
            elif isinstance(node, While):
                ct = self._expr(node.cond)
                if ct != "bool":
                    self.errors.append(
                        f"Semantic Error (line {node.line}): while-condition must be bool, got {ct}")
                for s in node.body:
                    self._stmt(s)
        except SemanticError as e:
            self.errors.append(str(e))

    def _check_assignable(self, target, value, name, line):
        if target == value:
            return
        if target == "float" and value == "int":   # int -> float widening ok
            return
        self.errors.append(
            f"Semantic Error (line {line}): cannot assign {value} to "
            f"{target} variable '{name}'")

    def _expr(self, node):
        if isinstance(node, Num):
            node.vtype = "float" if isinstance(node.value, float) else "int"
        elif isinstance(node, Bool):
            node.vtype = "bool"
        elif isinstance(node, Str):
            node.vtype = "string"
        elif isinstance(node, Var):
            node.vtype = self.table.lookup(node.name, node.line)
        elif isinstance(node, UnaryOp):
            t = self._expr(node.operand)
            if node.op == "!" and t != "bool":
                self.errors.append(
                    f"Semantic Error (line {node.line}): '!' needs bool, got {t}")
            if node.op == "-" and t not in ("int", "float"):
                self.errors.append(
                    f"Semantic Error (line {node.line}): unary '-' needs number, got {t}")
            node.vtype = "bool" if node.op == "!" else t
        elif isinstance(node, BinOp):
            lt = self._expr(node.left)
            rt = self._expr(node.right)
            node.vtype = self._binop_type(node.op, lt, rt, node.line)
        else:
            node.vtype = "unknown"
        return node.vtype

    def _binop_type(self, op, lt, rt, line):
        arith = {"+", "-", "*", "/"}
        rel = {"<", ">", "<=", ">=", "==", "!="}
        logic = {"&&", "||"}
        if op in arith:
            if lt in ("int", "float") and rt in ("int", "float"):
                return "float" if "float" in (lt, rt) else "int"
            self.errors.append(
                f"Semantic Error (line {line}): operator '{op}' needs numbers, got {lt},{rt}")
            return "int"
        if op in rel:
            if lt != rt and not (lt in ("int", "float") and rt in ("int", "float")):
                self.errors.append(
                    f"Semantic Error (line {line}): cannot compare {lt} with {rt}")
            return "bool"
        if op in logic:
            if lt != "bool" or rt != "bool":
                self.errors.append(
                    f"Semantic Error (line {line}): operator '{op}' needs bool operands")
            return "bool"
        return "unknown"
