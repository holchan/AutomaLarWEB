import * as vscode from "vscode";
import * as path from "path";
import * as os from "os";
// Removed 'fs' import as we'll rely solely on vscode.workspace.fs

// Define our extension's ID for global storage path
const EXTENSION_ID = "automalar.dev-aid"; // As per design doc

console.log("TaskService: Loading module...");

// --- Types adapted from Roo Code ---
interface RooMessageContentBlock {
  type: "text" | "image" | "tool_use" | "tool_result" | string;
  text?: string;
  source?: { media_type?: string; data?: string };
  name?: string;
  input?: any;
  id?: string;
  content?: string | RooMessageContentBlock[];
  is_error?: boolean;
}

interface RooMessageParam {
  role: "user" | "assistant";
  content: string | RooMessageContentBlock[];
}

interface RooTaskMetadata {
  id: string;
  number: number;
  ts: number; // Timestamp for the task start
  task: string; // Initial prompt/task description
  tokensIn?: number;
  tokensOut?: number;
  totalCost?: number;
  size?: number;
  workspace?: string;
}
// --- End Types ---

// Define the possible statuses for a task export
export type TaskStatus = "new" | "synced" | "out_of_sync" | "error";

export class TaskService {
  private context: vscode.ExtensionContext;

  constructor(context: vscode.ExtensionContext) {
    console.log("TaskService: constructor called.");
    this.context = context;
    if (!context || !context.globalStorageUri) {
      console.error(
        "TaskService FATAL: Extension context or globalStorageUri is unavailable during construction."
      );
      // Consider throwing an error or setting a 'disabled' state
    }
  }

  // --- Configuration Helpers ---

  private getConfiguration() {
    return vscode.workspace.getConfiguration("ai-task-history");
  }

  private getRooTasksPathOverride(): string | null {
    return this.getConfiguration().get<string | null>(
      "rooTasksPathOverride",
      null
    );
  }

  // --- Path Management ---

  /**
   * Gets the absolute path to this extension's dedicated export directory
   * within VS Code's global storage.
   */
  public getTargetPath(): string {
    // Changed from private to public
    if (!this.context.globalStorageUri) {
      console.error("TaskService: globalStorageUri is unavailable.");
      throw new Error(
        "Extension context is not available for determining storage path."
      );
    }
    const storagePath = this.context.globalStorageUri.fsPath;
    // Note: The directory name uses EXTENSION_ID which is 'automalar.dev-aid'
    const targetDir = path.join(storagePath, "task_exports");
    return targetDir;
  }

  /**
   * Ensures a directory exists, creating it if necessary using vscode.workspace.fs.
   */
  private async ensureDirectoryExists(dirPath: string): Promise<void> {
    console.log(`TaskService: ensureDirectoryExists() called for: ${dirPath}`);
    try {
      await vscode.workspace.fs.stat(vscode.Uri.file(dirPath));
      console.log(`TaskService: Directory already exists: ${dirPath}`);
    } catch (error) {
      if (
        error instanceof vscode.FileSystemError &&
        error.code === "FileNotFound"
      ) {
        console.log(`TaskService: Directory not found, creating: ${dirPath}`);
        try {
          await vscode.workspace.fs.createDirectory(vscode.Uri.file(dirPath));
          console.log(
            `TaskService: Successfully created directory: ${dirPath}`
          );
        } catch (createError) {
          console.error(
            `TaskService: Failed to create directory ${dirPath}:`,
            createError
          );
          vscode.window.showErrorMessage(
            // Show message outside try block
            `Failed to create required directory: ${dirPath}`
          );
          throw createError;
        }
      } else {
        console.error(
          `TaskService: Error checking directory ${dirPath}:`,
          error
        );
        throw error;
      }
    }
  }

