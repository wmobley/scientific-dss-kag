import secrets
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse
from importlib.resources import files
from . import __version__
from .connectors import fixture_catalog, integration_status
from .domain import domain_name, load
from .evaluation import evaluate
from .models import Backend, EvaluationRequest, Pathway, RetrievalRequest
from .openai_provider import OpenAIProvider, ProviderError
from .settings import OpenAISettings
from .retrieval import IntegrationUnavailable, Retriever
from .validation import validate_pathway


def require_local_origin(request: Request):
    host = request.url.hostname
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise HTTPException(403, "OpenAI operations require a trusted localhost Host.")
    origin = request.headers.get("origin")
    if origin and origin != f"{request.url.scheme}://{request.url.netloc}":
        raise HTTPException(403, "OpenAI operations require the same origin.")
    if request.headers.get("sec-fetch-site") in {"cross-site", "same-site"}:
        raise HTTPException(403, "Cross-origin OpenAI operations are forbidden.")
    # CLI requests may omit Origin, but must still use localhost and typed JSON.


def create_app(settings=None, provider=None, domain=None):
    domain = domain_name(domain)
    provider = provider or OpenAIProvider(settings or OpenAISettings.from_env())

    @asynccontextmanager
    async def lifespan(app):
        yield
        provider.close()

    app = FastAPI(title="Scientific DSS KAG research testbed", version=__version__, docs_url=None, redoc_url=None, lifespan=lifespan)
    retriever = Retriever(domain=domain)

    @app.middleware("http")
    async def secure_headers(request, call_next):
        # No arbitrary URL fetching, RDF imports, credential-entry or execution APIs.
        length = request.headers.get("content-length")
        if length and (not length.isdigit() or int(length) > 65536):
            return HTMLResponse("Request too large", status_code=413)
        chunks = []
        total = 0
        async for chunk in request.stream():
            total += len(chunk)
            if total > 65536:
                return HTMLResponse("Request too large", status_code=413)
            chunks.append(chunk)
        request._body = b"".join(chunks)
        request.state.docs_nonce = secrets.token_urlsafe(24)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        if request.url.path == "/docs":
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self' https://cdn.jsdelivr.net 'nonce-"
                + request.state.docs_nonce + "'; style-src 'self' https://cdn.jsdelivr.net; "
                "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"
            )
        return response

    @app.get("/docs", response_class=HTMLResponse, include_in_schema=False)
    def docs(request: Request):
        html = get_swagger_ui_html(openapi_url="/openapi.json", title="Scientific DSS API",
                                  swagger_favicon_url="/favicon.ico")
        return HTMLResponse(html.body.decode().replace("<script>", '<script nonce="' + request.state.docs_nonce + '">'))

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def workbench():
        return files("scientific_dss_kag").joinpath("static/index.html").read_text()

    @app.get("/workbench.js", include_in_schema=False)
    def javascript():
        from fastapi.responses import Response
        return Response(files("scientific_dss_kag").joinpath("static/workbench.js").read_text(), media_type="application/javascript")

    @app.get("/workbench.css", include_in_schema=False)
    def stylesheet():
        from fastapi.responses import Response
        return Response(files("scientific_dss_kag").joinpath("static/workbench.css").read_text(), media_type="text/css")

    @app.get("/health")
    def health():
        return {"status": "ok", "version": __version__, "mode": "offline_synthetic", "domain": domain, "corpus_hash": retriever.corpus_hash}

    @app.get("/integrations")
    def integrations():
        return {**integration_status(), "openai": provider.status()}

    @app.get("/catalog/models")
    def models():
        return {"origin": "synthetic_fixture", "live_verified": False, "records": fixture_catalog(domain)["models"]}

    @app.get("/catalog/variables")
    def variables():
        return {"origin": "synthetic_alignment_fixture", "live_verified": False, "records": fixture_catalog(domain)["variables"]}

    @app.get("/catalog/crosswalk")
    def crosswalk():
        return {"domain": domain, "review_required": True, **load(domain, "crosswalk.json")}

    @app.post("/retrieve")
    def retrieve(request: RetrievalRequest, http_request: Request):
        try:
            if request.backend == Backend.openai:
                require_local_origin(http_request)
                with provider.operation():
                    return retriever.retrieve(request, provider)
            return retriever.retrieve(request)
        except ProviderError as exc:
            raise HTTPException(exc.status, {"code": exc.code, "message": str(exc)}) from None
        except IntegrationUnavailable as exc:
            raise HTTPException(503, {"code": "integration_unavailable", "message": str(exc)}) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.post("/answer")
    def answer(request: RetrievalRequest, http_request: Request):
        require_local_origin(http_request)
        try:
            with provider.operation():
                retrieval = retriever.retrieve(request, provider)
                result = provider.answer(request.query, retrieval)
                return {**result, "retrieval": retrieval}
        except ProviderError as exc:
            raise HTTPException(exc.status, {"code": exc.code, "message": str(exc)}) from None
        except IntegrationUnavailable as exc:
            raise HTTPException(503, {"code": "integration_unavailable", "message": str(exc)}) from None
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None

    @app.post("/validate/pathway")
    def validate(pathway: Pathway):
        return validate_pathway(pathway, retriever)

    @app.post("/evaluate")
    def benchmark(request: EvaluationRequest):
        return evaluate(retriever, request.k)

    return app


app = create_app()
