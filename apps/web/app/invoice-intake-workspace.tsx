"use client";
import { useEffect, useRef, useState } from "react";
import {
  api,
  display,
  normalizeDecimalInput,
  sessionExpiredEvent,
  type Row,
} from "./workspace-schema";

type Line = {
  description: string;
  quantity: string | null;
  unit: string | null;
  unit_price: string | null;
  line_total: string | null;
};
type Fields = {
  invoice_number: string | null;
  invoice_date_text: string | null;
  seller_name: string | null;
  buyer_name: string | null;
  currency: string | null;
  subtotal: string | null;
  tax_total: string | null;
  grand_total: string | null;
  lines: Line[];
};
type Intake = Row & {
  version: number;
  status: string;
  raw_text: string;
  corrected_text: string;
  fields: Fields;
  source_sha256: string;
  extraction: { warnings: string[]; evidence: Record<string, string> };
};
const labels = {
  invoice_number: "شماره فاکتور",
  invoice_date_text: "تاریخ درج‌شده",
  seller_name: "نام فروشنده",
  buyer_name: "نام خریدار",
  currency: "ارز درج‌شده",
  subtotal: "جمع قبل از مالیات",
  tax_total: "مبلغ مالیات",
  grand_total: "مبلغ کل",
};
const lineLabels = {
  description: "شرح کالا",
  quantity: "مقدار",
  unit: "واحد درج‌شده",
  unit_price: "فی درج‌شده",
  line_total: "مبلغ ردیف",
};
const numeric = new Set([
  "subtotal",
  "tax_total",
  "grand_total",
  "quantity",
  "unit_price",
  "line_total",
]);

