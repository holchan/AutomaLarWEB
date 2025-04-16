import * as vscode from "vscode";
import * as path from "path";
import * as os from "os";
import * as fs from "fs"; // Import fs for existsSync

console.log("TaskService: Loading module...");

// --- Types adapted from Roo Code ---
// Basic structure based on observed api_conversation_history.json and export-markdown.ts
// We might need to refine these as we implement the parsing logic.
interface RooMessageContentBlock {
  type: "text" | "image" | "tool_use" | "tool_result" | string; // Allow other types
  text?: string;
  source?: { media_type?: string; data?: string }; // For images
  name?: string; // For tool use/result
  input?: any; // For tool use
  id?: string; // For tool use/result
  content?: string | RooMessageContentBlock[]; // For tool result
  is_error?: boolean; // For tool result
}

interface RooMessageParam {
  role: "user" | "assistant";
  content: string | RooMessageContentBlock[];
}

interface RooTaskMetadata {
  id: string;
  number: number;
  ts: number; // Timestamp for the task start - crucial for filename
  task: string; // Initial prompt/task description
  tokensIn?: number;
  tokensOut?: number;
  totalCost?: number;
  size?: number;
  workspace?: string;
  // Add other fields if needed based on task_metadata.json inspection
}

// --- End Types ---

export class TaskService {
  private context: vscode.ExtensionContext;

  constructor(context: vscode.ExtensionContext) {
    console.log("TaskService: constructor called.");
    this.context = context;
  }

  // --- Configuration Helpers ---

  private getConfiguration() {
    // console.log("TaskService: getConfiguration() called."); // Too noisy maybe
    return vscode.workspace.getConfiguration("ai-task-history");
  }

  private getRooTasksPathOverride(): string | null {
    const override = this.getConfiguration().get<string | null>(
      "rooTasksPathOverride",
      null
    );
    // console.log(`TaskService: getRooTasksPathOverride() returning: ${override}`); // Too noisy
    return override;
  }

  // --- Path Management ---

