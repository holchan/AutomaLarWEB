module.exports = {
  root: true,
  parser: "@typescript-eslint/parser",
  parserOptions: {
    ecmaVersion: 2020, // Allows for the parsing of modern ECMAScript features
    sourceType: "module", // Allows for the use of imports
    project: ["./tsconfig.json"], // Point to your tsconfig.json
    ecmaFeatures: {
      jsx: true, // Allows for the parsing of JSX
    },
  },
  settings: {
    react: {
      version: "detect", // Tells eslint-plugin-react to automatically detect the version of React to use
    },
  },
  plugins: [
    "@typescript-eslint",
    "react", // Add react plugin if using React in webviews
  ],
  extends: [
    "eslint:recommended",
    "plugin:@typescript-eslint/recommended", // Uses the recommended rules from @typescript-eslint/eslint-plugin
    "plugin:react/recommended", // Uses the recommended rules from @eslint-plugin-react
    "plugin:react-hooks/recommended", // Enforces Rules of Hooks
  ],
  env: {
    node: true, // Node.js global variables and Node.js scoping.
    es6: true, // Enable ES6 features automatically.
    browser: true, // Add browser globals for webview code if needed
  },
  rules: {
    // Place to specify ESLint rules. Can be used to overwrite rules specified from the extended configs
    // e.g. "@typescript-eslint/explicit-function-return-type": "off",
    "@typescript-eslint/no-unused-vars": ["warn", { argsIgnorePattern: "^_" }], // Warn about unused vars, except those starting with _
    "@typescript-eslint/no-explicit-any": "warn", // Warn about using 'any' type
    "@typescript-eslint/explicit-module-boundary-types": "off", // Allows exporting functions without explicit return types
    "react/prop-types": "off", // Disable prop-types as we use TypeScript for type checking
    "react/react-in-jsx-scope": "off", // Not needed with React 17+ JSX transform
    "no-console": "warn", // Warn about console.log statements
    // Add specific rules as needed
  },
  ignorePatterns: [
    "out/**/*",
    "node_modules/**/*",
    ".vscode-test/**/*",
    "*.vsix",
    "media/main.js", // Ignore compiled/bundled webview JS if applicable
  ],
};
