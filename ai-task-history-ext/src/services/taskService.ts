import * as vscode from "vscode";
import * as fs from "fs";
import * as path from "path";
import * as os from "os";
import { Task, SyncStatus } from "../models/task";

export class TaskService {
  private context: vscode.ExtensionContext;

  constructor(context: vscode.ExtensionContext) {
    this.context = context;
  }

  // --- Configuration Helpers ---

  private getConfiguration() {
    return vscode.workspace.getConfiguration("ai-task-history");
  }

  private getExportPathSetting(): string {
    return this.getConfiguration().get<string>(
      "exportPath",
      ".roo/task_history_exports"
    );
  }

  private getRooTasksPathOverride(): string | null {
    return this.getConfiguration().get<string | null>(
      "rooTasksPathOverride",
      null
    );
  }

  // --- Path Management ---

  /**
   * Gets the absolute path for exporting task files.
   * Resolves the configured relative path against the first workspace folder.
   * Returns null if no workspace is open.
   */
  public getAbsoluteExportPath(): string | null {
    const relativePath = this.getExportPathSetting();
    const workspaceFolders = vscode.workspace.workspaceFolders;
    if (workspaceFolders && workspaceFolders.length > 0) {
      return path.resolve(workspaceFolders[0].uri.fsPath, relativePath);
    }
    console.warn(
      "No workspace folder found. Cannot determine absolute export path."
    );
    return null; // Cannot determine path without a workspace
  }

