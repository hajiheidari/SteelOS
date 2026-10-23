"use client";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import {
  api,
  display,
  normalizeDecimalInput,
  type Row,
} from "./workspace-schema";

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
async function all(resource: string): Promise<Row[]> {
  const items: Row[] = [];
  for (let offset = 0; ; offset += 100) {
    const data = await api(`${resource}?limit=100&offset=${offset}`);
    items.push(...data.items);
    if (items.length >= data.total) return items;
  }
}

export function InventoryWorkspace({ role }: { role: string }) {
  const [tab, setTab] = useState<Tab>("balances");
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const [warehouse, setWarehouse] = useState("");
  const [rows, setRows] = useState<Row[]>([]);
  const [products, setProducts] = useState<Row[]>([]);
  const [parties, setParties] = useState<Row[]>([]);
  const [warehouses, setWarehouses] = useState<Row[]>([]);
  const [locations, setLocations] = useState<Row[]>([]);
  const [lots, setLots] = useState<Row[]>([]);
  const [drafts, setDrafts] = useState<Row[]>([]);
  const [reservations, setReservations] = useState<Row[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState<{
    row: Row;
    action: "post" | "reject";
  } | null>(null);
  const [ownerKind, setOwnerKind] = useState("company");
  const [productId, setProductId] = useState("");
  const [kind, setKind] = useState("receipt");
  const [lotId, setLotId] = useState("");
  const [quantity, setQuantity] = useState("");
  const [expiry, setExpiry] = useState(() =>
    localTime(new Date(Date.now() + 3600000)),
  );
  const sequence = useRef(0);
  const retry = useRef({ signature: "", key: "" });
  const admin = role === "admin";
  const writer = role !== "viewer";
  const product = (id: unknown) =>
    String(products.find((p) => p.id === id)?.name || "—");
  const owner = (row: Row) =>
    row.owner_kind === "company"
      ? "کالای شرکت"
      : String(
          parties.find((p) => p.id === row.owner_party_id)?.name ||
            "مالک شخص ثالث",
        );
  const lotLabel = (id: unknown) => {
    const row = lots.find((l) => l.id === id);
    return row
      ? `${row.code} · ${product(row.product_id)} · ${owner(row)}`
      : String(id || "—");
  };
  const locationLabel = (id: unknown) => {
    const row = locations.find((l) => l.id === id);
    return row
      ? `${warehouses.find((w) => w.id === row.warehouse_id)?.name} / ${row.name}`
      : "—";
  };
  const lot = lots.find((l) => l.id === lotId);
  const load = useCallback(async () => {
    const request = ++sequence.current;
    setLoading(true);
    setError("");
    try {
      const [p, people, w, l, b, d, r] = await Promise.all(
        [
          "products",
          "parties",
          "warehouses",
          "locations",
          "inventory/lots",
          "inventory/drafts",
          "inventory/reservations",
        ].map(all),
      );
      const suffix =
        warehouse && tab !== "lots" ? `&warehouse_id=${warehouse}` : "";
      const data = await api(
        `inventory/${tab}?limit=25&offset=${offset}${suffix}`,
      );
      if (request !== sequence.current) return;
      setProducts(p);
      setParties(people);
      setWarehouses(w);
      setLocations(l);
      setLots(b);
      setDrafts(d);
      setReservations(r);
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
      product_id: productId,
      unit: products.find((p) => p.id === productId)?.unit,
      owner_kind: ownerKind,
      owner_party_id: ownerKind === "party" ? f.get("owner_party_id") : null,
    };
    void run(async () => {
      await api("inventory/lots", "POST", data, key("lot", data));
      form.reset();
      setProductId("");
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
      setLotId("");
      setKind("receipt");
    });
  }
  const locationOptions = locations.map((l) => (
    <option key={l.id} value={l.id}>
      {locationLabel(l.id)}
    </option>
  ));
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
            <fieldset className="form-grid full" disabled={busy}>
              <label>
                کد lot (لاتین)
                <input
                  name="code"
                  required
                  maxLength={80}
                  pattern="[A-Za-z0-9_.-]+"
                />
              </label>
              <label>
                کالای lot
                <select
                  required
                  value={productId}
                  onChange={(e) => setProductId(e.target.value)}
                >
                  <option value="">انتخاب کنید</option>
                  {products
                    .filter((p) => p.active)
                    .map((p) => (
                      <option key={p.id} value={p.id}>
                        {String(p.name)}
                      </option>
                    ))}
                </select>
              </label>
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
                <label>
                  مالک شخص ثالث
                  <select name="owner_party_id" required>
                    <option value="">انتخاب کنید</option>
                    {parties
                      .filter((p) => p.active)
                      .map((p) => (
                        <option key={p.id} value={p.id}>
                          {String(p.name)}
                        </option>
                      ))}
                  </select>
                </label>
              )}
              <p>
                واحد ثابت lot:{" "}
                {display(products.find((p) => p.id === productId)?.unit)}
              </p>
              <button disabled={busy}>ثبت lot</button>
            </fieldset>
          </form>
        </section>
      )}
      {tab === "drafts" && writer && (
        <section className="card">
          <h2>پیش‌نویس عملیات انبار</h2>
          <form className="form-grid" onSubmit={submitDraft}>
            <fieldset className="form-grid full" disabled={busy}>
              <label>
                lot عملیات
                <select
                  value={lotId}
                  required
                  onChange={(e) => setLotId(e.target.value)}
                >
                  <option value="">انتخاب کنید</option>
                  {lots.map((l) => (
                    <option key={l.id} value={l.id}>
                      {lotLabel(l.id)}
                    </option>
                  ))}
                </select>
              </label>
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
                <label>
                  مکان مبدأ
                  <select name="from_location_id" required>
                    <option value="">انتخاب کنید</option>
                    {locationOptions}
                  </select>
                </label>
              )}
              {["receipt", "transfer"].includes(kind) && (
                <label>
                  مکان مقصد
                  <select name="to_location_id" required>
                    <option value="">انتخاب کنید</option>
                    {locationOptions}
                  </select>
                </label>
              )}
              {["release", "fulfill"].includes(kind) && (
                <label>
                  رزرو مرتبط
                  <select name="reservation_id" required>
                    <option value="">انتخاب کنید</option>
                    {reservations
                      .filter(
                        (r) =>
                          r.lot_id === lotId &&
                          String(r.remaining) !== "0.000" &&
                          String(r.remaining) !== "0",
                      )
                      .map((r) => (
                        <option key={r.id} value={r.id}>
                          {String(r.reference)} · باقی‌مانده{" "}
                          {display(r.remaining)}
                          {r.expired ? " · منقضی" : ""}
                        </option>
                      ))}
                  </select>
                </label>
              )}
              {kind === "reversal" && (
                <label>
                  گردش اصلی برای برگشت
                  <select
                    name="reverses_id"
                    required
                    defaultValue=""
                    onChange={(e) =>
                      setQuantity(
                        String(
                          drafts.find((d) => d.id === e.target.value)
                            ?.quantity || "",
                        ),
                      )
                    }
                  >
                    <option value="">انتخاب کنید</option>
                    {drafts
                      .filter(
                        (d) =>
                          d.lot_id === lotId &&
                          d.status === "posted" &&
                          d.kind !== "reversal",
                      )
                      .map((d) => (
                        <option key={d.id} value={d.id}>
                          {String(d.reference)} · {kinds[String(d.kind)]} ·{" "}
                          {display(d.quantity)}
                        </option>
                      ))}
                  </select>
                </label>
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
            <label>
              فیلتر انبار
              <select
                disabled={busy}
                value={warehouse}
                onChange={(e) => {
                  setWarehouse(e.target.value);
                  setOffset(0);
                }}
              >
                <option value="">همهٔ انبارهای مجاز</option>
                {warehouses.map((w) => (
                  <option key={w.id} value={w.id}>
                    {String(w.name)}
                  </option>
                ))}
              </select>
            </label>
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
                      <td>{product(row.product_id)}</td>
                      <td>{owner(row)}</td>
                      <td>{display(row.unit)}</td>
                    </>
                  ) : tab === "balances" ? (
                    <>
                      <td>
                        {String(row.code)} · {product(row.product_id)}
                      </td>
                      <td>{owner(row)}</td>
                      <td>{locationLabel(row.location_id)}</td>
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
                      <td>{lotLabel(row.lot_id)}</td>
                      <td>{kinds[String(row.kind)]}</td>
                      <td>{display(row.quantity)}</td>
                      <td>{locationLabel(row.from_location_id)}</td>
                      <td>{locationLabel(row.to_location_id)}</td>
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
                      <td>
                        {String(
                          drafts.find((d) => d.id === row.draft_id)
                            ?.reference || row.draft_id,
                        )}
                      </td>
                      <td>{lotLabel(row.lot_id)}</td>
                      <td>{locationLabel(row.location_id)}</td>
                      <td>{display(row.on_hand_delta)}</td>
                      <td>{display(row.blocked_delta)}</td>
                      <td>{display(row.reserved_delta)}</td>
                      <td>{display(row.created_at)}</td>
                    </>
                  ) : (
                    <>
                      <td>{String(row.reference)}</td>
                      <td>{lotLabel(row.lot_id)}</td>
                      <td>{locationLabel(row.location_id)}</td>
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
            · {display(confirm.row.quantity)}{" "}
            {display(lots.find((l) => l.id === confirm.row.lot_id)?.unit)}
          </p>
          <p>{lotLabel(confirm.row.lot_id)}</p>
          <p>
            مبدأ: {locationLabel(confirm.row.from_location_id)} · مقصد:{" "}
            {locationLabel(confirm.row.to_location_id)}
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
