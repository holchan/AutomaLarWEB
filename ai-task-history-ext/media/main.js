import React from "react";
import ReactDOM from "react-dom/client";

// Removed the check for global React/ReactDOM as they are now imported via bundling.

(function () {
  // React and ReactDOM are imported above.

  // Get VS Code API
  const vscode = acquireVsCodeApi();

  // Task status display info
  const STATUS_INFO = {
    new: {
      // Renamed from 'not_exported' and updated color/label
      icon: "codicon-circle-large-outline", // ⚪
      color: "var(--vscode-terminal-ansiRed)", // Red for New as per design doc
      label: "New (Not Exported)",
    },
    synced: {
      // Renamed from 'exported'
      icon: "codicon-check", // ✅
      color: "var(--vscode-terminal-ansiGreen)",
      label: "Synced",
    },
    out_of_sync: {
      // New status
      icon: "codicon-sync", // 🔄
      color: "var(--vscode-terminal-ansiYellow)",
      label: "Out of Sync",
    },
    error: {
      icon: "codicon-error",
      color: "var(--vscode-terminal-ansiRed)",
      label: "Error",
    },
    default: {
      // Fallback
      icon: "codicon-question",
      color: "var(--vscode-foreground)",
      label: "Unknown Status",
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
            // Ensure message.tasks is always an array
            const newTasks = Array.isArray(message.tasks) ? message.tasks : [];
            console.log("Webview: Calling setTasks with:", newTasks); // Log before setting state
            setTasks(newTasks);
            console.log("Webview: Calling setLoading(false)"); // Log before setting state
            setLoading(false);
            setError(null);
            // Log state *after* updates (Note: state updates might be async, this log might show old value)
            console.log("Webview: State update calls completed for setTasks.");
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
      console.log("Webview requesting initial tasks..."); // Debugging
      vscode.postMessage({ command: "getTasks" });

      // Cleanup listener on unmount
      return () => {
        window.removeEventListener("message", handleMessage);
      };
    }, []); // Empty dependency array means this effect runs once on mount

    // --- Event Handlers ---
    const handleExportTask = (taskId, event) => {
      event.stopPropagation(); // Prevent triggering other clicks
      // setLoading(true); // Optionally show loading state for the specific task
      vscode.postMessage({ command: "exportTask", payload: { taskId } });
    };

    // NEW Delete Task Handler - REMOVED
    // const handleDeleteTask = (taskId, event) => { ... };

    // Open Source Handler - REMOVED (functionality not implemented)
    // const handleOpenSource = (taskId, event) => { ... };

    // Open Export Handler - REMOVED (cannot open automatically anymore)
    // const handleOpenExport = (taskId, event) => { ... };

    // Handler to open the exported task file
    const handleOpenTask = (taskId) => {
      console.log(`Webview requesting to open task: ${taskId}`);
      vscode.postMessage({ command: "openTask", payload: { taskId } });
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

    // Log the state right before rendering the list
    console.log(
      `Webview: Rendering App component. Loading: ${loading}, Error: ${error}, Tasks count: ${tasks.length}`
    );
    console.log("Webview: Tasks state before mapping:", tasks);

    return React.createElement(
      "div",
      { className: "task-list" },
      tasks.map((task) => {
        // Get status info based on the status received from the backend
        const statusInfo = STATUS_INFO[task.status] || STATUS_INFO.default;
        // const canExport = task.status === "yellow" || task.status === "red"; // Old logic
        // const canDelete = task.status !== "unknown"; // Old logic
        // const canOpenExport = task.status === "green"; // Old logic
        // const canOpenSource = task.status !== "red";

        // console.log(`Task ${task.id} Status: ${task.status}`, statusInfo); // Debugging

        return React.createElement(
          "div",
          {
            key: task.id,
            className: `task-item`, // Removed status CSS class
            title: `Task ID: ${task.id}\nLast Modified: ${formatDate(
              task.lastModified
            )}\nClick to open exported file`, // Updated title
            onClick: () => handleOpenTask(task.id), // Add onClick handler
            style: { cursor: "pointer" }, // Add pointer cursor
          },
          [
            // Header: Title, Actions
            React.createElement("div", { className: "task-header" }, [
              React.createElement(
                "div",
                {
                  className: "task-title",
                  title: `Task: ${task.title || "Untitled"}`,
                },
                [
                  // Add Status icon
                  React.createElement("span", {
                    className: `codicon ${statusInfo.icon} status-icon`,
                    style: { color: statusInfo.color, marginRight: "6px" }, // Add color and spacing
                    title: statusInfo.label,
                  }),
                  React.createElement(
                    "span",
                    {},
                    task.title || "Untitled Task"
                  ),
                ]
              ),
              React.createElement("div", { className: "task-actions" }, [
                // Open Source Button REMOVED
                // Open Export Button REMOVED
                // Export Button (Always available now)
                React.createElement(
                  "button",
                  {
                    className: "action-button",
                    title: `Export Task (${task.id})`,
                    onClick: (e) => handleExportTask(task.id, e),
                  },
                  React.createElement("span", {
                    // Using export icon instead of sync
                    className: "codicon codicon-cloud-download",
                  })
                ),
                // Delete Task Button REMOVED
              ]),
            ]),
            // Info: Date only
            React.createElement("div", { className: "task-info" }, [
              React.createElement(
                "div",
                {
                  className: "task-date",
                  title: `Last Modified: ${new Date(
                    task.lastModified
                  ).toISOString()}`,
                },
                formatDate(task.lastModified)
              ),
              // Optionally add status label back if desired
              // React.createElement(
              //   "div",
              //   { className: "task-status", style: { color: statusInfo.color } },
              //   statusInfo.label
              // ),
            ]),
            // Stats section removed for simplicity
          ]
        );
      })
    );
  }

  // Render the app using the imported ReactDOM
  console.log(
    "Webview: Attempting to find container element '#task-list-container'"
  );
  const container = document.getElementById("task-list-container"); // <-- Target the correct container ID
  if (container) {
    console.log("Webview: Container found. Creating React root.");
    const root = ReactDOM.createRoot(container);
    console.log("Webview: Rendering React App component.");
    root.render(React.createElement(App));
    console.log("Webview: React App component rendered.");
  } else {
    console.error(
      "Root element '#task-list-container' not found for React app."
    );
  }
})();
