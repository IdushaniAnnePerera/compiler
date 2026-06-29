// test6_optimizations.sl — exercises all six Lecture-9 techniques
//
//  Technique          Where triggered
//  ─────────────────────────────────────────────────────────────────
//  1 Basic Blocks     printed for the whole program
//  2 Dead-Code Elim   dead_var is declared but never read again
//  3 Strength Reduc.  i * 2  (power-of-two multiply) inside loop
//  4 Loop-Inv. Motion b + a  inside while body (a, b never change)
//  5 Induction Var.   i = i + 1  in every iteration
//  6 PRE              a + b computed in BOTH branches of if/else

int a = 3;
int b = 5;
int i = 0;
int n = 10;
int x = 0;

// Dead code: dead_var is assigned but never used afterwards
int dead_var = a + b;

// Loop: contains invariant expression, induction variable, and * 2
while (i < n) begin
    int inv     = b + a;       // loop-invariant (a, b not modified)
    int doubled = i * 2;       // strength reduction: * 2  ->  << 1
    x = x + inv + doubled;     // uses both so neither is dead
    i = i + 1;                 // induction variable: step = +1
end

// If/else: same expression a+b on both paths — PRE candidate
bool flag = x < 100;
if (flag) begin
    int r1 = a + b;
    print(r1);
end else begin
    int r2 = a + b;
    print(r2);
end

print(x);
