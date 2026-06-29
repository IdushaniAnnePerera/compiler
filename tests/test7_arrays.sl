// test7_arrays.sl - array declaration, access, assignment, and bounds checking

int arr[5];

arr[0] = 10;
arr[1] = 20;
arr[2] = arr[0] + arr[1];

print(arr[0]);
print(arr[1]);
print(arr[2]);

// Loop over array elements using a variable index (runtime bounds)
int i = 0;
while (i < 3) begin
    print(arr[i]);
    i = i + 1;
end
