"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { BottomBar } from "@/components/bottom-bar";
import { Brand } from "@/components/brand";
import { ArrowLeftIcon, CheckIcon } from "@/components/icons";
import {
  renderParagraphWithTerms,
  termAppearsInText,
} from "@/components/inline-term";
import { SegmentProgress } from "@/components/segment-progress";
import { TermSheet } from "@/components/term-sheet";
import { ApiError, getIssue, submitDailyQuiz } from "@/lib/api";
import { completeIssue, getDailyPlan, isIssueComplete } from "@/lib/storage";
import type {
  DailyLearningItem,
  DailyQuizResult,
  IssueDetail,
  IssueTerm,
  StoredDailyPlan,
} from "@/lib/types";

export function LearningReader({ issueId }: { issueId: number }) {
  const router = useRouter();
  const [detail, setDetail] = useState<IssueDetail | null>(null);
  const [plan, setPlan] = useState<StoredDailyPlan | null>(null);
  const [item, setItem] = useState<DailyLearningItem | null>(null);
  const [stepIndex, setStepIndex] = useState(0);
  const [termsOpen, setTermsOpen] = useState(false);
  const [selectedTerm, setSelectedTerm] = useState<IssueTerm | null>(null);
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const [result, setResult] = useState<DailyQuizResult | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const headingRef = useRef<HTMLHeadingElement>(null);
  const termsButtonRef = useRef<HTMLButtonElement>(null);
  const optionRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const mountedRef = useRef(false);

  useEffect(() => {
    const stored = getDailyPlan();
    const learningItem = stored?.learning.items.find(
      (candidate) => candidate.issue.id === issueId,
    );
    if (!stored || !learningItem) {
      router.replace("/");
      return;
    }
    /* eslint-disable react-hooks/set-state-in-effect -- client-only 학습 계획을 hydration 뒤 복원하고, 이슈 전환 시 스텝 상태를 초기화한다. */
    setPlan(stored);
    setItem(learningItem);
    setStepIndex(0);
    setTermsOpen(false);
    setSelectedTerm(null);
    setSelectedIndex(null);
    setResult(null);
    setError(null);
    /* eslint-enable react-hooks/set-state-in-effect */

    let active = true;
    getIssue(issueId)
      .then((issue) => {
        if (active) setDetail(issue);
      })
      .catch((reason: unknown) => {
        if (active) {
          setError(
            reason instanceof ApiError
              ? reason.message
              : "서버에 연결하지 못했어요. 네트워크를 확인한 뒤 다시 시도해주세요.",
          );
        }
      });
    return () => {
      active = false;
    };
  }, [issueId, router]);

  useEffect(() => {
    if (!mountedRef.current) {
      mountedRef.current = true;
      return;
    }
    window.scrollTo({ top: 0, behavior: "instant" });
    headingRef.current?.focus({ preventScroll: true });
  }, [stepIndex]);

  const alreadyComplete = Boolean(plan && isIssueComplete(plan, issueId));
  const nextItem = useMemo(() => {
    if (!plan || !item) return null;
    return plan.learning.items.find(
      (candidate) => candidate.position === item.position + 1,
    ) ?? null;
  }, [item, plan]);

  async function submitQuiz() {
    if (selectedIndex === null || !item) return;
    setSubmitting(true);
    setError(null);
    try {
      const quizResult = await submitDailyQuiz(issueId, selectedIndex);
      setResult(quizResult);
      const updated = completeIssue(issueId);
      if (updated) setPlan(updated);
    } catch (reason) {
      setError(
        reason instanceof ApiError ? reason.message : "답을 제출하지 못했어요. 다시 시도해주세요.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  function moveNext() {
    if (nextItem) {
      router.push(`/learn/${nextItem.issue.id}`);
    } else {
      router.push("/complete");
    }
  }

  function onOptionKeyDown(
    event: React.KeyboardEvent<HTMLButtonElement>,
    index: number,
  ) {
    if (!item || result) return;
    const count = item.quiz.options.length;
    let next: number | null = null;
    if (event.key === "ArrowDown" || event.key === "ArrowRight") {
      next = (index + 1) % count;
    } else if (event.key === "ArrowUp" || event.key === "ArrowLeft") {
      next = (index - 1 + count) % count;
    }
    if (next !== null) {
      event.preventDefault();
      setSelectedIndex(next);
      optionRefs.current[next]?.focus();
    }
  }

  if (error && !detail) {
    return (
      <main className="shell">
        <header className="topbar">
          <Brand compact />
          <Link className="topbar__link" href="/">
            오늘의 목록
          </Link>
        </header>
        <section className="state-block">
          <h1>이슈를 열지 못했어요.</h1>
          <p>{error}</p>
          <Link className="btn btn--primary" href="/">
            홈으로 돌아가기
          </Link>
        </section>
      </main>
    );
  }

  if (!detail || !plan || !item) {
    return (
      <main className="shell">
        <header className="topbar">
          <Brand compact />
        </header>
        <div className="reader-skeleton">
          <div className="skeleton reader-skeleton__kicker" />
          <div className="skeleton reader-skeleton__title" />
          <div className="skeleton reader-skeleton__title reader-skeleton__title--short" />
          <div className="skeleton reader-skeleton__body" />
          <div className="skeleton reader-skeleton__body" />
        </div>
      </main>
    );
  }

  const totalSteps = detail.cards.length + 2;
  const isIntro = stepIndex === 0;
  const isQuiz = stepIndex === totalSteps - 1;
  const card = !isIntro && !isQuiz ? detail.cards[stepIndex - 1] : null;
  const resolved = Boolean(result) || alreadyComplete;
  const earlierCards = detail.cards.slice(0, Math.max(0, stepIndex - 1));
  const claimedTerms = new Set(
    detail.terms
      .filter((term) =>
        earlierCards.some((earlierCard) =>
          earlierCard.paragraphs.some((paragraph) =>
            termAppearsInText(paragraph, term),
          ),
        ),
      )
      .map((term) => term.name),
  );

  const primaryAction = isQuiz
    ? resolved
      ? {
          label: nextItem ? "다음 이슈 보기" : "오늘의 학습 마치기",
          onClick: moveNext,
          disabled: false,
        }
      : {
          label: submitting ? "답을 확인하고 있어요" : "답 확인하기",
          onClick: submitQuiz,
          disabled: selectedIndex === null || submitting,
        }
    : {
        label: stepIndex === totalSteps - 2 ? "퀴즈 풀기" : isIntro ? "읽기 시작하기" : "다음",
        onClick: () => setStepIndex((index) => index + 1),
        disabled: false,
      };

  return (
    <main className="shell">
      <header className="reader-topbar">
        {isIntro ? (
          <Link aria-label="오늘의 목록으로 돌아가기" className="icon-btn" href="/">
            <ArrowLeftIcon />
          </Link>
        ) : (
          <button
            aria-label="이전 단계"
            className="icon-btn"
            onClick={() => setStepIndex((index) => index - 1)}
            type="button"
          >
            <ArrowLeftIcon />
          </button>
        )}
        <SegmentProgress
          label={`읽기 진행 ${stepIndex + 1}/${totalSteps}`}
          total={totalSteps}
          value={stepIndex + 1}
        />
        {detail.terms.length > 0 ? (
          <button
            className="reader-topbar__terms"
            onClick={() => setTermsOpen(true)}
            ref={termsButtonRef}
            type="button"
          >
            용어 {detail.terms.length}
          </button>
        ) : (
          <span className="reader-topbar__spacer" aria-hidden="true" />
        )}
      </header>

      {isIntro && (
        <section className="step" key="intro">
          <p className="step__kicker">오늘의 {item.position}번째 이슈</p>
          <p className="step__meta">
            {item.role_label} · {detail.category}
          </p>
          <h1 className="step__title" ref={headingRef} tabIndex={-1}>
            {detail.title}
          </h1>
          <p className="step__teaser">{detail.teaser}</p>
          <p className="step__stats">기사 {detail.article_count}개 · 약 3분</p>

          {detail.sources.length > 0 && (
            <details className="sources">
              <summary>참고한 기사 {detail.sources.length}개</summary>
              <ul>
                {detail.sources.map((source) => (
                  <li key={source.id}>
                    <a href={source.url} rel="noreferrer" target="_blank">
                      <span className="sources__outlet">{source.news_source}</span>
                      <span className="sources__title">{source.title}</span>
                    </a>
                  </li>
                ))}
              </ul>
            </details>
          )}
        </section>
      )}

      {card && (
        <section className="step" key={`card-${stepIndex}`}>
          <p className="step__num" aria-hidden="true">
            {stepIndex}
          </p>
          <h2 className="step__head" ref={headingRef} tabIndex={-1}>
            {card.head}
          </h2>
          {card.paragraphs.map((paragraph, paragraphIndex) => (
            <p className="step__para" key={paragraphIndex}>
              {renderParagraphWithTerms(
                paragraph,
                detail.terms,
                claimedTerms,
                setSelectedTerm,
              )}
            </p>
          ))}
        </section>
      )}

      {isQuiz && (
        <section className="step" key="quiz">
          <p className="step__kicker">마지막 확인</p>
          <h2 className="quiz-question" ref={headingRef} tabIndex={-1}>
            {item.quiz.question}
          </h2>

          {alreadyComplete && !result ? (
            <div className="quiz-done">
              <CheckIcon className="quiz-done__check" size={18} />
              <p>이 이슈의 학습을 이미 마쳤어요.</p>
            </div>
          ) : (
            <div aria-label="퀴즈 답변" className="quiz-options" role="radiogroup">
              {item.quiz.options.map((option, index) => {
                const isAnswer = result !== null && index === result.answer_index;
                const isWrongPick =
                  result !== null &&
                  !result.is_correct &&
                  index === result.selected_index;
                const classNames = [
                  "quiz-option",
                  selectedIndex === index ? "is-selected" : "",
                  isAnswer ? "is-answer" : "",
                  isWrongPick ? "is-wrong-pick" : "",
                ]
                  .filter(Boolean)
                  .join(" ");
                return (
                  <button
                    aria-checked={selectedIndex === index}
                    className={classNames}
                    disabled={result !== null}
                    key={option}
                    onClick={() => setSelectedIndex(index)}
                    onKeyDown={(event) => onOptionKeyDown(event, index)}
                    ref={(node) => {
                      optionRefs.current[index] = node;
                    }}
                    role="radio"
                    tabIndex={
                      selectedIndex === index || (selectedIndex === null && index === 0)
                        ? 0
                        : -1
                    }
                    type="button"
                  >
                    <span aria-hidden="true" className="quiz-option__num">
                      {isAnswer ? <CheckIcon size={13} /> : index + 1}
                    </span>
                    <span className="quiz-option__text">{option}</span>
                  </button>
                );
              })}
            </div>
          )}

          <div aria-live="polite" className="quiz-feedback">
            {result && (
              <div
                className={`quiz-feedback__box ${
                  result.is_correct ? "is-correct" : "is-wrong"
                }`}
              >
                <p className="quiz-feedback__verdict">
                  {result.is_correct
                    ? "정답이에요."
                    : "괜찮아요. 학습은 지금부터예요."}
                </p>
                {result.explanation && (
                  <p className="quiz-feedback__explain">{result.explanation}</p>
                )}
              </div>
            )}
          </div>
          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
        </section>
      )}

      <BottomBar>
        <button
          className="btn btn--primary btn--wide"
          data-testid="primary-action"
          disabled={primaryAction.disabled}
          onClick={primaryAction.onClick}
          type="button"
        >
          {primaryAction.label}
        </button>
      </BottomBar>

      {termsOpen && (
        <TermSheet
          onClose={() => {
            setTermsOpen(false);
            termsButtonRef.current?.focus();
          }}
          terms={detail.terms}
        />
      )}
      {selectedTerm && (
        <TermSheet
          onClose={() => setSelectedTerm(null)}
          terms={[selectedTerm]}
          title="용어 설명"
        />
      )}
    </main>
  );
}
