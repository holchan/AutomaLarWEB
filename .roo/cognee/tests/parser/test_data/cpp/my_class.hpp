#ifndef MY_CLASS_HPP
#define MY_CLASS_HPP

#include <string>
#include <vector>

namespace Processing {

    // Class definition in header
    class MyDataProcessor {
    private:
        std::string processor_name;

    public:
        // Constructor
        MyDataProcessor(const std::string& name) : processor_name(name) {}

        // Destructor (example)
        virtual ~MyDataProcessor() = default;

        // Method declaration
        void processVector(const std::vector<std::string>& data);

        // Template method example (declaration only)
        template<typename T>
        T identity(T value) { return value; }
    };

    // Function declaration in header
    int helperFunction(int value);

} // namespace Processing

#endif // MY_CLASS_HPP
