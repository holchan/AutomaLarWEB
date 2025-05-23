#!/bin/bash
echo "--- ENTRYPOINT DEBUG ---"
echo "BUILD_PATH value: [${BUILD_PATH}]"
echo "WORKSPACE_PATH value: [${WORKSPACE_PATH}]"
echo "WEB_WORKSPACE_PATH value: [${WEB_WORKSPACE_PATH}]"
echo "PREBUILT_VENV_DIR will be: [${BUILD_PATH}/.venv]"
echo "TARGET_VENV_DIR will be: [${WORKSPACE_PATH}${WEB_WORKSPACE_PATH}/.roo/cognee/.venv]"
echo "Initial PATH: [${PATH}]"
echo "Arguments passed to script (\$@): [${@}]"
echo "--- END DEBUG ---"
set -e

PREBUILT_VENV_DIR="$BUILD_PATH/.venv"
TARGET_VENV_DIR="$WORKSPACE_PATH$WEB_WORKSPACE_PATH/.roo/cognee/.venv"

if [ ! -d "$PREBUILT_VENV_DIR" ]; then
    echo "FATAL ERROR: Intermediate venv directory $PREBUILT_VENV_DIR does not exist in the image!"
    exit 1
fi

if [ -d "$TARGET_VENV_DIR" ]; then
    echo "Entrypoint: Removing existing target directory $TARGET_VENV_DIR..."
    rm -rf "$TARGET_VENV_DIR"
    echo "Entrypoint: Existing target directory removed."
fi

echo "Entrypoint: Copying pre-built environment from $PREBUILT_VENV_DIR to $TARGET_VENV_DIR..."
mkdir -p "$(dirname "$TARGET_VENV_DIR")"
cp -a "$PREBUILT_VENV_DIR/." "$TARGET_VENV_DIR/"
echo "Entrypoint: Pre-built environment copied successfully."

echo "Entrypoint: Removing intermediate source venv from $PREBUILT_VENV_DIR..."
rm -rf "$PREBUILT_VENV_DIR"
if [ -d "$BUILD_PATH" ] && [ -z "$(ls -A "$BUILD_PATH")" ]; then
    echo "Entrypoint: Removing empty intermediate parent directory $BUILD_PATH..."
    rm -rf "$BUILD_PATH"
fi
echo "Entrypoint: Intermediate source venv (and possibly parent) removed."

echo "Entrypoint: Using PATH: $PATH"
echo "Entrypoint: Executing container command: ${@}"

exec "$@"
