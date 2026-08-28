"""Zerodha contract-note XLSX adapter -- the same document as
app.ingest.zerodha_contract_note (trades WITH charges), from a spreadsheet export
instead of a PDF.

WHY THIS EXISTS. Historical XIRR needs price AND charges going back to account
inception. Tradebook CSV upload already covers "one file per FY, merge and dedupe"
(app.ingest.zerodha_tradebook); contract notes -- the only source of charges -- had
no upload path at all, only email forwarding. Console's bulk contract-note export for
a chosen date range closes that gap: this is what "custom date range" means here --
the range is picked when the file is downloaded from Console, not inside this app.

TWO REAL SHAPES, BOTH VERIFIED AGAINST ACTUAL EXPORTS, NOT INVENTED:

**Bulk** (one workbook, one sheet per trading day, sheet name "DD-MM-YYYY"): a
cell-for-cell mirror of the same PDF layout app.ingest.zerodha_contract_note.TRADE_ROW
already parses -- same header labels, same "SYMBOL - SERIES / ISIN" security
description, same charge-line wording family. Verified against 67 real trading-day
sheets across five real per-FY exports (2022-23 through 2026-27, one investor).

**Clean** (a workbook with exactly the sheets "Trades" / "Charges & Net" /
"Note Details"): one note, three purpose-built sheets -- trades in Trades (ISIN and
Symbol already split into their own columns, unlike the bulk shape's combined
description cell), a labelled charge breakdown in "Charges & Net", note metadata in
"Note Details". Verified against one real single-day export.

**Neither shape's charge labels match app.ingest.zerodha_contract_note.CHARGE_PATTERNS.**
That module's regexes require PDF-exact phrasing ("Taxable value of Supply
(Brokerage)", bare "IGST"/"CGST"/"SGST") the bulk shape spells differently ("Brokerage",
"Integrated GST", "Central GST") and the clean shape differently again ("Brokerage
(taxable value)", "IGST @18%"). Reusing those regexes on reconstructed text would
silently under-count charges -- confirmed by checking each one against the real label
text before writing classify_charge_label, not assumed. A lenient, cell-native
keyword classifier is the correct fix here, not a third regex family.

Turnover apportionment itself IS reused, not reinvented:
app.ingest.zerodha_contract_note.apportion_charges/pro_rata_share -- refactored out of
that module into plain functions for exactly this reuse. One implementation of "spread
a note's charges pro rata by turnover, last row absorbs the rounding remainder" for
every contract-note shape this codebase reads, not one per format.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.ingest.base import ParseResult, Rejection
from app.ingest.zerodha_contract_note import ISIN_PATTERN, SIDES, _decimal, apportion_charges

#: "SYMBOL - SERIES / ISIN", the bulk shape's combined description cell -- same split
#: app.ingest.zerodha_contract_note.TRADE_ROW performs on PDF text, applied here to an
#: already-isolated cell instead of a whole line.
SYMBOL_ISIN = re.compile(r"^(?P<symbol>[A-Z0-9&.\-]+?)\s*-\s*\w+\s*/\s*(?P<isin>IN[A-Z0-9]{10})$")

#: The clean single-note shape has exactly these three sheets, and only these -- an
#: extra or missing sheet means it is not this shape, not a partial match to guess at.
CLEAN_SHEET_NAMES = frozenset({"Trades", "Charges & Net", "Note Details"})

DATE_IN_TEXT = re.compile(r"\d{2}[/-]\d{2}[/-]\d{4}")

#: (bucket, keywords) in priority order -- checked top to bottom, first match wins.
#: Order matters: a real label like "Integrated GST (@18% of Brokerage, SEBI and
#: Transaction Charges)" contains the substrings "brokerage" and "sebi" purely as rate-
#: basis explanation, not because it is a second charge -- checking the GST/STT/
#: exchange/SEBI/stamp keywords before the bare "brokerage" keyword is what keeps that
#: row classified as igst, not brokerage. Verified against every real label text in
#: both shapes before this list was written, not assumed to be exhaustive.
_CHARGE_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("igst", ("integrated gst", "igst")),
    ("cgst", ("central gst", "cgst")),
    ("sgst", ("state gst", "sgst")),
    ("stt", ("securities transaction",)),
    ("exchange", ("exchange transaction",)),
    ("sebi", ("sebi turnover",)),
    ("stamp", ("stamp duty",)),
    ("brokerage", ("brokerage",)),
]


def classify_charge_label(label: Any) -> str | None:
    """Which charge bucket a label cell names, or None if it names something this
    adapter does not recognise -- e.g. "Clearing Charges" (always 0 for equity in
    every real sample) or a totals/boilerplate row ("PAY IN / PAY OUT OBLIGATION",
    "Net amount Receivable..."). An unrecognised label contributes nothing, the same
    behaviour as the PDF adapter's CHARGE_PATTERNS simply not matching a line."""
    if not isinstance(label, str):
        return None
    lowered = label.strip().lower()
    for bucket, keywords in _CHARGE_RULES:
        if any(k in lowered for k in keywords):
            return bucket
    return None


