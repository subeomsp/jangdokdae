"""v4 일일 학습 후보의 역할·신선도·설명 깊이 판정."""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, Field, ValidationError, model_validator

JUDGE_PROMPT_VERSION = "selection-judge-v2.1"
HISTORY_DAYS = 7


class CandidateJudgmentV4(BaseModel):
    issue_id: int
    learn_value: int = Field(ge=0, le=10, description="초보자 학습 가치")
    focus_fit: int = Field(ge=0, le=10, description="핵심 역할 적합도")
    context_fit: int = Field(ge=0, le=10, description="맥락 역할 적합도")
    discovery_fit: int = Field(ge=0, le=10, description="발견 역할 적합도")
    explains_why: bool = Field(
        description="제공된 제목·훅이 원인이나 작동 구조를 명시하는지"
    )
    topic_overlap: bool = Field(description="최근 발행분과 실질적으로 같은 주제인지")
    has_new_development: bool = Field(
        description="같은 주제일 때 중심에 새 사실·결정·수치가 있는지"
    )
    matched_previous_issue_ids: list[int] = Field(
        default_factory=list,
        description="같은 주제로 판단한 최근 발행 issue_id",
    )
    reason: str = Field(description="점수·게이트 판정의 짧은 근거")

    @model_validator(mode="after")
    def validate_repetition_fields(self) -> CandidateJudgmentV4:
        if self.topic_overlap and not self.matched_previous_issue_ids:
            raise ValueError("같은 주제라면 최근 발행 issue_id가 필요합니다")
        if not self.topic_overlap and (
            self.matched_previous_issue_ids or not self.has_new_development
        ):
            raise ValueError(
                "다른 주제라면 matched_previous_issue_ids=[]와 "
                "has_new_development=true여야 합니다"
            )
        return self


class DayJudgmentV4(BaseModel):
    judgments: list[CandidateJudgmentV4]


PROMPT = """너는 주식 초보자를 위한 하루 세 가지 학습 콘텐츠의 편집장이다.
아래 [오늘 후보] 각각을 0~10점으로 평가하고, 최근 발행분 대비 반복 여부와 설명 깊이를
판정한다. 입력에 적힌 제목·훅만 근거로 쓰고, 일반 지식으로 빠진 설명을 보충해 추정하지 않는다.

역할:
- 핵심(focus): 그날 가장 중요한 구체적 사건. "오늘 하나만 읽는다면?"
- 맥락(context): 개별 사건 너머 시장 전체가 움직인 이유·상태. 제도·규제 발표는
  시장 영향이 있어도 상태가 아니라 사건이므로 맥락 점수를 낮춘다.
- 발견(discovery): 앞의 두 항목과 다른 영역에서 시장의 작동 원리를 배우는 콘텐츠.

판정 규칙:
1. learn_value는 제공된 문구에 실제로 드러난 학습 가치만 평가한다.
2. explains_why는 제목·훅 자체에 원인, 이유, 인과 또는 작동 구조가 명시돼야 true다.
   단순 실적·등락·발표 사실만 있고 "왜"가 없으면 false다.
3. topic_overlap은 최근 발행분과 사건·정책·현상이 실질적으로 같을 때 true다.
   매수 사이드카와 매도 사이드카처럼 방향만 반대인 같은 제도·현상도 같은 주제다.
   같은 산업이라는 이유만으로는 같은 주제가 아니다.
4. topic_overlap=true이면 has_new_development는 중심에 새 결정, 시행, 결과, 수치 변화,
   원인 규명처럼 독자가 새로 배울 전개가 있을 때만 true다. 표현 변경, 날짜 변경,
   등락 방향 변경, 같은 발표 반복은 새 전개가 아니다.
5. topic_overlap=false이면 has_new_development=true,
   matched_previous_issue_ids=[]로 반환한다.
6. matched_previous_issue_ids에는 [최근 발행분]에 표시된 issue_id만 넣는다.
   [오늘 후보]의 issue_id를 이 필드에 넣으면 안 된다.
7. 모든 오늘 후보를 정확히 한 번씩 반환한다.

[날짜] {date}

[최근 {history_days}일 발행분]
{previous}

[오늘 후보]
{candidates}"""


