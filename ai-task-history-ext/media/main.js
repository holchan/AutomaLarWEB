import React from "react";
import ReactDOM from "react-dom/client";

// Removed the check for global React/ReactDOM as they are now imported via bundling.

(function () {
  // React and ReactDOM are imported above.

  // Get VS Code API
  const vscode = acquireVsCodeApi();

  // Task status display info - REMOVED as status is no longer tracked this way
  // const STATUS_INFO = { ... };

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
            setTasks(Array.isArray(message.tasks) ? message.tasks : []);
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

    console.log("Rendering tasks:", tasks); // Debugging: Check the tasks array before mapping

    return React.createElement(
      "div",
      { className: "task-list" },
      tasks.map((task) => {
        // Status logic removed
        // const statusInfo = STATUS_INFO[task.status] || STATUS_INFO.default;
        // const canExport = task.status === "yellow" || task.status === "red";
        // const canDelete = task.status !== "unknown";
        // const canOpenExport = task.status === "green";
        // const canOpenSource = task.status !== "red";

        // console.log(`Task ${task.id} Status: ${task.status}`, statusInfo); // Debugging

        return React.createElement(
          "div",
          {
            key: task.id,
            className: `task-item`, // Removed status CSS class
            title: `Task ID: ${task.id}\nLast Modified: ${formatDate(
              task.lastModified
            )}`,
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
                  // Status icon removed
                  // React.createElement("span", {
                  //   className: `codicon ${statusInfo.icon} status-icon`,
                  //   title: statusInfo.label,
                  // }),
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
              // Status label removed
              // React.createElement(
              //   "div",
              //   { className: "task-status" },
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
  const container = document.getElementById("root");
  if (container) {
    const root = ReactDOM.createRoot(container);
    root.render(React.createElement(App));
  } else {
    console.error("Root element not found for React app.");
  }
})();
