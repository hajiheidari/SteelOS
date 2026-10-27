import { test, expect } from "@playwright/test";

test("catalog and identifier pages search registered aliases through real APIs", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("ایمیل", { exact: true }).fill("browser@example.test");
  await page.getByLabel("رمز عبور", { exact: true }).fill("Browser-test-only-123");
  await page.getByLabel("شناسه سازمان").fill("00000000-0000-0000-0000-000000000001");
  await page.getByRole("button", { name: "ورود", exact: true }).click();
  await expect(page.getByRole("heading", { name: "نمای کلی", exact: true })).toBeVisible();
  const stamp = Date.now().toString();
  const alias = "ALIAS%_\\" + stamp;
  const sku = "IDENTIFIER-" + stamp;
  async function create(path: string, data: object) {
    const response = await page.request.post("/api/backend/" + path, {
      headers: { Origin: "http://127.0.0.1:3000", "Idempotency-Key": crypto.randomUUID() },
      data,
    });
    expect(response.status(), await response.text()).toBe(201);
    return response.json();
  }
  const category = await create("catalog-references", {
    kind: "category", code: "ident-" + stamp, name: "گروه شناسه " + stamp,
    attribute_rules: { thickness: { unit: "mm", required: true } },
  });
  const product = await create("products", {
    category_id: category.id, sku, name: "محصول شناسه " + stamp, unit: "kg",
    attributes: { thickness: { value: "2", unit: "mm" } },
  });
  await create("products", {
    category_id: category.id, sku: "UNRELATED-" + stamp, name: "محصول دیگر " + stamp, unit: "kg",
    attributes: { thickness: { value: "3", unit: "mm" } },
  });
  for (const kind of ["barcode", "vendor"]) {
    await create("product-identifiers", { product_id: product.id, kind, value: alias });
  }
  await create("product-identifiers", { product_id: product.id, kind: "other", value: "unrelated-" + stamp });
  await page.getByRole("navigation").getByRole("button", { name: "کالاها", exact: true }).click();
  await page.getByLabel("جستجو", { exact: true }).fill(alias.toLowerCase());
  await page.getByRole("button", { name: "جستجو", exact: true }).click();
  await expect(page.getByRole("row").filter({ hasText: sku })).toHaveCount(1);
  await expect(page.getByText("۱ رکورد", { exact: true })).toBeVisible();
  await page.getByRole("navigation").getByRole("button", { name: "شناسه‌های کالا", exact: true }).click();
  await page.getByLabel("جستجو", { exact: true }).fill(alias.toLowerCase());
  await page.getByRole("button", { name: "جستجو", exact: true }).click();
  await expect(page.getByRole("row").filter({ hasText: alias })).toHaveCount(2);
  await expect(page.getByText("۲ رکورد", { exact: true })).toBeVisible();
  await expect(page.getByRole("row").filter({ hasText: "unrelated-" + stamp })).toHaveCount(0);
});
