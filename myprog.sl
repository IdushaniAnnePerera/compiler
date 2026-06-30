// myprog.sl — SimpleLang showcase
// Demonstrates every feature of the compiler in one program.

// ── 1. Variable declaration: int, float, bool ─────────────────────
int  base   = 6;
int  height = 9;
float area;
bool is_big;

// ── 2. Arithmetic: +  -  *  / ─────────────────────────────────────
int  perimeter = 2 * base + 2 * height;   // 30
int  diff      = height - base;            // 3
int  product   = base * height;            // 54
int  quotient  = product / base;           // 9

// ── 3. int → float widening ───────────────────────────────────────
area = product;                            // int 54 widened to float

// ── 4. All relational operators ───────────────────────────────────
bool lt = base <  height;      // true
bool gt = height >  base;      // true
bool le = base <= 6;           // true
bool ge = height >= 9;         // true
bool eq = quotient == height;  // true  (9 == 9)
bool ne = base != height;      // true

// ── 5. Logical AND / OR / NOT ─────────────────────────────────────
is_big   = gt && ge;           // true && true  = true
bool either  = lt || ne;       // true || true  = true
bool neither = !is_big;        // !true         = false

// ── 6. Unary minus ────────────────────────────────────────────────
int neg_diff = -diff;          // -3

// ── 7. if / else ──────────────────────────────────────────────────
if (is_big) begin
    print("shape is large");
end else begin
    print("shape is small");
end

// ── 8. if without else ────────────────────────────────────────────
if (eq) begin
    print("quotient equals height");
end

// ── 9. while loop ─────────────────────────────────────────────────
int i   = 1;
int acc = 0;
while (i <= base) begin
    acc = acc + i;
    i   = i + 1;
end
// acc = 1+2+3+4+5+6 = 21

// ── 10. Scope shadowing ───────────────────────────────────────────
int limit = 100;
if (acc < limit) begin
    int limit = 21;            // inner limit shadows outer
    print(limit);              // prints 21
end
print(limit);                  // prints 100 (outer, unchanged)

// ── 11. Array: declare, assign, access, variable index ───────────
int scores[5];
scores[0] = 80;
scores[1] = 65;
scores[2] = 90;
scores[3] = 72;
scores[4] = 85;

int idx   = 0;
int total = 0;
while (idx < 5) begin
    total = total + scores[idx];
    idx   = idx + 1;
end
// total = 392

// ── 12. Strength-reduction targets: *2, *4, *8 ───────────────────
int dbl  = base * 2;    // -> base << 1   (12)
int quad = base * 4;    // -> base << 2   (24)
int oct  = base * 8;    // -> base << 3   (48)

// ── 13. CSE opportunity (same expression twice in one block) ──────
int p = base + height;  // 15
int q = base + height;  // 15  — DAG marks this as CSE

// ── 14. Print summary ─────────────────────────────────────────────
print(perimeter);       // 30
print(area);            // 54.0
print(product);         // 54
print(quotient);        // 9
print(diff);            // 3
print(neg_diff);        // -3
print(acc);             // 21
print(total);           // 392
print(dbl);             // 12
print(quad);            // 24
print(oct);             // 48
print(p);               // 15
print(is_big);          // true
print(neither);         // false
