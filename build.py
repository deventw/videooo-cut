"""
Build script for creating cross-platform executables.
Usage:
    python build.py          # Build for current platform
    python build.py --mac    # Build for macOS
    python build.py --win    # Build for Windows (requires Windows or Wine)
"""
import subprocess
import sys
import platform
import os
from pathlib import Path


def build_app(target_platform=None):
    """Build the application for the specified platform."""
    if target_platform is None:
        target_platform = platform.system().lower()
    
    print(f"Building for {target_platform}...")
    
    # Check if translations.py exists
    translations_path = Path("translations.py")
    if not translations_path.exists():
        print("Warning: translations.py not found. Make sure it's in the project root.")
    
    # Base PyInstaller command
    cmd = [
        "pyinstaller",
        "--name=videooo-cut",
        "--windowed",  # No console window (GUI app)
        "--clean",
        "--noconfirm",  # Overwrite output directory without asking
    ]
    
    # Add translations.py as a hidden import to ensure it's included
    cmd.extend([
        "--hidden-import=translations",
    ])
    
    # Platform-specific options
    if target_platform == "darwin" or target_platform == "mac":
        # macOS: use onedir (not onefile) for .app bundles
        cmd.extend([
            "--onedir",
            "--osx-bundle-identifier=com.videooo.cut"
        ])
        # Add icon if it exists
        icon_path = "icon.icns"
        if os.path.exists(icon_path):
            cmd.extend(["--icon", icon_path])
    elif target_platform == "windows" or target_platform == "win":
        # Windows: onefile works fine
        cmd.extend([
            "--onefile",
            "--noconsole",  # Windows-specific: no console window
        ])
        # Add icon if it exists
        icon_path = "icon.ico"
        if os.path.exists(icon_path):
            cmd.extend(["--icon", icon_path])
    else:
        # Linux or other: use onefile
        cmd.append("--onefile")
    
    # Add main.py at the end
    cmd.append("main.py")
    
    print(f"Running: {' '.join(cmd)}")
    print()
    
    try:
        result = subprocess.run(cmd, check=True)
        print()
        if target_platform == "darwin" or target_platform == "mac":
            print(f"✓ Build complete! App bundle is in the 'dist/videooo-cut.app' folder.")
            print(f"  You can run it with: open dist/videooo-cut.app")
        elif target_platform == "windows" or target_platform == "win":
            print(f"✓ Build complete! Executable is in the 'dist' folder.")
            print(f"  File: dist/videooo-cut.exe")
        else:
            print(f"✓ Build complete! Executable is in the 'dist' folder.")
            print(f"  File: dist/videooo-cut")
    except subprocess.CalledProcessError as e:
        print(f"\n✗ Build failed: {e}")
        print("\nMake sure PyInstaller is installed:")
        print("  pip install pyinstaller")
        sys.exit(1)
    except FileNotFoundError:
        print("\n✗ PyInstaller not found!")
        print("Please install PyInstaller first:")
        print("  pip install pyinstaller")
        print("  or")
        print("  uv pip install pyinstaller")
        sys.exit(1)


if __name__ == "__main__":
    if "--mac" in sys.argv:
        build_app("mac")
    elif "--win" in sys.argv:
        build_app("win")
    else:
        build_app()

