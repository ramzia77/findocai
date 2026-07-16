"""Evaluate the RAG chain against evaluation/test_set.json using ragas
(faithfulness, answer_relevancy, context_precision, context_recall).

Requires real LLM + embedding credentials -- ragas uses an LLM as judge, so
this cannot run in fake/dry-run mode. Run
`python -m scripts.ingest_sample_docs` first to build a real-embedding index.

Usage:
    python -m evaluation.ragas_eval
"""
from __future__ import annotations

import json
from pathlib import Path

from rag.chain import RAGChain, get_llm_client
from settings import BASE_DIR, get_settings
from vectorstore.embedder import get_embedding_client
from vectorstore.index import FaissVectorStore
from vectorstore.retriever import Retriever

TEST_SET_PATH = Path(__file__).resolve().parent / "test_set.json"


def load_test_set(path: Path = TEST_SET_PATH) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_rag_chain(settings) -> RAGChain:
    embedder = get_embedding_client(settings)
    llm_client = get_llm_client(settings)
    vectorstore = FaissVectorStore(dimensions=embedder.dimensions)

    index_path = BASE_DIR / settings.vectorstore.index_path
    if not index_path.exists():
        raise FileNotFoundError(
            f"No index found at {index_path}; run `python -m scripts.ingest_sample_docs` first."
        )
    vectorstore.load(str(index_path))

    retriever = Retriever(vectorstore, embedder, top_k=settings.retrieval.top_k)
    return RAGChain(retriever, llm_client)


def run_rag_over_test_set(chain: RAGChain, test_set: list[dict]):
    from datasets import Dataset

    questions, answers, contexts, ground_truths = [], [], [], []
    for item in test_set:
        result = chain.answer(item["question"])
        questions.append(item["question"])
        answers.append(result.answer)
        contexts.append([c.snippet for c in result.citations])
        ground_truths.append(item["expected_answer_contains"])

    return Dataset.from_dict(
        {
            "question": questions,
            "answer": answers,
            "contexts": contexts,
            "ground_truth": ground_truths,
        }
    )


def evaluate(dataset):
    from ragas import evaluate as ragas_evaluate
    from ragas.metrics import answer_relevancy, context_precision, context_recall, faithfulness

    return ragas_evaluate(
        dataset, metrics=[faithfulness, answer_relevancy, context_precision, context_recall]
    )


def main() -> None:
    settings = get_settings()
    if not settings.has_llm_credentials or not settings.has_embedding_credentials:
        raise SystemExit(
            "ragas_eval requires real LLM + embedding credentials (ragas uses an LLM as "
            "judge). Set OPENAI_API_KEY (or the Azure OpenAI equivalents) in .env and re-run."
        )

    chain = build_rag_chain(settings)
    test_set = load_test_set()
    dataset = run_rag_over_test_set(chain, test_set)
    results = evaluate(dataset)
    print(results)


if __name__ == "__main__":
    main()
