import { test, expect } from "@playwright/test";

function pdf(value: string) {
  const stream = `BT /F1 18 Tf 40 750 Td (Invoice number: ${value}) Tj ET`;
  const objects = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    `<< /Length ${Buffer.byteLength(stream)} >>\nstream\n${stream}\nendstream`,
  ];
  let body = "%PDF-1.4\n";
  const offsets: number[] = [];
  objects.forEach((o, i) => {
    offsets.push(Buffer.byteLength(body));
    body += `${i + 1} 0 obj\n${o}\nendobj\n`;
  });
  const xref = Buffer.byteLength(body);
  body += `xref\n0 6\n0000000000 65535 f \n${offsets.map((o) => `${o.toString().padStart(10, "0")} 00000 n \n`).join("")}trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF`;
  return Buffer.from(body);
}

test("invoice file intake, human correction and immutable history have no business posting", async ({
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
  const get = async (path: string) =>
    (await page.request.get("/api/backend/" + path)).json();
  const counts = async () =>
    Promise.all(
      ["price-observations", "sales-drafts", "inventory/entries"].map(
        async (p) => (await get(p + "?limit=1")).total,
      ),
    );
  const before = await counts();
  await page
    .getByRole("button", { name: "دریافت و بررسی فاکتور", exact: true })
    .click();
  const original = "WEB" + Date.now();
  const buffer = pdf(original);
  await page.getByLabel("فایل فاکتور", { exact: true }).setInputFiles({
    name: "synthetic.pdf",
    mimeType: "application/pdf",
    buffer,
  });
  await page
    .getByRole("button", { name: "دریافت و استخراج محلی", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: /اصلاح و بررسی رونویسی/ }),
  ).toBeVisible();
  await expect(page.getByLabel("شماره فاکتور", { exact: true })).toHaveValue(
    original,
  );
  const list = await get("invoice-intakes?limit=100");
  const id = list.items.find(
    (r: { invoice_number: string }) => r.invoice_number === original,
  ).id;
  await page
    .getByLabel("شماره فاکتور", { exact: true })
    .fill("Human-" + original);
  await page.getByLabel("نام فروشنده", { exact: true }).fill("فروشندهٔ مصنوعی");
  await page.getByLabel("نام خریدار", { exact: true }).fill("خریدار مصنوعی");
  await page
    .getByRole("combobox", { name: "ارز درج‌شده", exact: true })
    .selectOption("IRR");
  await page.getByLabel("مبلغ کل", { exact: true }).fill("۲۷۱٫۵۹");
  await page.getByLabel("مبلغ مالیات", { exact: true }).fill("۲۴٫۶۹");
  await page
    .getByRole("button", { name: "افزودن ردیف دستی", exact: true })
    .click();
  for (const [label, value] of [
    ["شرح کالا", "ورق مصنوعی"],
    ["مقدار", "۲"],
    ["واحد درج‌شده", "kg"],
    ["فی درج‌شده", "۱۲۳٫۴۵"],
    ["مبلغ ردیف", "۲۴۶٫۹۰"],
  ])
    await page.getByLabel(label, { exact: true }).fill(value);
  await page
    .getByLabel("متن و داده‌ها را با اصل فاکتور تطبیق دادم", { exact: false })
    .check();
  await page
    .getByRole("button", { name: "ثبت بررسی انسانی متن", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText("نسخهٔ ۲ ذخیره شد");
  const current = await get(`invoice-intakes/${id}`);
  expect(current.fields.grand_total).toBe("271.59");
  expect(current.fields.lines[0].quantity).toBe("2");
  expect(current.fields.lines[0].unit_price).toBe("123.45");
  expect(current.status).toBe("reviewed");
  expect(current.financial_approval).toBe(false);
  expect(current.business_posted).toBe(false);
  expect(current.raw_text).toContain(original);
  await page.getByRole("button", { name: "نسخهٔ ۱", exact: true }).click();
  await expect(page.getByLabel("شماره فاکتور", { exact: true })).toHaveValue(
    original,
  );
  await expect(page.getByLabel("شماره فاکتور", { exact: true })).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "ذخیره اصلاحات", exact: true }),
  ).toHaveCount(0);
  await page
    .getByRole("button", { name: "بازخوانی نسخهٔ جاری", exact: true })
    .click();
  await expect(page.getByLabel("شماره فاکتور", { exact: true })).toHaveValue(
    "Human-" + original,
  );
  await page
    .getByLabel("متن اصلاح‌شده", { exact: true })
    .fill("بازبینی مجدد انسانی");
  await page
    .getByRole("button", { name: "ذخیره اصلاحات", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText("نسخهٔ ۳ ذخیره شد");
  expect((await get(`invoice-intakes/${id}`)).status).toBe("draft");
  expect(await counts()).toEqual(before);
  const headers = {
    Origin: "http://127.0.0.1:3000",
    "Content-Type": "application/pdf",
    "Idempotency-Key": crypto.randomUUID(),
  };
  const origin = await page.request.post(
    "/api/backend/invoice-intakes/extract",
    {
      headers: { ...headers, Origin: "https://unapproved.invalid" },
      data: buffer,
    },
  );
  expect(origin.status()).toBe(403);
  const big = await page.request.post("/api/backend/invoice-intakes/extract", {
    headers: { ...headers, "Content-Type": "image/png" },
    data: Buffer.alloc(5 * 1024 * 1024 + 1),
  });
  expect(big.status()).toBe(413);
  await page
    .getByRole("button", { name: "دریافت و استخراج محلی", exact: true })
    .click();
  await expect(
    page.getByRole("alert").filter({ hasText: "این فایل قبلاً ثبت شده است" }),
  ).toBeVisible();
  const pngBase64 = await page.evaluate((stamp) => {
    const canvas = document.createElement("canvas");
    canvas.width = 1200;
    canvas.height = 400;
    const ctx = canvas.getContext("2d")!;
    ctx.fillStyle = "white";
    ctx.fillRect(0, 0, 1200, 400);
    ctx.fillStyle = "black";
    ctx.font = "32px sans-serif";
    ctx.fillText("Invoice number: PNG" + stamp, 40, 80);
    ctx.fillText("Seller: Synthetic Steel", 40, 150);
    ctx.fillText("IRR", 40, 220);
    return canvas.toDataURL("image/png").split(",")[1];
  }, original);
  await page.getByLabel("فایل فاکتور", { exact: true }).setInputFiles({
    name: "synthetic.png",
    mimeType: "image/png",
    buffer: Buffer.from(pngBase64, "base64"),
  });
  await page
    .getByRole("button", { name: "دریافت و استخراج محلی", exact: true })
    .click();
  const preview = page.getByRole("img", {
    name: "اصل فاکتور انتخاب‌شده در همین مرورگر",
  });
  await expect(preview).toBeVisible();
  await expect
    .poll(() =>
      preview.evaluate((image) => (image as HTMLImageElement).naturalWidth),
    )
    .toBe(1200);
  expect(await counts()).toEqual(before);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});