export function InvoiceIntakeWorkspace({ role }: { role: string }) {
  const [rows, setRows] = useState<Row[]>([]),
    [total, setTotal] = useState(0),
    [offset, setOffset] = useState(0);
  const [draft, setDraft] = useState<Intake | null>(null),
    [fields, setFields] = useState<Fields | null>(null),
    [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null),
    [review, setReview] = useState(false),
    [historical, setHistorical] = useState(false);
  const [versions, setVersions] = useState<Row[]>([]),
    [versionOffset, setVersionOffset] = useState(0),
    [versionTotal, setVersionTotal] = useState(0);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [available, setAvailable] = useState<boolean | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [previewHash, setPreviewHash] = useState<string | null>(null);
  const versionSequence = useRef(0);
  const alive = useRef(true),
    sequence = useRef(0);
  useEffect(() => {
    setPreviewHash(null);
    if (!file || !["image/png", "image/jpeg"].includes(file.type)) {
      setPreview(null);
      return;
    }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);
  useEffect(() => {
    alive.current = true;
    void api("invoice-intakes/status")
      .then((d) => {
        if (alive.current) setAvailable(d.available);
      })
      .catch(() => {
        if (alive.current) setAvailable(false);
      });
    return () => {
      alive.current = false;
      sequence.current++;
    };
  }, []);
  useEffect(() => {
    let current = true;
    void api(`invoice-intakes?limit=25&offset=${offset}`)
      .then((d) => {
        if (current) {
          setRows(d.items);
          setTotal(d.total);
        }
      })
      .catch((e) => {
        if (current) setError(e.message);
      });
    return () => {
      current = false;
    };
  }, [offset, notice]);
  function show(d: Intake, history = false) {
    setDraft(d);
    setFields(d.fields);
    setText(d.corrected_text);
    setReview(false);
    setHistorical(history);
  }
  async function history(id: string, at: number) {
    const n = sequence.current,
      h = ++versionSequence.current;
    try {
      const data = await api(
        `invoice-intakes/${id}/revisions?limit=25&offset=${at}`,
      );
      if (
        alive.current &&
        n === sequence.current &&
        h === versionSequence.current
      ) {
        setVersions(data.items);
        setVersionOffset(at);
        setVersionTotal(data.total);
      }
    } catch (e) {
      if (
        alive.current &&
        n === sequence.current &&
        h === versionSequence.current
      )
        setError((e as Error).message);
    }
  }
  async function open(id: string, version?: number) {
    const n = ++sequence.current;
    setBusy(true);
    setError("");
    try {
      const d = await api(
        `invoice-intakes/${id}${version ? `/revisions/${version}` : ""}`,
      );
      if (alive.current && sequence.current === n) {
        show(d, !!version);
        if (!version) await history(id, 0);
      }
    } catch (e) {
      if (alive.current && sequence.current === n)
        setError((e as Error).message);
    } finally {
      if (alive.current && sequence.current === n) setBusy(false);
    }
  }
  async function upload() {
    if (!file || busy) return;
    if (file.size > 5 * 1024 * 1024) {
      setError("حداکثر اندازهٔ فایل ۵ مگابایت است.");
      return;
    }
    const n = ++sequence.current;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const response = await fetch("/api/backend/invoice-intakes/extract", {
        method: "POST",
        headers: {
          "Content-Type": file.type,
          "Idempotency-Key": crypto.randomUUID(),
        },
        body: file,
      });
      if (response.status === 401)
        window.dispatchEvent(new Event(sessionExpiredEvent));
      if (!response.ok)
        throw new Error(
          (
            {
              409: "این فایل قبلاً ثبت شده است؛ آن را از فهرست باز کنید.",
              413: "فایل بیش از ۵ مگابایت است.",
              415: "فقط فایل PNG، JPEG یا PDF پذیرفته می‌شود.",
              422: "فایل نامعتبر یا بیش از ۳ صفحه است.",
              429: "OCR مشغول است؛ کمی بعد تلاش کنید.",
              503: "OCR محلی آماده نیست.",
              504: "زمان پردازش تمام شد؛ تصویر ساده‌تر ارسال کنید.",
            } as Record<number, string>
          )[response.status] || "دریافت فایل ناموفق بود.",
        );
      const d = await response.json();
      if (alive.current && sequence.current === n) {
        show(d);
        setPreviewHash(d.source_sha256);
        setNotice("استخراج انجام شد؛ داده‌ها نیاز به بررسی دارند.");
        await history(d.id, 0);
      }
    } catch (e) {
      if (alive.current && sequence.current === n)
        setError((e as Error).message);
    } finally {
      if (alive.current && sequence.current === n) setBusy(false);
    }
  }
  const editable = role !== "viewer" && !historical && !busy;
  async function save() {
    if (!draft || !fields || !editable) return;
    const n = ++sequence.current;
    setBusy(true);
    setError("");
    const clean = (row: Record<string, unknown>) =>
      Object.fromEntries(
        Object.entries(row).map(([k, v]) => [
          k,
          v === ""
            ? null
            : numeric.has(k) && typeof v === "string"
              ? normalizeDecimalInput(v)
              : v,
        ]),
      );
    try {
      const d = await api(
        `invoice-intakes/${draft.id}`,
        "PUT",
        {
          expected_version: draft.version,
          corrected_text: text,
          fields: {
            ...clean(fields),
            lines: fields.lines.map((line) => clean(line)),
          },
          mark_reviewed: review,
        },
        crypto.randomUUID(),
      );
      if (alive.current && sequence.current === n) {
        show(d);
        setNotice(
          `نسخهٔ ${display(d.version)} ذخیره شد؛ تأیید مالی انجام نشده است.`,
        );
        await history(d.id, 0);
      }
    } catch (e) {
      if (alive.current && sequence.current === n)
        setError((e as Error).message);
    } finally {
      if (alive.current && sequence.current === n) setBusy(false);
    }
  }
  return (
    <section className="card">
      <h2>دریافت و بررسی فاکتور</h2>
      <p>
        PNG، JPEG یا PDF حداکثر ۳ صفحه و ۵ مگابایت. متن و داده‌های پیشنهادی ممکن
        است اشتباه باشند؛ آن‌ها را با اصل فاکتور تطبیق دهید.
      </p>
      <p className="info">
        این بخش فقط رونویسی و بررسی انسانی است؛ ثبت مالی، قیمت یا موجودی انجام
        نمی‌دهد. فایل اصلی ذخیره نمی‌شود؛ اصل آن را نزد خود حفظ کنید.
      </p>
      {available === false && (
        <p role="status" className="error">
          OCR محلی یا زبان فارسی/انگلیسی آماده نیست؛ راه‌اندازی سرور را تکمیل
          کنید.
        </p>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="success">
          {notice}
        </p>
      )}
      {role !== "viewer" && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void upload();
          }}
        >
          <label>
            فایل فاکتور
            <input
              type="file"
              accept="image/png,image/jpeg,application/pdf"
              required
              disabled={busy}
              onChange={(e) => setFile(e.target.files?.[0] || null)}
            />
          </label>
          <button disabled={!file || busy || available === false}>
            {busy ? "در حال پردازش…" : "دریافت و استخراج محلی"}
          </button>
        </form>
      )}
      <h3>ورودی‌های ثبت‌شده</h3>
      <ul>
        {rows.map((row) => (
          <li key={row.id}>
            <button disabled={busy} onClick={() => void open(row.id)}>
              {display(row.invoice_number)} · نسخه {display(row.version)} ·{" "}
              {row.status === "reviewed"
                ? "رونویسی بررسی‌شده"
                : "نیازمند بررسی"}
            </button>
          </li>
        ))}
      </ul>
      <div className="actions">
        <button
          disabled={offset === 0 || busy}
          onClick={() => setOffset(Math.max(0, offset - 25))}
        >
          صفحهٔ قبلی
        </button>
        <span>{display(total)} ورودی</span>
        <button
          disabled={offset + 25 >= total || busy}
          onClick={() => setOffset(offset + 25)}
        >
          صفحهٔ بعدی
        </button>
      </div>
      {draft && fields && (
        <div>
          <h3>
            {historical ? "نسخهٔ تاریخی (فقط مشاهده)" : "اصلاح و بررسی رونویسی"}{" "}
            · نسخه {display(draft.version)}
          </h3>
          {preview && previewHash === draft.source_sha256 && (
            <figure>
              <img
                src={preview}
                alt="اصل فاکتور انتخاب‌شده در همین مرورگر"
                style={{ maxWidth: "100%", height: "auto" }}
              />
              <figcaption>
                اصل همین فایل؛ ارقام و ممیزها را با آن تطبیق دهید.
              </figcaption>
            </figure>
          )}
          <p style={{ overflowWrap: "anywhere" }}>
            اثر فایل: <bdi>{draft.source_sha256}</bdi>
          </p>
          <p>
            مالیات و جمع‌ها عین دادهٔ درج‌شده‌اند؛ محاسبه یا اعتبارسنجی مالی
            نمی‌شوند. تومان به ریال تبدیل نمی‌شود.
          </p>
          <details>
            <summary>متن اولیهٔ استخراج‌شده (ثابت)</summary>
            <pre
              dir="auto"
              style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}
            >
              {draft.raw_text || "متنی خوانده نشد؛ ورود دستی لازم است."}
            </pre>
          </details>
          <details>
            <summary>شواهد فیلدهای پیشنهادی</summary>
            <ul>
              {Object.entries(draft.extraction.evidence).map(([key, value]) => (
                <li key={key}>
                  <bdi>{key}</bdi>: {value}
                </li>
              ))}
            </ul>
          </details>
          {draft.extraction.warnings.length > 0 && (
            <p className="info">
              ارز، ارقام و ممیزها، فیلدهای خالی و ردیف‌ها را دستی بررسی کنید؛
              خوانده‌نشدن فیلد به معنی صفر نیست.
            </p>
          )}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void save();
            }}
          >
            <label>
              متن اصلاح‌شده
              <textarea
                aria-label="متن اصلاح‌شده"
                dir="auto"
                rows={10}
                maxLength={100000}
                disabled={!editable}
                value={text}
                onChange={(e) => setText(e.target.value)}
              />
            </label>
            <div className="form-grid">
              {(Object.keys(labels) as (keyof typeof labels)[]).map((key) => (
                <label key={key}>
                  {labels[key]}
                  {key === "currency" ? (
                    <select
                      aria-label={labels[key]}
                      disabled={!editable}
                      value={fields.currency || ""}
                      onChange={(e) =>
                        setFields({
                          ...fields,
                          currency: e.target.value || null,
                        })
                      }
                    >
                      <option value="">نیازمند بررسی</option>
                      <option value="IRR">ریال</option>
                      <option value="IRT">تومان</option>
                      <option value="USD">دلار</option>
                      <option value="EUR">یورو</option>
                    </select>
                  ) : (
                    <input
                      disabled={!editable}
                      maxLength={
                        key === "seller_name" || key === "buyer_name"
                          ? 200
                          : 100
                      }
                      inputMode={numeric.has(key) ? "decimal" : "text"}
                      value={fields[key] || ""}
                      onChange={(e) =>
                        setFields({ ...fields, [key]: e.target.value || null })
                      }
                    />
                  )}
                </label>
              ))}
            </div>
            <h4>ردیف‌های رونویسی</h4>
            {fields.lines.map((line, index) => (
              <fieldset key={index} disabled={!editable}>
                <legend>ردیف {display(index + 1)}</legend>
                <div className="form-grid">
                  {(Object.keys(lineLabels) as (keyof Line)[]).map((key) => (
                    <label key={key}>
                      {lineLabels[key]}
                      <input
                        required={key === "description"}
                        maxLength={key === "description" ? 500 : 40}
                        value={line[key] || ""}
                        onChange={(e) =>
                          setFields({
                            ...fields,
                            lines: fields.lines.map((v, i) =>
                              i === index
                                ? { ...v, [key]: e.target.value || null }
                                : v,
                            ),
                          })
                        }
                      />
                    </label>
                  ))}
                </div>
                <button
                  type="button"
                  onClick={() =>
                    setFields({
                      ...fields,
                      lines: fields.lines.filter((_, i) => i !== index),
                    })
                  }
                >
                  حذف ردیف
                </button>
              </fieldset>
            ))}
            {editable && (
              <button
                type="button"
                disabled={fields.lines.length >= 100}
                onClick={() =>
                  setFields({
                    ...fields,
                    lines: [
                      ...fields.lines,
                      {
                        description: "",
                        quantity: null,
                        unit: null,
                        unit_price: null,
                        line_total: null,
                      },
                    ],
                  })
                }
              >
                افزودن ردیف دستی
              </button>
            )}
            {editable && (
              <label>
                <input
                  type="checkbox"
                  checked={review}
                  onChange={(e) => setReview(e.target.checked)}
                />
                متن و داده‌ها را با اصل فاکتور تطبیق دادم (بررسی رونویسی)
              </label>
            )}
            {role !== "viewer" && !historical && (
              <button disabled={busy}>
                {review ? "ثبت بررسی انسانی متن" : "ذخیره اصلاحات"}
              </button>
            )}
          </form>
          <h4>تاریخچهٔ تغییرات</h4>
          <div className="actions">
            {versions.map((v) => (
              <button
                key={v.id}
                disabled={busy}
                onClick={() => void open(draft.id, Number(v.version))}
              >
                نسخهٔ {display(v.version)}
              </button>
            ))}
            <button disabled={busy} onClick={() => void open(draft.id)}>
              بازخوانی نسخهٔ جاری
            </button>
          </div>
          <div className="actions">
            <button
              disabled={busy || versionOffset === 0}
              onClick={() =>
                void history(draft.id, Math.max(0, versionOffset - 25))
              }
            >
              تاریخچهٔ قبلی
            </button>
            <button
              disabled={busy || versionOffset + 25 >= versionTotal}
              onClick={() => void history(draft.id, versionOffset + 25)}
            >
              تاریخچهٔ بعدی
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
