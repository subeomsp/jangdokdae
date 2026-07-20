from types import SimpleNamespace

import pytest

from scripts.propose_dictionary_term_units import _load_targets, _save_proposal


@pytest.mark.asyncio
async def test_load_targets_rejects_requested_term_that_is_not_pending(monkeypatch):
    class Result:
        def scalars(self):
            return self

        def all(self):
            return []

    class Db:
        async def execute(self, _stmt):
            return Result()

    class SessionContext:
        async def __aenter__(self):
            return Db()

        async def __aexit__(self, *_args):
            return None

    monkeypatch.setattr(
        "scripts.propose_dictionary_term_units.AsyncSessionLocal",
        SessionContext,
    )

    with pytest.raises(ValueError, match="pending source terms not found"):
        await _load_targets(terms=["없는 항목"], limit=8, force=False)


@pytest.mark.asyncio
async def test_save_proposal_never_overwrites_approved(monkeypatch):
    row = SimpleNamespace(term_units_status="approved")

    class Db:
        async def get(self, *_args, **_kwargs):
            return row

        async def commit(self):
            raise AssertionError("approved row must not be committed")

    class SessionContext:
        async def __aenter__(self):
            return Db()

        async def __aexit__(self, *_args):
            return None

    monkeypatch.setattr(
        "scripts.propose_dictionary_term_units.AsyncSessionLocal",
        SessionContext,
    )

    saved = await _save_proposal(1, [{"term": "변경 금지"}], force=True)

    assert saved is False
    assert row.term_units_status == "approved"