  /**
   * Detects or retrieves the path to the Roo task storage directory.
   * Uses the override setting first, then attempts auto-detection.
   */
  public async getRooTasksPath(): Promise<string | null> {
    const overridePath = this.getRooTasksPathOverride();
    if (overridePath && (await this.isValidDirectory(overridePath))) {
      console.log(`Using overridden Roo tasks path: ${overridePath}`);
      return overridePath;
    }

    // Common locations for Roo Code task storage
    // Prioritize non-Insiders versions if both exist
    const possiblePaths = [
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
      // VS Code Server (Remote Development)
      path.join(
        os.homedir(),
        ".vscode-server",
        "data",
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
      // --- Insiders Versions ---
      path.join(
        os.homedir(),
        ".config",
        "Code - Insiders",
        "User",
        "globalStorage",
        "rooveterinaryinc.roo-cline"
      ),
      path.join(
        os.homedir(),
        "Library",
        "Application Support",
        "Code - Insiders",
        "User",
        "globalStorage",
        "rooveterinaryinc.roo-cline"
      ),
      path.join(
        os.homedir(),
        "AppData",
        "Roaming",
        "Code - Insiders",
        "User",
        "globalStorage",
        "rooveterinaryinc.roo-cline"
      ),
      path.join(
        os.homedir(),
        ".vscode-server-insiders",
        "data",
        "User",
        "globalStorage",
        "rooveterinaryinc.roo-cline"
      ),
      path.join(
        os.homedir(),
        ".var",
        "app",
        "com.visualstudio.code-insiders",
        "config",
        "Code - Insiders",
        "User",
        "globalStorage",
        "rooveterinaryinc.roo-cline"
      ),
    ];

    for (const p of possiblePaths) {
      if (await this.isValidDirectory(p)) {
        console.log(`Detected Roo tasks path: ${p}`);
        return p;
      }
    }

    console.warn(
      "Could not detect Roo Code tasks path. Please configure it manually in settings."
    );
    vscode.window.showWarningMessage(
      "Could not automatically detect the Roo task storage directory. Please set the 'AI Task History: Roo Tasks Path Override' setting if needed."
    );
    return null;
  }

  private async isValidDirectory(dirPath: string): Promise<boolean> {
    try {
      const stats = await vscode.workspace.fs.stat(vscode.Uri.file(dirPath));
      return stats.type === vscode.FileType.Directory;
    } catch (error) {
      // Ignore errors like ENOENT (Not Found)
      return false;
    }
  }

  /**
   * Ensures the export directory exists, creating it if necessary.
   * Returns true if the directory exists or was created, false otherwise.
   */
  private async ensureExportDirExists(): Promise<boolean> {
    const exportPath = this.getAbsoluteExportPath();
    if (!exportPath) {
      vscode.window.showErrorMessage(
        "Cannot ensure export directory: No workspace open."
      );
      return false;
    }
    try {
      await vscode.workspace.fs.stat(vscode.Uri.file(exportPath));
      return true; // Directory already exists
    } catch (error) {
      // If error is not "file not found", rethrow it
      if (
        !(
          error instanceof vscode.FileSystemError &&
          error.code === "FileNotFound"
        )
      ) {
        console.error(`Error checking export directory ${exportPath}:`, error);
        const message = error instanceof Error ? error.message : String(error);
        vscode.window.showErrorMessage(
          `Error checking export directory: ${message}`
        );
        return false;
      }
      // Directory does not exist, try to create it
      try {
        await vscode.workspace.fs.createDirectory(vscode.Uri.file(exportPath));
        console.log(`Created task export directory: ${exportPath}`);
        return true;
      } catch (createError) {
        console.error(
          `Error creating export directory ${exportPath}:`,
          createError
        );
        vscode.window.showErrorMessage(
          `Failed to create export directory: ${
            createError instanceof Error
              ? createError.message
              : String(createError)
          }`
        );
        return false;
      }
    }
  }

  // --- Core Task Operations (to be implemented) ---

  /**
   * Retrieves all tasks, comparing source files with exported files.
   */
  public async getTasks(): Promise<Task[]> {
    const rooTasksPath = await this.getRooTasksPath();
    const exportPath = this.getAbsoluteExportPath();

    if (!rooTasksPath) {
      console.error("Roo tasks path could not be determined.");
      return [];
    }
    // Allow proceeding even if exportPath is null, handle null later
    if (!exportPath) {
      console.warn(
        "Export path could not be determined (no workspace open?). Will proceed but exports might not work."
      );
    }

    const tasks: Task[] = [];
    try {
      // START OF MAIN TRY BLOCK
      console.log(`Attempting to read Roo tasks directory: ${rooTasksPath}`); // Log path
      const entries = await vscode.workspace.fs.readDirectory(
        vscode.Uri.file(rooTasksPath)
      );
      console.log(
        `Successfully read directory. Found ${entries.length} entries.`
      ); // Log success
      for (const [filename, fileType] of entries) {
        if (
          fileType === vscode.FileType.File &&
          filename.startsWith("task-") &&
          filename.endsWith(".json")
        ) {
          const taskId = filename.replace("task-", "").replace(".json", "");
          const sourceUri = vscode.Uri.joinPath(
            vscode.Uri.file(rooTasksPath),
            filename
          );
          // Handle null exportPath when creating exportUri
          const exportUri = exportPath
            ? vscode.Uri.joinPath(vscode.Uri.file(exportPath), `${taskId}.md`)
            : null;

          try {
            const sourceStats = await vscode.workspace.fs.stat(sourceUri);
            let exportStats: vscode.FileStat | null = null;
            let syncStatus: SyncStatus;

            // Determine sync status, handling null exportUri
            if (exportUri) {
              try {
                exportStats = await vscode.workspace.fs.stat(exportUri);
                // Basic timestamp comparison: Exported file should be newer or equal
                if (exportStats.mtime >= sourceStats.mtime) {
                  syncStatus = SyncStatus.InSync;
                } else {
                  syncStatus = SyncStatus.OutOfSync;
                }
              } catch (exportError) {
                if (
                  exportError instanceof vscode.FileSystemError &&
                  exportError.code === "FileNotFound"
                ) {
                  syncStatus = SyncStatus.NotExported;
                } else {
                  console.error(
                    `Error stating export file ${exportUri.fsPath}:`,
                    exportError
                  );
                  syncStatus = SyncStatus.Error;
                }
              }
            } else {
              // If export path couldn't be determined, assume not exported
              syncStatus = SyncStatus.NotExported;
            }

            // Attempt to read title from JSON content (optional, could be slow for many files)
            let title = `Task ${taskId}`;
            try {
              const contentBytes = await vscode.workspace.fs.readFile(
                sourceUri
              );
              const contentString = Buffer.from(contentBytes).toString("utf8");
              const taskData = JSON.parse(contentString);
              title = taskData?.title || taskData?.task || title; // Look for common title fields
            } catch (readError) {
              console.warn(
                `Could not read or parse ${filename} for title:`,
                readError
              );
            }

            tasks.push({
              id: taskId,
              title: title,
              sourceLastModified: sourceStats.mtime,
              exportLastModified: exportStats?.mtime ?? null,
              syncStatus: syncStatus,
              sourcePath: sourceUri.fsPath,
              exportPath: exportUri?.fsPath ?? "", // Handle null exportUri
              size: sourceStats.size,
            });
          } catch (sourceError) {
            console.error(
              `Error processing source task ${filename}:`,
              sourceError
            );
            // Optionally add an error task entry
          }
        }
      }

      // Check for orphaned export files only if exportPath is valid
      if (exportPath && (await this.isValidDirectory(exportPath))) {
        console.log(`Checking for orphaned exports in: ${exportPath}`);
        const exportEntries = await vscode.workspace.fs.readDirectory(
          vscode.Uri.file(exportPath)
        );
        // Removed extra );
        const sourceTaskIds = new Set(tasks.map((t) => t.id));
        for (const [exportFilename, exportFileType] of exportEntries) {
          if (
            exportFileType === vscode.FileType.File &&
            exportFilename.endsWith(".md")
          ) {
            const exportTaskId = exportFilename.replace(".md", "");
            if (!sourceTaskIds.has(exportTaskId)) {
              const exportUri = vscode.Uri.joinPath(
                vscode.Uri.file(exportPath),
                exportFilename
              );
              try {
                const exportStats = await vscode.workspace.fs.stat(exportUri);
                tasks.push({
                  id: exportTaskId,
                  title: `Orphaned Export: ${exportTaskId}`,
                  sourceLastModified: 0, // No source
                  exportLastModified: exportStats.mtime,
                  syncStatus: SyncStatus.SourceMissing,
                  sourcePath: "", // No source path
                  exportPath: exportUri.fsPath,
                  size: exportStats.size,
                });
              } catch (orphanStatError) {
                console.error(
                  `Error stating orphaned export file ${exportFilename}:`,
                  orphanStatError
                );
              } // End catch orphanStatError
            } // End if !sourceTaskIds.has
          } // End if fileType check
        } // End for loop
      } // End if exportPath && isValidDirectory
      // Add the check for skipping orphan logic here
      else if (exportPath) {
        console.log(
          `Export directory ${exportPath} not found or invalid, skipping orphan check.`
        );
      } else {
        console.log("No export path, skipping orphan check.");
      } // End of main for loop (line 270)
      // END OF MAIN TRY BLOCK - Catch block should follow immediately
    } catch (error) {
      console.error(
        `Error reading Roo tasks directory ${rooTasksPath}:`,
        error
      );
      vscode.window.showErrorMessage(
        `Error reading Roo tasks directory. Ensure the path is correct and accessible.`
      );
      return []; // Return empty on error
    } // END OF CATCH BLOCK

    // These should be outside the try...catch
    console.log(`Finished processing tasks. Found: ${tasks.length}`); // Log final count

    // Sort tasks: prioritize out-of-sync/not-exported, then by source modification date (newest first)
    tasks.sort((a, b) => {
      const statusOrder = (status: SyncStatus): number => {
        switch (status) {
          case SyncStatus.OutOfSync:
            return 1;
          case SyncStatus.NotExported:
            return 2;
          case SyncStatus.SourceMissing:
            return 3;
          case SyncStatus.Error:
            return 4;
          case SyncStatus.InSync:
            return 5;
          default:
            return 6;
        }
      };
      const statusDiff = statusOrder(a.syncStatus) - statusOrder(b.syncStatus);
      if (statusDiff !== 0) return statusDiff;
      // For same status, sort by source date (newest first), or export date if source missing
      const dateA = a.sourceLastModified || a.exportLastModified || 0;
      const dateB = b.sourceLastModified || b.exportLastModified || 0;
      return dateB - dateA;
    });

    return tasks; // Final return
  }

  /**
   * Exports a single task to Markdown. (Implementation needed)
   * Reuses logic from the previous task-exporter/index.js.
   */
  public async exportTask(taskId: string): Promise<boolean> {
    const rooTasksPath = await this.getRooTasksPath();
    const exportDir = this.getAbsoluteExportPath();

    if (!rooTasksPath || !exportDir) {
      vscode.window.showErrorMessage(
        "Cannot export task: Paths not configured correctly."
      );
      return false;
    }
    if (!(await this.ensureExportDirExists())) {
      vscode.window.showErrorMessage(
        "Cannot export task: Failed to create export directory."
      );
      return false;
    }

    const sourceUri = vscode.Uri.joinPath(
      vscode.Uri.file(rooTasksPath),
      `task-${taskId}.json`
    );
    const exportUri = vscode.Uri.joinPath(
      vscode.Uri.file(exportDir),
      `${taskId}.md`
    );

    try {
      // Read the source task JSON using vscode.workspace.fs
      const taskContentBytes = await vscode.workspace.fs.readFile(sourceUri);
      const taskJsonString = Buffer.from(taskContentBytes).toString("utf8");
      const taskData = JSON.parse(taskJsonString);

      // --- Start of Markdown Formatting Logic (adapted from previous implementation) ---
      let markdown = `# ${
        taskData.title || taskData?.task || `Task ${taskId}`
      }\n\n`;
      markdown += `**Task ID:** ${taskId}\n`;
      markdown += `**Created:** ${new Date(
        taskData.createdAt || Date.now()
      ).toISOString()}\n`;
      markdown += `**Updated:** ${new Date(
        taskData.updatedAt || Date.now()
      ).toISOString()}\n`;

      const modeSlug = this.getNestedValue(
        taskData,
        "history.0.mode.slug",
        "unknown"
      );
      markdown += `**Mode:** ${modeSlug}\n\n`;

      const messages = this.getNestedValue(taskData, "history.0.messages", []);
      if (Array.isArray(messages)) {
        messages.forEach((message: any) => {
          // Use 'any' for simplicity here, or define a Message interface
          const role = message.role || "unknown";
          const content = message.content || "";
          const timestamp = message.timestamp
            ? ` (${new Date(message.timestamp).toISOString()})`
            : "";

          switch (role.toLowerCase()) {
            case "user":
              markdown += `## Human:${timestamp}\n\n${content}\n\n`;
              break;
            case "assistant":
              const toolCalls = this.getNestedValue(message, "tool_calls", []);
              const toolResults = this.getNestedValue(
                message,
                "tool_results",
                []
              );
              markdown += `## Assistant:${timestamp}\n\n`;
              if (content) {
                markdown += `${content}\n\n`;
              }
              if (toolCalls.length > 0) {
                markdown += `**Tool Calls:**\n\`\`\`json\n${JSON.stringify(
                  toolCalls,
                  null,
                  2
                )}\n\`\`\`\n\n`;
              }
              if (toolResults.length > 0) {
                markdown += `**Tool Results:**\n`;
                toolResults.forEach((result: any) => {
                  let resultString = JSON.stringify(result, null, 2);
                  if (resultString.length > 1000) {
                    resultString =
                      resultString.substring(0, 1000) + "... [truncated]";
                  }
                  markdown += `\`\`\`json\n${resultString}\n\`\`\`\n`;
                });
                markdown += `\n`;
              }
              break;
            case "system":
              markdown += `## System:${timestamp}\n\n${content}\n\n`;
              break;
            case "tool":
              markdown += `## Tool Result:${timestamp}\n\n\`\`\`json\n${JSON.stringify(
                message,
                null,
                2
              )}\n\`\`\`\n\n`;
              break;
            default:
              markdown += `## ${
                role.charAt(0).toUpperCase() + role.slice(1)
              }:${timestamp}\n\n${content}\n\n`;
          }
        });
      } else {
        markdown += "\n*No messages found in task data.*\n";
      }
      // --- End of Markdown Formatting Logic ---

      // Write the markdown file using vscode.workspace.fs
      await vscode.workspace.fs.writeFile(
        exportUri,
        Buffer.from(markdown, "utf8")
      );
      console.log(`Exported task ${taskId} to ${exportUri.fsPath}`);
      return true;
    } catch (error) {
      console.error(`Error exporting task ${taskId}:`, error);
      vscode.window.showErrorMessage(
        `Failed to export task ${taskId}: ${
          error instanceof Error ? error.message : String(error)
        }`
      );
      // If source file not found, check if export exists and remove orphan
      if (
        error instanceof vscode.FileSystemError &&
        error.code === "FileNotFound"
      ) {
        await this.deleteExport(taskId, true); // Attempt to delete orphan silently
      }
      return false;
    }
  }

  /**
   * Exports all tasks that are not 'InSync'.
   */
  public async exportAllTasks(): Promise<{
    successCount: number;
    failCount: number;
  }> {
    const tasks = await this.getTasks();
    let successCount = 0;
    let failCount = 0;

    const tasksToExport = tasks.filter(
      (t) =>
        t.syncStatus !== SyncStatus.InSync &&
        t.syncStatus !== SyncStatus.SourceMissing &&
        t.syncStatus !== SyncStatus.Error
    );

    if (tasksToExport.length === 0) {
      vscode.window.showInformationMessage(
        "All tasks are already exported and up-to-date."
      );
      return { successCount: 0, failCount: 0 };
    }

    await vscode.window.withProgress(
      {
        location: vscode.ProgressLocation.Notification,
        title: `Exporting ${tasksToExport.length} tasks...`,
        cancellable: false, // Or true if you want to implement cancellation
      },
      async (progress) => {
        for (let i = 0; i < tasksToExport.length; i++) {
          const task = tasksToExport[i];
          progress.report({
            increment: (1 / tasksToExport.length) * 100,
            message: `Exporting ${task.id}...`,
          });
          const success = await this.exportTask(task.id);
          if (success) {
            successCount++;
          } else {
            failCount++;
          }
        }
      }
    );

    vscode.window.showInformationMessage(
      `Export finished. ${successCount} tasks exported, ${failCount} failed.`
    );
    return { successCount, failCount };
  }

  /**
   * Deletes a specific exported Markdown file.
   * @param taskId The ID of the task whose export should be deleted.
   * @param silent If true, suppresses error messages (used for orphan cleanup).
   */
  public async deleteExport(
    taskId: string,
    silent: boolean = false
  ): Promise<boolean> {
    const exportDir = this.getAbsoluteExportPath();
    if (!exportDir) {
      if (!silent)
        vscode.window.showErrorMessage(
          "Cannot delete export: Export path not determined."
        );
      return false;
    }
    const exportUri = vscode.Uri.joinPath(
      vscode.Uri.file(exportDir),
      `${taskId}.md`
    );
    try {
      await vscode.workspace.fs.delete(exportUri, { useTrash: false }); // Use false to permanently delete
      console.log(`Deleted export file: ${exportUri.fsPath}`);
      return true;
    } catch (error) {
      // Ignore "file not found" errors, as the goal is deletion
      if (
        error instanceof vscode.FileSystemError &&
        error.code === "FileNotFound"
      ) {
        console.log(
          `Export file ${exportUri.fsPath} not found, nothing to delete.`
        );
        return true; // Consider it a success if it's already gone
      }
      console.error(`Error deleting export file ${exportUri.fsPath}:`, error);
      if (!silent)
        vscode.window.showErrorMessage(
          `Failed to delete export ${taskId}: ${
            error instanceof Error ? error.message : String(error)
          }`
        );
      return false;
    }
  }

  /**
   * Deletes all files in the export directory. Use with caution!
   */
  public async deleteAllExports(): Promise<boolean> {
    const exportDir = this.getAbsoluteExportPath();
    if (!exportDir) {
      vscode.window.showErrorMessage(
        "Cannot delete exports: Export path not determined."
      );
      return false;
    }

    const confirm = await vscode.window.showWarningMessage(
      `Are you sure you want to delete ALL files in the export directory '${exportDir}'? This cannot be undone.`,
      { modal: true }, // Make it modal to force a choice
      "Delete All"
    );

    if (confirm !== "Delete All") {
      vscode.window.showInformationMessage("Deletion cancelled.");
      return false;
    }

    try {
      // Delete the directory recursively, then recreate it
      await vscode.workspace.fs.delete(vscode.Uri.file(exportDir), {
        recursive: true,
        useTrash: false,
      });
      console.log(`Deleted export directory: ${exportDir}`);
      // Recreate the directory
      await this.ensureExportDirExists();
      vscode.window.showInformationMessage(
        "All exported task files have been deleted."
      );
      return true;
    } catch (error) {
      // Handle case where directory didn't exist
      if (
        error instanceof vscode.FileSystemError &&
        error.code === "FileNotFound"
      ) {
        console.log(
          `Export directory ${exportDir} not found, nothing to delete.`
        );
        await this.ensureExportDirExists(); // Still ensure it exists afterwards
        vscode.window.showInformationMessage(
          "Export directory was not found. Nothing deleted."
        );
        return true;
      }
      console.error(`Error deleting export directory ${exportDir}:`, error);
      vscode.window.showErrorMessage(
        `Failed to delete all exports: ${
          error instanceof Error ? error.message : String(error)
        }`
      );
      return false;
    }
  }

  // --- Helper Methods ---

  /**
   * Safely get nested property value.
   * @param obj The object to query.
   * @param path The dot-separated path string.
   * @param defaultValue The default value if path is not found.
   */
  private getNestedValue(
    obj: any,
    path: string,
    defaultValue: any = undefined
  ): any {
    if (!obj || typeof path !== "string") {
      return defaultValue;
    }
    const keys = path.split(".");
    let result = obj;
    for (const key of keys) {
      if (result === null || typeof result !== "object" || !(key in result)) {
        return defaultValue;
      }
      result = result[key];
    }
    return result;
  }
}