def _cell_str(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _parse_date(raw: str) -> date | None:
    for fmt in ("%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


class ZerodhaContractNoteXlsxAdapter:
    """Zerodha contract notes exported as XLSX -- bulk (one sheet per trading day, a
    chosen date range) or clean (one note, three labelled sheets). See module
    docstring for how each shape was verified and why charge labels need their own
    classifier rather than reusing the PDF adapter's regexes."""

    name = "zerodha_contract_note_xlsx"

    def parse(self, content: bytes, account_id: str, filename: str = "") -> ParseResult:
        import io

        try:
            import openpyxl
        except ImportError as exc:  # pragma: no cover - dependency guard
            return ParseResult(
                rejections=[Rejection(0, f"openpyxl is not installed: {exc}")]
            )

        try:
            workbook = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
        except Exception as exc:  # noqa: BLE001 - openpyxl raises assorted types
            return ParseResult(rejections=[Rejection(0, f"could not read XLSX: {exc}")])

        if frozenset(workbook.sheetnames) == CLEAN_SHEET_NAMES:
            return self._parse_clean(workbook, account_id)
        return self._parse_bulk(workbook, account_id)

    # -- bulk: one sheet per trading day ------------------------------------------

    def _parse_bulk(self, workbook: Any, account_id: str) -> ParseResult:
        all_rows = []
        all_rejections = []
        parsed_dates: list[date] = []
        row_counter = 0
        recognised_days = 0

        for sheet_name in workbook.sheetnames:
            rows_2d = list(workbook[sheet_name].iter_rows(values_only=True))
            header = self._find_bulk_header(rows_2d)
            if header is None:
                row_counter += 1
                all_rejections.append(
                    Rejection(
                        row_counter,
                        f"sheet {sheet_name!r}: does not look like a contract-note "
                        "trading day (no recognisable header row)",
                    )
                )
                continue

            header_idx, col = header
            txn_date = self._bulk_trade_date(rows_2d, header_idx, sheet_name)
            if txn_date is None:
                row_counter += 1
                all_rejections.append(
                    Rejection(row_counter, f"sheet {sheet_name!r}: no readable trade date")
                )
                continue

            contract_number = self._bulk_contract_number(rows_2d, header_idx)
            candidates, charges_by_bucket, rejections = self._bulk_rows(
                rows_2d, header_idx, col, txn_date, row_counter, sheet_name
            )
            row_counter += len(rows_2d) - header_idx
            all_rejections.extend(rejections)

            if not candidates:
                continue

            recognised_days += 1
            parsed_dates.append(txn_date)
            # stt is a SUBSET of total_charges, not additive -- same convention as
            # zerodha_contract_note.py, see that module's Session 10 note.
            total_charges = sum(charges_by_bucket.values(), Decimal("0"))
            total_stt = charges_by_bucket.get("stt", Decimal("0"))
            all_rows.extend(
                apportion_charges(candidates, total_charges, total_stt, account_id, contract_number)
            )

        notes = [self._range_note(recognised_days, parsed_dates)]
        return ParseResult(rows=all_rows, rejections=all_rejections, notes=notes)

    @staticmethod
    def _find_bulk_header(rows_2d: list[tuple]) -> tuple[int, dict[str, int]] | None:
        for idx, row in enumerate(rows_2d[:40]):
            cells = [_cell_str(c).lower() for c in row]
            if not any("order no" in c for c in cells):
                continue
            if not any("trade no" in c for c in cells):
                continue
            col: dict[str, int] = {}
            for i, c in enumerate(cells):
                if "order no" in c:
                    col["order"] = i
                elif "trade no" in c:
                    col["trade"] = i
                elif "security" in c and "description" in c:
                    col["description"] = i
                elif "buy" in c and "sell" in c:
                    col["side"] = i
                elif c == "quantity":
                    col["quantity"] = i
                elif c == "exchange":
                    col["exchange"] = i
                elif "gross rate" in c or "trade price per unit" in c:
                    col["price"] = i
                elif "net total" in c and "levies" in c:
                    col["net_total"] = i
            required = {
                "order", "trade", "description", "side", "quantity", "exchange", "price",
                "net_total",
            }
            if required <= set(col):
                return idx, col
        return None

    @staticmethod
    def _bulk_trade_date(rows_2d: list[tuple], header_idx: int, sheet_name: str) -> date | None:
        for row in rows_2d[: header_idx + 1]:
            for i, cell in enumerate(row):
                if "trade date" not in _cell_str(cell).lower():
                    continue
                for later in row[i:]:
                    text = _cell_str(later)
                    match = DATE_IN_TEXT.search(text)
                    if match:
                        found = _parse_date(match.group(0))
                        if found:
                            return found
        # Fall back to the sheet name itself -- confirmed identical to the in-sheet
        # "Trade Date:" value on every real sample, and the only signal left when a
        # label cell wraps unusually.
        return _parse_date(sheet_name.strip())

    @staticmethod
    def _bulk_contract_number(rows_2d: list[tuple], header_idx: int) -> str | None:
        for row in rows_2d[: header_idx + 1]:
            for i, cell in enumerate(row):
                if "contract note no" not in _cell_str(cell).lower():
                    continue
                for later in row[i:]:
                    text = _cell_str(later)
                    if text and "contract note no" not in text.lower():
                        return text
        return None

    def _bulk_rows(
        self,
        rows_2d: list[tuple],
        header_idx: int,
        col: dict[str, int],
        txn_date: date,
        row_offset: int,
        sheet_name: str,
    ) -> tuple[list[dict[str, Any]], dict[str, Decimal], list[Rejection]]:
        candidates: list[dict[str, Any]] = []
        charges: dict[str, Decimal] = {}
        rejections: list[Rejection] = []
        # The charges sub-table below the trades has its OWN "NET TOTAL" column,
        # confirmed at a DIFFERENT index than the trades table's "Net Total (Before
        # Levies)" column on the real sample (11 vs 12) -- the two blocks are not
        # column-aligned. Found by locating the literal "NET TOTAL" sub-header cell
        # rather than assumed to match col["net_total"].
        charge_net_total_idx: int | None = None

        def get(row: tuple, key: str) -> Any:
            idx = col[key]
            return row[idx] if idx < len(row) else None

        for offset, row in enumerate(rows_2d[header_idx + 1 :], start=1):
            row_number = row_offset + offset
            side_raw = _cell_str(get(row, "side")).upper()
            description = _cell_str(get(row, "description"))

            if side_raw in SIDES and description:
                match = SYMBOL_ISIN.match(description)
                if not match:
                    rejections.append(
                        Rejection(
                            row_number,
                            f"sheet {sheet_name!r}: unrecognised security description "
                            f"{description!r}",
                        )
                    )
                    continue
                isin = match.group("isin").upper()
                if not ISIN_PATTERN.match(isin):
                    rejections.append(
                        Rejection(
                            row_number, f"sheet {sheet_name!r}: not a security ISIN: {isin!r}"
                        )
                    )
                    continue
                try:
                    quantity = _decimal(str(get(row, "quantity")))
                    price = _decimal(str(get(row, "price")))
                except InvalidOperation:
                    rejections.append(
                        Rejection(
                            row_number, f"sheet {sheet_name!r}: unparseable quantity or price"
                        )
                    )
                    continue
                if quantity <= 0 or price < 0:
                    rejections.append(
                        Rejection(
                            row_number,
                            f"sheet {sheet_name!r}: implausible quantity/price "
                            f"{quantity}/{price}",
                        )
                    )
                    continue
                trade_no = _cell_str(get(row, "trade"))
                if not trade_no:
                    rejections.append(
                        Rejection(row_number, f"sheet {sheet_name!r}: trade row has no Trade No.")
                    )
                    continue
                candidates.append(
                    {
                        "row_number": row_number,
                        "isin": isin,
                        "symbol": match.group("symbol"),
                        "txn_type": SIDES[side_raw],
                        "quantity": quantity,
                        "price": price,
                        "trade_id": trade_no,
                        "order_id": _cell_str(get(row, "order")),
                        "exchange": _cell_str(get(row, "exchange")),
                        "txn_date": txn_date,
                    }
                )
                continue

            if charge_net_total_idx is None:
                for i, cell in enumerate(row):
                    if _cell_str(cell).strip().upper() == "NET TOTAL":
                        charge_net_total_idx = i
                        break
                if charge_net_total_idx is not None:
                    continue  # this row is the sub-header itself, not a charge line

            label = row[0] if row else None
            bucket = classify_charge_label(label)
            if bucket is None or charge_net_total_idx is None:
                continue
            if charge_net_total_idx >= len(row):
                continue
            try:
                amount = abs(_decimal(str(row[charge_net_total_idx])))
            except InvalidOperation:
                continue
            charges[bucket] = charges.get(bucket, Decimal("0")) + amount

        return candidates, charges, rejections

    @staticmethod
    def _range_note(days: int, dates: list[date]) -> str:
        if not dates:
            return "no recognisable trading days found in this workbook"
        return (
            f"{days} trading day(s) parsed, {min(dates)} to {max(dates)} -- "
            "confirm this matches the date range you downloaded from Console"
        )

    # -- clean: one note, three sheets ---------------------------------------------

    def _parse_clean(self, workbook: Any, account_id: str) -> ParseResult:
        trades_ws = workbook["Trades"]
        charges_ws = workbook["Charges & Net"]
        details_ws = workbook["Note Details"]

        details = {
            _cell_str(row[0]).lower(): _cell_str(row[1])
            for row in details_ws.iter_rows(values_only=True)
            if row and row[0] and row[1] is not None
        }
        contract_number = details.get("contract note no.")
        raw_date = details.get("trade date", "")
        match = DATE_IN_TEXT.search(raw_date)
        txn_date = _parse_date(match.group(0)) if match else None
        if txn_date is None:
            return ParseResult(
                rejections=[Rejection(0, "Note Details sheet: no readable trade date")]
            )

        header_idx = None
        col: dict[str, int] = {}
        trade_rows = list(trades_ws.iter_rows(values_only=True))
        for idx, row in enumerate(trade_rows):
            cells = [_cell_str(c).lower() for c in row]
            if "isin" in cells and "side" in cells and "quantity" in cells:
                header_idx = idx
                for i, c in enumerate(cells):
                    if c == "isin":
                        col["isin"] = i
                    elif c == "symbol":
                        col["symbol"] = i
                    elif c == "side":
                        col["side"] = i
                    elif c == "exchange":
                        col["exchange"] = i
                    elif c == "quantity":
                        col["quantity"] = i
                    elif "price" in c or "wap" in c:
                        col.setdefault("price", i)
                break
        if header_idx is None or "isin" not in col:
            return ParseResult(
                rejections=[Rejection(0, "Trades sheet: no recognisable header row")]
            )

        candidates: list[dict[str, Any]] = []
        rejections: list[Rejection] = []
        for offset, row in enumerate(trade_rows[header_idx + 1 :], start=1):
            row_number = header_idx + 1 + offset
            isin = _cell_str(row[col["isin"]] if col["isin"] < len(row) else None).upper()
            if not isin:
                continue
            if not ISIN_PATTERN.match(isin):
                rejections.append(Rejection(row_number, f"not a security ISIN: {isin!r}"))
                continue
            # The clean shape spells the side out ("BUY"/"SELL"), unlike the bulk
            # shape's single letter ("B"/"S") -- confirmed against the real sample,
            # not assumed to match SIDES' PDF-derived keys.
            side_raw = _cell_str(row[col["side"]] if col["side"] < len(row) else None).upper()
            side_key = {"BUY": "B", "SELL": "S"}.get(side_raw, side_raw)
            if side_key not in SIDES:
                rejections.append(Rejection(row_number, f"unknown side {side_raw!r}"))
                continue
            try:
                quantity = _decimal(str(row[col["quantity"]]))
                price = _decimal(str(row[col["price"]]))
            except InvalidOperation:
                rejections.append(Rejection(row_number, "unparseable quantity or price"))
                continue
            if quantity <= 0 or price < 0:
                rejections.append(
                    Rejection(row_number, f"implausible quantity/price {quantity}/{price}")
                )
                continue
            candidates.append(
                {
                    "row_number": row_number,
                    "isin": isin,
                    "symbol": _cell_str(row[col["symbol"]]) if "symbol" in col else "",
                    "txn_type": SIDES[side_key],
                    "quantity": quantity,
                    "price": price,
                    # This sheet carries no per-trade trade number -- source_ref is
                    # left unset, same as any adapter with no stable per-trade id
                    # (app.db.precedence.trade_identity returns None without one,
                    # which is the honest outcome, not a guess).
                    "trade_id": None,
                    "order_id": None,
                    "exchange": _cell_str(row[col["exchange"]]) if "exchange" in col else "",
                    "txn_date": txn_date,
                }
            )

        charges: dict[str, Decimal] = {}
        for row in charges_ws.iter_rows(values_only=True):
            if not row or row[0] is None:
                continue
            bucket = classify_charge_label(row[0])
            if bucket is None:
                continue
            try:
                amount = abs(_decimal(str(row[1])))
            except (InvalidOperation, IndexError, TypeError):
                continue
            charges[bucket] = charges.get(bucket, Decimal("0")) + amount

        total_charges = sum(charges.values(), Decimal("0"))
        total_stt = charges.get("stt", Decimal("0"))
        rows = apportion_charges(candidates, total_charges, total_stt, account_id, contract_number)
        notes = [
            f"contract note {contract_number or '(number not found)'} dated {txn_date}",
            f"charges {total_charges} apportioned pro rata by turnover across "
            f"{len(candidates)} trade(s): {', '.join(sorted(charges)) or 'none found'}",
        ]
        return ParseResult(rows=rows, rejections=rejections, notes=notes)
