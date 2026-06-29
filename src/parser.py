"""
Phase 2: Syntax Analyzer (Parser)
A recursive-descent parser that consumes the token stream and builds an AST,
following this grammar:

    program      -> stmt*
    stmt         -> arr_decl | var_decl | arr_assign | assign
                  | print | if | while | block
    arr_decl     -> type ID '[' NUMBER ']' ';'
    var_decl     -> type ID ('=' expr)? ';'
    arr_assign   -> ID '[' expr ']' '=' expr ';'
    assign       -> ID '=' expr ';'
    print        -> 'print' '(' expr ')' ';'
    if           -> 'if' '(' expr ')' block ('else' block)?
    while        -> 'while' '(' expr ')' block
    block        -> 'begin' stmt* 'end'
    expr         -> logic_or
    logic_or     -> logic_and ('||' logic_and)*
    logic_and    -> equality ('&&' equality)*
    equality     -> relational (('=='|'!=') relational)*
    relational   -> additive (('<'|'>'|'<='|'>=') additive)*
    additive     -> term (('+'|'-') term)*
    term         -> unary (('*'|'/') unary)*
    unary        -> ('!'|'-') unary | primary
    primary      -> NUMBER | STRING | true | false
                  | ID '[' expr ']' | ID | '(' expr ')'
"""

from ast_nodes import (
    Program, VarDecl, Assign, Print, If, While,
    BinOp, UnaryOp, Num, Bool, Str, Var,
    ArrayDecl, ArrayAccess, ArrayAssign,
)

TYPES = {"int", "float", "bool"}


class SyntaxError_(Exception):
    pass


