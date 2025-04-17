import * as vscode from "vscode";
import { TaskService, TaskStatus } from "../services/taskService"; // Import TaskStatus
import { getNonce } from "../utils/getNonce";
import { getUri } from "../utils/getUri";
import * as path from "path";
import * as os from "os";

console.log("TaskViewProvider: Loading module...");

// Define a type for the task details we expect from the main Roo extension's command
// Adjust this based on the actual data returned by 'roovet.getTaskDetails'
interface RooTaskDetails {
  id: string;
  title: string; // Will be the Task ID for now
  lastModified: number; // Timestamp of the *task directory*
  // Add other relevant fields like token counts if available
  tokensIn?: number;
  tokensOut?: number;
  totalCost?: number;
  size?: number;
  workspace?: string;
}

// Define the structure we send to the webview
// type TaskStatus = "exported" | "not_exported" | "error"; // REMOVED - Now imported from TaskService
type WebViewTask = RooTaskDetails & {
  status: TaskStatus; // Use imported TaskStatus type
  lastModified: number;
};

export class TaskViewProvider implements vscode.WebviewViewProvider {
  public static readonly viewType = "ai-task-history.taskView";

  private _view?: vscode.WebviewView;
  private _taskService: TaskService;
  private _extensionUri: vscode.Uri;
  private _disposables: vscode.Disposable[] = [];

  constructor(context: vscode.ExtensionContext) {
    console.log("TaskViewProvider: constructor called.");
    this._extensionUri = context.extensionUri;
    this._taskService = new TaskService(context); // Instantiate TaskService here
  }

  // REMOVED: getTaskStatus method - Logic moved to TaskService

  public resolveWebviewView(
    webviewView: vscode.WebviewView,
    context: vscode.WebviewViewResolveContext,
    _token: vscode.CancellationToken
  ) {
    console.log("TaskViewProvider: resolveWebviewView called.");
    this._view = webviewView;

    console.log("TaskViewProvider: Setting webview options.");
    webviewView.webview.options = {
      enableScripts: true,
      localResourceRoots: [
        vscode.Uri.joinPath(this._extensionUri, "media"),
        vscode.Uri.joinPath(this._extensionUri, "dist"),
        vscode.Uri.file(os.homedir()), // Allow access broadly
      ],
    };

    console.log("TaskViewProvider: Setting webview HTML.");
    webviewView.webview.html = this._getHtmlForWebview(webviewView.webview);
    console.log("TaskViewProvider: Webview HTML set.");

    console.log("TaskViewProvider: Setting webview message listener.");
    this._setWebviewMessageListener(webviewView.webview);
    console.log("TaskViewProvider: Message listener set.");

    console.log(
      "TaskViewProvider: Initial task load triggered from resolveWebviewView."
    );
    this._loadTasks();

    webviewView.onDidDispose(
      () => {
        console.log("TaskViewProvider: Webview disposed.");
        this.dispose();
      },
      null,
      this._disposables
    );
  }

  public dispose() {
    console.log("TaskViewProvider: dispose() called.");
    while (this._disposables.length) {
      const x = this._disposables.pop();
      if (x) {
        x.dispose();
      }
    }
    console.log("TaskViewProvider: Disposables disposed.");
  }

