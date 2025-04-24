#include <iostream>
#include <vector>
#include <string>
#include "my_class.hpp" // Include header

// Using directive
using namespace std;

namespace Processing {

    // Implementation of the MyDataProcessor class method
    void MyDataProcessor::processVector(const vector<string>& data) {
        cout << "Processing C++ vector data..." << endl;
        for (const auto& item : data) {
            cout << " - Item: " << item << endl;
        }
    }

    // Standalone function within namespace
    int helperFunction(int value) {
        return value * 2;
    }

} // namespace Processing

// Global function using the class
int main() {
    Processing::MyDataProcessor processor("MainProcessor");
    vector<string> items = {"alpha", "beta", "gamma"};
    processor.processVector(items);

    cout << "Helper result: " << Processing::helperFunction(5) << endl;

    return 0;
}
