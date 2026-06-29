"""
Phase 1: Lexical Analyzer (Scanner)
Reads source text, produces a stream of tokens, ignores whitespace/comments,
and reports lexical errors.
"""

KEYWORDS = {
    "int", "float", "bool", "if", "else", "while", "for",
    "print", "begin", "end", "true", "false"
}


class Token:
    def __init__(self, type_, value, line, col):
        self.type = type_      # token category, e.g. KEYWORD, ID, NUMBER
        self.value = value     # the lexeme / literal value
        self.line = line
        self.col = col

    def __repr__(self):
        return f"<{self.type}, {self.value!r}, line {self.line}>"


class LexicalError(Exception):
    pass


class Lexer:
    def __init__(self, src):
        self.src = src
        self.pos = 0
        self.line = 1
        self.col = 1
        self.tokens = []
        self.errors = []

    def _peek(self, k=0):
        i = self.pos + k
        return self.src[i] if i < len(self.src) else ""

    def _advance(self):
        ch = self.src[self.pos]
        self.pos += 1
        if ch == "\n":
            self.line += 1
            self.col = 1
        else:
            self.col += 1
        return ch

    def _add(self, type_, value, line, col):
        self.tokens.append(Token(type_, value, line, col))

    def _error(self, msg, line):
        self.errors.append(f"Lexical Error (line {line}): {msg}")

    def tokenize(self):
        while self.pos < len(self.src):
            ch = self._peek()

            # whitespace (counted for lines, otherwise ignored)
            if ch in " \t\r\n":
                self._advance()
                continue

            # single-line comment  //
            if ch == "/" and self._peek(1) == "/":
                while self.pos < len(self.src) and self._peek() != "\n":
                    self._advance()
                continue

            # multi-line comment  /* ... */
            if ch == "/" and self._peek(1) == "*":
                start = self.line
                self._advance(); self._advance()
                closed = False
                while self.pos < len(self.src):
                    if self._peek() == "*" and self._peek(1) == "/":
                        self._advance(); self._advance()
                        closed = True
                        break
                    self._advance()
                if not closed:
                    self._error("Unterminated multi-line comment", start)
                continue

            line, col = self.line, self.col

            # identifiers / keywords
            if ch.isalpha() or ch == "_":
                lexeme = ""
                while self._peek().isalnum() or self._peek() == "_":
                    lexeme += self._advance()
                ttype = "KEYWORD" if lexeme in KEYWORDS else "ID"
                self._add(ttype, lexeme, line, col)
                continue

            # numbers (int or float); detect malformed numbers like 12.3.4
            if ch.isdigit():
                lexeme = ""
                dots = 0
                while self._peek().isdigit() or self._peek() == ".":
                    if self._peek() == ".":
                        dots += 1
                    lexeme += self._advance()
                if dots == 0:
                    # a letter/underscore right after digits => invalid identifier
                    if self._peek().isalpha() or self._peek() == "_":
                        bad = lexeme
                        while self._peek().isalnum() or self._peek() == "_":
                            bad += self._advance()
                        self._error(f"Invalid identifier '{bad}'", line)
                    else:
                        self._add("NUMBER", int(lexeme), line, col)
                elif dots == 1 and not lexeme.endswith("."):
                    self._add("NUMBER", float(lexeme), line, col)
                else:
                    self._error(f"Malformed number '{lexeme}'", line)
                continue

            # string literals
            if ch == '"':
                self._advance()
                s = ""
                terminated = False
                while self.pos < len(self.src):
                    c = self._peek()
                    if c == "\n":
                        break
                    if c == '"':
                        self._advance()
                        terminated = True
                        break
                    s += self._advance()
                if terminated:
                    self._add("STRING", s, line, col)
                else:
                    self._error("Unterminated string literal", line)
                continue

            # operators and delimiters (longest match first)
            two = self.src[self.pos:self.pos + 2]
            if two in ("==", "!=", "<=", ">=", "&&", "||"):
                self._advance(); self._advance()
                self._add("OP", two, line, col)
                continue

            if ch in "+-*/=<>!":
                self._advance()
                self._add("OP", ch, line, col)
                continue

            if ch in "()[]{};,":
                self._advance()
                self._add("DELIM", ch, line, col)
                continue

            # anything else is illegal
            self._error(f"Invalid symbol '{ch}'", line)
            self._advance()

        self._add("EOF", None, self.line, self.col)
        return self.tokens, self.errors
