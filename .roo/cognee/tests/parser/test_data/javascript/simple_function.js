// Simple JS functions
const path = require("path");
import { utils } from "./utils"; // ES6 import

/**
 * Adds two numbers.
 * @param {number} a First number
 * @param {number} b Second number
 * @returns {number} Sum
 */
function add(a, b) {
  return a + b;
}

const multiply = (a, b) => {
  console.log(`Multiplying ${a} and ${b}`);
  utils.logOperation("multiply"); // Use imported util
  return a * b;
};

// Immediately invoked function expression (IIFE)
(function () {
  console.log("IIFE executed");
})();
