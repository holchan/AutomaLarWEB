// .roo/cognee/tests/parser/test_data/cpp/calls_specific.cpp
#include <iostream>
#include <vector>
#include <string>
#include "my_class.hpp"

void utility_printer(const std::string& msg);

typedef void (*PrinterFuncPtr)(const std::string&);

namespace CallTestNS {
    struct MyCallableStruct {
        int id;
        void operator()(const std::string& s) const {
            std::cout << "MyCallableStruct(" << id << ") called with: " << s << std::endl;
        }
    };

    void a_namespaced_function(int x) {
        std::cout << "CallTestNS::a_namespaced_function called with " << x << std::endl;
        utility_printer("from namespaced_function");
    }

    template<typename T>
    T generic_processor(T input) {
        std::cout << "generic_processor with a " << typeid(input).name() << std::endl;
        if (input > 0) {
             a_namespaced_function(input);
        }
        return input;
    }
}

void global_function_no_args() {
    std::cout << "global_function_no_args called" << std::endl;
}

void global_function_with_args(int a, std::string b) {
    std::cout << "global_function_with_args called with " << a << " and " << b << std::endl;
    CallTestNS::a_namespaced_function(a);
}

void utility_printer(const std::string& msg) {
    std::cout << "[UTIL] " << msg << std::endl;
}

class MemberCallTester {
public:
    std::string name;
    MemberCallTester(std::string n) : name(std::move(n)) {}

    void simple_member_method(int val) {
        std::cout << name << "::simple_member_method(" << val << ")" << std::endl;
        this->another_member_method(val + 10, "from simple_member");
        global_function_no_args();
    }

    void another_member_method(int x, const char* context) const {
        std::cout << name << "::another_member_method(" << x << ", " << context << ")" << std::endl;
    }

    static void static_method_caller() {
        std::cout << "Static method caller" << std::endl;
    }

    static std::string static_method_target(int code) {
        return "Static target called with " + std::to_string(code);
    }

    std::vector<int> get_vector() { return {1,2,3}; }
};

int main_calls_demo(int argc, char *argv[]) {
    global_function_no_args();
    global_function_with_args(10, "hello from main");

    CallTestNS::a_namespaced_function(20);

    PrinterFuncPtr func_ptr = utility_printer;
    func_ptr("via function pointer (typedef'd)");

    void (*raw_func_ptr)(const std::string&) = &utility_printer;
    raw_func_ptr("via raw function pointer");

    CallTestNS::MyCallableStruct callable_struct_instance {101};
    callable_struct_instance("Struct as Functor");

    MemberCallTester tester_obj("TesterObj");
    tester_obj.simple_member_method(5);

    MemberCallTester* tester_ptr = new MemberCallTester("PtrObj");
    tester_ptr->another_member_method(15, "via pointer");

    std::string static_res = MemberCallTester::static_method_target(200);
    MemberCallTester::static_method_caller();

    int template_arg = 77;
    CallTestNS::generic_processor<int>(template_arg);
    CallTestNS::generic_processor(88);

    std::vector<int> my_vec = tester_obj.get_vector();
    my_vec.push_back(4);

    Processing::MyDataProcessor processor_ext("ExternalClass");
    std::vector<std::string> data_ext = {"ext_data"};
    processor_ext.processVector(data_ext);

    int x = 5, y = 3;
    int z = x + y;
    std::cout << "Result: " << z << std::endl;

    delete tester_ptr;
    return 0;
}
