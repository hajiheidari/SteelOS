"use client";
import { useEffect, useRef, useState } from "react";
import { api, display, type Row } from "./workspace-schema";

type Answer = Row & { products: (Row & { prices: Row[] })[] };
const currencies: Record<string, string> = {
  IRR: "ریال",
  IRT: "تومان",
  USD: "دلار",
  EUR: "یورو",
};

const dimensionLabels: Record<string, string> = {
  thickness: "ضخامت",
  width: "عرض",
  length: "طول",
  diameter: "قطر",
  height: "ارتفاع",
};
type Measurement = { value: string; unit: string };
type ComparisonOp = "gt" | "gte" | "lt" | "lte";
const comparisonLabels: Record<ComparisonOp, string> = {
  gt: "بیشتر از",
  gte: "بزرگ‌تر یا مساوی",
  lt: "کمتر از",
  lte: "کوچک‌تر یا مساوی",
};
type DimensionFilter =
  | Measurement
  | { min: Measurement; max: Measurement; min_inclusive?: boolean; max_inclusive?: boolean }
  | { op: ComparisonOp; bound: Measurement };
function measurement(value: Measurement) {
  return `${display(value.value)} ${value.unit === "none" ? "" : value.unit}`;
}
function Dimensions({ value, title }: { value: unknown; title: string }) {
  const entries = Object.entries(
    (value || {}) as Record<string, DimensionFilter>,
  );
  return entries.length ? (
    <p>
      {title}:{" "}
      {entries.map(([key, dimension], index) => (
        <span key={key}>
          {index > 0 && " · "}
          {dimensionLabels[key] || key}:{" "}
          <bdi>
            {"op" in dimension
              ? `${comparisonLabels[dimension.op]} ${measurement(dimension.bound)}`
              : "min" in dimension
              ? dimension.min_inclusive === false || dimension.max_inclusive === false
                ? `${dimension.min_inclusive === false ? "بیشتر از" : "حداقل"} ${measurement(dimension.min)} و ${dimension.max_inclusive === false ? "کمتر از" : "حداکثر"} ${measurement(dimension.max)}`
                : `از ${measurement(dimension.min)} تا ${measurement(dimension.max)} (شامل دو حد)`
              : measurement(dimension)}
          </bdi>
        </span>
      ))}
    </p>
  ) : null;
}

export function SalesAssistantWorkspace() {
  const [status, setStatus] = useState<Row | null>(null);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    void api("sales-assistant/status")
      .then((data) => {
        if (alive.current) setStatus(data);
      })
      .catch((e) => {
        if (alive.current) setError((e as Error).message);
      });
    return () => {
      alive.current = false;
    };
  }, []);
  return (
    <section className="card">
      <h2>دستیار جست‌وجوی فروش</h2>
      <p>
        نام کالا یا سؤال دربارهٔ قیمت را بنویسید. پاسخ از کالاها و قیمت‌های
        معتبر همین سازمان تهیه می‌شود؛ این دستیار فقط می‌خواند و سندی ثبت یا
        تأیید نمی‌کند.
      </p>
      {status && !status.configured && (
        <p className="info" role="status">
          مدل محلی هنوز تنظیم نشده است؛ مدیر سامانه باید اتصال را فعال کند.
        </p>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          setBusy(true);
          setError("");
          setAnswer(null);
          void api("sales-assistant/query", "POST", { question })
            .then((data) => {
              if (alive.current) setAnswer(data);
            })
            .catch((e) => {
              if (alive.current) setError((e as Error).message);
            })
            .finally(() => {
              if (alive.current) setBusy(false);
            });
        }}
      >
        <label htmlFor="sales-assistant-question">سؤال فروش</label>
        <textarea
          id="sales-assistant-question"
          required
          minLength={2}
          maxLength={1000}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          disabled={busy}
          placeholder="مثلاً: قیمت میلگرد چقدر است؟"
        />
        <button disabled={busy || !status?.configured}>
          {busy ? "در حال جست‌وجو…" : "پرسیدن از دستیار"}
        </button>
      </form>
      {answer && (
        <section aria-label="نتیجهٔ دستیار فروش">
          <p className="info">
            این پاسخ پیش‌فاکتور مشتری نیست. قیمت‌ها هنگام خواندن بررسی شده‌اند؛
            پیش از ثبت سند، اعتبار دوباره بررسی می‌شود.
          </p>
          <p>
            بازهٔ خواندن داده: {display(answer.retrieval_started_at)} تا{" "}
            {display(answer.retrieval_finished_at)}
          </p>
          <Dimensions value={answer.dimensions} title="مشخصات جست‌وجو" />
          {answer.needs_clarification ? (
            <p role="status">
              عدد و واحد ابعاد را دقیق بنویسید؛ مثلاً «ورق، ضخامت ۲ میلی‌متر،
              عرض ۱۲۰۰ میلی‌متر». شرط مبهم حذف نمی‌شود و جست‌وجو انجام نشده است.
            </p>
          ) : answer.query == null ? (
            <p>
              در این مرحله فقط جست‌وجوی کالا و قیمت پشتیبانی می‌شود؛ نام کالا را
              در سؤال مشخص کنید.
            </p>
          ) : (
            <p>
              جست‌وجو برای «{String(answer.query)}» ·{" "}
              {display(answer.product_total)} کالا · ارز{" "}
              {currencies[String(answer.currency)]}
            </p>
          )}
          {answer.query != null && answer.products.length === 0 && (
            <p>
              کالایی مطابق این جست‌وجو یافت نشد؛ نام یا SKU دقیق‌تر بنویسید.
            </p>
          )}
          {answer.products.map((product) => (
            <article className="record-detail" key={product.id}>
              <h3>
                {String(product.name)} · <bdi>{String(product.sku)}</bdi>
              </h3>
              <Dimensions value={product.attributes} title="مشخصات کالا" />
              {product.prices.length === 0 && (
                <p>قیمت تأییدشده و معتبر در این ارز یافت نشد.</p>
              )}
              {product.prices.map((price) => (
                <section key={price.id} className="card">
                  <p>
                    <strong>
                      {display(price.amount)}{" "}
                      {currencies[String(price.currency)]} /{" "}
                      {display(price.unit)}
                    </strong>
                  </p>
                  <p>
                    منبع: {String(price.source_name || "—")} · منشأ:{" "}
                    {String(price.provenance)}
                  </p>
                  <p>
                    مشاهده: {display(price.observed_at)} · اعتبار تا:{" "}
                    {display(price.valid_until)}
                  </p>
                  <p>
                    تحویل: {String(price.delivery_location)} ·{" "}
                    {String(price.delivery_terms)} ·{" "}
                    {price.tax_included ? "شامل مالیات" : "بدون مالیات"}
                  </p>
                  <p className="muted">
                    شناسهٔ شاهد قیمت: <bdi>{price.id}</bdi>
                  </p>
                </section>
              ))}
              {Number(product.price_total) > product.prices.length && (
                <p className="muted">
                  پنج قیمت اخیر نمایش داده شد؛ تاریخچهٔ کامل در صفحهٔ مشاهدات
                  قیمت است.
                </p>
              )}
            </article>
          ))}
          {Number(answer.product_total) > answer.products.length && (
            <p className="muted">
              پنج کالای نخست نمایش داده شد؛ برای نتیجهٔ دقیق‌تر نام یا SKU را
              مشخص کنید.
            </p>
          )}
        </section>
      )}
    </section>
  );
}
