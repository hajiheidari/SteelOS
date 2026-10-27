"""Versioned product training; deterministic self-checks, not generated/legal advice."""

from typing import Annotated, Literal

from app.schemas import Input, StoredText
from pydantic import Field, StrictInt

VERSION = "foundation-learning-v1"
LESSONS = [
    {
        "id": "ownership",
        "title": "مالکیت و محل نگهداری",
        "reference": "docs/M2_WAREHOUSE_ACCEPTANCE.md",
        "reference_title": "قواعد مستند عملیات انبار",
        "paragraphs": [
            "مالک قانونی کالا و محل نگهداری آن دو دادهٔ جدا هستند. نگهداری در انبار شرکت به معنی مالکیت شرکت نیست.",
            "در این مثال فرضی، مشتری الف مالک ورق است و ورق در انبار شرکت ب نگهداری می‌شود. جابه‌جایی محل، به‌تنهایی مالکیت را منتقل نمی‌کند.",
        ],
        "questions": [
            {
                "id": "owner",
                "prompt": "مالک ورق در مثال چه کسی است؟",
                "options": ["مشتری الف", "شرکت ب به دلیل انبارداری", "خود انبار"],
                "answer": 0,
                "explanation": "مشتری الف مالک است؛ انبار شرکت ب فقط محل نگهداری معرفی شده است.",
            },
            {
                "id": "move",
                "prompt": "تغییر محل نگهداری، به‌تنهایی چه اثری بر مالکیت دارد؟",
                "options": [
                    "مالکیت را به انبار مقصد می‌دهد",
                    "مالکیت را تغییر نمی‌دهد",
                    "کالا را بی‌مالک می‌کند",
                ],
                "answer": 1,
                "explanation": "انتقال فیزیکی محل با انتقال مالکیت یکی نیست.",
            },
        ],
    },
    {
        "id": "pricing",
        "title": "اعتبار و منشأ قیمت",
        "reference": "docs/REQUIREMENTS.md",
        "reference_title": "نیازمندی‌های تأییدشدهٔ محصول",
        "paragraphs": [
            "قیمت باید منشأ، زمان مشاهده، اعتبار، ارز، واحد و شرایط تحویل مشخص داشته باشد. ورود دستی قیمت مجاز است؛ منشأ آن همچنان باید ثبت شود.",
            "تأییدشدن قیمت، انقضای آن را بی‌اثر نمی‌کند. قیمت منقضی یا تأییدنشده مبنای اعلام قیمت تأییدشده به مشتری نیست.",
        ],
        "questions": [
            {
                "id": "expired",
                "prompt": "قیمتی قبلاً تأیید شده ولی اکنون منقضی است؛ کدام پاسخ درست است؟",
                "options": [
                    "همیشه معتبر می‌ماند",
                    "برای اعلام قیمت تأییدشدهٔ جاری کافی نیست",
                    "می‌توان تاریخ آن را حدس زد",
                ],
                "answer": 1,
                "explanation": "وضعیت تأیید و بازهٔ اعتبار هر دو باید بررسی شوند.",
            },
            {
                "id": "manual",
                "prompt": "در ورود دستی قیمت کدام کار لازم است؟",
                "options": [
                    "حذف منشأ",
                    "ثبت بدون ارز و واحد",
                    "ثبت منشأ و مشخصات اعتبار، ارز، واحد و تحویل",
                ],
                "answer": 2,
                "explanation": "دستی‌بودن ورود، نیاز به شناسنامهٔ قیمت را حذف نمی‌کند.",
            },
        ],
    },
    {
        "id": "sales-draft",
        "title": "سند فروش داخلی و محاسبات",
        "reference": "docs/SALES_DRAFTS.md",
        "reference_title": "قواعد سند فروش داخلی",
        "paragraphs": [
            "سند فروش این مرحله داخلی و غیرالزام‌آور است؛ بازبینی داخلی، تأیید مالی یا صدور سند برای مشتری نیست.",
            "قاعدهٔ تأییدشدهٔ داخلی، ریال و دو رقم اعشار با گردکردن معمول است: ۱۲۳٫۴۵۶ به ۱۲۳٫۴۶ تبدیل می‌شود. پایه و مالیات هر ردیف جدا گرد و جمع سند از جمع همین ردیف‌ها ساخته می‌شود.",
            "مالیات جدا به پایه اضافه می‌شود. نرخ پیش‌فرض داخلی فعلاً ۱۰٪ و قابل تنظیم است؛ این آموزش ادعای نرخ قانونی یا انطباق مالیاتی ندارد.",
        ],
        "questions": [
            {
                "id": "rounding",
                "prompt": "در قاعدهٔ داخلی دو اعشار، ۱۲۳٫۴۵۶ چگونه ثبت می‌شود؟",
                "options": ["۱۲۳٫۴۵", "۱۲۳٫۴۶", "۱۲۴٫۰۰"],
                "answer": 1,
                "explanation": "در گردکردن معمول رقم سوم ۵ یا بیشتر، رقم دوم را بالا می‌برد.",
            },
            {
                "id": "approval",
                "prompt": "بازبینی داخلی سند فروش چه معنایی دارد؟",
                "options": [
                    "صدور خودکار فاکتور قانونی",
                    "تأیید مالی خودکار",
                    "بررسی داخلی همان نسخه؛ بدون صدور یا تأیید مالی",
                ],
                "answer": 2,
                "explanation": "بررسی داخلی هیچ مجوز ارسال، ثبت قانونی یا تأیید مالی ایجاد نمی‌کند.",
            },
        ],
    },
]


class CheckInput(Input):
    version: Literal["foundation-learning-v1"]
    answers: Annotated[
        dict[Annotated[StoredText, Field(min_length=1, max_length=40)], StrictInt],
        Field(min_length=1, max_length=10),
    ]


def catalog():
    return {
        "version": VERSION,
        "generated_by_model": False,
        "progress_persisted": False,
        "lessons": [
            {
                **lesson,
                "questions": [
                    {k: v for k, v in question.items() if k not in ("answer", "explanation")}
                    for question in lesson["questions"]
                ],
            }
            for lesson in LESSONS
        ],
    }
