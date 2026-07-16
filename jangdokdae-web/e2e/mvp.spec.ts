import { expect, test } from "@playwright/test";

test("관심 선택부터 세 이슈 퀴즈와 오늘의 완료까지 이어진다", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/onboarding$/);

  const sectorCards = page.locator(".sector-card:not(.sector-card--skeleton)");
  await expect(sectorCards).toHaveCount(11);
  await sectorCards.first().click();
  await page.getByRole("button", { name: "오늘의 세 가지 만나기" }).click();

  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("heading", { name: /오늘은/ })).toBeVisible();
  await expect(page.locator(".daily-card")).toHaveCount(3);

  await page.getByRole("link", { name: "첫 번째 이슈 시작하기" }).click();
  await expect(page.getByText("오늘의 1번째 이슈")).toBeVisible();
  await expect(page.locator(".reader-card")).toHaveCount(4);

  for (let position = 1; position <= 3; position += 1) {
    await expect(page.getByText(`오늘의 ${position}번째 이슈`)).toBeVisible();
    await page.getByRole("button", { name: "퀴즈 풀기" }).click();
    await page.locator(".quiz-options button").first().click();
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
