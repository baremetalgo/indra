"""Tiny shared utilities with no dependencies on other Indra modules.

Exists specifically to avoid circular imports between ``schemas`` (which
needs to mint IDs) and ``storage`` (which persists them).
"""

from __future__ import annotations

import uuid


def new_id() -> str:
    return uuid.uuid4().hex