  /**
   * Ensures a directory exists, creating it if necessary.
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
            `Failed to create required directory: ${dirPath}`
          );
          throw createError; // Re-throw to indicate failure
        }
      } else {
        // Log other errors during stat
        console.error(
          `TaskService: Error checking directory ${dirPath}:`,
          error
        );
        throw error; // Re-throw other errors
      }
    }
  }

  /**
   * Detects or retrieves the path to the Roo task storage directory.
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
      // Use fs.existsSync for synchronous check before async operations
      if (fs.existsSync(overridePath)) {
        try {
          const stats = await vscode.workspace.fs.stat(
            vscode.Uri.file(overridePath)
          );
          if (stats.type === vscode.FileType.Directory) {
            console.log(
              `TaskService: Using valid overridden path: ${overridePath}`
            );
            basePath = overridePath;
          } else {
            console.warn(
              `TaskService: Overridden path ${overridePath} exists but is not a directory. Falling back to auto-detection.`
            );
            vscode.window.showWarningMessage(
              `The configured 'Roo Tasks Path Override' (${overridePath}) is not a directory. Trying auto-detection.`
            );
          }
        } catch (statError) {
          // Handle potential errors during stat, e.g., permission issues
          console.warn(
            `TaskService: Error stating overridden path ${overridePath}:`,
            statError
          );
          vscode.window.showWarningMessage(
            `Could not verify the configured 'Roo Tasks Path Override' (${overridePath}). Trying auto-detection.`
          );
        }
      } else {
        console.warn(
          `TaskService: Overridden path ${overridePath} does not exist. Falling back to auto-detection.`
        );
        vscode.window.showWarningMessage(
          `The configured 'Roo Tasks Path Override' (${overridePath}) was not found. Trying auto-detection.`
        );
      }
    }

    if (!basePath) {
      console.log("TaskService: Starting auto-detection of Roo tasks path...");
      // Common locations for Roo Code task storage
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
        // VS Code (Linux)
        path.join(
          os.homedir(),
          ".config",
          "Code",
          "User",
          "globalStorage",
          "rooveterinaryinc.roo-cline"
        ),
        // VS Code (macOS)
        path.join(
          os.homedir(),
          "Library",
          "Application Support",
          "Code",
          "User",
          "globalStorage",
          "rooveterinaryinc.roo-cline"
        ),
        // VS Code (Windows)
        path.join(
          os.homedir(),
          "AppData",
          "Roaming",
          "Code",
          "User",
          "globalStorage",
          "rooveterinaryinc.roo-cline"
        ),
        // Flatpak installations
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
        // --- Insiders Versions --- (Add if needed, check common paths)
      ];

      for (const p of possiblePaths) {
        // console.log(`TaskService: Checking possible path: ${p}`); // Verbose
        if (await this.isValidDirectory(p)) {
          console.log(`TaskService: Auto-detected Roo tasks path: ${p}`);
          basePath = p;
          break; // Found a valid path
        }
      }
      console.log("TaskService: Auto-detection finished.");
    }

    if (basePath) {
      console.log(
        `TaskService: Ensuring required subdirectories under: ${basePath}`
      );
      try {
        // Ensure base path exists (should already, but good practice)
        await this.ensureDirectoryExists(basePath);
        // Ensure 'tasks' subdirectory exists
        await this.ensureDirectoryExists(path.join(basePath, "tasks"));
        // REMOVED check/creation for 'exports' directory
        console.log(`TaskService: Required subdirectories ensured.`);
        return basePath;
      } catch (error) {
        console.error(
          `TaskService: Failed to ensure required subdirectories exist under ${basePath}.`,
          error
        );
        vscode.window.showErrorMessage(
          `Failed to ensure required Roo directories exist. Check permissions for ${basePath}.`
        );
        return null; // Failed to ensure directories
      }
    } else {
      console.error(
        "TaskService: Could not detect or validate Roo Code tasks path. Please configure it manually in settings."
      );
      vscode.window.showErrorMessage(
        "Could not find the Roo task storage directory. Please set the 'AI Task History: Roo Tasks Path Override' setting if needed."
      );
      return null;
    }
  }

  private async isValidDirectory(dirPath: string): Promise<boolean> {
    // console.log(`TaskService: isValidDirectory() called for: ${dirPath}`); // Very verbose
    try {
      // Use fs.existsSync for a quick check first
      if (!fs.existsSync(dirPath)) {
        // console.log(`TaskService: isValidDirectory - ${dirPath} does not exist (fs.existsSync).`); // Verbose
        return false;
      }
      // If it exists, then perform the async stat to confirm it's a directory
      const stats = await vscode.workspace.fs.stat(vscode.Uri.file(dirPath));
      // console.log(`TaskService: stat successful for ${dirPath}, type: ${stats.type}`); // Verbose
      return stats.type === vscode.FileType.Directory;
    } catch (error) {
      // Catch errors from fs.stat specifically (e.g., permissions)
      if (
        !(
          error instanceof vscode.FileSystemError &&
          error.code === "FileNotFound"
        )
      ) {
        // Log errors other than FileNotFound (which is handled by existsSync)
        console.warn(`TaskService: Error during stat for ${dirPath}:`, error);
      } else {
        // This case should ideally not be reached if existsSync is false, but included for safety
        // console.log(`TaskService: stat failed for ${dirPath} (FileNotFound, expected during checks).`); // Verbose
      }
      return false;
    }
  }

  /**
   * Discovers task UUIDs by listing directories in the tasks subfolder.
   * Returns an array of task UUID strings.
   */
  public async discoverTaskIds(): Promise<string[]> {
    console.log("TaskService: discoverTaskIds() called.");
    const rooTasksPath = await this.getRooTasksPath(); // This now ensures subdirs exist
    if (!rooTasksPath) {
      console.error(
        "TaskService: Roo tasks path could not be determined for discovery. Cannot discover task IDs."
      );
      return [];
    }

    let taskIds: string[] = [];
    const actualTasksDirPath = path.join(rooTasksPath, "tasks");

    try {
      console.log(
        "TaskService: Discovering task IDs via directory listing in:",
        actualTasksDirPath
      );

      // Re-check if tasks dir exists, although getRooTasksPath should have created it
      if (!(await this.isValidDirectory(actualTasksDirPath))) {
        console.warn(
          `TaskService: 'tasks' subdirectory not found at ${actualTasksDirPath} even after check. Cannot discover tasks.`
        );
        return [];
      }

      console.log(
        `TaskService: Reading directory entries for ${actualTasksDirPath}...`
      );
      const entries = await vscode.workspace.fs.readDirectory(
        vscode.Uri.file(actualTasksDirPath)
      );
      console.log(
        `TaskService: Found ${entries.length} entries in tasks subdirectory.`
      );

      for (const [entryName, entryType] of entries) {
        // console.log(`TaskService: Processing entry: ${entryName}, type: ${entryType}`); // Verbose
        if (entryType === vscode.FileType.Directory) {
          // Basic UUID check (adjust if Roo's format is different)
          if (
            /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i.test(
              entryName
            )
          ) {
            taskIds.push(entryName);
            // console.log(`TaskService: Added potential task ID: ${entryName}`); // Verbose
          } else {
            // Only warn if it's not the known 'checkpoints' folder name pattern
            if (!entryName.startsWith("checkpoints")) {
              console.warn(
                `TaskService: Skipping entry '${entryName}' as it doesn't look like a standard UUID directory.`
              );
            }
          }
        } else {
          // console.log(`TaskService: Skipping non-directory entry: ${entryName}`); // Verbose
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
    // Sort tasks reverse chronologically based on UUID structure (less reliable than timestamp)
    // A better approach would be to read metadata for each task, but that's slower.
    taskIds.sort().reverse(); // Simple reverse alphabetical sort for now
    return taskIds;
  }

  // --- Manual Export Implementation ---

  /**
   * Reads task data, formats it as markdown, and prompts the user to save it.
   */
  public async exportTaskManually(taskId: string): Promise<void> {
    console.log(`TaskService: exportTaskManually() called for task ${taskId}.`);
    const rooTasksPath = await this.getRooTasksPath();
    if (!rooTasksPath) {
      console.error(
        "TaskService: Cannot export manually, Roo tasks path not found."
      );
      vscode.window.showErrorMessage(
        "Could not determine Roo tasks path for export."
      );
      return;
    }

    const taskDirPath = path.join(rooTasksPath, "tasks", taskId);
    const metadataPath = path.join(taskDirPath, "task_metadata.json");
    const historyPath = path.join(taskDirPath, "api_conversation_history.json");

    let metadata: RooTaskMetadata | null = null;
    let conversationHistory: RooMessageParam[] = [];

    try {
      // --- Read Metadata ---
      console.log(`TaskService: Reading metadata from ${metadataPath}...`);
      if (!fs.existsSync(metadataPath)) {
        throw new Error(`Metadata file not found: ${metadataPath}`);
      }
      const metadataContent = await vscode.workspace.fs.readFile(
        vscode.Uri.file(metadataPath)
      );
      metadata = JSON.parse(
        Buffer.from(metadataContent).toString("utf8")
      ) as RooTaskMetadata;
      if (!metadata || typeof metadata.ts !== "number") {
        throw new Error(
          `Invalid or missing timestamp in metadata: ${metadataPath}`
        );
      }
      console.log(
        `TaskService: Metadata read successfully. Timestamp: ${metadata.ts}`
      );

      // --- Read History ---
      console.log(`TaskService: Reading history from ${historyPath}...`);
      if (!fs.existsSync(historyPath)) {
        // It's possible a task exists with metadata but no history yet
        console.warn(
          `TaskService: History file not found: ${historyPath}. Exporting with empty history.`
        );
        // Allow export to continue, will result in an empty markdown file (or just headers)
      } else {
        const historyContent = await vscode.workspace.fs.readFile(
          vscode.Uri.file(historyPath)
        );
        conversationHistory = JSON.parse(
          Buffer.from(historyContent).toString("utf8")
        ) as RooMessageParam[];
        console.log(
          `TaskService: History read successfully. ${conversationHistory.length} messages.`
        );
      }

      // --- Generate Filename (adapted from Roo Code) ---
      const dateTs = metadata.ts; // Use timestamp from metadata
      const date = new Date(dateTs);
      const month = date
        .toLocaleString("en-US", { month: "short" })
        .toLowerCase();
      const day = date.getDate();
      const year = date.getFullYear();
      let hours = date.getHours();
      const minutes = date.getMinutes().toString().padStart(2, "0");
      const seconds = date.getSeconds().toString().padStart(2, "0");
      const ampm = hours >= 12 ? "pm" : "am";
      hours = hours % 12;
      hours = hours ? hours : 12; // the hour '0' should be '12'
      const defaultFileName = `cline_task_${month}-${day}-${year}_${hours}-${minutes}-${seconds}-${ampm}.md`;
      console.log(
        `TaskService: Generated default filename: ${defaultFileName}`
      );

      // --- Generate Markdown Content (adapted from Roo Code) ---
      const markdownContent = conversationHistory
        .map((message) => {
          // Basic validation
          if (!message || !message.role || !message.content) {
            console.warn(
              "TaskService: Skipping invalid message structure:",
              message
            );
            return null; // Skip invalid messages
          }
          const role = message.role === "user" ? "**User:**" : "**Assistant:**";
          const content = Array.isArray(message.content)
            ? message.content
                .map((block) => this.formatContentBlockToMarkdown(block)) // Use the helper method
                .join("\n\n") // Use double newline between blocks for better spacing
            : typeof message.content === "string"
            ? message.content
            : "[Unsupported Content Format]"; // Handle plain string content
          return `${role}\n\n${content}\n\n`; // Add double newline after role and content
        })
        .filter(Boolean) // Remove null entries from skipped messages
        .join("---\n\n"); // Separator between messages
      console.log(
        `TaskService: Generated markdown content (length: ${markdownContent.length}).`
      );

      // --- Prompt user for save location ---
      console.log(`TaskService: Prompting user for save location...`);
      const saveUri = await vscode.window.showSaveDialog({
        filters: { Markdown: ["md"] },
        defaultUri: vscode.Uri.file(
          path.join(os.homedir(), "Downloads", defaultFileName) // Default to Downloads
        ),
        saveLabel: "Export Task History",
        title: `Export Roo Task (${taskId})`,
      });

      if (saveUri) {
        console.log(
          `TaskService: User selected save location: ${saveUri.fsPath}`
        );
        // Write content to the selected location
        await vscode.workspace.fs.writeFile(
          saveUri,
          Buffer.from(markdownContent)
        );
        console.log(
          `TaskService: Markdown file successfully saved to ${saveUri.fsPath}.`
        );
        vscode.window.showInformationMessage(
          `Task ${taskId} exported successfully to ${path.basename(
            saveUri.fsPath
          )}`
        );
        // Optionally open the saved file
        // vscode.window.showTextDocument(saveUri, { preview: true });
      } else {
        console.log("TaskService: User cancelled save dialog.");
      }
    } catch (error) {
      console.error(
        `TaskService: Failed to manually export task ${taskId}:`,
        error
      );
      // Provide more specific feedback based on the error type
      let errorMessage = `Failed to export task ${taskId}.`;
      if (error instanceof Error) {
        if (error.message.includes("Metadata file not found")) {
          errorMessage = `Could not find metadata for task ${taskId}. It might be corrupted or incomplete.`;
        } else if (error.message.includes("History file not found")) {
          errorMessage = `Could not find history file for task ${taskId}. It might be corrupted or incomplete.`;
        } else if (error.message.includes("Invalid or missing timestamp")) {
          errorMessage = `Metadata for task ${taskId} is missing a valid timestamp. Cannot generate filename.`;
        } else if (error instanceof SyntaxError) {
          errorMessage = `Failed to parse task data for ${taskId}. Files might be corrupted.`;
        } else {
          errorMessage = `Failed to export task ${taskId}: ${error.message}`;
        }
      } else {
        errorMessage = `Failed to export task ${taskId}: ${String(error)}`;
      }
      vscode.window.showErrorMessage(errorMessage);
    }
  }

  /**
   * Formats a single content block from Roo's conversation history into Markdown.
   * Adapted directly from Roo Code's export-markdown.ts.
   */
  private formatContentBlockToMarkdown(block: RooMessageContentBlock): string {
    // Add basic validation for the block structure
    if (!block || typeof block.type !== "string") {
      console.warn("TaskService: Skipping invalid content block:", block);
      return "[Invalid Content Block]";
    }

    switch (block.type) {
      case "text":
        return block.text ?? ""; // Handle potentially undefined text
      case "image":
        // You might want to include more info if available, e.g., media type
        // For now, keep it simple like Roo Code
        return `[Image]`; // Simple placeholder
      case "tool_use":
        let inputStr: string;
        // Safely handle different input types
        if (typeof block.input === "object" && block.input !== null) {
          try {
            // Format object inputs nicely, handle potential circular references during stringify
            inputStr = Object.entries(block.input)
              .map(
                ([key, value]) =>
                  `${
                    key.charAt(0).toUpperCase() + key.slice(1)
                  }: ${JSON.stringify(value, null, 2)}` // Pretty print JSON
              )
              .join("\n");
          } catch (e) {
            console.warn(
              "TaskService: Could not stringify tool input object:",
              e
            );
            inputStr = "[Could not display tool input object]";
          }
        } else if (block.input !== undefined && block.input !== null) {
          inputStr = String(block.input); // Convert other non-nullish types to string
        } else {
          inputStr = "[No Input Provided]";
        }
        // Include the tool name and formatted input within a code block
        return `\`\`\`tool_use\nTool: ${
          block.name || "Unknown Tool"
        }\nInput:\n${inputStr}\n\`\`\``;
      case "tool_result":
        const toolName = block.name || "Tool"; // Use name if available
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

  // Removed triggerExportCommand and deleteExportedFile methods
} // End of TaskService class

console.log("TaskService: Module loaded.");
