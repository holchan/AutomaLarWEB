import * as vscode from "vscode";
import { TaskViewProvider } from "./providers/TaskViewProvider";
import { TaskService } from "./services/taskService"; // Import TaskService
import * as path from "path";
import * as fs from "fs"; // Import the fs module

console.log("AI Task History: Loading extension module...");

// Define expected Roo Code API structure (Simplified - only events potentially relevant)
interface RooCodeAPI {
  // Event Emitter methods (Optional: Keep if needed for real-time updates beyond file watcher)
  on?(event: "taskCreated", listener: (taskId: string) => void): this;
  on?(
    event: "taskCompleted",
    listener: (taskId: string, usage: any) => void
  ): this;
  // Add other relevant events if needed
}

/**
 * This method is called when your extension is activated.
 */
export async function activate(context: vscode.ExtensionContext) {
  console.log("AI Task History: activate() called.");

  // --- Roo Code API Activation (Optional - Keep if using events) ---
  console.log("AI Task History: Attempting to get Roo Code extension...");
  const rooExtension = vscode.extensions.getExtension<RooCodeAPI>(
    "rooveterinaryinc.roo-cline"
  );
  let rooApi: RooCodeAPI | undefined;
  if (rooExtension) {
    console.log("AI Task History: Roo Code extension found.");
    if (!rooExtension.isActive) {
      try {
        console.log(
          "AI Task History: Activating Roo Code extension for event listeners (if any)..."
        );
        rooApi = await rooExtension.activate();
        console.log(
          "AI Task History: Roo Code extension activated via activate()."
        );
      } catch (err) {
        console.error(
          "AI Task History: Failed to activate Roo Code extension:",
          err
        );
        // Non-critical if only using commands and file watcher
      }
    } else {
      console.log("AI Task History: Roo Code extension already active.");
      rooApi = rooExtension.exports;
    }
    if (rooApi) {
      console.log(
        "AI Task History: Roo Code API obtained (for potential event listeners)."
      );
    } else {
      console.warn(
        "AI Task History: Could not obtain Roo Code API (needed for event listeners)."
      );
    }
  } else {
    console.warn(
      "AI Task History: Roo Code extension (rooveterinaryinc.roo-cline) not found."
    );
  }
  // --- End Optional API Activation ---

  // Create Task Service and Task View Provider
  console.log("AI Task History: Creating TaskService instance...");
  const taskService = new TaskService(context); // Instantiate service first
  console.log("AI Task History: Creating TaskViewProvider instance...");
  const taskViewProvider = new TaskViewProvider(context); // Constructor only takes context

  // Register the Task View Provider
  console.log("AI Task History: Registering TaskViewProvider...");
  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider(
      TaskViewProvider.viewType,
      taskViewProvider,
      {
        webviewOptions: { retainContextWhenHidden: true },
      }
    )
  );
  console.log("AI Task History: TaskViewProvider registered.");

  // Register commands defined in package.json
  console.log("AI Task History: Registering commands...");
  context.subscriptions.push(
    vscode.commands.registerCommand("ai-task-history.refresh", () => {
      console.log(
        "AI Task History: Command 'ai-task-history.refresh' executed."
      );
      taskViewProvider.refreshTasks();
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("ai-task-history.configure", () => {
      console.log(
        "AI Task History: Command 'ai-task-history.configure' executed."
      );
      vscode.commands.executeCommand(
        "workbench.action.openSettings",
        "ai-task-history"
      );
    })
  );

  // *** REMOVED: Register the exportAll command (incompatible with manual export) ***
  // context.subscriptions.push(
  //   vscode.commands.registerCommand("ai-task-history.exportAll", async () => {
  //     console.log(
  //       "AI Task History: Command 'ai-task-history.exportAll' executed."
  //     );
  //     // We need to trigger the logic similar to 'exportAllTasksFromWebview'
  //     // Accessing the provider directly is one way, or add a method to the provider
  //     // await taskViewProvider.handleExportAllTasks(); // This method was removed
  //   })
  // );
  console.log("AI Task History: Commands registered.");

  // --- Setup Roo Code Event Listeners (Optional) ---
  if (rooApi) {
    const setupListeners = (api: RooCodeAPI) => {
      console.log(
        "AI Task History: Setting up Roo Code event listeners (if API supports 'on')..."
      );
      if (api.on) {
        api.on("taskCreated", (taskId) => {
          console.log(
            `AI Task History: Roo event: taskCreated - ${taskId}. Refreshing list.`
          );
          taskViewProvider.refreshTasks();
        });
        api.on("taskCompleted", (taskId, usage) => {
          console.log(
            `AI Task History: Roo event: taskCompleted - ${taskId}. Refreshing list.`
          );
          taskViewProvider.refreshTasks();
        });
        console.log(
          "AI Task History: Roo Code event listeners potentially set up."
        );
      } else {
        console.log(
          "AI Task History: Roo Code API does not seem to support 'on' method for events."
        );
      }
    };
    setupListeners(rooApi);
  }
  // --- End Optional Event Listeners ---

  // --- Setup File System Watcher (Primary update mechanism) ---
  console.log("AI Task History: Setting up File System Watcher...");
  // TaskService instance already created above
  const rooTasksPath = await taskService.getRooTasksPath(); // Ensures directories exist
  if (rooTasksPath) {
    const watchPaths = [
      path.join(rooTasksPath, "tasks"),
      path.join(rooTasksPath, "exports"),
    ];

    watchPaths.forEach((watchPath) => {
      try {
        // Check if path exists before watching
        if (fs.existsSync(watchPath)) {
          console.log(
            `AI Task History: Setting up file system watcher for: ${watchPath}`
          );
          const watcher = vscode.workspace.createFileSystemWatcher(
            new vscode.RelativePattern(watchPath, "**/*") // Watch contents
          );

          // Debounce refresh calls slightly
          let refreshTimeout: NodeJS.Timeout | null = null;
          const debounceMs = 500; // Adjust as needed

          const refreshHandler = (uri: vscode.Uri | undefined) => {
            if (refreshTimeout) {
              clearTimeout(refreshTimeout);
            }
            refreshTimeout = setTimeout(() => {
              console.log(
                `AI Task History: File system event in ${watchPath} (debounced). Refreshing task list.`
              );
              taskViewProvider.refreshTasks();
              refreshTimeout = null;
            }, debounceMs);
          };

          watcher.onDidChange(refreshHandler);
          watcher.onDidCreate(refreshHandler);
          watcher.onDidDelete(refreshHandler);

          context.subscriptions.push(watcher);
          console.log(
            `AI Task History: File system watcher started for ${watchPath}`
          );
        } else {
          console.warn(
            `AI Task History: Directory not found, cannot start watcher: ${watchPath}`
          );
        }
      } catch (watchError) {
        console.error(
          `AI Task History: Error setting up watcher for ${watchPath}:`,
          watchError
        );
      }
    });
  } else {
    console.warn(
      "AI Task History: Could not start file system watcher: Roo tasks path not found."
    );
  }
  console.log("AI Task History: File System Watcher setup complete.");
  console.log("AI Task History: Activation finished.");
  // --- End File System Watcher ---
}

/**
 * This method is called when your extension is deactivated.
 */
export function deactivate() {
  console.log("AI Task History: deactivate() called.");
  console.log('Your extension "ai-task-history-ext" is now deactivated.');
}
