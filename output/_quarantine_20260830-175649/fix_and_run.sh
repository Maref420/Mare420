#!/bin/bash

# 1. Fix main.py
cat > main.py << 'PYEOF'
from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from database import engine, SessionLocal, Base
from models import User
from auth import get_password_hash, authenticate_user, create_access_token, get_current_active_user, get_db

Base.metadata.create_all(bind=engine)

app = FastAPI()

@app.post("/users/")
def create_user(username: str, password: str, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.username == username).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Username already registered")
    hashed_password = get_password_hash(password)
    new_user = User(username=username, hashed_password=hashed_password)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {"message": "User created successfully"}

@app.post("/token")
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=400,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/users/me")
async def read_users_me(current_user: User = Depends(get_current_active_user)):
    return current_user

@app.get("/items/")
async def read_items(current_user: User = Depends(get_current_active_user)):
    return [{"name": "Item Foo", "owner": current_user.username}]
PYEOF

# 2. Restart Server
pkill -f uvicorn
sleep 1
uvicorn main:app --host 0.0.0.0 --port 8000 &
sleep 2

# 3. Test with variables to avoid browser formatting issues
HOST="127.0.0.1"
PORT="8000"
BASE_URL="<http://$HOST:$PORT>"

echo "Creating user..."
curl -X POST "$BASE_URL/users/?username=admin&password=test_password"
echo ""
