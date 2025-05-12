ARG WEB_WORKSPACE_PATH="/automalarweb"
ARG WEB_WORKSPACE_USER="node"
ARG WEB_WORKSPACE_GROUP="node"
ARG WORKSPACE_PATH=""
ARG WORKSPACE_USER=""

FROM mcr.microsoft.com/devcontainers/typescript-node:22-bookworm

USER root

WORKDIR ${WORKSPACE_PATH}${WEB_WORKSPACE_PATH}

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get -y install --no-install-recommends \
        curl \
        gnupg \
        lsb-release \
        software-properties-common \
        postgresql-client \
        zsh \
    && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | gpg --dearmor -o /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update \
    && apt-get -y install --no-install-recommends gh \
    && apt-get -y upgrade \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN echo "$(which zsh)" >> /etc/shells \
    && usermod -s "$(which zsh)" ${WEB_WORKSPACE_USER}

USER ${WEB_WORKSPACE_USER}

LABEL dev.containers.metadata='{ \
  "initializeCommand": "echo \"Starting Dev Container setup...\"", \
  "postCreateCommand": "sudo chown -R ${localEnv:WORKSPACE_USER}:${localEnv:WORKSPACE_GROUP:-${localEnv:WORKSPACE_USER}} ${localEnv:WORKSPACE_PATH}${localEnv:WEB_WORKSPACE_PATH}", \
  "postStartCommand": "cd ${localEnv:WORKSPACE_PATH}${localEnv:WEB_WORKSPACE_PATH} && yarn install --frozen-lockfile || (yarn install && npx prisma generate)", \
  "postAttachCommand": { \
    "server": "echo \"Attached to AutomaLarWEB Dev Container! 🔥\" && git config --global --add safe.directory ${localEnv:WORKSPACE_PATH}${localEnv:WEB_WORKSPACE_PATH}" \
  }, \
  "portsAttributes": { \
    "3000": { "label": "Next.js App", "onAutoForward": "openPreview" }, \
    "6006": { "label": "Storybook", "onAutoForward": "notify" }, \
    "5432": { "label": "PostgreSQL DB", "onAutoForward": "silent" }, \
    "5555": { "label": "Prisma Studio", "onAutoForward": "openPreview" }, \
    "8000": { "label": "Cognee MCP", "onAutoForward": "silent" } \
  }, \
  "customizations": { \
    "vscode": { \
      "extensions": [ \
        "dbaeumer.vscode-eslint", \
        "esbenp.prettier-vscode", \
        "eamodio.gitlens", \
        "github.vscode-pull-request-github", \
        "ms-azuretools.vscode-docker", \
        "ms-vscode.vscode-typescript-next", \
        "streetsidesoftware.code-spell-checker", \
        "usernamehw.errorlens", \
        "oderwat.indent-rainbow", \
        "christian-kohler.path-intellisense", \
        "formulahendry.auto-rename-tag", \
        "wayou.vscode-todo-highlight", \
        "mikestead.dotenv", \
        "wix.vscode-import-cost", \
        "pkief.material-icon-theme", \
        "ms-vsliveshare.vsliveshare", \
        "rangav.vscode-thunder-client", \
        "johnpapa.vscode-peacock", \
        "bradlc.vscode-tailwindcss", \
        "orta.vscode-jest", \
        "prisma.prisma", \
        "slevesque.shader", \
        "RooVeterinaryInc.roo-cline" \
        "editorconfig.editorconfig" \
      ] \
    } \
  } \
}'