  /**
   * Detects or retrieves the path to the Roo task storage directory (Source).
   * Uses the override setting first, then attempts auto-detection.
   * Ensures the base path and the 'tasks' subdirectory exist.
   */
  public async getRooTasksPath(): Promise<string | null> {
    console.log("TaskService: getRooTasksPath() called.");
    let basePath: string | null = null;
    const overridePath = this.getRooTasksPathOverride();

    if (overridePath) {
      console.log(
        `TaskService: Checking overridden Roo tasks path: ${overridePath}`
      );
      if (await this.isValidDirectory(overridePath)) {
        console.log(
          `TaskService: Using valid overridden path: ${overridePath}`
        );
        basePath = overridePath;
      } else {
        console.warn(
          `TaskService: Overridden path ${overridePath} is invalid or not a directory. Falling back to auto-detection.`
        );
        vscode.window.showWarningMessage(
          `The configured 'Roo Tasks Path Override' (${overridePath}) is invalid. Trying auto-detection.`
        );
      }
    }

    if (!basePath) {
      console.log("TaskService: Starting auto-detection of Roo tasks path...");
      const possiblePaths = [
        // VS Code Server (Remote Development) - Most likely in devcontainer
        path.join(
          os.homedir(),
          ".vscode-server",
          "data",
          "User",
          "globalStorage",
          "rooveterinaryinc.roo-cline"
        ),
        // Other common paths... (Linux, macOS, Windows, Flatpak) - Copied from previous version
        path.join(
          os.homedir(),
          ".config",
          "Code",
          "User",
          "globalStorage",
          "rooveterinaryinc.roo-cline"
        ),
        path.join(
          os.homedir(),
          "Library",
          "Application Support",
          "Code",
          "User",
          "globalStorage",
          "rooveterinaryinc.roo-cline"
        ),
        path.join(
          os.homedir(),
          "AppData",
          "Roaming",
          "Code",
          "User",
          "globalStorage",
          "rooveterinaryinc.roo-cline"
        ),
        path.join(
          os.homedir(),
          ".var",
          "app",
          "com.visualstudio.code",
          "config",
          "Code",
          "User",
          "globalStorage",
          "rooveterinaryinc.roo-cline"
        ),
      ];

      for (const p of possiblePaths) {
        if (await this.isValidDirectory(p)) {
          console.log(`TaskService: Auto-detected Roo tasks path: ${p}`);
          basePath = p;
          break;
        }
      }
      console.log("TaskService: Auto-detection finished.");
    }

    if (basePath) {
      console.log(
        `TaskService: Ensuring required subdirectories under: ${basePath}`
      );
      try {
        await this.ensureDirectoryExists(basePath);
        await this.ensureDirectoryExists(path.join(basePath, "tasks"));
        console.log(`TaskService: Required source subdirectories ensured.`);
        return basePath; // Return the base path, not the 'tasks' subpath directly
      } catch (error) {
        console.error(
          `TaskService: Failed to ensure required source subdirectories exist under ${basePath}.`,
          error
        );
        vscode.window.showErrorMessage(
          `Failed to ensure required Roo directories exist. Check permissions for ${basePath}.`
        );
        return null;
      }
    } else {
      console.error(
        "TaskService: Could not detect or validate Roo Code tasks path."
      );
      vscode.window.showErrorMessage(
        "Could not find the Roo task storage directory. Please set the 'AI Task History: Roo Tasks Path Override' setting if needed."
      );
      return null;
    }
  }

  /** Checks if a path exists and is a directory using vscode.workspace.fs */
  private async isValidDirectory(dirPath: string): Promise<boolean> {
    try {
      const stats = await vscode.workspace.fs.stat(vscode.Uri.file(dirPath));
      return stats.type === vscode.FileType.Directory;
    } catch (error) {
      if (
        !(
          error instanceof vscode.FileSystemError &&
          error.code === "FileNotFound"
        )
      ) {
        console.warn(`TaskService: Error during stat for ${dirPath}:`, error);
      }
      return false;
    }
  }

  /**
   * Discovers task UUIDs by listing directories in the source tasks subfolder.
   */
  public async discoverTaskIds(): Promise<string[]> {
    console.log("TaskService: discoverTaskIds() called.");
    const rooTasksBasePath = await this.getRooTasksPath();
    if (!rooTasksBasePath) {
      console.error(
        "TaskService: Roo tasks base path could not be determined. Cannot discover task IDs."
      );
      return [];
    }

    const actualTasksDirPath = path.join(rooTasksBasePath, "tasks");
    let taskIds: string[] = [];

    try {
      console.log(
        "TaskService: Discovering task IDs via directory listing in:",
        actualTasksDirPath
      );
      if (!(await this.isValidDirectory(actualTasksDirPath))) {
        console.warn(
          `TaskService: 'tasks' subdirectory not found at ${actualTasksDirPath}. Cannot discover tasks.`
        );
        return [];
      }

      const entries = await vscode.workspace.fs.readDirectory(
        vscode.Uri.file(actualTasksDirPath)
      );
      console.log(
        `TaskService: Found ${entries.length} entries in tasks subdirectory.`
      );

      for (const [entryName, entryType] of entries) {
        if (entryType === vscode.FileType.Directory) {
          // Basic UUID check
          if (
            /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i.test(
              entryName
            )
          ) {
            taskIds.push(entryName);
          } else if (!entryName.startsWith("checkpoints")) {
            // Ignore known non-task folders
            console.warn(
              `TaskService: Skipping entry '${entryName}' as it doesn't look like a standard UUID directory.`
            );
          }
        }
      }
    } catch (error) {
      console.error(
        `TaskService: Error discovering tasks in ${actualTasksDirPath}:`,
        error
      );
      vscode.window.showErrorMessage(
        `Error discovering Roo tasks. Ensure the path is correct and accessible.`
      );
      return [];
    }

    console.log(
      `TaskService: Finished discovery. Found ${taskIds.length} potential task IDs.`
    );
    taskIds.sort().reverse(); // Simple reverse alphabetical sort
    return taskIds;
  }

