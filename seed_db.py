from database import SessionLocal
from routers.auth import initialize_demo_users
from models import Role, User

if __name__ == "__main__":
    db = SessionLocal()
    try:
        initialize_demo_users(db)
        print("Successfully seeded the database with default admin, recruiter, and candidate!")
    except Exception as e:
        print(f"Error seeding database: {e}")
    finally:
        db.close()
