from __future__ import annotations

from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel

from ingestion.cleaner import PIIRedactor, get_redactor
from ingestion.metadata import DocType, SourceRef
from vectorstore.index import ScoredChunk
from vectorstore.retriever import Retriever

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


def _load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


# --- provider-agnostic LLM boundary ---------------------------------------


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str


class ToolCallResult(BaseModel):
    name: str
    arguments: dict


class LLMClient(Protocol):
    def chat(self, messages: list[ChatMessage], temperature: float = 0.0) -> str: ...
    def chat_with_tools(
        self, messages: list[ChatMessage], tools: list[dict], tool_choice: dict | None = None
    ) -> ToolCallResult: ...


def _to_openai_messages(messages: list[ChatMessage]) -> list[dict]:
    return [{"role": m.role, "content": m.content} for m in messages]


class OpenAIClient:
    def __init__(self, model: str, api_key: str | None = None):
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key)
        self._model = model

    def chat(self, messages: list[ChatMessage], temperature: float = 0.0) -> str:
        response = self._client.chat.completions.create(
            model=self._model, messages=_to_openai_messages(messages), temperature=temperature
        )
        return response.choices[0].message.content or ""

    def chat_with_tools(
        self, messages: list[ChatMessage], tools: list[dict], tool_choice: dict | None = None
    ) -> ToolCallResult:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=_to_openai_messages(messages),
            tools=tools,
            tool_choice=tool_choice or "required",
        )
        tool_call = response.choices[0].message.tool_calls[0]
        import json

        return ToolCallResult(name=tool_call.function.name, arguments=json.loads(tool_call.function.arguments))


class AzureOpenAIClient:
    def __init__(self, deployment: str, endpoint: str, api_key: str, api_version: str):
        from openai import AzureOpenAI

        self._client = AzureOpenAI(azure_endpoint=endpoint, api_key=api_key, api_version=api_version)
        self._deployment = deployment

    def chat(self, messages: list[ChatMessage], temperature: float = 0.0) -> str:
        response = self._client.chat.completions.create(
            model=self._deployment, messages=_to_openai_messages(messages), temperature=temperature
        )
        return response.choices[0].message.content or ""

    def chat_with_tools(
        self, messages: list[ChatMessage], tools: list[dict], tool_choice: dict | None = None
    ) -> ToolCallResult:
        response = self._client.chat.completions.create(
            model=self._deployment,
            messages=_to_openai_messages(messages),
            tools=tools,
            tool_choice=tool_choice or "required",
        )
        tool_call = response.choices[0].message.tool_calls[0]
        import json

        return ToolCallResult(name=tool_call.function.name, arguments=json.loads(tool_call.function.arguments))


class OllamaClient:
    """Local, free chat/tool-calling via a running Ollama server (`ollama
    serve`, with a tool-calling-capable model already pulled, e.g.
    `ollama pull llama3.1:8b`). Uses Ollama's OpenAI-compatible /api/chat
    endpoint over plain HTTP -- no API key, no additional dependency beyond
    `requests` (already required).

    Unlike OpenAI, Ollama has no way to *force* a tool call -- it decides
    whether to call a tool based on the model's own judgment given the
    `tools` list, so `tool_choice` is accepted for interface compatibility
    but not enforced. If the model doesn't call a tool, chat_with_tools
    raises a clear error rather than silently returning nothing."""

    def __init__(self, model: str, base_url: str = "http://localhost:11434"):
        self._model = model
        self._base_url = base_url.rstrip("/")

    def _post(self, payload: dict) -> dict:
        import requests

        response = requests.post(f"{self._base_url}/api/chat", json=payload, timeout=120)
        response.raise_for_status()
        return response.json()

    def chat(self, messages: list[ChatMessage], temperature: float = 0.0) -> str:
        result = self._post(
            {
                "model": self._model,
                "messages": _to_openai_messages(messages),
                "stream": False,
                "options": {"temperature": temperature},
            }
        )
        return result["message"]["content"] or ""

    def chat_with_tools(
        self, messages: list[ChatMessage], tools: list[dict], tool_choice: dict | None = None
    ) -> ToolCallResult:
        result = self._post(
            {
                "model": self._model,
                "messages": _to_openai_messages(messages),
                "tools": tools,
                "stream": False,
            }
        )
        tool_calls = result["message"].get("tool_calls") or []
        if not tool_calls:
            raise RuntimeError(
                f"Ollama model {self._model!r} did not return a tool call for this "
                "prompt -- it may not support function calling, or declined to use it."
            )
        call = tool_calls[0]["function"]
        arguments = call["arguments"]
        if isinstance(arguments, str):
            import json

            arguments = json.loads(arguments)
        return ToolCallResult(name=call["name"], arguments=arguments)


