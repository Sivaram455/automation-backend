"""
Quick diagnostic + startup script for Windows.
Run with: python startup_check.py
"""
import subprocess
import sys
import os

os.chdir(os.path.dirname(os.path.abspath(__file__)))

print("="*55)
print("  JobPull Backend - Startup Check")
print("="*55)

# 1. Check/install packages
packages = [
    ("bcrypt", "bcrypt"),
    ("passlib[bcrypt]", "passlib"),
    ("pymysql", "pymysql"),
    ("cryptography", "cryptography"),
    ("python-jose[cryptography]", "jose"),
    ("python-multipart", "multipart"),
    ("requests", "requests"),
    ("openai", "openai"),
    ("uvicorn", "uvicorn"),
    ("fastapi", "fastapi"),
    ("sqlalchemy", "sqlalchemy"),
    ("pydantic", "pydantic"),
    ("python-dotenv", "dotenv"),
    ("beautifulsoup4", "bs4"),
]

print("\n[1] Checking packages...")
missing = []
for pip_name, import_name in packages:
    try:
        __import__(import_name)
        print(f"  OK  {pip_name}")
    except ImportError:
        print(f"  MISSING  {pip_name}")
        missing.append(pip_name)

if missing:
    print(f"\n  Installing {len(missing)} missing packages...")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install"] + missing,
        capture_output=True, text=True
    )
    print(result.stdout[-1000:] if result.stdout else "")
    if result.returncode != 0:
        print("ERROR:", result.stderr[-500:])
    else:
        print("  All packages installed!")

# 2. Check auth imports
print("\n[2] Checking auth module...")
try:
    from passlib.context import CryptContext
    ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
    h = ctx.hash("test")
    assert ctx.verify("test", h)
    print("  OK  passlib + bcrypt working")
except Exception as e:
    print(f"  ERROR: {e}")

# 3. Check DB connectivity  
print("\n[3] Checking MySQL connection...")
try:
    import pymysql
    conn = pymysql.connect(
        host="127.0.0.1", user="root",
        password="welcome@123", db="jobpulldb",
        connect_timeout=3
    )
    print("  OK  MySQL connected!")
    conn.close()
except Exception as e:
    print(f"  WARN: MySQL not reachable: {e}")
    print("       Make sure MySQL service is running.")

print("\n[4] Starting uvicorn on http://localhost:8000 ...")
print("="*55)

# 4. Start uvicorn (Windows compatible)
os.system(f'"{sys.executable}" -m uvicorn main:app --reload --port 8000')
