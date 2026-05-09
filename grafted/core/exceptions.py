from __future__ import annotations


class HarnessError(Exception):
    """Base class for all grafted errors."""


class InfraError(HarnessError):
    """HTTP/network failure communicating with the victim."""


class CatalogError(HarnessError):
    """Catalog load or validation failure."""


class OracleError(HarnessError):
    """Oracle evaluation failure (e.g. LLM oracle API error)."""


class VictimResetError(HarnessError):
    """Failed to reset victim session between runs."""
