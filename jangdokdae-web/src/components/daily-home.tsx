"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { Brand } from "@/components/brand";
import { ProgressDots } from "@/components/progress-dots";
import { getTodayLearning } from "@/lib/api";
import {
  getInterests,
  getValidDailyPlan,
  isIssueComplete,
  saveDailyPlan,
} from "@/lib/storage";
import type { StoredDailyPlan } from "@/lib/types";

function formatToday(date: string): string {
  const parsed = new Date(`${date}T00:00:00+09:00`);
  return new Intl.DateTimeFormat("ko-KR", {
    timeZone: "Asia/Seoul",
    month: "long",
    day: "numeric",
    weekday: "long",
  }).format(parsed);
}

export function DailyHome() {
  const router = useRouter();
  const [plan, setPlan] = useState<StoredDailyPlan | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const interests = getInterests();
    if (!interests) {
      router.replace("/onboarding");
      return () => {
        active = false;
      };
    }

    const cached = getValidDailyPlan(interests.sectorIds);
    if (cached) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- client-only 캐시를 hydration 뒤 복원한다.
      setPlan(cached);
      setLoading(false);
      return () => {
        active = false;
      };
    }

    getTodayLearning(interests.sectorIds)
      .then((learning) => {
        if (active) setPlan(saveDailyPlan(learning, interests.sectorIds));
      })
      .catch((reason: unknown) => {
        if (active) {
          setError(
            reason instanceof Error
              ? reason.message
              : "오늘의 이슈를 불러오지 못했어요.",
          );
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [router]);

  const completedCount = plan?.completedIssueIds.length ?? 0;
  const nextItem = useMemo(
    () =>
      plan?.learning.items.find(
        (item) => !plan.completedIssueIds.includes(item.issue.id),
      ) ?? null,
    [plan],
  );

  if (loading) {
    return (
      <main className="app-shell home-shell">
        <header className="topbar">
          <Brand />
        </header>
        <section className="loading-state" aria-live="polite">
          <span className="loading-state__jar" />
          <p>오늘 꼭 볼 세 가지를 담고 있어요</p>
        </section>
      </main>
    );
  }

  if (error || !plan) {
    return (
      <main className="app-shell home-shell">
        <header className="topbar">
          <Brand />
        </header>
        <section className="empty-state">
          <span className="eyebrow">잠시만요</span>
          <h1>오늘의 장독대를 열지 못했어요.</h1>
          <p>{error ?? "API 서버 연결을 확인해주세요."}</p>
          <button className="button button--primary" onClick={() => location.reload()}>
            다시 불러오기
          </button>
        </section>
      </main>
    );
  }

  const isComplete =
    plan.learning.total_count > 0 && completedCount >= plan.learning.total_count;

  return (
    <main className="app-shell home-shell">
      <header className="topbar">
        <Brand />
        <Link className="text-link" href="/onboarding">
          관심 바꾸기
        </Link>
      </header>

      <section className="home-intro">
        <p className="home-intro__date">{formatToday(plan.learningDate)}</p>
        <h1>
          오늘은
          <br />세 가지만 보면 돼요.
        </h1>
        <p className="home-intro__copy">
          넘치는 뉴스 대신, 지금 이해할 흐름만 담았습니다.
        </p>
      </section>

      <section className="daily-progress" aria-label="오늘의 학습 현황">
        <div className="daily-progress__top">
          <span>오늘의 학습</span>
          <strong>
            {completedCount}<small> / {plan.learning.total_count}</small>
          </strong>
        </div>
        <ProgressDots total={plan.learning.total_count} completed={completedCount} />
      </section>

      {plan.learning.items.length === 0 ? (
        <section className="empty-state empty-state--inline">
          <span className="eyebrow">오늘은 조용한 날</span>
          <h2>꼭 읽어야 할 이슈가 아직 없어요.</h2>
          <p>중요하지 않은 소식으로 세 자리를 억지로 채우지 않을게요.</p>
        </section>
      ) : (
        <section className="daily-list" aria-label="오늘의 세 가지 이슈">
          {plan.learning.items.map((item) => {
            const completed = isIssueComplete(plan, item.issue.id);
            return (
              <Link
                className={`daily-card ${completed ? "is-complete" : ""}`}
                href={`/learn/${item.issue.id}`}
                key={item.issue.id}
              >
                <div className="daily-card__number">
                  {completed ? <span aria-label="완료">✓</span> : item.position}
                </div>
                <div className="daily-card__body">
                  <div className="daily-card__meta">
                    <span>{item.role_label}</span>
                    <span>{item.issue.category}</span>
                  </div>
                  <h2>{item.issue.title}</h2>
                  <p>{completed ? "학습 완료" : item.reason}</p>
                </div>
                <span className="daily-card__arrow" aria-hidden="true">→</span>
              </Link>
            );
          })}
        </section>
      )}

      {plan.learning.items.length > 0 && (
        <div className="home-action">
          <Link
            className="button button--primary button--wide"
            href={
              isComplete
                ? "/complete"
                : `/learn/${nextItem?.issue.id ?? plan.learning.items[0].issue.id}`
            }
          >
            {isComplete
              ? "오늘의 마무리 보기"
              : completedCount === 0
                ? "첫 번째 이슈 시작하기"
                : "이어서 학습하기"}
          </Link>
          {!isComplete && <p>이슈 하나에 약 3분이면 충분해요</p>}
        </div>
      )}
    </main>
  );
}
