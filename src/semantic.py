"""
Phase 3: Semantic Analyzer

Walks the AST, builds a scoped symbol table, and checks:
  - Scope resolution   : variables declared before use; inner scopes shadow outer
  - No duplicate declarations in the same scope
  - Type checking      : type compatibility in assignments, arithmetic, relational,
                         logical, and unary operations; if/while conditions must be bool
  - Array type safety  : array element type checked on read and write
  - Array-bound checking: out-of-bounds access reported when the index is a
                          compile-time integer constant

Annotates expression nodes with an inferred .vtype for later phases.
Array types are stored in the symbol table as the string  "elem_type[size]"
(e.g. "int[5]") so the display in compiler.py stays format-compatible.
"""

from ast_nodes import (
    Program, VarDecl, Assign, Print, If, While,
    BinOp, UnaryOp, Num, Bool, Str, Var,
    ArrayDecl, ArrayAccess, ArrayAssign,
)


class SemanticError(Exception):
    pass


# ── Symbol Table (scoped) ─────────────────────────────────────────────────────

class SymbolTable:
    """Stack of dicts; each dict is one lexical scope.
    scopes[0] is the global (outermost) scope."""

    def __init__(self):
        self.scopes = [{}]

    def push_scope(self):
        self.scopes.append({})

    def pop_scope(self):
        if len(self.scopes) > 1:
            self.scopes.pop()

    @property
    def symbols(self):
        """Expose the global scope for display (block-scoped vars are popped)."""
        return self.scopes[0]

    def declare(self, name, type_str, line):
        """Declare in the innermost (current) scope only."""
        if name in self.scopes[-1]:
            raise SemanticError(
                f"Semantic Error (line {line}): variable '{name}' already declared "
                f"in this scope"
            )
        self.scopes[-1][name] = type_str

    def lookup(self, name, line):
        """Search from innermost to outermost scope."""
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        raise SemanticError(
            f"Semantic Error (line {line}): variable '{name}' used before declaration"
        )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_array_type(t):
    return isinstance(t, str) and "[" in t

def _elem_type(arr_type_str):
    """Extract element type from "int[5]" -> "int"."""
    return arr_type_str.split("[")[0]

def _array_size(arr_type_str):
    """Extract declared size from "int[5]" -> 5."""
    try:
        return int(arr_type_str.split("[")[1].rstrip("]"))
    except (IndexError, ValueError):
        return None


# ── Semantic Analyzer ─────────────────────────────────────────────────────────

