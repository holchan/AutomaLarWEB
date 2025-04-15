import React from "react";
import ReactDOM from "react-dom/client";

// Removed the check for global React/ReactDOM as they are now imported via bundling.

(function () {
  // React and ReactDOM are imported above.

  // Get VS Code API
  const vscode = acquireVsCodeApi();

  // Task status constants from model (ensure consistency)
  const STATUS = {
    InSync: "inSync",
    OutOfSync: "outOfSync",
    NotExported: "notExported",
    SourceMissing: "sourceMissing",
    Error: "error",
  };

  // Task status display info
  const STATUS_INFO = {
    [STATUS.InSync]: {
      label: "Exported & Up-to-date",
      icon: "codicon-check",
      cssClass: "status-inSync",
    },
    [STATUS.OutOfSync]: {
      label: "Exported (Outdated)",
      icon: "codicon-sync-ignored",
      cssClass: "status-outOfSync",
    },
    [STATUS.NotExported]: {
      label: "Not Exported",
      icon: "codicon-circle-outline",
      cssClass: "status-notExported",
    },
    [STATUS.SourceMissing]: {
      label: "Source Missing (Orphaned Export)",
      icon: "codicon-error",
      cssClass: "status-sourceMissing",
    },
    [STATUS.Error]: {
      label: "Error Checking Status",
      icon: "codicon-warning",
      cssClass: "status-error",
    },
    default: {
      label: "Unknown Status",
      icon: "codicon-question",
      cssClass: "status-unknown",
    },
  };

  // Format date
  function formatDate(timestamp) {
    if (!timestamp) return "N/A";
    try {
      const date = new Date(timestamp);
      // Use a more compact locale string
      return date.toLocaleString(undefined, {
        year: "numeric",
        month: "numeric",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
      });
    } catch (e) {
      return "Invalid Date";
    }
  }

  // Format file size
  function formatSize(bytes) {
    if (bytes === undefined || bytes === null || isNaN(bytes)) return "N/A";
    if (bytes < 1024) return bytes + " B";
    const units = ["KB", "MB", "GB"];
    let size = bytes / 1024;
    let unitIndex = 0;

    while (size >= 1024 && unitIndex < units.length - 1) {
      size /= 1024;
      unitIndex++;
    }

    return size.toFixed(1) + " " + units[unitIndex];
  }

  // Main App component
  function App() {
    const [tasks, setTasks] = React.useState([]);
    const [loading, setLoading] = React.useState(true);
    const [error, setError] = React.useState(null);

    React.useEffect(() => {
      // Listener for messages from the extension backend
      const handleMessage = (event) => {
        const message = event.data;
        console.log("Webview received message:", message); // Debugging

        switch (message.type) {
          case "loading":
            setLoading(true);
            setError(null);
            break;
          case "setTasks":
            setTasks(message.tasks || []);
            setLoading(false);
            setError(null);
            break;
          case "error":
            setError(message.message || "An unknown error occurred.");
            setLoading(false);
            break;
          // Add other message types if needed (e.g., taskSynced confirmation)
        }
      };

      window.addEventListener("message", handleMessage);

      // Request initial tasks when component mounts
      vscode.postMessage({ command: "getTasks" });

      // Cleanup listener on unmount
      return () => {
        window.removeEventListener("message", handleMessage);
      };
    }, []); // Empty dependency array means this effect runs once on mount

    // --- Event Handlers ---
    const handleExportTask = (taskId, event) => {
      event.stopPropagation(); // Prevent triggering other clicks
      setLoading(true); // Optionally show loading state for the specific task
      vscode.postMessage({ command: "exportTask", payload: { taskId } });
    };

    const handleDeleteExport = (taskId, event) => {
      event.stopPropagation();
      // Optional: Add confirmation dialog here if desired
      vscode.postMessage({ command: "deleteExport", payload: { taskId } });
    };

    const handleOpenSource = (taskId, event) => {
      event.stopPropagation();
      vscode.postMessage({ command: "openSourceFile", payload: { taskId } });
    };

    const handleOpenExport = (taskId, event) => {
      event.stopPropagation();
      vscode.postMessage({ command: "openExportFile", payload: { taskId } });
    };

    // --- Rendering Logic ---
    if (loading && tasks.length === 0) {
      return React.createElement(
        "div",
        { className: "loading" },
        "Loading tasks..."
      );
    }

    if (error) {
      return React.createElement(
        "div",
        { className: "error" },
        `Error: ${error}`
      );
    }

    if (!loading && tasks.length === 0) {
      return React.createElement(
        "div",
        { className: "empty-state" },
        "No Roo tasks found or path not configured."
      );
    }

    return React.createElement(
      "div",
      { className: "task-list" },
      tasks.map((task) => {
        const statusInfo = STATUS_INFO[task.syncStatus] || STATUS_INFO.default;
        const canExport =
          task.syncStatus === STATUS.NotExported ||
          task.syncStatus === STATUS.OutOfSync;
        const canDelete =
          task.syncStatus !== STATUS.NotExported &&
          task.syncStatus !== STATUS.SourceMissing; // Can delete if export exists
        const canOpenExport =
          task.syncStatus !== STATUS.NotExported &&
          task.syncStatus !== STATUS.SourceMissing;
        const canOpenSource = task.syncStatus !== STATUS.SourceMissing;

        return React.createElement(
          "div",
          {
            key: task.id,
            className: `task-item ${statusInfo.cssClass}`,
            title: `Task ID: ${task.id}\nStatus: ${
              statusInfo.label
            }\nSource Modified: ${formatDate(
              task.sourceLastModified
            )}\nExport Modified: ${formatDate(task.exportLastModified)}`,
          },
          [
            // Header: Status Icon, Title, Actions
            React.createElement("div", { className: "task-header" }, [
              React.createElement(
                "div",
                {
                  className: "task-title",
                  onClick: (e) => canOpenSource && handleOpenSource(task.id, e),
                  title: canOpenSource
                    ? `Click to open source: ${task.sourcePath}`
                    : "Source file missing",
                },
                [
                  React.createElement("span", {
                    className: `codicon ${statusInfo.icon} status-icon`,
                    title: statusInfo.label, // Tooltip for icon
                  }),
                  React.createElement(
                    "span",
                    {},
                    task.title || "Untitled Task"
                  ),
                ]
              ),
              React.createElement("div", { className: "task-actions" }, [
                // Open Source Button
                canOpenSource &&
                  React.createElement(
                    "button",
                    {
                      className: "action-button",
                      title: `Open Source JSON (${task.id})`,
                      onClick: (e) => handleOpenSource(task.id, e),
                    },
                    React.createElement("span", {
                      className: "codicon codicon-json",
                    })
                  ),
                // Open Export Button
                canOpenExport &&
                  React.createElement(
                    "button",
                    {
                      className: "action-button",
                      title: `Open Exported Markdown (${task.id})`,
                      onClick: (e) => handleOpenExport(task.id, e),
                    },
                    React.createElement("span", {
                      className: "codicon codicon-markdown",
                    })
                  ),
                // Export/Re-export Button
                canExport &&
                  React.createElement(
                    "button",
                    {
                      className: "action-button",
                      title:
                        task.syncStatus === STATUS.OutOfSync
                          ? `Re-export Task (${task.id})`
                          : `Export Task (${task.id})`,
                      onClick: (e) => handleExportTask(task.id, e),
                    },
                    React.createElement("span", {
                      className: "codicon codicon-sync",
                    })
                  ),
                // Delete Export Button
                canDelete &&
                  React.createElement(
                    "button",
                    {
                      className: "action-button",
                      title: `Delete Exported File (${task.id})`,
                      onClick: (e) => handleDeleteExport(task.id, e),
                    },
                    React.createElement("span", {
                      className: "codicon codicon-trash",
                    })
                  ),
              ]),
            ]),
            // Info: Date, Status Label
            React.createElement("div", { className: "task-info" }, [
              React.createElement(
                "div",
                {
                  className: "task-date",
                  title: `Source Modified: ${new Date(
                    task.sourceLastModified
                  ).toISOString()}`,
                },
                formatDate(task.sourceLastModified)
              ),
              React.createElement(
                "div",
                { className: "task-status" },
                statusInfo.label
              ),
            ]),
            // Stats: Size
            React.createElement("div", { className: "task-stats" }, [
              React.createElement(
                "span",
                { className: "task-stat", title: "Size of source JSON file" },
                [
                  React.createElement(
                    "span",
                    { className: "stat-label" },
                    "Size:"
                  ),
                  React.createElement(
                    "span",
                    { className: "stat-value" },
                    formatSize(task.size)
                  ),
                ]
              ),
              // Add token counts here if available in task model and needed
              // React.createElement('span', { className: 'task-stat' }, `Tokens: ${task.tokensIn || 0}/${task.tokensOut || 0}`)
            ]),
          ]
        );
      })
    );
  }

  // Render the app using the imported ReactDOM
  const container = document.getElementById("root");
  if (container) {
    const root = ReactDOM.createRoot(container);
    root.render(React.createElement(App));
  } else {
    console.error("Root element not found for React app.");
  }
})();
