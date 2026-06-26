// test4_sem_error.sl - semantic errors
int a = 5;
int a = 9;          // duplicate declaration
b = 10;             // used before declaration
bool c = a + 2;     // type mismatch: int assigned to bool
if (a + 1) begin    // condition not bool
    print(a);
end
