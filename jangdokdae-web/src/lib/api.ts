import type {
  DailyLearning,
  DailyQuizResult,
  IssueDetail,
  Sector,
} from "@/lib/types";

const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"
).replace(/\/$/, "");

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
  }
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });

  if (!response.ok) {
    let message = "요청을 처리하지 못했어요.";
    try {
      const body = (await response.json()) as {
        detail?: string;
        error?: { message?: string };
      };
      message = body.error?.message ?? body.detail ?? message;
    } catch {
      // 응답 본문이 JSON이 아니어도 상태 코드로 오류를 전달한다.
    }
    throw new ApiError(message, response.status);
  }
  return (await response.json()) as T;
}

export function getTodayLearning(sectorIds: number[]): Promise<DailyLearning> {
  const params = new URLSearchParams();
  for (const sectorId of sectorIds) {
    params.append("sector_ids", String(sectorId));
  }
  const query = params.size > 0 ? `?${params.toString()}` : "";
  return apiFetch<DailyLearning>(`/api/v1/learning/today${query}`);
}

export function getIssue(issueId: number): Promise<IssueDetail> {
  return apiFetch<IssueDetail>(`/api/v1/issues/${issueId}`);
}

export function submitDailyQuiz(
  issueId: number,
  selectedIndex: number,
): Promise<DailyQuizResult> {
  return apiFetch<DailyQuizResult>(`/api/v1/learning/today/${issueId}/quiz`, {
    method: "POST",
    body: JSON.stringify({ selected_index: selectedIndex }),
  });
}

export function getSectors(): Promise<Sector[]> {
  return apiFetch<Sector[]>("/api/v1/sectors");
}
