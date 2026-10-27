import { test, expect } from "@playwright/test";

test("four internal agents use permitted evidence, human reviews and source revocation without external actions", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByLabel("ایمیل", { exact: true }).fill("browser@example.test");
  await page
    .getByLabel("رمز عبور", { exact: true })
    .fill("Browser-test-only-123");
  await page
    .getByLabel("شناسه سازمان")
    .fill("00000000-0000-0000-0000-000000000001");
  await page.getByRole("button", { name: "ورود", exact: true }).click();
  await page
    .getByRole("button", { name: "مرکز ایجنت‌ها", exact: true })
    .click();
  const stamp = Date.now().toString();
  const name = "دانش مجاز " + stamp;
  const content =
    "مالکیت کالا مستقل از محل نگهداری است. این متن برای تست داخلی مصنوعی است.";
  await page.getByText("ثبت منبع مجاز", { exact: true }).click();
  await page.getByLabel("عنوان منبع", { exact: true }).fill(name);
  await page.getByLabel("متن دانش", { exact: true }).fill(content);
  await page
    .getByLabel("انتساب و مجوز استفاده")
    .fill("Synthetic internal browser fixture");
  await page
    .getByRole("checkbox", {
      name: "اجازهٔ استفاده از این متن و ارسال آن به مدل محلی را دارم.",
    })
    .check();
  const sourceResponse = page.waitForResponse(
    (r) =>
      r.url().endsWith("/agent-workbench/sources") &&
      r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "ثبت دانش مجاز", exact: true })
    .click();
  expect((await sourceResponse).status()).toBe(201);
  await page.getByRole("checkbox", { name: new RegExp(name) }).check();
  const counts = async () =>
    Promise.all(
      ["price-observations", "sales-drafts", "inventory/entries"].map(
        async (p) =>
          (await (await page.request.get("/api/backend/" + p)).json()).total,
      ),
    );
  const before = await counts();
  let researchId = "";
  const region = page.getByRole("region", { name: "خروجی ایجنت" });
  const roles = [
    ["تحقیق و توسعه", "research"],
    ["آموزش", "education"],
    ["بازاریابی", "marketing"],
    ["فروش", "sales"],
  ];
  for (const [label, kind] of roles) {
    await page.getByRole("button", { name: label, exact: true }).click();
    await page
      .getByLabel("درخواست ایجنت", { exact: true })
      .fill("با این منبع یک پیش‌نویس داخلی برای " + label + " بساز");
    const response = page.waitForResponse(
      (r) =>
        r.url().endsWith("/agent-workbench/runs") &&
        r.request().method() === "POST",
    );
    await page
      .getByRole("button", { name: "تولید پیش‌نویس داخلی", exact: true })
      .click();
    const result = await response;
    expect(result.status()).toBe(201);
    const data = await result.json();
    expect(data.kind).toBe(kind);
    if (kind === "research") researchId = data.id;
    expect(data.financial_approval).toBe(false);
    expect(data.external_actions).toBe(false);
    expect(data.published).toBe(false);
    expect(data.evidence[0].snapshot.content).toBe(content);
    await expect(
      region.getByRole("heading", { name: "نقل‌قول‌های دقیق از شواهد" }),
    ).toBeVisible();
    if (kind === "research") {
      await page
        .getByLabel("یادداشت بازبینی", { exact: true })
        .fill("بازبینی داخلی تست؛ مجوز انتشار نیست");
      await page
        .getByRole("checkbox", {
          name: "می‌دانم بازبینی داخلی، مجوز انتشار یا تأیید مالی نیست.",
        })
        .check();
      await page
        .getByRole("button", { name: "ثبت بازبینی انسانی", exact: true })
        .click();
      await expect(region.getByRole("status")).toContainText(
        "بازبینی داخلی پذیرفته شد",
      );
    }
  }
  await page
    .getByRole("button", { name: "لغو اعتبار " + name, exact: true })
    .click();
  await page
    .getByRole("button", { name: "تأیید لغو اعتبار منبع", exact: true })
    .click();
  await expect(region.getByRole("alert")).toContainText(
    "اعتبار یکی از منابع لغو شده است",
  );
  const historic = await (
    await page.request.get("/api/backend/agent-workbench/runs/" + researchId)
  ).json();
  expect(historic.review.decision).toBe("accepted");
  expect(historic.evidence_current).toBe(false);
  expect(await counts()).toEqual(before);
  expect(
    (
      await page.request.post("/api/backend/agent-workbench/runs", {
        headers: { Origin: "https://untrusted.example" },
        data: { kind: "research", brief: "Do not execute this request" },
      })
    ).status(),
  ).toBe(403);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});

test("documented ownership lesson gives deterministic self-checks without model generation", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByLabel("ایمیل", { exact: true }).fill("browser@example.test");
  await page
    .getByLabel("رمز عبور", { exact: true })
    .fill("Browser-test-only-123");
  await page
    .getByLabel("شناسه سازمان")
    .fill("00000000-0000-0000-0000-000000000001");
  await page.getByRole("button", { name: "ورود", exact: true }).click();
  await page
    .getByRole("button", { name: "مرکز ایجنت‌ها", exact: true })
    .click();
  let generated = 0;
  page.on("request", (request) => {
    if (
      request.method() === "POST" &&
      request.url().endsWith("/agent-workbench/runs")
    )
      generated++;
  });
  await page.getByRole("button", { name: "آموزش", exact: true }).click();
  const training = page.getByRole("region", { name: "آموزش پایهٔ سیستم" });
  await training.getByText("مالکیت و محل نگهداری", { exact: true }).click();
  const lesson = training
    .locator("details")
    .filter({ hasText: "مالکیت و محل نگهداری" });
  await lesson
    .getByRole("radio", { name: "شرکت ب به دلیل انبارداری", exact: true })
    .check();
  await lesson
    .getByRole("radio", { name: "مالکیت را به انبار مقصد می‌دهد", exact: true })
    .check();
  await lesson
    .getByRole("button", { name: "بررسی پاسخ‌ها", exact: true })
    .click();
  await expect(lesson.getByRole("status")).toContainText("پاسخ درست: ۰ از ۲");
  await expect(lesson.getByRole("status")).toContainText("مشتری الف مالک است");
  await lesson.getByRole("radio", { name: "مشتری الف", exact: true }).check();
  await lesson
    .getByRole("radio", { name: "مالکیت را تغییر نمی‌دهد", exact: true })
    .check();
  await expect(lesson.getByRole("status")).toHaveCount(0);
  await lesson
    .getByRole("button", { name: "بررسی پاسخ‌ها", exact: true })
    .click();
  await expect(lesson.getByRole("status")).toContainText("پاسخ درست: ۲ از ۲");
  await expect(training).toContainText("پاسخ‌ها و پیشرفت ذخیره نمی‌شوند");
  expect(generated).toBe(0);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth + 1,
    ),
  ).toBe(true);
});
