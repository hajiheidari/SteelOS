import { test, expect } from "@playwright/test";

test("read-only sales assistant displays grounded API prices and unsupported intent", async ({
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
  const name = "کالای دستیار " + stamp;
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
    name,
    code: "ai-" + stamp,
    attribute_rules: {
      thickness: { unit: "mm", required: true },
      width: { unit: "mm", required: true },
    },
  });
  const product = await create("products", {
    category_id: category.id,
    sku: "AI-" + stamp,
    name,
    unit: "kg",
    attributes: {
      thickness: { value: "2", unit: "mm" },
      width: { value: "1200", unit: "mm" },
    },
  });
  await create("products", {
    category_id: category.id,
    sku: "NOMATCH-" + stamp,
    name,
    unit: "kg",
    attributes: {
      thickness: { value: "3", unit: "mm" },
      width: { value: "1200", unit: "mm" },
    },
  });
  const source = await create("price-sources", {
    code: "ai-" + stamp,
    name: "منبع دستیار " + stamp,
    kind: "manual",
    approved: true,
    provenance: "آزمایش مجاز",
  });
  const price = await create("price-observations", {
    source_id: source.id,
    product_id: product.id,
    amount: "987654.123456",
    currency: "IRR",
    unit: "kg",
    observed_at: new Date(Date.now() - 60000).toISOString(),
    valid_until: new Date(Date.now() + 3600000).toISOString(),
    delivery_location: "تهران",
    delivery_terms: "درب انبار",
    tax_included: false,
    provenance: "شاهد قیمت دستیار",
  });
  expect(
    (
      await page.request.post(
        `/api/backend/price-observations/${price.id}/decision`,
        { headers, data: { status: "approved" } },
      )
    ).ok(),
  ).toBeTruthy();
  const before = (
    await (await page.request.get("/api/backend/sales-drafts?limit=1")).json()
  ).total;
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "دستیار فروش", exact: true })
    .click();
  const submit = page.getByRole("button", {
    name: "پرسیدن از دستیار",
    exact: true,
  });
  await expect(submit).toBeEnabled();
  await page
    .getByLabel("سؤال فروش", { exact: true })
    .fill(name + " ضخامت۲mm عرض۱٫۲m");
  const answerResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/sales-assistant/query") &&
      response.request().method() === "POST",
  );
  await submit.click();
  const response = await answerResponse;
  expect(response.status()).toBe(200);
  const answer = await response.json();
  expect(answer.read_only).toBe(true);
  expect(answer.financial_approval).toBe(false);
  expect(answer.product_total).toBe(1);
  expect(answer.dimensions).toEqual({
    thickness: { value: "2", unit: "mm" },
    width: { value: "1.2", unit: "m" },
  });
  expect(answer.needs_clarification).toBe(false);
  expect(answer.products[0].prices[0].amount).toBe("987654.123456");
  const result = page.getByRole("region", { name: "نتیجهٔ دستیار فروش" });
  await expect(
    result.getByRole("heading", { name: name + " · AI-" + stamp, exact: true }),
  ).toBeVisible();
  await expect(
    result.getByText("۹۸۷۶۵۴.۱۲۳۴۵۶ ریال / کیلوگرم", { exact: true }),
  ).toBeVisible();
  await expect(
    result.getByText("شناسهٔ شاهد قیمت:", { exact: false }),
  ).toContainText(price.id);
  await expect(result.getByText("منبع:", { exact: false })).toContainText(
    source.name,
  );
  await expect(
    result.getByText("مشخصات جست‌وجو:", { exact: false }),
  ).toContainText("عرض");
  await expect(
    result.getByText("مشخصات کالا:", { exact: false }),
  ).toContainText("۱۲۰۰");
  await page.getByLabel("سؤال فروش", { exact: true }).fill(name + " ضخامت۲");
  await submit.click();
  await expect(
    page.getByText("عدد و واحد ابعاد را دقیق بنویسید", { exact: false }),
  ).toBeVisible();
  await expect(result.getByRole("heading", { level: 3 })).toHaveCount(0);
  await page.getByLabel("سؤال فروش", { exact: true }).fill("سلام");
  await submit.click();
  await expect(
    page.getByText(
      "در این مرحله فقط جست‌وجوی کالا و قیمت پشتیبانی می‌شود؛ نام کالا را در سؤال مشخص کنید.",
      { exact: true },
    ),
  ).toBeVisible();
  expect(
    (await (await page.request.get("/api/backend/sales-drafts?limit=1")).json())
      .total,
  ).toBe(before);
});
