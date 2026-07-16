"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { Brand } from "@/components/brand";
import { ProgressDots } from "@/components/progress-dots";
import { getIssue, submitDailyQuiz } from "@/lib/api";
import { completeIssue, getDailyPlan, isIssueComplete } from "@/lib/storage";
import type {
  DailyLearningItem,
  DailyQuizResult,
  IssueDetail,
  StoredDailyPlan,
} from "@/lib/types";

export function LearningReader({ issueId }: { issueId: number }) {
  const router = useRouter();
  const [detail, setDetail] = useState<IssueDetail | null>(null);
  const [plan, setPlan] = useState<StoredDailyPlan | null>(null);
  const [item, setItem] = useState<DailyLearningItem | null>(null);
  const [quizOpen, setQuizOpen] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const [result, setResult] = useState<DailyQuizResult | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const stored = getDailyPlan();
    const learningItem = stored?.learning.items.find(
      (candidate) => candidate.issue.id === issueId,
    );
    if (!stored || !learningItem) {
      router.replace("/");
      return;
    }
    // eslint-disable-next-line react-hooks/set-state-in-effect -- client-only 학습 계획을 hydration 뒤 복원한다.
    setPlan(stored);
    setItem(learningItem);

    let active = true;
    getIssue(issueId)
      .then((issue) => {
        if (active) setDetail(issue);
      })
      .catch((reason: unknown) => {
        if (active) {
          setError(
            reason instanceof Error ? reason.message : "이슈를 불러오지 못했어요.",
          );
        }
      });
    return () => {
      active = false;
    };
  }, [issueId, router]);

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
      setError(reason instanceof Error ? reason.message : "답을 제출하지 못했어요.");
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

  if (error && !detail) {
    return (
      <main className="reader-shell">
        <header className="reader-topbar">
          <Brand compact />
          <Link href="/">오늘의 목록</Link>
        </header>
        <section className="empty-state">
          <h1>이슈를 열지 못했어요.</h1>
          <p>{error}</p>
          <Link className="button button--primary" href="/">홈으로 돌아가기</Link>
        </section>
      </main>
    );
  }

  if (!detail || !plan || !item) {
    return (
      <main className="reader-shell">
        <header className="reader-topbar"><Brand compact /></header>
        <section className="reader-loading">
          <span />
          <span />
          <span />
        </section>
      </main>
    );
  }

  const completedBefore = plan.learning.items.filter(
    (candidate) => candidate.position < item.position,
  ).length;

  return (
    <main className="reader-shell">
      <header className="reader-topbar">
        <Link className="icon-link" href="/" aria-label="오늘의 목록으로 돌아가기">←</Link>
        <ProgressDots
          total={plan.learning.total_count}
          completed={Math.max(completedBefore, plan.completedIssueIds.length)}
          current={item.position}
        />
        <Brand compact />
      </header>

      <article className="reader-article">
        <header className="article-hero">
          <div className="article-hero__meta">
            <span className={`role-badge role-badge--${item.role}`}>{item.role_label}</span>
            <span>{detail.category}</span>
          </div>
          <p className="article-hero__step">오늘의 {item.position}번째 이슈</p>
          <h1>{detail.title}</h1>
          <p className="article-hero__teaser">{detail.teaser}</p>
          <div className="article-hero__source">
            <span>{detail.article_count}개 기사를 함께 읽었어요</span>
            <span>약 3분</span>
          </div>
        </header>

        <div className="reader-cards">
          {detail.cards.map((card, index) => (
            <section className="reader-card" key={`${card.head}-${index}`}>
              <span className="reader-card__number">{String(index + 1).padStart(2, "0")}</span>
              <h2>{card.head}</h2>
              {card.paragraphs.map((paragraph, paragraphIndex) => (
                <p key={paragraphIndex}>{paragraph}</p>
              ))}
            </section>
          ))}
        </div>

        {detail.terms.length > 0 && (
          <section className="term-box">
            <div className="section-heading">
              <span className="eyebrow">낯선 말 잠깐</span>
              <h2>이것만 알고 넘어가요</h2>
            </div>
            <div className="term-list">
              {detail.terms.map((term) => (
                <details key={term.name}>
                  <summary>{term.name}<span>＋</span></summary>
                  <p>{term.definition}</p>
                </details>
              ))}
            </div>
          </section>
        )}

        <details className="sources-box">
          <summary>참고한 원문 {detail.sources.length}개 보기 <span>＋</span></summary>
          <ul>
            {detail.sources.map((source) => (
              <li key={source.id}>
                <a href={source.url} target="_blank" rel="noreferrer">
                  <span>{source.news_source}</span>
                  {source.title}
                </a>
              </li>
            ))}
          </ul>
        </details>

        <section className="quiz-section" id="quiz">
          {!quizOpen && !alreadyComplete ? (
            <div className="quiz-gate">
              <span className="quiz-gate__icon">?</span>
              <span className="eyebrow">마지막 한 걸음</span>
              <h2>읽은 내용을 한 문제로 정리해볼까요?</h2>
              <p>맞히는 것보다 생각해보는 것이 중요해요.</p>
              <button
                className="button button--primary button--wide"
                onClick={() => setQuizOpen(true)}
                type="button"
              >
                퀴즈 풀기
              </button>
            </div>
          ) : alreadyComplete && !result ? (
            <div className="quiz-result quiz-result--complete">
              <span className="quiz-result__mark">✓</span>
              <span className="eyebrow">이미 완료했어요</span>
              <h2>이 이슈의 학습을 마쳤습니다.</h2>
              <button className="button button--primary button--wide" onClick={moveNext}>
                {nextItem ? "다음 이슈 보기" : "오늘의 학습 마치기"}
              </button>
            </div>
          ) : result ? (
            <div className={`quiz-result ${result.is_correct ? "is-correct" : "is-wrong"}`}>
              <span className="quiz-result__mark">{result.is_correct ? "✓" : "!"}</span>
              <span className="eyebrow">
                {result.is_correct ? "잘 이해했어요" : "이렇게 기억하면 돼요"}
              </span>
              <h2>{result.is_correct ? "정답이에요." : "괜찮아요. 학습은 지금부터예요."}</h2>
              <p>{result.explanation}</p>
              <button className="button button--primary button--wide" onClick={moveNext}>
                {nextItem ? "다음 이슈 보기" : "오늘의 학습 마치기"}
              </button>
            </div>
          ) : (
            <div className="quiz-card">
              <span className="eyebrow">오늘의 한 문제</span>
              <h2>{item.quiz.question}</h2>
              <div className="quiz-options" role="radiogroup" aria-label="퀴즈 답변">
                {item.quiz.options.map((option, index) => (
                  <button
                    className={selectedIndex === index ? "is-selected" : ""}
                    key={option}
                    onClick={() => setSelectedIndex(index)}
                    role="radio"
                    aria-checked={selectedIndex === index}
                    type="button"
                  >
                    <span>{index + 1}</span>{option}
                  </button>
                ))}
              </div>
              {error && <p className="form-error" role="alert">{error}</p>}
              <button
                className="button button--primary button--wide"
                disabled={selectedIndex === null || submitting}
                onClick={submitQuiz}
                type="button"
              >
                {submitting ? "답을 확인하고 있어요" : "답 확인하기"}
              </button>
            </div>
          )}
        </section>
      </article>
    </main>
  );
}
