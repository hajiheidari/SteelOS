import { test, expect } from "@playwright/test";
test.use({ timezoneId: "Asia/Tehran" });

test("CRM manual follow-ups preserve local due date and overdue status without sending messages", async ({
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
  await expect(
    page.getByRole("heading", { name: "نمای کلی", exact: true }),
  ).toBeVisible();
  const stamp = Date.now().toString();
  const response = await page.request.post("/api/backend/parties", {
    headers: {
      Origin: "http://127.0.0.1:3000",
      "Idempotency-Key": crypto.randomUUID(),
    },
    data: {
      name: "طرف پیگیری " + stamp,
      kind: "legal_entity",
      roles: ["customer", "supplier"],
    },
  });
  expect(response.status()).toBe(201);
  const party = await response.json();
  await page
    .getByRole("button", {
      name: "پیگیری مشتریان و تأمین‌کنندگان",
      exact: true,
    })
    .click();
  await page.getByRole("button", { name: /ثبت جدید/ }).click();
  await page
    .getByLabel("موضوع پیگیری", { exact: false })
    .fill("پیگیری " + stamp);
  const picker = page.getByRole("combobox", { name: /مشتری یا تأمین‌کننده/ });
  await page
    .getByRole("textbox", { name: /^جست‌وجوی مشتری یا تأمین‌کننده/ })
    .fill(party.name);
  await picker.selectOption(party.id);
  await page
    .getByLabel("موعد پیگیری", { exact: false })
    .fill("2020-01-01T12:00");
  await page
    .getByLabel("یادداشت پیگیری", { exact: false })
    .fill("یادداشت داخلی آزمایشی");
  await page.getByRole("button", { name: "ذخیره", exact: true }).click();
  const row = page.getByRole("row").filter({ hasText: "پیگیری " + stamp });
  await expect(row).toContainText(party.name);
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "نمای کلی", exact: true })
    .click();
  await page.getByRole("button", { name: /پیگیری‌های عقب‌افتاده/ }).click();
  await expect(
    page.getByRole("combobox", { name: "نمایش پیگیری‌ها", exact: true }),
  ).toHaveValue("overdue");
  await expect(row).toBeVisible();
  const list = await (
    await page.request.get(
      "/api/backend/crm-follow-ups?q=" + encodeURIComponent("پیگیری " + stamp),
    )
  ).json();
  expect(list.total).toBe(1);
  expect(list.items[0].due_at).toBe("2020-01-01T08:30:00+00:00");
  await page
    .getByRole("combobox", { name: "نمایش پیگیری‌ها", exact: true })
    .selectOption("overdue");
  await expect(row).toBeVisible();
  await row.getByRole("button", { name: "ویرایش", exact: true }).click();
  await expect(page.getByLabel("موعد پیگیری", { exact: false })).toHaveValue(
    "2020-01-01T12:00",
  );
  await page
    .getByRole("combobox", { name: /وضعیت پیگیری/ })
    .selectOption("completed");
  await page.getByRole("button", { name: "ذخیره", exact: true }).click();
  await expect(row).toHaveCount(0);
  await page
    .getByRole("combobox", { name: "نمایش پیگیری‌ها", exact: true })
    .selectOption("completed");
  await expect(row).toContainText("انجام‌شده");
  const stored = await (
    await page.request.get("/api/backend/crm-follow-ups/" + list.items[0].id)
  ).json();
  expect(stored.status).toBe("completed");
  expect(stored.due_at).toBe(list.items[0].due_at);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});
