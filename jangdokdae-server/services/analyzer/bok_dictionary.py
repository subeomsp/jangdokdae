"""한국은행 「경제금융용어 800선」 PDF 파서.

PDF에서 제목, 본문, 연관검색어에 서로 다른 글꼴이 사용되는 점을 이용한다. 원문은
화면용 요약과 분리해 저장하므로 여기서는 문장을 고치거나 요약하지 않는다.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from pypdf import PdfReader

BOK_SOURCE_CODE = "bok_800"
BOK_SOURCE_TITLE = "한국은행 경제금융용어 800선"
BOK_SOURCE_VERSION = "2024"
BOK_SOURCE_URL = (
    "https://www.bok.or.kr/portal/bbs/B0000249/view.do"
    "?depth=200765&menuNo=200765&nttId=10096081&oldMenuNo=201150"
    "&programType=newsData&relate=Y"
)
BOK_PDF_URL = (
    "https://www.bok.or.kr/fileSrc/portal/"
    "5cbf35f51f3842dd9ed1fba7cef5199a/1/"
    "74ac2f04b15c4debac64fd6931aea9fd.pdf"
)

# PDF 앞표지와 목차 다음의 책 1쪽이 PDF 뷰어 19쪽이다.
CONTENT_START_PDF_PAGE = 19
CONTENT_END_PDF_PAGE = 423


@dataclass(frozen=True)
class BokDictionaryEntry:
    term: str
    aliases: list[str]
    raw_definition: str
    related_terms: list[str]
    source_page: int
    pdf_page: int
    content_hash: str


@dataclass
class _EntryBuffer:
    term: str
    definition_parts: list[str]
    related_parts: list[str]
    pdf_page: int


def normalize_term(term: str) -> str:
    """PDF 조각에서 조립한 제목의 공백과 괄호를 정리한다."""

    normalized = re.sub(r"\s+", " ", term).strip()
    normalized = re.sub(r"\s+([),/])", r"\1", normalized)
    normalized = re.sub(r"([(,/])\s+", r"\1", normalized)
    return normalized


def build_aliases(term: str) -> list[str]:
    """본문 매칭에 사용할 안전한 별칭을 만든다."""

    candidates = [term]
    depth = 0
    start = 0
    slash_parts: list[str] = []
    for index, character in enumerate(term):
        if character == "(":
            depth += 1
        elif character == ")":
            depth = max(0, depth - 1)
        elif character == "/" and depth == 0:
            slash_parts.append(term[start:index])
            start = index + 1
    if slash_parts:
        slash_parts.append(term[start:])
        candidates.extend(part.strip() for part in slash_parts)

    parenthetical = re.fullmatch(r"(.+?)\(([^()]*)\)", term)
    if parenthetical:
        candidates.extend([parenthetical.group(1).strip(), parenthetical.group(2).strip()])

    # '가상자산공개(ICO)'처럼 본문에서 약어만 쓰이는 경우를 지원한다.
    candidates.extend(re.findall(r"\(([A-Za-z][A-Za-z0-9+\-. ]{1,30})\)", term))

    aliases: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        alias = normalize_term(candidate)
        key = alias.casefold()
        if alias and key not in seen:
            seen.add(key)
            aliases.append(alias)
    return aliases


def _font_name(font: dict[str, Any] | None) -> str:
    return str(font.get("/BaseFont", "")) if font else ""


def _is_heading_font(font_name: str) -> bool:
    return "SUIT-ExtraBold" in font_name or "DIN-Bold" in font_name


def _append_heading_fragment(parts: list[str], fragment: str) -> None:
    text = fragment.replace("\n", "").strip()
    if not text:
        return
    if not parts:
        parts.append(text)
        return

    previous = parts[-1]
    needs_space = (
        previous[-1:].isascii()
        and previous[-1:].isalnum()
        and text[:1].isascii()
        and text[:1].isalnum()
        and not text.endswith("(")
    )
    parts.append((" " if needs_space else "") + text)


def _clean_definition(parts: list[str]) -> str:
    text = "".join(part.replace("\n", "") for part in parts)
    text = text.replace("I 경제금융용어  800선", "").replace("I 경제금융용어 800선", "")
    return re.sub(r"\s+", " ", text).strip()


def _clean_related_terms(parts: list[str]) -> list[str]:
    text = re.sub(r"\s+", " ", "".join(parts)).strip()
    text = text.replace("I 경제금융용어 800선", "")
    terms = [normalize_term(term) for term in re.split(r"[,，]", text)]
    return [term for term in terms if term and "경제금융용어 800선" not in term]


def _finish_entry(buffer: _EntryBuffer | None) -> BokDictionaryEntry | None:
    if buffer is None:
        return None
    definition = _clean_definition(buffer.definition_parts)
    term = normalize_term(buffer.term)
    if not term or not definition:
        return None
    digest = hashlib.sha256(f"{term}\n{definition}".encode()).hexdigest()
    return BokDictionaryEntry(
        term=term,
        aliases=build_aliases(term),
        raw_definition=definition,
        related_terms=_clean_related_terms(buffer.related_parts),
        source_page=buffer.pdf_page - CONTENT_START_PDF_PAGE + 1,
        pdf_page=buffer.pdf_page,
        content_hash=digest,
    )


def parse_bok_dictionary(pdf_path: str | Path) -> list[BokDictionaryEntry]:
    """공식 PDF를 원문 항목 목록으로 변환한다."""

    reader = PdfReader(str(pdf_path))
    entries: list[BokDictionaryEntry] = []
    current: _EntryBuffer | None = None
    heading_parts: list[str] = []
    related_mode = False

    for pdf_page in range(CONTENT_START_PDF_PAGE, CONTENT_END_PDF_PAGE + 1):
        page = reader.pages[pdf_page - 1]

        def visit(
            text: str,
            _cm: list[float],
            _tm: list[float],
            font: dict[str, Any] | None,
            _font_size: float,
        ) -> None:
            nonlocal current, heading_parts, related_mode
            font_name = _font_name(font)
            stripped = text.strip()
            if not stripped:
                return

            if _is_heading_font(font_name):
                _append_heading_fragment(heading_parts, text)
                return

            if "KoPubBatangLight" in font_name:
                if heading_parts:
                    finished = _finish_entry(current)
                    if finished is not None:
                        entries.append(finished)
                    current = _EntryBuffer(
                        term="".join(heading_parts),
                        definition_parts=[],
                        related_parts=[],
                        pdf_page=pdf_page,
                    )
                    heading_parts = []
                    related_mode = False
                if current is not None and "경제금융용어 800선" not in stripped:
                    current.definition_parts.append(text)
                return

            if "KoPubDotumBold" in font_name and "연관검색어" in stripped:
                related_mode = True
                return

            if "KoPubDotumMedium" in font_name and related_mode and current is not None:
                current.related_parts.append(stripped)
                return

            if "KoPubDotumLight" in font_name and current is not None and not related_mode:
                current.definition_parts.append(text)

        page.extract_text(visitor_text=visit)

    finished = _finish_entry(current)
    if finished is not None:
        entries.append(finished)
    validate_entries(entries)
    return entries


def validate_entries(entries: list[BokDictionaryEntry]) -> None:
    """PDF 구조 변경이나 잘못된 파일을 조용히 DB에 넣지 않도록 차단한다."""

    if not 750 <= len(entries) <= 820:
        raise ValueError(f"expected 750-820 dictionary entries, parsed {len(entries)}")
    terms = [entry.term for entry in entries]
    if len(terms) != len(set(terms)):
        duplicates = sorted({term for term in terms if terms.count(term) > 1})
        raise ValueError(f"duplicate dictionary terms: {duplicates[:10]}")
    if any(len(entry.raw_definition) < 10 for entry in entries):
        raise ValueError("one or more dictionary definitions are unexpectedly short")


def download_bok_pdf(destination: str | Path) -> Path:
    """공식 한국은행 URL에서 PDF를 내려받는다."""

    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    with httpx.stream("GET", BOK_PDF_URL, follow_redirects=True, timeout=60) as response:
        response.raise_for_status()
        with path.open("wb") as output:
            for chunk in response.iter_bytes():
                output.write(chunk)
    return path
