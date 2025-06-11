// .roo/cognee/tests/parser/test_data/cpp/slicing/closely_packed_definitions.cpp
struct Point2D { int x_coord; int y_coord; }; // Line 0. Def: Point2D. Slice point.
namespace TinyNS { class Helper { public: void assist(); }; } // Line 1. Def: TinyNS, Def: TinyNS::Helper, Decl: TinyNS::Helper::assist. Slices for NS, Class, Method.
enum class Color { RED, GREEN, BLUE }; // Line 2. Def: Color. Slice point.
void standaloneFunction(int param) { /* body */ } // Line 3. Def: standaloneFunction(int). Slice point.
typedef Point2D Vec2D; // Line 4. Def: TypeAlias Vec2D. Slice point.
