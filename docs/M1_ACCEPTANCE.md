# بازبینی پذیرش M1

این گزارش قابلیت‌های پیاده‌شده و شواهد خودکار را از کارهای آینده جدا می‌کند.
نتیجه و commit آخرین اجرای واقعی CI در `DEVELOPMENT_STATUS.md` ثبت می‌شود.

| معیار | پیاده‌سازی / شاهد |
| --- | --- |
| clean setup و اتصال DB | README، Compose، health/ready؛ راه‌اندازی volume خالی و bootstrap مدیر بررسی شده |
| migration | Alembic baseline، roundtrip upgrade/downgrade/upgrade و model drift در `test_migrations.py` |
| احراز هویت | Argon2، opaque sessions، rotation/revocation، throttle، تغییر رمز؛ `test_foundation.py` و `test_settings.py` |
| جداسازی سازمان | query scope، FK مرکب، CRUD خارج از سازمان و permission matrix در تست‌های backend |
| مجوز هم‌زمان | mutual admin removal/demotion و writeهای queued پس از تغییر عضویت؛ `test_settings.py` و `test_permission_concurrency.py` |
| کاتالوگ | CRUD، SKU/spec uniqueness، قواعد ابعاد، شناسه‌ها، جستجو/فیلتر؛ تست domain و `test_catalog_concurrency.py` |
| CRM | حقیقی/حقوقی، customer/supplier هم‌زمان، تماس/نشانی، CRUD، ثبت یکتای registration ID موجود |
| انبار | انبار مستقل، hierarchy، cycle prevention، grants؛ بدون ماندهٔ دستی؛ قراردادهای آیندهٔ مالکیت/lot/movement/reservation |
| قیمت | دستی/mock، provenance و currency/unit/tax/delivery، history، تصمیم مدیر، رد expiry/source نامعتبر، idempotency |
| dashboard فارسی | صفحات اصلی متصل به API، RTL، responsive، Jalali، ارقام فارسی/عربی و precision رشته‌ای |
| فرم و نشست مرورگر | ابعاد اختیاری/اجباری، واحد ثابت، ورود و خروج، cookie HttpOnly، رفتار رمز اشتباه/token revoked و پاسخ دیررس |
| audit و خطا | audit تراکنشی، validation redaction، consistent error envelope و request ID |
| تست و CI | PostgreSQL واقعی، 24 تست backend و 12 تست production-browser در مجموعهٔ فعلی؛ نتیجهٔ آخرین run را جداگانه بررسی کنید |
| مرزهای مجاز | main دست‌نخورده؛ بدون merge، public deployment، paid service، statutory submission یا موتور حسابداری ناقص |

## آنچه موفقیت تست اثبات نمی‌کند

آمادگی production، انطباق مالیاتی، بازیابی رمز/MFA، backup/restore عملیاتی، تست نفوذ،
مقیاس بالای pickerها و همهٔ سناریوهای کسب‌وکار ادعا نمی‌شود. این محدودیت‌ها در SECURITY،
DATA_MODEL و ARCHITECTURE مشخص‌اند. CI جایگزین پذیرش کسب‌وکار نیست.

## مرز تصمیم بعدی

دامنهٔ اجرایی مصوب فعلی M1 است. هیچ API عملیاتی inventory/trading/accounting در این
بسته ساخته نشده است. پیشنهاد M2 در `M2_SCOPE_PROPOSAL.md` صرفاً طرح قابل بازبینی است؛
شروع آن نیازمند تأیید دامنه و قاعدهٔ انسانی اختیار ثبت گردش کالا است. پذیرش این طرح،
مجوز merge در main یا استقرار عمومی محسوب نمی‌شود.
