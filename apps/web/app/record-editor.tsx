"use client";
import { FormEvent, useRef, useState } from "react";
import {
  type Row,
  type Field,
  translations,
  normalizeDecimalInput,
} from "./workspace-schema";

type DimensionRules = Record<string, { unit: string; required: boolean }>;

function Collection({
  field,
  value,
  set,
  rules,
}: {
  field: Field;
  value: unknown;
  set: (v: unknown) => void;
  rules?: DimensionRules;
}) {
  const type = field.type;
  if (type === "rules" || type === "dimensions") {
    const stored = (value || {}) as Record<string, Record<string, unknown>>;
    const obj =
      type === "dimensions" && rules
        ? Object.fromEntries(
            Object.entries(rules).map(([key, rule]) => [
              key,
              { unit: rule.unit, value: stored[key]?.value ?? "" },
            ]),
          )
        : stored;
    return (
      <fieldset className="collection">
        <legend>{field.label}</legend>
        {Object.entries(obj).map(([key, val]) => (
          <div className="inline" key={key}>
            <span>
              {key}
              {rules && (
                <small> · {rules[key]?.required ? "الزامی" : "اختیاری"}</small>
              )}
            </span>
            {type === "dimensions" ? (
              <input
                aria-label={`مقدار ${key}`}
                required={rules ? !!rules[key]?.required : true}
                inputMode="decimal"
                value={String(val.value || "")}
                onChange={(e) =>
                  set({ ...obj, [key]: { ...val, value: e.target.value } })
                }
              />
            ) : null}
            <select
              disabled={type === "dimensions" && !!rules}
              aria-label={`واحد ${key}`}
              value={String(val.unit || "mm")}
              onChange={(e) =>
                set({ ...obj, [key]: { ...val, unit: e.target.value } })
              }
            >
              {["mm", "cm", "m", "kg", "none"].map((u) => (
                <option key={u}>{u}</option>
              ))}
            </select>
            {type === "rules" && (
              <label>
                <input
                  type="checkbox"
                  checked={!!val.required}
                  onChange={(e) =>
                    set({
                      ...obj,
                      [key]: { ...val, required: e.target.checked },
                    })
                  }
                />{" "}
                الزامی
              </label>
            )}
            {!(type === "dimensions" && rules) && (
              <button
                type="button"
                className="quiet"
                onClick={() =>
                  set(
                    Object.fromEntries(
                      Object.entries(obj).filter(([k]) => k !== key),
                    ),
                  )
                }
              >
                حذف {key}
              </button>
            )}
          </div>
        ))}
        {!(type === "dimensions" && rules) && (
          <div className="inline">
            <input
              aria-label="نام بعد جدید (لاتین)"
              placeholder="thickness"
              id={`new-${type}`}
            />
            <button
              type="button"
              className="quiet"
              onClick={() => {
                const el = document.getElementById(
                  `new-${type}`,
                ) as HTMLInputElement;
                const key = el.value.trim();
                if (/^[A-Za-z0-9_.-]+$/.test(key) && !obj[key]) {
                  set({
                    ...obj,
                    [key]:
                      type === "rules"
                        ? { unit: "mm", required: false }
                        : { unit: "mm", value: "" },
                  });
                  el.value = "";
                }
              }}
            >
              افزودن بعد
            </button>
          </div>
        )}
      </fieldset>
    );
  }
  const rows = (value || []) as Record<string, string>[];
  return (
    <fieldset className="collection">
      <legend>{field.label}</legend>
      {rows.map((row, i) => (
        <div className="inline" key={i}>
          {type === "contacts" && (
            <select
              aria-label={`نوع تماس ${i + 1}`}
              value={row.kind}
              onChange={(e) =>
                set(
                  rows.map((r, j) =>
                    j === i ? { ...r, kind: e.target.value } : r,
                  ),
                )
              }
            >
              <option value="phone">تلفن</option>
              <option value="email">ایمیل</option>
              <option value="contact_person">شخص رابط</option>
            </select>
          )}
          {(type === "contacts"
            ? [
                ["name", "نام"],
                ["value", "مقدار تماس"],
              ]
            : [
                ["city", "شهر"],
                ["address", "نشانی"],
                ["postal_code", "کد پستی"],
              ]
          ).map(([key, label]) => (
            <input
              key={key}
              required={key !== "postal_code"}
              aria-label={`${label} ${i + 1}`}
              placeholder={label}
              value={row[key] || ""}
              onChange={(e) =>
                set(
                  rows.map((r, j) =>
                    j === i ? { ...r, [key]: e.target.value } : r,
                  ),
                )
              }
            />
          ))}
          <button
            type="button"
            className="quiet"
            onClick={() => set(rows.filter((_, j) => j !== i))}
          >
            حذف ردیف {i + 1}
          </button>
        </div>
      ))}
      <button
        type="button"
        className="quiet"
        onClick={() =>
          set([
            ...rows,
            type === "contacts"
              ? { kind: "phone", name: "", value: "" }
              : { city: "", address: "", postal_code: "" },
          ])
        }
      >
        افزودن ردیف
      </button>
    </fieldset>
  );
}
export function Editor({
  fields,
  initial,
  onSave,
  onCancel,
  page,
  refs,
}: {
  fields: Field[];
  initial?: Row;
  onSave: (data: Record<string, unknown>, key: string) => Promise<void>;
  onCancel: () => void;
  page: string;
  refs: Row[];
}) {
  const [values, setValues] = useState<Record<string, unknown>>(() =>
    Object.fromEntries(
      fields.map((f) => [
        f.key,
        initial?.[f.key] ??
          (f.type === "checkbox"
            ? f.key === "active"
            : f.type === "roles"
              ? ["customer"]
              : f.type === "rules" || f.type === "dimensions"
                ? {}
                : f.type === "contacts" || f.type === "addresses"
                  ? []
                  : f.default || ""),
      ]),
    ),
  );
  const dimensionRules = (refs.find((r) => r.id === values.category_id)
    ?.attribute_rules || {}) as DimensionRules;
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const retry = useRef({ signature: "", key: "" });
  function set(key: string, value: unknown) {
    setValues((old) => {
      const next = { ...old, [key]: value };
      if (page === "products" && key === "category_id") {
        const rules =
          (refs.find((r) => r.id === value)?.attribute_rules as Record<
            string,
            { unit: string }
          >) || {};
        next.attributes = Object.fromEntries(
          Object.entries(rules).map(([k, r]) => [
            k,
            { unit: r.unit, value: "" },
          ]),
        );
      }
      return next;
    });
  }
  async function submit(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError("");
    try {
      const data = { ...values };
      if (page === "products") {
        const attributes = (values.attributes || {}) as Record<
          string,
          { unit: string; value: string }
        >;
        data.attributes = Object.fromEntries(
          Object.entries(attributes)
            .filter(
              ([key, dimension]) =>
                dimensionRules[key]?.required ||
                String(dimension.value).trim() !== "",
            )
            .map(([key, dimension]) => [
              key,
              {
                ...dimension,
                value: normalizeDecimalInput(String(dimension.value)),
              },
            ]),
        );
      }
      for (const field of fields) {
        if (field.type === "decimal")
          data[field.key] = normalizeDecimalInput(String(data[field.key]));
        if (field.type === "datetime-local")
          data[field.key] = new Date(String(data[field.key])).toISOString();
        if (field.required === false && data[field.key] === "")
          data[field.key] = null;
      }
      const signature = JSON.stringify(data);
      if (retry.current.signature !== signature)
        retry.current = { signature, key: crypto.randomUUID() };
      await onSave(data, retry.current.key);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }
  return (
    <section className="card">
      <h2>{initial ? "ویرایش رکورد" : "ثبت رکورد جدید"}</h2>
      <form onSubmit={submit} className="form-grid">
        {fields.map((f) =>
          ["rules", "dimensions", "contacts", "addresses"].includes(
            f.type || "",
          ) ? (
            <Collection
              key={f.key}
              field={f}
              value={values[f.key]}
              rules={f.type === "dimensions" ? dimensionRules : undefined}
              set={(v) => set(f.key, v)}
            />
          ) : f.type === "roles" ? (
            <fieldset key={f.key}>
              <legend>نقش‌ها</legend>
              {["customer", "supplier"].map((role) => (
                <label className="check" key={role}>
                  <input
                    type="checkbox"
                    checked={(values.roles as string[]).includes(role)}
                    onChange={(e) =>
                      set(
                        "roles",
                        e.target.checked
                          ? [...(values.roles as string[]), role]
                          : (values.roles as string[]).filter(
                              (r) => r !== role,
                            ),
                      )
                    }
                  />
                  {translations[role]}
                </label>
              ))}
            </fieldset>
          ) : (
            <label key={f.key}>
              {f.label}
              {f.required !== false && f.type !== "checkbox" ? " *" : ""}
              {f.options ? (
                <select
                  required={f.required !== false}
                  value={String(values[f.key] || "")}
                  onChange={(e) => set(f.key, e.target.value)}
                >
                  <option value="">انتخاب کنید</option>
                  {f.options.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              ) : f.type === "checkbox" ? (
                <input
                  type="checkbox"
                  checked={!!values[f.key]}
                  onChange={(e) => set(f.key, e.target.checked)}
                />
              ) : (
                <input
                  required={f.required !== false}
                  maxLength={f.type === "decimal" ? 30 : 1000}
                  type={f.type === "decimal" ? "text" : f.type || "text"}
                  inputMode={f.type === "decimal" ? "decimal" : undefined}
                  value={String(values[f.key] || "")}
                  onChange={(e) => set(f.key, e.target.value)}
                />
              )}
            </label>
          ),
        )}
        {error && (
          <p className="error full" role="alert">
            {error}
          </p>
        )}
        <div className="actions full">
          <button disabled={saving}>
            {saving ? "در حال ذخیره…" : "ذخیره"}
          </button>
          <button type="button" className="quiet" onClick={onCancel}>
            انصراف
          </button>
        </div>
      </form>
    </section>
  );
}
