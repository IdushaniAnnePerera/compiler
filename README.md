# SimpleLang Compiler — Full Six-Phase Implementation

**Course:** COSC 44283 — Theory of Compilers  
**Language:** Python 3 (no external libraries, no build tools)  
**Architecture:** Register-based code generation with explicit Activation Record

---

## 1. Six-Phase Compiler Pipeline

| # | Phase | File | Implementation |
|---|-------|------|---------------|
| 1 | Lexical Analysis | `src/lexer.py` | Hand-coded DFA — 10 explicit states |
| 2 | Syntax Analysis | `src/parser.py` | Recursive-descent LL(1) parser with panic-mode recovery |
| 3 | Semantic Analysis | `src/semantic.py` | Hand-coded HashTable symbol table; type checking; scope stack |
| 4 | IR Generation | `src/ir_gen.py` | Three-Address Code (TAC) as Quad(op, arg1, arg2, result) |
| 5 | Optimization | `src/optimizer.py` | 9 passes; CFG; DAG-based CSE; backward liveness analysis |
| 6 | Code Generation | `src/codegen.py` | Register-based assembly; Address Descriptor; Activation Record |

`src/compiler.py` drives the full pipeline. `src/ast_nodes.py` holds AST node definitions.

---

## 2. Phase 1 — Lexical Analysis: Hand-Coded DFA

The tokenizer is implemented as a **Deterministic Finite Automaton (DFA)** — a `while True` loop whose only input is the current character and whose only output is a state transition or a token emission. No regular-expression library is used.

### DFA States (10 total)

| Constant | Value | Meaning |
|----------|-------|---------|
| `_S_START` | 0 | Between tokens — initial and accepting state |
| `_S_ID` | 1 | Inside an identifier or keyword (`alpha` or `_` seen) |
| `_S_INT` | 2 | Inside an integer literal (digit seen) |
| `_S_FLOAT` | 3 | Inside the fractional part of a float (`.` seen after digits) |
| `_S_FLOAT_ERR` | 4 | Malformed number (second `.` seen inside a float) |
| `_S_STR` | 5 | Inside a double-quoted string literal |
| `_S_OP` | 6 | First character of a (possibly two-character) operator consumed |
| `_S_CLINE` | 7 | Inside a `//` single-line comment |
| `_S_CBLK` | 8 | Inside a `/* … */` block-comment body |
| `_S_CBLK_STAR` | 9 | Inside block comment, last character was `*` |

### Key DFA Design Decisions
- **Longest-match rule** for operators: in `_S_OP`, the look-ahead character is peeked (not consumed) and the two-character string `lexeme + ch` is tested against `{"==","!=","<=",">=","&&","||"}` before the single-character operator is emitted.
- **Keyword priority**: after `_S_ID` accepts (non-alphanumeric seen), the completed lexeme is looked up in the `KEYWORDS` set — if found, a `KEYWORD` token is emitted instead of an `ID` token.
- **Non-consuming transitions**: when a state emits a token it resets to `_S_START` *without* advancing the position, so the current character is re-examined as the first character of the next token.
- **Error recovery**: invalid characters and malformed numbers are reported with line and column numbers; the DFA resets to `_S_START` and continues scanning.

### Token Categories

| Category | Examples |
|----------|---------|
| `KEYWORD` | `int float bool if else while for print begin end true false` |
| `ID` | `x`, `sum`, `_count` |
| `NUMBER` | `10` (int), `3.14` (float) |
| `STRING` | `"hello"` |
| `OP` | `+ - * / = == != < > <= >= && \|\| !` |
| `DELIM` | `; , ( ) [ ] { }` |
| `EOF` | end of input |

---

## 3. Phase 2 — Syntax Analysis: Recursive-Descent Parser

The parser is a hand-written **predictive recursive-descent (LL(1))** parser. Each non-terminal in the grammar has a corresponding method that reads the token stream and builds an AST node.

### Grammar