  // --- Automated Export Implementation ---

  /**
   * Reads source task data (metadata, history), generates markdown,
   * and writes it to the dedicated target export directory.
   * This is the core function for the automated workflow.
   */
  public async processAndExportTask(taskId: string): Promise<string | null> {
    console.log(
      `TaskService: processAndExportTask() called for task ${taskId}.`
    );
    const rooTasksBasePath = await this.getRooTasksPath();
    if (!rooTasksBasePath) {
      console.error(
        `TaskService: Cannot process task ${taskId}, Roo tasks path not found.`
      );
      return null; // Indicate failure
    }

    const taskDirPath = path.join(rooTasksBasePath, "tasks", taskId);
    const metadataPath = path.join(taskDirPath, "task_metadata.json");
    const historyPath = path.join(taskDirPath, "api_conversation_history.json");

    let metadata: RooTaskMetadata | null = null;
    let conversationHistory: RooMessageParam[] = [];
    let markdownContent = "";

    try {
      // --- Read Metadata (Optional) ---
      try {
        console.log(`TaskService: Reading metadata from ${metadataPath}...`);
        const metadataContentBytes = await vscode.workspace.fs.readFile(
          vscode.Uri.file(metadataPath)
        );
        metadata = JSON.parse(
          Buffer.from(metadataContentBytes).toString("utf8")
        ) as RooTaskMetadata;
        console.log(`TaskService: Metadata read successfully for ${taskId}.`);
        // Add timestamp if missing (important for status checks later)
        if (metadata && typeof metadata.ts !== "number") {
          metadata.ts = Date.now(); // Use current time as fallback
          console.warn(
            `TaskService: Added missing timestamp to metadata for ${taskId}`
          );
        }
      } catch (error) {
        if (
          error instanceof vscode.FileSystemError &&
          error.code === "FileNotFound"
        ) {
          console.warn(
            `TaskService: Metadata file not found for task ${taskId}: ${metadataPath}. Proceeding without it.`
          );
          metadata = {
            id: taskId,
            number: 0,
            ts: Date.now(),
            task: "[Metadata Missing]",
          }; // Create placeholder metadata
        } else {
          console.error(
            `TaskService: Error reading metadata for task ${taskId}:`,
            error
          );
          // Decide if we should throw or continue with placeholder
          metadata = {
            id: taskId,
            number: 0,
            ts: Date.now(),
            task: "[Metadata Error]",
          };
        }
      }

      // --- Read History ---
      try {
        console.log(`TaskService: Reading history from ${historyPath}...`);
        const historyContentBytes = await vscode.workspace.fs.readFile(
          vscode.Uri.file(historyPath)
        );
        conversationHistory = JSON.parse(
          Buffer.from(historyContentBytes).toString("utf8")
        ) as RooMessageParam[];
        console.log(
          `TaskService: History read successfully for ${taskId}. ${conversationHistory.length} messages.`
        );
      } catch (error) {
        if (
          error instanceof vscode.FileSystemError &&
          error.code === "FileNotFound"
        ) {
          console.warn(
            `TaskService: History file not found for task ${taskId}: ${historyPath}. Exporting empty history.`
          );
          // Continue with empty history
        } else {
          console.error(
            `TaskService: Error reading history for task ${taskId}:`,
            error
          );
          // Decide if we should throw or continue with empty history
          vscode.window.showWarningMessage(
            `Could not read history for task ${taskId}. Export may be incomplete.`
          );
        }
      }

      // --- Generate Markdown Content ---
      // Add a header with metadata if available
      let header = `<!-- Task ID: ${taskId} -->\n`;
      if (metadata) {
        header += `# Task: ${metadata.task || "[No Task Description]"}\n`;
        header += `*   **ID:** ${metadata.id}\n`;
        header += `*   **Timestamp:** ${new Date(
          metadata.ts
        ).toLocaleString()}\n`;
        // Add other metadata fields if desired
        header += `\n---\n\n`;
      }

      const historyMarkdown = conversationHistory
        .map((message) => {
          if (!message || !message.role || !message.content) {
            console.warn(
              "TaskService: Skipping invalid message structure:",
              message
            );
            return null;
          }
          const role = message.role === "user" ? "**User:**" : "**Assistant:**";
          const content = Array.isArray(message.content)
            ? message.content
                .map((block) => this.formatContentBlockToMarkdown(block))
                .join("\n\n")
            : typeof message.content === "string"
            ? message.content
            : "[Unsupported Content Format]";
          return `${role}\n\n${content}\n\n`;
        })
        .filter(Boolean)
        .join("---\n\n");

      markdownContent = header + historyMarkdown;
      console.log(
        `TaskService: Generated markdown content for ${taskId} (length: ${markdownContent.length}).`
      );

      // --- Write to Target Export Directory ---
      const targetDir = this.getTargetPath();
      const targetFilename = `${taskId}.md`; // Use UUID as filename
      const targetExportPath = path.join(targetDir, targetFilename);

      console.log(
        `TaskService: Preparing to write export for ${taskId} to: ${targetExportPath}`
      );
      await this.ensureDirectoryExists(targetDir); // Ensure target dir exists

      await vscode.workspace.fs.writeFile(
        vscode.Uri.file(targetExportPath),
        Buffer.from(markdownContent, "utf8")
      );
      console.log(
        `TaskService: Successfully exported task ${taskId} to: ${targetExportPath}`
      );
      return targetExportPath; // Return the path of the exported file
    } catch (error) {
      console.error(
        `TaskService: Failed to process and export task ${taskId}:`,
        error
      );
      vscode.window.showErrorMessage(
        `Failed to automatically export task ${taskId}. Check logs for details.`
      );
      return null; // Indicate failure
    }
  }

