from services.analyzer.bok_dictionary import build_aliases, normalize_term


def test_build_aliases_includes_korean_name_and_abbreviation():
    assert build_aliases("가계부실위험지수(HDRI)") == [
        "가계부실위험지수(HDRI)",
        "가계부실위험지수",
        "HDRI",
    ]


def test_build_aliases_splits_slash_term_without_duplicates():
    assert build_aliases("간접금융/직접금융") == [
        "간접금융/직접금융",
        "간접금융",
        "직접금융",
    ]


def test_normalize_term_joins_pdf_parenthesis_fragments():
    assert normalize_term("G20( Group of 20 )") == "G20(Group of 20)"
