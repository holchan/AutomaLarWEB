import * as vscode from "vscode";

/**
 * A helper function that returns a URI for a resource in the extension's media directory.
 *
 * @param webview The webview instance.
 * @param extensionUri The URI of the extension directory.
 * @param pathList An array of strings representing the path segments to the resource.
 * @returns A URI pointing to the resource suitable for use in the webview's HTML.
 */
export function getUri(
  webview: vscode.Webview,
  extensionUri: vscode.Uri,
  pathList: string[]
): vscode.Uri {
  return webview.asWebviewUri(vscode.Uri.joinPath(extensionUri, ...pathList));
}
