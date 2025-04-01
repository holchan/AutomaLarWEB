# VS Code Project Configurations

This folder contains configuration files specific to the Visual Studio Code editor experience for this project. These settings are generally recommended to be committed to the repository (unless they contain user-specific paths or secrets) to ensure a consistent experience for all developers using VS Code.

## Files

*   **`launch.json`**: Defines configurations for the VS Code debugger (accessible via the "Run and Debug" panel). This includes setups for debugging:
    *   Next.js client-side code (in Chrome/Edge).
    *   Next.js server-side code.
    *   Full-stack Next.js debugging (attaching to both client and server).
    *   Placeholders/examples for debugging Storybook and automated tests (e.g., Jest/Vitest).
*   **`tasks.json`**: Defines common project tasks that can be run directly from the VS Code Command Palette (`Ctrl+Shift+P` -> "Tasks: Run Task"). This typically includes tasks for:
    *   Starting development servers (Next.js, Storybook).
    *   Running database migrations (`prisma migrate dev`).
    *   Generating Prisma Client (`prisma generate`).
    *   Opening Prisma Studio (`prisma studio`).
    *   Running linters (`eslint`) and formatters (`prettier`).
    *   Executing automated tests (`jest`, `vitest`).
    These tasks usually correspond to scripts defined in the root `package.json` file.
*   **`settings.json`** (Optional): While most workspace settings are defined within the `.devcontainer/devcontainer.json` file (under `customizations.vscode.settings`) to ensure they apply specifically *within* the Dev Container, you *could* have a `.vscode/settings.json` for settings you want to apply *regardless* of whether the project is opened in a container or locally. However, for Dev Container projects, it's generally best practice to keep workspace settings within `devcontainer.json`.
*   **`extensions.json`** (Optional): Similar to settings, extension recommendations are primarily handled by `devcontainer.json` (`customizations.vscode.extensions`) for Dev Container projects. This ensures extensions are installed *inside* the container. A `.vscode/extensions.json` could recommend extensions for developers *not* using the Dev Container, but might cause confusion.

## Usage

These files enhance the development workflow within VS Code:

*   Use the "Run and Debug" panel (usually on the left sidebar) to select a launch configuration from `launch.json` and start debugging.
*   Use the Command Palette (`Ctrl+Shift+P` or `Cmd+Shift+P`) and type "Tasks: Run Task" to execute common project commands defined in `tasks.json` without needing to type them manually in the terminal.

Ensure your root `package.json` contains the necessary scripts referenced by `tasks.json`.