  /**
   * Formats a single content block from Roo's conversation history into Markdown.
   */
  private formatContentBlockToMarkdown(block: RooMessageContentBlock): string {
    if (!block || typeof block.type !== "string") {
      console.warn("TaskService: Skipping invalid content block:", block);
      return "[Invalid Content Block]";
    }

    switch (block.type) {
      case "text":
        return block.text ?? "";
      case "image":
        return `[Image]`; // Placeholder
      case "tool_use":
        let inputStr: string;
        try {
          inputStr =
            typeof block.input === "object" && block.input !== null
              ? JSON.stringify(block.input, null, 2) // Pretty print JSON
              : block.input !== undefined && block.input !== null
              ? String(block.input)
              : "[No Input Provided]";
        } catch (e) {
          console.warn("TaskService: Could not stringify tool input:", e);
          inputStr = "[Could not display tool input]";
        }
        return `\`\`\`tool_use\nTool: ${
          block.name || "Unknown Tool"
        }\nInput:\n${inputStr}\n\`\`\``;
      case "tool_result":
        const toolName = block.name || "Tool";
        let resultStr: string;
        // Handle string content
        if (typeof block.content === "string") {
          resultStr = block.content;
        }
        // Handle array of content blocks (recursive formatting)
        else if (Array.isArray(block.content)) {
          resultStr = block.content
            .map((contentBlock) =>
              this.formatContentBlockToMarkdown(contentBlock)
            )
            .join("\n");
        }
        // Handle cases where content might be missing or of unexpected type
        else if (block.content === undefined || block.content === null) {
          resultStr = "[No Result Content]";
        } else {
          // Attempt to stringify other types, but be cautious
          try {
            resultStr = JSON.stringify(block.content, null, 2);
          } catch (e) {
            console.warn(
              "TaskService: Could not stringify tool result content:",
              e
            );
            resultStr = "[Unsupported tool result content format]";
          }
        }
        // Indicate if it was an error result, within a code block
        return `\`\`\`tool_result\nResult from: ${toolName}${
          block.is_error ? " (Error)" : ""
        }\n${resultStr}\n\`\`\``;
      default:
        // Fallback for unknown content types, include the type for debugging
        console.warn(
          `TaskService: Encountered unknown content block type: ${block.type}`
        );
        return `[Unsupported content type: ${block.type}]`;
    }
  }

