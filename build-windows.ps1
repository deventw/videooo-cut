# Build script for Windows (PowerShell)
# Usage: .\build-windows.ps1

Write-Host "Building videooo-cut for Windows..." -ForegroundColor Cyan
Write-Host ""

# Check if Python is available
try {
    $pythonVersion = python --version 2>&1
    Write-Host "Found Python: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "Error: Python is not installed or not in PATH" -ForegroundColor Red
    exit 1
}

# Check if PyInstaller is installed
try {
    python -c "import PyInstaller" 2>&1 | Out-Null
    Write-Host "PyInstaller found" -ForegroundColor Green
} catch {
    Write-Host "PyInstaller not found. Installing..." -ForegroundColor Yellow
    pip install pyinstaller
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Failed to install PyInstaller" -ForegroundColor Red
        exit 1
    }
}

# Run the build script
Write-Host ""
Write-Host "Running build script..." -ForegroundColor Cyan
python build.py --win

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "Build failed!" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Build completed successfully!" -ForegroundColor Green
Write-Host "The executable is in the dist folder: dist\videooo-cut.exe" -ForegroundColor Green
Write-Host ""

