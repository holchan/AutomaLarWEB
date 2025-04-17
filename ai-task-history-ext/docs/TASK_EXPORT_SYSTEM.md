# Task Export System Design

## 1. Directory Structure & Paths

- **Source (Read-Only):** Original Roo task data located in VS Code's global storage for the Roo extension.

  ```
  [VSCode Global Storage Root]/rooveterinaryinc.roo-cline/tasks/
    [task-uuid]/
      task_metadata.json
      api_conversation_history.json
  ```

  _(Example path in dev container: `/home/node/.vscode-server/data/User/globalStorage/rooveterinaryinc.roo-cline/tasks/`)_

- **Target (Managed Exports):** Automatically generated and updated markdown files stored in this extension's dedicated global storage.
  ```
  [VSCode Global Storage Root]/automalar.dev-aid/task_exports/
    [task-uuid].md           # Mirrored markdown version
  ```
  _(Example path in dev container: `/home/node/.vscode-server/data/User/globalStorage/automalar.dev-aid/task_exports/`)_

## 2. Status Indicators

| Color  | Icon | Meaning              |
| ------ | ---- | -------------------- |
| Red    | ⚪   | New task (no export) |
| Green  | ✅   | Exported & in sync   |
| Yellow | 🔄   | Out of sync          |

## 3. Automatic Processing Logic

```mermaid
flowchart TD
    A[Watch Source Dir: .../rooveterinaryinc.roo-cline/tasks/] --> B{Change Detected\n(New Task / Modified Task)}
    B --> C[Get Task UUID]
    C --> D[Read Source Files\n(metadata, history)]
    D --> E[Generate Markdown Content]
    E --> F[Construct Target Path:\n.../automalar.dev-aid/task_exports/[uuid].md]
    F --> G[Write/Overwrite Target MD File]
    G --> H[Update Status (Compare Source/Target Timestamps)]
    H --> I{Display Status in UI:\n🔴 New\n🟢 Synced\n🟡 Out of Sync}
```

## 4. Implementation Steps

1. **File Watcher Service**

   - Monitor the **Source** directory (`.../rooveterinaryinc.roo-cline/tasks/`) using `vscode.workspace.createFileSystemWatcher`.
   - Trigger processing on file/folder creation and changes within that directory.
   - Implement periodic re-scan (e.g., every 5 minutes) as a fallback.

2. **Export Service**

   - **Input:** Task UUID.
   - **Process:**
     - Read `task_metadata.json`, optional file, sometimes is missing, and `api_conversation_history.json` from the **Source** directory for the given UUID.
     - Generate markdown content.
     - Determine the **Target** path (`.../automalar.dev-aid/task_exports/[uuid].md`).
     - Write/overwrite the markdown file to the **Target** path using `vscode.workspace.fs.writeFile`.
     - Ensure the `automalar.dev-aid/task_exports` directory exists using `vscode.workspace.fs.createDirectory`.

3. **Status Service**
   - Compare source vs export timestamps
   - Update UI indicators accordingly
