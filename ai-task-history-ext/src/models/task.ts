/**
 * Represents the sync status of an exported task file relative to the original Roo task JSON.
 */
export enum SyncStatus {
  // The exported file exists and seems up-to-date (based on timestamp comparison).
  InSync = "inSync",
  // The exported file exists but might be older than the Roo task JSON.
  OutOfSync = "outOfSync",
  // The exported file does not exist.
  NotExported = "notExported",
  // The original Roo task JSON file could not be found (orphaned export).
  SourceMissing = "sourceMissing",
  // An error occurred trying to determine the status.
  Error = "error",
}

/**
 * Represents a Roo task, including information about its exported state.
 */
export interface Task {
  // The unique ID of the task (extracted from filename).
  id: string;
  // The title of the task (from JSON data or filename).
  title: string;
  // Timestamp of the last modification of the source Roo task JSON file.
  sourceLastModified: number;
  // Timestamp of the last modification of the exported Markdown file (if it exists).
  exportLastModified: number | null;
  // The calculated sync status between the source and export file.
  syncStatus: SyncStatus;
  // Full path to the source Roo task JSON file.
  sourcePath: string;
  // Full path to the potential exported Markdown file.
  exportPath: string;
  // Size of the source JSON file in bytes.
  size?: number;
  // Optional: Extracted content or metadata for display.
  content?: string;
  tokensIn?: number;
  tokensOut?: number;
}
