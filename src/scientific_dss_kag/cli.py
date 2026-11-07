import argparse
import json
from .domain import DEFAULT_DOMAIN, domain_name
from .evaluation import evaluate
from .retrieval import Retriever


def main():
    parser = argparse.ArgumentParser(description="Run reproducible synthetic retrieval benchmarks and LLM tooling")
    parser.add_argument("command", choices=["benchmark", "openai-smoke", "gateway", "policy-check", "catalog-verify", "vector-migrate", "vector-index", "vector-status", "compare-backends"])
    parser.add_argument("--k", type=int, choices=range(1,21), default=3)
    parser.add_argument("--port", type=int, default=8092, help="gateway port (always binds 127.0.0.1)")
    parser.add_argument("--domain", default=None, help="domain under domains/ (default: DSS_DOMAIN or vector-borne-disease)")
    parser.add_argument("--root", default=".", help="repository root for policy-check")
    args = parser.parse_args()
    if args.command == "benchmark":
        print(json.dumps(evaluate(Retriever(domain=args.domain or DEFAULT_DOMAIN), args.k), indent=2))
    elif args.command == "policy-check":
        from .policy import check_policy
        result = check_policy(args.root)
        print(json.dumps(result, indent=2))
        raise SystemExit(0 if result["ok"] else 1)
    elif args.command == "catalog-verify":
        import httpx
        from .connectors import CatalogClient
        from .crosswalk import aligned, validate_crosswalk
        from .domain import load
        from .settings import catalog_url_from_env
        try:
            url, domain = catalog_url_from_env(), domain_name(args.domain)
        except ValueError as exc:
            parser.exit(1, f"catalog-verify configuration error: {exc}\n")
        client = CatalogClient(url)  # anonymous, GET-only
        try:
            index = {kind: client.list_all(kind)["normalized"] for kind in ("standardvariables", "models")}
        except (httpx.HTTPError, ValueError) as exc:
            parser.exit(1, f"catalog read failed: {type(exc).__name__}\n")
        finally:
            client.close()
        crosswalk = load(domain, "crosswalk.json")
        report = validate_crosswalk(crosswalk, index, load(domain, "catalog.json"))
        print(json.dumps({"domain": domain, "catalog_host": url.split("/")[2],
                          "live_counts": {k: len(v) for k, v in index.items()},
                          "validation": report, "aligned_after_human_review": aligned(crosswalk),
                          "note": "A passing check proves IDs, labels and SVO links exist in the live catalog, not scientific applicability."}, indent=2))
        raise SystemExit(0 if report["ok"] else 1)
    elif args.command in ("vector-migrate", "vector-index", "vector-status", "compare-backends"):
        from dotenv import load_dotenv
        from .vector_store import VectorSettings, VectorStore, build_index
        load_dotenv(".env.openspg", override=False)  # local, git-ignored secrets (POSTGRES_PASSWORD)
        try:
            store = VectorStore(VectorSettings.from_env())
            domain = domain_name(args.domain)
            if args.command == "vector-migrate":
                print(json.dumps({"applied": store.migrate()}))
            elif args.command == "vector-status":
                print(json.dumps({"domain": domain, "indexes": store.status(domain)}, indent=2))
            else:  # these spend model calls: one batched call for the index, len(cases) + 1 for the comparison
                from .openai_provider import OpenAIProvider, ProviderError
                from .settings import OpenAISettings
                provider = OpenAIProvider(OpenAISettings.from_env())
                retriever = Retriever(domain=domain)
                try:
                    with provider.operation():
                        if args.command == "vector-index":
                            print(json.dumps(build_index(provider, store, retriever), indent=2))
                        else:
                            from .evaluation import compare_backends
                            print(json.dumps(compare_backends(retriever, provider, store, args.k), indent=2))
                except ProviderError as exc:
                    parser.exit(1, f"{exc.code}: {exc}\n")
                finally:
                    provider.close()
        except ValueError as exc:
            parser.exit(1, f"vector store configuration error: {exc}\n")
        except Exception as exc:  # database errors must not print connection details
            if exc.__class__.__module__.startswith("psycopg") or exc.__class__.__name__ == "StaleIndex":
                parser.exit(1, f"vector store error: {exc.__class__.__name__}: {str(exc).splitlines()[0][:160] if exc.__class__.__name__ == 'StaleIndex' else 'is it running and migrated? (docs/setup.md)'}\n")
            raise
    elif args.command == "gateway":
        import uvicorn
        from .gateway import create_gateway_app
        from .settings import GatewaySettings
        try:
            settings = GatewaySettings.from_env()
        except ValueError as exc:
            parser.exit(1, f"gateway configuration error: {exc}\n")
        uvicorn.run(create_gateway_app(settings), host="127.0.0.1", port=args.port, log_level="warning")
    else:
        from .models import RetrievalRequest
        from .openai_provider import OpenAIProvider, ProviderError
        from .settings import OpenAISettings
        provider = OpenAIProvider(OpenAISettings.from_env())
        try:
            with provider.operation():
                request = RetrievalRequest(query="What limitations affect MaxEnt habitat suitability interpretation?", mode="ontology", context=["ScientificMethod"], backend="openai", k=2)
                retrieval = Retriever().retrieve(request, provider)
                answer = provider.answer(request.query, retrieval)
                print(json.dumps({"provider": provider.status(), "answer": answer,
                                  "retrieval_method": retrieval["method"], "embedding_usage": retrieval["embedding_usage"]}, indent=2))
        except ProviderError as exc:
            parser.exit(1, f"{exc.code}: {exc}\n")
        finally:
            provider.close()


if __name__ == "__main__":
    main()
