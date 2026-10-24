"use client";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { RemoteSelect } from "./remote-select";
import {
  api,
  display,
  normalizeDecimalInput,
  type Row,
} from "./workspace-schema";

type FormLine = {
  key: string;
  product: Row | null;
  price: Row | null;
  quantity: string;
};
type Snapshot = {
  product: { name: string; sku: string };
  price: {
    delivery_location: string;
    delivery_terms: string;
    tax_included: boolean;
    provenance: string;
  };
  source: { name: string; provenance: string };
};
const currencies: Record<string, string> = {
  IRR: "ریال",
  IRT: "تومان",
  USD: "دلار",
  EUR: "یورو",
};
const blank = (): FormLine => ({
  key: crypto.randomUUID(),
  product: null,
  price: null,
  quantity: "",
});
const lineRows = (draft: Row) => draft.lines as Row[];
const snapshot = (line: Row) => line.snapshot as Snapshot;

export function SalesDraftsWorkspace({ role }: { role: string }) {
  const [rows, setRows] = useState<Row[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<Row | null>(null);
  const [editing, setEditing] = useState<Row | null | undefined>(undefined);
  const [historical, setHistorical] = useState(false);
  const [revisions, setRevisions] = useState<Row[]>([]);
  const [revisionTotal, setRevisionTotal] = useState(0);
  const [revisionOffset, setRevisionOffset] = useState(0);
  const [customer, setCustomer] = useState<Row | null>(null);
  const [code, setCode] = useState("");
  const [currency, setCurrency] = useState("IRR");
  const [note, setNote] = useState("");
  const [lines, setLines] = useState<FormLine[]>(() => [blank()]);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [cancel, setCancel] = useState(false);
  const alive = useRef(true);
  const generation = useRef(0);
  const retry = useRef({ signature: "", key: "" });
  const writer = role !== "viewer";
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      generation.current += 1;
    };
  }, []);
  const load = useCallback(async () => {
    const request = ++generation.current;
    setLoading(true);
    try {
      const data = await api(
        `sales-drafts?limit=25&offset=${offset}&q=${encodeURIComponent(search)}`,
      );
      if (!alive.current || request !== generation.current) return;
      setRows(data.items);
      setTotal(data.total);
    } catch (e) {
      if (alive.current && request === generation.current)
        setError((e as Error).message);
    } finally {
      if (alive.current && request === generation.current) setLoading(false);
    }
  }, [offset, search]);
  useEffect(() => {
    void load();
    return () => {
      generation.current += 1;
    };
  }, [load]);
  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await action();
    } catch (e) {
      if (alive.current) setError((e as Error).message);
    } finally {
      if (alive.current) setBusy(false);
    }
  }
  function key(path: string, data: unknown) {
    const signature = path + JSON.stringify(data);
    if (retry.current.signature !== signature)
      retry.current = { signature, key: crypto.randomUUID() };
    return retry.current.key;
  }
  async function open(id: string) {
    await run(async () => {
      const [draft, history] = await Promise.all([
        api(`sales-drafts/${id}`),
        api(`sales-drafts/${id}/revisions?limit=25&offset=0`),
      ]);
      if (!alive.current) return;
      setSelected(draft);
      setRevisions(history.items);
      setRevisionTotal(history.total);
      setRevisionOffset(0);
      setHistorical(false);
      setEditing(undefined);
      setCancel(false);
    });
  }
  function edit(draft: Row | null) {
    setError("");
    setNotice("");
    setEditing(draft);
    setCode(String(draft?.code || ""));
    setCurrency(String(draft?.currency || "IRR"));
    setNote(String(draft?.note || ""));
    setCustomer(
      draft
        ? { id: String(draft.customer_id), name: draft.customer_name }
        : null,
    );
    setLines(
      draft
        ? lineRows(draft).map((line) => ({
            key: crypto.randomUUID(),
            quantity: String(line.quantity),
            product: {
              id: String(line.product_id),
              name: snapshot(line).product.name,
            },
            price: {
              id: String(line.price_id),
              amount: line.unit_price,
              currency: draft.currency,
              unit: line.unit,
              delivery_location: snapshot(line).price.delivery_location,
            },
          }))
        : [blank()],
    );
    if (!draft) {
      setSelected(null);
      setRevisions([]);
      setHistorical(false);
    }
  }
  function changeLine(index: number, changes: Partial<FormLine>) {
    setLines((old) =>
      old.map((line, i) => (i === index ? { ...line, ...changes } : line)),
    );
  }
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const body = {
      code,
      customer_id: customer?.id,
      currency,
      note,
      lines: lines.map((line) => ({
        price_id: line.price?.id,
        quantity: normalizeDecimalInput(line.quantity),
      })),
      ...(editing ? { expected_version: editing.version } : {}),
    };
    const path = `sales-drafts${editing ? "/" + editing.id : ""}`;
    void run(async () => {
      const saved = await api(
        path,
        editing ? "PUT" : "POST",
        body,
        key(path, body),
      );
      if (!alive.current) return;
      setEditing(undefined);
      setSelected(saved);
      setHistorical(false);
      setNotice("پیش‌نویس داخلی ذخیره شد.");
      const history = await api(
        `sales-drafts/${saved.id}/revisions?limit=25&offset=0`,
      );
      if (!alive.current) return;
      setRevisions(history.items);
      setRevisionTotal(history.total);
      setRevisionOffset(0);
      await load();
    });
  }
  async function historyPage(next: number) {
    if (!selected) return;
    await run(async () => {
      const data = await api(
        `sales-drafts/${selected.id}/revisions?limit=25&offset=${next}`,
      );
      if (!alive.current) return;
      setRevisions(data.items);
      setRevisionTotal(data.total);
      setRevisionOffset(next);
    });
  }
  return (
    <>
      <p className="info">
        این سند پیش‌نویس داخلی است. برآورد خام، مبلغ مالی نهایی یا پیش‌فاکتور
        تأییدشدهٔ مشتری نیست؛ مالیات، حمل و گردکردن نهایی جداگانه تعیین می‌شوند.
        ثبت این سند موجودی را رزرو نمی‌کند.
      </p>
      {error && !cancel && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p className="success" role="status">
          {notice}
        </p>
      )}
      <div className="toolbar">
        <form
          className="inline"
          onSubmit={(e) => {
            e.preventDefault();
            setOffset(0);
            setSearch(query);
          }}
        >
          <label>
            جست‌وجوی سند
            <input
              maxLength={200}
              value={query}
              disabled={busy}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
          <button disabled={busy}>جست‌وجو</button>
        </form>
        {writer && (
          <button disabled={busy} onClick={() => edit(null)}>
            پیش‌نویس فروش جدید
          </button>
        )}
      </div>
      {editing !== undefined && (
        <section className="card">
          <h2>{editing ? "ویرایش پیش‌نویس فروش" : "پیش‌نویس فروش جدید"}</h2>
          <form onSubmit={submit}>
            <fieldset className="form-grid full" disabled={busy}>
              <label>
                کد سند
                <input
                  required
                  maxLength={80}
                  pattern="[A-Za-z0-9_.-]+"
                  readOnly={!!editing}
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                />
              </label>
              <RemoteSelect
                label="مشتری سند"
                resource="parties?role=customer&active=true"
                required
                value={customer?.id || ""}
                selectedOption={customer}
                onChange={setCustomer}
              />
              <label>
                ارز سند
                <select
                  value={currency}
                  onChange={(e) => {
                    setCurrency(e.target.value);
                    setLines((old) =>
                      old.map((line) => ({ ...line, price: null })),
                    );
                  }}
                >
                  {Object.entries(currencies).map(([value, name]) => (
                    <option key={value} value={value}>
                      {name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                یادداشت سند
                <input
                  maxLength={2000}
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                />
              </label>
            </fieldset>
            {lines.map((line, index) => (
              <fieldset
                className="card form-grid"
                key={line.key}
                disabled={busy}
              >
                <legend>ردیف {display(index + 1)}</legend>
                <RemoteSelect
                  label={`کالای ردیف ${index + 1}`}
                  resource="products?active=true"
                  required
                  value={line.product?.id || ""}
                  selectedOption={line.product}
                  onChange={(product) =>
                    changeLine(index, { product, price: null })
                  }
                />
                <RemoteSelect
                  key={`${line.product?.id}-${currency}`}
                  label={`قیمت ردیف ${index + 1}`}
                  required
                  value={line.price?.id || ""}
                  selectedOption={line.price}
                  resource={
                    line.product
                      ? `price-observations?product_id=${line.product.id}&currency=${currency}&approved_only=true`
                      : ""
                  }
                  optionLabel={(row) =>
                    `${display(row.amount)} ${currencies[String(row.currency)]} / ${display(row.unit)} · ${row.delivery_location}`
                  }
                  onChange={(price) => changeLine(index, { price })}
                />
                <label>
                  مقدار ردیف {index + 1}
                  <input
                    required
                    inputMode="decimal"
                    value={line.quantity}
                    onChange={(e) =>
                      changeLine(index, { quantity: e.target.value })
                    }
                  />
                </label>
                <p>
                  واحد مقدار: {display(line.price?.unit)} · قیمت برای همین واحد
                  است.
                </p>
                <button
                  type="button"
                  className="quiet danger"
                  disabled={busy || lines.length === 1}
                  onClick={() =>
                    setLines((old) => old.filter((_, i) => i !== index))
                  }
                >
                  حذف ردیف {index + 1}
                </button>
              </fieldset>
            ))}
            <div className="actions">
              <button
                type="button"
                className="quiet"
                disabled={busy || lines.length >= 100}
                onClick={() => setLines((old) => [...old, blank()])}
              >
                افزودن ردیف کالا
              </button>
              <button disabled={busy}>
                {busy ? "در حال ذخیره…" : "ذخیره پیش‌نویس فروش"}
              </button>
              <button
                type="button"
                className="quiet"
                disabled={busy}
                onClick={() => setEditing(undefined)}
              >
                انصراف از ویرایش
              </button>
            </div>
          </form>
        </section>
      )}
      <section className="card">
        {loading && <p role="status">در حال دریافت سندها…</p>}
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>کد</th>
                <th>مشتری</th>
                <th>برآورد خام</th>
                <th>ارز</th>
                <th>وضعیت</th>
                <th>نسخه</th>
                <th>نمایش</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id}>
                  <td>{String(row.code)}</td>
                  <td>{String(row.customer_name)}</td>
                  <td>{display(row.estimated_total)}</td>
                  <td>{currencies[String(row.currency)]}</td>
                  <td>
                    {row.status === "cancelled" ? "لغو شده" : "پیش‌نویس داخلی"}
                    {!!row.has_expired_price && (
                      <small className="expired">قیمت منقضی</small>
                    )}
                  </td>
                  <td>{display(row.version)}</td>
                  <td>
                    <button
                      className="quiet"
                      disabled={busy}
                      onClick={() => void open(row.id)}
                    >
                      جزئیات سند
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!loading && rows.length === 0 && (
          <p className="empty">سندی وجود ندارد.</p>
        )}
        <div className="pagination">
          <button
            className="quiet"
            disabled={busy || offset === 0}
            onClick={() => setOffset(offset - 25)}
          >
            اسناد قبلی
          </button>
          <span>{display(total)} سند</span>
          <button
            className="quiet"
            disabled={busy || offset + 25 >= total}
            onClick={() => setOffset(offset + 25)}
          >
            اسناد بعدی
          </button>
        </div>
      </section>
      {selected && (
        <section className="card">
          <h2>
            جزئیات {String(selected.code)} · نسخه {display(selected.version)}
          </h2>
          {historical && (
            <p className="info">
              نسخهٔ تاریخی؛ نتیجهٔ بررسی قیمت مربوط به زمان ثبت همین نسخه است.
            </p>
          )}
          <p>
            مشتری: {String(selected.customer_name)} ·{" "}
            {selected.status === "cancelled" ? "لغو شده" : "پیش‌نویس داخلی"}
          </p>
          <p>
            برآورد خام بدون گردکردن:{" "}
            <strong>
              {display(selected.estimated_total)}{" "}
              {currencies[String(selected.currency)]}
            </strong>
          </p>
          {(!selected.prices_usable || !selected.customer_eligible) && (
            <p className="error">
              قیمت یا وضعیت مشتری نیاز به بازبینی دارد. این سند تأیید مالی
              ندارد.
            </p>
          )}
          <p className="muted">
            زمان بررسی قیمت: {display(selected.price_checks_as_of)}
          </p>
          {lineRows(selected).map((line) => (
            <article className="card" key={line.id}>
              <h3>{snapshot(line).product.name}</h3>
              <p>
                {display(line.quantity)} {display(line.unit)} ×{" "}
                {display(line.unit_price)}{" "}
                {currencies[String(selected.currency)]} · برآورد:{" "}
                {display(line.estimated_amount)}
              </p>
              <p>
                {snapshot(line).price.delivery_location} ·{" "}
                {snapshot(line).price.delivery_terms}
              </p>
              <p>
                {snapshot(line).price.tax_included
                  ? "مالیات در قیمت منبع لحاظ شده"
                  : "قیمت منبع بدون مالیات"}{" "}
                · {snapshot(line).source.name}
              </p>
              <p className="muted">
                مرجع: {snapshot(line).price.provenance} · اعتبار تا{" "}
                {display(line.price_valid_until)}
              </p>
            </article>
          ))}
          <p>{String(selected.note)}</p>
          <div className="actions">
            <button
              className="quiet"
              disabled={busy}
              onClick={() => void open(selected.id)}
            >
              دریافت آخرین نسخه
            </button>
            {writer && !historical && selected.status === "draft" && (
              <>
                <button disabled={busy} onClick={() => edit(selected)}>
                  ویرایش سند
                </button>
                <button
                  className="quiet danger"
                  disabled={busy}
                  onClick={() => setCancel(true)}
                >
                  لغو سند
                </button>
              </>
            )}
          </div>
          <h3>تاریخچهٔ نسخه‌ها</h3>
          {revisions.map((row) => (
            <p key={row.id}>
              نسخه {display(row.version)} · {display(row.created_at)}{" "}
              <button
                className="quiet"
                disabled={busy}
                onClick={() =>
                  void run(async () => {
                    const revision = await api(
                      `sales-drafts/${selected.id}/revisions/${row.version}`,
                    );
                    if (!alive.current) return;
                    setSelected(revision.snapshot);
                    setHistorical(true);
                    setEditing(undefined);
                    setCancel(false);
                  })
                }
              >
                نمایش نسخه {display(row.version)}
              </button>
            </p>
          ))}
          <div className="pagination">
            <button
              className="quiet"
              disabled={busy || revisionOffset === 0}
              onClick={() => void historyPage(revisionOffset - 25)}
            >
              نسخه‌های جدیدتر
            </button>
            <span>{display(revisionTotal)} نسخه</span>
            <button
              className="quiet"
              disabled={busy || revisionOffset + 25 >= revisionTotal}
              onClick={() => void historyPage(revisionOffset + 25)}
            >
              نسخه‌های قدیمی‌تر
            </button>
          </div>
        </section>
      )}
      {cancel && selected && (
        <section
          className="confirm card"
          role="alertdialog"
          aria-labelledby="sales-cancel-title"
        >
          <h2 id="sales-cancel-title">تأیید لغو پیش‌نویس</h2>
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
          <p>
            {String(selected.code)} · {String(selected.customer_name)} · نسخه{" "}
            {display(selected.version)}
          </p>
          <p>
            سند و تاریخچه باقی می‌مانند و این سند پس از لغو قابل ویرایش نیست.
          </p>
          <div className="actions">
            <button
              disabled={busy}
              onClick={() =>
                void run(async () => {
                  const body = { expected_version: selected.version };
                  const result = await api(
                    `sales-drafts/${selected.id}/cancel`,
                    "POST",
                    body,
                    key(`cancel/${selected.id}`, body),
                  );
                  if (!alive.current) return;
                  setSelected(result);
                  setCancel(false);
                  setEditing(undefined);
                  setNotice("پیش‌نویس لغو شد.");
                  await load();
                  const history = await api(
                    `sales-drafts/${selected.id}/revisions?limit=25&offset=0`,
                  );
                  if (alive.current) {
                    setRevisions(history.items);
                    setRevisionTotal(history.total);
                    setRevisionOffset(0);
                  }
                })
              }
            >
              تأیید لغو
            </button>
            <button
              className="quiet"
              disabled={busy}
              onClick={() => setCancel(false)}
            >
              انصراف از لغو
            </button>
          </div>
        </section>
      )}
    </>
  );
}
