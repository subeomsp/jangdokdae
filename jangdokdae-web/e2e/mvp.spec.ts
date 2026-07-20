import { expect, test } from "@playwright/test";

test("관심 선택부터 세 이슈 퀴즈와 오늘의 완료까지 이어진다", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/onboarding$/);

  const sectorButtons = page
    .getByRole("region", { name: "관심 섹터 선택" })
    .getByRole("button");
  await expect(sectorButtons).toHaveCount(11);
  await sectorButtons.first().click();
  await page.getByRole("button", { name: "오늘의 세 가지 만나기" }).click();

  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("heading", { name: /오늘은/ })).toBeVisible();
  await expect(
    page.getByRole("list", { name: "오늘의 세 가지 이슈" }).getByRole("listitem"),
  ).toHaveCount(3);

  await page.getByRole("link", { name: "첫 번째 이슈 시작하기" }).click();
  await expect(page.getByText("오늘의 1번째 이슈")).toBeVisible();
  // 인트로 + 해설 카드 4개 + 퀴즈 = 6스텝
  await expect(
    page.getByRole("progressbar", { name: /읽기 진행/ }),
  ).toHaveAttribute("aria-valuemax", "6");

  const primaryAction = page.getByTestId("primary-action");

  for (let position = 1; position <= 3; position += 1) {
    await expect(page.getByText(`오늘의 ${position}번째 이슈`)).toBeVisible();

    // 읽기 스텝을 순서대로 통과해 퀴즈 스텝에 도달한다 (카드 수 3~5개에 견고).
    for (let step = 0; step < 8; step += 1) {
      const label = (await primaryAction.textContent())?.trim();
      if (label === "퀴즈 풀기") break;
      await primaryAction.click();
    }
    await expect(primaryAction).toHaveText("퀴즈 풀기");
    await primaryAction.click();

    await page.getByRole("radio").first().click();
    await page.getByRole("button", { name: "답 확인하기" }).click();

    const nextLabel = position < 3 ? "다음 이슈 보기" : "오늘의 학습 마치기";
    await page.getByRole("button", { name: nextLabel }).click();
  }

  await expect(page).toHaveURL(/\/complete$/);
  await expect(
    page.getByRole("heading", { name: /오늘 알아야 할 만큼은/ }),
  ).toBeVisible();
  await expect(page.getByText("3/3")).toBeVisible();
});
