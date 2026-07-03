from datetime import datetime

import jwt
from fastapi import Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from pwdlib import PasswordHash
from .config import get_settings
from .db import get_db
from .models import User


settings = get_settings()
hashalgo = PasswordHash.recommended()


def hash_password(password:str) -> str:
    return hashalgo.hash(password)

def verify_password(password: str, hash_pass:str) -> bool:
    return hashalgo.verify(password, hash_pass)

async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    token = request.headers.get("authorization", "")
    token = token.split(" ")[-1]
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"error":"You are Unauthorized !"})
        
    try:
        data = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except Exception:
        raise credentials_error
    
    user_id = data.get("_id")

    user = await session.get(User, user_id)
    if user is None:
        raise credentials_error
  
    return user
