"""Object storage retrieval (serves stored/label images to the frontend).

Delegates to the configured StorageService; a missing object surfaces as a
structured 404 via the storage backend.
"""
from __future__ import annotations

import mimetypes

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from app.api.deps import get_current_user, get_services_dep
from app.models import User
from app.services.registry import Services

router = APIRouter(prefix="/storage", tags=["storage"])


@router.get("/{key:path}")
def get_object(
    key: str,
    _user: User = Depends(get_current_user),
    services: Services = Depends(get_services_dep),
) -> Response:
    data = services.storage.read(key=key)
    media_type = mimetypes.guess_type(key)[0] or "application/octet-stream"
    return Response(content=data, media_type=media_type)
