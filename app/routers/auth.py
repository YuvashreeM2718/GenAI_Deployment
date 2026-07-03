"""Auth endpoints: register, sign in (get a token), and read the current user."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta
from ..db import get_db
from ..models import User
from ..schemas import UserCreate, UserOut, Token, LoginDTO
from ..security import hash_password, verify_password, get_current_user
import jwt
from ..config import get_settings

router = APIRouter(tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(data: UserCreate, session: AsyncSession = Depends(get_db)):
    existing = (await session.scalars(select(User).where(User.email == data.email))).first()
    if existing:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Email already registered")
    user = User(email=data.email, hashed_password=hash_password(data.password))
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@router.post("/signin", response_model=Token)
async def signin(user:LoginDTO, db: AsyncSession = Depends(get_db)):
    setting = get_settings()
    isUser = await db.execute(
        select(User).where(User.email == user.username)
    )
    isUser = isUser.scalar_one_or_none()
    if not isUser :
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="You entered wrong username")
    
    if not verify_password(user.password, isUser.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="You entered wrong password")
    
    expTime = datetime.now() + timedelta(minutes=setting.jwt_expire_minutes)
    token = jwt.encode({"_id":isUser.id, "exp":expTime}, setting.jwt_secret, setting.jwt_algorithm)
    return {"access_token":token}


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return user
