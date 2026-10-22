"use client";
import { useCallback, useEffect, useState } from "react";
import {
  type Row,
  type Me,
  api,
  display,
  getFields,
  titles,
  roles,
} from "./workspace-schema";
import { Editor } from "./record-editor";

export default function Home() {
  const [me, setMe] = useState<Me | null>(null);
  const [checking, setChecking] = useState(true);
  const [page, setPage] = useState("dashboard");
  const [rows, setRows] = useState<Row[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(false);
  const [editing, setEditing] = useState<Row | null | undefined>(undefined);
  const [refs, setRefs] = useState<Row[]>([]);
  const [warehouses, setWarehouses] = useState<Row[]>([]);
  const [products, setProducts] = useState<Row[]>([]);
  const [sources, setSources] = useState<Row[]>([]);
  const [locations, setLocations] = useState<Row[]>([]);
  const [stats, setStats] = useState<Record<string, number>>({});
  const [members, setMembers] = useState<Row[]>([]);
  const [grants, setGrants] = useState<Row[]>([]);
  const [confirmDelete, setConfirmDelete] = useState<Row | null>(null);
  useEffect(() => {
    api("auth/me")
      .then(setMe)
      .catch(() => {})
      .finally(() => setChecking(false));
  }, []);
  const all = async (resource: string): Promise<Row[]> => {
    const items: Row[] = [];
    let offset = 0;
    while (true) {
      const data = await api(`${resource}?limit=100&offset=${offset}`);
      items.push(...data.items);
      if (items.length >= data.total) return items;
      offset += 100;
    }
  };
  const load = useCallback(async () => {
    if (!me) return;
    setLoading(true);
    setError("");
    try {
      const referenceData = await Promise.all(
        [
          "catalog-references",
          "warehouses",
          "products",
          "price-sources",
          "locations",
        ].map(all),
      );
      setRefs(referenceData[0]);
      setWarehouses(referenceData[1]);
      setProducts(referenceData[2]);
      setSources(referenceData[3]);
      setLocations(referenceData[4]);
      if (page === "dashboard") {
        const keys = [
          "products",
          "parties",
          "warehouses",
          "price-observations",
        ];
        const values = await Promise.all(keys.map((k) => api(`${k}?limit=1`)));
        setStats(Object.fromEntries(keys.map((k, i) => [k, values[i].total])));
      } else if (page === "settings") {
        if (me.role === "admin") {
          setMembers((await api("organization/members")).items);
          setGrants(await all("warehouse-access"));
        }
      } else {
        const extra =
          filter && page === "parties"
            ? `&role=${filter}`
            : filter && page === "price-observations"
              ? "&approved_only=true"
              : "";
        const data = await api(
          `${page}?limit=25&offset=${offset}&q=${encodeURIComponent(search)}${extra}`,
        );
        setRows(data.items);
        setTotal(data.total);
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [me, page, offset, search, filter]);
  useEffect(() => {
    void load();
  }, [load]);
  function navigate(key: string) {
    setPage(key);
    setOffset(0);
    setQuery("");
    setSearch("");
    setFilter("");
    setEditing(undefined);
    setError("");
    setNotice("");
    setConfirmDelete(null);
  }
  async function mutate(action: () => Promise<unknown>) {
    setError("");
    try {
      await action();
      setNotice("عملیات با موفقیت انجام شد.");
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  }
  if (checking)
    return (
      <main className="login">
        <p role="status">در حال بررسی نشست…</p>
      </main>
    );
  if (!me)
    return (
      <main className="login">
        <div className="login-brand">
          <span className="brand">
            Steel<span>OS</span>
          </span>
          <h1>مدیریت یکپارچهٔ تجارت فولاد</h1>
          <p>کالا، ارتباطات تجاری، انبار و رصد قیمت در یک محیط کاری.</p>
          <span className="badge">بنیان عملیاتی · M1</span>
        </div>
        <section className="card">
          <h2>ورود به فضای کاری</h2>
          <p className="muted">شناسهٔ سازمان را از مدیر سامانه دریافت کنید.</p>
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              setLoading(true);
              setError("");
              const f = new FormData(e.currentTarget);
              try {
                await api("auth/login", "POST", Object.fromEntries(f));
                setMe(await api("auth/me"));
              } catch (e) {
                setError((e as Error).message);
              } finally {
                setLoading(false);
              }
            }}
          >
            <label>
              ایمیل
              <input
                name="email"
                type="email"
                dir="ltr"
                autoComplete="username"
                required
              />
            </label>
            <label>
              رمز عبور
              <input
                name="password"
                type="password"
                dir="ltr"
                autoComplete="current-password"
                required
                maxLength={128}
              />
            </label>
            <label>
              شناسه سازمان
              <input
                name="organization_id"
                dir="ltr"
                required
                pattern="[a-fA-F0-9-]{36}"
              />
            </label>
            {error && (
              <p className="error" role="alert">
                {error}
              </p>
            )}
            <button disabled={loading}>
              {loading ? "در حال ورود…" : "ورود"}
            </button>
          </form>
        </section>
      </main>
    );
  const admin = me.role === "admin";
  const canWrite = me.role !== "viewer";
  const fields = getFields(
    page,
    refs,
    warehouses,
    products,
    sources,
    locations,
  );
  const columns = fields
    .filter(
      (f) =>
        ![
          "attributes",
          "attribute_rules",
          "contacts",
          "addresses",
          "provenance",
          "delivery_terms",
        ].includes(f.key),
    )
    .slice(0, 7);
  return (
    <div className="shell">
      <a className="skip" href="#content">
        رفتن به محتوا
      </a>
      <aside>
        <div className="brand">
          Steel<span>OS</span>
        </div>
        <p className="org">{me.organization.name}</p>
        <nav aria-label="ناوبری اصلی">
          {Object.entries(titles).map(([key, title]) => (
            <button
              key={key}
              aria-current={page === key ? "page" : undefined}
              className={page === key ? "selected" : ""}
              onClick={() => navigate(key)}
            >
              {title}
            </button>
          ))}
        </nav>
        <div className="sidebar-foot">
          نسخهٔ بنیادین M1
          <br />
          تجارت فولاد، با دادهٔ قابل اعتماد
        </div>
      </aside>
      <div className="workspace">
        <header>
          <span>{display(new Date().toISOString())}</span>
          <div>
            {me.email} <span className="badge">{display(me.role)}</span>{" "}
            <button
              className="quiet"
              onClick={() =>
                mutate(async () => {
                  await api("auth/logout", "POST");
                  setMe(null);
                })
              }
            >
              خروج
            </button>
          </div>
        </header>
        <main id="content">
          <div className="page-heading">
            <div>
              <p className="eyebrow">فضای کاری / {titles[page]}</p>
              <h1>{titles[page]}</h1>
            </div>
            {fields.length > 0 &&
              canWrite &&
              (!["warehouses", "catalog-references", "price-sources"].includes(
                page,
              ) ||
                admin) && (
                <button
                  onClick={() => {
                    setEditing(null);
                    setNotice("");
                  }}
                >
                  + ثبت جدید
                </button>
              )}
          </div>
          {error && (
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
              در حال دریافت اطلاعات…
            </p>
          )}
          {page === "dashboard" ? (
            <>
              <div className="stats">
                {Object.entries(stats).map(([key, n]) => (
                  <button
                    className="card stat"
                    key={key}
                    onClick={() => navigate(key)}
                  >
                    <span>{titles[key]}</span>
                    <strong>{display(n)}</strong>
                    <small>مشاهدهٔ فهرست ←</small>
                  </button>
                ))}
              </div>
              <section className="card">
                <h2>فضای کاری شما آماده است</h2>
                <p>
                  ابتدا تعاریف کاتالوگ و کالاها را ثبت کنید. سپس اطلاعات طرف‌های
                  تجاری، انبارها و مشاهدات قیمت را تکمیل کنید.
                </p>
                <p className="muted">
                  موجودی عملیاتی و حسابداری متعلق به مراحل بعد هستند. محل
                  نگهداری کالا نشان‌دهندهٔ مالکیت آن نیست.
                </p>
              </section>
            </>
          ) : page === "settings" ? (
            <>
              <section className="card">
                <h2>حساب کاربری</h2>
                <p>
                  سازمان: <bdi>{me.organization.id}</bdi>
                </p>
                <form
                  className="form-grid"
                  onSubmit={(e) => {
                    e.preventDefault();
                    const data = Object.fromEntries(
                      new FormData(e.currentTarget),
                    );
                    void mutate(async () => {
                      await api("auth/password", "PUT", data);
                      setMe(null);
                    });
                  }}
                >
                  <label>
                    رمز عبور فعلی
                    <input
                      type="password"
                      name="current_password"
                      autoComplete="current-password"
                      required
                    />
                  </label>
                  <label>
                    رمز عبور جدید (حداقل ۱۲ نویسه)
                    <input
                      type="password"
                      name="new_password"
                      minLength={12}
                      maxLength={128}
                      autoComplete="new-password"
                      required
                    />
                  </label>
                  <button>تغییر رمز و خروج از همه نشست‌ها</button>
                </form>
              </section>
              {admin && (
                <>
                  <section className="card">
                    <h2>تنظیمات سازمان</h2>
                    <form
                      className="inline"
                      onSubmit={(e) => {
                        e.preventDefault();
                        const name = new FormData(e.currentTarget).get("name");
                        void mutate(async () => {
                          await api("organization", "PUT", { name });
                          setMe(await api("auth/me"));
                        });
                      }}
                    >
                      <label>
                        نام سازمان
                        <input
                          name="name"
                          defaultValue={me.organization.name}
                          required
                          maxLength={200}
                        />
                      </label>
                      <button>ذخیره نام سازمان</button>
                    </form>
                  </section>
                  <section className="card">
                    <h2>کاربران سازمان</h2>
                    <div className="table-wrap">
                      <table>
                        <thead>
                          <tr>
                            <th>ایمیل</th>
                            <th>نقش</th>
                            <th>عملیات</th>
                          </tr>
                        </thead>
                        <tbody>
                          {members.map((m) => (
                            <tr key={String(m.user_id)}>
                              <td>{String(m.email)}</td>
                              <td>
                                <select
                                  aria-label={`نقش ${m.email}`}
                                  value={String(m.role)}
                                  onChange={(e) =>
                                    void mutate(() =>
                                      api(
                                        `organization/members/${m.user_id}`,
                                        "PUT",
                                        { role: e.target.value },
                                      ),
                                    )
                                  }
                                >
                                  {roles.map((r) => (
                                    <option key={r.value} value={r.value}>
                                      {r.label}
                                    </option>
                                  ))}
                                </select>
                              </td>
                              <td>
                                <button
                                  className="quiet"
                                  onClick={() =>
                                    setConfirmDelete({
                                      ...m,
                                      id: String(m.user_id),
                                      kind: "member",
                                      name: m.email,
                                    })
                                  }
                                >
                                  حذف دسترسی
                                </button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    <form
                      className="form-grid"
                      onSubmit={(e) => {
                        e.preventDefault();
                        const form = e.currentTarget;
                        const data = Object.fromEntries(new FormData(form));
                        void mutate(async () => {
                          await api("organization/members", "POST", data);
                          form.reset();
                        });
                      }}
                    >
                      <label>
                        ایمیل کاربر جدید
                        <input name="email" type="email" required />
                      </label>
                      <label>
                        رمز عبور اولیه
                        <input
                          type="password"
                          name="password"
                          minLength={12}
                          maxLength={128}
                          autoComplete="new-password"
                          required
                        />
                      </label>
                      <label>
                        نقش
                        <select name="role">
                          {roles.map((r) => (
                            <option key={r.value} value={r.value}>
                              {r.label}
                            </option>
                          ))}
                        </select>
                      </label>
                      <button>افزودن کاربر</button>
                    </form>
                  </section>
                  <section className="card">
                    <h2>دسترسی انبار</h2>
                    <p className="muted">
                      مدیران به همهٔ انبارها دسترسی دارند. برای سایر کاربران،
                      دسترسی جداگانه ثبت کنید.
                    </p>
                    <form
                      className="inline"
                      onSubmit={(e) => {
                        e.preventDefault();
                        const data = Object.fromEntries(
                          new FormData(e.currentTarget),
                        );
                        void mutate(() =>
                          api(
                            "warehouse-access",
                            "POST",
                            data,
                            crypto.randomUUID(),
                          ),
                        );
                      }}
                    >
                      <label>
                        کاربر
                        <select name="user_id" required>
                          <option value="">انتخاب کنید</option>
                          {members.map((m) => (
                            <option
                              key={String(m.user_id)}
                              value={String(m.user_id)}
                            >
                              {String(m.email)}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        انبار
                        <select name="warehouse_id" required>
                          <option value="">انتخاب کنید</option>
                          {warehouses.map((w) => (
                            <option key={w.id} value={w.id}>
                              {String(w.name)}
                            </option>
                          ))}
                        </select>
                      </label>
                      <button>ثبت دسترسی</button>
                    </form>
                    {grants.map((g) => (
                      <p key={g.id}>
                        {String(
                          members.find((m) => m.user_id === g.user_id)?.email ||
                            g.user_id,
                        )}{" "}
                        ·{" "}
                        {String(
                          warehouses.find((w) => w.id === g.warehouse_id)?.name,
                        )}{" "}
                        <button
                          className="quiet"
                          onClick={() =>
                            void mutate(() =>
                              api(`warehouse-access/${g.id}`, "DELETE"),
                            )
                          }
                        >
                          لغو دسترسی
                        </button>
                      </p>
                    ))}
                  </section>
                </>
              )}
            </>
          ) : (
            <>
              {editing !== undefined && (
                <Editor
                  key={`${page}-${editing?.id || "new"}`}
                  fields={fields}
                  refs={refs}
                  initial={editing || undefined}
                  page={page}
                  onCancel={() => setEditing(undefined)}
                  onSave={async (data, key) => {
                    await api(
                      page + (editing ? "/" + editing.id : ""),
                      editing ? "PUT" : "POST",
                      data,
                      key,
                    );
                    setEditing(undefined);
                    setNotice("رکورد ذخیره شد.");
                    await load();
                  }}
                />
              )}
              {page === "price-observations" && (
                <p className="info">
                  قیمت ثبت‌شده پیشنهاد فروش قطعی نیست. فقط قیمت‌های تأییدشده،
                  دارای منبع مجاز و اعتبار زمانی قابل استفاده هستند.
                </p>
              )}
              {page === "catalog-references" && (
                <p className="info">
                  برای گروه کالا، ابعاد مورد نیاز مانند thickness و واحد آن‌ها
                  را تعریف کنید. قواعد گروهی که کالا دارد قابل تغییر نیست.
                </p>
              )}
              <section className="card">
                <form
                  className="toolbar"
                  onSubmit={(e) => {
                    e.preventDefault();
                    setSearch(query);
                    setOffset(0);
                  }}
                >
                  <label className="search">
                    جستجو
                    <input
                      value={query}
                      onChange={(e) => setQuery(e.target.value)}
                      placeholder="نام، کد یا شناسه…"
                    />
                  </label>
                  {page === "parties" && (
                    <label>
                      نقش
                      <select
                        value={filter}
                        onChange={(e) => {
                          setFilter(e.target.value);
                          setOffset(0);
                        }}
                      >
                        <option value="">همه</option>
                        <option value="customer">مشتری</option>
                        <option value="supplier">تأمین‌کننده</option>
                      </select>
                    </label>
                  )}
                  {page === "price-observations" && (
                    <label>
                      نمایش
                      <select
                        value={filter}
                        onChange={(e) => {
                          setFilter(e.target.value);
                          setOffset(0);
                        }}
                      >
                        <option value="">همه مشاهدات</option>
                        <option value="approved">
                          فقط قیمت معتبر و تأییدشده
                        </option>
                      </select>
                    </label>
                  )}
                  <button className="quiet">جستجو</button>
                  <span className="muted">{display(total)} رکورد</span>
                </form>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        {columns.map((f) => (
                          <th key={f.key} scope="col">
                            {f.label}
                          </th>
                        ))}
                        {page === "price-observations" && (
                          <th scope="col">وضعیت</th>
                        )}
                        <th scope="col">عملیات</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((row) => (
                        <tr key={row.id}>
                          {columns.map((f) => (
                            <td key={f.key}>
                              {f.key.endsWith("_id")
                                ? String(
                                    [
                                      ...refs,
                                      ...warehouses,
                                      ...products,
                                      ...sources,
                                      ...locations,
                                    ].find((r) => r.id === row[f.key])?.name ||
                                      "—",
                                  )
                                : display(row[f.key])}
                            </td>
                          ))}
                          {page === "price-observations" && (
                            <td>
                              <span className={`badge ${row.status}`}>
                                {display(row.status)}
                              </span>
                              {new Date(String(row.valid_until)) <
                                new Date() && (
                                <small className="expired">منقضی شده</small>
                              )}
                            </td>
                          )}
                          <td className="row-actions">
                            {canWrite &&
                              page !== "price-observations" &&
                              (![
                                "warehouses",
                                "catalog-references",
                                "price-sources",
                              ].includes(page) ||
                                admin) && (
                                <button
                                  className="quiet"
                                  onClick={() => setEditing(row)}
                                >
                                  ویرایش
                                </button>
                              )}
                            {admin && page !== "price-observations" && (
                              <button
                                className="quiet danger"
                                onClick={() => setConfirmDelete(row)}
                              >
                                حذف
                              </button>
                            )}
                            {admin &&
                              page === "price-observations" &&
                              row.status === "pending" && (
                                <>
                                  <button
                                    className="quiet"
                                    onClick={() =>
                                      void mutate(() =>
                                        api(
                                          `${page}/${row.id}/decision`,
                                          "POST",
                                          { status: "approved" },
                                        ),
                                      )
                                    }
                                  >
                                    تأیید
                                  </button>
                                  <button
                                    className="quiet danger"
                                    onClick={() =>
                                      void mutate(() =>
                                        api(
                                          `${page}/${row.id}/decision`,
                                          "POST",
                                          { status: "rejected" },
                                        ),
                                      )
                                    }
                                  >
                                    رد
                                  </button>
                                </>
                              )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {!loading && rows.length === 0 && (
                  <div className="empty">
                    <h2>هنوز رکوردی ثبت نشده است</h2>
                    <p>
                      برای شروع از «ثبت جدید» استفاده کنید یا جستجوی خود را
                      تغییر دهید.
                    </p>
                  </div>
                )}
                <div className="pagination">
                  <button
                    className="quiet"
                    disabled={offset === 0}
                    onClick={() => setOffset(offset - 25)}
                  >
                    قبلی
                  </button>
                  <span>صفحه {display(Math.floor(offset / 25) + 1)}</span>
                  <button
                    className="quiet"
                    disabled={offset + 25 >= total}
                    onClick={() => setOffset(offset + 25)}
                  >
                    بعدی
                  </button>
                </div>
              </section>
            </>
          )}
          {confirmDelete && (
            <section
              role="alertdialog"
              aria-labelledby="delete-title"
              className="confirm card"
            >
              <h2 id="delete-title">حذف رکورد</h2>
              <p>
                حذف «
                {String(
                  confirmDelete.name || confirmDelete.code || confirmDelete.id,
                )}
                » را تأیید می‌کنید؟
              </p>
              <div className="actions">
                <button
                  className="danger"
                  onClick={() =>
                    void mutate(async () => {
                      await api(
                        confirmDelete.kind === "member"
                          ? `organization/members/${confirmDelete.id}`
                          : `${page}/${confirmDelete.id}`,
                        "DELETE",
                      );
                      setConfirmDelete(null);
                    })
                  }
                >
                  تأیید حذف
                </button>
                <button
                  className="quiet"
                  onClick={() => setConfirmDelete(null)}
                >
                  انصراف
                </button>
              </div>
            </section>
          )}
        </main>
        <footer>
          SteelOS · زمان نمایش: تقویم جلالی، منطقهٔ تهران · داده‌ها متعلق به
          سازمان جاری هستند
        </footer>
      </div>
    </div>
  );
}