  /**
   * Loads task details by discovering IDs and checking export status.
   */
  private async _loadTasks() {
    console.log("TaskViewProvider: _loadTasks() started.");
    if (!this._view) {
      console.log("TaskViewProvider: _loadTasks returning early - no view.");
      return;
    }
    console.log("TaskViewProvider: Posting 'loading' message to webview.");
    this._view.webview.postMessage({ type: "loading" });

    try {
      console.log("TaskViewProvider: Calling taskService.discoverTaskIds...");
      const taskIds = await this._taskService.discoverTaskIds();
      console.log(`TaskViewProvider: Discovered ${taskIds.length} task IDs.`); // <-- Keep this log

      // Add logging for number of tasks before processing
      if (taskIds.length > 50) {
        console.warn(
          `TaskViewProvider: Processing a large number of tasks (${taskIds.length}). This might be slow.`
        );
      }

      console.log("TaskViewProvider: Mapping task IDs to details...");
      console.time("TaskViewProvider: loadTaskDetails"); // Start timer for detail loading
      const taskDetailsPromises = taskIds.map(async (id) => {
        // console.log(`TaskViewProvider [${id}]: Processing task ID.`); // Very verbose
        let lastModified = 0;
        let taskDirectoryExists = false;
        let metadata: any = null; // To store metadata if read
        let title = `Task ${id}`; // Default title

        try {
          const rooTasksPath = await this._taskService.getRooTasksPath();
          if (!rooTasksPath) {
            console.error(
              `TaskViewProvider [${id}]: Roo tasks path could not be determined.`
            );
            return {
              id: id,
              title: `Task ${id} (Roo path error)`,
              lastModified: 0,
              status: "error",
            } as WebViewTask;
          }

          const taskDirectoryPath = path.join(rooTasksPath, "tasks", id);

          try {
            const dirStats = await vscode.workspace.fs.stat(
              vscode.Uri.file(taskDirectoryPath)
            );
            if (dirStats.type !== vscode.FileType.Directory) {
              console.warn(
                `TaskViewProvider: Path exists but is not a directory: ${taskDirectoryPath}. Skipping task.`
              );
              return null;
            }
            lastModified = dirStats.mtime;
            taskDirectoryExists = true;
          } catch (dirStatError) {
            if (
              dirStatError instanceof vscode.FileSystemError &&
              dirStatError.code === "FileNotFound"
            ) {
              console.warn(
                `TaskViewProvider [${id}]: Task directory NOT FOUND: ${taskDirectoryPath}. Skipping task.`
              );
            } else {
              console.error(
                `TaskViewProvider: Error stating task directory ${taskDirectoryPath}:`,
                dirStatError
              );
            }
            return null; // Skip task if directory doesn't exist or error occurs
          }

          // Try to read metadata to get a better title/timestamp if possible
          const metadataPath = path.join(
            taskDirectoryPath,
            "task_metadata.json"
          );
          try {
            const metadataContent = await vscode.workspace.fs.readFile(
              vscode.Uri.file(metadataPath)
            );
            metadata = JSON.parse(
              Buffer.from(metadataContent).toString("utf8")
            ) as any; // Loosen type for now
            if (metadata && typeof metadata.ts === "number") {
              lastModified = metadata.ts; // Overwrite directory mtime with metadata timestamp
            }
            // Use task description from metadata as title if available
            if (metadata && metadata.task) {
              title = `${metadata.task.substring(0, 50)}... (${id.substring(
                0,
                8
              )})`;
            }
          } catch (metaError) {
            if (
              !(
                metaError instanceof vscode.FileSystemError &&
                metaError.code === "FileNotFound"
              )
            ) {
              console.warn(
                `TaskViewProvider [${id}]: Failed to read or parse metadata ${metadataPath}:`,
                metaError
              );
            }
          }

          // Determine task status
          const status = await this._taskService.getTaskStatus(id); // Use service method

          return {
            id: id,
            title: title,
            lastModified: lastModified,
            status: status,
          } as WebViewTask;
        } catch (error) {
          // Handle case where task directory might disappear or other errors occur
          if (
            error instanceof Error &&
            error.message.includes("ENOENT") &&
            !taskDirectoryExists
          ) {
            console.warn(
              `TaskViewProvider [${id}]: Task directory likely deleted during processing.`
            );
            return null; // Skip this task
          }
          console.error(
            `TaskViewProvider [${id}]: Failed to get details:`,
            error
          );
          return {
            id: id,
            title: `Task ${id} (Error)`,
            lastModified: 0,
            status: "error",
          } as WebViewTask;
        }
      });

      console.log("TaskViewProvider: Waiting for all task details promises...");
      const tasks = (await Promise.all(taskDetailsPromises)).filter(
        (details): details is WebViewTask => details !== null
      );
      console.timeEnd("TaskViewProvider: loadTaskDetails"); // End timer for detail loading
      console.log(
        `TaskViewProvider: Filtered task details complete. Count: ${tasks.length}`
      );

      console.log("TaskViewProvider: Sorting tasks by lastModified date...");
      tasks.sort((a, b) => b.lastModified - a.lastModified);
      console.log("TaskViewProvider: Tasks sorted.");

      console.log(
        `TaskViewProvider: Posting 'setTasks' message to webview with ${tasks.length} tasks.`
      );
      this._view.webview.postMessage({ type: "setTasks", tasks });
      console.log("TaskViewProvider: 'setTasks' message posted.");
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      console.error("TaskViewProvider: Error in _loadTasks:", error);
      if (this._view) {
        console.log("TaskViewProvider: Posting 'error' message to webview.");
        this._view.webview.postMessage({
          type: "error",
          message: `Error loading tasks: ${message}`,
        });
      }
      vscode.window.showErrorMessage(`Error loading tasks: ${message}`);
    }
    console.log("TaskViewProvider: _loadTasks() finished.");
  }

