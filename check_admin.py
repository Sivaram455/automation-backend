import sys
from sqlalchemy.orm import Session
from database import SessionLocal
from models import User, Role

def check_admin():
    db = SessionLocal()
    try:
        # Check all roles
        roles = db.query(Role).all()
        print("--- Roles ---")
        for r in roles:
            print(f"Role ID: {r.id}, Name: {r.role_name}, Description: {r.description}")
        
        # Check all users
        users = db.query(User).all()
        print("\n--- Users ---")
        admin_found = False
        for u in users:
            role_name = next((r.role_name for r in roles if r.id == u.role_id), "Unknown")
            print(f"User ID: {u.id}, Email: {u.email}, Role: {role_name}, Active: {u.is_active}")
            if role_name == 'admin':
                admin_found = True
                
        if admin_found:
            print("\n Administrator user exists.")
        else:
            print("\n Administrator user DOES NOT exist.")
            
    except Exception as e:
        print(f"Database error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    check_admin()
