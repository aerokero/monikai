"""Structured bank-statement extraction for the Savings workspace.

The importer deliberately separates extraction from saving.  A statement is
parsed into reviewable rows; the browser decides which rows and which wallet
will be committed.  This is important for financial data: a language model or
an OCR result may suggest a merchant/category, but it must not silently alter
the ledger.

PKO Bank Polski statements are handled with a layout-aware parser because the
PDF already contains a reliable transaction id, signed amount and post-entry
balance.  CSV/TSV/JSON/plain-text exports use a small generic adapter.
"""

from __future__ import annotations

import csv
import io
import json
import re
import unicodedata
from hashlib import sha256
from pathlib import Path
from typing import Any


MAX_STATEMENT_BYTES = 25 * 1024 * 1024
MAX_STATEMENT_ROWS = 2000

_DATE_TOKEN = r"\d{2}[./]\d{2}[./]\d{4}"
_ISO_DATE_TOKEN = r"20\d{2}[-/.]\d{1,2}[-/.]\d{1,2}"
_NUMBER_TOKEN = r"[+-]?\s*(?:\d{1,3}(?:[ \u00a0.]\d{3})+|\d+),\d{2}"
_PKO_HEADER_RE = re.compile(
    rf"^\s*(?P<date>{_DATE_TOKEN})\s+"
    rf"(?P<external_id>[A-Za-z0-9][A-Za-z0-9_-]{{8,}})\s+"
    rf"(?P<operation>.+?)\s+(?P<amount>{_NUMBER_TOKEN})\s+"
    rf"(?P<balance>{_NUMBER_TOKEN})\s*$",
    re.IGNORECASE,
)
_DATE_RE = re.compile(rf"\b{_DATE_TOKEN}\b")
_DATE_ANY_RE = re.compile(rf"\b(?:{_DATE_TOKEN}|{_ISO_DATE_TOKEN})\b")
_PERIOD_RE = re.compile(rf"za\s+okres\s+(?P<start>{_DATE_TOKEN})\s*-\s*(?P<end>{_DATE_TOKEN})", re.IGNORECASE)
_AMOUNT_RE = re.compile(rf"(?P<amount>{_NUMBER_TOKEN})")


class StatementParseError(ValueError):
    """Raised when a document cannot be converted into ledger rows."""


def _fold(value: object) -> str:
    text = str(value or "")
    return "".join(
        char for char in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(char)
    ).lower()


