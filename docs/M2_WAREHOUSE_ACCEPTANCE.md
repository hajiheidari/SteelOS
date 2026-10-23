# پذیرش دامنهٔ محدود عملیات انبار M2

دامنهٔ این گزارش همان پیشنهاد تأییدشدهٔ انبار است؛ تکمیل کل roadmap معاملات یا حسابداری نیست.
شاخه: `codex/m1-foundation`، backend اولیه: `b97c3e5`، رابط: `ac31269`، اصلاحات مجوز/هم‌زمانی: `7a5c71c` و `ad60a5c`.

| معیار | پیاده‌سازی و شاهد |
|---|---|
| مالکیت مستقل از محل | lot ثابت company/party؛ ledger با موقعیت‌های متعدد؛ آزمون مالک شرکت/مشتری در یک محل |
| اختیار ثبت | editor پیش‌نویس و admin posting/reject؛ viewer فقط انبار مجاز؛ آزمون tenant/grant |
| تاریخچهٔ غیرقابل ویرایش | signed entries، trigger منع update/delete؛ اصلاح با reversal کامل |
| دریافت/خروج/انتقال | یک تراکنش با audit/idempotency؛ انتقال مقدار و مالک را حفظ می‌کند |
| جلوگیری از مصرف تکراری | قفل lot؛ آزمون دو actor برای خروج، رزرو و انتقال با یک موفق/یک conflict |
| رزرو و مسدودی | reserve/release/fulfill و block/unblock؛ انقضای UTC بدون worker؛ آزمون expiry/dependency |
| مانده | مشتق‌شدهٔ on_hand/blocked/active reserved/available؛ بدون balance قابل ویرایش |
| migration | clean head، ارتقای M1 دارای داده، حفظ داده، downgrade/upgrade و model drift موفق |
| رابط فارسی | فرم lot و تمام انواع عملیات؛ جدول موجودی/گردش/رزرو؛ تأیید صریح مدیر؛ pagination/filter |
| مرورگر | ۱۴ تست production desktop/mobile؛ چرخهٔ دریافت، رزرو، fulfill/release، block/unblock، انتقال، برگشت و رد خروج نامعتبر |
| راه‌اندازی پاک | Docker Compose با volume مستقل و image تازه؛ health/ready و alembic check موفق |

۳۸ تست backend، Ruff، TypeScript و build محلی موفق‌اند. نتیجهٔ CI ثبت‌شده در
[DEVELOPMENT_STATUS.md](DEVELOPMENT_STATUS.md) مرجع نتیجهٔ اجرای GitHub است.

## محدودیت‌های عملیاتی

- lot/پیش‌نویس edit/delete ندارند؛ اصلاح draft با reject/new، اصلاح posted با reversal/new.
- تنها برگشت کامل یک گردش مجاز است؛ برگشت وابسته ممکن است به‌علت ماندهٔ ناکافی رد شود.
- انتقال مالکیت، تبدیل واحد، تاریخ‌گذاری گذشته، ارزش‌گذاری، اسناد خرید/فروش و مالیات اجرا نشده‌اند.
- تاریخ انقضای فرم بر اساس زمان محلی دستگاه است و با برچسب صریح به UTC تبدیل می‌شود.
- فهرست‌های انتخاب فرم در این نسخه تمام صفحات دادهٔ مجاز را بارگذاری می‌کنند؛ برای حجم بسیار
  بزرگ، جست‌وجوی راه‌دور و سنجش عملکرد پیش از استفادهٔ عملیاتی لازم است.
- این نسخه گواهی قانونی/حسابداری یا مجوز استقرار عمومی نیست؛ پذیرش کسب‌وکار با founder است.
