# Videooo Cut

A cross-platform GUI desktop video editing application built with Python, PyQt6, and OpenCV.

## Features

- **Import Videos**: Support for MP4, AVI, MOV, MKV, and WebM formats
- **Video Preview**: Playback controls with frame-by-frame navigation
- **Rotation**: Rotate videos by 90°, 180°, or 270°
- **Crop Selection**: Drag to select area to crop (interactive crop rectangle)
- **Export**: Export processed videos with customizable quality settings:
  - Quality presets (High, Medium, Low, Custom)
  - Bitrate control
  - Codec selection (H.264, H.265/HEVC, MPEG-4)
  - Frame rate adjustment

## Setup

This project uses [uv](https://github.com/astral-sh/uv) for fast Python package management.

### Prerequisites

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) installed

### Installation

1. Install dependencies:
```bash
uv sync
```

2. Activate the virtual environment:
```bash
source .venv/bin/activate  # On macOS/Linux
# or
.venv\Scripts\activate     # On Windows
```

## Running the Application

### Development Mode

```bash
uv run python main.py
```

Or activate the virtual environment and run:
```bash
python main.py
```

## Building Executables

**Important:** Run the build script with `python build.py` (not `uv run build.py`). You can also use `uv run python build.py` if you want to ensure the virtual environment is used.

### Build for Current Platform

```bash
python build.py
# or
uv run python build.py
```

### Build for macOS

**Option 1: Using Python script (cross-platform)**
```bash
python build.py --mac
# or
python3 build.py --mac
```

**Option 2: Using shell script (macOS/Linux only)**
```bash
./build-mac.sh
```

**Note:** The build creates a `.app` bundle. You may need to sign it for distribution outside the App Store.

### Build for Windows

**Option 1: Using Python script (cross-platform)**
```bash
python build.py --win
```

**Option 2: Using Windows batch script (Windows only)**
```batch
build-windows.bat
```

**Option 3: Using PowerShell script (Windows only)**
```powershell
.\build-windows.ps1
```

**Important:** Windows executables must be built on a Windows machine. PyInstaller cannot create Windows `.exe` files on macOS or Linux.

**Options for building Windows version:**
1. **Use a Windows machine** (recommended) - Install Python and run `build-windows.bat`
2. **Use a Windows VM** - Run Windows in VirtualBox, VMware, or Parallels
3. **Use GitHub Actions** (free) - Push to GitHub and use the workflow (see `.github/workflows/build-windows.yml`)
4. **Use Wine** (experimental) - May work but not guaranteed: `WINEARCH=win64 wine python build.py --win`

The built executables will be in the `dist/` folder:
- **macOS**: Creates a `.app` bundle in `dist/videooo-cut.app`
- **Windows**: Creates a single `.exe` file in `dist/videooo-cut.exe`

## Project Structure

```
videooo-cut/
├── main.py              # Main application entry point
├── translations.py      # Translation strings for i18n
├── build.py             # Build script for creating executables
├── build-mac.sh         # macOS shell build script
├── build-windows.bat    # Windows batch build script
├── build-windows.ps1    # Windows PowerShell build script
├── pyproject.toml       # Project configuration and dependencies
└── README.md            # This file
```

## Development

### Adding Dependencies

```bash
uv add package-name
```

### Adding Development Dependencies

```bash
uv add --dev package-name
```

## Cross-Platform Building Tips

1. **macOS**: The built app will be a `.app` bundle. You may need to sign it for distribution.
2. **Windows**: The built app will be a `.exe` file. Consider code signing for distribution.
3. **Icons**: Add `.icns` (macOS) or `.ico` (Windows) files and update the build script.

## License

Add your license here.

