from __future__ import annotations

from typing import Any

from harness.core.exceptions import CatalogError

REQUIRED_ATTACK_FIELDS = ("id", "category", "turns", "owasp", "atlas", "success_criteria")


def validate_catalog(payload: dict[str, Any], *, catalog_path: str = "") -> None:
    if not isinstance(payload, dict):
        raise CatalogError(f"Catalog root must be an object: {catalog_path or '<memory>'}")

    attacks = payload.get("attacks")
    if not isinstance(attacks, list):
        raise CatalogError(f"Catalog 'attacks' must be a list: {catalog_path or '<memory>'}")
    if not attacks:
        raise CatalogError(f"Catalog has no attacks: {catalog_path or '<memory>'}")

    for idx, attack in enumerate(attacks):
        if not isinstance(attack, dict):
            raise CatalogError(f"Attack #{idx} must be an object")
        attack_id = str(attack.get("id", f"index-{idx}"))

        for key in REQUIRED_ATTACK_FIELDS:
            if key not in attack:
                raise CatalogError(f"Missing required key '{key}' in attack: {attack_id}")

        turns = attack.get("turns")
        if not isinstance(turns, list) or not turns:
            raise CatalogError(f"Attack turns must be a non-empty list: {attack_id}")
        for turn_idx, turn in enumerate(turns):
            if not isinstance(turn, str) or not turn.strip():
                raise CatalogError(f"Attack turn #{turn_idx} must be a non-empty string: {attack_id}")

        prelude_turns = attack.get("prelude_turns", [])
        if prelude_turns is not None:
            if not isinstance(prelude_turns, list) or any(not isinstance(t, str) for t in prelude_turns):
                raise CatalogError(f"prelude_turns must be a list[str]: {attack_id}")

        uploads = attack.get("uploads", [])
        if uploads is not None:
            if not isinstance(uploads, list):
                raise CatalogError(f"uploads must be a list: {attack_id}")
            for upload_idx, upload in enumerate(uploads):
                if not isinstance(upload, dict):
                    raise CatalogError(f"uploads[{upload_idx}] must be an object: {attack_id}")
                if "fixture" not in upload:
                    raise CatalogError(f"uploads[{upload_idx}] missing 'fixture': {attack_id}")
