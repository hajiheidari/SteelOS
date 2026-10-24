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
    const saved = page.waitForResponse(
      (response) =>
        response.url().includes("/api/backend/") &&
        ["POST", "PUT"].includes(response.request().method()),
    );
    await page.getByRole("button", { name: "ذخیره", exact: true }).click();
    expect((await saved).ok()).toBeTruthy();
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
  await page.getByLabel("نام بعد جدید (لاتین)").fill("width");
  await page.getByRole("button", { name: "افزودن بعد", exact: true }).click();
  await save("گروه " + unique);
  await newRecord("کالاها");
  await page.getByLabel("کد کالا (SKU)").fill("sku-" + unique);
  await page.getByLabel("نام کالا").fill("کالا " + unique);
  await page
    .getByRole("combobox", { name: /^گروه کالا/ })
    .selectOption({ label: "گروه " + unique });
  await page.getByLabel("مقدار thickness").fill("۲٫۰۰۰");
  await expect(page.getByLabel("مقدار thickness")).toHaveAttribute(
    "required",
    "",
  );
  await expect(page.getByLabel("مقدار width")).not.toHaveAttribute(
    "required",
    "",
  );
  await expect(page.getByLabel("واحد thickness")).toBeDisabled();
  await expect(page.getByLabel("واحد width")).toBeDisabled();
  await page.getByRole("combobox", { name: /^واحد \*/ }).selectOption("kg");
  await save("کالا " + unique);
  const productList = await (
    await page.request.get(
      "/api/backend/products?q=" + encodeURIComponent("کالا " + unique),
    )
  ).json();
  const product = productList.items[0];
  expect(product.attributes).toEqual({ thickness: { value: "2", unit: "mm" } });
  const productRow = page
    .getByRole("row")
    .filter({ hasText: "کالا " + unique });
  await productRow.getByRole("button", { name: "ویرایش", exact: true }).click();
  await expect(page.getByLabel("مقدار width")).toHaveValue("");
  await page.getByLabel("مقدار width").fill("۱٬۲۵۰٫۵");
  await save("کالا " + unique);
  const updatedProduct = await (
    await page.request.get("/api/backend/products/" + product.id)
  ).json();
  expect(updatedProduct.attributes.width).toEqual({
    value: "1250.5",
    unit: "mm",
  });
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
  await page
    .getByRole("combobox", { name: /^منبع قیمت/ })
    .selectOption({ label: "منبع " + unique });
  await page.getByLabel("قیمت واحد").fill("١٢٣٬٤٥٦٫۱۲۳۴۵۶");
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
  const prices = await (
    await page.request.get(
      "/api/backend/price-observations?product_id=" + product.id,
    )
  ).json();
  expect(prices.items[0].amount).toBe("123456.123456");
});

async function loginWorkspace(page: import("@playwright/test").Page) {
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
  await expect(page.locator(".stats .stat")).toHaveCount(4);
}

test("incorrect current password preserves the authenticated session", async ({
  page,
  context,
}) => {
  await loginWorkspace(page);
  const original = (await context.cookies()).find(
    (c) => c.name === "steelos_session",
  )!;
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "کاربران و تنظیمات", exact: true })
    .click();
  await page
    .getByLabel("رمز عبور فعلی", { exact: true })
    .fill("Incorrect-password-123");
  await page
    .getByLabel("رمز عبور جدید (حداقل ۱۲ نویسه)")
    .fill("Unused-new-password-123");
  await page
    .getByRole("button", { name: "تغییر رمز و خروج از همه نشست‌ها" })
    .click();
  await expect(
    page
      .getByRole("alert")
      .filter({ hasText: /رمز عبور فعلی درست نیست|نشست شما پایان یافته/ }),
  ).toHaveText("رمز عبور فعلی درست نیست.");
  expect(
    (await context.cookies()).find((c) => c.name === "steelos_session")?.value,
  ).toBe(original.value);
  expect((await page.request.get("/api/backend/auth/me")).status()).toBe(200);
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "نمای کلی", exact: true }),
  ).toBeVisible();
});

