"use client";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import {
  api,
  display,
  normalizeDecimalInput,
  type Row,
} from "./workspace-schema";

import { RemoteSelect } from "./remote-select";

type Tab = "balances" | "lots" | "drafts" | "entries" | "reservations";
const tabs: Record<Tab, string> = {
  balances: "موجودی محاسبه‌شده",
  lots: "lot و مالکیت",
  drafts: "پیش‌نویس و گردش‌ها",
  entries: "دفتر گردش",
  reservations: "رزروها",
};
const kinds: Record<string, string> = {
  receipt: "دریافت",
  dispatch: "خروج",
  transfer: "انتقال",
  block: "مسدودکردن",
  unblock: "رفع مسدودی",
  reserve: "رزرو",
  release: "آزادسازی رزرو",
  fulfill: "خروج از رزرو",
  reversal: "برگشت کامل گردش",
};
const statuses: Record<string, string> = {
  draft: "پیش‌نویس",
  posted: "ثبت نهایی",
  rejected: "رد شده",
};
function localTime(date: Date) {
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16);
}

export function InventoryWorkspace({ role }: { role: string }) {
  const [tab, setTab] = useState<Tab>("balances");
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const [warehouse, setWarehouse] = useState("");
  const [warehouseOption, setWarehouseOption] = useState<Row | null>(null);
  const [rows, setRows] = useState<Row[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState<{
    row: Row;
    action: "post" | "reject";
  } | null>(null);
  const [ownerKind, setOwnerKind] = useState("company");
  const [selectedProduct, setSelectedProduct] = useState<Row | null>(null);
  const [formEpoch, setFormEpoch] = useState(0);
  const [kind, setKind] = useState("receipt");
  const [lot, setLot] = useState<Row | null>(null);
  const lotId = lot?.id || "";
  const [quantity, setQuantity] = useState("");
  const [expiry, setExpiry] = useState(() =>
    localTime(new Date(Date.now() + 3600000)),
  );
  const sequence = useRef(0);
  const retry = useRef({ signature: "", key: "" });
  const admin = role === "admin";
  const writer = role !== "viewer";
  const owner = (row: Row) =>
    row.owner_kind === "company"
      ? "کالای شرکت"
      : String(row.owner_name || "مالک شخص ثالث");
  const lotLabel = (row: Row) =>
    `${row.lot_code || row.code} · ${row.product_name || "—"} · ${owner(row)}`;
  const locationLabel = (row: Row, prefix = "") =>
    row[prefix + "location_name"]
      ? `${row[prefix + "warehouse_name"] || "—"} / ${row[prefix + "location_name"]}`
      : "—";
  const load = useCallback(async () => {
    const request = ++sequence.current;
    setLoading(true);
    setError("");
    try {
      const suffix =
        warehouse && tab !== "lots" ? `&warehouse_id=${warehouse}` : "";
      const data = await api(
        `inventory/${tab}?limit=25&offset=${offset}${suffix}`,
      );
      if (request !== sequence.current) return;
      setRows(data.items);
      setTotal(data.total);
    } catch (e) {
      if (request === sequence.current) setError((e as Error).message);
    } finally {
      if (request === sequence.current) setLoading(false);
    }
  }, [tab, offset, warehouse]);
  useEffect(() => {
    void load();
    return () => {
      sequence.current += 1;
    };
  }, [load]);
  async function run(action: () => Promise<unknown>) {
    const view = sequence.current;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await action();
      if (view !== sequence.current) return;
      setConfirm(null);
      setNotice("عملیات با موفقیت انجام شد.");
      await load();
    } catch (e) {
      if (view === sequence.current) setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function key(path: string, data: unknown) {
    const signature = path + JSON.stringify(data);
    if (retry.current.signature !== signature)
      retry.current = { signature, key: crypto.randomUUID() };
    return retry.current.key;
  }
  function submitLot(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const f = new FormData(form);
    const data = {
      code: f.get("code"),
      product_id: selectedProduct?.id,
      unit: selectedProduct?.unit,
      owner_kind: ownerKind,
      owner_party_id: ownerKind === "party" ? f.get("owner_party_id") : null,
    };
    void run(async () => {
      await api("inventory/lots", "POST", data, key("lot", data));
      form.reset();
      setSelectedProduct(null);
      setFormEpoch((n) => n + 1);
      setOwnerKind("company");
    });
  }
  function submitDraft(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const f = new FormData(form);
    const data: Record<string, unknown> = {
      lot_id: lotId,
      kind,
      quantity: normalizeDecimalInput(quantity),
      reference: f.get("reference"),
      note: f.get("note") || "",
    };
    if (["dispatch", "transfer", "block", "unblock", "reserve"].includes(kind))
      data.from_location_id = f.get("from_location_id");
    if (["receipt", "transfer"].includes(kind))
      data.to_location_id = f.get("to_location_id");
    if (["release", "fulfill"].includes(kind))
      data.reservation_id = f.get("reservation_id");
    if (kind === "reserve") data.expires_at = new Date(expiry).toISOString();
    if (kind === "reversal") data.reverses_id = f.get("reverses_id");
    void run(async () => {
      await api("inventory/drafts", "POST", data, key("draft", data));
      form.reset();
      setQuantity("");
      setLot(null);
      setFormEpoch((n) => n + 1);
      setKind("receipt");
    });
  }
  return (
    <>
      <p className="info">
        مالک حقوقی lot از محل نگهداری مستقل است. پیش‌نویس اثری بر موجودی ندارد؛
        فقط مدیر ثبت نهایی می‌کند. مانده‌ها از دفتر غیرقابل ویرایش محاسبه
        می‌شوند.
      </p>
      <nav className="toolbar" aria-label="بخش‌های موجودی">
        {Object.entries(tabs).map(([value, label]) => (
          <button
            key={value}
            disabled={busy}
            className={tab === value ? "" : "quiet"}
            aria-current={tab === value ? "page" : undefined}
            onClick={() => {
              if (tab === value) return;
              sequence.current += 1;
              setRows([]);
              setOffset(0);
              setTab(value as Tab);
              setNotice("");
              setError("");
            }}
          >
            {label}
          </button>
        ))}
      </nav>
      {error && !confirm && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p className="success" role="status">
          {notice}
        </p>
      )}
      {loading && (
        <p className="muted" role="status">
          در حال دریافت موجودی…
        </p>
      )}
      {tab === "lots" && writer && (
        <section className="card">
          <h2>ثبت lot با مالک مشخص</h2>
          <form className="form-grid" onSubmit={submitLot}>
            <fieldset
              key={formEpoch}
              className="form-grid full"
              disabled={busy}
            >
              <label>
                کد lot (لاتین)
                <input
                  name="code"
                  required
                  maxLength={80}
                  pattern="[A-Za-z0-9_.-]+"
                />
              </label>
              <RemoteSelect
                label="کالای lot"
                resource="products?active=true"
                required
                value={selectedProduct?.id || ""}
                onChange={setSelectedProduct}
              />
              <label>
                نوع مالک
                <select
                  value={ownerKind}
                  onChange={(e) => setOwnerKind(e.target.value)}
                >
                  <option value="company">شرکت جاری</option>
                  <option value="party">شخص ثالث / مشتری</option>
                </select>
              </label>
              {ownerKind === "party" && (
                <RemoteSelect
                  label="مالک شخص ثالث"
                  resource="parties?active=true"
                  name="owner_party_id"
                  required
                />
              )}
              <p>واحد ثابت lot: {display(selectedProduct?.unit)}</p>
              <button disabled={busy}>ثبت lot</button>
            </fieldset>
          </form>
        </section>
      )}
      {tab === "drafts" && writer && (
        <section className="card">
          <h2>پیش‌نویس عملیات انبار</h2>
          <form className="form-grid" onSubmit={submitDraft}>
            <fieldset
              key={formEpoch}
              className="form-grid full"
              disabled={busy}
            >
              <RemoteSelect
                label="lot عملیات"
                resource="inventory/lots"
                required
                value={lotId}
                optionLabel={lotLabel}
                onChange={setLot}
              />
              <label>
                نوع عملیات
                <select
                  value={kind}
                  onChange={(e) => {
                    setKind(e.target.value);
                    setQuantity("");
                  }}
                >
                  {Object.entries(kinds).map(([k, v]) => (
                    <option key={k} value={k}>
                      {v}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                مقدار عملیات
                <input
                  required
                  inputMode="decimal"
                  value={quantity}
                  readOnly={kind === "reversal"}
                  onChange={(e) => setQuantity(e.target.value)}
                />
              </label>
              <p>
                واحد: {display(lot?.unit)} · مالک: {lot ? owner(lot) : "—"}
              </p>
              {["dispatch", "transfer", "block", "unblock", "reserve"].includes(
                kind,
              ) && (
                <RemoteSelect
                  label="مکان مبدأ"
                  resource="locations"
                  name="from_location_id"
                  required
                  optionLabel={(row) => `${row.warehouse_name} / ${row.name}`}
                />
              )}
              {["receipt", "transfer"].includes(kind) && (
                <RemoteSelect
                  label="مکان مقصد"
                  resource="locations"
                  name="to_location_id"
                  required
                  optionLabel={(row) => `${row.warehouse_name} / ${row.name}`}
                />
              )}
              {["release", "fulfill"].includes(kind) && (
                <RemoteSelect
                  key={`${kind}-${lotId}`}
                  label="رزرو مرتبط"
                  name="reservation_id"
                  required
                  resource={
                    lotId
                      ? `inventory/reservations?lot_id=${lotId}&remaining_only=true${kind === "fulfill" ? "&unexpired_only=true" : ""}`
                      : ""
                  }
                  optionLabel={(row) =>
                    `${row.reference} · باقی‌مانده ${display(row.remaining)}${row.expired ? " · منقضی" : ""}`
                  }
                />
              )}
              {kind === "reversal" && (
                <RemoteSelect
                  key={lotId}
                  label="گردش اصلی برای برگشت"
                  name="reverses_id"
                  required
                  resource={
                    lotId
                      ? `inventory/drafts?lot_id=${lotId}&reversible_only=true`
                      : ""
                  }
                  optionLabel={(row) =>
                    `${row.reference} · ${kinds[String(row.kind)]} · ${display(row.quantity)}`
                  }
                  onChange={(row) => setQuantity(String(row?.quantity || ""))}
                />
              )}
              {kind === "reserve" && (
                <label>
                  انقضای رزرو (زمان محلی دستگاه)
                  <input
                    required
                    type="datetime-local"
                    value={expiry}
                    onChange={(e) => setExpiry(e.target.value)}
                  />
                </label>
              )}
              <label>
                مرجع عملیات
                <input name="reference" required maxLength={200} />
              </label>
              <label>
                یادداشت عملیات
                <input name="note" maxLength={1000} />
              </label>
              <button disabled={busy}>ثبت پیش‌نویس</button>
            </fieldset>
          </form>
        </section>
      )}
      <section className="card">
        <div className="toolbar">
          {tab !== "lots" && (
            <RemoteSelect
              label="فیلتر انبار"
              resource="warehouses"
              disabled={busy}
              value={warehouse}
              selectedOption={warehouseOption}
              emptyLabel="همهٔ انبارهای مجاز"
              onChange={(row) => {
                if ((row?.id || "") === warehouse) return;
                sequence.current += 1;
                setWarehouse(row?.id || "");
                setWarehouseOption(row);
                setOffset(0);
              }}
            />
          )}
          <span>{display(total)} رکورد</span>
          <button
            className="quiet"
            disabled={busy || loading}
            onClick={() => void load()}
          >
            به‌روزرسانی موجودی
          </button>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                {tab === "lots" ? (
                  <>
                    <th>کد lot</th>
                    <th>کالا</th>
                    <th>مالک حقوقی</th>
                    <th>واحد</th>
                  </>
                ) : tab === "balances" ? (
                  <>
                    <th>lot / کالا</th>
                    <th>مالک حقوقی</th>
                    <th>محل نگهداری</th>
                    <th>موجود فیزیکی</th>
                    <th>مسدود</th>
                    <th>رزرو فعال</th>
                    <th>قابل استفاده</th>
                    <th>واحد</th>
                  </>
                ) : tab === "drafts" ? (
                  <>
                    <th>مرجع</th>
                    <th>lot / مالک</th>
                    <th>عملیات</th>
                    <th>مقدار</th>
                    <th>مبدأ</th>
                    <th>مقصد</th>
                    <th>وضعیت</th>
                    <th>عملیات مدیر</th>
                  </>
                ) : tab === "entries" ? (
                  <>
                    <th>گردش</th>
                    <th>lot / مالک</th>
                    <th>محل</th>
                    <th>تغییر موجود</th>
                    <th>تغییر مسدود</th>
                    <th>تغییر رزرو</th>
                    <th>زمان ثبت</th>
                  </>
                ) : (
                  <>
                    <th>مرجع</th>
                    <th>lot / مالک</th>
                    <th>محل</th>
                    <th>مقدار اولیه</th>
                    <th>باقی‌مانده</th>
                    <th>انقضا</th>
                    <th>وضعیت</th>
                  </>
                )}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <tr key={row.id || `${row.lot_id}-${row.location_id}-${index}`}>
                  {tab === "lots" ? (
                    <>
                      <td>{String(row.code)}</td>
                      <td>{String(row.product_name || "—")}</td>
                      <td>{owner(row)}</td>
                      <td>{display(row.unit)}</td>
                    </>
                  ) : tab === "balances" ? (
                    <>
                      <td>
                        {String(row.code)} · {String(row.product_name || "—")}
                      </td>
                      <td>{owner(row)}</td>
                      <td>{locationLabel(row)}</td>
                      <td>{display(row.on_hand)}</td>
                      <td>{display(row.blocked)}</td>
                      <td>{display(row.reserved)}</td>
                      <td>
                        <strong>{display(row.available)}</strong>
                      </td>
                      <td>{display(row.unit)}</td>
                    </>
                  ) : tab === "drafts" ? (
                    <>
                      <td>{String(row.reference)}</td>
                      <td>{lotLabel(row)}</td>
                      <td>{kinds[String(row.kind)]}</td>
                      <td>{display(row.quantity)}</td>
                      <td>{locationLabel(row, "from_")}</td>
                      <td>{locationLabel(row, "to_")}</td>
                      <td>
                        <span className="badge">
                          {statuses[String(row.status)]}
                        </span>
                      </td>
                      <td>
                        {admin && row.status === "draft" && (
                          <div className="row-actions">
                            <button
                              className="quiet"
                              disabled={busy}
                              onClick={() => {
                                setConfirm({ row, action: "post" });
                                setError("");
                              }}
                            >
                              ثبت نهایی
                            </button>
                            <button
                              className="quiet danger"
                              disabled={busy}
                              onClick={() => {
                                setConfirm({ row, action: "reject" });
                                setError("");
                              }}
                            >
                              رد پیش‌نویس
                            </button>
                          </div>
                        )}
                      </td>
                    </>
                  ) : tab === "entries" ? (
                    <>
                      <td>{String(row.draft_reference || row.draft_id)}</td>
                      <td>{lotLabel(row)}</td>
                      <td>{locationLabel(row)}</td>
                      <td>{display(row.on_hand_delta)}</td>
                      <td>{display(row.blocked_delta)}</td>
                      <td>{display(row.reserved_delta)}</td>
                      <td>{display(row.created_at)}</td>
                    </>
                  ) : (
                    <>
                      <td>{String(row.reference)}</td>
                      <td>{lotLabel(row)}</td>
                      <td>{locationLabel(row)}</td>
                      <td>{display(row.quantity)}</td>
                      <td>{display(row.remaining)}</td>
                      <td>{display(row.expires_at)}</td>
                      <td>{row.expired ? "منقضی" : "در بازهٔ اعتبار"}</td>
                    </>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!loading && rows.length === 0 && (
          <p className="empty">رکوردی در این بخش وجود ندارد.</p>
        )}
        <div className="pagination">
          <button
            className="quiet"
            disabled={busy || offset === 0}
            onClick={() => setOffset(offset - 25)}
          >
            قبلی
          </button>
          <span>صفحه {display(offset / 25 + 1)}</span>
          <button
            className="quiet"
            disabled={busy || offset + 25 >= total}
            onClick={() => setOffset(offset + 25)}
          >
            بعدی
          </button>
        </div>
      </section>
      {confirm && (
        <section
          className="confirm card"
          role="alertdialog"
          aria-labelledby="inventory-confirm-title"
        >
          <h2 id="inventory-confirm-title">
            {confirm.action === "post"
              ? "تأیید ثبت نهایی"
              : "تأیید رد پیش‌نویس"}
          </h2>
          <p>
            {String(confirm.row.reference)} · {kinds[String(confirm.row.kind)]}{" "}
            · {display(confirm.row.quantity)} {display(confirm.row.unit)}
          </p>
          <p>{lotLabel(confirm.row)}</p>
          <p>
            مبدأ: {locationLabel(confirm.row, "from_")} · مقصد:{" "}
            {locationLabel(confirm.row, "to_")}
          </p>
          <p className="muted">
            گردش ثبت‌شده قابل ویرایش یا حذف نیست؛ اصلاح آن با پیش‌نویس برگشت و
            کنترل موجودی انجام می‌شود.
          </p>
          {error && (
            <p role="alert" className="error">
              {error}
            </p>
          )}
          <div className="actions">
            <button
              disabled={busy}
              onClick={() =>
                void run(() =>
                  api(
                    `inventory/drafts/${confirm.row.id}/${confirm.action}`,
                    "POST",
                    undefined,
                    key(confirm.action, confirm.row.id),
                  ),
                )
              }
            >
              {busy
                ? "در حال پردازش…"
                : confirm.action === "post"
                  ? "تأیید ثبت نهایی"
                  : "تأیید رد پیش‌نویس"}
            </button>
            <button
              className="quiet"
              disabled={busy}
              onClick={() => {
                setConfirm(null);
                setError("");
              }}
            >
              انصراف
            </button>
          </div>
        </section>
      )}
    </>
  );
}
