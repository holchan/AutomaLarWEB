#ifndef HEADER_H
#define HEADER_H

// A simple struct definition
typedef struct {
    int x;
    int y;
} Point;

// Function prototype defined in header
void print_point(Point p);
int add(int a, int b); // Also declare add here

#endif // HEADER_H
