from __future__ import annotations

from abc import ABC, abstractmethod


class VictimAdapter(ABC):
    """Abstract base class for all victim integrations."""

    @abstractmethod
    async def send_turn(
        self,
        session_id: str,
        message: str,
        *,
        mode: str = "chat",
        timeout: float = 120.0,
    ) -> dict:
        """Send one conversation turn and return response payload."""

    @abstractmethod
    async def upload_file(
        self,
        session_id: str,
        filename: str,
        content: bytes,
        content_type: str,
        *,
        timeout: float = 120.0,
    ) -> dict:
        """Upload a file to the victim and return server response dict."""

    @abstractmethod
    async def list_docs(
        self,
        session_id: str,
        *,
        timeout: float = 30.0,
    ) -> list[dict]:
        """List documents visible to the given session."""

    @abstractmethod
    async def reset_session(
        self,
        session_id: str,
        *,
        timeout: float = 10.0,
    ) -> None:
        """Reset/clear session state on the victim."""
