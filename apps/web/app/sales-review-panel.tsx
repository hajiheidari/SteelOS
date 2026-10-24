"use client";
import { useEffect, useState } from "react";
import { api, display, type Row } from "./workspace-schema";

export function SalesReviewPanel({
  draft,
  historical,
  admin,
  busy,
  submit,
}: {
  draft: Row;
  historical: boolean;
  admin: boolean;
  busy: boolean;
  submit: (decision: string, note: string) => void;
}) {
  const [rows, setRows] = useState<Row[]>([]);
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [decision, setDecision] = useState("accepted");
  const [note, setNote] = useState("");
  const [confirm, setConfirm] = useState(false);
  useEffect(() => {
    let active = true;
    setLoading(true);
    void api(`sales-drafts/${draft.id}/reviews?limit=25&offset=${offset}`)
      .then((data) => {
        if (active) {
          setRows(data.items);
          setTotal(data.total);
          setError("");
        }
      })
      .catch((e) => {
        if (active) setError((e as Error).message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [draft.id, offset]);
  const current = draft.internal_review as Row | null;
  return (
    <section aria-label="بازبینی داخلی فروش">
      <h3>بازبینی داخلی فروش</h3>
      <p className="muted">
        این بازبینی تأیید مالی یا مجوز ارسال به مشتری نیست. ویرایش سند، بازبینی
        نسخهٔ تازه می‌خواهد.
      </p>
      {current && (
        <p role="status">
          نتیجهٔ این نسخه:{" "}
          {current.decision === "accepted"
            ? "پذیرفته‌شدهٔ داخلی"
            : "نیازمند اصلاح"}
          {!historical &&
            current.decision === "accepted" &&
            !draft.internal_review_usable &&
            "؛ قیمت یا وضعیت مشتری/سند اکنون نیاز به بررسی دوباره دارد."}
        </p>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {admin && !historical && draft.status === "draft" && !current && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setConfirm(true);
          }}
        >
          <fieldset disabled={busy || confirm}>
            <label>
              نتیجهٔ بازبینی
              <select
                value={decision}
                onChange={(e) => setDecision(e.target.value)}
              >
                <option value="accepted">پذیرفتن داخلی</option>
                <option value="rejected">نیازمند اصلاح</option>
              </select>
            </label>
            <label>
              یادداشت بازبینی
              <textarea
                maxLength={2000}
                required={decision === "rejected"}
                value={note}
                onChange={(e) => setNote(e.target.value)}
              />
            </label>
            <button>ثبت بازبینی داخلی</button>
          </fieldset>
        </form>
      )}
      {confirm && (
        <section
          className="confirm card"
          role="alertdialog"
          aria-labelledby="sales-review-confirm"
        >
          <h4 id="sales-review-confirm">
            تأیید بازبینی نسخه {display(draft.version)}
          </h4>
          <p>
            {decision === "accepted" ? "پذیرفتن داخلی" : "نیازمند اصلاح"} · مبلغ
            با مالیات: {display(draft.grand_total)}{" "}
            {{ IRR: "ریال", IRT: "تومان", USD: "دلار", EUR: "یورو" }[
              String(draft.currency)
            ] || String(draft.currency)}
          </p>
          <p>
            نتیجه و یادداشت در تاریخچه باقی می‌مانند؛ ارسال به مشتری انجام
            نمی‌شود.
          </p>
          <button disabled={busy} onClick={() => submit(decision, note)}>
            تأیید ثبت بازبینی
          </button>
          <button
            className="quiet"
            disabled={busy}
            onClick={() => setConfirm(false)}
          >
            انصراف از بازبینی
          </button>
        </section>
      )}
      {loading && <p role="status">در حال دریافت بازبینی‌ها…</p>}
      {rows.map((row) => (
        <article key={row.id} className="record-detail">
          <p>
            بازبینی نسخه {display(row.version)} ·{" "}
            {row.decision === "accepted"
              ? "پذیرفته‌شدهٔ داخلی"
              : "نیازمند اصلاح"}{" "}
            · {display(row.created_at)}
          </p>
          <p>{String(row.note)}</p>
        </article>
      ))}
      <div className="pagination">
        <button
          className="quiet"
          disabled={busy || loading || offset === 0}
          onClick={() => setOffset(offset - 25)}
        >
          بازبینی‌های جدیدتر
        </button>
        <span>{display(total)} بازبینی</span>
        <button
          className="quiet"
          disabled={busy || loading || offset + 25 >= total}
          onClick={() => setOffset(offset + 25)}
        >
          بازبینی‌های قدیمی‌تر
        </button>
      </div>
    </section>
  );
}
