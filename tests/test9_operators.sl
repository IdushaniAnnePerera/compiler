// test9_operators.sl
// Covers every operator and construct not reached by test1-test8:
//   subtraction, division, float arithmetic, int-to-float widening,
//   unary minus, logical NOT, all 6 relational ops (>, >=, ==, !=),
//   logical AND / OR, and if-without-else.

// ── Arithmetic: subtraction and division ──────────────────────────
int a = 20;
int b = 4;
int diff = a - b;           // 20 - 4 = 16
int quot = a / b;           // 20 / 4 = 5

// ── Float arithmetic ──────────────────────────────────────────────
float fx = 7.5;
float fy = 2.5;
float fsum  = fx + fy;      // 10.0
float fdiff = fx - fy;      // 5.0

// ── int widened to float (type-compatible assignment) ─────────────
float wide = a;             // int 20 -> float (widening)

// ── Unary minus ───────────────────────────────────────────────────
int neg = -b;               // -4

// ── Logical NOT ───────────────────────────────────────────────────
bool t = true;
bool f = !t;                // !true = false

// ── All 6 relational operators ────────────────────────────────────
bool lt = a <  100;         // true
bool gt = a >  b;           // true   (20 > 4)
bool le = b <= 4;           // true   (4 <= 4)
bool ge = a >= 20;          // true   (20 >= 20)
bool eq = a == 20;          // true
bool ne = a != b;           // true

// ── Logical AND / OR ─────────────────────────────────────────────
bool both   = gt && eq;     // true && true  = true
bool either = f  || ne;     // false || true = true

// ── if without else ───────────────────────────────────────────────
if (both) begin
    print(diff);            // 16
    print(quot);            // 5
end

print(fsum);                // 10.0
print(neg);                 // -4
print(both);                // true (1)
print(either);              // true (1)
