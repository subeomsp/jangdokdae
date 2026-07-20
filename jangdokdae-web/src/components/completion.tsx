"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { BottomBar } from "@/components/bottom-bar";
import { Brand } from "@/components/brand";
import { CheckIcon } from "@/components/icons";
import { getDailyPlan } from "@/lib/storage";
import type { StoredDailyPlan } from "@/lib/types";

export function Completion() {
  const [plan, setPlan] = useState<StoredDailyPlan | null>(null);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- localStorage는 hydration 뒤에만 읽는다.
    setPlan(getDailyPlan());
  }, []);

  const completed = plan?.completedIssueIds.length ?? 0;
  const total = plan?.learning.total_count ?? 3;

  return (
    <main className="shell">
      <header className="topbar">
        <Brand />
      </header>

      <section className="completion">
        <span className="completion__check" aria-hidden="true">
          <svg fill="none" height="64" viewBox="0 0 64 64" width="64">
            <circle
              cx="32"
              cy="32"
              r="29"
              stroke="currentColor"
              strokeWidth="3"
              className="completion__check-ring"
            />
            <path
              d="M20 33.5 28.5 42 44 24"
              stroke="currentColor"
              strokeWidth="3.5"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="completion__check-mark"
            />
          </svg>
        </span>
        <p className="completion__count">
          {completed}/{total}
        </p>
        <p className="page-head__label">오늘의 학습 완료</p>
        <h1>
          오늘 알아야 할 만큼은
          <br />충분히 알았어요.
        </h1>
        <p className="completion__copy">
          더 많은 뉴스를 읽지 않아도 괜찮아요.
          <br />내일 다시 중요한 세 가지만 담아둘게요.
        </p>

        {plan && plan.learning.items.length > 0 && (
          <ul className="completion__recap" aria-label="오늘 학습한 이슈">
            {plan.learning.items.map((item) => (
              <li key={item.issue.id}>
                <CheckIcon className="completion__recap-check" size={16} />
                <span>{item.issue.title}</span>
              </li>
            ))}
          </ul>
        )}

        <p className="completion__mantra">많이 보는 것보다, 제대로 이해하는 하루.</p>
      </section>

      <BottomBar>
        <Link className="btn btn--ghost btn--wide" href="/">
          오늘의 이슈 다시 보기
        </Link>
      </BottomBar>
    </main>
  );
}
