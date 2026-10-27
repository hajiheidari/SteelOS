"""Small synthetic native-OCR regression, not a language/financial accuracy benchmark."""

import io
import json
from datetime import UTC, datetime

from app.modules.invoices.ocr import extract
from app.modules.invoices.parser import propose
from PIL import Image, ImageDraw, ImageFont
from test_invoice_intake import image_bytes


def main():
    cases = []
    for format, media in (("PNG", "image/png"), ("PDF", "application/pdf")):
        cases.append(
            (
                "synthetic-English-" + format,
                image_bytes(format),
                media,
                {"invoice_number": "12345", "grand_total": "271.59"},
            )
        )
    image = Image.new("RGB", (1400, 650), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 44)
    for index, line in enumerate(
        ("فروشنده: فولاد", "خریدار: آزمون", "شماره فاکتور: ۱۲۳۴۵", "مبلغ کل: ۱۲۳۴٫۵۶", "ریال")
    ):
        draw.text(
            (1320, 40 + index * 100), line, font=font, fill="black", direction="rtl", anchor="ra"
        )
    data = io.BytesIO()
    image.save(data, format="PNG")
    cases.append(
        (
            "synthetic-Persian-PNG",
            data.getvalue(),
            "image/png",
            {
                "seller_name": "فولاد",
                "buyer_name": "آزمون",
                "invoice_number": "۱۲۳۴۵",
                "grand_total": "1234.56",
            },
        )
    )
    results = []
    for name, content, media, expected in cases:
        raw, pages, engine = extract(content, media)
        proposal = propose(raw)
        observed = {key: proposal["fields"].get(key) for key in expected}
        results.append(
            {
                "case": name,
                "engine": engine,
                "pages": pages,
                "raw_text": raw,
                "expected": expected,
                "observed": observed,
                "exact_match": observed == expected,
            }
        )
    report = {
        "recorded_at": datetime.now(UTC).isoformat(),
        "scope": "Three synthetic native OCR cases; no production/general-language or financial accuracy claim",
        "warning": "OCR can drop decimal separators; human comparison with the original is mandatory. No inferred numeric repair.",
        "results": results,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
