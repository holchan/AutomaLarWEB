#pragma once // Line 0

class MyForwardClass; // Line 2. Forward class declaration.
struct MyForwardStruct; // Line 3. Forward struct declaration.

namespace FwdNS {
    enum MyFwdEnum : int; // Line 6. Forward enum declaration.
    class AnotherFwdClass; // Line 7.
}

void fwd_declared_func(int); // Line 10. Function prototype (declaration).
int fwd_declared_var_init = 10; // Global variable, not a CodeEntity we typically capture unless it has complex init.
extern int fwd_declared_var_extern; // Extern variable declaration.
