#!/bin/bash
# This script installs the Cognee MCP server dependencies and downloads the necessary code.
set -e

echo "--- Installing Homebrew (if necessary) ---"
# Install Homebrew if the 'brew' command is not found
if ! command -v brew &> /dev/null
then
  # Run the official installer non-interactively
  yes | /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  # Add brew to PATH for the current script execution
  eval "$(/home/linuxbrew/.linuxbrew/bin/brew shellenv)"
  # Add brew to PATH for future shell sessions by adding to .zshrc
  echo 'eval \"$(/home/linuxbrew/.linuxbrew/bin/brew shellenv)\"' >> /home/node/.zshrc
  echo "Homebrew installed and configured."
else
  echo "Homebrew already installed."
fi

echo "--- Downloading Cognee-MCP using sparse clone ---"
# Define target directory within .roo and ensure it's clean
TARGET_DIR="/workspace/.roo/cognee" # Renamed directory
rm -rf "$TARGET_DIR"
mkdir -p /workspace/.roo # Ensure .roo parent directory exists

# Attempt to disable credential helper globally to avoid interference
echo "Disabling global credential helper..."
git config --global --unset credential.helper || true

# Clone repository sparsely (only metadata, no blobs initially)
echo "Cloning sparsely into $TARGET_DIR..."
git clone --filter=blob:none --sparse --depth 1 --branch dev https://github.com/topoteretes/cognee.git "$TARGET_DIR"
if [ $? -ne 0 ]; then
  echo "Error: Failed to clone repository."
  exit 1
fi

# Configure sparse checkout within the repository
cd "$TARGET_DIR"
echo "Setting sparse checkout to only include 'cognee-mcp'..."
git sparse-checkout set cognee-mcp
if [ $? -ne 0 ]; then
  echo "Error: Failed to set sparse checkout."
  exit 1
fi

# Checkout the branch to populate the working directory with sparse files
echo "Checking out dev branch to populate sparse files..."
git checkout dev
if [ $? -ne 0 ]; then
  echo "Error: Failed to checkout dev branch."
  exit 1
fi
echo "Cognee-MCP downloaded successfully to $TARGET_DIR."

# Remove all files/dirs in root except cognee-mcp and .git
echo "Removing extraneous files from root..."
find . -maxdepth 1 -mindepth 1 ! -name "cognee-mcp" ! -name ".git" -exec rm -rf {} +
if [ $? -ne 0 ]; then
    echo "Warning: Failed to remove some extraneous files. Continuing..."
fi


# Create .gitignore to ignore everything in root, preventing accidental commits
echo "*" > .gitignore
echo "!.gitignore" >> .gitignore
echo "!cognee-mcp/" >> .gitignore

echo "--- Installing Cognee-MCP dependencies ---"
# Install dependencies inside the cognee-mcp folder
cd "$TARGET_DIR/cognee-mcp"
echo "Installing uv..."
brew install uv
echo "Syncing Python dependencies with uv..."
uv sync --dev --all-extras --reinstall
if [ $? -ne 0 ]; then
  echo "Error: Failed to install Python dependencies with uv."
  exit 1
fi

echo "--- Cognee MCP setup complete in $TARGET_DIR ---"
