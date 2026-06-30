// test9_full_coverage.sl
// Covers every operator, type, and semantic feature not exercised by tests 1-8.
//
// Features exercised here:
//   Operators  : ==, !=, >, >=, <=, &&, ||, !, unary -, -, /
//   Semantic   : int->float widening, scope shadowing, CSE in same block
//   DAG CSE    : same expression (a + b) computed twice in one basic block

// ── Basic arithmetic with every operator ─────────────────────────────────────
int a = 20;
int b = 4;

int diff    = a - b;          // subtraction
int quot    = a / b;          // division  (20 / 4 = 5)
int neg     = -b;             // unary minus  (neg = -4)

print(diff);
print(quot);
print(neg);

// ── Relational operators not yet tested ──────────────────────────────────────
bool eq   = a == 20;          // equal         (true)
bool neq  = a != b;           // not equal     (true)
bool gt   = a > b;            // greater than  (true)
bool gte  = a >= 20;          // greater-equal (true)
bool lte  = b <= 4;           // less-equal    (true)

print(eq);
print(neq);
print(gt);
print(gte);
print(lte);

// ── Logical operators && || ! ─────────────────────────────────────────────────
bool p = a > 10;              // true
bool q = b < 2;               // false

bool both   = p && q;         // false
bool either = p || q;         // true
bool inv    = !p;             // false

print(both);
print(either);
print(inv);

// ── int -> float widening (semantic: assigning int expression to float var) ──
float ratio = quot;           // int 5 widened to float 5.0

print(ratio);

// ── Scope shadowing: inner 'a' shadows outer 'a' ─────────────────────────────
// outer a = 20
if (gt) begin
    int a = 99;               // new 'a' in inner scope — shadows outer a
    print(a);                 // prints 99
end
// back to outer scope: a is still 20
print(a);                     // prints 20

// ── CSE: same expression computed twice inside one basic block ────────────────
// Both r1 and r2 = a + b in the same block => DAG detects the shared node.
int r1 = a + b;
int r2 = a + b;               // DAG node shared with r1
print(r1);
print(r2);
