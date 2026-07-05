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
from ..rag.ingest import process_pdf

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
    
    file_hash = hashlib.sha256(content).hexdigest()
    isFile = await _find_by_hash(session, user.id, file_hash)
    if isFile:
        return {"doc":isFile}
    
    user_dir = os.path.join(settings.upload_dir, str(user.id))
    os.makedirs(user_dir, exist_ok=True)
    path = os.path.join(user_dir, file.filename)
    
    with open(path, "wb") as f:
        f.write(content)
        
    doc = Document(user_id=user.id, filename=file.filename, 
                   file_hash=file_hash, 
                   path=path,
                   status="processing")
    session.add(doc)
    await session.commit()
    await session.refresh(doc)
    
    pages = await process_pdf(user.id, doc.id, path, file.filename)
    doc.status = "ready"
    doc.pages = pages
    session.add(doc)
    await session.commit()
    await session.refresh(doc)
    
    return {"doc":doc }


@router.post("/process", response_model=ProcessResponse)
async def process(user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db)):
    processed, skipped = [], []

    return ProcessResponse(processed=processed, skipped=skipped)


@router.get("/read", response_model=list[DocumentOut])
async def read(user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db)):
    return (await session.scalars(select(Document).where(Document.user_id == user.id))).all()


@router.delete("/delete/{doc_id}")
async def delete(doc_id: int, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db)):
    doc = await session.get(Document, doc_id)
    if not doc or doc.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")

    #### delete emebeddings
    
    if doc.path.startswith(settings.upload_dir) and os.path.exists(doc.path):
        os.remove(doc.path)                      
    await session.delete(doc)
    await session.commit()
    return {"deleted": doc_id}
