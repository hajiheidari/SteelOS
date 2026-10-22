import { test, expect } from "@playwright/test";

test("Persian workspace uses real API, secure cookie and responsive CRUD", async ({
  page,
  context,
}, info) => {
  await page.goto("/");
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await page.getByLabel("ایمیل", { exact: true }).fill("browser@example.test");
  await page
    .getByLabel("رمز عبور", { exact: true })
    .fill("Browser-test-only-123");
  await page
    .getByLabel("شناسه سازمان")
    .fill("00000000-0000-0000-0000-000000000001");
  await page.getByRole("button", { name: "ورود", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "نمای کلی", exact: true }),
  ).toBeVisible();
  const cookies = await context.cookies();
  expect(cookies.find((c) => c.name === "steelos_session")?.httpOnly).toBe(
    true,
  );
  expect(await page.evaluate(() => localStorage.length)).toBe(0);
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "مشتریان و تأمین‌کنندگان", exact: true })
    .click();
  await page.getByRole("button", { name: "+ ثبت جدید", exact: true }).click();
  const name = `آزمون ${info.project.name} ${Date.now()}`;
  await page.getByLabel("نام شخص یا شرکت").fill(name);
  await page.getByLabel("نوع شخص").selectOption("legal_entity");
  await page.getByLabel("تأمین‌کننده", { exact: true }).check();
  await page.getByRole("button", { name: "ذخیره", exact: true }).click();
  const row = page.getByRole("row").filter({ hasText: name });
  await expect(row).toBeVisible();
  await expect(row).toContainText("مشتری، تأمین‌کننده");
  await row.getByRole("button", { name: "ویرایش" }).click();
  await page.getByLabel("نام شخص یا شرکت").fill(name + " ویرایش");
  await page.getByRole("button", { name: "ذخیره", exact: true }).click();
  await expect(
    page.getByRole("row").filter({ hasText: name + " ویرایش" }),
  ).toBeVisible();
  await page.screenshot({
    path: `test-results/workspace-${info.project.name}.png`,
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page
    .getByRole("row")
    .filter({ hasText: name })
    .getByRole("button", { name: "حذف", exact: true })
    .click();
  await page.getByRole("button", { name: "تأیید حذف", exact: true }).click();
  await expect(page.getByRole("row").filter({ hasText: name })).toHaveCount(0);
  await page.getByRole("button", { name: "خروج", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "ورود به فضای کاری" }),
  ).toBeVisible();
});

test("browser proxy rejects cross-origin mutations", async ({ request }) => {
  const result = await request.post("/api/backend/auth/logout", {
    headers: { Origin: "https://example.test" },
  });
  expect(result.status()).toBe(403);
});

test("catalog, warehouse and approved pricing form workflow", async ({
  page,
}, info) => {
  const unique = `${info.project.name}-${Date.now()}`;
  await page.goto("/");
  await page.getByLabel("ایمیل", { exact: true }).fill("browser@example.test");
  await page
    .getByLabel("رمز عبور", { exact: true })
    .fill("Browser-test-only-123");
  await page
    .getByLabel("شناسه سازمان")
    .fill("00000000-0000-0000-0000-000000000001");
  await page.getByRole("button", { name: "ورود", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "نمای کلی", exact: true }),
  ).toBeVisible();
  async function newRecord(name: string) {
    await page
      .getByRole("navigation")
      .getByRole("button", { name, exact: true })
      .click();
    await page.getByRole("button", { name: "+ ثبت جدید", exact: true }).click();
  }
  async function save(name: string) {
    await page.getByRole("button", { name: "ذخیره", exact: true }).click();
    await expect(page.getByRole("row").filter({ hasText: name })).toBeVisible();
  }
  await newRecord("تعاریف کاتالوگ");
  await page.getByLabel("نوع تعریف").selectOption("category");
  await page.getByLabel("کد (لاتین)").fill("cat-" + unique);
  await page
    .getByLabel("نام", { exact: false })
    .filter({ visible: true })
    .first()
    .fill("گروه " + unique);
  await page.getByLabel("نام بعد جدید (لاتین)").fill("thickness");
  await page.getByRole("button", { name: "افزودن بعد", exact: true }).click();
  await page.getByLabel("الزامی", { exact: false }).check();
  await save("گروه " + unique);
  await newRecord("کالاها");
  await page.getByLabel("کد کالا (SKU)").fill("sku-" + unique);
  await page.getByLabel("نام کالا").fill("کالا " + unique);
  await page.getByLabel("گروه کالا").selectOption({ label: "گروه " + unique });
  await page.getByLabel("مقدار thickness").fill("2.000");
  await page.getByRole("combobox", { name: /^واحد \*/ }).selectOption("kg");
  await save("کالا " + unique);
  await newRecord("انبارها");
  await page.getByLabel("کد انبار (لاتین)").fill("wh-" + unique);
  await page.getByLabel("نام انبار").fill("انبار " + unique);
  await page.getByLabel("شهر").fill("تهران");
  await page.getByLabel("نشانی").fill("نشانی آزمایشی");
  await save("انبار " + unique);
  await newRecord("مکان‌های انبار");
  await page
    .getByRole("combobox", { name: /^انبار \*/ })
    .selectOption({ label: "انبار " + unique });
  await page.getByLabel("کد مکان (لاتین)").fill("hall");
  await page.getByLabel("نام مکان").fill("سالن " + unique);
  await save("سالن " + unique);
  await newRecord("منابع قیمت");
  await page.getByLabel("کد منبع (لاتین)").fill("source-" + unique);
  await page.getByLabel("نام منبع").fill("منبع " + unique);
  await page.getByRole("combobox", { name: /^نوع \*/ }).selectOption("manual");
  await page.getByLabel("منشأ و مجوز استفاده").fill("مجوز محلی آزمایشی");
  await page.getByLabel("منبع مجاز است").check();
  await save("منبع " + unique);
  await newRecord("مشاهدات قیمت");
  await page
    .getByRole("combobox", { name: /^کالا \*/ })
    .selectOption({ label: "کالا " + unique });
  await page.getByLabel("منبع قیمت").selectOption({ label: "منبع " + unique });
  await page.getByLabel("قیمت واحد").fill("123456.123456");
  await page.getByLabel("ارز").selectOption("IRR");
  await page.getByRole("combobox", { name: /^واحد \*/ }).selectOption("kg");
  await page
    .getByLabel("زمان مشاهده")
    .fill(new Date(Date.now() - 60000).toISOString().slice(0, 16));
  await page
    .getByLabel("معتبر تا")
    .fill(new Date(Date.now() + 3600000).toISOString().slice(0, 16));
  await page.getByLabel("محل تحویل").fill("تهران");
  await page.getByLabel("شرایط تحویل").fill("تحویل درب انبار");
  await page.getByLabel("مرجع این مشاهده").fill("ثبت آزمایشی مرورگر");
  await save("کالا " + unique);
  const observation = page
    .getByRole("row")
    .filter({ hasText: "کالا " + unique });
  await expect(observation).toContainText("در انتظار بررسی");
  await observation.getByRole("button", { name: "تأیید", exact: true }).click();
  await expect(observation).toContainText("تأیید شده");
  await page.getByRole("combobox", { name: /^نمایش/ }).selectOption("approved");
  await expect(observation).toBeVisible();
});
