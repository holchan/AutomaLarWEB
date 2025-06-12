#include <iostream>
#include <vector>
#include <string>
#include <functional>
#include <array>

class ForwardDeclaredClass;

typedef int Number;
typedef void (*FuncPtr)(int);
typedef std::vector<std::string> StringVector;


namespace TestNS {
    namespace InnerNS {
        void innerFunction() {
            std::cout << "InnerNS function" << std::endl;
        }
    }

    struct DataContainer {
        int id;
        StringVector data_items;
    };

    void namespacedFunction(const DataContainer& dc) {
        std::cout << "Namespace function called with ID: " << dc.id << std::endl;
        InnerNS::innerFunction();
    }
}

namespace {
    const double PI_ANON = 3.14159;
    void anonNSFunction() {
        std::cout << "Anonymous namespace function. PI_ANON = " << PI_ANON << std::endl;
    }
}

struct SimpleStruct {
    Number value;
    char label[10];
};

enum UnscopedEnum { VAL_A, VAL_B };
namespace TestNS {
    enum class ScopedEnum : unsigned char { OPTION_X, OPTION_Y };
}


template<typename T, size_t N>
std::array<T, N> createInitializedArray(T val) {
    std::array<T, N> arr;
    arr.fill(val);
    return arr;
}

class MyComplexClass {
public:
    static int static_member;
    const std::string class_name;

    MyComplexClass(std::string name = "DefaultComplex") : class_name(std::move(name)) {
        std::cout << "MyComplexClass constructor for: " << class_name << std::endl;
    }

    virtual ~MyComplexClass() {
        std::cout << "MyComplexClass destructor for: " << class_name << std::endl;
    }

    virtual void virtualMethod() {
        std::cout << "MyComplexClass::virtualMethod" << std::endl;
    }

    void constMethod() const {
        std::cout << "MyComplexClass::constMethod (const)" << std::endl;
    }

    static void staticMethod() {
        std::cout << "MyComplexClass::staticMethod. static_member = " << ++static_member << std::endl;
    }

    void deletedMethod() = delete;

    MyComplexClass operator+(const MyComplexClass& other) const {
        return MyComplexClass(this->class_name + "_" + other.class_name);
    }

private:
    int private_data = 0;
    friend void friendFunction(MyComplexClass&);
};
int MyComplexClass::static_member = 0;

void friendFunction(MyComplexClass& mcc) {
    mcc.private_data = 100;
    std::cout << "Friend function accessed private_data, set to: " << mcc.private_data << std::endl;
}

namespace TestNS {
    class DerivedClass : public MyComplexClass {
    public:
        DerivedClass(std::string name) : MyComplexClass(name) {
            std::cout << "DerivedClass constructor for: " << name << std::endl;
        }

        void virtualMethod() override {
            std::cout << "DerivedClass::virtualMethod (overridden)" << std::endl;
            MyComplexClass::virtualMethod();
        }

        void anotherVirtualMethod() {
             std::cout << "DerivedClass::anotherVirtualMethod" << std::endl;
        }
    };
}


void useLambda() {
    std::function<int(int, int)> add = [](int a, int b) -> int { return a + b; };
    std::cout << "Lambda add(5,3) = " << add(5,3) << std::endl;

    int x = 10;
    auto capture_lambda = [x](int val) { return x + val; };
    std::cout << "Capture lambda (10 + 7) = " << capture_lambda(7) << std::endl;
}

extern "C" {
    void c_style_function(int i) {
        printf("C-style function called with: %d\n", i);
    }
}

using namespace std;

int main() {
    cout << "Complex Features Demo" << endl;

    MyComplexClass obj1("Obj1");
    obj1.constMethod();
    obj1.virtualMethod();
    MyComplexClass::staticMethod();

    MyComplexClass obj2 = obj1 + MyComplexClass("Obj2_Added");
    cout << "Obj2 name: " << obj2.class_name << endl;

    friendFunction(obj1);

    TestNS::DataContainer dc = {1, {"item1", "item2"}};
    TestNS::namespacedFunction(dc);
    anonNSFunction();

    TestNS::DerivedClass derived_obj("DerivedObj");
    derived_obj.virtualMethod();
    derived_obj.anotherVirtualMethod();

    auto arr = createInitializedArray<int, 5>(7);
    cout << "Array element: " << arr[0] << endl;

    useLambda();
    c_style_function(42);

    UnscopedEnum ue = VAL_A;
    TestNS::ScopedEnum se = TestNS::ScopedEnum::OPTION_X;
    if (ue == VAL_A && se == TestNS::ScopedEnum::OPTION_X) {
        cout << "Enums match." << endl;
    }

    return 0;
}