test("revoked session discards workspace and returns to login with a Persian message", async ({
  page,
  context,
}) => {
  await loginWorkspace(page);
  const cookies = await context.cookies();
  const revoked = await page.request.post("/api/backend/auth/logout", {
    headers: { Origin: "http://127.0.0.1:3000" },
  });
  expect(revoked.status()).toBe(200);
  // Simulate a tab retaining a token revoked by another client.
  await context.addCookies(cookies);
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "کالاها", exact: true })
    .click();
  await expect(page).toHaveURL(/session=expired/);
  await expect(
    page.getByRole("heading", { name: "ورود به فضای کاری" }),
  ).toBeVisible();
  await expect(
    page
      .getByRole("alert")
      .filter({ hasText: /رمز عبور فعلی درست نیست|نشست شما پایان یافته/ }),
  ).toHaveText("نشست شما پایان یافته است. دوباره وارد شوید.");
  await expect(page.getByRole("navigation")).toHaveCount(0);
  expect(
    (await context.cookies()).find((c) => c.name === "steelos_session"),
  ).toBeUndefined();
});

test("a delayed product response cannot overwrite a newer party page", async ({
  page,
}, info) => {
  await loginWorkspace(page);
  const name = `طرف تجاری ${info.project.name} ${Date.now()}`;
  const party = await page.request.post("/api/backend/parties", {
    headers: {
      Origin: "http://127.0.0.1:3000",
      "Idempotency-Key": crypto.randomUUID(),
    },
    data: { name, kind: "individual", roles: ["customer"] },
  });
  expect(party.status()).toBe(201);
  let release!: () => void;
  const delay = new Promise<void>((resolve) => {
    release = resolve;
  });
  let started = false;
  let finished!: () => void;
  const delivered = new Promise<void>((resolve) => {
    finished = resolve;
  });
  await page.route("**/api/backend/products?limit=25*", async (route) => {
    const response = await route.fetch();
    started = true;
    await delay;
    await route.fulfill({ response });
    finished();
  });
  try {
    await page
      .getByRole("navigation")
      .getByRole("button", { name: "کالاها", exact: true })
      .click();
    await expect.poll(() => started).toBe(true);
    await page
      .getByRole("navigation")
      .getByRole("button", { name: "مشتریان و تأمین‌کنندگان", exact: true })
      .click();
    await expect(page.getByRole("row").filter({ hasText: name })).toBeVisible();
    release();
    await delivered;
    // Let the browser render the response before inspecting the newer table.
    await page.evaluate(
      () =>
        new Promise<void>((resolve) =>
          requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
        ),
    );
    await expect(
      page.getByRole("heading", {
        name: "مشتریان و تأمین‌کنندگان",
        exact: true,
      }),
    ).toBeVisible();
    await expect(page.getByRole("row").filter({ hasText: name })).toBeVisible();
  } finally {
    release();
  }
});

