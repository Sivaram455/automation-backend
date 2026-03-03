@echo off
echo ============================================
echo  JobPull Backend - Dependency Installer
echo ============================================
echo.

echo Step 1: Installing Python dependencies...
venv\Scripts\pip install bcrypt passlib[bcrypt] pymysql cryptography python-jose[cryptography] python-multipart requests openai python-dotenv uvicorn fastapi sqlalchemy pydantic beautifulsoup4 python-docx pdfminer.six

echo.
echo Step 2: Verifying critical imports...
venv\Scripts\python -c "import bcrypt; from passlib.context import CryptContext; import pymysql; import jose; import fastapi; import uvicorn; print('[OK] All dependencies verified!')"

echo.
echo Step 3: Starting backend server...
echo Backend will be available at: http://localhost:8000
echo Press Ctrl+C to stop the server.
echo.
venv\Scripts\python -m uvicorn main:app --reload --port 8000
