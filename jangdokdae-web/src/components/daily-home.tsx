"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { BottomBar } from "@/components/bottom-bar";
import { Brand } from "@/components/brand";
import { CheckIcon, ChevronRightIcon } from "@/components/icons";
import { SegmentProgress } from "@/components/segment-progress";
import { ApiError, getTodayLearning } from "@/lib/api";
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
            reason instanceof ApiError
              ? reason.message
              : "서버에 연결하지 못했어요. 네트워크를 확인한 뒤 다시 시도해주세요.",
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
      <main className="shell">
        <header className="topbar">
          <Brand />
        </header>
        <div className="home-skeleton" aria-live="polite">
          <div className="skeleton home-skeleton__date" />
          <div className="skeleton home-skeleton__title" />
          <div className="skeleton home-skeleton__title home-skeleton__title--short" />
          {Array.from({ length: 3 }, (_, index) => (
            <div className="skeleton home-skeleton__row" key={index} />
          ))}
          <p className="loading-caption">오늘 꼭 볼 세 가지를 담고 있어요</p>
        </div>
      </main>
    );
  }

  if (error || !plan) {
    return (
      <main className="shell">
        <header className="topbar">
          <Brand />
        </header>
        <section className="state-block">
          <p className="page-head__label">잠시만요</p>
          <h1>오늘의 장독대를 열지 못했어요.</h1>
          <p>{error ?? "API 서버 연결을 확인해주세요."}</p>
          <button className="btn btn--primary" onClick={() => location.reload()} type="button">
            다시 불러오기
          </button>
        </section>
      </main>
    );
  }

  const isComplete =
    plan.learning.total_count > 0 && completedCount >= plan.learning.total_count;

  return (
    <main className="shell">
      <header className="topbar">
        <Brand />
        <Link className="topbar__link" href="/onboarding">
          관심 바꾸기
        </Link>
      </header>

      <section className="home-head">
        <p className="home-head__date">{formatToday(plan.learningDate)}</p>
        <h1>
          오늘은
          <br />세 가지만 보면 돼요.
        </h1>
        <p className="home-head__sub">넘치는 뉴스 대신, 지금 이해할 흐름만 담았습니다.</p>
      </section>

      <section className="home-progress" aria-label="오늘의 학습 현황">
        <div className="home-progress__row">
          <span className="home-progress__label">오늘의 학습</span>
          <strong className="home-progress__count">
            {completedCount}
            <span>/{plan.learning.total_count}</span>
          </strong>
        </div>
        <SegmentProgress
          label={`오늘의 학습 ${completedCount}/${plan.learning.total_count}`}
          total={plan.learning.total_count}
          value={completedCount}
        />
      </section>

      {plan.learning.items.length === 0 ? (
        <section className="state-block state-block--center">
          <p className="quiet-marks" aria-hidden="true">– – –</p>
          <p className="page-head__label">오늘은 조용한 날</p>
          <h2>꼭 읽어야 할 이슈가 아직 없어요.</h2>
          <p>중요하지 않은 소식으로 세 자리를 억지로 채우지 않을게요.</p>
        </section>
      ) : (
        <ol className="daily-list" aria-label="오늘의 세 가지 이슈">
          {plan.learning.items.map((item) => {
            const completed = isIssueComplete(plan, item.issue.id);
            return (
              <li key={item.issue.id}>
                <Link
                  className={`daily-row ${completed ? "is-complete" : ""}`}
                  href={`/learn/${item.issue.id}`}
                >
                  <span className="daily-row__num">
                    {completed ? (
                      <>
                        <CheckIcon size={24} />
                        <span className="sr-only">완료</span>
                      </>
                    ) : (
                      item.position
                    )}
                  </span>
                  <span className="daily-row__body">
                    <span className="daily-row__meta">
                      {item.role_label} · {item.issue.category}
                    </span>
                    <strong className="daily-row__title">{item.issue.title}</strong>
                    <span className="daily-row__reason">
                      {completed ? "학습 완료" : item.reason}
                    </span>
                  </span>
                  <ChevronRightIcon className="daily-row__chev" size={18} />
                </Link>
              </li>
            );
          })}
        </ol>
      )}

      {plan.learning.items.length > 0 && (
        <BottomBar caption={isComplete ? undefined : "이슈 하나에 약 3분이면 충분해요"}>
          <Link
            className="btn btn--primary btn--wide"
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
        </BottomBar>
      )}
    </main>
  );
}
