import type {
  DailyLearning,
  StoredDailyPlan,
  StoredInterests,
} from "@/lib/types";

const INTERESTS_KEY = "jangdokdae.interests.v1";
const DAILY_PLAN_KEY = "jangdokdae.daily-plan.v1";

function readJson<T>(key: string): T | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

function writeJson(key: string, value: unknown): void {
  window.localStorage.setItem(key, JSON.stringify(value));
}

export function getKstDate(): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}

export function getInterests(): StoredInterests | null {
  return readJson<StoredInterests>(INTERESTS_KEY);
}

export function saveInterests(sectorIds: number[]): StoredInterests {
  const interests = {
    sectorIds: [...new Set(sectorIds)].sort((a, b) => a - b),
    savedAt: new Date().toISOString(),
  };
  writeJson(INTERESTS_KEY, interests);
  window.localStorage.removeItem(DAILY_PLAN_KEY);
  return interests;
}

export function interestKey(sectorIds: number[]): string {
  return [...sectorIds].sort((a, b) => a - b).join(",");
}

export function getDailyPlan(): StoredDailyPlan | null {
  return readJson<StoredDailyPlan>(DAILY_PLAN_KEY);
}

export function getValidDailyPlan(sectorIds: number[]): StoredDailyPlan | null {
  const plan = getDailyPlan();
  if (
    !plan ||
    plan.learningDate !== getKstDate() ||
    plan.interestKey !== interestKey(sectorIds)
  ) {
    return null;
  }
  return plan;
}

export function saveDailyPlan(
  learning: DailyLearning,
  sectorIds: number[],
): StoredDailyPlan {
  const completedIssueIds = learning.items
    .filter((item) => item.completed)
    .map((item) => item.issue.id);
  const plan = {
    learningDate: learning.learning_date,
    interestKey: interestKey(sectorIds),
    learning,
    completedIssueIds,
  };
  writeJson(DAILY_PLAN_KEY, plan);
  return plan;
}

export function completeIssue(issueId: number): StoredDailyPlan | null {
  const plan = getDailyPlan();
  if (!plan) return null;
  plan.completedIssueIds = [...new Set([...plan.completedIssueIds, issueId])];
  plan.learning.completed_count = plan.completedIssueIds.length;
  plan.learning.is_complete =
    plan.learning.total_count > 0 &&
    plan.completedIssueIds.length >= plan.learning.total_count;
  writeJson(DAILY_PLAN_KEY, plan);
  return plan;
}

export function isIssueComplete(plan: StoredDailyPlan, issueId: number): boolean {
  return plan.completedIssueIds.includes(issueId);
}
