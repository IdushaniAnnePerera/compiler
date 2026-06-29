// test8_array_bounds_error.sl - demonstrates compile-time array bounds checking

int data[3];

data[0] = 100;
data[5] = 999;   // ERROR: index 5 is out of bounds [0..2]

print(data[0]);
print(data[-1]);  // ERROR: negative index
