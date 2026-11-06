import argparse
import json
from .evaluation import evaluate
from .retrieval import Retriever


def main():
    parser = argparse.ArgumentParser(description="Run reproducible synthetic retrieval benchmarks")
    parser.add_argument("command", choices=["benchmark"])
    parser.add_argument("--k", type=int, choices=range(1,21), default=3)
    args = parser.parse_args()
    print(json.dumps(evaluate(Retriever(), args.k), indent=2))


if __name__ == "__main__":
    main()
