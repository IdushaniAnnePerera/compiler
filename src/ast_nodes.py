"""
Abstract Syntax Tree node definitions, shared by the parser,
semantic analyzer and code generators.
"""


class Node:
    pass


class Program(Node):
    def __init__(self, statements):
        self.statements = statements


class VarDecl(Node):              # int x;   or   int x = expr;
    def __init__(self, var_type, name, init, line):
        self.var_type = var_type
        self.name = name
        self.init = init
        self.line = line


class Assign(Node):               # x = expr;
    def __init__(self, name, expr, line):
        self.name = name
        self.expr = expr
        self.line = line


class Print(Node):                # print(expr);
    def __init__(self, expr, line):
        self.expr = expr
        self.line = line


class If(Node):
    def __init__(self, cond, then_body, else_body, line):
        self.cond = cond
        self.then_body = then_body
        self.else_body = else_body
        self.line = line


class While(Node):
    def __init__(self, cond, body, line):
        self.cond = cond
        self.body = body
        self.line = line


class BinOp(Node):
    def __init__(self, op, left, right, line):
        self.op = op
        self.left = left
        self.right = right
        self.line = line


class UnaryOp(Node):
    def __init__(self, op, operand, line):
        self.op = op
        self.operand = operand
        self.line = line


class Num(Node):
    def __init__(self, value, line):
        self.value = value
        self.line = line


class Bool(Node):
    def __init__(self, value, line):
        self.value = value
        self.line = line


class Str(Node):
    def __init__(self, value, line):
        self.value = value
        self.line = line


class Var(Node):
    def __init__(self, name, line):
        self.name = name
        self.line = line
