"""
Core helpers used across the app (logger and shared helper functions).

This module provides the minimal surface area needed by the service after
being moved from another repo. It intentionally avoids external runtime
dependencies (other than `logging`) and exposes an `_get_firestore_client`
helper used by both the adapter and routes modules.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

from google.cloud import firestore


@lru_cache(maxsize=1)
def _get_firestore_client() -> Optional[firestore.Client]:
    """Return a Firestore client for the current project, or None on error.

    The behavior mirrors the standalone helper used in routes: if a project
    cannot be determined, the function returns a client with no explicit
    project, which will attempt to use application default credentials.
    On any exception, None is returned so higher-level code can fall back
    to treating Firestore as a dependent service that is unavailable.
    """
    try:
        proj = (
            os.environ.get("GCP_PROJECT")
            or os.environ.get("GCP_PROJECT_ID")
            or os.environ.get("GOOGLE_CLOUD_PROJECT")
        )
        return firestore.Client(project=proj) if proj else firestore.Client()
    except Exception:
        return None