class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0
        self.errors = []

    def _cur(self):
        return self.tokens[self.pos]

    def _at(self, type_, value=None):
        t = self._cur()
        if t.type != type_:
            return False
        return value is None or t.value == value

    def _eat(self, type_, value=None):
        t = self._cur()
        if t.type == type_ and (value is None or t.value == value):
            self.pos += 1
            return t
        want = value if value is not None else type_
        raise SyntaxError_(
            f"Syntax Error (line {t.line}): expected '{want}' but found '{t.value}'"
        )

    def parse(self):
        """Parse the whole program.

        Uses PANIC-MODE error recovery (Lecture 3): when a syntax error is
        found, the error is reported, then the parser skips input up to the
        next delimiter (a ';' or 'end') and resumes, so that several errors
        can be reported in a single run instead of stopping at the first.
        """
        statements = []
        while not self._at("EOF"):
            try:
                statements.append(self._statement())
            except SyntaxError_ as e:
                self.errors.append(str(e))
                self._panic_recover()
        return Program(statements), self.errors

    def _panic_recover(self):
        """Skip tokens until past a ';' or up to 'end'/EOF, then resume."""
        start = self.pos
        skipped = []
        while not self._at("EOF"):
            t = self._cur()
            if t.type == "DELIM" and t.value == ";":
                self.pos += 1          # consume the ';' and resume after it
                break
            if t.type == "KEYWORD" and t.value == "end":
                break                  # stop before 'end'; resume there
            skipped.append(str(t.value))
            self.pos += 1
        # guarantee forward progress so we can never loop forever
        if self.pos == start and not self._at("EOF"):
            self.pos += 1
        near = skipped[0] if skipped else "next statement"
        self.errors.append(
            f"  --> Panic-mode recovery near '{near}': skipped to delimiter, "
            f"resuming parsing.")

    # ---- statements ----
    def _statement(self):
        t = self._cur()
        if t.type == "KEYWORD" and t.value in TYPES:
            return self._var_decl()
        if t.type == "KEYWORD" and t.value == "print":
            return self._print()
        if t.type == "KEYWORD" and t.value == "if":
            return self._if()
        if t.type == "KEYWORD" and t.value == "while":
            return self._while()
        if t.type == "KEYWORD" and t.value == "begin":
            return self._block()
        if t.type == "ID":
            return self._assign()
        raise SyntaxError_(
            f"Syntax Error (line {t.line}): unexpected token '{t.value}'"
        )

    def _var_decl(self):
        ttok = self._eat("KEYWORD")
        name = self._eat("ID").value
        if self._at("DELIM", "["):
            self._eat("DELIM", "[")
            size_tok = self._eat("NUMBER")
            if not isinstance(size_tok.value, int) or size_tok.value <= 0:
                raise SyntaxError_(
                    f"Syntax Error (line {size_tok.line}): "
                    f"array size must be a positive integer"
                )
            self._eat("DELIM", "]")
            self._eat("DELIM", ";")
            return ArrayDecl(ttok.value, name, size_tok.value, ttok.line)
        init = None
        if self._at("OP", "="):
            self._eat("OP", "=")
            init = self._expr()
        self._eat("DELIM", ";")
        return VarDecl(ttok.value, name, init, ttok.line)

    def _assign(self):
        name_tok = self._eat("ID")
        if self._at("DELIM", "["):
            self._eat("DELIM", "[")
            index = self._expr()
            self._eat("DELIM", "]")
            self._eat("OP", "=")
            expr = self._expr()
            self._eat("DELIM", ";")
            return ArrayAssign(name_tok.value, index, expr, name_tok.line)
        self._eat("OP", "=")
        expr = self._expr()
        self._eat("DELIM", ";")
        return Assign(name_tok.value, expr, name_tok.line)

    def _print(self):
        ptok = self._eat("KEYWORD", "print")
        self._eat("DELIM", "(")
        expr = self._expr()
        self._eat("DELIM", ")")
        self._eat("DELIM", ";")
        return Print(expr, ptok.line)

    def _block(self):
        self._eat("KEYWORD", "begin")
        stmts = []
        while not self._at("KEYWORD", "end"):
            if self._at("EOF"):
                raise SyntaxError_("Syntax Error: missing 'end' for 'begin' block")
            stmts.append(self._statement())
        self._eat("KEYWORD", "end")
        return stmts

    def _if(self):
        itok = self._eat("KEYWORD", "if")
        self._eat("DELIM", "(")
        cond = self._expr()
        self._eat("DELIM", ")")
        then_body = self._block()
        else_body = None
        if self._at("KEYWORD", "else"):
            self._eat("KEYWORD", "else")
            else_body = self._block()
        return If(cond, then_body, else_body, itok.line)

    def _while(self):
        wtok = self._eat("KEYWORD", "while")
        self._eat("DELIM", "(")
        cond = self._expr()
        self._eat("DELIM", ")")
        body = self._block()
        return While(cond, body, wtok.line)

    # ---- expressions (precedence climbing) ----
    def _expr(self):
        return self._logic_or()

    def _logic_or(self):
        node = self._logic_and()
        while self._at("OP", "||"):
            op = self._eat("OP").value
            node = BinOp(op, node, self._logic_and(), node.line)
        return node

    def _logic_and(self):
        node = self._equality()
        while self._at("OP", "&&"):
            op = self._eat("OP").value
            node = BinOp(op, node, self._equality(), node.line)
        return node

    def _equality(self):
        node = self._relational()
        while self._at("OP", "==") or self._at("OP", "!="):
            op = self._eat("OP").value
            node = BinOp(op, node, self._relational(), node.line)
        return node

    def _relational(self):
        node = self._additive()
        while any(self._at("OP", o) for o in ("<", ">", "<=", ">=")):
            op = self._eat("OP").value
            node = BinOp(op, node, self._additive(), node.line)
        return node

    def _additive(self):
        node = self._term()
        while self._at("OP", "+") or self._at("OP", "-"):
            op = self._eat("OP").value
            node = BinOp(op, node, self._term(), node.line)
        return node

    def _term(self):
        node = self._unary()
        while self._at("OP", "*") or self._at("OP", "/"):
            op = self._eat("OP").value
            node = BinOp(op, node, self._unary(), node.line)
        return node

    def _unary(self):
        if self._at("OP", "!") or self._at("OP", "-"):
            op_tok = self._eat("OP")
            return UnaryOp(op_tok.value, self._unary(), op_tok.line)
        return self._primary()

    def _primary(self):
        t = self._cur()
        if t.type == "NUMBER":
            self.pos += 1
            return Num(t.value, t.line)
        if t.type == "STRING":
            self.pos += 1
            return Str(t.value, t.line)
        if t.type == "KEYWORD" and t.value in ("true", "false"):
            self.pos += 1
            return Bool(t.value == "true", t.line)
        if t.type == "ID":
            name = t.value
            self.pos += 1
            if self._at("DELIM", "["):
                self._eat("DELIM", "[")
                index = self._expr()
                self._eat("DELIM", "]")
                return ArrayAccess(name, index, t.line)
            return Var(name, t.line)
        if self._at("DELIM", "("):
            self._eat("DELIM", "(")
            node = self._expr()
            self._eat("DELIM", ")")
            return node
        raise SyntaxError_(
            f"Syntax Error (line {t.line}): unexpected token '{t.value}' in expression"
        )
