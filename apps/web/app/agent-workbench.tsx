"use client";
import { useEffect, useRef, useState } from "react";
import { AgentLearning } from "./agent-learning";
import { api, display, type Row } from "./workspace-schema";

type Kind = "research" | "education" | "marketing" | "sales";
const agents: Record<Kind, { name: string; purpose: string }> = {
  research: {
    name: "تحقیق و توسعه",
    purpose: "جمع‌بندی شواهد، فرضیه و طرح آزمایش با معیار موفقیت",
  },
  education: {
    name: "آموزش",
    purpose: "درس کوتاه، تمرین و پرسش‌های خودارزیابی",
  },
  marketing: {
    name: "بازاریابی",
    purpose: "مخاطب، پیام و پیش‌نویس محتوا برای بررسی انسانی",
  },
  sales: {
    name: "فروش",
    purpose: "کشف نیاز مشتری و برنامهٔ پیگیری؛ بدون اعلام قیمت یا تعهد",
  },
};
type Source = Row & {
  name: string;
  content: string;
  active: boolean;
  attribution: string;
};
type Draft = Row & {
  grounding: string;
  evidence_current: boolean;
  output: {
    title: string;
    sections: { heading: string; body: string; sources: string[] }[];
    evidence_quotes: { source: string; quote: string }[];
    questions: string[];
  };
  evidence: {
    alias: string;
    snapshot: {
      name: string;
      content: string;
      attribution: string;
      source_url: string | null;
    };
  }[];
  review: { decision: string; note: string } | null;
};

