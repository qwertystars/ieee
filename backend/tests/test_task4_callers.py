from __future__ import annotations

import ast
from pathlib import Path

CALLER_FILES = (
    "app/streaming/consumer.py",
    "app/ingestion/adapters/event_registry.py",
    "app/ingestion/adapters/instagram.py",
    "app/ingestion/adapters/reddit.py",
    "app/ingestion/adapters/twitter.py",
    "app/ingestion/adapters/unipile.py",
    "app/ingestion/adapters/youtube.py",
)


def test_production_idempotency_callers_bind_scope_and_payload() -> None:
    root = Path(__file__).parents[1]
    calls = []
    for relative_path in CALLER_FILES:
        tree = ast.parse((root / relative_path).read_text())
        calls.extend(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "check_and_record"
        )

    assert calls
    for call in calls:
        keyword_names = {keyword.arg for keyword in call.keywords}
        assert {"org_id", "payload"} <= keyword_names


def test_streaming_idempotency_is_joined_to_observation_commit() -> None:
    source = (Path(__file__).parents[1] / "app/streaming/consumer.py").read_text()
    tree = ast.parse(source)
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "check_and_record"
    ]

    assert len(calls) == 1
    commit_keyword = next(keyword for keyword in calls[0].keywords if keyword.arg == "commit")
    assert isinstance(commit_keyword.value, ast.Constant)
    assert commit_keyword.value.value is False
