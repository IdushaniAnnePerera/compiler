"""
Phase 1: Lexical Analyzer (Scanner) — Finite Automaton implementation

Implements a hand-coded DFA (Deterministic Finite Automaton) with explicit
states.  The tokenize() loop is a pure state-transition function: the current
state and the current character together determine the next state and any token
to emit.

DFA States:
    _S_START        — between tokens; initial and final accept state
    _S_ID           — inside an identifier or keyword  (alpha/_ seen)
    _S_INT          — inside an integer literal         (digit seen)
    _S_FLOAT        — inside fractional part of float   ('.' seen after digits)
    _S_FLOAT_ERR    — malformed number (second '.' seen inside float)
    _S_STR          — inside a double-quoted string literal
    _S_OP           — first character of a (possibly two-char) operator consumed
    _S_CLINE        — inside a // single-line comment
    _S_CBLK         — inside a /* ... */ block comment body
    _S_CBLK_STAR    — inside block comment, last char was '*'

Transition rules implement:
    Longest-Match Rule  : two-char operators tried before one-char
    Keyword Priority    : lexeme checked against KEYWORDS set after _S_ID
    Whitespace removal  : consumed in _S_START without emitting a token
    Comment removal     : consumed in _S_CLINE / _S_CBLK without emitting
"""

KEYWORDS = {
    "int", "float", "bool", "if", "else", "while", "for",
    "print", "begin", "end", "true", "false"
}

# ── DFA state constants ────────────────────────────────────────────────────────
_S_START      = 0
_S_ID         = 1
_S_INT        = 2
_S_FLOAT      = 3
_S_FLOAT_ERR  = 4
_S_STR        = 5
_S_OP         = 6
_S_CLINE      = 7
_S_CBLK       = 8
_S_CBLK_STAR  = 9

STATE_NAMES = {
    _S_START:     "START",
    _S_ID:        "IN_ID",
    _S_INT:       "IN_INT",
    _S_FLOAT:     "IN_FLOAT",
    _S_FLOAT_ERR: "IN_FLOAT_ERR",
    _S_STR:       "IN_STR",
    _S_OP:        "IN_OP",
    _S_CLINE:     "IN_CLINE",
    _S_CBLK:      "IN_CBLK",
    _S_CBLK_STAR: "IN_CBLK_STAR",
}


class Token:
    def __init__(self, type_, value, line, col):
        self.type  = type_
        self.value = value
        self.line  = line
        self.col   = col

    def __repr__(self):
        return f"<{self.type}, {self.value!r}, line {self.line}>"


class LexicalError(Exception):
    pass


