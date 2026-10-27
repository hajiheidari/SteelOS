"""Conservative labelled candidates; raw text remains authoritative extraction evidence."""

import re

from app.modules.invoices.schemas import InvoiceFields, InvoiceLine
from pydantic import ValidationError

DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
LABELS = {
    "invoice_number": ("شماره فاکتور", "شماره صورتحساب", "invoice number", "invoice no"),
    "invoice_date_text": ("تاریخ", "date"),
    "seller_name": ("فروشنده", "seller"),
    "buyer_name": ("خریدار", "buyer"),
    "subtotal": ("جمع قبل از مالیات", "subtotal"),
    "tax_total": ("مبلغ مالیات", "tax total"),
    "grand_total": ("مبلغ کل", "grand total"),
}


def number(value):
    value = value.strip().translate(DIGITS).replace("٫", ".")
    if "٬" in value or "," in value:
        if not re.fullmatch(r"[0-9]{1,3}([٬,][0-9]{3})+(\.[0-9]+)?", value):
            raise ValueError("Ambiguous grouping")
        value = value.replace("٬", "").replace(",", "")
    if not re.fullmatch(r"[0-9]+(\.[0-9]+)?", value):
        raise ValueError("Explicit unsigned decimal required")
    return value


def propose(text):
    data, evidence, warnings = {}, {}, ["manual_review_required"]
    for key, labels in LABELS.items():
        matches = []
        for line in text.splitlines():
            for label in labels:
                found = re.fullmatch(re.escape(label) + r"\s*[:：]\s*(.+)", line.strip(), re.I)
                if found:
                    matches.append((found.group(1).strip(), line))
        if len(matches) == 1:
            value, line = matches[0]
            try:
                candidate = (
                    number(value) if key in ("subtotal", "tax_total", "grand_total") else value
                )
                InvoiceFields.model_validate({key: candidate})
                data[key], evidence[key] = candidate, line
            except (ValueError, ValidationError):
                warnings.append("unparsed_" + key)
        elif matches:
            warnings.append("ambiguous_" + key)
    currencies = set()
    for code, label in (("IRR", "ریال"), ("IRT", "تومان"), ("USD", "دلار"), ("EUR", "یورو")):
        if re.search(r"(?<!\w)(?:" + code + "|" + label + r")(?!\w)", text, re.I):
            currencies.add(code)
    if len(currencies) == 1:
        data["currency"] = currencies.pop()
    else:
        warnings.append("currency_requires_review")
    lines = []
    for line in text.splitlines():
        cells = [cell.strip() for cell in line.split("|")]
        if len(cells) == 5:
            if len(lines) >= 100:
                warnings.append("line_limit_requires_manual_review")
                continue
            try:
                item = InvoiceLine(
                    description=cells[0],
                    quantity=number(cells[1]),
                    unit=cells[2],
                    unit_price=number(cells[3]),
                    line_total=number(cells[4]),
                )
                lines.append(item.model_dump(mode="json"))
                evidence[f"lines/{len(lines) - 1}"] = line
            except (ValueError, ValidationError):
                warnings.append("unparsed_table_row")
    data["lines"] = lines
    if not lines:
        warnings.append("line_items_require_manual_entry")
    return {
        "fields": InvoiceFields.model_validate(data).model_dump(mode="json"),
        "evidence": evidence,
        "warnings": sorted(set(warnings)),
        "parser": "labelled-v1",
    }
