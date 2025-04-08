FROM mcr.microsoft.com/devcontainers/typescript-node:22-bookworm

WORKDIR /workspaces/${localWorkspaceFolderBasename}

RUN sudo apt-get update && export DEBIAN_FRONTEND=noninteractive \
   && sudo apt-get -y install --no-install-recommends postgresql-client \
   && sudo apt-get clean && sudo rm -rf /var/lib/apt/lists/*
