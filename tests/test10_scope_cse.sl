// test10_scope_cse.sl
// Covers:
//   scope shadowing  — inner variable with same name as outer
//   DAG CSE          — same expression computed twice in one basic block
//   strength reduction with higher powers (x*4 -> <<2, x*8 -> <<3)

// ── Scope shadowing ───────────────────────────────────────────────
// The outer x = 10 is visible everywhere except inside the if-block,
// where an inner x = 99 shadows it.  After the block, outer x = 10
// is accessible again unchanged.

int x = 10;
if (x < 20) begin
    int x = 99;             // inner x — separate variable, same name
    print(x);               // prints 99
end
print(x);                   // prints 10  (outer x, unaffected)

// ── DAG CSE: same expression twice in one basic block ─────────────
// The DAG detects that 'a + b' is computed twice and shows cse_count=1.
// Constant folding will eliminate both (4+7=11), but the DAG report
// (built before optimization) captures the redundancy in the source.

int a = 4;
int b = 7;
int p = a + b;              // first computation of a + b
int q = a + b;              // second — DAG marks this as CSE

print(p);                   // 11
print(q);                   // 11

// ── Strength reduction with higher powers of 2 ────────────────────
int s4 = a * 4;             // 4*4 = 16  →  after opt: a << 2
int s8 = a * 8;             // 4*8 = 32  →  after opt: a << 3

print(s4);                  // 16
print(s8);                  // 32
