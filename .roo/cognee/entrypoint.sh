#!/bin/bash
set -e

PREBUILT_VENV_DIR="$BUILD_PATH/.venv"

TARGET_VENV_DIR="$WORKSPACE_PATH/.roo/cognee/.venv"

if [ -z "$BUILD_PATH" ] || [ -z "$WORKSPACE_PATH" ]; then
    echo "Entrypoint: ERROR - Required environment variables BUILD_PATH or WORKSPACE_PATH are missing!"
    echo "Entrypoint: Check the ENV definitions in your Dockerfile's final stage."
    exit 1
fi

echo "Entrypoint: Source: $PREBUILT_VENV_DIR"
echo "Entrypoint: Target: $TARGET_VENV_DIR"

if [ ! -d "$PREBUILT_VENV_DIR" ]; then
    echo "Entrypoint: ERROR - Pre-built source venv NOT FOUND at $PREBUILT_VENV_DIR!"
    echo "Entrypoint: Cannot proceed. Please check the Dockerfile build log and COPY commands."
    exit 1
fi

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