```
program     -> stmt*
stmt        -> var_decl | assign | if | while | print | block
var_decl    -> type ID ('=' expr)? ';'
assign      -> ID ('[' expr ']')? '=' expr ';'
print       -> 'print' '(' expr ')' ';'
if          -> 'if' '(' expr ')' block ('else' block)?
while       -> 'while' '(' expr ')' block
block       -> 'begin' stmt* 'end'
type        -> 'int' | 'float' | 'bool' | 'int' '[' NUMBER ']' | etc.
expr        -> logic_or
logic_or    -> logic_and ('||' logic_and)*
logic_and   -> equality  ('&&' equality)*
equality    -> relational (('=='|'!=') relational)*
relational  -> additive   (('<'|'>'|'<='|'>=') additive)*
additive    -> term (('+'|'-') term)*
term        -> unary (('*'|'/') unary)*
unary       -> ('!'|'-') unary | primary
primary     -> NUMBER | STRING | 'true' | 'false' | ID ('[' expr ']')? | '(' expr ')'
```

Operator precedence is encoded directly in the grammar hierarchy: `||` binds least tightly; `!` and unary `-` bind most tightly among binary/unary ops.

### Panic-Mode Error Recovery (Lecture 3)

On a syntax error the parser:
1. Reports the error with line number.
2. Skips tokens until it finds a synchronisation point (`;` or `end`).
3. Resumes parsing from that point.

This allows multiple syntax errors to be reported in a single compilation run. (Lecture 3 describes four strategies — panic mode, statement mode, error productions, global correction; this compiler uses panic mode, the simplest.)

---

## 4. Phase 3 — Semantic Analysis: Hand-Coded Symbol Table

### HashTable (DJB2 — no Python `dict`)

```
Capacity : 64 buckets
Hash     : DJB2 — h = 5381; for each character: h = ((h << 5) + h) XOR ord(c); h &= 0xFFFFFFFF
Collision: Separate chaining (each bucket is a list of (key, value) pairs)
```

All symbol lookups and insertions run in O(1) average time.

### SymbolEntry

Each declared variable is stored as a `SymbolEntry` with three fields:

| Field | Description |
|-------|-------------|
| `type_str` | The declared type as a string: `"int"`, `"float"`, `"bool"`, `"string"`, or `"int[N]"` |
| `size` | Size in bytes: `int`=2, `float`=4, `bool`=1, `string`=8, array=element-size × count |
| `offset` | Byte offset from the Activation Record base (cumulative, assigned at declaration) |

### Scope Stack

Scopes are managed as a stack of `HashTable` objects:
- A new scope is pushed at every `begin` (block entry).
- It is popped at the matching `end` (block exit) — so variables declared inside a block are not visible after the block closes.
- Name lookup walks from the innermost scope outward (supports shadowing: an inner variable with the same name as an outer one hides it within its block).

### Checks Performed

- Duplicate declaration in the same scope
- Use of undeclared variable
- Type mismatch in assignment and operations
- Non-boolean condition in `if` / `while`
- Compile-time array index out-of-bounds (when index is a literal)

---

## 5. Phase 4 — Intermediate Code Generation (TAC)

Intermediate Representation: **Three-Address Code (TAC)**, represented as `Quad(op, arg1, arg2, result)`.

### Quad Opcodes

| Category | Opcodes |
|----------|---------|
| Arithmetic | `+  -  *  /` |
| Unary | `neg  not` |
| Relational | `<  >  <=  >=  ==  !=` |
| Logical | `&&  \|\|` |
| Copy | `=` |
| Control | `goto  ifFalse  label` |
| Array | `alloc_arr  load_arr  store_arr` |
| Print | `print` |

Temporaries are named `t0, t1, t2, …`; labels are `L0, L1, L2, …`.

`if/else` generates two labels (true branch, end); `while` generates a loop-top label and a loop-exit label.

---

## 6. Phase 5 — Optimization (9 Passes)

### Control-Flow Graph (CFG)

Before optimisation the TAC is split into **basic blocks** (maximal sequences with no internal branches). A `CFGNode` holds:
- `block_id` — integer index
- `quads` — the list of `Quad` objects in this block
- `successors` / `predecessors` — lists of adjacent `CFGNode` objects (set bidirectionally when the CFG is built)

