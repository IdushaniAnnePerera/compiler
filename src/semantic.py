"""
Phase 3: Semantic Analyzer

Infrastructure
--------------
HashTable   : hand-coded hash table (DJB2 hash, separate chaining).
              Used as the backing store for every scope in the symbol table.

SymbolEntry : one symbol-table row, carrying:
              type_str — declared type (e.g. "int", "float", "int[5]")
              size     — memory footprint in bytes
                         (int=2, float=4, bool=1, string=8, array=elem*count)
              offset   — byte offset from the base of the activation record
                         (assigned sequentially for global-scope variables)

SymbolTable : scoped stack of HashTables.
              scopes[0] is the global scope; each if/while block pushes a
              fresh scope that is popped on exit.

Semantic checks
---------------
  - Scope resolution   : variables declared before use; inner scopes shadow outer
  - No duplicate declarations in the same scope
  - Type checking      : compatible operands for every operator
  - Array type safety  : element type checked on read and write
  - Array-bound check  : out-of-bounds reported for compile-time constant indices

Annotates every expression node with .vtype for downstream phases.
Array types are stored in the symbol table as "elem_type[size]" (e.g. "int[5]").
"""

from ast_nodes import (
    Program, VarDecl, Assign, Print, If, While,
    BinOp, UnaryOp, Num, Bool, Str, Var,
    ArrayDecl, ArrayAccess, ArrayAssign,
)


class SemanticError(Exception):
    pass


# ── Hand-coded Hash Table ─────────────────────────────────────────────────────

class HashTable:
    """
    Separate-chaining hash table backed by a fixed-capacity bucket array.
    Hash function: DJB2  (h = 5381; for each char: h = h*33 XOR ord(ch))
    Capacity: 64 buckets.  Each bucket is a list of (key, value) pairs.
    """
    _CAP = 64

    def __init__(self):
        self._buckets = [[] for _ in range(self._CAP)]
        self._len = 0

    def _hash(self, key):
        h = 5381
        for ch in str(key):
            h = ((h << 5) + h) ^ ord(ch)
            h &= 0xFFFFFFFF              # keep within 32 bits
        return h % self._CAP

    def __setitem__(self, key, val):
        h = self._hash(key)
        for i, (k, _) in enumerate(self._buckets[h]):
            if k == key:
                self._buckets[h][i] = (key, val)   # update existing
                return
        self._buckets[h].append((key, val))         # insert new
        self._len += 1

    def __getitem__(self, key):
        h = self._hash(key)
        for k, v in self._buckets[h]:
            if k == key:
                return v
        raise KeyError(key)

    def __contains__(self, key):
        h = self._hash(key)
        return any(k == key for k, _ in self._buckets[h])

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def items(self):
        """Yield all (key, value) pairs across all buckets."""
        for bucket in self._buckets:
            yield from bucket

    def __len__(self):
        return self._len


# ── Symbol Table Entry ────────────────────────────────────────────────────────

_TYPE_BYTES = {"int": 2, "float": 4, "bool": 1, "string": 8}


def _compute_size(type_str):
    """Return the byte size for a type string."""
    if "[" in type_str:
        elem  = type_str.split("[")[0]
        count = int(type_str.split("[")[1].rstrip("]"))
        return _TYPE_BYTES.get(elem, 2) * count
    return _TYPE_BYTES.get(type_str, 2)


class SymbolEntry:
    """One row in the symbol table (type + memory layout)."""
    __slots__ = ("type_str", "size", "offset")

    def __init__(self, type_str, offset):
        self.type_str = type_str
        self.size     = _compute_size(type_str)
        self.offset   = offset

    def __repr__(self):
        return (f"SymbolEntry(type={self.type_str!r}, "
                f"size={self.size}B, offset={self.offset})")


# ── Symbol Table (scoped) ─────────────────────────────────────────────────────

class SymbolTable:
    """
    Scoped symbol table backed by HashTable instances.

    scopes[0] is the global scope; push_scope / pop_scope bracket if/while
    blocks.  Offset tracking is done only for global-scope entries so that the
    activation-record layout is computed correctly.
    """

    def __init__(self):
        self.scopes       = [HashTable()]   # scopes[0] = global scope
        self._next_offset = 0               # next byte offset (global scope)

    def push_scope(self):
        self.scopes.append(HashTable())

    def pop_scope(self):
        if len(self.scopes) > 1:
            self.scopes.pop()

    @property
    def symbols(self):
        """Expose the global-scope HashTable (values are SymbolEntry objects)."""
        return self.scopes[0]

    @property
    def total_size(self):
        """Total bytes occupied by all global-scope variables."""
        return self._next_offset

    def declare(self, name, type_str, line):
        """Declare name in the innermost (current) scope."""
        if name in self.scopes[-1]:
            raise SemanticError(
                f"Semantic Error (line {line}): variable '{name}' already declared "
                f"in this scope"
            )
        offset = self._next_offset if len(self.scopes) == 1 else 0
        entry = SymbolEntry(type_str, offset)
        self.scopes[-1][name] = entry
        if len(self.scopes) == 1:
            self._next_offset += entry.size

    def lookup(self, name, line):
        """Return the type_str of name (searches from innermost scope out)."""
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name].type_str
        raise SemanticError(
            f"Semantic Error (line {line}): variable '{name}' used before declaration"
        )

    def lookup_entry(self, name):
        """Return the full SymbolEntry, or None if not found."""
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        return None


# ── Type helpers ──────────────────────────────────────────────────────────────

def _is_array_type(t):
    return isinstance(t, str) and "[" in t

def _elem_type(arr_type_str):
    return arr_type_str.split("[")[0]

def _array_size(arr_type_str):
    try:
        return int(arr_type_str.split("[")[1].rstrip("]"))
    except (IndexError, ValueError):
        return None


# ── Semantic Analyzer ─────────────────────────────────────────────────────────

class SemanticAnalyzer:
    def __init__(self):
        self.table  = SymbolTable()
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
        if target == "float" and value == "int":
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
