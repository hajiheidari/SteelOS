"use client";
import { useEffect, useId, useRef, useState } from "react";
import { api, display, type Row } from "./workspace-schema";

type Props = {
  label: string;
  resource: string;
  name?: string;
  value?: string;
  selectedOption?: Row | null;
  required?: boolean;
  disabled?: boolean;
  emptyLabel?: string;
  optionLabel?: (row: Row) => string;
  onChange?: (row: Row | null) => void;
};

/** Native select with bounded server search; selected values survive page changes. */
export function RemoteSelect({
  label,
  resource,
  name,
  value,
  selectedOption,
  required,
  disabled,
  emptyLabel = "انتخاب کنید",
  optionLabel = (row) => String(row.name || row.code),
  onChange,
}: Props) {
  const id = useId();
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [rows, setRows] = useState<Row[]>([]);
  const [total, setTotal] = useState(0);
  const [selected, setSelected] = useState<Row | null>(null);
  const [internalValue, setInternalValue] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const sequence = useRef(0);
  const current = value ?? internalValue;
  useEffect(() => {
    const request = ++sequence.current;
    setLoading(Boolean(resource));
    setError("");
    setRows([]);
    if (!resource) {
      setTotal(0);
      return;
    }
    const timer = setTimeout(
      async () => {
        try {
          const separator = resource.includes("?") ? "&" : "?";
          const data = await api(
            `${resource}${separator}limit=25&offset=${offset}&q=${encodeURIComponent(query)}`,
          );
          if (request !== sequence.current) return;
          setRows(data.items);
          setTotal(data.total);
        } catch (e) {
          if (request === sequence.current) {
            setError((e as Error).message);
            setTotal(0);
          }
        } finally {
          if (request === sequence.current) setLoading(false);
        }
      },
      query ? 250 : 0,
    );
    return () => {
      clearTimeout(timer);
      sequence.current += 1;
    };
  }, [resource, query, offset]);
  const saved = selectedOption || selected;
  const options =
    saved && current === saved.id && !rows.some((row) => row.id === current)
      ? [saved, ...rows]
      : rows;
  return (
    <div className="remote-select">
      <label htmlFor={id}>{label}</label>
      <input
        aria-label={`جست‌وجوی ${label}`}
        placeholder="جست‌وجوی گزینه‌ها…"
        onKeyDown={(event) => {
          if (event.key === "Enter") event.preventDefault();
        }}
        value={query}
        disabled={disabled || !resource}
        maxLength={200}
        onChange={(e) => {
          if (e.target.value === query) return;
          sequence.current += 1;
          setQuery(e.target.value);
          setOffset(0);
        }}
      />
      <select
        id={id}
        name={name}
        required={required}
        value={current}
        disabled={disabled || !resource}
        aria-busy={loading}
        onChange={(e) => {
          const row = options.find((row) => row.id === e.target.value) || null;
          setInternalValue(e.target.value);
          setSelected(row);
          onChange?.(row);
        }}
      >
        <option value="">{emptyLabel}</option>
        {options.map((row) => (
          <option key={row.id} value={row.id}>
            {optionLabel(row)}
          </option>
        ))}
      </select>
      <div className="toolbar">
        <button
          type="button"
          className="quiet"
          aria-label={`گزینه‌های قبلی ${label}`}
          disabled={disabled || loading || offset === 0}
          onClick={() => {
            sequence.current += 1;
            setOffset(offset - 25);
          }}
        >
          قبلی
        </button>
        <span role="status">
          {loading ? "در حال جست‌وجو…" : `${display(total)} گزینه`}
        </span>
        <button
          type="button"
          className="quiet"
          aria-label={`گزینه‌های بعدی ${label}`}
          disabled={disabled || loading || offset + 25 >= total}
          onClick={() => {
            sequence.current += 1;
            setOffset(offset + 25);
          }}
        >
          بعدی
        </button>
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
