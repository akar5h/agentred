from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from harness.victim.mock.handlers import handle_chat
from harness.victim.mock.state import add_doc, get_doc, get_or_create, list_docs, reset

app = FastAPI(title="deeppeak-harness mock victim", docs_url=None, redoc_url=None)


class ChatRequest(BaseModel):
    session_id: str
    message: str


class ResetRequest(BaseModel):
    session_id: str


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat")
async def chat(req: ChatRequest) -> dict:
    response = handle_chat(req.session_id, req.message)
    return {"response": response, "usage": {}}


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest) -> StreamingResponse:
    response = handle_chat(req.session_id, req.message)

    async def _gen() -> AsyncIterator[bytes]:
        payload = json.dumps({"result": {"response": response, "usage": {}}})
        yield f"event: done\ndata: {payload}\n\n".encode("utf-8")

    return StreamingResponse(_gen(), media_type="text/event-stream")


@app.post("/upload")
async def upload(file: UploadFile = File(...), session_id: str = Form(...)) -> dict:
    body = await file.read()
    text = body.decode("utf-8", errors="ignore")
    doc = add_doc(session_id=session_id, filename=file.filename, content_text=text)
    return {"id": doc.id, "filename": doc.filename}


@app.get("/docs")
async def docs(session_id: str) -> list[dict]:
    out: list[dict] = []
    for doc in list_docs(session_id):
        out.append(
            {
                "id": doc.id,
                "filename": doc.filename,
                "is_ai_generated": doc.filename.startswith("ai_generated"),
            }
        )
    return out


@app.get("/docs/{doc_id}")
async def doc_detail(doc_id: int, session_id: str) -> dict:
    doc = get_doc(session_id, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="doc not found")
    return {"id": doc.id, "content_text": doc.content_text, "filename": doc.filename}


@app.post("/reset")
async def reset_session(req: ResetRequest) -> dict:
    reset(req.session_id)
    get_or_create(req.session_id)
    return {"ok": True}
