"""Localhost LLM gateway: the only process that talks to the upstream OpenAI-compatible endpoint.

It holds the upstream key, enforces one shared sliding-window rate limit and an optional call cap
for every consumer (this app and KAG), and passes through a fixed set of API routes. It never
logs request bodies or credentials and never resends a request on its own.
"""
import asyncio
from collections import deque
from contextlib import asynccontextmanager
import secrets
import time
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from .settings import GatewaySettings

ALLOWED_ROUTES = {("POST", "chat/completions"), ("POST", "embeddings"), ("POST", "responses"), ("GET", "models")}
MAX_REQUEST_BYTES = 1024 * 1024
MAX_RESPONSE_BYTES = 16 * 1024 * 1024


class LimiterTimeout(Exception):
    pass


class SlidingWindowLimiter:
    """At most `rate` admissions per `window` seconds; callers queue (bounded by max_wait)."""

    def __init__(self, rate, window, clock=time.monotonic):
        self.rate, self.window, self.clock = rate, window, clock
        self._stamps = deque()
        self._lock = asyncio.Lock()
        self.paused_until = 0.0
        self.waiting = 0

    def recent(self):
        now = self.clock()
        while self._stamps and now - self._stamps[0] >= self.window:
            self._stamps.popleft()
        return len(self._stamps)

    def pause(self, seconds):
        self.paused_until = max(self.paused_until, self.clock() + seconds)

    async def acquire(self, max_wait):
        deadline = self.clock() + max_wait
        self.waiting += 1
        try:
            while True:
                async with self._lock:
                    now = self.clock()
                    if now < self.paused_until:
                        wait = self.paused_until - now
                    elif self.recent() < self.rate:
                        self._stamps.append(now)
                        return
                    else:
                        wait = self.window - (now - self._stamps[0])
                if self.clock() + wait > deadline:
                    raise LimiterTimeout
                await asyncio.sleep(max(wait, 0.01))
        finally:
            self.waiting -= 1


def error(status, code, message, headers=None):
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status, headers=headers)


def create_gateway_app(settings: GatewaySettings, transport=None):
    limiter = SlidingWindowLimiter(settings.rate_per_minute, settings.window_seconds)
    gate = asyncio.Semaphore(settings.max_concurrency)
    stats = {"calls": 0, "last_429_age": None, "last_429": None}
    holder = {}

    def client():
        if "client" not in holder:  # created lazily inside the running loop
            holder["client"] = httpx.AsyncClient(base_url=settings.upstream + "/", timeout=120, follow_redirects=False,
                                                trust_env=False, transport=transport)
        return holder["client"]

    @asynccontextmanager
    async def lifespan(app):
        yield
        if "client" in holder:
            await holder["client"].aclose()

    app = FastAPI(title="LLM gateway", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

    def authorized(request):
        supplied = request.headers.get("authorization", "")
        return secrets.compare_digest(supplied.encode(), f"Bearer {settings.token}".encode())

    @app.get("/status")
    async def status(request: Request):
        if not authorized(request):
            return error(401, "unauthorized", "Missing or invalid gateway token.")
        paused = max(0.0, limiter.paused_until - limiter.clock())
        return {"upstream_host": settings.upstream.split("/")[2], "rate_per_minute": settings.rate_per_minute,
                "calls_last_window": limiter.recent(), "calls_total": stats["calls"], "call_cap": settings.max_calls,
                "queue_depth": limiter.waiting, "paused_seconds": round(paused, 1),
                "last_429_seconds_ago": None if stats["last_429"] is None else round(limiter.clock() - stats["last_429"], 1)}

    @app.api_route("/v1/{path:path}", methods=["GET", "POST"])
    async def proxy(path: str, request: Request):
        if not authorized(request):
            return error(401, "unauthorized", "Missing or invalid gateway token.")
        if (request.method, path) not in ALLOWED_ROUTES:
            return error(404, "route_not_allowed", "This gateway only forwards chat, embeddings, responses and models.")
        length = request.headers.get("content-length")
        if length and (not length.isdigit() or int(length) > MAX_REQUEST_BYTES):
            return error(413, "request_too_large", "Request body too large.")
        body = await request.body()
        if len(body) > MAX_REQUEST_BYTES:
            return error(413, "request_too_large", "Request body too large.")
        if settings.max_calls is not None and stats["calls"] >= settings.max_calls:
            return error(429, "gateway_call_cap", "The gateway call cap for this run is exhausted.")
        try:
            await limiter.acquire(settings.max_wait_seconds)
        except LimiterTimeout:
            return error(429, "gateway_rate_limited", "Rate limit queue wait exceeded; try again later.",
                         {"Retry-After": str(int(settings.window_seconds))})
        stats["calls"] += 1  # counts every upstream attempt, including failures
        headers = {"Authorization": f"Bearer {settings.upstream_api_key}"}
        if request.method == "POST":
            headers["Content-Type"] = "application/json"
        try:
            async with gate:
                async with client().stream(request.method, path, content=body or None, headers=headers) as response:
                    size, parts = 0, []
                    async for part in response.aiter_bytes():
                        size += len(part)
                        if size > MAX_RESPONSE_BYTES:
                            return error(502, "upstream_response_too_large", "Upstream response exceeded the size limit.")
                        parts.append(part)
                    status_code, retry_after = response.status_code, response.headers.get("retry-after", "")
        except httpx.HTTPError:
            return error(502, "upstream_unreachable", "The upstream LLM endpoint request failed.")
        if status_code == 429:
            # The endpoint is shared with other users: pause everyone, surface the error, never resend.
            seconds = min(int(retry_after), 120) if retry_after.isdigit() else 15
            limiter.pause(seconds)
            stats["last_429"] = limiter.clock()
            return error(429, "upstream_rate_limited", "The upstream endpoint is rate limited.", {"Retry-After": str(seconds)})
        if not 200 <= status_code < 300:
            return error(502, "upstream_error", f"The upstream endpoint returned HTTP {status_code}.")
        return Response(b"".join(parts), status_code=status_code, media_type="application/json")

    return app
