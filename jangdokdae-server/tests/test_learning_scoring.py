from evaluation.learning.scoring import select_daily_v4


def _row(
    issue_id: int,
    *,
    scope: str = "회사",
    frame: str = "EARNINGS",
    sectors: list[int] | None = None,
) -> dict:
    return {
        "issue_id": issue_id,
        "run_date": "2026-07-28",
        "stable_id": issue_id,
        "scope": scope,
        "frame": frame,
        "sector_ids": sectors or [],
        "size": 5,
        "source_count": 3,
    }


def _judgment(
    *,
    focus: int,
    context: int,
    discovery: int,
    explains_why: bool = True,
    topic_overlap: bool = False,
    has_new_development: bool = True,
) -> dict:
    return {
        "learn_value": 8,
        "focus_fit": focus,
        "context_fit": context,
        "discovery_fit": discovery,
        "explains_why": explains_why,
        "topic_overlap": topic_overlap,
        "has_new_development": has_new_development,
    }


def test_v4_excludes_topic_repeat_without_new_development():
    rows = [
        _row(1, scope="시장 전체", frame="TREND", sectors=[1]),
        _row(2, sectors=[2]),
        _row(3, sectors=[3]),
        _row(4, sectors=[4]),
    ]
    judgments = {
        1: _judgment(
            focus=10,
            context=10,
            discovery=7,
            topic_overlap=True,
            has_new_development=False,
        ),
        2: _judgment(focus=9, context=3, discovery=5),
        3: _judgment(focus=5, context=9, discovery=6),
        4: _judgment(focus=4, context=2, discovery=9),
    }

    selected = select_daily_v4(
        rows,
        "2026-07-28",
        prev_selected=[],
        similarity=None,
        judgments=judgments,
    )

    assert 1 not in {row["issue_id"] for _, row in selected}


def test_v4_keeps_same_topic_when_there_is_a_new_development():
    rows = [
        _row(1, scope="시장 전체", frame="TREND", sectors=[1]),
        _row(2, sectors=[2]),
        _row(3, sectors=[3]),
    ]
    judgments = {
        1: _judgment(
            focus=4,
            context=10,
            discovery=4,
            topic_overlap=True,
            has_new_development=True,
        ),
        2: _judgment(focus=10, context=3, discovery=5),
        3: _judgment(focus=4, context=2, discovery=10),
    }

    selected = select_daily_v4(
        rows,
        "2026-07-28",
        prev_selected=[],
        similarity=None,
        judgments=judgments,
    )

    assert {row["issue_id"] for _, row in selected} == {1, 2, 3}


def test_v4_discovery_requires_explicit_why_and_uses_next_candidate():
    rows = [
        _row(1, scope="시장 전체", frame="TREND", sectors=[1]),
        _row(2, sectors=[2]),
        _row(3, sectors=[3]),
        _row(4, sectors=[4]),
    ]
    judgments = {
        1: _judgment(focus=3, context=10, discovery=3),
        2: _judgment(focus=10, context=2, discovery=4),
        3: _judgment(
            focus=2,
            context=2,
            discovery=10,
            explains_why=False,
        ),
        4: _judgment(focus=2, context=2, discovery=8),
    }

    selected = select_daily_v4(
        rows,
        "2026-07-28",
        prev_selected=[],
        similarity=None,
        judgments=judgments,
    )

    assert dict((role, row["issue_id"]) for role, row in selected)["discovery"] == 4


def test_v4_returns_fewer_than_three_when_no_discovery_is_qualified():
    rows = [
        _row(1, scope="시장 전체", frame="TREND", sectors=[1]),
        _row(2, sectors=[2]),
        _row(3, sectors=[3]),
    ]
    judgments = {
        1: _judgment(focus=3, context=10, discovery=3, explains_why=False),
        2: _judgment(focus=10, context=2, discovery=4, explains_why=False),
        3: _judgment(focus=2, context=2, discovery=10, explains_why=False),
    }

    selected = select_daily_v4(
        rows,
        "2026-07-28",
        prev_selected=[],
        similarity=None,
        judgments=judgments,
    )

    assert [role for role, _ in selected] == ["context", "focus"]


def test_v4_does_not_fill_today_with_older_candidates():
    rows = [
        _row(1, scope="시장 전체", frame="TREND", sectors=[1]),
        {**_row(2, sectors=[2]), "run_date": "2026-07-27"},
        {**_row(3, sectors=[3]), "run_date": "2026-07-27"},
    ]
    judgments = {
        1: _judgment(focus=8, context=10, discovery=7),
        2: _judgment(focus=10, context=2, discovery=9),
        3: _judgment(focus=9, context=3, discovery=10),
    }

    selected = select_daily_v4(
        rows,
        "2026-07-28",
        prev_selected=[],
        similarity=None,
        judgments=judgments,
    )

    assert [row["issue_id"] for _, row in selected] == [1]
