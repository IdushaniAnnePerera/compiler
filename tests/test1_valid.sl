// test1_valid.sl - a fully valid program exercising every construct
int a = 5;
int b = 10;
int sum;
sum = a + b * 2;          /* arithmetic with precedence */
float pi = 3.14;
bool flag = a < b;

if (flag) begin
    print("a is smaller");
    print(sum);
end else begin
    print("a is bigger");
end

int i = 0;
while (i < 3) begin
    print(i);
    i = i + 1;
end