  /**
   * Determines the synchronization status of a task's export file
   * by comparing source file timestamps with the export file timestamp.
   * @param taskId The UUID of the task.
   * @returns The calculated TaskStatus.
   */
  public async getTaskStatus(taskId: string): Promise<TaskStatus> {
    console.log(`TaskService: getTaskStatus() called for task ${taskId}.`);
    const rooTasksBasePath = await this.getRooTasksPath();
    if (!rooTasksBasePath) {
      console.error(
        `TaskService: Cannot get status for task ${taskId}, Roo tasks path not found.`
      );
      return "error";
    }

    const taskDirPath = path.join(rooTasksBasePath, "tasks", taskId);
    const metadataPath = path.join(taskDirPath, "task_metadata.json");
    const historyPath = path.join(taskDirPath, "api_conversation_history.json");
    const exportPath = path.join(this.getTargetPath(), `${taskId}.md`);

    let sourceMtime = 0;
    let exportMtime = -1; // Use -1 to indicate not found initially
    let sourceExists = false;

    try {
      // --- Check Source Files ---
      try {
        const metadataStats = await vscode.workspace.fs.stat(
          vscode.Uri.file(metadataPath)
        );
        sourceMtime = Math.max(sourceMtime, metadataStats.mtime);
        sourceExists = true;
      } catch (error) {
        if (
          !(
            error instanceof vscode.FileSystemError &&
            error.code === "FileNotFound"
          )
        ) {
          console.warn(
            `TaskService [${taskId}]: Error stating metadata file:`,
            error
          );
        } // Ignore FileNotFound for metadata
      }

      try {
        const historyStats = await vscode.workspace.fs.stat(
          vscode.Uri.file(historyPath)
        );
        sourceMtime = Math.max(sourceMtime, historyStats.mtime);
        sourceExists = true;
      } catch (error) {
        if (
          error instanceof vscode.FileSystemError &&
          error.code === "FileNotFound"
        ) {
          // If history is missing but metadata existed, that's okay.
          // If both are missing, sourceExists will remain false.
        } else {
          console.warn(
            `TaskService [${taskId}]: Error stating history file:`,
            error
          );
        }
      }

      if (!sourceExists) {
        console.warn(
          `TaskService [${taskId}]: Neither metadata nor history file found in source directory ${taskDirPath}. Cannot determine status accurately.`
        );
        // If source doesn't exist, we can't really determine status vs export.
        // Let's check if the export exists and treat it as 'error' or 'new'.
        try {
          await vscode.workspace.fs.stat(vscode.Uri.file(exportPath));
          // Export exists but source doesn't? This is an error state.
          return "error";
        } catch (exportStatError) {
          if (
            exportStatError instanceof vscode.FileSystemError &&
            exportStatError.code === "FileNotFound"
          ) {
            // Neither source nor export exists. Could be considered 'new' but is unusual.
            // Let's return 'error' as the source is missing.
            return "error";
          }
          // Error stating the export file itself
          console.error(
            `TaskService [${taskId}]: Error stating export file when source was missing:`,
            exportStatError
          );
          return "error";
        }
      }

      // --- Check Export File ---
      try {
        const exportStats = await vscode.workspace.fs.stat(
          vscode.Uri.file(exportPath)
        );
        exportMtime = exportStats.mtime;
      } catch (error) {
        if (
          error instanceof vscode.FileSystemError &&
          error.code === "FileNotFound"
        ) {
          // Export file doesn't exist, status is 'new'
          console.log(
            `TaskService [${taskId}]: Export file not found. Status: new.`
          );
          return "new";
        } else {
          // Other error stating the export file
          console.error(
            `TaskService [${taskId}]: Error stating export file:`,
            error
          );
          return "error";
        }
      }

      // --- Compare Timestamps ---
      if (exportMtime >= sourceMtime) {
        console.log(
          `TaskService [${taskId}]: Export is up-to-date. Status: synced.`
        );
        return "synced";
      } else {
        console.log(
          `TaskService [${taskId}]: Export is older than source. Status: out_of_sync.`
        );
        return "out_of_sync";
      }
    } catch (error) {
      // Catch any unexpected errors during the process
      console.error(
        `TaskService [${taskId}]: Unexpected error during getTaskStatus:`,
        error
      );
      return "error";
    }
  }

  // Removed triggerExportCommand and deleteExportedFile methods
} // End of TaskService class

console.log("TaskService: Module loaded.");
