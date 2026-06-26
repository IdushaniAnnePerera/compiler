// test2_optimize.sl - constant folding & algebraic simplification demo
int x = 3 + 4 * 2;     // folds to 11
int y = x * 1;         // simplifies to x
int z = y + 0;         // simplifies to y
int w = x * 0;         // simplifies to 0
print(x);
print(w);
