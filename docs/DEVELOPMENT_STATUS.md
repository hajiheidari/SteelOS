# وضعیت توسعه SteelOS

## بستهٔ backend — 2026-10-22

- شاخه: `codex/m1-foundation`؛ مبنای بررسی: `6a8127e`، بدون تغییر در `main`.
- پیاده‌شده: PostgreSQL، SQLAlchemy، migration اولیه Alembic، نشست‌های Argon2 و opaque token با rotation/revocation، عضویت سازمانی، نقش‌های admin/editor/viewer و کنترل دسترسی.
- کاتالوگ با قواعد ابعاد قابل توسعه، SKU و مشخصات یکتا؛ CRM چندنقشی؛ انبار و مکان سلسله‌مراتبی با مجوز انبار؛ قیمت دستی و adapter محلی، تاریخچه و تصمیم تأیید؛ audit و idempotency.
- آزمون: ۸ تست روی PostgreSQL 17 موفق؛ تست‌های سلامت، احراز هویت، جداسازی سازمان، محدودیت FK، کالا، CRM، انبار، قیمت و OpenAPI.
- CI مبنای قبلی دو بار بدون اجرای هیچ step ناموفق بوده؛ علت هنوز از GitHub قابل تشخیص نیست. CI جدید پس از push باید بررسی شود.
- محدودیت فعلی: UI، آزمون مرورگر، مستندات کامل راه‌اندازی و تأیید CI هنوز باقی است. M1 کامل اعلام نمی‌شود.
- بستهٔ بعد: داشبورد Persian RTL متصل به API، گسترش آزمون‌ها و مستندات و بررسی clean setup.
- هیچ سرویس پولی، استقرار عمومی، merge یا تغییر main انجام نشده است.

## بستهٔ داشبورد و پذیرش محلی — 2026-10-22

- شاخه: `codex/m1-foundation`؛ commit قبلی backend: `a9a991e`؛ شناسهٔ دقیق این بسته در تاریخچهٔ Git ثبت می‌شود و در به‌روزرسانی بعدی گزارش درج خواهد شد.
- پیاده‌شده: Next.js/TypeScript، همهٔ صفحات اصلی Persian RTL، فرم‌های واقعی کالا و ابعاد، CRM و تماس/نشانی، انبار و سلسله‌مراتب، منبع/مشاهده/تأیید قیمت، کاربران/نقش‌ها/مجوز انبار و تغییر رمز/نام سازمان.
- cookie با HttpOnly و SameSite Strict؛ Secure در build تولیدی، بررسی APP_ORIGIN برای mutation، بدون bearer در localStorage یا پاسخ قابل مشاهدهٔ مرورگر.
- بررسی محلی: ۱۴ تست backend روی PostgreSQL 17، شامل migration roundtrip، جداسازی همهٔ master resourceها، FK سازمانی، retry هم‌زمان و adapter واقعی از مسیر API، موفق شدند.
- ۶ تست Playwright برای desktop/mobile روی build تولیدی موفق شدند؛ ورود، CRUD طرف تجاری، کاتالوگ/ابعاد، انبار/مکان، دریافت و تأیید قیمت و CSRF پوشش داده شده‌اند. build و TypeScript و auditهای Python/npm موفق‌اند.
- راه‌اندازی Compose با volume خالی، اجرای migration توسط کاربر غیر root، health/ready، alembic check و bootstrap تعاملی حساب مدیر بررسی شد. پورت‌ها فقط loopback هستند.
- قراردادهای lot/movement/reservation و مرز حسابداری/تطبیق موازی مستند شده‌اند؛ هیچ ماندهٔ قابل ویرایش، موتور حسابداری ناقص یا API عملیاتی موجودی اضافه نشده است.
- نقص شناخته‌شدهٔ مسدودکنندهٔ محلی: در بررسی‌های انجام‌شده مشاهده نشد. هشدار غیرمسدودکننده: TestClient نسخهٔ Starlette دربارهٔ جایگزینی آیندهٔ httpx هشدار می‌دهد.
- محدودیت‌ها: password recovery/MFA، offline sync، autocomplete سمت سرور برای مجموعه‌های بزرگ، تست نفوذ و عملیات production خارج از این بسته‌اند؛ سطح پوشش مرورگر همهٔ ترکیب‌های خطا را شامل نمی‌شود.
- مانع پذیرش M1: GitHub Actions به‌علت خطای billing/spending limit حساب، job را قبل از هر step متوقف می‌کند. پیام رسمی: “The job was not started because recent account payments have failed or your spending limit needs to be increased.” هیچ تغییری در تنظیمات مالی انجام نشده است.
- کار باقی‌ماندهٔ M1: اجرای واقعی CI پس از رفع مانع حساب GitHub، بررسی founder و رفع یافته‌های احتمالی. M1 کامل یا production-ready اعلام نمی‌شود.
- بستهٔ بعد: بازبینی نتیجهٔ CI و یافته‌های پذیرش؛ شروع M2 در این تغییر انجام نمی‌شود.
- main تغییر نکرده؛ merge، استقرار عمومی، سرویس پولی یا ارسال قانونی انجام نشده است.
