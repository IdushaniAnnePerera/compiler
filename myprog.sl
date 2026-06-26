// myprog.sl - my own test program

int n = 5;
int result = 1;
int i = 1;

while (i <= n) begin
    result = result * i;
    i = i + 1;
end

print(result);