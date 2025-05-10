# Project Development Container Environment

This folder defines the configuration for the VS Code Dev Containers feature, providing a consistent, fully-featured development environment for the AutomaLarWEB.

## Overview

This setup utilizes Docker Compose to orchestrate the necessary services for local development:

1.  **`app` Service:**
    - Builds from `./Dockerfile`.
    - Runs Node.js v22 on Debian Bookworm.
    - Mounts the project source code from the parent directory into `/workspaces/`.
    - Installs project dependencies using Yarn based on `../package.json`.
    - Includes common development utilities (Git, Zsh, GitHub CLI) via Dev Container Features.
    - Forwards ports for the Next.js app (3000), Storybook (6006), and Prisma Studio (5555).
    - Runs as the non-root `node` user for security and file permission compatibility.
2.  **`db` Service:**
    - Runs a PostgreSQL 15 database container.
    - Persists data using a named Docker volume (`postgres_data_devcontainer`) on the host machine.
    - Configured with default credentials (`devuser`/`devpassword`/`devdb`) - **for development only**.
    - Accessible from the `app` service using the hostname `db` on port `5432`.
    - Optionally exposes port 5432 to the host for external DB tool access.
    - Includes a healthcheck to ensure it's ready before the `app` service fully starts.
3.  **Shared Network:** Both services run on a dedicated Docker network (`home_automation_dev_net`), allowing easy communication.
4.  **Named Volumes:** Used for `node_modules`, `.next` cache, `.storybook-cache`, Zsh history, and PostgreSQL data to improve performance and persist state across container restarts.

## How to Use

1.  **Prerequisites:**
    - Docker Desktop (or compatible Docker environment) installed and running.
    - VS Code installed.
    - The "Dev Containers" extension (ID: `ms-vscode-remote.remote-containers`) installed in VS Code.
2.  **Clone the Repository:** Clone the main project repository to your local machine.
3.  **Open in VS Code:** Open the _root folder_ of the cloned repository in VS Code.
4.  **Reopen in Container:** Open Command Pallete by (`Ctrl+Shift+P` or `F1` -> "Dev Containers: Reopen in Container").
5.  **Wait for Build:** The first time, Docker will build the `app` image and download the PostgreSQL image. Subsequent starts will be much faster. VS Code will install the specified extensions and run setup commands (`yarn install`, `yarn prisma generate`).
6.  **Start Developing:** Once the container is ready, VS Code will be connected. Use the integrated terminal (which runs inside the `app` container as the `node` user) to run project commands (e.g., `yarn dev`, `yarn storybook`, `yarn migrate:dev`).

## Key Features & Best Practices

- **Consistency:** Ensures all developers use the same OS, Node version, dependencies, and tooling.
- **Integrated Database:** Provides a dedicated PostgreSQL database that starts automatically with the environment.
- **Non-Root User:** Enhances security and prevents file permission issues with mounted volumes. Use `sudo` inside the terminal for system tasks (passwordless `sudo` is configured).
- **Persistence:** Node modules, database data, caches, and shell history are persisted using named volumes.
- **VS Code Integration:** Pre-installs useful extensions and applies tailored settings for optimal DX (ESLint, Prettier, GitLens, Prisma, Storybook, Peacock, etc.).
- **Task Automation:** Common tasks (start dev server, run migrations, lint, test) should be configured in `.vscode/tasks.json` for easy access via the Command Palette (`Ctrl+Shift+P` -> "Tasks: Run Task").
- **Debugging:** Debugging configurations for Next.js (client/server), Storybook, and tests should be defined in `.vscode/launch.json`.
- **Environment Variables:** Development secrets/config (like `DATABASE_URL`) are managed via a `.env` file in the project root.
- **Separation of Concerns:** This setup is strictly for _development_. Production builds use a separate, multi-stage `Dockerfile` (typically at the project root) and connect to managed cloud databases. Deployment configurations reside in the `deploy/` folder.

## Important Initial Setup Steps (After First Open)

Refer to the "Actionable Next Steps" section in `devcontainer.json` and the main project `README.md` for crucial one-time setup tasks like running `yarn prisma init`, setting up Husky, and configuring `.env`.
