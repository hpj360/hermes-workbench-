@echo off

rem 检查 Python 是否可用
python --version >nul 2>&1
if %errorlevel% equ 0 (
    python "%~dp0scripts\skill_manager.py" %*
) else (
    echo Python is not available.
    echo Please install Python to use skill-manager.
    pause
    exit /b 1
)