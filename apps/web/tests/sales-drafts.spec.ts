import { test, expect } from "@playwright/test";

test("internal sales draft preserves exact estimates and revisions without stock effects", async ({
  page,
}) => {
  test.setTimeout(90_000);
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
  const headers = {
    Origin: "http://127.0.0.1:3000",
    "Idempotency-Key": crypto.randomUUID(),
  };
  async function create(path: string, data: object) {
    const response = await page.request.post("/api/backend/" + path, {
      headers: { ...headers, "Idempotency-Key": crypto.randomUUID() },
      data,
    });
    expect(response.status(), await response.text()).toBe(201);
    return response.json();
  }
  const category = await create("catalog-references", {
    kind: "category",
    code: "sale-" + stamp,
    name: "گروه فروش " + stamp,
  });
  const product = await create("products", {
    sku: "sale-" + stamp,
    name: "کالای فروش " + stamp,
    category_id: category.id,
    unit: "kg",
    attributes: {},
  });
  const customer = await create("parties", {
    name: "مشتری سند " + stamp,
    kind: "legal_entity",
    roles: ["customer", "supplier"],
  });
  const source = await create("price-sources", {
    code: "sale-" + stamp,
    name: "منبع سند " + stamp,
    kind: "manual",
    approved: true,
    provenance: "منبع آزمایشی مجاز",
  });
  const data = {
    product_id: product.id,
    source_id: source.id,
    amount: "123456.123456",
    currency: "IRR",
    unit: "kg",
    observed_at: new Date(Date.now() - 60_000).toISOString(),
    valid_until: new Date(Date.now() + 3600_000).toISOString(),
    delivery_location: "تهران",
    delivery_terms: "درب انبار",
    tax_included: false,
    provenance: "قیمت قابل ردگیری",
  };
  const price = await create("price-observations", data);
  const pending = await create("price-observations", data);
  expect(
    (
      await page.request.post(
        `/api/backend/price-observations/${price.id}/decision`,
        { headers, data: { status: "approved" } },
      )
    ).ok(),
  ).toBeTruthy();
  const beforeStock = (
    await (
      await page.request.get("/api/backend/inventory/entries?limit=1")
    ).json()
  ).total;
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "پیش‌نویس فروش", exact: true })
    .click();
  await page
    .getByRole("button", { name: "پیش‌نویس فروش جدید", exact: true })
    .click();
  await page.getByLabel("کد سند", { exact: true }).fill("Q-" + stamp);
  await page.getByLabel("مشتری سند", { exact: true }).selectOption(customer.id);
  await page.getByLabel("یادداشت سند", { exact: true }).fill("یادداشت اولیه");
  await page
    .getByLabel("کالای ردیف 1", { exact: true })
    .selectOption(product.id);
  const priceSelect = page.getByLabel("قیمت ردیف 1", { exact: true });
  await page
    .getByRole("combobox", { name: "ارز سند", exact: true })
    .selectOption("IRT");
  await expect(
    page.getByText("این ارز فقط برای برآورد داخلی است", { exact: false }),
  ).toBeVisible();
  await page
    .getByRole("combobox", { name: "ارز سند", exact: true })
    .selectOption("IRR");
  await expect(
    page.getByText("این ارز فقط برای برآورد داخلی است", { exact: false }),
  ).toHaveCount(0);
  await priceSelect.selectOption(price.id);
  await expect(
    priceSelect.locator(`option[value="${pending.id}"]`),
  ).toHaveCount(0);
  await page.getByLabel("مقدار ردیف 1", { exact: true }).fill("۲٫۱۲۳");
  let writes = 0;
  page.on("request", (request) => {
    if (request.method() === "POST" && request.url().endsWith("/sales-drafts"))
      writes++;
  });
  const searchResponse = page.waitForResponse(
    (response) =>
      new URL(response.url()).searchParams.get("q") === customer.name,
  );
  await page
    .getByLabel("جست‌وجوی مشتری سند", { exact: true })
    .fill(customer.name);
  await page.getByLabel("جست‌وجوی مشتری سند", { exact: true }).press("Enter");
  await searchResponse;
  expect(writes).toBe(0);
  const creation = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      response.url().endsWith("/sales-drafts"),
  );
  await page
    .getByRole("button", { name: "ذخیره پیش‌نویس فروش", exact: true })
    .click();
  const createdResponse = await creation;
  expect(createdResponse.status()).toBe(201);
  const draft = await createdResponse.json();
  expect(draft.estimated_total).toBe("262097.350097088");
  expect(draft.financial_approval).toBe(false);
  expect(draft.tax_rate_percent).toBe("10.000000");
  expect(draft.subtotal).toBe("262097.35");
  expect(draft.tax_total).toBe("26209.74");
  expect(draft.grand_total).toBe("288307.09");
  expect(draft.invoice_policy).toEqual({
    version: "iran-invoice-v3",
    currency: "IRR",
    rounding: "half_up",
    decimal_places: 2,
    calculation: "per_line",
    currency_matches: true,
    tax_workflow: "exclusive",
  });
  const row = page.getByRole("row").filter({ hasText: "Q-" + stamp });
  await expect(row).toContainText("پیش‌نویس داخلی");
  await page
    .getByLabel("یادداشت بازبینی", { exact: true })
    .fill("بازبینی نسخه اول");
  await page
    .getByRole("button", { name: "ثبت بازبینی داخلی", exact: true })
    .click();
  const acceptedReview = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      response.url().endsWith(`/sales-drafts/${draft.id}/review`),
  );
  await page
    .getByRole("alertdialog")
    .getByRole("button", { name: "تأیید ثبت بازبینی", exact: true })
    .click();
  expect((await acceptedReview).status()).toBe(201);
  await expect(
    page.getByText("نتیجهٔ این نسخه: پذیرفته‌شدهٔ داخلی", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "ویرایش سند", exact: true }).click();
  await page.getByLabel("مقدار ردیف 1", { exact: true }).fill("۳");
  await page
    .getByLabel("درصد مالیات بر ارزش افزوده سند", { exact: true })
    .fill("۹٫۵");
  await page.getByLabel("یادداشت سند", { exact: true }).fill("یادداشت جدید");
  const update = page.waitForResponse(
    (response) =>
      response.request().method() === "PUT" &&
      response.url().endsWith("/sales-drafts/" + draft.id),
  );
  await page
    .getByRole("button", { name: "ذخیره پیش‌نویس فروش", exact: true })
    .click();
  const updated = await update;
  expect(updated.ok()).toBeTruthy();
  const newVersion = await updated.json();
  expect(newVersion.internal_review).toBeNull();
  expect(newVersion.internal_review_usable).toBe(false);
  expect(newVersion.estimated_total).toBe("370368.370368000");
  expect(newVersion.tax_rate_percent).toBe("9.500000");
  expect(newVersion.tax_total).toBe("35185.00");
  expect(newVersion.grand_total).toBe("405553.37");
  await page.getByRole("button", { name: "نمایش نسخه ۱", exact: true }).click();
  await expect(page.getByText("یادداشت اولیه", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("button", { name: "ویرایش سند", exact: true }),
  ).toHaveCount(0);
  await page
    .getByRole("button", { name: "دریافت آخرین نسخه", exact: true })
    .click();
  await expect(page.getByText("یادداشت جدید", { exact: true })).toBeVisible();
  expect(
    (
      await page.request.put("/api/backend/price-sources/" + source.id, {
        headers,
        data: {
          code: source.code,
          name: source.name,
          kind: source.kind,
          provenance: source.provenance,
          approved: false,
        },
      })
    ).ok(),
  ).toBeTruthy();
  await page
    .getByRole("button", { name: "دریافت آخرین نسخه", exact: true })
    .click();
  await expect(
    page.getByText(
      "قیمت یا وضعیت مشتری نیاز به بازبینی دارد. این سند تأیید مالی ندارد.",
      { exact: true },
    ),
  ).toBeVisible();
  await page
    .getByRole("combobox", { name: "نتیجهٔ بازبینی", exact: true })
    .selectOption("rejected");
  await page
    .getByLabel("یادداشت بازبینی", { exact: true })
    .fill("منبع نیاز به بررسی دارد");
  await page
    .getByRole("button", { name: "ثبت بازبینی داخلی", exact: true })
    .click();
  const rejectedReview = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      response.url().endsWith(`/sales-drafts/${draft.id}/review`),
  );
  await page
    .getByRole("alertdialog")
    .getByRole("button", { name: "تأیید ثبت بازبینی", exact: true })
    .click();
  expect((await rejectedReview).status()).toBe(201);
  await expect(
    page.getByText("نتیجهٔ این نسخه: نیازمند اصلاح", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "لغو سند", exact: true }).click();
  const cancel = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      response.url().endsWith(`/sales-drafts/${draft.id}/cancel`),
  );
  await page
    .getByRole("alertdialog")
    .getByRole("button", { name: "تأیید لغو", exact: true })
    .click();
  expect((await cancel).ok()).toBeTruthy();
  await expect(row).toContainText("لغو شده");
  expect(
    (
      await (
        await page.request.get("/api/backend/inventory/entries?limit=1")
      ).json()
    ).total,
  ).toBe(beforeStock);
  expect(
    (
      await (
        await page.request.get(
          `/api/backend/sales-drafts/${draft.id}/revisions?limit=25`,
        )
      ).json()
    ).total,
  ).toBe(3);
});
