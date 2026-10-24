"use client";
import { useEffect, useState } from "react";
import {
  api,
  display,
  normalizeDecimalInput,
  type Row,
} from "./workspace-schema";

export function TaxPolicySettings() {
  const [policy, setPolicy] = useState<Row | null>(null);
  const [rate, setRate] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  useEffect(() => {
    let active = true;
    void api("organization/tax-policy")
      .then((value) => {
        if (active) {
          setPolicy(value);
          setRate(String(value.tax_rate_percent));
        }
      })
      .catch((e) => {
        if (active) setError((e as Error).message);
      });
    return () => {
      active = false;
    };
  }, []);
  return (
    <form
      className="inline"
      onSubmit={(e) => {
        e.preventDefault();
        if (!policy || busy) return;
        setBusy(true);
        setError("");
        setNotice("");
        void api("organization/tax-policy", "PUT", {
          tax_rate_percent: normalizeDecimalInput(rate),
          expected_version: policy.version,
        })
          .then((value) => {
            setPolicy(value);
            setRate(String(value.tax_rate_percent));
            setNotice("نرخ پیش‌فرض ذخیره شد؛ نرخ اسناد قبلی تغییر نکرد.");
          })
          .catch((e) => setError((e as Error).message))
          .finally(() => setBusy(false));
      }}
    >
      <p>
        مالیات جدا از قیمت پایه؛ مبلغ هر ردیف با دو رقم اعشار و گردکردن معمول
        محاسبه می‌شود. ارز فاکتور ایران ریال است. این نرخ برای پیش‌نویس‌های جدید
        است و اعلام ضابطهٔ قانونی نیست.
      </p>
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
      <label>
        درصد پیش‌فرض مالیات بر ارزش افزوده
        <input
          required
          inputMode="decimal"
          maxLength={10}
          value={rate}
          disabled={busy || !policy}
          onChange={(e) => setRate(e.target.value)}
        />
      </label>
      {policy && (
        <p className="muted">نسخهٔ تنظیمات: {display(policy.version)}</p>
      )}
      <button disabled={busy || !policy}>ذخیره نرخ پیش‌فرض مالیات</button>
      <button
        type="button"
        disabled={busy}
        onClick={() => {
          setBusy(true);
          void api("organization/tax-policy")
            .then((value) => {
              setPolicy(value);
              setRate(String(value.tax_rate_percent));
              setError("");
            })
            .catch((e) => setError((e as Error).message))
            .finally(() => setBusy(false));
        }}
      >
        دریافت آخرین نرخ مالیات
      </button>
    </form>
  );
}
