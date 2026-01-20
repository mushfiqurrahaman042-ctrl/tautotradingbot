@echo off
REM Production Deployment Script for Arts Trading Bot
REM This script sets up and starts the production bot

echo Starting Arts Trading Bot Production Deployment...

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo Python is not installed or not in PATH
    echo Please install Python 3.8 or higher
    pause
    exit /b 1
)

REM Check if requirements are installed
echo Installing dependencies...
pip install -r requirements.txt

REM Start the bot
echo Starting the trading bot...
python run.py

pause