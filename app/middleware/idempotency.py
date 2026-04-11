import base64
import hashlib
from datetime import datetime, timedelta

from fastapi.responses import JSONResponse
from pymongo.errors import DuplicateKeyError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from ..core.config import settings
from ..database.mongo import get_db


IDEMPOTENCY_HEADER = "Idempotency-Key"
MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _hash_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


class IdempotencyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not settings.IDEMPOTENCY_ENABLED:
            return await call_next(request)

        method = request.method.upper()
        if method not in MUTATING_METHODS:
            return await call_next(request)

        key = request.headers.get(IDEMPOTENCY_HEADER)
        if not key:
            return await call_next(request)

        db = await get_db()
        col = db.idempotency_requests

        raw_body = await request.body()
        # Re-inject cached body so downstream parsers (e.g. OAuth2 form parsing)
        # can consume it normally after middleware inspection.
        async def _receive():
            return {"type": "http.request", "body": raw_body, "more_body": False}

        request._receive = _receive  # type: ignore[attr-defined]

        content_type = (request.headers.get("Content-Type") or "").lower()
        hashable_payload = not content_type.startswith("multipart/form-data")
        body_hash = _hash_bytes(raw_body) if hashable_payload else None
        auth_hash = _hash_text(request.headers.get("Authorization", ""))
        now = datetime.utcnow()
        expires_at = now + timedelta(hours=settings.IDEMPOTENCY_TTL_HOURS)
        path = request.url.path

        doc = {
            "method": method,
            "path": path,
            "idempotency_key": key,
            "auth_hash": auth_hash,
            "request_body_hash": body_hash,
            "status": "processing",
            "created_at": now,
            "updated_at": now,
            "expires_at": expires_at,
        }

        identity_filter = {
            "method": method,
            "path": path,
            "idempotency_key": key,
            "auth_hash": auth_hash,
        }

        try:
            await col.insert_one(doc)
            owns_lock = True
        except DuplicateKeyError:
            owns_lock = False

        if not owns_lock:
            existing = await col.find_one(identity_filter)
            if not existing:
                return JSONResponse(status_code=409, content={"detail": "Idempotency conflict. Please retry."})

            if (
                existing.get("request_body_hash") is not None
                and body_hash is not None
                and existing.get("request_body_hash") != body_hash
            ):
                return JSONResponse(
                    status_code=409,
                    content={"detail": "Idempotency-Key was already used with a different request payload."},
                )

            if existing.get("status") == "completed":
                cached = existing.get("response") or {}
                status_code = int(cached.get("status_code") or 200)
                content_type = str(cached.get("content_type") or "application/json")
                body_text = cached.get("body_text")
                body_b64 = cached.get("body_b64")
                if body_b64:
                    content = base64.b64decode(body_b64.encode("ascii"))
                else:
                    content = str(body_text or "").encode("utf-8")
                return Response(content=content, status_code=status_code, media_type=content_type)

            return JSONResponse(
                status_code=409,
                content={"detail": "Request with this Idempotency-Key is already in progress. Retry shortly."},
            )

        try:
            response = await call_next(request)
        except Exception:
            await col.delete_one(identity_filter)
            raise

        if response.status_code >= 500:
            await col.delete_one(identity_filter)
            return response

        response_bytes = b""
        async for chunk in response.body_iterator:
            response_bytes += chunk

        content_type = response.headers.get("content-type", "application/json")
        cached_response = {
            "status_code": int(response.status_code),
            "content_type": content_type,
        }
        try:
            cached_response["body_text"] = response_bytes.decode("utf-8")
        except UnicodeDecodeError:
            cached_response["body_b64"] = base64.b64encode(response_bytes).decode("ascii")

        await col.update_one(
            identity_filter,
            {
                "$set": {
                    "status": "completed",
                    "updated_at": datetime.utcnow(),
                    "response": cached_response,
                }
            },
        )

        return Response(
            content=response_bytes,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.media_type,
            background=response.background,
        )
