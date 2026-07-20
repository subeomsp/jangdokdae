import { expect, test, type Page } from "@playwright/test";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

const VIEWPORTS = [
  { name: "mobile-390x844", width: 390, height: 844 },
  { name: "small-360x800", width: 360, height: 800 },
  { name: "desktop-1280x900", width: 1280, height: 900 },
];

async function shot(page: Page, dir: string, name: string, fullPage = true) {
  // 스텝 전환·시트 등장 애니메이션(120~500ms)이 끝난 뒤 캡처한다.
  await page.waitForTimeout(600);
  await page.screenshot({ path: `screenshots/${dir}/${name}.png`, fullPage });
}

async function advanceToQuiz(page: Page) {
  const primaryAction = page.getByTestId("primary-action");
  for (let step = 0; step < 8; step += 1) {
    const label = (await primaryAction.textContent())?.trim();
    if (label === "퀴즈 풀기") break;
    await primaryAction.click();
  }
  await expect(primaryAction).toHaveText("퀴즈 풀기");
}

async function fetchAnswerIndex(page: Page, issueId: string) {
  const response = await page.request.post(
    `${API_BASE}/api/v1/learning/today/${issueId}/quiz`,
    { data: { selected_index: 0 } },
  );
  const body = (await response.json()) as { answer_index: number };
  return body.answer_index;
}

test.describe("스크린샷 캡처", () => {
  test.skip(!process.env.SCREENSHOTS, "SCREENSHOTS=1일 때만 실행");

  for (const viewport of VIEWPORTS) {
    test(`전체 흐름 ${viewport.name}`, async ({ page }) => {
      test.setTimeout(120_000);
      await page.setViewportSize(viewport);
      const dir = viewport.name;

      await page.goto("/onboarding");
      const sectorButtons = page
        .getByRole("region", { name: "관심 섹터 선택" })
        .getByRole("button");
      await expect(sectorButtons.first()).toBeVisible();
      await shot(page, dir, "01-onboarding");

      await sectorButtons.first().click();
      await shot(page, dir, "02-onboarding-selected");

      await page.getByRole("button", { name: "오늘의 세 가지 만나기" }).click();
      await expect(
        page.getByRole("list", { name: "오늘의 세 가지 이슈" }).getByRole("listitem"),
      ).toHaveCount(3);
      await shot(page, dir, "03-home");

      await page.getByRole("link", { name: "첫 번째 이슈 시작하기" }).click();
      await expect(page.getByText("오늘의 1번째 이슈")).toBeVisible();
      await shot(page, dir, "04-reader-intro");

      const termsButton = page.getByRole("button", { name: /^용어 \d+$/ });
      if (await termsButton.isVisible()) {
        await termsButton.click();
        await expect(page.getByRole("dialog", { name: "용어 설명" })).toBeVisible();
        await shot(page, dir, "05-reader-terms", false);
        await page.getByRole("button", { name: "닫기" }).click();
      }

      const primaryAction = page.getByTestId("primary-action");
      await primaryAction.click();
      await shot(page, dir, "06-reader-card");

      await advanceToQuiz(page);
      await primaryAction.click();
      await shot(page, dir, "07-reader-quiz");

      // 정답 인덱스를 미리 조회해 정답 피드백을 확정적으로 캡처한다.
      const firstIssueId = page.url().split("/learn/")[1];
      const answerIndex = await fetchAnswerIndex(page, firstIssueId);
      await page.getByRole("radio").nth(answerIndex).click();
      await shot(page, dir, "08-reader-quiz-selected");
      await page.getByRole("button", { name: "답 확인하기" }).click();
      await expect(page.getByText("정답이에요.")).toBeVisible();
      await shot(page, dir, "09-reader-quiz-correct");

      await page.goto("/");
      await expect(page.getByRole("link", { name: "이어서 학습하기" })).toBeVisible();
      await shot(page, dir, "10-home-partial");

      // 두 번째 이슈: 오답 피드백을 확정적으로 캡처한다.
      await page.getByRole("link", { name: "이어서 학습하기" }).click();
      await expect(page.getByText("오늘의 2번째 이슈")).toBeVisible();
      await advanceToQuiz(page);
      await primaryAction.click();
      const secondIssueId = page.url().split("/learn/")[1];
      const secondAnswer = await fetchAnswerIndex(page, secondIssueId);
      await page.getByRole("radio").nth((secondAnswer + 1) % 4).click();
      await page.getByRole("button", { name: "답 확인하기" }).click();
      await expect(page.getByText("괜찮아요. 학습은 지금부터예요.")).toBeVisible();
      await shot(page, dir, "11-reader-quiz-wrong");

      await page.getByRole("button", { name: "다음 이슈 보기" }).click();
      await expect(page.getByText("오늘의 3번째 이슈")).toBeVisible();
      await advanceToQuiz(page);
      await primaryAction.click();
      await page.getByRole("radio").first().click();
      await page.getByRole("button", { name: "답 확인하기" }).click();
      await page.getByRole("button", { name: "오늘의 학습 마치기" }).click();

      await expect(
        page.getByRole("heading", { name: /오늘 알아야 할 만큼은/ }),
      ).toBeVisible();
      await shot(page, dir, "12-complete");
    });
  }

  test("로딩·오류·빈 상태 (390x844)", async ({ page }) => {
    test.setTimeout(120_000);
    await page.setViewportSize({ width: 390, height: 844 });
    const dir = "states-390x844";

    // 온보딩 로딩
    await page.route("**/api/v1/sectors", async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 4000));
      await route.continue().catch(() => {});
    });
    await page.goto("/onboarding");
    await page.waitForTimeout(400);
    await shot(page, dir, "01-onboarding-loading");
    await page.unrouteAll({ behavior: "ignoreErrors" });

    // 관심사를 저장해 홈 상태를 재현한다.
    await page.evaluate(() => {
      localStorage.clear();
      localStorage.setItem(
        "jangdokdae.interests.v1",
        JSON.stringify({ sectorIds: [8], savedAt: new Date().toISOString() }),
      );
    });

    // 홈 로딩
    await page.route("**/api/v1/learning/today*", async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 4000));
      await route.continue().catch(() => {});
    });
    await page.goto("/");
    await page.waitForTimeout(400);
    await shot(page, dir, "02-home-loading");
    await page.unrouteAll({ behavior: "ignoreErrors" });

    // 홈 오류
    await page.route("**/api/v1/learning/today*", (route) => route.abort());
    await page.goto("/");
    await expect(page.getByText("오늘의 장독대를 열지 못했어요.")).toBeVisible();
    await shot(page, dir, "03-home-error");
    await page.unrouteAll({ behavior: "ignoreErrors" });

    // 콘텐츠 없음
    await page.route("**/api/v1/learning/today*", (route) =>
      route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          learning_date: "2026-07-20",
          items: [],
          completed_count: 0,
          total_count: 0,
          is_complete: false,
          personalized: true,
        }),
      }),
    );
    await page.evaluate(() => localStorage.removeItem("jangdokdae.daily-plan.v1"));
    await page.goto("/");
    await expect(page.getByText("꼭 읽어야 할 이슈가 아직 없어요.")).toBeVisible();
    await shot(page, dir, "04-home-empty");
  });
});
