#!/bin/bash
set -e

PREBUILT_VENV_DIR="$BUILD_PATH/.venv"

TARGET_VENV_DIR="$WORKSPACE_PATH$WEB_WORKSPACE_PATH/.roo/cognee/.venv"

echo "Cognee Entrypoint: Source: $PREBUILT_VENV_DIR"
echo "Cognee Entrypoint: Target: $TARGET_VENV_DIR"

echo "Entrypoint: Removing existing target directory (if any) at $TARGET_VENV_DIR..."
rm -rf "$TARGET_VENV_DIR"
echo "Entrypoint: Existing target directory removed."

echo "Entrypoint: Copying pre-built environment from $PREBUILT_VENV_DIR to $TARGET_VENV_DIR..."
mkdir -p "$(dirname "$TARGET_VENV_DIR")"
cp -a "$PREBUILT_VENV_DIR/." "$TARGET_VENV_DIR/"
echo "Entrypoint: Pre-built environment copied successfully."

echo "Entrypoint: Removing source pre-built venv from $PREBUILT_VENV_DIR..."
rm -rf "$PREBUILT_VENV_DIR"
echo "Entrypoint: Source pre-built venv removed."

export PATH="$TARGET_VENV_DIR/bin:$PATH"

echo "Entrypoint: Using PATH: $PATH"
echo "Entrypoint: Executing container command: $@"

exec "$@"
