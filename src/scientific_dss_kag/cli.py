import argparse
import json
from .evaluation import evaluate
from .retrieval import Retriever


def main():
    parser = argparse.ArgumentParser(description="Run reproducible synthetic retrieval benchmarks and LLM tooling")
    parser.add_argument("command", choices=["benchmark", "openai-smoke", "gateway", "policy-check"])
    parser.add_argument("--k", type=int, choices=range(1,21), default=3)
    parser.add_argument("--port", type=int, default=8092, help="gateway port (always binds 127.0.0.1)")
    parser.add_argument("--root", default=".", help="repository root for policy-check")
    args = parser.parse_args()
    if args.command == "benchmark":
        print(json.dumps(evaluate(Retriever(), args.k), indent=2))
    elif args.command == "policy-check":
        from .policy import check_policy
        result = check_policy(args.root)
        print(json.dumps(result, indent=2))
        raise SystemExit(0 if result["ok"] else 1)
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
