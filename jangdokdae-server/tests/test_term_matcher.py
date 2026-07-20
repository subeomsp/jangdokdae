from services.analyzer.term_matcher import TermCandidate, match_terms


def _term(name: str, aliases: list[str] | None = None) -> TermCandidate:
    return TermCandidate(
        name=name,
        definition=f"{name} 설명입니다.",
        aliases=aliases or [name],
    )


def test_match_terms_uses_alias_and_returns_content_order():
    result = match_terms(
        ["연준의 기준금리 결정 뒤 주가수익비율(PER)도 주목받았습니다."],
        [
            _term("PER", ["주가수익비율(PER)", "주가수익비율", "PER"]),
            _term("기준금리"),
        ],
    )

    assert [term.name for term in result] == ["기준금리", "PER"]


def test_match_terms_ignores_short_automatic_terms_but_keeps_priority():
    candidates = [_term("금리"), _term("기준금리")]

    automatic = match_terms(["기준금리와 시장금리를 비교합니다."], candidates)
    priority = match_terms(
        ["기준금리와 시장금리를 비교합니다."],
        candidates,
        priority_names=["금리"],
    )

    assert [term.name for term in automatic] == ["기준금리"]
    assert [term.name for term in priority] == ["기준금리", "금리"]


def test_match_terms_limits_and_deduplicates_across_paragraphs():
    candidates = [_term(f"경제용어{index}") for index in range(7)]
    texts = [
        " ".join(term.name for term in candidates[:4]),
        " ".join(term.name for term in candidates[3:]),
    ]

    result = match_terms(texts, candidates, max_terms=5)

    assert [term.name for term in result] == [f"경제용어{index}" for index in range(5)]
