#pragma once
#include <string>

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

    class DerivedSingle : public Base1 {
    public:
        void commonMethod() override {}
        void derivedSingleMethod() {}
    };

    class DerivedMultiple : public Base1, private Base2 {
    public:
        void commonMethod() override {}
        void derivedMultipleMethod() {
            name_base2 = "from_derived_multiple";
            base2Method();
        }
    };

    class DerivedFromTemplate : public TemplatedBase<int> {
    public:
        void useTemplatedFeature() {
            templated_data = 100;
            templatedBaseMethod(200);
        }
    };

    class IndependentClass {
        int id;
    };

    struct DerivedStruct : Base1 {
         void commonMethod() override {}
    };

}
