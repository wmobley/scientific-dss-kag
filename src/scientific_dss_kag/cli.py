import argparse
import json
from .evaluation import evaluate
from .retrieval import Retriever


def main():
    parser = argparse.ArgumentParser(description="Run reproducible synthetic retrieval benchmarks")
    parser.add_argument("command", choices=["benchmark", "openai-smoke"])
    parser.add_argument("--k", type=int, choices=range(1,21), default=3)
    args = parser.parse_args()
    if args.command == "benchmark":
        print(json.dumps(evaluate(Retriever(), args.k), indent=2))
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