test("catalog editor resolves a category beyond the first page without losing dimension rules", async ({
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
  async function create(path: string, data: object) {
    const response = await page.request.post("/api/backend/" + path, {
      headers: {
        Origin: "http://127.0.0.1:3000",
        "Idempotency-Key": crypto.randomUUID(),
      },
      data,
    });
    expect(response.status(), await response.text()).toBe(201);
    return response.json();
  }
  const category = await create("catalog-references", {
    kind: "category",
    code: "selected-" + stamp,
    name: "گروه قدیمی " + stamp,
    attribute_rules: {
      thickness: { unit: "mm", required: true },
      width: { unit: "mm", required: false },
    },
  });
  for (let index = 0; index < 27; index++)
    await create("catalog-references", {
      kind: "category",
      code: `page-${stamp}-${index}`,
      name: `گروه ${stamp}-${index}`,
    });
  const product = await create("products", {
    sku: "edit-" + stamp,
    name: "کالای قبلی " + stamp,
    category_id: category.id,
    unit: "kg",
    attributes: { thickness: { unit: "mm", value: "2" } },
  });
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "کالاها", exact: true })
    .click();
  const row = page.getByRole("row").filter({ hasText: product.name });
  await expect(row).toContainText(category.name);
  await row.getByRole("button", { name: "ویرایش", exact: true }).click();
  const select = page.getByRole("combobox", { name: /^گروه کالا/ });
  await expect(select).toHaveValue(category.id);
  await expect(page.getByLabel("مقدار thickness")).toHaveValue("2");
  await expect(page.getByLabel("مقدار thickness")).toHaveAttribute(
    "required",
    "",
  );
  await expect(page.getByLabel("واحد thickness")).toBeDisabled();
  await page.getByLabel("مقدار width").fill("۱۲۵۰٫۵");
  const saved = page.waitForResponse(
    (response) =>
      response.request().method() === "PUT" &&
      response.url().endsWith("/products/" + product.id),
  );
  await page.getByRole("button", { name: "ذخیره", exact: true }).click();
  expect((await saved).ok()).toBeTruthy();
  await expect(
    page.getByRole("heading", { name: "ویرایش رکورد", exact: true }),
  ).toHaveCount(0);
  const updated = await (
    await page.request.get("/api/backend/products/" + product.id)
  ).json();
  expect(updated.attributes.width).toEqual({ unit: "mm", value: "1250.5" });
  await page.getByRole("button", { name: "+ ثبت جدید", exact: true }).click();
  await page.getByLabel("کد کالا (SKU)").fill("new-" + stamp);
  await page.getByLabel("نام کالا").fill("کالای جدید " + stamp);
  await page
    .getByLabel("جست‌وجوی گروه کالا *", { exact: true })
    .fill(category.name);
  await select.selectOption(category.id);
  await page.getByLabel("مقدار thickness").fill("۳");
  await page.getByRole("combobox", { name: /^واحد \*/ }).selectOption("kg");
  const created = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      response.url().endsWith("/products"),
  );
  await page.getByRole("button", { name: "ذخیره", exact: true }).click();
  const response = await created;
  expect(response.status()).toBe(201);
  expect((await response.json()).attributes).toEqual({
    thickness: { unit: "mm", value: "3" },
  });
});

test("organization settings use searchable users and warehouse grants", async ({
  page,
}) => {
  await loginWorkspace(page);
  const stamp = Date.now().toString();
  const email = `member-${stamp}@example.test`;
  const warehouseResponse = await page.request.post("/api/backend/warehouses", {
    headers: {
      Origin: "http://127.0.0.1:3000",
      "Idempotency-Key": crypto.randomUUID(),
    },
    data: {
      code: "grant-" + stamp,
      name: "انبار دسترسی " + stamp,
      city: "تهران",
      address: "آزمون",
    },
  });
  expect(warehouseResponse.status()).toBe(201);
  const warehouse = await warehouseResponse.json();
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "کاربران و تنظیمات", exact: true })
    .click();
  await page.getByLabel("ایمیل کاربر جدید").fill(email);
  await page.getByLabel("رمز عبور اولیه").fill("Temporary-browser-only-123");
  await page
    .getByRole("combobox", { name: "نقش", exact: true })
    .selectOption("editor");
  const creation = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      response.url().endsWith("/organization/members"),
  );
  await page.getByRole("button", { name: "افزودن کاربر", exact: true }).click();
  expect((await creation).status()).toBe(201);
  const memberRow = page.getByRole("row").filter({ hasText: email });
  await expect(memberRow).toBeVisible();
  await page.getByLabel("جست‌وجوی کاربر", { exact: true }).fill(email);
  await page
    .getByLabel("کاربر", { exact: true })
    .selectOption({ label: email });
  await page.getByLabel("جست‌وجوی انبار", { exact: true }).fill(warehouse.name);
  await page.getByLabel("انبار", { exact: true }).selectOption(warehouse.id);
  const grantRequest = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      response.url().endsWith("/warehouse-access"),
  );
  await page.getByRole("button", { name: "ثبت دسترسی", exact: true }).click();
  expect((await grantRequest).status()).toBe(201);
  const grant = page
    .locator("p")
    .filter({ hasText: email })
    .filter({ hasText: warehouse.name });
  await expect(grant).toBeVisible();
  const revoked = page.waitForResponse(
    (response) =>
      response.request().method() === "DELETE" &&
      response.url().includes("/warehouse-access/"),
  );
  await grant.getByRole("button", { name: "لغو دسترسی", exact: true }).click();
  expect((await revoked).ok()).toBeTruthy();
  await expect(grant).toHaveCount(0);
});
