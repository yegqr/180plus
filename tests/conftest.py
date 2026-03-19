"""
Shared pytest fixtures and configuration.
"""

import pytest


# ---------------------------------------------------------------------------
# Fixtures: standard question payloads
# ---------------------------------------------------------------------------

@pytest.fixture
def choice_answer() -> dict:
    return {"answer": "А", "options": 5}


@pytest.fixture
def short_answer() -> dict:
    return {"answer": "4.5"}


@pytest.fixture
def match_answer() -> dict:
    return {"pairs": {"1": "А", "2": "Б", "3": "В"}}
