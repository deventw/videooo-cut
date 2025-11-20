#!/bin/bash
# Build script for macOS
# Usage: ./build-mac.sh

set -e  # Exit on error

echo "Building videooo-cut for macOS..."
echo ""

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed or not in PATH"
    exit 1
fi

PYTHON_VERSION=$(python3 --version 2>&1)
echo "Found: $PYTHON_VERSION"

# Check if PyInstaller is installed
if ! python3 -c "import PyInstaller" 2>&1 > /dev/null; then
    echo "PyInstaller not found. Installing..."
    pip3 install pyinstaller
    if [ $? -ne 0 ]; then
        echo "Failed to install PyInstaller"
        exit 1
    fi
fi

# Run the build script
echo ""
echo "Running build script..."
python3 build.py --mac

if [ $? -ne 0 ]; then
    echo ""
    echo "Build failed!"
    exit 1
fi

echo ""
echo "✓ Build completed successfully!"
echo "The app bundle is in the dist folder: dist/videooo-cut.app"
echo ""
echo "You can run it with:"
echo "  open dist/videooo-cut.app"
echo ""

