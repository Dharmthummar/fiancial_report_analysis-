@echo off
REM Check if dependencies are already installed
python -m pip show opencv-python pytesseract pdf2image pandas numpy >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing dependencies...
    pip install -r requirements.txt
) else (
    echo Dependencies already installed. Skipping installation.
)

REM Run the Python script
python dk3.py

pause