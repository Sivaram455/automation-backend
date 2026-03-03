@echo off
echo Installing dependencies...
call venv\Scripts\pip install bcrypt passlib[bcrypt] pymysql cryptography python-jose[cryptography] python-multipart requests openai python-dotenv uvicorn fastapi sqlalchemy pydantic
echo.
echo Done! Testing import...
call venv\Scripts\python.exe -c "import bcrypt; import passlib; import pymysql; print('All imports OK!')"
pause
