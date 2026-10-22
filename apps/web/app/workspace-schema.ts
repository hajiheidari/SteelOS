export type Row = Record<string, unknown> & { id: string };
export type Option = { value: string; label: string };
export type Field = {
  key: string;
  label: string;
  type?: string;
  options?: Option[];
  required?: boolean;
  default?: string;
};
export type Me = {
  email: string;
  role: string;
  organization: { id: string; name: string };
};
export const units = [
  { value: "kg", label: "کیلوگرم" },
  { value: "tonne", label: "تن" },
  { value: "piece", label: "عدد" },
  { value: "m", label: "متر" },
  { value: "m2", label: "متر مربع" },
];
export const kinds = [
  { value: "category", label: "گروه کالا" },
  { value: "manufacturer", label: "تولیدکننده" },
  { value: "grade", label: "گرید" },
  { value: "standard", label: "استاندارد" },
];
export const roles = [
  { value: "admin", label: "مدیر" },
  { value: "editor", label: "کارشناس" },
  { value: "viewer", label: "مشاهده‌گر" },
];
export const titles: Record<string, string> = {
  dashboard: "نمای کلی",
  products: "کالاها",
  "catalog-references": "تعاریف کاتالوگ",
  "product-identifiers": "شناسه‌های کالا",
  parties: "مشتریان و تأمین‌کنندگان",
  warehouses: "انبارها",
  locations: "مکان‌های انبار",
  "price-sources": "منابع قیمت",
  "price-observations": "مشاهدات قیمت",
  settings: "کاربران و تنظیمات",
};
export const translations: Record<string, string> = {
  pending: "در انتظار بررسی",
  approved: "تأیید شده",
  rejected: "رد شده",
  manual: "دستی",
  mock: "آزمایشی",
  individual: "شخص حقیقی",
  legal_entity: "شخص حقوقی",
  customer: "مشتری",
  supplier: "تأمین‌کننده",
  category: "گروه کالا",
  manufacturer: "تولیدکننده",
  grade: "گرید",
  standard: "استاندارد",
  admin: "مدیر",
  editor: "کارشناس",
  viewer: "مشاهده‌گر",
  kg: "کیلوگرم",
  tonne: "تن",
  piece: "عدد",
  m: "متر",
  m2: "متر مربع",
};
export const errorMessages: Record<number, string> = {
  401: "نشست معتبر نیست یا اطلاعات ورود نادرست است.",
  403: "مجوز انجام این کار را ندارید.",
  404: "رکورد پیدا نشد.",
  409: "رکورد تکراری است یا دادهٔ وابسته دارد.",
  422: "اطلاعات واردشده با قواعد سامانه سازگار نیست.",
  429: "تعداد تلاش‌ها زیاد است؛ ۱۵ دقیقه بعد تلاش کنید.",
  503: "ارتباط با پایگاه داده یا سرور برقرار نیست.",
};

