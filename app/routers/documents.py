import hashlib
import os

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..config import get_settings
from ..db import get_db
from ..models import Document, User
from ..schemas import DocumentOut, ProcessResponse
from ..security import get_current_user
from ..s3 import upload_file

settings = get_settings()
router = APIRouter(tags=["documents"])


async def _find_by_hash(session:AsyncSession, user_id:int, file_hash:str):
    loader = await session.execute(select(Document).where(Document.file_hash == file_hash, 
                                                          Document.user_id == user_id))
    oneFile = loader.scalar_one_or_none()
    return oneFile

@router.post("/upload")
async def upload(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only PDF files are supported")
    
    content = await file.read()
    
    if len(content) > (settings.max_upload_mb * 1024 * 1024):
        return HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, f"File is larger then {settings.max_upload_mb} MB")
        
    
    file_hash = hashlib.sha256(content).hexdigest()
    isFile = await _find_by_hash(session, user.id, file_hash)
    if isFile: ## None, {}
        return {"doc":isFile}
    
    
    key = upload_file(user.id, fileName=file.filename, content=content, content_type=file.content_type )
    
        
    doc = Document(user_id=user.id, filename=file.filename, 
                   file_hash=file_hash, s3_key=key)
    session.add(doc)
    await session.commit()
    await session.refresh(doc)
    
    return {"doc":doc }


@router.post("/process", response_model=ProcessResponse)
async def process(user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db)):
    processed, skipped = [], []
    ### list all the pdfs (files) : 
    ### read one to one pdf
    
    
    return ProcessResponse(processed=processed, skipped=skipped)


@router.get("/read", response_model=list[DocumentOut])
async def read(user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db)):
    return (await session.scalars(select(Document).where(Document.user_id == user.id))).all()


@router.delete("/delete/{doc_id}")
async def delete(doc_id: int, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db)):
    doc = await session.get(Document, doc_id)
    if not doc or doc.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")

    return {"deleted": doc_id}


#### You have to deploy this complete project on Docker.