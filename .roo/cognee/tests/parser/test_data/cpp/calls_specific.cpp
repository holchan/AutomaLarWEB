// .roo/cognee/tests/parser/test_data/cpp/calls_specific.cpp
#include <iostream> // ExtRef: std::iostream. Slice point.
#include <vector>   // ExtRef: std::vector. Slice point.
#include <string>   // ExtRef: std::string. Slice point.
#include "my_class.hpp" // ExtRef: my_class.hpp. Slice point. (Assume my_class.hpp exists in test_data/cpp/)

// Forward declaration for use in function pointer
void utility_printer(const std::string& msg); // Decl: utility_printer(const std::string&). Slice point.

// Typedef for function pointer
typedef void (*PrinterFuncPtr)(const std::string&); // TypeAlias: PrinterFuncPtr. Slice point.

namespace CallTestNS { // NS: CallTestNS. Slice point.
    struct MyCallableStruct { // Struct: CallTestNS::MyCallableStruct. Slice point.
        int id;
        void operator()(const std::string& s) const { // MethodDef: CallTestNS::MyCallableStruct::operator()(const std::string&). Slice point.
            std::cout << "MyCallableStruct(" << id << ") called with: " << s << std::endl; // CallSite: std::cout, operator<<
        }
    };

    void a_namespaced_function(int x) { // FuncDef: CallTestNS::a_namespaced_function(int). Slice point.
        std::cout << "CallTestNS::a_namespaced_function called with " << x << std::endl; // CallSite: std::cout, operator<<
        utility_printer("from namespaced_function"); // CallSite: utility_printer
    }

    template<typename T> // TemplateFuncDef. Slice point for template, then for func.
    T generic_processor(T input) { // FuncDef: CallTestNS::generic_processor(T)
        std::cout << "generic_processor with a " << typeid(input).name() << std::endl; // CallSite: std::cout, typeid, .name, operator<<
        if (input > 0) { // operator>
             a_namespaced_function(input); // CallSite: a_namespaced_function
        }
        return input;
    }
} // namespace CallTestNS

void global_function_no_args() { // FuncDef: global_function_no_args(). Slice point.
    std::cout << "global_function_no_args called" << std::endl; // CallSite: std::cout, operator<<
}

void global_function_with_args(int a, std::string b) { // FuncDef: global_function_with_args(int,std::string). Slice point.
    std::cout << "global_function_with_args called with " << a << " and " << b << std::endl; // CallSite: std::cout, operator<<
    CallTestNS::a_namespaced_function(a); // CallSite: CallTestNS::a_namespaced_function
}

void utility_printer(const std::string& msg) { // FuncDef: utility_printer(const std::string&). Slice point.
    std::cout << "[UTIL] " << msg << std::endl; // CallSite: std::cout, operator<<
}

class MemberCallTester { // ClassDef: MemberCallTester. Slice point.
public:
    std::string name;
    MemberCallTester(std::string n) : name(std::move(n)) {} // ConstructorDef: MemberCallTester::MemberCallTester(std::string). Slice point.

    void simple_member_method(int val) { // MethodDef: MemberCallTester::simple_member_method(int). Slice point.
        std::cout << name << "::simple_member_method(" << val << ")" << std::endl; // CallSite: std::cout, operator<<
        this->another_member_method(val + 10, "from simple_member"); // CallSite: this->another_member_method
        global_function_no_args(); // CallSite: global_function_no_args
    }

    void another_member_method(int x, const char* context) const { // MethodDef: MemberCallTester::another_member_method(int,const char*). Slice point.
        std::cout << name << "::another_member_method(" << x << ", " << context << ")" << std::endl; // CallSite: std::cout, operator<<
    }

    static void static_method_caller() { // Static MethodDef: MemberCallTester::static_method_caller(). Slice point.
        std::cout << "Static method caller" << std::endl; // CallSite: std::cout, operator<<
    }

    static std::string static_method_target(int code) { // Static MethodDef: MemberCallTester::static_method_target(int). Slice point.
        return "Static target called with " + std::to_string(code); // CallSite: std::to_string, operator+
    }

    std::vector<int> get_vector() { return {1,2,3}; } // MethodDef: MemberCallTester::get_vector(). Slice point.
};

// Main function to exercise calls
int main_calls_demo(int argc, char *argv[]) { // FuncDef: main_calls_demo(int,char**). Slice point.
    global_function_no_args(); // CSR #0
    global_function_with_args(10, "hello from main"); // CSR #1

    CallTestNS::a_namespaced_function(20); // CSR #2

    PrinterFuncPtr func_ptr = utility_printer; // Variable declaration
    func_ptr("via function pointer (typedef'd)"); // CSR #3 (called_name_expr: "func_ptr")

    void (*raw_func_ptr)(const std::string&) = &utility_printer; // Variable declaration
    raw_func_ptr("via raw function pointer"); // CSR #4 (called_name_expr: "raw_func_ptr")

    CallTestNS::MyCallableStruct callable_struct_instance {101}; // Variable declaration
    callable_struct_instance("Struct as Functor"); // CSR #5 (called_name_expr: "callable_struct_instance", operator() call)

    MemberCallTester tester_obj("TesterObj"); // Variable declaration, CSR for constructor MemberCallTester::MemberCallTester
    tester_obj.simple_member_method(5); // CSR #6 (called_name_expr: "tester_obj.simple_member_method")

    MemberCallTester* tester_ptr = new MemberCallTester("PtrObj"); // Variable declaration, CSR for new, CSR for constructor
    tester_ptr->another_member_method(15, "via pointer"); // CSR #7 (called_name_expr: "tester_ptr->another_member_method")

    std::string static_res = MemberCallTester::static_method_target(200); // CSR #8
    MemberCallTester::static_method_caller(); // CSR #9

    int template_arg = 77;
    CallTestNS::generic_processor<int>(template_arg); // CSR #10
    CallTestNS::generic_processor(88); // CSR #11

    std::vector<int> my_vec = tester_obj.get_vector(); // CSR #12
    my_vec.push_back(4); // CSR #13 (called_name_expr: "my_vec.push_back")

    // Assume MyDataProcessor is from "my_class.hpp"
    Processing::MyDataProcessor processor_ext("ExternalClass"); // CSR #14 (Constructor)
    std::vector<std::string> data_ext = {"ext_data"};
    processor_ext.processVector(data_ext); // CSR #15 (called_name_expr: "processor_ext.processVector")

    // Operator calls
    int x = 5, y = 3;
    int z = x + y; // CSR #16 (called_name_expr: "operator+" or similar based on query)
    std::cout << "Result: " << z << std::endl; // CSR #17 (called_name_expr: "operator<<" for std::cout)
                                            // CSR #18 (called_name_expr: "operator<<" for z)
                                            // CSR #19 (called_name_expr: "operator<<" for std::endl)
                                            // Note: operator<< calls are tricky, might show as one or multiple.

    delete tester_ptr; // CSR for delete
    return 0;
}