class SemanticAnalyzer:
    def __init__(self):
        self.table = SymbolTable()
        self.errors = []

    def analyze(self, program):
        for stmt in program.statements:
            self._stmt(stmt)
        return self.table, self.errors

    # ── statements ──────────────────────────────────────────────────────────

    def _stmt(self, node):
        try:
            if isinstance(node, VarDecl):
                self.table.declare(node.name, node.var_type, node.line)
                if node.init is not None:
                    t = self._expr(node.init)
                    self._check_assignable(node.var_type, t, node.name, node.line)

            elif isinstance(node, ArrayDecl):
                if node.size <= 0:
                    self.errors.append(
                        f"Semantic Error (line {node.line}): array '{node.name}' "
                        f"size must be positive, got {node.size}"
                    )
                arr_type = f"{node.var_type}[{node.size}]"
                self.table.declare(node.name, arr_type, node.line)

            elif isinstance(node, Assign):
                declared = self.table.lookup(node.name, node.line)
                if _is_array_type(declared):
                    self.errors.append(
                        f"Semantic Error (line {node.line}): '{node.name}' is an "
                        f"array; use '{node.name}[index] = ...' for element assignment"
                    )
                else:
                    t = self._expr(node.expr)
                    self._check_assignable(declared, t, node.name, node.line)

            elif isinstance(node, ArrayAssign):
                declared = self.table.lookup(node.name, node.line)
                if not _is_array_type(declared):
                    self.errors.append(
                        f"Semantic Error (line {node.line}): '{node.name}' is not "
                        f"an array"
                    )
                else:
                    elem = _elem_type(declared)
                    size = _array_size(declared)
                    idx_t = self._expr(node.index)
                    if idx_t not in ("int",):
                        self.errors.append(
                            f"Semantic Error (line {node.line}): array index must "
                            f"be int, got {idx_t}"
                        )
                    # Compile-time bounds check
                    if isinstance(node.index, Num) and size is not None:
                        idx_val = int(node.index.value)
                        if not (0 <= idx_val < size):
                            self.errors.append(
                                f"Semantic Error (line {node.line}): array "
                                f"'{node.name}' index {idx_val} out of bounds "
                                f"[0..{size - 1}]"
                            )
                    val_t = self._expr(node.expr)
                    self._check_assignable(elem, val_t, f"{node.name}[...]", node.line)

            elif isinstance(node, Print):
                self._expr(node.expr)

            elif isinstance(node, If):
                ct = self._expr(node.cond)
                if ct != "bool":
                    self.errors.append(
                        f"Semantic Error (line {node.line}): if-condition must be "
                        f"bool, got {ct}"
                    )
                self.table.push_scope()
                try:
                    for s in node.then_body:
                        self._stmt(s)
                finally:
                    self.table.pop_scope()
                if node.else_body:
                    self.table.push_scope()
                    try:
                        for s in node.else_body:
                            self._stmt(s)
                    finally:
                        self.table.pop_scope()

            elif isinstance(node, While):
                ct = self._expr(node.cond)
                if ct != "bool":
                    self.errors.append(
                        f"Semantic Error (line {node.line}): while-condition must "
                        f"be bool, got {ct}"
                    )
                self.table.push_scope()
                try:
                    for s in node.body:
                        self._stmt(s)
                finally:
                    self.table.pop_scope()

        except SemanticError as e:
            self.errors.append(str(e))

    # ── type-compatibility check ─────────────────────────────────────────────

    def _check_assignable(self, target, value, name, line):
        if _is_array_type(target):
            self.errors.append(
                f"Semantic Error (line {line}): cannot assign to array '{name}' "
                f"directly; use index notation"
            )
            return
        if target == value:
            return
        if target == "float" and value == "int":   # int -> float widening
            return
        self.errors.append(
            f"Semantic Error (line {line}): cannot assign {value} to "
            f"{target} variable '{name}'"
        )

    # ── expressions ──────────────────────────────────────────────────────────

    def _expr(self, node):
        if isinstance(node, Num):
            node.vtype = "float" if isinstance(node.value, float) else "int"

        elif isinstance(node, Bool):
            node.vtype = "bool"

        elif isinstance(node, Str):
            node.vtype = "string"

        elif isinstance(node, Var):
            declared = self.table.lookup(node.name, node.line)
            if _is_array_type(declared):
                self.errors.append(
                    f"Semantic Error (line {node.line}): '{node.name}' is an array; "
                    f"use '{node.name}[index]' to read an element"
                )
                node.vtype = _elem_type(declared)
            else:
                node.vtype = declared

        elif isinstance(node, ArrayAccess):
            declared = self.table.lookup(node.name, node.line)
            if not _is_array_type(declared):
                self.errors.append(
                    f"Semantic Error (line {node.line}): '{node.name}' is not an array"
                )
                node.vtype = "unknown"
            else:
                elem = _elem_type(declared)
                size = _array_size(declared)
                idx_t = self._expr(node.index)
                if idx_t not in ("int",):
                    self.errors.append(
                        f"Semantic Error (line {node.line}): array index must be "
                        f"int, got {idx_t}"
                    )
                # Compile-time bounds check
                if isinstance(node.index, Num) and size is not None:
                    idx_val = int(node.index.value)
                    if not (0 <= idx_val < size):
                        self.errors.append(
                            f"Semantic Error (line {node.line}): array "
                            f"'{node.name}' index {idx_val} out of bounds "
                            f"[0..{size - 1}]"
                        )
                node.vtype = elem

        elif isinstance(node, UnaryOp):
            t = self._expr(node.operand)
            if node.op == "!" and t != "bool":
                self.errors.append(
                    f"Semantic Error (line {node.line}): '!' needs bool, got {t}"
                )
            if node.op == "-" and t not in ("int", "float"):
                self.errors.append(
                    f"Semantic Error (line {node.line}): unary '-' needs number, "
                    f"got {t}"
                )
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
        rel   = {"<", ">", "<=", ">=", "==", "!="}
        logic = {"&&", "||"}

        if op in arith:
            if lt in ("int", "float") and rt in ("int", "float"):
                return "float" if "float" in (lt, rt) else "int"
            self.errors.append(
                f"Semantic Error (line {line}): operator '{op}' needs numbers, "
                f"got {lt},{rt}"
            )
            return "int"

        if op in rel:
            if lt != rt and not (lt in ("int", "float") and rt in ("int", "float")):
                self.errors.append(
                    f"Semantic Error (line {line}): cannot compare {lt} with {rt}"
                )
            return "bool"

        if op in logic:
            if lt != "bool" or rt != "bool":
                self.errors.append(
                    f"Semantic Error (line {line}): operator '{op}' needs bool "
                    f"operands"
                )
            return "bool"

        return "unknown"
