// Simple Rust module example
use std::collections::HashMap; // Standard library import
use crate::utils::helper; // Crate relative import

mod utils; // Declare submodule

pub struct Point {
    x: i32,
    y: i32,
}

impl Point {
    pub fn new(x: i32, y: i32) -> Self {
        Point { x, y }
    }

    pub fn distance_from_origin(&self) -> f64 {
        ((self.x.pow(2) + self.y.pow(2)) as f64).sqrt()
    }
}

pub enum Status {
    Active,
    Inactive(String), // Enum with data
}

pub trait Summary {
    fn summarize(&self) -> String;
}

impl Summary for Point {
    fn summarize(&self) -> String {
        format!("Point({}, {})", self.x, self.y)
    }
}

// A function using the types
fn process_point(p: Point) -> Status {
    println!("Processing point: {}", p.summarize());
    helper(); // Call helper from utils module
    if p.distance_from_origin() > 10.0 {
        Status::Inactive("Too far".to_string())
    } else {
        Status::Active
    }
}

// Macro definition example
macro_rules! create_map {
    ($($key:expr => $value:expr),* $(,)?) => {
        {
            let mut map = HashMap::new();
            $(
                map.insert($key, $value);
            )*
            map
        }
    };
}

fn main() {
   let p1 = Point::new(3, 4);
   let status = process_point(p1);
   let _my_map = create_map!("a" => 1, "b" => 2); // Macro invocation
}