class Lexer:
    def __init__(self, src):
        self.src    = src
        self.pos    = 0
        self.line   = 1
        self.col    = 1
        self.tokens = []
        self.errors = []

    # ── internal helpers ──────────────────────────────────────────────────────

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

    def _error(self, msg, line, col):
        self.errors.append(f"Lexical Error (line {line}, col {col}): {msg}")

    # ── DFA main loop ─────────────────────────────────────────────────────────

    def tokenize(self):
        """
        Run the DFA over self.src, producing self.tokens and self.errors.

        Each iteration reads the look-ahead character (ch = self._peek())
        without consuming it.  A state handler either:
          - Consumes ch via self._advance() and stays in / transitions to a state, or
          - Emits a token and resets to _S_START WITHOUT consuming ch,
            so ch is re-examined on the next iteration as the start of a new token.
        """
        state    = _S_START
        lexeme   = ""
        tok_line = tok_col = 1   # position where the current token started

        while True:
            ch = self._peek()    # "" at EOF

            # ── START ─────────────────────────────────────────────────────────
            if state == _S_START:
                if ch == "":
                    break                              # EOF — done

                tok_line, tok_col = self.line, self.col

                if ch in " \t\r\n":
                    self._advance()                    # discard whitespace

                elif ch.isalpha() or ch == "_":
                    lexeme = self._advance()
                    state  = _S_ID

                elif ch.isdigit():
                    lexeme = self._advance()
                    state  = _S_INT

                elif ch == '"':
                    self._advance()                    # consume opening quote
                    lexeme = ""
                    state  = _S_STR

                elif ch == "/" and self._peek(1) == "/":
                    self._advance(); self._advance()   # consume "//"
                    state = _S_CLINE

                elif ch == "/" and self._peek(1) == "*":
                    self._advance(); self._advance()   # consume "/*"
                    state = _S_CBLK

                elif ch in "+-*/=<>!&|":
                    lexeme = self._advance()
                    state  = _S_OP

                elif ch in "()[]{};,":
                    self._add("DELIM", ch, tok_line, tok_col)
                    self._advance()

                else:
                    self._error(f"Invalid symbol '{ch}'", self.line, self.col)
                    self._advance()

            # ── IN_ID ─────────────────────────────────────────────────────────
            elif state == _S_ID:
                if ch.isalnum() or ch == "_":
                    lexeme += self._advance()
                else:
                    # End of identifier: check keyword priority
                    ttype = "KEYWORD" if lexeme in KEYWORDS else "ID"
                    self._add(ttype, lexeme, tok_line, tok_col)
                    lexeme = ""
                    state  = _S_START
                    # Do NOT consume ch — re-examine in START

            # ── IN_INT ────────────────────────────────────────────────────────
            elif state == _S_INT:
                if ch.isdigit():
                    lexeme += self._advance()
                elif ch == ".":
                    # Decimal point: transition to float scanning
                    lexeme += self._advance()
                    state   = _S_FLOAT
                elif ch.isalpha() or ch == "_":
                    # Digit string immediately followed by letter => invalid identifier
                    while self._peek().isalnum() or self._peek() == "_":
                        lexeme += self._advance()
                    self._error(f"Invalid identifier '{lexeme}'", tok_line, tok_col)
                    lexeme = ""
                    state  = _S_START
                else:
                    self._add("NUMBER", int(lexeme), tok_line, tok_col)
                    lexeme = ""
                    state  = _S_START

            # ── IN_FLOAT ──────────────────────────────────────────────────────
            elif state == _S_FLOAT:
                if ch.isdigit():
                    lexeme += self._advance()
                elif ch == ".":
                    # Second decimal point => malformed
                    lexeme += self._advance()
                    state   = _S_FLOAT_ERR
                else:
                    if lexeme.endswith("."):
                        # e.g. "12." — fractional part missing
                        self._error(f"Malformed number '{lexeme}'", tok_line, tok_col)
                    else:
                        self._add("NUMBER", float(lexeme), tok_line, tok_col)
                    lexeme = ""
                    state  = _S_START

            # ── IN_FLOAT_ERR ──────────────────────────────────────────────────
            elif state == _S_FLOAT_ERR:
                if ch.isdigit() or ch == ".":
                    lexeme += self._advance()
                else:
                    self._error(f"Malformed number '{lexeme}'", tok_line, tok_col)
                    lexeme = ""
                    state  = _S_START

            # ── IN_STR ────────────────────────────────────────────────────────
            elif state == _S_STR:
                if ch == "" or ch == "\n":
                    self._error("Unterminated string literal", tok_line, tok_col)
                    if ch == "\n":
                        self._advance()
                    lexeme = ""
                    state  = _S_START
                elif ch == '"':
                    self._advance()                    # consume closing quote
                    self._add("STRING", lexeme, tok_line, tok_col)
                    lexeme = ""
                    state  = _S_START
                else:
                    lexeme += self._advance()

            # ── IN_OP ─────────────────────────────────────────────────────────
            elif state == _S_OP:
                # Longest-Match Rule: try two-char operator first.
                # ch is the NEXT character (not yet consumed).
                two = lexeme + ch               # ch may be "" at EOF
                if two in ("==", "!=", "<=", ">=", "&&", "||"):
                    self._advance()             # consume the second character
                    self._add("OP", two, tok_line, tok_col)
                else:
                    self._add("OP", lexeme, tok_line, tok_col)
                    # Do NOT consume ch — re-examine in START
                lexeme = ""
                state  = _S_START

            # ── IN_CLINE ──────────────────────────────────────────────────────
            elif state == _S_CLINE:
                if ch == "" or ch == "\n":
                    if ch == "\n":
                        self._advance()
                    state = _S_START
                else:
                    self._advance()

            # ── IN_CBLK ───────────────────────────────────────────────────────
            elif state == _S_CBLK:
                if ch == "":
                    self._error("Unterminated multi-line comment",
                                tok_line, tok_col)
                    break
                elif ch == "*":
                    self._advance()
                    state = _S_CBLK_STAR
                else:
                    self._advance()

            # ── IN_CBLK_STAR ──────────────────────────────────────────────────
            elif state == _S_CBLK_STAR:
                if ch == "/":
                    self._advance()             # consume '/' — comment closed
                    state = _S_START
                elif ch == "*":
                    self._advance()             # stay: "***/" is still valid
                elif ch == "":
                    self._error("Unterminated multi-line comment",
                                tok_line, tok_col)
                    break
                else:
                    self._advance()
                    state = _S_CBLK            # '*' was not followed by '/'

        self._add("EOF", None, self.line, self.col)
        return self.tokens, self.errors
