import { test, expect } from "@playwright/test";

test("inventory lifecycle enforces posting, reservations, transfers and reversal", async ({
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
  const otherWarehouse = await create("warehouses", {
    code: "dest" + suffix,
    name: "مقصد " + suffix,
    city: "تهران",
    address: "آزمون",
  });
  const destination = await create("locations", {
    warehouse_id: otherWarehouse.id,
    code: "hall",
    name: "مقصد " + suffix,
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
  await expect(
    row.getByRole("cell", { name: "ثبت نهایی", exact: true }),
  ).toBeVisible();
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
  await page
    .getByRole("button", { name: "پیش‌نویس و گردش‌ها", exact: true })
    .click();
  async function operation(
    kind: string,
    quantity: string,
    reference: string,
    options: {
      from?: string;
      to?: string;
      reservation?: string;
      reverses?: string;
    } = {},
  ) {
    await page.getByLabel("نوع عملیات").selectOption(kind);
    await page.getByLabel("lot عملیات").selectOption(lot.id);
    if (kind !== "reversal")
      await page.getByLabel("مقدار عملیات").fill(quantity);
    if (options.from)
      await page.getByLabel("مکان مبدأ").selectOption(options.from);
    if (options.to) await page.getByLabel("مکان مقصد").selectOption(options.to);
    if (options.reservation)
      await page.getByLabel("رزرو مرتبط").selectOption(options.reservation);
    if (options.reverses)
      await page
        .getByLabel("گردش اصلی برای برگشت")
        .selectOption(options.reverses);
    await page.getByLabel("مرجع عملیات").fill(reference + suffix);
    await page
      .getByRole("button", { name: "ثبت پیش‌نویس", exact: true })
      .click();
    const result = page
      .getByRole("row")
      .filter({ hasText: reference + suffix });
    await expect(
      result.getByRole("cell", { name: "پیش‌نویس", exact: true }),
    ).toBeVisible();
    await result
      .getByRole("button", { name: "ثبت نهایی", exact: true })
      .click();
    await page
      .getByRole("alertdialog")
      .getByRole("button", { name: "تأیید ثبت نهایی", exact: true })
      .click();
    return result;
  }
  async function posted(result: ReturnType<typeof page.getByRole>) {
    await expect(
      result.getByRole("cell", { name: "ثبت نهایی", exact: true }),
    ).toBeVisible();
    await expect(page.getByRole("alertdialog")).toHaveCount(0);
  }
  async function position(locationId: string) {
    const response = await page.request.get(
      `/api/backend/inventory/balances?lot_id=${lot.id}`,
    );
    expect(response.ok()).toBeTruthy();
    return (await response.json()).items.find(
      (item: { location_id: string }) => item.location_id === locationId,
    );
  }
  await posted(await operation("reserve", "۴", "رزرو ", { from: location.id }));
  expect((await position(location.id)).available).toBe("8.500");
  const reservations = await (
    await page.request.get(
      `/api/backend/inventory/reservations?lot_id=${lot.id}`,
    )
  ).json();
  const reservation = reservations.items[0];
  await posted(
    await operation("fulfill", "۱٫۵", "تحویل ", {
      reservation: reservation.id,
    }),
  );
  expect((await position(location.id)).on_hand).toBe("11.000");
  expect((await position(location.id)).reserved).toBe("2.500");
  await posted(
    await operation("release", "۲٫۵", "آزادسازی ", {
      reservation: reservation.id,
    }),
  );
  await posted(await operation("block", "۲", "مسدودی ", { from: location.id }));
  expect((await position(location.id)).available).toBe("9.000");
  await posted(
    await operation("unblock", "۲", "رفع مسدودی ", { from: location.id }),
  );
  await posted(
    await operation("transfer", "۳", "انتقال ", {
      from: location.id,
      to: destination.id,
    }),
  );
  expect((await position(location.id)).on_hand).toBe("8.000");
  expect((await position(destination.id)).on_hand).toBe("3.000");
  const drafts = await (
    await page.request.get(`/api/backend/inventory/drafts?lot_id=${lot.id}`)
  ).json();
  const transfer = drafts.items.find(
    (item: { reference: string }) => item.reference === "انتقال " + suffix,
  );
  await posted(
    await operation("reversal", "", "برگشت ", { reverses: transfer.id }),
  );
  expect((await position(location.id)).on_hand).toBe("11.000");
  expect((await position(destination.id)).on_hand).toBe("0.000");
  await posted(
    await operation("dispatch", "۱", "خروج ", { from: location.id }),
  );
  const invalid = await operation("dispatch", "۹۹", "خروج نامعتبر ", {
    from: location.id,
  });
  await expect(page.getByRole("alertdialog")).toContainText(
    "موجودی قابل استفاده کافی نیست",
  );
  await page
    .getByRole("alertdialog")
    .getByRole("button", { name: "انصراف", exact: true })
    .click();
  await invalid
    .getByRole("button", { name: "رد پیش‌نویس", exact: true })
    .click();
  await page
    .getByRole("alertdialog")
    .getByRole("button", { name: "تأیید رد پیش‌نویس", exact: true })
    .click();
  await expect(
    invalid.getByRole("cell", { name: "رد شده", exact: true }),
  ).toBeVisible();
  expect((await position(location.id)).available).toBe("10.000");
});
