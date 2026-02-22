from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class MockDoc:
    id: int
    session_id: str
    filename: str
    content_text: str


@dataclass
class MockSession:
    session_id: str
    docs: list[MockDoc] = field(default_factory=list)
    next_doc_id: int = 1


_sessions: dict[str, MockSession] = {}


def get_or_create(session_id: str) -> MockSession:
    if session_id not in _sessions:
        _sessions[session_id] = MockSession(session_id=session_id)
    return _sessions[session_id]


def reset(session_id: str) -> None:
    _sessions.pop(session_id, None)


def add_doc(session_id: str, filename: str, content_text: str) -> MockDoc:
    sess = get_or_create(session_id)
    doc = MockDoc(
        id=sess.next_doc_id,
        session_id=session_id,
        filename=filename,
        content_text=content_text,
    )
    sess.docs.append(doc)
    sess.next_doc_id += 1
    return doc


def list_docs(session_id: str) -> list[MockDoc]:
    return list(get_or_create(session_id).docs)


def get_doc(session_id: str, doc_id: int) -> Optional[MockDoc]:
    for doc in get_or_create(session_id).docs:
        if doc.id == doc_id:
            return doc
    return None
