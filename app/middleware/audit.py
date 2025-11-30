import time

from jose import JWTError
from jose import jwt as jose_jwt
from orso.logging import get_logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = get_logger()


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.time()
        try:
            response: Response = await call_next(request)
            status = response.status_code
            message = "okay"
        except Exception as exc:
            # Use exception detail if available (e.g. HTTPException.detail)
            message = getattr(exc, "detail", str(exc))
            if hasattr(exc, "status_code"):
                status = exc.status_code
                response = Response(status_code=status)
            else:
                status = 500
                response = Response(status_code=status)
        finally:
            duration_ms = int((time.time() - start) * 1000)
            # Avoid logging sensitive headers
            xff = request.headers.get("x-forwarded-for", "-")
            payload = {
                "method": request.method,
                "path": request.url.path,
                "status": status,
                "duration_ms": duration_ms,
                "from": xff,
                "timestamp": int(time.time()),
                "message": message,
            }
            # If a bearer token is present, extract the 'sub' (identity) claim
            # via unverified claims and include it in the audit payload. We do not
            # attempt to verify the token here (audit should not require key fetch).
            auth = request.headers.get("authorization")
            if auth and auth.lower().startswith("bearer "):
                try:
                    token = auth.split(" ", 1)[1]
                    claims = jose_jwt.get_unverified_claims(token)
                    sub = claims.get("sub") if isinstance(claims, dict) else None
                    if sub:
                        payload["jwt_sub"] = sub
                        payload["jwt_present"] = True
                    else:
                        payload["jwt_present"] = True
                except JWTError:
                    # best-effort: ignore any parsing errors
                    payload["jwt_present"] = True

            print(payload)
            # Prefer a structured audit call; fall back to info if not available
            # Inspect the response body: if the response is JSON and contains an
            # `audit` object, include that in the audit payload so the logger
            # has access to structured response metadata.
            try:
                content_type = response.headers.get("content-type", "")
                body_bytes = None
                if "application/json" in content_type:
                    # Some responses expose `body` attribute
                    if hasattr(response, "body") and response.body is not None:
                        body_bytes = response.body
                    # Some responses are streaming and expose a body_iterator;
                    # consume and replace the iterator with a rebuilt response.
                    elif hasattr(response, "body_iterator"):
                        chunks = [c async for c in response.body_iterator]
                        body_bytes = b"".join(chunks)
                        response = Response(
                            content=body_bytes,
                            status_code=response.status_code,
                            headers=dict(response.headers),
                            media_type=response.media_type,
                        )

                if body_bytes:
                    try:
                        import orjson as _orjson  # local import to keep deps explicit

                        parsed = _orjson.loads(body_bytes)
                        if isinstance(parsed, dict) and "audit" in parsed:
                            payload["response_audit"] = parsed["audit"]
                    except (TypeError, ValueError):
                        # best-effort: do not crash auditing if parsing fails
                        pass
            except (AttributeError, RuntimeError, TypeError):
                # best-effort: no-op if we cannot inspect response body
                pass
            try:
                logger.audit(payload)
            except AttributeError as exc_attr:
                # Best-effort: audit method missing - log at error level
                logger.error(f"audit payload fallback: {payload} - error={exc_attr}")
        return response
