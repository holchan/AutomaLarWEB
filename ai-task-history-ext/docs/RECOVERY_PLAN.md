# AI Task History Extension - Recovery Plan (2025-04-17)

## 1. Assessment Summary

Based on analysis of `TASK_EXPORT_SYSTEM.md` and the current codebase (`extension.ts`, `TaskService.ts`, `TaskViewProvider.ts`):

- **Core Functionality:** The automatic export mechanism (watcher -> `TaskService.processAndExportTask`) is mostly implemented. `TaskService` handles reading source files, formatting content, and writing the markdown export.
- **Status Logic:** Status determination (`getTaskStatus`) is currently implemented in `TaskViewProvider.ts`. Its logic compares the _source task directory's_ modification time against the _export file's_ modification time.
- **UI Interaction:** The webview displays the task list but likely lacks the functionality to open the corresponding exported markdown file when a task is clicked.
- **Code Location:** Status logic resides in `TaskViewProvider` instead of `TaskService`.

## 2. Identified Discrepancies & Issues

1.  **Inaccurate Status Checking:** The current `getTaskStatus` logic doesn't accurately compare source _file_ timestamps (`metadata.json`, `history.json`) vs. the export timestamp, as implied by the design doc for detecting "Out of Sync".
2.  **Incomplete Status Mapping:** The current logic returns `"not_exported"` for both "never exported" and "out of sync", failing to map directly to the three distinct states (New ⚪, Synced ✅, Out of Sync 🔄) required by the design.
3.  **Missing "Open Export" Feature:** The UI lacks the interaction to open the exported `.md` file.
4.  **(Minor) Suboptimal Code Structure:** Status logic is in the UI provider, not the service layer.

## 3. Proposed Recovery Plan

1.  **Refine Status Logic:**

    - **Goal:** Implement accurate status checking based on source file timestamps.
    - **Action:** Modify `TaskViewProvider.getTaskStatus` (or move logic to `TaskService`).
    - **Details:** Compare the latest `mtime` of `task_metadata.json` / `api_conversation_history.json` (sourceTimestamp) with the `mtime` of `[task-uuid].md` (exportTimestamp).
      - No export file: Status `new` (⚪).
      - `exportTimestamp >= sourceTimestamp`: Status `synced` (✅).
      - `exportTimestamp < sourceTimestamp`: Status `out_of_sync` (🔄).
      - Errors: Status `error`.
    - **Data Structure:** Update `WebViewTask` type and `TaskStatus` enum/type (e.g., `'new' | 'synced' | 'out_of_sync' | 'error'`).

2.  **Update UI for Status Display:**

    - **Goal:** Visually represent the three distinct statuses in the webview.
    - **Action:** Modify webview HTML (`_getHtmlForWebview`) and JS (`media/main.js`).
    - **Details:** Use refined status to display corresponding icons/colors (⚪, ✅, 🔄).

3.  **Implement "Open Exported File" Interaction:**

    - **Goal:** Allow users to click a task to open its export file.
    - **Action:** Add JS in `media/main.js` to send `"openTask"` message. Add handler in `TaskViewProvider.ts` to use `vscode.window.showTextDocument`.

4.  **(Optional but Recommended) Refactor Status Logic Location:**
    - **Goal:** Improve code structure.
    - **Action:** Move refined `getTaskStatus` logic from `TaskViewProvider` to `TaskService`. Update `TaskViewProvider` call.

## 4. Proposed Flow Diagram

```mermaid
graph TD
    subgraph Extension Host (TypeScript)
        A[File Watcher (extension.ts)] -- Triggers --> B(TaskService.processAndExportTask)
        B -- Reads --> C{Source Files (metadata.json, history.json)}
        B -- Generates & Writes --> D[Target Export File (.md)]
        E[TaskViewProvider._loadTasks] -- Calls --> F(TaskService.discoverTaskIds)
        E -- Calls --> G(TaskService.getTaskStatus - Proposed Refinement)
        G -- Reads --> C
        G -- Reads --> D
        G -- Returns --> H{Task Status (new/synced/out_of_sync/error)}
        E -- Sends --> I{WebViewTask List (with Status)}
        J[TaskViewProvider._setWebviewMessageListener] -- Receives 'openTask' --> K{Open Export File Logic}
        K -- Opens --> D
    end

    subgraph Webview (HTML/JS)
        L[main.js] -- Receives --> I
        L -- Renders --> M[Task List UI (with Status Icons)]
        M -- User Click --> N[Send 'openTask' Message]
        N -- Sends --> J
    end

    I --> L
```
