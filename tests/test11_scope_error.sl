// test11_scope_error.sl
// Semantic error: variable declared inside a block used after the block ends.
// When the if-block closes, inner is removed from the scope stack.
// The print(inner) below the block should trigger:
//   Semantic Error: variable 'inner' used before declaration

int outer = 5;

if (outer < 10) begin
    int inner = 42;         // declared in inner scope only
    print(inner);           // OK — still in scope here
end

print(inner);               // ERROR: inner no longer in scope