export async function api(
  path: string,
  method = "GET",
  body?: unknown,
  key?: string,
) {
  const result = await fetch("/api/backend/" + path, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(key ? { "Idempotency-Key": key } : {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await result.json();
  if (!result.ok) {
    const details = data.error?.details
      ?.map((d: { location: string[] }) => d.location.slice(1).join("."))
      .join("، ");
    throw new Error(
      (errorMessages[result.status] || "عملیات ناموفق بود.") +
        (details ? ` (${details})` : ""),
    );
  }
  return data;
}
export function display(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "بله" : "خیر";
  if (Array.isArray(value)) return value.map(display).join("، ");
  const s = String(value);
  if (/^\d{4}-\d{2}-\d{2}T/.test(s))
    return new Intl.DateTimeFormat("fa-IR-u-ca-persian", {
      dateStyle: "medium",
      timeStyle: "short",
      timeZone: "Asia/Tehran",
    }).format(new Date(s));
  if (/^\d+(\.\d+)?$/.test(s))
    return s.replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[Number(d)]);
  return translations[s] || s;
}
export function getFields(
  page: string,
  refs: Row[],
  warehouses: Row[],
  products: Row[],
  sources: Row[],
  locations: Row[],
): Field[] {
  const opts = (rows: Row[]) =>
    rows.map((r) => ({ value: r.id, label: String(r.name || r.code) }));
  switch (page) {
    case "catalog-references":
      return [
        { key: "kind", label: "نوع تعریف", options: kinds },
        { key: "code", label: "کد (لاتین)" },
        { key: "name", label: "نام" },
        {
          key: "attribute_rules",
          label: "قواعد ابعاد",
          type: "rules",
          required: false,
        },
      ];
    case "products":
      return [
        { key: "sku", label: "کد کالا (SKU)" },
        { key: "name", label: "نام کالا" },
        ...["category", "manufacturer", "grade", "standard"].map((kind) => ({
          key: kind + "_id",
          label: kinds.find((k) => k.value === kind)!.label,
          options: opts(refs.filter((r) => r.kind === kind)),
          required: kind === "category",
        })),
        { key: "unit", label: "واحد", options: units },
        { key: "attributes", label: "ابعاد فنی", type: "dimensions" },
        { key: "active", label: "فعال", type: "checkbox" },
      ];
    case "product-identifiers":
      return [
        { key: "product_id", label: "کالا", options: opts(products) },
        { key: "kind", label: "نوع شناسه (لاتین)", default: "barcode" },
        { key: "value", label: "شناسه" },
      ];
    case "parties":
      return [
        { key: "name", label: "نام شخص یا شرکت" },
        {
          key: "kind",
          label: "نوع شخص",
          options: [
            { value: "individual", label: "حقیقی" },
            { value: "legal_entity", label: "حقوقی" },
          ],
        },
        {
          key: "registration_id",
          label: "شناسه ملی / شماره ثبت",
          required: false,
        },
        { key: "roles", label: "نقش‌ها", type: "roles" },
        {
          key: "contacts",
          label: "اطلاعات تماس",
          type: "contacts",
          required: false,
        },
        {
          key: "addresses",
          label: "نشانی‌ها",
          type: "addresses",
          required: false,
        },
        { key: "active", label: "فعال", type: "checkbox" },
      ];
    case "warehouses":
      return [
        { key: "code", label: "کد انبار (لاتین)" },
        { key: "name", label: "نام انبار" },
        { key: "city", label: "شهر" },
        { key: "address", label: "نشانی" },
        { key: "active", label: "فعال", type: "checkbox" },
      ];
    case "locations":
      return [
        { key: "warehouse_id", label: "انبار", options: opts(warehouses) },
        {
          key: "parent_id",
          label: "مکان والد",
          options: opts(locations),
          required: false,
        },
        { key: "code", label: "کد مکان (لاتین)" },
        { key: "name", label: "نام مکان" },
        { key: "kind", label: "نوع مکان (لاتین)", default: "hall" },
      ];
    case "price-sources":
      return [
        { key: "code", label: "کد منبع (لاتین)" },
        { key: "name", label: "نام منبع" },
        {
          key: "kind",
          label: "نوع",
          options: [
            { value: "manual", label: "دستی" },
            { value: "mock", label: "آزمایشی محلی" },
          ],
        },
        { key: "provenance", label: "منشأ و مجوز استفاده" },
        { key: "approved", label: "منبع مجاز است", type: "checkbox" },
      ];
    case "price-observations":
      return [
        { key: "product_id", label: "کالا", options: opts(products) },
        { key: "source_id", label: "منبع قیمت", options: opts(sources) },
        { key: "amount", label: "قیمت واحد", type: "decimal" },
        {
          key: "currency",
          label: "ارز",
          options: [
            { value: "IRR", label: "ریال" },
            { value: "IRT", label: "تومان" },
            { value: "USD", label: "دلار" },
            { value: "EUR", label: "یورو" },
          ],
        },
        { key: "unit", label: "واحد", options: units },
        {
          key: "observed_at",
          label: "زمان مشاهده (زمان محلی دستگاه)",
          type: "datetime-local",
        },
        {
          key: "valid_until",
          label: "معتبر تا (زمان محلی دستگاه)",
          type: "datetime-local",
        },
        { key: "delivery_location", label: "محل تحویل" },
        { key: "delivery_terms", label: "شرایط تحویل" },
        {
          key: "tax_included",
          label: "مالیات در قیمت لحاظ شده",
          type: "checkbox",
        },
        { key: "provenance", label: "مرجع این مشاهده" },
      ];
    default:
      return [];
  }
}
