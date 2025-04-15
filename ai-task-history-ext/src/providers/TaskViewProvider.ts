import * as vscode from "vscode";
import { TaskService } from "../services/taskService";
import { getNonce } from "../utils/getNonce";
import { getUri } from "../utils/getUri";
import { Task, SyncStatus } from "../models/task";

export class TaskViewProvider implements vscode.WebviewViewProvider {
  public static readonly viewType = "ai-task-history.taskView";

  private _view?: vscode.WebviewView;
  private _taskService: TaskService;
  private _extensionUri: vscode.Uri;
  private _disposables: vscode.Disposable[] = [];

  constructor(context: vscode.ExtensionContext) {
    this._extensionUri = context.extensionUri;
    this._taskService = new TaskService(context);

    vscode.workspace.onDidChangeConfiguration(
      (e) => {
        if (e.affectsConfiguration("ai-task-history")) {
          console.log(
            "AI Task History configuration changed. Refreshing view."
          );
          this.refreshTasks();
        }
      },
      null,
      this._disposables
    );
  }

  public resolveWebviewView(
    webviewView: vscode.WebviewView,
    context: vscode.WebviewViewResolveContext,
    _token: vscode.CancellationToken
  ) {
    console.log("TaskViewProvider: resolveWebviewView called.");
    this._view = webviewView;

    webviewView.webview.options = {
      enableScripts: true,
      localResourceRoots: [
        vscode.Uri.joinPath(this._extensionUri, "media"),
        vscode.Uri.joinPath(this._extensionUri, "dist"), // Allow loading from dist
      ],
    };

    webviewView.webview.html = this._getHtmlForWebview(webviewView.webview);
    console.log("TaskViewProvider: Webview HTML set.");

    this._setWebviewMessageListener(webviewView.webview);
    console.log("TaskViewProvider: Message listener set.");

    this._loadTasks();

    webviewView.onDidDispose(
      () => {
        this.dispose();
      },
      null,
      this._disposables
    );
  }

  public dispose() {
    while (this._disposables.length) {
      const x = this._disposables.pop();
      if (x) {
        x.dispose();
      }
    }
  }

  private async _loadTasks() {
    console.log("TaskViewProvider: _loadTasks called.");
    if (!this._view) {
      console.log("TaskViewProvider: _loadTasks returning early - no view.");
      return;
    }
    this._view.webview.postMessage({ type: "loading" });
    console.log("TaskViewProvider: Posted 'loading' message.");
    try {
      console.log("TaskViewProvider: Calling taskService.getTasks...");
      const tasks = await this._taskService.getTasks();
      console.log(
        `TaskViewProvider: taskService.getTasks returned ${tasks.length} tasks.`
      );
      this._view.webview.postMessage({ type: "setTasks", tasks });
      console.log("TaskViewProvider: Posted 'setTasks' message.");
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      console.error("Error loading tasks for webview:", error);
      this._view.webview.postMessage({
        type: "error",
        message: `Error loading tasks: ${message}`,
      });
      vscode.window.showErrorMessage(`Error loading tasks: ${message}`);
      console.error("TaskViewProvider: Error in _loadTasks:", error);
    }
  }

  public async refreshTasks() {
    console.log("Refreshing tasks...");
    await this._loadTasks();
  }

  public async exportAllTasks() {
    console.log("Exporting all tasks...");
    await this._taskService.exportAllTasks();
    await this._loadTasks();
  }

  public async deleteAllExports() {
    console.log("Deleting all exports...");
    const success = await this._taskService.deleteAllExports();
    if (success) {
      await this._loadTasks();
    }
  }

