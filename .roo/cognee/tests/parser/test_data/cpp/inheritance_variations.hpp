#pragma once // Include guard
#include <string> // For std::string

namespace InheritanceTest {

    class Base1 {
    public:
        virtual ~Base1() = default;
        virtual void commonMethod() = 0;
        void base1Method() {}
    };

    class Base2 {
    public:
        std::string name_base2;
        void base2Method() {}
    };

    template<typename T>
    class TemplatedBase {
    public:
        T templated_data;
        void templatedBaseMethod(T val) { templated_data = val; }
    };

    // Single Inheritance
    class DerivedSingle : public Base1 {
    public:
        void commonMethod() override {}
        void derivedSingleMethod() {}
    };

    // Multiple Inheritance
    class DerivedMultiple : public Base1, private Base2 {
    public:
        void commonMethod() override {}
        void derivedMultipleMethod() {
            name_base2 = "from_derived_multiple"; // Accessing Base2 member
            base2Method(); // Calling Base2 method
        }
    };

    // Inheriting from a templated class
    class DerivedFromTemplate : public TemplatedBase<int> {
    public:
        void useTemplatedFeature() {
            templated_data = 100; // Accessing TemplatedBase<int>::templated_data
            templatedBaseMethod(200); // Calling TemplatedBase<int>::templatedBaseMethod
        }
    };

    // Class without inheritance
    class IndependentClass {
        int id;
    };

    // Struct inheriting
    struct DerivedStruct : Base1 {
         void commonMethod() override {}
    };

} // namespace InheritanceTest
