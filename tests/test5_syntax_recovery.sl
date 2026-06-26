// test5_syntax_recovery.sl - demonstrates panic-mode error recovery
int x = 5 + 3       // ERROR: missing semicolon
int y = 10;
int z = ;           // ERROR: missing expression
print(y);
