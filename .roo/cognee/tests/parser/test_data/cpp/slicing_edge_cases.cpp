// File 1: Only comments but with an include
// Expected: slice_lines=[0], 1 ExternalReference CodeEntity for iostream, associated with chunk 0.
#include <iostream> // ExternalReference: std::iostream
// Another comment
// End of comments-only file.

// Separator for conceptual files, not actual C++ syntax
// --- NEW CONCEPTUAL FILE: empty_with_block_comment.cpp ---
/*
 * Block comment
 * #include <vector> // This include within a block comment should NOT be parsed as an ExternalReference by tree-sitter
 */
// Expected: slice_lines=[0] (or [] if parser doesn't add 0 for non-blank if nothing else found), no CodeEntities related to vector.

// --- NEW CONCEPTUAL FILE: closely_packed.cpp ---
struct Point { int x; int y; }; // Def: Point, slice_lines should include its start
namespace MiniNS { void func1() {} } // Def: MiniNS, Def: MiniNS::func1, slice_lines for ns and func1
void globalFunc() {} // Def: globalFunc, slice_lines for globalFunc
// Expected: slice_lines like [start_of_Point, start_of_MiniNS, start_of_func1, start_of_globalFunc]
// Each definition should map to its respective small chunk.

// --- NEW CONCEPTUAL FILE: include_then_code.cpp ---
#include <string> // ExternalReference: std::string, slice_lines=[0] or [start_of_include, start_of_MyStringUser]
class MyStringUser { // Def: MyStringUser
    std::string name;
public:
    MyStringUser(std::string s) : name(std::move(s)) {} // Def: MyStringUser::MyStringUser
    void printName() { std::cout << name; } // Def: MyStringUser::printName
};
// Expected: slice_lines like [start_of_include, start_of_MyStringUser, start_of_constructor, start_of_printName]
// ExternalReference for string should be in first chunk. Class and methods in subsequent.

// --- NEW CONCEPTUAL FILE: file_with_only_forward_decl.hpp ---
class ForwardDeclaredClass; // This is a declaration, not a full definition.
// Our current queries might not pick this up as a "ClassDefinition" CodeEntity,
// or might pick it up as a simple declaration. How this is handled needs to be defined.
// For now, assume it might not create a CodeEntity or a specific slice_line.
// If we want to capture forward declarations, a new query and entity type (e.g., "ClassDeclaration") would be needed.
// Expected: slice_lines=[0] (if contentful), possibly no specific CodeEntity.