  private _setWebviewMessageListener(webview: vscode.Webview) {
    webview.onDidReceiveMessage(
      async (message: any) => {
        const command = message.command;
        const payload = message.payload;

        switch (command) {
          case "getTasks":
            await this._loadTasks();
            return;

          case "exportTask":
            if (payload?.taskId) {
              vscode.window.withProgress(
                {
                  location: vscode.ProgressLocation.Notification,
                  title: `Exporting task ${payload.taskId}...`,
                },
                async () => {
                  const success = await this._taskService.exportTask(
                    payload.taskId
                  );
                  if (success) {
                    await this._loadTasks();
                  }
                }
              );
            }
            return;

          case "deleteExport":
            if (payload?.taskId) {
              const success = await this._taskService.deleteExport(
                payload.taskId
              );
              if (success) {
                await this._loadTasks();
              }
            }
            return;

          case "openSourceFile":
            if (payload?.taskId) {
              const tasks = await this._taskService.getTasks();
              const task = tasks.find((t) => t.id === payload.taskId);
              if (task?.sourcePath) {
                try {
                  const uri = vscode.Uri.file(task.sourcePath);
                  await vscode.window.showTextDocument(uri);
                } catch (error) {
                  const message =
                    error instanceof Error ? error.message : String(error);
                  vscode.window.showErrorMessage(
                    `Error opening source file ${task.sourcePath}: ${message}`
                  );
                }
              } else {
                vscode.window.showErrorMessage(
                  `Could not find source path for task ${payload.taskId}.`
                );
              }
            }
            return;

          case "openExportFile":
            if (payload?.taskId) {
              const tasks = await this._taskService.getTasks();
              const task = tasks.find((t) => t.id === payload.taskId);
              if (
                task?.exportPath &&
                task.syncStatus !== SyncStatus.NotExported &&
                task.syncStatus !== SyncStatus.SourceMissing
              ) {
                try {
                  const uri = vscode.Uri.file(task.exportPath);
                  await vscode.window.showTextDocument(uri);
                } catch (error) {
                  if (
                    error instanceof vscode.FileSystemError &&
                    error.code === "FileNotFound"
                  ) {
                    vscode.window.showWarningMessage(
                      `Export file for task ${payload.taskId} not found. It might need exporting.`
                    );
                    await this._loadTasks();
                  } else {
                    const message =
                      error instanceof Error ? error.message : String(error);
                    vscode.window.showErrorMessage(
                      `Error opening export file ${task.exportPath}: ${message}`
                    );
                  }
                }
              } else if (task?.syncStatus === SyncStatus.NotExported) {
                vscode.window.showInformationMessage(
                  `Task ${payload.taskId} has not been exported yet.`
                );
              } else if (task?.syncStatus === SyncStatus.SourceMissing) {
                vscode.window.showInformationMessage(
                  `Cannot open export file for orphaned task ${payload.taskId}.`
                );
              } else {
                vscode.window.showErrorMessage(
                  `Could not find export path for task ${payload.taskId}.`
                );
              }
            }
            return;

          case "showInfoMessage":
            if (payload?.message) {
              vscode.window.showInformationMessage(payload.message);
            }
            return;
        }
      },
      undefined,
      this._disposables
    );
  }

  /**
   * Generates the HTML content for the webview panel.
   */
  private _getHtmlForWebview(webview: vscode.Webview): string {
    // Get URIs for required resources from the 'dist' directory
    const scriptUri = getUri(webview, this._extensionUri, [
      "dist",
      "bundle.js",
    ]);
    const styleUri = getUri(webview, this._extensionUri, ["dist", "style.css"]);

    const nonce = getNonce();

    return /*html*/ `
      <!DOCTYPE html>
      <html lang="en">
      <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <!-- Update CSP to allow loading from 'dist' -->
        <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src ${webview.cspSource}; font-src ${webview.cspSource}; img-src ${webview.cspSource} https:; script-src 'nonce-${nonce}';">
        <link href="${styleUri}" rel="stylesheet">
        <title>AI Task History</title>
      </head>
      <body>
        <div id="root"></div>
        <!-- Load the bundled script -->
        <script nonce="${nonce}" src="${scriptUri}"></script>
      </body>
      </html>
    `;
  }
}
