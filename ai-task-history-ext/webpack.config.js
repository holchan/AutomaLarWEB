const path = require("path");
const CopyPlugin = require("copy-webpack-plugin");

module.exports = {
  entry: "./media/main.js", // Entry point of your React application
  mode: "development", // Or 'production' for optimized builds
  devtool: "inline-source-map", // Helps with debugging in VS Code
  output: {
    filename: "bundle.js", // Output bundle file name
    path: path.resolve(__dirname, "dist"), // Output directory
  },
  module: {
    rules: [
      {
        test: /\.js$/,
        exclude: /node_modules/,
        use: {
          loader: "ts-loader", // Use ts-loader for TypeScript files
          options: {
            transpileOnly: true, // Speeds up build process
          },
        },
      },
    ],
  },
  resolve: {
    extensions: [".js"], // Add .ts and .tsx if you have TypeScript components
  },
  plugins: [
    new CopyPlugin({
      patterns: [
        { from: "media/style.css", to: "style.css" }, // Copy CSS file to dist folder
        { from: "media/icon.svg", to: "icon.svg" }, // Copy icon file to dist folder
        // Add codicon assets
        {
          from: "node_modules/@vscode/codicons/dist/codicon.css",
          to: "codicon.css",
        },
        {
          from: "node_modules/@vscode/codicons/dist/codicon.ttf",
          to: "codicon.ttf",
        },
      ],
    }),
  ],
};
