"""콘텐츠 본문과 승인된 용어 사전을 결정적으로 연결한다."""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class TermCandidate:
    name: str
    definition: str
    aliases: list[str] = field(default_factory=list)
    source_label: str | None = None
    source_title: str | None = None
    source_url: str | None = None
    source_page: int | None = None
    original_url: str | None = None
    ai_generated: bool = True
    verification_status: str = "legacy"


def _safe_automatic_alias(alias: str) -> bool:
    compact = re.sub(r"[\s()\-/]", "", alias)
    if not compact:
        return False
    if re.fullmatch(r"[A-Za-z0-9+.\-]+", compact):
        return len(compact) >= 3
    return len(compact) >= 3


def _find_alias(text: str, alias: str) -> int | None:
    if re.fullmatch(r"[A-Za-z0-9+.\- ]+", alias):
        match = re.search(
            rf"(?<![A-Za-z0-9]){re.escape(alias)}(?![A-Za-z0-9])",
            text,
            flags=re.IGNORECASE,
        )
        return match.start() if match else None
    index = text.find(alias)
    return index if index >= 0 else None


def match_terms(
    texts: list[str],
    candidates: list[TermCandidate],
    priority_names: list[str] | None = None,
    max_terms: int = 5,
) -> list[TermCandidate]:
    """본문 등장 순으로 최대 ``max_terms``개를 고른다.

    LLM이 뽑은 ``priority_names``는 짧은 용어도 허용하되 실제 본문에 있어야 한다.
    자동 탐색은 '금리' 같은 짧고 일반적인 단어의 과도한 밑줄을 막는다.
    """

    priority = {name.casefold() for name in (priority_names or [])}
    matches: list[tuple[int, int, int, TermCandidate]] = []
    cursor = 0
    for text in texts:
        for candidate in candidates:
            aliases = candidate.aliases or [candidate.name]
            best: tuple[int, int] | None = None
            is_priority = candidate.name.casefold() in priority
            for alias in sorted(set(aliases), key=len, reverse=True):
                if not is_priority and not _safe_automatic_alias(alias):
                    continue
                index = _find_alias(text, alias)
                if index is None:
                    continue
                value = (index, -len(alias))
                if best is None or value < best:
                    best = value
            if best is not None:
                matches.append(
                    (
                        cursor + best[0],
                        0 if is_priority else 1,
                        best[1],
                        candidate,
                    )
                )
        cursor += len(text) + 1

    selected: list[TermCandidate] = []
    seen: set[str] = set()
    for _, _, _, candidate in sorted(matches, key=lambda item: item[:3]):
        key = candidate.name.casefold()
        if key in seen:
            continue
        seen.add(key)
        selected.append(candidate)
        if len(selected) >= max_terms:
            break
    return selected
