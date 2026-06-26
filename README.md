# SimpleLang — A Full Compiler (All Phases)

**Course:** COSC 44283 — Theory of Compilers
**Deliverable:** Design & implementation of a complete compiler for a simple
programming language, covering every phase of compilation.

This project implements a complete compiler **front-end and back-end** for a
small custom language called **SimpleLang**, written in pure Python (no external
libraries, no build tools — just Python 3).

---

## 1. The Six Phases Implemented

| Phase | Name                         | File              | What it does |
|-------|------------------------------|-------------------|--------------|
| 1     | Lexical Analysis             | `src/lexer.py`    | Reads source text, produces tokens, ignores whitespace/comments, reports lexical errors |
| 2     | Syntax Analysis (Parsing)    | `src/parser.py`   | Recursive-descent parser builds an Abstract Syntax Tree (AST) |
| 3     | Semantic Analysis            | `src/semantic.py` | Symbol table, declaration checks, type checking |
| 4     | Intermediate Code Generation | `src/ir_gen.py`   | Generates Three-Address Code (TAC) |
| 5     | Code Optimization            | `src/optimizer.py`| Constant folding/propagation, algebraic simplification, dead-code removal |
| 6     | Target Code Generation       | `src/codegen.py`  | Emits **register-based** assembly (`MOV`, `ADD`, `R1`, `R2` …), matching the register model in Lecture 7 |

`src/compiler.py` is the driver that runs all six phases in a pipeline.
`src/ast_nodes.py` holds the shared AST node definitions.

### Alignment with the course lectures
- **Phase 2 uses panic-mode error recovery** (Lecture 3): on a syntax error the
  parser reports it, skips to the next delimiter (`;` or `end`), and resumes —
  so several syntax errors are caught in one run instead of stopping at the
  first. (Lecture 3 lists four strategies: panic mode, statement mode, error
  productions, global correction; this implements panic mode, "the easiest way
  of error-recovery".)
- **Phase 6 produces register-based target code** (Lecture 7), where the
  three-address temporaries `t1, t2, …` are mapped onto target registers
  `R1, R2, …`, exactly as the lecture's example (`r1 = c * d; r2 = b + r1;`)
  describes "r being used as registers in the target program."

---

## 2. The SimpleLang Language

### Token categories (recognised by the lexer)
- **Keywords:** `int float bool if else while for print begin end true false`
- **Identifiers:** begin with a letter or `_`, then letters/digits/`_`
- **Numeric constants:** integers (`10`, `0`) and floats (`3.14`)
- **String literals:** `"Hello"`
- **Operators:** arithmetic `+ - * /`, assignment `=`, relational `== != < > <= >=`, logical `&& || !`
- **Delimiters:** `; , ( ) { }`
- **Comments:** single-line `// ...` and multi-line `/* ... */`

### Grammar (used by the parser)
```
program     -> stmt*
stmt        -> var_decl | assign | print | if | while | block
var_decl    -> type ID ('=' expr)? ';'
assign      -> ID '=' expr ';'
print       -> 'print' '(' expr ')' ';'
if          -> 'if' '(' expr ')' block ('else' block)?
while       -> 'while' '(' expr ')' block
block       -> 'begin' stmt* 'end'
expr        -> logic_or
logic_or    -> logic_and ('||' logic_and)*
logic_and   -> equality ('&&' equality)*
equality    -> relational (('=='|'!=') relational)*
relational  -> additive (('<'|'>'|'<='|'>=') additive)*
additive    -> term (('+'|'-') term)*
term        -> unary (('*'|'/') unary)*
unary       -> ('!'|'-') unary | primary
primary     -> NUMBER | STRING | true | false | ID | '(' expr ')'
```

A sample valid program:
```
int a = 5;
int b = 10;
int sum;
sum = a + b * 2;
if (a < b) begin
    print("a is smaller");
end else begin
    print("a is bigger");
end
```

---

## 3. Project Structure
```
SimpleCompiler/
├── README.md
├── src/
│   ├── compiler.py      <- run this
│   ├── lexer.py         (Phase 1)
│   ├── parser.py        (Phase 2)
│   ├── ast_nodes.py
│   ├── semantic.py      (Phase 3)
│   ├── ir_gen.py        (Phase 4)
│   ├── optimizer.py     (Phase 5)
│   └── codegen.py       (Phase 6)
├── tests/               <- sample input programs (.sl)
│   ├── test1_valid.sl        (a correct program, all constructs)
│   ├── test2_optimize.sl     (shows the optimizer working)
│   ├── test3_lex_error.sl    (lexical errors)
│   ├── test4_sem_error.sl    (semantic errors)
│   └── test5_syntax_recovery.sl  (panic-mode error recovery)
└── output/              <- generated reports (one .txt per test)
```

---

## 4. How to Run It (Simple Guide — Windows)

You only need **Python 3** installed. No packages to install.

### Step 1 — open a terminal (PowerShell or CMD) in the project folder
```
cd SimpleCompiler
```

### Step 2 — compile a source file
Print all six phases to the screen (note the **backslashes** in Windows paths):
```
python src\compiler.py tests\test1_valid.sl
```
If `python` isn't recognised, use `py` instead:
```
py src\compiler.py tests\test1_valid.sl
```

### Step 3 — save the report to a file (optional)
```
python src\compiler.py tests\test1_valid.sl -o output\test1_valid_output.txt
```

### Step 4 — try the other tests
```
python src\compiler.py tests\test2_optimize.sl          # watch Phase 5 shrink the code
python src\compiler.py tests\test3_lex_error.sl         # lexical errors reported
python src\compiler.py tests\test4_sem_error.sl         # semantic errors reported
python src\compiler.py tests\test5_syntax_recovery.sl   # panic-mode error recovery
```

### Step 5 — write your own program
Create a file `myprog.sl`, then:
```
python src\compiler.py myprog.sl
```

> On macOS/Linux, use `python3` and forward slashes (e.g. `tests/test1_valid.sl`).

---

## 5. What You Will See

For a **valid** program the output prints, in order:
1. the **token table** (Phase 1),
2. the **AST** (Phase 2),
3. the **symbol table** + "No semantic errors" (Phase 3),
4. the **three-address code** (Phase 4),
5. the **optimized** three-address code with a before/after count (Phase 5),
6. the **target stack-machine assembly** (Phase 6),
7. `COMPILATION SUCCESSFUL`.

For a program with **errors**, the pipeline stops at the failing phase and prints
a clear, line-numbered error report — for example:
```
Lexical Error (line 2): Invalid identifier '2name'
Lexical Error (line 4): Unterminated string literal
Semantic Error (line 3): variable 'a' already declared
```

Pre-generated reports for all four tests are in the `output/` folder.
