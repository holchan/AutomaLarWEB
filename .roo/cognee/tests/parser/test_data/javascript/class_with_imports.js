import fs from "fs/promises";
const { join } = require("path"); // CommonJS require

class FileManager {
  constructor(baseDir) {
    this.baseDir = baseDir || "/tmp";
    console.log(`File Manager initialized for ${this.baseDir}`);
  }

  async readFile(fileName) {
    const filePath = join(this.baseDir, fileName);
    try {
      const content = await fs.readFile(filePath, "utf-8");
      return content;
    } catch (err) {
      console.error(`Error reading file ${filePath}:`, err);
      return null;
    }
  }

  listDirectory() {
    // Example of sync method if needed
    try {
      return require("fs").readdirSync(this.baseDir); // Sync require inside method
    } catch (err) {
      return [];
    }
  }
}

module.exports = FileManager; // CommonJS export
