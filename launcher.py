import subprocess
import sys

def main():
    with open("app_log.txt", "w", encoding="utf-8") as f:
        f.write("Installing dependencies...\n")
        f.flush()
        
        try:
            # Install packages
            pip_args = [
                sys.executable, "-m", "pip", "install", 
                "bcrypt", "passlib[bcrypt]", "pymysql", "cryptography", 
                "python-jose[cryptography]", "python-multipart", "requests", 
                "openai", "uvicorn", "fastapi", "sqlalchemy", 
                "pydantic", "python-dotenv", "beautifulsoup4"
            ]
            
            p1 = subprocess.run(pip_args, stdout=f, stderr=subprocess.STDOUT, text=True)
            f.write(f"\nPIP finished with code {p1.returncode}\n")
            f.flush()

            # Start backend
            f.write("\nStarting backend...\n")
            f.flush()
            
            p2 = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "main:app", "--port", "8000"],
                stdout=f, stderr=subprocess.STDOUT, text=True
            )
            
            f.write(f"Backend started with PID {p2.pid}\n")
            f.flush()
            
        except Exception as e:
            f.write(f"Error: {e}\n")

if __name__ == "__main__":
    main()
