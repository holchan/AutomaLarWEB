// .roo/cognee/tests/parser/test_data/cpp/complex_features.cpp
#include <iostream>
#include <vector>
#include <string>
#include <functional> // For std::function
#include <array>      // For std::array

// Forward declaration
class ForwardDeclaredClass;

// C-style typedef
typedef int Number;
typedef void (*FuncPtr)(int); // Function pointer typedef
typedef std::vector<std::string> StringVector; // C-style typedef for StringVector to be caught by 'typedefs' query


// Namespace and nested namespace
namespace TestNS {
    namespace InnerNS {
        void innerFunction() {
            std::cout << "InnerNS function" << std::endl;
        }
    }

    struct DataContainer {
        int id;
        StringVector data_items; // Uses the typedef'd StringVector
    };

    void namespacedFunction(const DataContainer& dc) {
        std::cout << "Namespace function called with ID: " << dc.id << std::endl;
        InnerNS::innerFunction();
    }
} // namespace TestNS

// Anonymous namespace
namespace {
    const double PI_ANON = 3.14159;
    void anonNSFunction() {
        std::cout << "Anonymous namespace function. PI_ANON = " << PI_ANON << std::endl;
    }
}

// Global struct
struct SimpleStruct {
    Number value; // Uses the typedef'd Number
    char label[10];
};

// Enums (unscoped and scoped)
enum UnscopedEnum { VAL_A, VAL_B }; // global enum
namespace TestNS {
    enum class ScopedEnum : unsigned char { OPTION_X, OPTION_Y }; // Scoped enum inside TestNS
}


// Template function definition (global)
template<typename T, size_t N>
std::array<T, N> createInitializedArray(T val) {
    std::array<T, N> arr;
    arr.fill(val);
    return arr;
}

// Class with various features
class MyComplexClass {
public:
    static int static_member;
    const std::string class_name;

    // Constructor with initializer list and default argument
    MyComplexClass(std::string name = "DefaultComplex") : class_name(std::move(name)) {
        std::cout << "MyComplexClass constructor for: " << class_name << std::endl;
    }

    // Virtual destructor (good practice for base classes)
    virtual ~MyComplexClass() {
        std::cout << "MyComplexClass destructor for: " << class_name << std::endl;
    }

    // Virtual method
    virtual void virtualMethod() {
        std::cout << "MyComplexClass::virtualMethod" << std::endl;
    }

    // Const method
    void constMethod() const {
        std::cout << "MyComplexClass::constMethod (const)" << std::endl;
    }

    // Static method
    static void staticMethod() {
        std::cout << "MyComplexClass::staticMethod. static_member = " << ++static_member << std::endl;
    }

    // Deleted method (C++11)
    void deletedMethod() = delete;

    // Operator overloading
    MyComplexClass operator+(const MyComplexClass& other) const {
        return MyComplexClass(this->class_name + "_" + other.class_name);
    }

private:
    int private_data = 0;
    friend void friendFunction(MyComplexClass&); // Friend function declaration
};
int MyComplexClass::static_member = 0; // Static member definition

// Friend function definition (global scope)
void friendFunction(MyComplexClass& mcc) {
    mcc.private_data = 100;
    std::cout << "Friend function accessed private_data, set to: " << mcc.private_data << std::endl;
}

// Derived class
namespace TestNS {
    class DerivedClass : public MyComplexClass { // MyComplexClass is global, so no TestNS:: prefix needed here for base
    public:
        DerivedClass(std::string name) : MyComplexClass(name) { // Call base constructor
            std::cout << "DerivedClass constructor for: " << name << std::endl;
        }

        // Override virtual method
        void virtualMethod() override {
            std::cout << "DerivedClass::virtualMethod (overridden)" << std::endl;
            MyComplexClass::virtualMethod(); // Call base class version
        }

        void anotherVirtualMethod() { // Not overriding, just another virtual
             std::cout << "DerivedClass::anotherVirtualMethod" << std::endl;
        }
    };
} // namespace TestNS


// Function using lambda and std::function (global scope)
void useLambda() {
    std::function<int(int, int)> add = [](int a, int b) -> int { return a + b; };
    std::cout << "Lambda add(5,3) = " << add(5,3) << std::endl;

    int x = 10;
    auto capture_lambda = [x](int val) { return x + val; }; // Lambda
    std::cout << "Capture lambda (10 + 7) = " << capture_lambda(7) << std::endl;
}

// Extern "C" linkage (example) (global scope)
extern "C" {
    void c_style_function(int i) {
        printf("C-style function called with: %d\n", i);
    }
}

// Using namespace std (often discouraged in headers, fine in .cpp)
using namespace std; // This should generate an IMPORTS relationship to "std"

int main() { // global main
    cout << "Complex Features Demo" << endl;

    MyComplexClass obj1("Obj1");
    obj1.constMethod();
    obj1.virtualMethod();
    MyComplexClass::staticMethod();
    // obj1.deletedMethod(); // This would be a compile error

    MyComplexClass obj2 = obj1 + MyComplexClass("Obj2_Added");
    cout << "Obj2 name: " << obj2.class_name << endl;

    friendFunction(obj1);

    TestNS::DataContainer dc = {1, {"item1", "item2"}};
    TestNS::namespacedFunction(dc);
    anonNSFunction();

    TestNS::DerivedClass derived_obj("DerivedObj");
    derived_obj.virtualMethod();
    derived_obj.anotherVirtualMethod();

    auto arr = createInitializedArray<int, 5>(7); // Use global template function
    cout << "Array element: " << arr[0] << endl;

    useLambda();
    c_style_function(42);

    UnscopedEnum ue = VAL_A;
    TestNS::ScopedEnum se = TestNS::ScopedEnum::OPTION_X; // Use scoped enum
    if (ue == VAL_A && se == TestNS::ScopedEnum::OPTION_X) {
        cout << "Enums match." << endl;
    }

    return 0;
}
