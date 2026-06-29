"""
Phase 4: Intermediate Code Generation
Produces Three-Address Code (TAC) from the AST.
Each instruction is a tuple-like Quad: (op, arg1, arg2, result).
"""

from ast_nodes import (
    VarDecl, Assign, Print, If, While,
    BinOp, UnaryOp, Num, Bool, Str, Var,
    ArrayDecl, ArrayAccess, ArrayAssign,
)


class Quad:
    def __init__(self, op, arg1, arg2, result):
        self.op = op
        self.arg1 = arg1
        self.arg2 = arg2
        self.result = result

    def __repr__(self):
        # human-readable three-address form
        a1 = "" if self.arg1 is None else str(self.arg1)
        a2 = "" if self.arg2 is None else str(self.arg2)
        if self.op in ("+", "-", "*", "/", "<", ">", "<=", ">=",
                       "==", "!=", "&&", "||"):
            return f"{self.result} = {a1} {self.op} {a2}"
        if self.op == "=":
            return f"{self.result} = {a1}"
        if self.op == "uminus":
            return f"{self.result} = -{a1}"
        if self.op == "not":
            return f"{self.result} = !{a1}"
        if self.op == "label":
            return f"{self.result}:"
        if self.op == "goto":
            return f"goto {self.result}"
        if self.op == "ifFalse":
            return f"ifFalse {a1} goto {self.result}"
        if self.op == "print":
            return f"print {a1}"
        if self.op == "shl":
            return f"{self.result} = {a1} << {a2}"
        if self.op == "alloc_arr":
            return f"alloc_arr {a1}[{a2}]"
        if self.op == "load_arr":
            return f"{self.result} = {a1}[{a2}]"
        if self.op == "store_arr":
            # arg1=arr, arg2=idx, result=value_place
            return f"{a1}[{a2}] = {self.result}"
        return f"{self.op} {a1} {a2} {self.result}"


class IRGenerator:
    def __init__(self):
        self.code = []
        self.temp_count = 0
        self.label_count = 0

    def _new_temp(self):
        self.temp_count += 1
        return f"t{self.temp_count}"

    def _new_label(self):
        self.label_count += 1
        return f"L{self.label_count}"

    def _emit(self, op, arg1=None, arg2=None, result=None):
        self.code.append(Quad(op, arg1, arg2, result))

    def generate(self, program):
        for stmt in program.statements:
            self._stmt(stmt)
        return self.code

    def _stmt(self, node):
        if isinstance(node, VarDecl):
            if node.init is not None:
                place = self._expr(node.init)
                self._emit("=", place, None, node.name)
        elif isinstance(node, ArrayDecl):
            self._emit("alloc_arr", node.name, node.size)
        elif isinstance(node, ArrayAssign):
            idx   = self._expr(node.index)
            val   = self._expr(node.expr)
            # store_arr: arg1=array_name, arg2=index_place, result=value_place
            self._emit("store_arr", node.name, idx, val)
        elif isinstance(node, Assign):
            place = self._expr(node.expr)
            self._emit("=", place, None, node.name)
        elif isinstance(node, Print):
            place = self._expr(node.expr)
            self._emit("print", place)
        elif isinstance(node, If):
            cond = self._expr(node.cond)
            if node.else_body is None:
                end = self._new_label()
                self._emit("ifFalse", cond, None, end)
                for s in node.then_body:
                    self._stmt(s)
                self._emit("label", result=end)
            else:
                else_l = self._new_label()
                end = self._new_label()
                self._emit("ifFalse", cond, None, else_l)
                for s in node.then_body:
                    self._stmt(s)
                self._emit("goto", result=end)
                self._emit("label", result=else_l)
                for s in node.else_body:
                    self._stmt(s)
                self._emit("label", result=end)
        elif isinstance(node, While):
            start = self._new_label()
            end = self._new_label()
            self._emit("label", result=start)
            cond = self._expr(node.cond)
            self._emit("ifFalse", cond, None, end)
            for s in node.body:
                self._stmt(s)
            self._emit("goto", result=start)
            self._emit("label", result=end)

    def _expr(self, node):
        if isinstance(node, Num):
            return node.value
        if isinstance(node, Bool):
            return "true" if node.value else "false"
        if isinstance(node, Str):
            return f'"{node.value}"'
        if isinstance(node, Var):
            return node.name
        if isinstance(node, ArrayAccess):
            idx = self._expr(node.index)
            t = self._new_temp()
            # load_arr: arg1=array_name, arg2=index_place, result=dest_temp
            self._emit("load_arr", node.name, idx, t)
            return t
        if isinstance(node, UnaryOp):
            a = self._expr(node.operand)
            t = self._new_temp()
            self._emit("uminus" if node.op == "-" else "not", a, None, t)
            return t
        if isinstance(node, BinOp):
            a = self._expr(node.left)
            b = self._expr(node.right)
            t = self._new_temp()
            self._emit(node.op, a, b, t)
            return t
        return None
