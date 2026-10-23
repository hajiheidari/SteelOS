# پیشنهاد دامنهٔ M2 — نیازمند تصمیم founder، پیاده‌سازی نشده

## خروجی پیشنهادی

یک زیرسیستم عملیاتی محدود انبار، روی foundation مصوب M1:

1. lot با product، واحد، warehouse/location و مالک حقوقی مستقل: company یا party مشخص.
2. receipt/dispatch/transfer به شکل ledger append-only، با reference کسب‌وکار و idempotency.
3. block/unblock و reservation/release/fulfillment، بدون فیلد balance قابل ویرایش.
4. نمای مشتق‌شدهٔ موجودی، blocked/reserved/available در scope سازمان/مالک/کالا/lot/location/unit.
5. اصلاح از طریق reversal مرتبط؛ نه ویرایش/حذف گردش ثبت‌شده.
6. API، migration، UI فارسی، audit و تست race/tenant isolation برای هر batch کوچک.

## پیشنهاد اختیار ثبت برای نسخهٔ اول

- viewer: مشاهده در انبارهای مجاز.
- editor: تهیهٔ پیش‌نویس؛ بدون اثر بر موجودی تا تأیید.
- admin: تأیید/ثبت نهایی و reversal در سازمان خود، با audit و کنترل invariant.
- این پیشنهاد برای کالای شرکت و کالای مشتری یکسان است؛ انتقال محل هیچ‌گاه انتقال مالکیت نیست.
- عامل AI اجازهٔ نوشتن مستقیم ledger یا تأیید نهایی ندارد.

این ماتریس پیشنهادی یک تصمیم عملیاتی کسب‌وکار است و در کد اجرا نشده؛ founder باید آن را
تأیید یا اصلاح کند، خصوصاً دربارهٔ اختیار editor برای خروج کالای مشتری.

## invariantها و آزمون پذیرش پیشنهادی

- quantities از Decimal و NUMERIC(20,3)، واحد صریح و بدون تبدیل ضمنی؛ مالک third-party اجباری.
- موجودی منفی و over-reservation رد می‌شود؛ دو درخواست هم‌زمان آخرین موجودی را دوباره مصرف نمی‌کنند.
- transfer اتمیک، مجموع quantity و مالکیت را حفظ می‌کند؛ هر دو انبار باید مجاز باشند.
- ثبت نهایی و اثر ledger یک تراکنش با audit/idempotency هستند؛ پیش‌نویس اثر موجودی ندارد.
- retry ثبت یا reversal نتیجهٔ تکراری می‌دهد؛ هیچ حرکت دوباره ثبت نمی‌شود.
- FK و API جلوی ارتباط cross-organization را می‌گیرند؛ location باید داخل warehouse همان lot باشد.
- timestamp رخداد UTC و posting time مستقل؛ backdating و دوره‌بندی فراتر از receipt جاری قبل از طراحی روشن نمی‌شوند.

## ترتیب batchهای پیشنهادی

1. قرارداد persistence و migration lot/draft/event و تست قیود مالکیت؛ بدون UI فریبندهٔ balance.
2. دریافت و خروج با اختیار مصوب، idempotency و کنترل هم‌زمانی؛ UI فارسی.
3. transfer اتمیک و reversal با audit و تست conserved quantity.
4. reservation/block و نمای available با تست رقابت و دسترسی انبار.
5. پذیرش end-to-end، clean setup و CI، مستندات و گزارش واقعی محدودیت‌ها.

## خارج از این پیشنهاد

ترید Spot/Salaf/Forward، قرارداد فروش/خرید کامل، پرداخت/اعتبار، قیمت‌گذاری quotation نهایی،
ارزش‌گذاری حسابداری، journal، ارسال مالیاتی، OCR، paid feeds، scraping، deployment و تغییر main.
اتصال این ماژول به معاملات/حسابداری بعداً به دامنه و بررسی مستقل نیاز دارد.
