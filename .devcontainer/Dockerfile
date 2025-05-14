ARG NODE_VERSION="22"
FROM node:${NODE_VERSION}-bookworm-slim

ARG TIMEZONE="America/Sao_Paulo"

ARG WEB_WORKSPACE_PATH="/automalarweb"
ARG WEB_WORKSPACE_USER="node"
ARG WEB_WORKSPACE_USER_UID="1000"
ARG WEB_WORKSPACE_GROUP_UID="1000"
ARG WORKSPACE_PATH=""

ARG NVM_VERSION="0.39.7"

ENV DEBIAN_FRONTEND=noninteractive
ENV NVM_DIR="/opt/nvm"

ENV PATH="${NVM_DIR}/versions/node/v${NODE_VERSION}/bin:${PATH}"

USER root

WORKDIR ${WORKSPACE_PATH}${WEB_WORKSPACE_PATH}

RUN apt-get update \
    && apt-get -y install --no-install-recommends \
        curl \
        gnupg \
        lsb-release \
        software-properties-common \
        postgresql-client \
        zsh \
        apt-utils \
        sudo \
        git \
        openssh-client \
        procps \
        wget \
        unzip \
        nano \
        jq \
        ca-certificates \
        dialog \
        locales \
        tzdata \
    && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | gpg --dearmor -o /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update \
    && apt-get -y install --no-install-recommends gh \
    && apt-get -y upgrade \
    && apt-get autoremove -y \
    && apt-get clean -y \
    && rm -rf /var/lib/apt/lists/*


# Create non-root user and group
RUN if ! getent group "${WEB_WORKSPACE_GROUP_UID}" > /dev/null 2>&1; then \
        groupadd --gid "${WEB_WORKSPACE_GROUP_UID}" "${WEB_WORKSPACE_USER}"; \
    fi \
    && if ! id -u "${WEB_WORKSPACE_USER}" > /dev/null 2>&1; then \
        useradd --uid "${WEB_WORKSPACE_USER_UID}" --gid "${WEB_WORKSPACE_GROUP_UID}" --shell /bin/bash -m "${WEB_WORKSPACE_USER}"; \
    else \
        usermod --uid "${WEB_WORKSPACE_USER_UID}" --gid "${WEB_WORKSPACE_GROUP_UID}" "${WEB_WORKSPACE_USER}"; \
    fi

# Configure passwordless sudo for user.
RUN echo "${WEB_WORKSPACE_USER} ALL=(ALL) NOPASSWD:ALL" > "/etc/sudoers.d/${WEB_WORKSPACE_USER}" \
    && chmod 0440 "/etc/sudoers.d/${WEB_WORKSPACE_USER}"

# Configure locale
RUN echo "en_US.UTF-8 UTF-8" >> /etc/locale.gen \
    && locale-gen en_US.UTF-8 \
    && update-locale LANG=en_US.UTF-8
ENV LANG=en_US.UTF-8
ENV LANGUAGE=en_US:en
ENV LC_ALL=en_US.UTF-8

# Configure Timezone
RUN ln -snf "/usr/share/zoneinfo/${TIMEZONE}" /etc/localtime \
    && echo "${TIMEZONE}" > /etc/timezone \
    && dpkg-reconfigure -f noninteractive tzdata

# Install NVM
RUN mkdir -p "${NVM_DIR}" \
    && curl -o- "https://raw.githubusercontent.com/nvm-sh/nvm/v${NVM_VERSION}/install.sh" | PROFILE=/dev/null NVM_DIR="${NVM_DIR}" bash \
    && { \
        echo ""; \
        echo "export NVM_DIR=\"${NVM_DIR}\""; \
        echo "[ -s \"\$NVM_DIR/nvm.sh\" ] && \. \"\$NVM_DIR/nvm.sh\""; \
        echo "[ -s \"\$NVM_DIR/bash_completion\" ] && \. \"\$NVM_DIR/bash_completion\""; \
    } >> /etc/skel/.bashrc \
    && cp /etc/skel/.bashrc "/home/${WEB_WORKSPACE_USER}/.bashrc" \
    && { \
        echo ""; \
        echo "export NVM_DIR=\"${NVM_DIR}\""; \
        echo "[ -s \"\$NVM_DIR/nvm.sh\" ] && \. \"\$NVM_DIR/nvm.sh\""; \
    } >> /etc/skel/.zshrc; \
    if [ ! -f "/home/${WEB_WORKSPACE_USER}/.zshrc" ]; then cp /etc/skel/.zshrc "/home/${WEB_WORKSPACE_USER}/.zshrc" 2>/dev/null || touch "/home/${WEB_WORKSPACE_USER}/.zshrc"; fi; \
    if ! grep -q "NVM_DIR" "/home/${WEB_WORKSPACE_USER}/.zshrc"; then \
        { echo ""; echo "export NVM_DIR=\"${NVM_DIR}\""; echo "[ -s \"\$NVM_DIR/nvm.sh\" ] && \. \"\$NVM_DIR/nvm.sh\""; } >> "/home/${WEB_WORKSPACE_USER}/.zshrc"; \
    fi; \
    chown -R "${WEB_WORKSPACE_USER_UID}:${WEB_WORKSPACE_GROUP_UID}" "${NVM_DIR}" "/home/${WEB_WORKSPACE_USER}/.bashrc" \
    && if [ -f "/home/${WEB_WORKSPACE_USER}/.zshrc" ]; then chown "${WEB_WORKSPACE_USER_UID}:${WEB_WORKSPACE_GROUP_UID}" "/home/${WEB_WORKSPACE_USER}/.zshrc"; fi \
    && chmod -R g+rwx "${NVM_DIR}"

# Install Node.js (uses your NODE_VERSION ARG), Yarn, & TypeScript
RUN bash -c ". ${NVM_DIR}/nvm.sh \
    && nvm install ${NODE_VERSION} \
    && nvm alias default ${NODE_VERSION} \
    && nvm use default \
    && npm install -g typescript yarn"

# Set Zsh as default shell and Install Oh My Zsh for user.
RUN _ZSH_INSTALL_PATH=$(which zsh) \
    && [ -n "$_ZSH_INSTALL_PATH" ] \
    && grep -qxF "$_ZSH_INSTALL_PATH" /etc/shells || echo "$_ZSH_INSTALL_PATH" >> /etc/shells \
    && usermod -s "$_ZSH_INSTALL_PATH" "${WEB_WORKSPACE_USER}" \
    && _OMZ_SCRIPT="/tmp/install_omz.sh" \
    && echo '#!/bin/bash' > "${_OMZ_SCRIPT}" \
    && echo "set -e" >> "${_OMZ_SCRIPT}" \
    && echo "if [ ! -f \"/home/${WEB_WORKSPACE_USER}/.zshrc\" ]; then touch \"/home/${WEB_WORKSPACE_USER}/.zshrc\"; fi" >> "${_OMZ_SCRIPT}" \
    && echo "chown '${WEB_WORKSPACE_USER_UID}:${WEB_WORKSPACE_GROUP_UID}' \"/home/${WEB_WORKSPACE_USER}/.zshrc\"" >> "${_OMZ_SCRIPT}" \
    && echo "sh -c \"\$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh) --unattended\"" >> "${_OMZ_SCRIPT}" \
    && echo "if ! grep -q 'NVM_DIR=\"${NVM_DIR}\"' \"/home/${WEB_WORKSPACE_USER}/.zshrc\"; then " >> "${_OMZ_SCRIPT}" \
    && echo "  { echo ''; echo 'export NVM_DIR=\"${NVM_DIR}\"'; echo '[ -s \"\$NVM_DIR/nvm.sh\" ] && \. \"\$NVM_DIR/nvm.sh\"'; } >> \"/home/${WEB_WORKSPACE_USER}/.zshrc\"; " >> "${_OMZ_SCRIPT}" \
    && echo "fi" >> "${_OMZ_SCRIPT}" \
    && chmod +x "${_OMZ_SCRIPT}" \
    && sudo -u "${WEB_WORKSPACE_USER}" SHELL="${_ZSH_INSTALL_PATH}" HOME="/home/${WEB_WORKSPACE_USER}" bash "${_OMZ_SCRIPT}" \
    && rm "${_OMZ_SCRIPT}" \
    && echo "Zsh, Oh My Zsh, and NVM sourcing configured for ${WEB_WORKSPACE_USER}."

USER ${WEB_WORKSPACE_USER_UID}

ENV HOME="/home/${WEB_WORKSPACE_USER}"

LABEL dev.containers.metadata='{ \
  "initializeCommand": "echo \"Starting Dev Container setup...\"", \
  "postCreateCommand": "sudo chown -R ${localEnv:HOST_USER_NAME:-${WEB_WORKSPACE_USER}}:${localEnv:HOST_GROUP_ID:-${WEB_WORKSPACE_GROUP_UID}} ${WORKSPACE_PATH}${WEB_WORKSPACE_PATH}", \
  "postStartCommand": "cd ${WORKSPACE_PATH}${WEB_WORKSPACE_PATH} && yarn install --frozen-lockfile || (yarn install && npx prisma generate)", \
  "postAttachCommand": { \
    "server": "echo \"Attached to ${WEB_PROJECT_SLUG} Dev Container! 🔥\" && git config --global --add safe.directory ${WORKSPACE_PATH}${WEB_WORKSPACE_PATH}" \
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
        "dbaeumer.vscode-eslint", "esbenp.prettier-vscode", "eamodio.gitlens", \
        "github.vscode-pull-request-github", "ms-azuretools.vscode-docker", \
        "ms-vscode.vscode-typescript-next", "streetsidesoftware.code-spell-checker", \
        "usernamehw.errorlens", "oderwat.indent-rainbow", "christian-kohler.path-intellisense", \
        "formulahendry.auto-rename-tag", "wayou.vscode-todo-highlight", "mikestead.dotenv", \
        "wix.vscode-import-cost", "pkief.material-icon-theme", "ms-vsliveshare.vsliveshare", \
        "rangav.vscode-thunder-client", "johnpapa.vscode-peacock", "bradlc.vscode-tailwindcss", \
        "orta.vscode-jest", "prisma.prisma", "slevesque.shader", "RooVeterinaryInc.roo-cline", \
        "editorconfig.editorconfig" \
      ] \
    } \
  } \
}'

CMD ["/bin/zsh"]
