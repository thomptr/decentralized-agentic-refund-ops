"""Integration-test conftest for observability: tests require a running LangFuse instance."""

import os

import pytest


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    langfuse_host = os.environ.get("LANGFUSE_HOST", "")
    public_key = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
    secret_key = os.environ.get("LANGFUSE_SECRET_KEY", "")
    if not (langfuse_host and public_key and secret_key):
        skip = pytest.mark.skip(
            reason="LANGFUSE_HOST/PUBLIC_KEY/SECRET_KEY not set — "
            "skipping observability integration tests"
        )
        for item in items:
            if "observability" in str(item.fspath):
                item.add_marker(skip)
