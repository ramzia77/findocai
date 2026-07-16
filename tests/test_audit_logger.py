import json

from api.auth import AuditLogger


def test_audit_logger_writes_redacted_jsonl_line(tmp_path):
    log_path = tmp_path / "audit.jsonl"
    logger = AuditLogger(path=str(log_path))

    logger.log_query(
        request_id="r1",
        api_key_id="abcd",
        endpoint="/query",
        question="What is the SSN 523-11-8890?",
        retrieved_chunk_ids=["c1"],
        answer="answer text",
        timestamp="2026-01-01T00:00:00+00:00",
        doc_type=None,
        latency_ms=1.0,
        status_code=200,
    )

    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1

    record = json.loads(lines[0])
    assert record["request_id"] == "r1"
    assert record["retrieved_chunk_ids"] == ["c1"]
    assert "523-11-8890" not in record["question"]
    assert "[REDACTED:SSN]" in record["question"]


def test_audit_logger_appends_multiple_lines(tmp_path):
    log_path = tmp_path / "audit.jsonl"
    logger = AuditLogger(path=str(log_path))

    for i in range(3):
        logger.log_query(
            request_id=f"r{i}",
            api_key_id="abcd",
            endpoint="/query",
            question=f"question {i}",
            retrieved_chunk_ids=[],
            answer="ok",
            timestamp="2026-01-01T00:00:00+00:00",
            doc_type=None,
            latency_ms=1.0,
            status_code=200,
        )

    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3