### DAG (Directed Acyclic Graph) — CSE Detection

A DAG is built per basic block to detect **Common Subexpressions (CSE)**:
- Leaf nodes represent constants and variable references.
- Interior nodes represent computations `(op, left_uid, right_uid)`.
- When a new computation matches an existing node's key, it is a CSE (`cse_count` incremented); the existing node's result is reused instead of creating a duplicate.

### Backward Liveness Analysis

**Live variables** at each point are computed by a fixed-point backward data-flow iteration over the CFG:

```
live_out[B] = ∪ live_in[S]  for each successor S of B
live_in[B]  = use[B] ∪ (live_out[B] − def[B])
```

The iteration repeats until no `live_in` or `live_out` set changes. Results are used by Dead Code Elimination (DCE).

### The 9 Optimisation Passes (applied in order)

| # | Pass | What it does |
|---|------|-------------|
| 1 | Constant Folding | Evaluates constant expressions at compile time: `2 + 3` → `5` |
| 2 | Constant Propagation | Replaces variable uses with their known constant values |
| 3 | Algebraic Simplification | `x * 1` → `x`, `x + 0` → `x`, `x * 0` → `0` |
| 4 | Strength Reduction | `x * 2` → `x << 1`, `x * 4` → `x << 2`, `x * 8` → `x << 3` |
| 5 | Loop-Invariant Code Motion | Moves computations that do not change inside a loop to before the loop |
| 6 | Induction Variable Detection | Identifies variables incremented by a fixed step inside a loop |
| 7 | Partial Redundancy Elimination (PRE) | Hoists expressions computed in all predecessors of a join block |
| 8 | Dead Code Elimination (DCE) | Removes assignments whose result is never used (uses liveness sets) |
| 9 | Dead Copy Elimination | Removes `x = y` copies where the original `y` can be used directly |

---

## 7. Phase 6 — Target Code Generation

### Register-Based Assembly (Lecture 7 Model)

Unlimited virtual registers `R1, R2, R3, …` are used. Each TAC temporary `t_i` is mapped to a register; the mapping follows the **Address Descriptor**.

Sample output for `sum = a + b * 2`:
```
MOV  2, R1
MUL  b, R1, R2
ADD  a, R2, R3
MOV  R3, sum
```

### Address Descriptor

An `AddressDescriptor` tracks where each named variable's current value lives — in a register, in memory (the Activation Record), or both:

```
Variable  Locations
--------  ---------
a         {R2, mem}
sum       {R3, mem}
t0        {R1}
```

- Temporaries (`t_i`) exist only in registers.
- Named variables are marked as `{reg, mem}` on first store (they were allocated in the AR at declaration time).

### Activation Record (AR)

When a symbol table is available, the code generator emits a full AR prologue and epilogue:

```
AR_INIT  <total_bytes>   ; allocate stack frame (sum of all variable sizes)
FP_SET                   ; set frame pointer
  ... body instructions ...
AR_RET                   ; restore frame and return
```

`total_bytes` equals the sum of `entry.size` for every variable in the global scope (e.g., four `int` variables + one `float` + one `bool` = 4×2 + 4 + 1 = 13 bytes).

---

## 8. Test Suite (12 Files)

| File | Expected outcome | Features exercised |
|------|------------------|--------------------|
| `test1_valid.sl` | SUCCESS | int/float/bool variables, arithmetic, if/else, while, print |
| `test2_optimize.sl` | SUCCESS | Constant folding, algebraic simplify |
| `test3_lex_error.sl` | LEX ERROR | Invalid identifier, malformed float, unterminated string, invalid symbol |
| `test4_sem_error.sl` | SEM ERROR | Duplicate declaration, undeclared variable, type mismatch, non-bool condition |
| `test5_syntax_recovery.sl` | SYN ERROR | Panic-mode recovery across multiple syntax errors |
| `test6_optimizations.sl` | SUCCESS | DCE, strength reduction (`i*2`→`i<<1`), loop-invariant motion, induction variable, PRE |
| `test7_arrays.sl` | SUCCESS | Array declaration, index access, assignment, variable index in while loop |
| `test8_array_bounds_error.sl` | SEM ERROR | Compile-time out-of-bounds index detection |
| `test9_operators.sl` | SUCCESS | `-` `/` float arithmetic, int→float widening, unary `-` `!`, all 6 relational ops, `&&` `\|\|`, if-without-else |
| `test9_full_coverage.sl` | SUCCESS | All operators + scope shadowing + DAG CSE in one program |
| `test10_scope_cse.sl` | SUCCESS | Scope shadowing, DAG CSE (`a+b` twice), strength reduction `*4` and `*8` |
| `test11_scope_error.sl` | SEM ERROR | Variable used after its declaring block exits |

