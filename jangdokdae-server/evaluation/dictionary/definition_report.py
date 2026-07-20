"""쉬운 설명 반복 평가 Markdown 리포트."""

from evaluation.dictionary.definition_runner import DefinitionEvalRun


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def render_definition_run_markdown(run: DefinitionEvalRun) -> str:
    metrics = run.metrics
    power_label = f"pass^{run.repeats}"
    lines = [
        "# 한국은행 개별 용어 쉬운 설명 평가 결과",
        "",
        "## 요약",
        "",
        f"- 모델: `{run.model_name}`",
        f"- 프롬프트 버전: `{run.prompt_version}`",
        f"- 실행 시각(UTC): `{run.started_at.isoformat()}`",
        f"- 통과 점수: {run.minimum_score}점",
        f"- Task: {metrics.task_count}개 × {run.repeats}회 = {metrics.trial_count} Trials",
        f"- 총 생성 시도: {metrics.generation_attempt_count}회",
        f"- 자동 보정 Trial: {metrics.retried_trial_count}건",
        f"- `pass@1`: {metrics.pass_at_1:.1%}",
        f"- `{power_label}`: {metrics.pass_power_k:.1%}",
        f"- 전체 Trial 통과: {metrics.passed_trial_count}/{metrics.trial_count}",
        f"- 평균 점수: {metrics.average_score:.2f}",
        f"- 코드 검사 실패: {metrics.deterministic_failure_count}건",
        f"- 원문 근거 미지원: {metrics.unsupported_count}건",
        f"- 실행 오류: {metrics.errored_trial_count}건",
        "",
        "## Trial 상세",
        "",
        "| Task | 용어 | Trial | 시도 | 점수 | 근거 | 통과 | 지연 | 실패 원인 |",
        "| --- | --- | ---: | ---: | ---: | --- | --- | ---: | --- |",
    ]
    for trial in run.trials:
        score = trial.verdict.score if trial.verdict else 0
        supported = (
            "supported"
            if trial.verdict and trial.verdict.supported
            else "unsupported"
        )
        failures = trial.error or ", ".join(trial.deterministic_problems)
        if not failures and trial.verdict and not trial.passed:
            failures = trial.verdict.reason
        lines.append(
            f"| `{trial.task_id}` | {trial.term} | {trial.trial_number} "
            f"| {len(trial.attempts)} | {score} "
            f"| {supported} | {'PASS' if trial.passed else 'FAIL'} "
            f"| {trial.latency_ms}ms | {_cell(failures or '-')} |"
        )

    retried_trials = [trial for trial in run.trials if len(trial.attempts) > 1]
    if retried_trials:
        lines.extend(["", "## 자동 보정 상세", ""])
        for trial in retried_trials:
            lines.append(
                f"### {trial.term} · Trial {trial.trial_number}"
            )
            lines.append("")
            for attempt in trial.attempts:
                problem_text = ", ".join(attempt.deterministic_problems) or "-"
                lines.extend(
                    [
                        (
                            f"- Attempt {attempt.attempt_number}: "
                            f"{attempt.verdict.score}점, "
                            f"{'supported' if attempt.verdict.supported else 'unsupported'}, "
                            f"코드 문제 `{problem_text}`"
                        ),
                        f"  - 정의: {_cell(attempt.draft.definition)}",
                        f"  - 검증: {_cell(attempt.verdict.reason)}",
                    ]
                )
            lines.append("")

    gate_passed = (
        metrics.pass_at_1 == 1
        and metrics.pass_power_k == 1
        and metrics.errored_trial_count == 0
    )
    lines.extend(
        [
            "",
            "## 현재 게이트 판정",
            "",
            (
                "**PASS** — 소형 설명 회귀 게이트를 통과했습니다."
                if gate_passed
                else "**HOLD** — 실패 후보를 사람이 검토하고 생성·검증 규칙을 보완해야 합니다."
            ),
            "",
        ]
    )
    return "\n".join(lines)