export function AgentWorkbench({ role }: { role: string }) {
  const [kind, setKind] = useState<Kind>("research");
  const [configured, setConfigured] = useState(false);
  const [sources, setSources] = useState<Source[]>([]);
  const [sourceTotal, setSourceTotal] = useState(0);
  const [sourceOffset, setSourceOffset] = useState(0);
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [runs, setRuns] = useState<Row[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [revoking, setRevoking] = useState<string | null>(null);
  const action = useRef(0);
  const pendingWrite = useRef<{ signature: string; key: string } | null>(null);
  async function agentApi(path: string, method = "GET", body?: unknown) {
    if (method !== "POST") return api(path, method, body);
    const signature = JSON.stringify([path, body]);
    const key =
      pendingWrite.current?.signature === signature
        ? pendingWrite.current.key
        : crypto.randomUUID();
    pendingWrite.current = { signature, key };
    const result = await api(path, method, body, key);
    if (pendingWrite.current?.key === key) pendingWrite.current = null;
    return result;
  }

  useEffect(
    () => () => {
      action.current++;
    },
    [],
  );
  useEffect(() => {
    const timer = setTimeout(() => {
      setSearch(query);
      setSourceOffset(0);
    }, 250);
    return () => clearTimeout(timer);
  }, [query]);
  useEffect(() => {
    let current = true;
    Promise.all([
      agentApi("agent-workbench/status"),
      agentApi(
        `agent-workbench/sources?limit=25&offset=${sourceOffset}&q=${encodeURIComponent(search)}`,
      ),
      agentApi(`agent-workbench/runs?kind=${kind}&limit=25&offset=${offset}`),
    ])
      .then(([status, sourcePage, runPage]) => {
        if (current) {
          setConfigured(status.configured);
          setSources(sourcePage.items);
          setSourceTotal(sourcePage.total);
          setRuns(runPage.items);
          setTotal(runPage.total);
        }
      })
      .catch((e) => {
        if (current) setError((e as Error).message);
      });
    return () => {
      current = false;
    };
  }, [kind, offset, sourceOffset, search, refresh]);
  async function perform(work: () => Promise<void>) {
    const sequence = ++action.current;
    setBusy(true);
    setError("");
    try {
      await work();
      if (sequence === action.current) setRefresh((v) => v + 1);
    } catch (e) {
      if (sequence === action.current) setError((e as Error).message);
    } finally {
      if (sequence === action.current) setBusy(false);
    }
  }
  async function open(id: string) {
    const sequence = action.current;
    const value = await agentApi("agent-workbench/runs/" + id);
    if (sequence === action.current) setDraft(value);
  }
  return (
    <>
      <section className="card">
        <div className="inline" aria-label="نقش ایجنت">
          {(Object.keys(agents) as Kind[]).map((key) => (
            <button
              key={key}
              aria-pressed={kind === key}
              disabled={busy}
              onClick={() => {
                if (key === kind) return;
                action.current++;
                setKind(key);
                setRuns([]);
                setTotal(0);
                setOffset(0);
                setDraft(null);
                setError("");
              }}
            >
              {agents[key].name}
            </button>
          ))}
        </div>
        <h2>{agents[kind].name}</h2>
        <p>{agents[kind].purpose}</p>
        <p className="muted">
          خروجی پیشنهادی است؛ صحت ادعاها را انسان بررسی می‌کند. این بخش پیام
          ارسال یا منتشر نمی‌کند و تأیید مالی ندارد. بدون منبع فقط طرح اولیه
          تولید می‌شود.
        </p>
        {configured && (
          <p role="status">
            تولید متن آزمایشی است؛ کیفیت مدل فعلی برای تحقیق، آموزش و فروش
            پذیرفته نشده است. درس‌های مستند آموزش پایه از این مدل استفاده
            نمی‌کنند.
          </p>
        )}
        {!configured && (
          <p role="status">
            مدل محلی تنظیم نشده است؛ راه‌اندازی محلی مطابق راهنما لازم است.
            منابع و سوابق قابل مشاهده‌اند.
          </p>
        )}
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        {role !== "viewer" && (
          <form
            className="form-grid"
            onSubmit={(e) => {
              e.preventDefault();
              const brief = String(new FormData(e.currentTarget).get("brief"));
              const sequence = action.current + 1;
              void perform(async () => {
                const value = await agentApi("agent-workbench/runs", "POST", {
                  kind,
                  brief,
                  source_ids: selected,
                });
                if (action.current === sequence) setDraft(value);
              });
            }}
          >
            <label>
              درخواست ایجنت
              <textarea
                name="brief"
                required
                minLength={10}
                maxLength={1000}
                rows={4}
                disabled={busy}
              />
            </label>
            <p>
              منابع انتخاب‌شده: {display(selected.length)} از ۳؛ انتخاب در بخش
              دانش انجام می‌شود.
            </p>
            <button disabled={busy || !configured}>
              {busy ? "در حال آماده‌سازی…" : "تولید پیش‌نویس داخلی"}
            </button>
          </form>
        )}
      </section>
      {kind === "education" && <AgentLearning />}
      {draft && (
        <section className="card" aria-label="خروجی ایجنت">
          <h2>{draft.output.title}</h2>
          <p>
            {draft.grounding === "no_sources_plan_only"
              ? "طرح اولیه بدون منبع؛ یافتهٔ تحقیق محسوب نمی‌شود"
              : "پیش‌نویس دارای استناد؛ صحت تمام ادعاها نیازمند بررسی است"}
          </p>
          {!draft.evidence_current && (
            <p className="error" role="alert">
              اعتبار یکی از منابع لغو شده است؛ پیش‌نویس باید با منبع معتبر
              بازتولید شود.
            </p>
          )}
          {draft.output.sections.map((section, i) => (
            <article key={i}>
              <h3>{section.heading}</h3>
              <p style={{ whiteSpace: "pre-wrap" }}>{section.body}</p>
              <small>{section.sources.join("، ")}</small>
            </article>
          ))}
          {draft.output.evidence_quotes.length > 0 && (
            <h3>نقل‌قول‌های دقیق از شواهد</h3>
          )}
          {draft.output.evidence_quotes.map((quote) => (
            <blockquote key={quote.source}>
              <b>{quote.source}</b>
              <p>{quote.quote}</p>
            </blockquote>
          ))}
          {draft.evidence.map((evidence) => (
            <details key={evidence.alias}>
              <summary>
                {evidence.alias} — {evidence.snapshot.name}
              </summary>
              <p style={{ whiteSpace: "pre-wrap" }}>
                {evidence.snapshot.content}
              </p>
              <p>{evidence.snapshot.attribution}</p>
              {evidence.snapshot.source_url && (
                <a
                  style={{ overflowWrap: "anywhere" }}
                  href={evidence.snapshot.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  مرجع ثبت‌شدهٔ منبع
                </a>
              )}
            </details>
          ))}
          {draft.output.questions.length > 0 && (
            <>
              <h3>پرسش‌های باز</h3>
              <ul>
                {draft.output.questions.map((q, i) => (
                  <li key={i}>{q}</li>
                ))}
              </ul>
            </>
          )}
          {draft.review ? (
            <p role="status">
              {draft.review.decision === "accepted"
                ? "بازبینی داخلی پذیرفته شد؛ مجوز انتشار نیست"
                : "پیش‌نویس رد شد"}{" "}
              — {draft.review.note}
            </p>
          ) : (
            role === "admin" && (
              <form
                className="form-grid"
                onSubmit={(e) => {
                  e.preventDefault();
                  const form = new FormData(e.currentTarget);
                  void perform(async () =>
                    setDraft(
                      await agentApi(
                        `agent-workbench/runs/${draft.id}/review`,
                        "POST",
                        {
                          decision: form.get("decision"),
                          note: form.get("note"),
                        },
                      ),
                    ),
                  );
                }}
              >
                <label>
                  تصمیم بازبینی
                  <select name="decision">
                    <option value="accepted">پذیرش داخلی</option>
                    <option value="rejected">رد</option>
                  </select>
                </label>
                <label>
                  یادداشت بازبینی
                  <input name="note" required maxLength={1000} />
                </label>
                <label className="check">
                  <input type="checkbox" required />
                  می‌دانم بازبینی داخلی، مجوز انتشار یا تأیید مالی نیست.
                </label>
                <button disabled={busy}>ثبت بازبینی انسانی</button>
              </form>
            )
          )}
        </section>
      )}
      <section className="card">
        <h2>سوابق {agents[kind].name}</h2>
        <p>{display(total)} پیش‌نویس</p>
        {runs.map((run) => (
          <p key={run.id}>
            <button
              disabled={busy}
              onClick={() => void perform(() => open(run.id))}
            >
              {String((run.output as { title: string }).title)}
            </button>{" "}
            <small>{display(run.created_at)}</small>
          </p>
        ))}
        <div className="inline">
          <button
            disabled={busy || offset === 0}
            onClick={() => setOffset((v) => Math.max(0, v - 25))}
          >
            سوابق قبلی
          </button>
          <button
            disabled={busy || offset + 25 >= total}
            onClick={() => setOffset((v) => v + 25)}
          >
            سوابق بعدی
          </button>
        </div>
      </section>
      <section className="card">
        <h2>دانش و شواهد مجاز</h2>
        <p>
          فقط متن مجاز ثبت‌شدهٔ مدیر استفاده می‌شود؛ این صفحه وب را جست‌وجو یا
          منبع را دریافت نمی‌کند.
        </p>
        <label>
          جست‌وجوی دانش
          <input
            value={query}
            maxLength={200}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        {sources.map((source) => (
          <article key={source.id}>
            <label className="check">
              <input
                type="checkbox"
                checked={selected.includes(source.id)}
                disabled={
                  busy ||
                  (!source.active && !selected.includes(source.id)) ||
                  role === "viewer" ||
                  (!selected.includes(source.id) && selected.length >= 3)
                }
                onChange={(e) =>
                  setSelected((ids) =>
                    e.target.checked
                      ? [...ids, source.id]
                      : ids.filter((id) => id !== source.id),
                  )
                }
              />
              {source.name} — {source.active ? "معتبر" : "لغوشده"}
            </label>
            <details>
              <summary>متن {source.name}</summary>
              <p style={{ whiteSpace: "pre-wrap" }}>{source.content}</p>
              <p>{source.attribution}</p>
            </details>
            {role === "admin" && source.active && (
              <button disabled={busy} onClick={() => setRevoking(source.id)}>
                لغو اعتبار {source.name}
              </button>
            )}
          </article>
        ))}
        {revoking && (
          <div role="group" aria-label="تأیید لغو منبع">
            <p>سابقه حفظ می‌شود و این منبع دیگر قابل استفاده نخواهد بود.</p>
            <button
              disabled={busy}
              onClick={() =>
                void perform(async () => {
                  await agentApi(
                    `agent-workbench/sources/${revoking}/revoke`,
                    "POST",
                  );
                  setSelected((ids) => ids.filter((id) => id !== revoking));
                  setRevoking(null);
                  if (draft) await open(draft.id);
                })
              }
            >
              تأیید لغو اعتبار منبع
            </button>
            <button onClick={() => setRevoking(null)}>انصراف</button>
          </div>
        )}
        <div className="inline">
          <button
            disabled={sourceOffset === 0}
            onClick={() => setSourceOffset((v) => Math.max(0, v - 25))}
          >
            منابع قبلی
          </button>
          <span>{display(sourceTotal)} منبع</span>
          <button
            disabled={sourceOffset + 25 >= sourceTotal}
            onClick={() => setSourceOffset((v) => v + 25)}
          >
            منابع بعدی
          </button>
        </div>
        {role === "admin" && (
          <details>
            <summary>ثبت منبع مجاز</summary>
            <form
              className="form-grid"
              onSubmit={(e) => {
                e.preventDefault();
                const form = e.currentTarget;
                const data = new FormData(form);
                void perform(async () => {
                  await agentApi("agent-workbench/sources", "POST", {
                    name: data.get("name"),
                    kind: data.get("kind"),
                    content: data.get("content"),
                    attribution: data.get("attribution"),
                    source_url: data.get("source_url") || null,
                    rights_confirmed: data.get("rights") === "on",
                  });
                  form.reset();
                  setSourceOffset(0);
                  setQuery("");
                });
              }}
            >
              <label>
                عنوان منبع
                <input name="name" required maxLength={200} />
              </label>
              <label>
                نوع منبع
                <select name="kind">
                  <option value="internal_note">یادداشت داخلی</option>
                  <option value="public_excerpt">نقل‌قول عمومی مجاز</option>
                </select>
              </label>
              <label>
                متن دانش
                <textarea
                  name="content"
                  required
                  minLength={10}
                  maxLength={1500}
                  rows={4}
                />
              </label>
              <label>
                انتساب و مجوز استفاده
                <input name="attribution" required maxLength={1000} />
              </label>
              <label>
                نشانی مرجع (برای نقل‌قول عمومی الزامی)
                <input
                  name="source_url"
                  type="url"
                  maxLength={2000}
                  dir="ltr"
                />
              </label>
              <label className="check">
                <input name="rights" type="checkbox" required />
                اجازهٔ استفاده از این متن و ارسال آن به مدل محلی را دارم.
              </label>
              <button disabled={busy}>ثبت دانش مجاز</button>
            </form>
          </details>
        )}
      </section>
    </>
  );
}