def _clean_line(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\u00a0", " ")).strip()


def _lines(text: str) -> list[str]:
    return [_clean_line(line) for line in str(text or "").splitlines() if _clean_line(line)]


def _parse_amount(value: object) -> float:
    """Parse Polish and international bank notation.

    Statements exported by Polish banks usually use a space for thousands
    and a comma for decimals (``-2 885,72``), while CSV/JSON exports often use
    ``2885.72`` or ``2,885.72``.  Normalize both forms before converting.
    """
    raw = str(value or "").replace("\u00a0", " ").strip()
    if not raw:
        return 0.0
    negative = raw.startswith("-") or raw.startswith("(")
    compact = re.sub(r"[^0-9,.]", "", raw)
    if not compact or not re.search(r"\d", compact):
        return 0.0

    comma_at = compact.rfind(",")
    dot_at = compact.rfind(".")
    if comma_at >= 0 and dot_at >= 0:
        decimal_separator = "," if comma_at > dot_at else "."
        whole, decimal = compact.rsplit(decimal_separator, 1)
        whole = re.sub(r"[,.]", "", whole) or "0"
        number = float(f"{whole}.{decimal}")
    elif comma_at >= 0:
        whole, decimal = compact.rsplit(",", 1)
        if len(decimal) in (1, 2):
            number = float(f"{whole or '0'}.{decimal}")
        else:
            number = float(compact.replace(",", ""))
    elif dot_at >= 0:
        whole, decimal = compact.rsplit(".", 1)
        if len(decimal) in (1, 2):
            number = float(f"{whole or '0'}.{decimal}")
        else:
            number = float(compact.replace(".", ""))
    else:
        number = float(compact)
    return round(-number if negative else number, 2)


def _date_iso(value: object) -> str:
    text = str(value or "")
    iso_match = re.search(_ISO_DATE_TOKEN, text)
    if iso_match:
        year, month, day = re.split(r"[-/.]", iso_match.group(0))
        return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
    match = re.search(_DATE_TOKEN, text)
    if match:
        day, month, year = re.split(r"[./]", match.group(0))
        return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
    return ""


def _amount_after_label(text: str, label: str) -> float | None:
    match = re.search(rf"{re.escape(label)}\s*(?P<amount>{_NUMBER_TOKEN})", text, re.IGNORECASE)
    if not match:
        return None
    return _parse_amount(match.group("amount"))


def _clean_merchant(lines: list[str], operation: str) -> str:
    """Prefer the merchant after PKO's ``Lokalizacja`` field.

    Transfer descriptions do not have a separate merchant field, so the first
    meaningful description line is used.  Reference numbers, card metadata
    and PDF footer text are intentionally omitted from the user-facing name.
    """
    cleaned = [_clean_line(line) for line in lines if _clean_line(line)]
    description = " ".join(cleaned)
    location = re.search(r"lokalizacja:\s*(.+?)(?:\s+nr\s+ref:|$)", description, re.IGNORECASE)
    if location:
        merchant = _clean_line(location.group(1))
    else:
        candidates: list[str] = []
        for line in cleaned:
            candidate = _DATE_RE.sub(" ", line)
            candidate = _clean_line(candidate)
            folded = _fold(candidate)
            if not candidate:
                continue
            if folded.startswith((
                "karta:",
                "kwota oryg",
                "tel:",
                "nr ref",
                "koszty przeliczenia",
                "data przetw",
                "data dokumentu",
            )):
                continue
            if "saldo do przeniesienia" in folded or "saldo koncowe" in folded:
                continue
            candidates.append(candidate)
        merchant = candidates[0] if candidates else _clean_line(operation)
    merchant = re.sub(r"\s+", " ", merchant).strip(" -:;,.|")
    return merchant[:120] or "Imported transaction"


def _category_for(merchant: str, operation: str, signed_amount: float) -> tuple[str, float]:
    """Return a conservative category suggestion and its review confidence."""
    text = _fold(f"{merchant} {operation}")
    if signed_amount > 0:
        return "Income", 0.98
    if re.search(r"fundusz|inwest|investment|emerytur|tfi|pkb", text):
        return "Assets", 0.94
    if re.search(r"kredyt|credit|pozycz|loan|rata|debt", text):
        return "Debt", 0.94
    if re.search(
        r"auchan|biedronka|lidl|carrefour|zabka|zabka|pepco|super[- ]?pharm|hebe|drogeria|natura|grocery|market|food|spozyw|"
        r"mieszkanie|rent|czynsz|prad|energia|utility|orange|telefon|internet|koleo|pkp|jakdojade|bolt|uber",
        text,
    ):
        return "Needs", 0.92
    if re.search(
        r"steam|g2a|kinguin|spotify|amazon|anthropic|claude|restaurant|burger|kawi|cafe|kino|cinema|"
        r"targ|sklep|shopping|harro|nocowanko|maison|araneus",
        text,
    ):
        return "Wants", 0.88
    return "Other", 0.55


def _operation_rows(text: str) -> list[dict[str, Any]]:
    """Parse PKO's one-line transaction header plus following description."""
    lines = _lines(text)
    rows: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    def flush() -> None:
        nonlocal current
        if not current:
            return
        signed = round(float(current["signedAmount"]), 2)
        merchant = _clean_merchant(current.get("description", []), current["operation"])
        category, confidence = _category_for(merchant, current["operation"], signed)
        external_id = str(current["externalId"])
        rows.append({
            "id": f"statement-{external_id}",
            "externalId": external_id,
            "date": current["date"],
            "merchant": merchant,
            "description": " ".join(current.get("description", []))[:500],
            "operationType": current["operation"],
            "category": category,
            "categoryConfidence": confidence,
            "amount": abs(signed),
            "direction": "income" if signed > 0 else "expense",
            "balanceAfter": current.get("balanceAfter"),
            "source": "bank-statement",
            "selected": True,
        })
        current = None

    for line in lines:
        match = _PKO_HEADER_RE.match(line)
        if match:
            flush()
            current = {
                "date": _date_iso(match.group("date")),
                "externalId": match.group("external_id"),
                "operation": _clean_line(match.group("operation")),
                "signedAmount": _parse_amount(match.group("amount")),
                "balanceAfter": round(_parse_amount(match.group("balance")), 2),
                "description": [],
            }
            continue
        if not current:
            continue
        folded = _fold(line)
        if folded.startswith(("saldo do przeniesienia", "saldo koncowe")):
            flush()
            continue
        if folded.startswith((
            "www.pkobp.pl",
            "powszechna kasa oszczednosci",
            "niniejszy dokument",
            "nr rachunku/karty",
            "nr iban",
            "wyciag za okres",
            "data operacji",
            "data waluty",
            "strona ",
            "informacja o bankowym",
            "srodki na rachunku",
            "zadbaj o wygode",
        )):
            continue
        current["description"].append(line)
    flush()
    return rows[:MAX_STATEMENT_ROWS]


def _pko_metadata(text: str, rows: list[dict[str, Any]], filename: str) -> dict[str, Any]:
    compact = " ".join(_lines(text))
    period = _PERIOD_RE.search(compact)
    account_match = re.search(r"Nr rachunku/karty:\s*([0-9 ]{10,})", compact, re.IGNORECASE)
    currency_match = re.search(r"Waluta rachunku:\s*([A-Z]{3})", compact, re.IGNORECASE)
    statement_match = re.search(r"\bNr:\s*([^\s]+)", compact, re.IGNORECASE)
    opening = _amount_after_label(compact, "Saldo poprzednie")
    closing = _amount_after_label(compact, "Saldo końcowe")
    if closing is None:
        closing = _amount_after_label(compact, "Saldo koncowe")
    if closing is None and rows:
        closing = rows[-1].get("balanceAfter")
    # PKO's PDF text layer places the summary values below a three-column
    # heading, so the first number after ``Saldo poprzednie`` may actually be
    # ``Obroty MA``.  Once all operation rows are present, the balance equation
    # is unambiguous and gives the real opening balance:
    # opening + income - expenses = closing.
    if closing is not None and rows:
        net_change = sum(
            float(row.get("amount") or 0) * (1 if row.get("direction") == "income" else -1)
            for row in rows
        )
        opening = round(float(closing) - net_change, 2)
    expense_rows = [row for row in rows if row.get("direction") == "expense"]
    income_rows = [row for row in rows if row.get("direction") == "income"]
    return {
        "bank": "PKO Bank Polski" if "pkobp" in _fold(text) or "pko bank" in _fold(text) else "Bank statement",
        "fileName": Path(filename or "statement.pdf").name,
        "statementNumber": statement_match.group(1) if statement_match else "",
        "periodStart": _date_iso(period.group("start")) if period else "",
        "periodEnd": _date_iso(period.group("end")) if period else "",
        "account": re.sub(r"\D", "", account_match.group(1)) if account_match else "",
        "currency": currency_match.group(1).upper() if currency_match else "PLN",
        "openingBalance": opening,
        "closingBalance": closing,
        "transactionCount": len(rows),
        "expenseCount": len(expense_rows),
        "incomeCount": len(income_rows),
        "expenseTotal": round(sum(float(row.get("amount") or 0) for row in expense_rows), 2),
        "incomeTotal": round(sum(float(row.get("amount") or 0) for row in income_rows), 2),
        "parser": "PKO structured statement",
    }


def _generic_row(
    *,
    date: object,
    merchant: object,
    signed_amount: float,
    index: int,
    external_id: object = "",
    category: object = "",
) -> dict[str, Any]:
    merchant_text = _clean_line(merchant)[:120] or f"Imported transaction {index + 1}"
    category_text = _clean_line(category)
    if category_text not in {"Needs", "Wants", "Assets", "Debt", "Other", "Income"}:
        category_text, confidence = _category_for(merchant_text, "", signed_amount)
    else:
        confidence = 1.0
    token = _clean_line(external_id)
    if not token:
        token = sha256(f"{_date_iso(date)}|{merchant_text}|{signed_amount:.2f}|{index}".encode()).hexdigest()[:20]
    return {
        "id": f"statement-{token}",
        "externalId": token,
        "date": _date_iso(date) or str(date or ""),
        "merchant": merchant_text,
        "description": merchant_text,
        "operationType": "Imported transaction",
        "category": category_text,
        "categoryConfidence": confidence,
        "amount": abs(round(signed_amount, 2)),
        "direction": "income" if signed_amount > 0 else "expense",
        "balanceAfter": None,
        "source": "bank-statement",
        "selected": True,
    }


def _generic_rows(text: str, filename: str) -> list[dict[str, Any]]:
    stripped = str(text or "").strip()
    if not stripped:
        return []

    # JSON exports are common for fintech accounts.
    if Path(filename or "").suffix.lower() == ".json" or stripped[:1] in "[{":
        try:
            payload = json.loads(stripped)
            items = payload if isinstance(payload, list) else payload.get("transactions", payload.get("entries", []))
            if isinstance(items, list):
                rows: list[dict[str, Any]] = []
                for index, item in enumerate(items[:MAX_STATEMENT_ROWS]):
                    if not isinstance(item, dict):
                        continue
                    amount = item.get("amount", item.get("value", item.get("kwota")))
                    signed = _parse_amount(amount)
                    if not signed:
                        continue
                    rows.append(_generic_row(
                        date=item.get("date", item.get("transaction_date", item.get("data", ""))),
                        merchant=item.get("merchant", item.get("description", item.get("opis", item.get("name", "")))),
                        signed_amount=signed,
                        index=index,
                        external_id=item.get("id", item.get("reference", "")),
                        category=item.get("category", ""),
                    ))
                return rows
        except (ValueError, TypeError, AttributeError):
            pass

    raw_lines = _lines(stripped)
    if not raw_lines:
        return []
    delimiter = ";"
    try:
        delimiter = csv.Sniffer().sniff("\n".join(raw_lines[:8]), delimiters=",;\t|").delimiter
    except csv.Error:
        if "," in raw_lines[0] and ";" not in raw_lines[0]:
            delimiter = ","
    if delimiter in raw_lines[0] or len(raw_lines) > 1 and delimiter in raw_lines[1]:
        reader = csv.DictReader(io.StringIO("\n".join(raw_lines)), delimiter=delimiter)
        if reader.fieldnames:
            fields = { _fold(name): name for name in reader.fieldnames if name }

            def field(row: dict[str, Any], names: tuple[str, ...]) -> str:
                for name in names:
                    key = fields.get(name)
                    if key is not None and row.get(key) not in (None, ""):
                        return str(row.get(key))
                return ""

            rows = []
            for index, row in enumerate(reader):
                amount_raw = field(row, ("amount", "kwota", "value", "transaction amount"))
                debit_raw = field(row, ("debit", "withdrawal", "obciazenie", "wn"))
                credit_raw = field(row, ("credit", "deposit", "uznanie", "ma"))
                signed = _parse_amount(amount_raw)
                if debit_raw and credit_raw:
                    signed = _parse_amount(credit_raw) - abs(_parse_amount(debit_raw))
                elif debit_raw and not amount_raw:
                    signed = -abs(_parse_amount(debit_raw))
                elif credit_raw and not amount_raw:
                    signed = abs(_parse_amount(credit_raw))
                if not signed:
                    continue
                rows.append(_generic_row(
                    date=field(row, ("date", "data", "transaction date", "booking date", "value date")),
                    merchant=field(row, ("merchant", "description", "opis", "name", "title", "counterparty")),
                    signed_amount=signed,
                    index=index,
                    external_id=field(row, ("id", "reference", "ref", "transaction id")),
                    category=field(row, ("category", "kategoria")),
                ))
            return rows[:MAX_STATEMENT_ROWS]

    # Last-resort plain text adapter: one date + one signed amount per line.
    rows = []
    for index, line in enumerate(raw_lines[:MAX_STATEMENT_ROWS]):
        date_match = _DATE_ANY_RE.search(line)
        without_date = line.replace(date_match.group(0), " ") if date_match else line
        amount_match = _AMOUNT_RE.search(without_date)
        if not amount_match:
            amount_match = re.search(r"(?P<amount>[+-]?\s*\d+(?:\.\d{1,2}))", without_date)
        if not date_match or not amount_match:
            continue
        signed = _parse_amount(amount_match.group("amount"))
        if not signed:
            continue
        merchant = _clean_line(without_date.replace(amount_match.group(0), " "))
        rows.append(_generic_row(
            date=date_match.group(0),
            merchant=merchant,
            signed_amount=signed,
            index=index,
        ))
    return rows


def extract_pdf_text(payload: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - deployment configuration
        raise StatementParseError("PDF support is not installed on the server") from exc
    try:
        reader = PdfReader(io.BytesIO(payload))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as exc:
        raise StatementParseError(f"Could not read the PDF: {exc}") from exc


def parse_bank_statement(payload: bytes, filename: str = "statement", content_type: str = "") -> dict[str, Any]:
    """Extract a statement into safe-to-review rows without persisting it."""
    if len(payload) > MAX_STATEMENT_BYTES:
        raise StatementParseError("The statement is larger than the 25 MB import limit")
    if not payload:
        raise StatementParseError("The uploaded statement is empty")
    suffix = Path(filename or "statement").suffix.lower()
    if suffix == ".pdf" or "pdf" in str(content_type).lower() or payload[:4] == b"%PDF":
        text = extract_pdf_text(payload)
    else:
        text = payload.decode("utf-8-sig", errors="replace")

    pko_rows = _operation_rows(text)
    if pko_rows:
        statement = _pko_metadata(text, pko_rows, filename)
        return {"ok": True, "statement": statement, "rows": pko_rows}

    rows = _generic_rows(text, filename)
    if not rows:
        raise StatementParseError("No transactions could be detected in this statement")
    expense_rows = [row for row in rows if row.get("direction") == "expense"]
    income_rows = [row for row in rows if row.get("direction") == "income"]
    return {
        "ok": True,
        "statement": {
            "bank": "Bank statement",
            "fileName": Path(filename or "statement").name,
            "statementNumber": "",
            "periodStart": min((row["date"] for row in rows if row.get("date")), default=""),
            "periodEnd": max((row["date"] for row in rows if row.get("date")), default=""),
            "account": "",
            "currency": "PLN",
            "openingBalance": None,
            "closingBalance": None,
            "transactionCount": len(rows),
            "expenseCount": len(expense_rows),
            "incomeCount": len(income_rows),
            "expenseTotal": round(sum(float(row.get("amount") or 0) for row in expense_rows), 2),
            "incomeTotal": round(sum(float(row.get("amount") or 0) for row in income_rows), 2),
            "parser": "Generic statement parser",
        },
        "rows": rows,
    }
