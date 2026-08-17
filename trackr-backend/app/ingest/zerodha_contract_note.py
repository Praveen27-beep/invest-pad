"""Zerodha contract-note PDF adapter.

The contract note is the only document that carries CHARGES. A tradebook has quantities
and prices but no brokerage, STT, GST, SEBI turnover fee or stamp duty, so a cost basis
built from tradebooks alone is understated by exactly those. This adapter is how they get
in.

Two facts about the format that shape everything here:

**Charges are stated once per NOTE, not per trade.** A single note can cover eight trades
across five securities and reports one brokerage figure, one STT figure, and so on. Getting
them onto individual transactions therefore requires apportionment, which is a derivation
rather than a reading -- and that is why every row from this adapter scores
CONFIDENCE_DERIVED rather than CONFIDENCE_CERTAIN.

**The broker's own SEBI registration looks like an ISIN.** `INZ000031633` matches a naive
`^IN[A-Z0-9]{10}$`, and it appears in the header of every note. Real Indian securities are
`INE` (equity) or `INF` (fund), so the prefix is narrowed here. Without that, every note
would yield a phantom security named after the broker's licence.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.engine.types import Source, Transaction, TxnType
from app.ingest.base import CONFIDENCE_DERIVED, ParseResult, Rejection, StagedRow

#: INE = equity, INF = mutual fund. Deliberately NOT [A-Z0-9]: that admits INZ000031633,
#: Zerodha's SEBI registration, which is printed on every note.
ISIN_PATTERN = re.compile(r"^IN[EF][A-Z0-9]{9}$")

#: order-no time trade-no time SYMBOL-SERIES/ISIN B|S EXCHANGE qty brokerage rate ...
TRADE_ROW = re.compile(
    r"^(?P<order>\d{10,})\s+\S+\s+(?P<trade>\d+)\s+\S+\s+"
    r"(?P<symbol>[A-Z0-9&.\-]+?)\s*-\s*\w+\s*/\s*(?P<isin>IN[A-Z0-9]{10})\s+"
    r"(?P<side>[BS])\s+(?P<exchange>\w+)\s+(?P<qty>[\d,]+(?:\.\d+)?)\s+"
    r"(?P<brokerage>[\d,]+(?:\.\d+)?)\s+(?P<rate>[\d,]+(?:\.\d+)?)"
)

#: Zerodha changed the layout between 2023 and 2026: older notes print "Tradedate:" and
#: "ContractNoteno.:" with no spaces, newer ones "Trade Date:" and "Contract Note No:".
#: A client's history spans the change, so both have to work -- and three of the forty real
#: notes in this project are the older kind.
TRADE_DATE = re.compile(r"Trade\s*date\s*:\s*(\d{2}/\d{2}/\d{4})", re.I)
CONTRACT_NUMBER = re.compile(r"Contract\s*Note\s*no\.?\s*:\s*(\S+)", re.I)

#: Every charge line states its value as a bracketed negative. What sits between the label
#: and that value varies: a currency marker in its own brackets ("(Rs)", "(₹)"), a footnote
#: digit, or nothing. So the gap is matched lazily and the CAPTURE is required to be
#: numeric -- otherwise "(₹)" is read as the amount and the charge silently becomes zero.
_AMOUNT = r".{0,60}?\((\d[\d,]*(?:\.\d+)?)\)"

CHARGE_PATTERNS = {
    "brokerage": re.compile(r"Taxable value of Supply \(Brokerage\)" + _AMOUNT),
    "stt": re.compile(r"Securities [Tt]ransaction [Tt]ax" + _AMOUNT),
    "exchange": re.compile(r"Exchange transaction charges" + _AMOUNT),
    "igst": re.compile(r"IGST" + _AMOUNT),
    "cgst": re.compile(r"CGST" + _AMOUNT),
    "sgst": re.compile(r"SGST" + _AMOUNT),
    "sebi": re.compile(r"SEBI turnover fees" + _AMOUNT),
    "stamp": re.compile(r"Stamp duty" + _AMOUNT),
}

SIDES = {"B": TxnType.BUY, "S": TxnType.SELL}

CONTRACT_NOTE_MARKER = "CONTRACT NOTE"


class PdfTextExtractionError(RuntimeError):
    """The PDF could not be opened or produced no text."""


def _decimal(raw: str) -> Decimal:
    return Decimal(raw.replace(",", "").strip())


def extract_text(content: bytes, password: str = "") -> str:
    """Pull text out of a contract-note PDF.

    Separated so tests can feed text directly and so the PDF library stays one import
    behind a seam -- pdfplumber is slow and heavy, and nothing else here needs it.
    """
    import io

    try:
        import pdfplumber
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise PdfTextExtractionError(
            "pdfplumber is not installed. pip install -e '.[pdf]'"
        ) from exc

    try:
        with pdfplumber.open(io.BytesIO(content), password=password) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages)
    except Exception as exc:
        raise PdfTextExtractionError(f"could not read PDF: {exc}") from exc


def parse_charges(text: str) -> dict[str, Decimal]:
    """Note-level charge components. Absent lines are simply absent, never assumed zero."""
    flat = " ".join(text.split())
    charges: dict[str, Decimal] = {}
    for name, pattern in CHARGE_PATTERNS.items():
        match = pattern.search(flat)
        if match:
            try:
                charges[name] = _decimal(match.group(1))
            except InvalidOperation:
                continue
    return charges


class ZerodhaContractNoteAdapter:
    """Contract notes: trades WITH charges.

    Charges are apportioned across the note's trades **pro rata by turnover**
    (quantity x price). That is an approximation, and a deliberate one: STT applies at
    different rates to buys and sells, brokerage is capped per order, and the note does not
    break any of it down per trade. Turnover is the honest single basis available, and the
    resulting rows are marked CONFIDENCE_DERIVED so a reviewer knows the charge figure was
    computed rather than read.

    The alternative -- charging everything to the first trade, or dropping charges
    entirely -- would be exact for one row and wrong for the rest, or understate every cost
    basis. Spreading it is the least wrong option, and saying so is the point of the
    confidence score.
    """

    name = "zerodha_contract_note"

    def __init__(self, password: str = ""):
        self.password = password

    def parse(self, content: bytes, account_id: str, filename: str = "") -> ParseResult:
        try:
            text = content.decode("utf-8") if content[:5] != b"%PDF-" else extract_text(
                content, self.password
            )
        except PdfTextExtractionError as exc:
            return ParseResult(rejections=[Rejection(0, str(exc))])
        except UnicodeDecodeError:
            return ParseResult(rejections=[Rejection(0, "not a readable contract note")])

        return self.parse_text(text, account_id, filename)

    def parse_text(self, text: str, account_id: str, filename: str = "") -> ParseResult:
        if CONTRACT_NOTE_MARKER not in text.upper():
            return ParseResult(
                rejections=[Rejection(0, "not a contract note: header marker absent")]
            )

        date_match = TRADE_DATE.search(text)
        if not date_match:
            return ParseResult(rejections=[Rejection(0, "no trade date on the note")])
        try:
            txn_date = datetime.strptime(date_match.group(1), "%d/%m/%Y").date()
        except ValueError:
            return ParseResult(
                rejections=[Rejection(0, f"unparseable trade date {date_match.group(1)!r}")]
            )

        contract_number = (
            CONTRACT_NUMBER.search(text).group(1) if CONTRACT_NUMBER.search(text) else None
        )
        charges = parse_charges(text)
        total_charges = sum(charges.values(), Decimal("0"))

        candidates, rejections = self._extract_rows(text, txn_date)

        notes = [
            f"contract note {contract_number or '(number not found)'} dated {txn_date}",
            (
                f"charges {total_charges} apportioned pro rata by turnover across "
                f"{len(candidates)} trade(s): {', '.join(sorted(charges)) or 'none found'}"
            ),
        ]
        if not charges:
            notes.append(
                "NO CHARGE LINES FOUND. Rows carry charges of 0, which is absence of data "
                "rather than evidence the trades were free."
            )

        rows = self._apportion(candidates, total_charges, account_id, contract_number)
        return ParseResult(rows=rows, rejections=rejections, notes=notes)

    def _extract_rows(
        self, text: str, txn_date: date
    ) -> tuple[list[dict[str, Any]], list[Rejection]]:
        candidates: list[dict[str, Any]] = []
        rejections: list[Rejection] = []

        for line_number, line in enumerate(text.splitlines(), start=1):
            match = TRADE_ROW.match(line.strip())
            if not match:
                continue

            isin = match.group("isin").upper()
            if not ISIN_PATTERN.match(isin):
                # INZ000031633 is the broker's SEBI registration, printed on every note.
                # It matches a looser ISIN shape and would become a phantom security.
                rejections.append(
                    Rejection(line_number, f"not a security ISIN: {isin!r}", {"line": line[:120]})
                )
                continue

            try:
                quantity = _decimal(match.group("qty"))
                price = _decimal(match.group("rate"))
            except InvalidOperation:
                rejections.append(
                    Rejection(line_number, "unparseable quantity or rate", {"line": line[:120]})
                )
                continue

            if quantity <= 0 or price < 0:
                rejections.append(
                    Rejection(line_number, f"implausible quantity/price {quantity}/{price}")
                )
                continue

            candidates.append(
                {
                    "row_number": line_number,
                    "isin": isin,
                    "symbol": match.group("symbol"),
                    "txn_type": SIDES[match.group("side")],
                    "quantity": quantity,
                    "price": price,
                    "trade_id": match.group("trade"),
                    "order_id": match.group("order"),
                    "exchange": match.group("exchange"),
                    "txn_date": txn_date,
                }
            )
        return candidates, rejections

    def _apportion(
        self,
        candidates: list[dict[str, Any]],
        total_charges: Decimal,
        account_id: str,
        contract_number: str | None,
    ) -> list[StagedRow]:
        turnovers = [c["quantity"] * c["price"] for c in candidates]
        total_turnover = sum(turnovers, Decimal("0"))

        rows: list[StagedRow] = []
        allocated = Decimal("0")
        for index, candidate in enumerate(candidates):
            if total_turnover > 0 and total_charges > 0:
                if index == len(candidates) - 1:
                    # The last row absorbs the rounding remainder, so the apportioned
                    # charges sum to exactly what the note states. Otherwise a portfolio
                    # reconciled against the note is out by a few paise for no good reason.
                    share = total_charges - allocated
                else:
                    share = (total_charges * turnovers[index] / total_turnover).quantize(
                        Decimal("0.01")
                    )
                    allocated += share
            else:
                share = Decimal("0")

            rows.append(
                StagedRow(
                    row_number=candidate["row_number"],
                    transaction=Transaction(
                        isin=candidate["isin"],
                        txn_date=candidate["txn_date"],
                        txn_type=candidate["txn_type"],
                        quantity=candidate["quantity"],
                        price=candidate["price"],
                        charges=share,
                        account_id=account_id,
                        source=Source.CONTRACT_NOTE,
                        # The TRADE number, matching the tradebook's trade_id, so the same
                        # trade from either source has the same identity.
                        source_ref=candidate["trade_id"],
                    ),
                    # Never CERTAIN: the charge figure is apportioned, not read.
                    confidence=CONFIDENCE_DERIVED,
                    raw={
                        "symbol": candidate["symbol"],
                        "exchange": candidate["exchange"],
                        "order_id": candidate["order_id"],
                        "contract_number": contract_number,
                    },
                )
            )
        return rows
