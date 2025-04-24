// Simple TS types and functions
import { type Logger } from "./logger"; // Type-only import

export interface User {
  id: number;
  name: string;
  isActive?: boolean; // Optional property
}

export type Result<T> =
  | { success: true; data: T }
  | { success: false; error: string };

function processUser(user: User, logger: Logger): Result<string> {
  if (!user.name) {
    return { success: false, error: "User name is missing" };
  }
  logger.log(`Processing user ${user.id}`);
  return { success: true, data: `Processed ${user.name}` };
}

const formatResult = <T>(result: Result<T>): string => {
  return result.success ? `Data: ${result.data}` : `Error: ${result.error}`;
};
