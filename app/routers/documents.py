"""Document endpoints. Upload/process/delete are ADMIN only (company knowledge base).
Reading the list is open to any logged-in user."""
import hashlib
import os

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..db import get_db
from ..models import Document, User
from ..schemas import DocumentOut, ProcessResponse
from ..security import get_current_user, require_admin
from ..rag.ingest import file_sha256, ingest, delete_document_vectors
from ..guardrails.rules import refresh_all

settings = get_settings()
router = APIRouter(tags=["documents"])


async def _find_by_hash(session: AsyncSession, file_hash: str) -> Document | None:
    return (await session.scalars(select(Document).where(Document.file_hash == file_hash))).first()


async def _ingest_new(session: AsyncSession, admin_id: int, path: str, filename: str, file_hash: str) -> Document:
    doc = Document(user_id=admin_id, filename=filename, file_hash=file_hash, path=path, status="processing")
    session.add(doc)
    await session.commit()
    await session.refresh(doc)
    try:
        doc.pages = await ingest(doc.id, path, filename)
        doc.status = "ready"
    except Exception as exc:
        print("exception",exc)
        doc.status = "failed"
        await session.commit()
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR,
                            f"Failed to process {filename}: {type(exc).__name__}: {exc}")
    await session.commit()
    await session.refresh(doc)
    await refresh_all()                 # <-- guardrails topics/rules + golden dataset auto-update
    return doc


@router.post("/upload", response_model=DocumentOut)
async def upload(
    file: UploadFile = File(...),
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only PDF files are supported")

    content = await file.read()
    file_hash = hashlib.sha256(content).hexdigest()

    existing = await _find_by_hash(session, file_hash)
    if existing:
        return existing

    os.makedirs(settings.upload_dir, exist_ok=True)
    path = os.path.join(settings.upload_dir, file.filename)
    with open(path, "wb") as f:
        f.write(content)
    return await _ingest_new(session, admin.id, path, file.filename, file_hash)


@router.post("/process", response_model=ProcessResponse)
async def process(admin: User = Depends(require_admin), session: AsyncSession = Depends(get_db)):
    """Process every PDF in the configured repo folder (skipping already-processed ones)."""
    os.makedirs(settings.repo_dir, exist_ok=True)
    processed, skipped = [], []
    for filename in sorted(os.listdir(settings.repo_dir)):
        if not filename.lower().endswith(".pdf"):
            continue
        path = os.path.join(settings.repo_dir, filename)
        file_hash = file_sha256(path)
        if await _find_by_hash(session, file_hash):
            skipped.append(filename)
            continue
        await _ingest_new(session, admin.id, path, filename, file_hash)
        processed.append(filename)
    return ProcessResponse(processed=processed, skipped=skipped)


@router.get("", response_model=list[DocumentOut])
async def read(user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db)):
    return (await session.scalars(select(Document).order_by(Document.id))).all()


@router.delete("/{doc_id}")
async def delete(doc_id: int, admin: User = Depends(require_admin), session: AsyncSession = Depends(get_db)):
    doc = await session.get(Document, doc_id)
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    await delete_document_vectors(doc.id)
    if doc.path.startswith(settings.upload_dir) and os.path.exists(doc.path):
        os.remove(doc.path)
    await session.delete(doc)
    await session.commit()
    return {"deleted": doc_id}
