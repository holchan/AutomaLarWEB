import * as vscode from "vscode";
import { TaskService } from "../services/taskService";
import { getNonce } from "../utils/getNonce";
import { getUri } from "../utils/getUri";
import * as fs from "fs";
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
}

// Define the structure we send to the webview (simplified - status removed for now)
type WebViewTask = RooTaskDetails;
// type WebViewTask = RooTaskDetails & {
//   status: "yellow" | "green" | "unknown"; // Simplified status: Yellow (Needs Export), Green (Exported)
// };

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

    console.log("TaskViewProvider: Setting up configuration change listener.");
    vscode.workspace.onDidChangeConfiguration(
      (e: vscode.ConfigurationChangeEvent) => {
        if (e.affectsConfiguration("ai-task-history")) {
          console.log(
            "TaskViewProvider: AI Task History configuration changed. Refreshing view."
          );
          this.refreshTasks();
        }
      },
      null,
      this._disposables
    );
    console.log("TaskViewProvider: Configuration change listener set up.");
  }

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
      console.log(`TaskViewProvider: Discovered ${taskIds.length} task IDs.`);

      console.log("TaskViewProvider: Mapping task IDs to details...");
      const taskDetailsPromises = taskIds.map(async (id) => {
        // console.log(`TaskViewProvider [${id}]: Processing task ID.`); // Very verbose
        // let status: "yellow" | "green" | "unknown" = "unknown"; // Status removed
        let lastModified = 0;
        let taskDirectoryExists = false;
        let metadata: any = null; // To store metadata if read

        try {
          // console.log(`TaskViewProvider [${id}]: Getting Roo tasks path...`); // Verbose
          const rooTasksPath = await this._taskService.getRooTasksPath();
          if (!rooTasksPath) {
            console.error(
              `TaskViewProvider [${id}]: Roo tasks path could not be determined.`
            );
            // status = "unknown"; // Status removed
            return {
              id: id,
              title: `Task ${id} (Roo path error)`,
              lastModified: 0,
              // status: status, // Status removed
            } as WebViewTask;
          }

          const taskDirectoryPath = path.join(rooTasksPath, "tasks", id);
          const metadataPath = path.join(
            taskDirectoryPath,
            "task_metadata.json"
          ); // Path to metadata

          // console.log(`TaskViewProvider [${id}]: Checking task directory: ${taskDirectoryPath}`); // Verbose
          taskDirectoryExists = fs.existsSync(taskDirectoryPath);
          // console.log(`TaskViewProvider [${id}]: Task directory exists? ${taskDirectoryExists}`); // Verbose

          if (!taskDirectoryExists) {
            console.warn(
              `TaskViewProvider [${id}]: Task directory NOT FOUND. Skipping task.`
            );
            return null;
          }

          // Get last modified time of the directory itself
          lastModified = fs.statSync(taskDirectoryPath).mtimeMs;

          // Try to read metadata to get a better title/timestamp if possible
          if (fs.existsSync(metadataPath)) {
            try {
              const metadataContent = fs.readFileSync(metadataPath, "utf8");
              metadata = JSON.parse(metadataContent);
              // Use metadata timestamp if available and valid, otherwise keep directory mtime
              if (metadata && typeof metadata.ts === "number") {
                lastModified = metadata.ts;
              }
            } catch (metaError) {
              console.warn(
                `TaskViewProvider [${id}]: Failed to read or parse metadata ${metadataPath}:`,
                metaError
              );
              // Proceed without metadata, using directory mtime
            }
          }

          // --- Status check based on old export path REMOVED ---

          // Use task description from metadata as title if available
          const title =
            metadata && metadata.task
              ? `${metadata.task.substring(0, 50)}... (${id.substring(0, 8)})`
              : `Task ${id}`;

          return {
            id: id,
            title: title, // Use potentially better title
            lastModified: lastModified, // Use potentially better timestamp
            // status: status, // Status removed
          } as WebViewTask;
        } catch (error) {
          // Handle case where task directory might disappear between existsSync and statSync
          if (
            error instanceof Error &&
            error.message.includes("ENOENT") &&
            !taskDirectoryExists // Check the flag we set earlier
          ) {
            console.warn(
              `TaskViewProvider [${id}]: Task directory likely deleted during processing.`
            );
            return null; // Skip this task
          }
          // Log other errors
          console.error(
            `TaskViewProvider [${id}]: Failed to get details:`,
            error
          );
          return {
            id: id,
            title: `Task ${id} (Error)`,
            lastModified: 0,
            // status: "unknown", // Status removed
          } as WebViewTask;
        }
      });

      console.log("TaskViewProvider: Waiting for all task details promises...");
      const tasks = (await Promise.all(taskDetailsPromises)).filter(
        (details): details is WebViewTask => details !== null
      );
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
            await this._loadTasks();
            break;

          case "exportTask":
            console.log("TaskViewProvider: Handling 'exportTask' message.");
            if (payload?.taskId) {
              const taskId = payload.taskId;
              try {
                vscode.window.showInformationMessage(
                  `Exporting task ${taskId}...` // Keep user feedback
                );
                // Call the NEW manual export method
                await this._taskService.exportTaskManually(taskId);
                // No automatic refresh needed as file location is chosen by user
              } catch (error) {
                // Error handling remains the same, error is logged by service now
                console.error(
                  `TaskViewProvider: Export failed for task ${taskId}`,
                  error
                );
              }
            } else {
              console.error(
                "TaskViewProvider: Invalid payload for exportTask:",
                payload
              );
            }
            break;

          // --- deleteTask case REMOVED ---
          // --- exportSelectedTasks case REMOVED ---
          // --- exportAllTasksFromWebview case REMOVED ---

          case "showInfoMessage":
            console.log(
              "TaskViewProvider: Handling 'showInfoMessage' message."
            );
            if (payload?.message) {
              vscode.window.showInformationMessage(payload.message);
            }
            break;

          case "openExportFile":
            // Inform user we cannot automatically open the file anymore.
            console.log("TaskViewProvider: Handling 'openExportFile' message.");
            if (payload?.taskId) {
              vscode.window.showInformationMessage(
                `Cannot automatically open export for task ${payload.taskId}. Please locate the file where you saved it.`
              );
            } else {
              console.error(
                "TaskViewProvider: Invalid payload for openExportFile:",
                payload
              );
            }
            break;

          default:
            console.warn(
              `TaskViewProvider: Received unknown command from webview: ${command}`
            );
        }
        console.log(
          `TaskViewProvider: Finished handling message command='${command}'.`
        );
      },
      undefined,
      this._disposables
    );
    console.log("TaskViewProvider: Webview message listener attached.");
  }

  /**
   * Generates the HTML content for the webview panel.
   */
  private _getHtmlForWebview(webview: vscode.Webview): string {
    console.log("TaskViewProvider: _getHtmlForWebview called");
    // Use the bundler's output (assuming webpack or similar)
    const scriptUri = getUri(webview, this._extensionUri, [
      "dist",
      "bundle.js",
    ]);
    const styleUri = getUri(webview, this._extensionUri, ["dist", "style.css"]);
    const codiconsUri = getUri(webview, this._extensionUri, [
      "dist",
      "codicon.css",
    ]); // Make sure this is copied to dist
    const nonce = getNonce();
    console.log(
      `TaskViewProvider: Script URI: ${scriptUri.toString()}, Style URI: ${styleUri.toString()}, Codicons URI: ${codiconsUri.toString()}, Nonce: ${nonce}`
    );

    // Removed "Export Selected" and "Export All" buttons from HTML
    return /*html*/ `
      <!DOCTYPE html>
      <html lang="en">
      <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src ${webview.cspSource} 'unsafe-inline'; font-src ${webview.cspSource}; script-src 'nonce-${nonce}';">
        <link href="${styleUri}" rel="stylesheet" />
        <link href="${codiconsUri}" rel="stylesheet" />
        <title>AI Task History</title>
      </head>
      <body>
        <h1>Roo Task History</h1>
        <div class="controls">
          <button id="refresh-button" title="Refresh Task List">
            <i class="codicon codicon-refresh"></i> Refresh
          </button>
          <!-- Removed Export Selected/All buttons -->
        </div>
        <div id="task-list-container">
          <p id="loading-message">Loading tasks...</p>
          <p id="error-message" class="error-message" style="display: none;"></p>
          <ul id="task-list"></ul>
        </div>
        <script type="module" nonce="${nonce}" src="${scriptUri}"></script>
      </body>
      </html>
    `;
  }
}

console.log("TaskViewProvider: Module loaded.");