def build_editorial_llm():
    from langchain_google_vertexai import ChatVertexAI

    from app.config import settings

    return ChatVertexAI(
        model=settings.vertex_model,
        project=settings.google_cloud_project or None,
        location=settings.google_cloud_location,
        temperature=0,
        max_retries=2,
    ).with_structured_output(DayJudgmentV4)


def candidate_lines(candidates: Sequence[dict]) -> str:
    return "\n".join(
        f"- issue_id={candidate['issue_id']} | scope={candidate['scope']} | "
        f"frame={candidate['frame']} | "
        f"섹터={','.join(candidate.get('sector_names', [])) or '없음'}\n"
        f"  제목: {candidate['title']}\n"
        f"  훅: {candidate['hook']}"
        for candidate in candidates
    )


def previous_lines(previous: Sequence[dict]) -> str:
    if not previous:
        return "- 없음"
    return "\n".join(
        f"- issue_id={candidate['issue_id']} | "
        f"발행일={candidate.get('_selected_on', candidate['run_date'])}\n"
        f"  제목: {candidate['title']}\n"
        f"  훅: {candidate['hook']}"
        for candidate in previous
    )


def normalize_judgments(
    day: str,
    result: DayJudgmentV4,
    candidate_ids: list[int],
    previous_ids: set[int],
) -> list[CandidateJudgmentV4]:
    judgments = result.judgments
    judged_ids = [item.issue_id for item in judgments]
    if len(judged_ids) != len(set(judged_ids)):
        raise RuntimeError(f"{day}: LLM 판정에 중복 issue_id가 있습니다")

    valid_ids = set(candidate_ids)
    unexpected = set(judged_ids) - valid_ids
    if unexpected:
        raise RuntimeError(
            f"{day}: 오늘 후보가 아닌 issue_id를 판정했습니다: {sorted(unexpected)}"
        )
    missing = valid_ids - set(judged_ids)
    if missing:
        raise RuntimeError(f"{day}: LLM 판정 누락 issue_id={sorted(missing)}")

    judgments_by_id = {item.issue_id: item for item in judgments}
    ordered = [judgments_by_id[issue_id] for issue_id in candidate_ids]
    for item in ordered:
        invalid_matches = set(item.matched_previous_issue_ids) - previous_ids
        if invalid_matches:
            raise RuntimeError(
                f"{day}: issue_id={item.issue_id}의 비교 대상이 최근 발행분에 없습니다: "
                f"{sorted(invalid_matches)}"
            )
    return ordered


async def judge_candidates(
    day: str,
    candidates: list[dict],
    previous: list[dict],
    *,
    llm=None,
) -> tuple[list[CandidateJudgmentV4], bool]:
    """후보 전체를 판정하고 구조 오류면 오류 사유를 넣어 한 번만 보정한다."""
    candidate_ids = [candidate["issue_id"] for candidate in candidates]
    previous_ids = {candidate["issue_id"] for candidate in previous}
    prompt = PROMPT.format(
        date=day,
        history_days=HISTORY_DAYS,
        previous=previous_lines(previous),
        candidates=candidate_lines(candidates),
    )
    model = llm or build_editorial_llm()
    try:
        result: DayJudgmentV4 = await model.ainvoke(prompt)
        return normalize_judgments(day, result, candidate_ids, previous_ids), False
    except (RuntimeError, ValidationError) as error:
        allowed_previous = sorted(previous_ids)
        repair_prompt = (
            f"{prompt}\n\n[이전 출력 오류]\n{error}\n\n"
            "전체 오늘 후보를 다시 판정하라. "
            f"matched_previous_issue_ids에 허용되는 값은 {allowed_previous}뿐이며, "
            "오늘 후보 ID는 절대 넣지 않는다."
        )
        repaired: DayJudgmentV4 = await model.ainvoke(repair_prompt)
        return (
            normalize_judgments(day, repaired, candidate_ids, previous_ids),
            True,
        )
