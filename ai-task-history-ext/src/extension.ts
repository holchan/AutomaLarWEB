import * as vscode from "vscode";
import { TaskViewProvider } from "./providers/TaskViewProvider";

/**
 * This method is called when your extension is activated.
 * Your extension is activated the very first time the command is executed
 * or when the view specified in activationEvents is shown.
 */
export function activate(context: vscode.ExtensionContext) {
  console.log("AI Task History extension is now active!");

  // Create and register the Task View Provider
  const taskViewProvider = new TaskViewProvider(context);
  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider(
      TaskViewProvider.viewType,
      taskViewProvider,
      {
        webviewOptions: { retainContextWhenHidden: true }, // Keep webview state even when not visible
      }
    )
  );

  // Register commands defined in package.json
  context.subscriptions.push(
    vscode.commands.registerCommand("ai-task-history.refresh", () => {
      taskViewProvider.refreshTasks();
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("ai-task-history.exportAll", () => {
      taskViewProvider.exportAllTasks();
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("ai-task-history.deleteAllExports", () => {
      taskViewProvider.deleteAllExports();
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("ai-task-history.configure", () => {
      vscode.commands.executeCommand(
        "workbench.action.openSettings",
        "ai-task-history"
      );
    })
  );
}

/**
 * This method is called when your extension is deactivated.
 */
export function deactivate() {
  console.log('Your extension "ai-task-history-ext" is now deactivated.');
}
