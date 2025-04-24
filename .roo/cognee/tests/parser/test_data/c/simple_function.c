#include <stdio.h>
#include <stdlib.h>
#include "header.h" // Local header include

// Max value constant (example preprocessor)
#define MAX_ITEMS 100

/*
 * A simple function to add two integers.
 */
int add(int a, int b) {
    return a + b; // Return sum
}

typedef struct {
    int id;
    char name[50];
} Record;

int main(int argc, char *argv[]) {
    printf("Testing C parser...\n");
    int sum = add(5, 3);
    printf("Sum is %d\n", sum);

    Point p = {10, 20}; // Using struct from header.h
    print_point(p);

    Record rec;
    rec.id = 1;

    // Check MAX_ITEMS
    if (MAX_ITEMS > 50) {
        puts("Max items is large.");
    }

    return EXIT_SUCCESS;
}
