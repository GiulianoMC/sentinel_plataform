#!/usr/bin/env python
import os
import sys
sys.path.append("/code")

from app.database import SessionLocal
from app.models.UserModel import User
from app.core.security import hash_password

def main():
    email = os.environ.get("ADMIN_EMAIL", "admin@sentinela.local")
    password = os.environ.get("ADMIN_PASSWORD", "changeme123")
    
    db = SessionLocal()
    try:
        if db.query(User).filter(User.email == email).first():
            print(f"Admin {email} já existe")
            return
        
        admin = User(
            email=email,
            hashed_password=hash_password(password),
            role="admin",
            is_active=True
        )
        db.add(admin)
        db.commit()
        print(f"Admin criado: {email}")
    finally:
        db.close()

if __name__ == "__main__":
    main()