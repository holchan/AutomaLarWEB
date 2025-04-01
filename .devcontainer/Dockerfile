# .devcontainer/Dockerfile

# Base Image: Node 22 on Debian Bookworm with TypeScript tools pre-installed.
# Includes node, npm, yarn, git, common utilities, and a non-root 'node' user (UID 1000 typically).
FROM mcr.microsoft.com/devcontainers/typescript-node:22-bookworm

# Set the working directory. Matches the target in docker-compose.yml volume mount.
WORKDIR /workspaces/${localWorkspaceFolderBasename}

# Install PostgreSQL client tools (useful for interacting with the DB service via psql)
# and clean up apt cache in the same layer to optimize image size.
RUN sudo apt-get update && export DEBIAN_FRONTEND=noninteractive \
   && sudo apt-get -y install --no-install-recommends postgresql-client \
   && sudo apt-get clean && sudo rm -rf /var/lib/apt/lists/*

# The container's command is managed by docker-compose.yml (sleep infinity).