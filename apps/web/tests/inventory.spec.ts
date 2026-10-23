import { test, expect } from "@playwright/test";

test("inventory draft requires explicit posting and derives stock", async ({
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
  const suffix = Date.now().toString();
  async function create(path: string, data: object) {
    const response = await page.request.post(`/api/backend/${path}`, {
      headers: {
        "Idempotency-Key": crypto.randomUUID(),
        Origin: "http://127.0.0.1:3000",
      },
      data,
    });
    expect(response.status(), await response.text()).toBe(201);
    return response.json();
  }
  const category = await create("catalog-references", {
    kind: "category",
    code: "inv" + suffix,
    name: "گروه " + suffix,
  });
  const product = await create("products", {
    sku: "inv" + suffix,
    name: "کالا " + suffix,
    category_id: category.id,
    unit: "kg",
    attributes: {},
  });
  const warehouse = await create("warehouses", {
    code: "inv" + suffix,
    name: "انبار " + suffix,
    city: "تهران",
    address: "آزمون",
  });
  const location = await create("locations", {
    warehouse_id: warehouse.id,
    code: "hall",
    name: "سالن " + suffix,
    kind: "hall",
  });
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "عملیات و موجودی انبار", exact: true })
    .click();
  await page.getByRole("button", { name: "lot و مالکیت", exact: true }).click();
  await page.getByLabel("کد lot").fill("LOT-" + suffix);
  await page.getByLabel("کالای lot").selectOption(product.id);
  await page.getByRole("button", { name: "ثبت lot", exact: true }).click();
  await expect(
    page.getByRole("row").filter({ hasText: "LOT-" + suffix }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "پیش‌نویس و گردش‌ها", exact: true })
    .click();
  await page.getByLabel("lot عملیات").selectOption({
    label: "LOT-" + suffix + " · کالا " + suffix + " · کالای شرکت",
  });
  await page.getByLabel("مقدار عملیات").fill("۱۲٫۵۰۰");
  await page.getByLabel("مکان مقصد").selectOption(location.id);
  await page.getByLabel("مرجع عملیات").fill("رسید " + suffix);
  await page.getByRole("button", { name: "ثبت پیش‌نویس", exact: true }).click();
  const row = page.getByRole("row").filter({ hasText: "رسید " + suffix });
  await expect(row).toContainText("پیش‌نویس");
  const lots = await (
    await page.request.get("/api/backend/inventory/lots?limit=100")
  ).json();
  const lot = lots.items.find(
    (item: { code: string }) => item.code === "LOT-" + suffix,
  );
  expect(
    (
      await (
        await page.request.get(
          `/api/backend/inventory/balances?lot_id=${lot.id}`,
        )
      ).json()
    ).total,
  ).toBe(0);
  await row.getByRole("button", { name: "ثبت نهایی", exact: true }).click();
  const dialog = page.getByRole("alertdialog");
  await expect(dialog).toContainText("کالای شرکت");
  await dialog
    .getByRole("button", { name: "تأیید ثبت نهایی", exact: true })
    .click();
  await expect(row).toContainText("ثبت نهایی");
  await expect(dialog).toHaveCount(0);
  const balances = await (
    await page.request.get(`/api/backend/inventory/balances?lot_id=${lot.id}`)
  ).json();
  expect(balances.items[0].available).toBe("12.500");
  await page
    .getByRole("button", { name: "موجودی محاسبه‌شده", exact: true })
    .click();
  await expect(
    page.getByRole("row").filter({ hasText: "LOT-" + suffix }),
  ).toContainText("کالای شرکت");
});