---

## 9. Project Structure

```
compiler/
├── README.md
├── src/
│   ├── compiler.py      ← entry point — run this
│   ├── lexer.py         Phase 1: DFA tokenizer
│   ├── parser.py        Phase 2: recursive-descent parser
│   ├── ast_nodes.py     shared AST node classes
│   ├── semantic.py      Phase 3: HashTable, SymbolEntry, scope stack
│   ├── ir_gen.py        Phase 4: TAC / Quad generation
│   ├── optimizer.py     Phase 5: CFG, DAG, liveness, 9 passes
│   └── codegen.py       Phase 6: register assembly, AddressDescriptor, AR
└── tests/
    ├── test1_valid.sl
    ├── test2_optimize.sl
    ├── test3_lex_error.sl
    ├── test4_sem_error.sl
    ├── test5_syntax_recovery.sl
    ├── test6_optimizations.sl
    ├── test7_arrays.sl
    ├── test8_array_bounds_error.sl
    ├── test9_operators.sl
    ├── test9_full_coverage.sl
    ├── test10_scope_cse.sl
    └── test11_scope_error.sl
```

---

## 10. How to Run

You only need **Python 3** installed — no packages, no setup.

```bash
# Compile a valid program (prints all 6 phases)
python src/compiler.py tests/test1_valid.sl

# Compile and save output to a file
python src/compiler.py tests/test1_valid.sl > output.txt

# Test error detection
python src/compiler.py tests/test3_lex_error.sl
python src/compiler.py tests/test4_sem_error.sl
python src/compiler.py tests/test5_syntax_recovery.sl

# Test optimizations
python src/compiler.py tests/test6_optimizations.sl

# Test all at once (PowerShell)
foreach ($f in Get-ChildItem tests\*.sl) { python src\compiler.py $f.FullName }
```

> On Windows use `python src\compiler.py tests\test1_valid.sl` (backslashes).  
> On macOS/Linux use `python3 src/compiler.py tests/test1_valid.sl`.

---

## 11. Output Format

For a valid program, the compiler prints all six phases in sequence:

```
================================================================
PHASE 1: LEXICAL ANALYSIS
================================================================
Token table: type, value, line number for every token

================================================================
PHASE 2: SYNTAX ANALYSIS (PARSING)
================================================================
AST printed as indented tree

================================================================
PHASE 3: SEMANTIC ANALYSIS
================================================================
Symbol table: NAME | TYPE | SIZE(B) | OFFSET(B)
Total AR size in bytes
No semantic errors.

================================================================
PHASE 4: INTERMEDIATE CODE GENERATION (TAC)
================================================================
Numbered list of Quads

================================================================
PHASE 5: CODE OPTIMIZATION
================================================================
CFG: blocks with predecessors and successors
DAG per block (leaf nodes, operation nodes, CSE count)
Liveness: live_in and live_out per block
Before / after quad count, optimized TAC

================================================================
PHASE 6: TARGET CODE GENERATION
================================================================
Register-based assembly (AR_INIT … AR_RET)
Address Descriptor table

================================================================
COMPILATION SUCCESSFUL
================================================================
```

For a program with errors, the pipeline stops at the failing phase and prints line-numbered error messages:
```
Lexical Error (line 2, col 1): Invalid identifier '2name'
Semantic Error (line 5): variable 'x' used before declaration
```
