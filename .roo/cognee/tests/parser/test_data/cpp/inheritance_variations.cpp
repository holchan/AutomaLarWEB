// .roo/cognee/tests/parser/test_data/cpp/inheritance_variations.hpp
#pragma once // Include guard. Slice Point.
#include <string> // ExtRef: std::string. Slice Point.

namespace InheritanceTest { // NS: InheritanceTest. Slice Point.

    class Base1 { // ClassDef: InheritanceTest::Base1. Slice Point.
    public:
        virtual ~Base1() = default; // DestructorDef: InheritanceTest::Base1::~Base1(). Slice Point.
        virtual void commonMethod() = 0; // MethodDecl: InheritanceTest::Base1::commonMethod(). Slice Point. (Pure virtual)
        void base1Method() {} // MethodDef: InheritanceTest::Base1::base1Method(). Slice Point.
    };

    class Base2 { // ClassDef: InheritanceTest::Base2. Slice Point.
    public:
        std::string name_base2;
        void base2Method() {} // MethodDef: InheritanceTest::Base2::base2Method(). Slice Point.
    };

    template<typename T> // TemplateClass. Slice Point for template, then for class.
    class TemplatedBase { // ClassDef: InheritanceTest::TemplatedBase.
    public:
        T templated_data;
        void templatedBaseMethod(T val) { templated_data = val; } // MethodDef: InheritanceTest::TemplatedBase::templatedBaseMethod(T). Slice Point.
    };

    // Single Inheritance
    class DerivedSingle : public Base1 { // ClassDef: InheritanceTest::DerivedSingle. EXTENDS Base1. Slice Point.
    public:
        void commonMethod() override {} // MethodDef: InheritanceTest::DerivedSingle::commonMethod(). Slice Point.
        void derivedSingleMethod() {} // MethodDef: InheritanceTest::DerivedSingle::derivedSingleMethod(). Slice Point.
    };

    // Multiple Inheritance
    class DerivedMultiple : public Base1, private Base2 { // ClassDef: InheritanceTest::DerivedMultiple. EXTENDS Base1, EXTENDS Base2. Slice Point.
    public:
        void commonMethod() override {} // MethodDef: InheritanceTest::DerivedMultiple::commonMethod(). Slice Point.
        void derivedMultipleMethod() { // MethodDef: InheritanceTest::DerivedMultiple::derivedMultipleMethod(). Slice Point.
            name_base2 = "from_derived_multiple";
            base2Method(); // CallSite: base2Method (implicitly this->base2Method)
        }
    };

    // Inheriting from a templated class
    class DerivedFromTemplate : public TemplatedBase<int> { // ClassDef: InheritanceTest::DerivedFromTemplate. EXTENDS TemplatedBase<int>. Slice Point.
    public:
        void useTemplatedFeature() { // MethodDef: InheritanceTest::DerivedFromTemplate::useTemplatedFeature(). Slice Point.
            templated_data = 100;
            templatedBaseMethod(200); // CallSite: templatedBaseMethod (implicitly this->templatedBaseMethod)
        }
    };

    class IndependentClass { // ClassDef: InheritanceTest::IndependentClass. Slice Point.
        int id;
    };

    struct DerivedStruct : Base1 { // StructDef: InheritanceTest::DerivedStruct. EXTENDS Base1. Slice Point.
         void commonMethod() override {} // MethodDef: InheritanceTest::DerivedStruct::commonMethod(). Slice Point.
    };

} // namespace InheritanceTest