class FakeLLMClient:
    """Canned-response client for offline tests and dry-run mode. `chat`
    returns a fixed answer citing the first two chunks it was given context
    on; `chat_with_tools` echoes back a minimal, schema-shaped stub so
    extraction tests can exercise validation without a real model."""

    def __init__(self, canned_answer: str | None = None, canned_tool_args: dict | None = None):
        self.canned_answer = canned_answer
        self.canned_tool_args = canned_tool_args or {}
        self.last_messages: list[ChatMessage] = []

    def chat(self, messages: list[ChatMessage], temperature: float = 0.0) -> str:
        self.last_messages = messages
        if self.canned_answer is not None:
            return self.canned_answer
        return "I could not find this in the provided documents."

    def chat_with_tools(
        self, messages: list[ChatMessage], tools: list[dict], tool_choice: dict | None = None
    ) -> ToolCallResult:
        self.last_messages = messages
        tool_name = tools[0]["function"]["name"] if tools else "extract"
        return ToolCallResult(name=tool_name, arguments=self.canned_tool_args)


def get_llm_client(settings) -> LLMClient:
    provider = settings.llm.provider
    if provider == "fake" or not settings.has_llm_credentials:
        return FakeLLMClient()
    if provider == "openai":
        return OpenAIClient(model=settings.llm.model, api_key=settings.openai_api_key)
    if provider == "azure_openai":
        return AzureOpenAIClient(
            deployment=settings.llm.azure.deployment,
            endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            api_version=settings.llm.azure.api_version,
        )
    if provider == "ollama":
        return OllamaClient(model=settings.llm.model, base_url=settings.llm.ollama.base_url)
    raise ValueError(f"Unsupported LLM provider: {provider!r}")


# --- RAG chain -------------------------------------------------------------


class Citation(BaseModel):
    source: SourceRef
    snippet: str


class RAGAnswer(BaseModel):
    answer: str
    citations: list[Citation]
    query: str


class RAGChain:
    def __init__(self, retriever: Retriever, llm_client: LLMClient, redactor: PIIRedactor | None = None):
        self.retriever = retriever
        self.llm_client = llm_client
        self.redactor = redactor or get_redactor()
        self._system_prompt = _load_prompt("rag_system.txt")

    def answer(self, question: str, doc_type: DocType | None = None, top_k: int = 5) -> RAGAnswer:
        safe_question = self._redact_query(question)
        scored_chunks = self.retriever.retrieve(safe_question, doc_type=doc_type, top_k=top_k)

        citations = [
            Citation(source=sc.chunk.source, snippet=sc.chunk.text) for sc in scored_chunks
        ]
        messages = self._build_prompt(safe_question, scored_chunks)
        answer_text = self.llm_client.chat(messages)

        return RAGAnswer(answer=answer_text, citations=citations, query=safe_question)

    def _redact_query(self, question: str) -> str:
        redacted, _ = self.redactor.redact(question)
        return redacted

    def _build_prompt(self, question: str, chunks: list[ScoredChunk]) -> list[ChatMessage]:
        context_lines = []
        for i, sc in enumerate(chunks, start=1):
            source = sc.chunk.source
            location = f"{source.filename} p.{source.page_number}"
            if source.section:
                location += f" ({source.section})"
            context_lines.append(f"[{i}] ({location})\n{sc.chunk.text}")

        context_block = "\n\n".join(context_lines) if context_lines else "(no relevant context found)"
        user_content = f"Context:\n{context_block}\n\nQuestion: {question}"

        return [
            ChatMessage(role="system", content=self._system_prompt),
            ChatMessage(role="user", content=user_content),
        ]