  public async refreshTasks() {
    console.log("TaskViewProvider: refreshTasks() called.");
    await this._loadTasks();
  }

  // --- handleExportAllTasks REMOVED as its logic is incompatible with manual export ---

  private _setWebviewMessageListener(webview: vscode.Webview) {
    console.log("TaskViewProvider: _setWebviewMessageListener() called.");
    webview.onDidReceiveMessage(
      async (message: any) => {
        const command = message.command;
        const payload = message.payload;
        console.log(
          `TaskViewProvider: Received message from webview: command='${command}', payload=`,
          payload
        );

        if (!this._view) {
          console.warn(
            "TaskViewProvider: Received message but view is disposed. Ignoring."
          );
          return;
        }

        switch (command) {
          case "getTasks":
            console.log("TaskViewProvider: Handling 'getTasks' message.");
            await this._loadTasks(); // Call _loadTasks when webview requests
            break; // Correct break statement
          case "openTask": {
            // Handle request to open the exported markdown file
            const taskId = payload?.taskId;
            if (typeof taskId === "string") {
              console.log(
                `TaskViewProvider: Handling 'openTask' message for task ${taskId}.`
              );
              try {
                // We need the TaskService to construct the target path
                const targetDir = this._taskService.getTargetPath(); // Assuming TaskService has a method like this
                const exportFilename = `${taskId}.md`;
                const exportPath = path.join(targetDir, exportFilename);
                const exportUri = vscode.Uri.file(exportPath);

                // Check if file exists before trying to open
                try {
                  await vscode.workspace.fs.stat(exportUri);
                  await vscode.window.showTextDocument(exportUri);
                  console.log(
                    `TaskViewProvider: Opened exported file: ${exportPath}`
                  );
                } catch (statError) {
                  if (
                    statError instanceof vscode.FileSystemError &&
                    statError.code === "FileNotFound"
                  ) {
                    console.warn(
                      `TaskViewProvider: Export file not found for task ${taskId}: ${exportPath}`
                    );
                    vscode.window.showWarningMessage(
                      `Export file for task ${taskId} not found. It might need to be exported first.`
                    );
                  } else {
                    throw statError; // Re-throw other stat errors
                  }
                }
              } catch (error) {
                console.error(
                  `TaskViewProvider: Error opening task file for ${taskId}:`,
                  error
                );
                vscode.window.showErrorMessage(
                  `Failed to open export file for task ${taskId}.`
                );
              }
            } else {
              console.warn(
                "TaskViewProvider: 'openTask' message received without a valid taskId in payload."
              );
            }
            break;
          }
          // Add other cases here if needed
        }
      } // End of async message handler
    ); // End of onDidReceiveMessage
  } // End of _setWebviewMessageListener

  /**
   * Gets the HTML content for the webview panel.
   */
  private _getHtmlForWebview(webview: vscode.Webview): string {
    // Get URIs for required assets
    // Get URIs for required assets from the 'dist' directory
    const styleUri = getUri(webview, this._extensionUri, ["dist", "style.css"]);
    const codiconUri = getUri(webview, this._extensionUri, [
      "dist",
      "codicon.css",
    ]);
    const scriptUri = getUri(webview, this._extensionUri, [
      "dist",
      "bundle.js", // Point to the bundled script
    ]);
    const nonce = getNonce();

    // Basic HTML structure (can be enhanced)
    return /*html*/ `
      <!DOCTYPE html>
      <html lang="en">
      <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <meta
          http-equiv="Content-Security-Policy"
          content="default-src 'none'; style-src ${webview.cspSource} 'unsafe-inline'; font-src ${webview.cspSource}; script-src 'nonce-${nonce}';">
        <link rel="stylesheet" type="text/css" href="${codiconUri}">
        <link rel="stylesheet" type="text/css" href="${styleUri}">
        <title>AI Task History</title>
      </head>
      <body>
        <h1>AI Task History</h1>
        <button id="refresh-button">Refresh</button>
        <div id="task-list-container">
          <p id="loading-message">Loading tasks...</p>
          <ul id="task-list"></ul>
        </div>
        <p id="error-message" style="color: red; display: none;"></p>

        <script nonce="${nonce}" type="module" src="${scriptUri}"></script>
      </body>
    </html>
  `;
  } // End of _getHtmlForWebview
} // End of TaskViewProvider class
