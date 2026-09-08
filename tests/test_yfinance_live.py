"""app.prices.yfinance_live -- ticker resolution, Decimal conversion, and the
never-raise contract. No network: yf.download is monkeypatched throughout, with real
pandas frames shaped the way yfinance actually returns them.

Confirmed empirically against the installed yfinance version (see live docs/session
notes): with group_by="ticker", the returned frame ALWAYS carries a (Ticker, Field)
MultiIndex on its columns, whether one symbol was requested or several -- it does NOT
flatten to bare field columns for a single symbol. `_multi_frame` below builds that
real shape and is used for every "normal" case, including one-symbol ones. A separate,
explicitly-named `_flat_frame` covers `_last_close`'s fallback branch for a frame with
no Ticker level at all, in case a different yfinance/pandas version ever produces one --
that branch existing is defensive, not the expected shape from this dependency today.

The live/today-only gating this feeds into is tests/test_db_live_prices.py's job, not
this file's.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

import pandas as pd
import pytest
from app.prices import yfinance_live as live


def _multi_frame(data: dict[str, list[float | None]]) -> pd.DataFrame:
    """The real shape of a group_by="ticker" download -- (Ticker, Field) MultiIndex
    columns -- for one symbol or several alike."""
    n = len(next(iter(data.values())))
    idx = pd.date_range("2024-09-25", periods=n, freq="D")
    frames = {
        symbol: pd.DataFrame({"Open": closes, "Close": closes}, index=idx)
        for symbol, closes in data.items()
    }
    return pd.concat(frames, axis=1)


def _flat_frame(closes: list[float | None]) -> pd.DataFrame:
    """A frame with NO Ticker level -- `_last_close`'s fallback branch. Not what the
    installed yfinance actually returns for any request shape observed so far; exists
    to keep that branch from silently rotting if it's ever genuinely exercised."""
    idx = pd.date_range("2024-09-25", periods=len(closes), freq="D")
    return pd.DataFrame({"Open": closes, "Close": closes}, index=idx)


class TestResolveTicker:
    def test_nse_gets_ns_suffix(self) -> None:
        assert live.resolve_ticker("RELIANCE", "NSE") == "RELIANCE.NS"

    def test_bse_only_gets_bo_suffix(self) -> None:
        assert live.resolve_ticker("KALYANI-M", "BSE") == "KALYANI-M.BO"

    def test_both_defaults_to_ns(self) -> None:
        assert live.resolve_ticker("TCS", "BOTH") == "TCS.NS"

    def test_missing_exchange_defaults_to_ns(self) -> None:
        assert live.resolve_ticker("TCS", None) == "TCS.NS"


class TestLastClose:
    def test_single_symbol_multiindex_frame_is_read_correctly(self) -> None:
        # This is the regression test for the real bug: a single-symbol request still
        # comes back with a (Ticker, Field) MultiIndex, not flat columns. An earlier
        # version of this function decided the frame's shape from `len(symbols) > 1`
        # instead of the frame itself, so this exact case (`multi=False`, but the
        # frame was still a MultiIndex) hit a caught KeyError and silently returned
        # None -- meaning a live fetch for exactly one ISIN always failed, in
        # production, every time.
        frame = _multi_frame({"TCS.NS": [100.0, 101.5, 102.25]})

        price = live._last_close(frame, "TCS.NS")

        assert price == Decimal("102.25")
        assert isinstance(price, Decimal)

    def test_multi_symbol_frame_indexes_by_symbol_first(self) -> None:
        frame = _multi_frame({"TCS.NS": [100.0, 105.0], "INFY.NS": [1500.0, 1510.5]})

        assert live._last_close(frame, "TCS.NS") == Decimal("105")
        assert live._last_close(frame, "INFY.NS") == Decimal("1510.5")

    def test_flat_frame_fallback_path_still_works(self) -> None:
        # Defensive coverage for a frame shape this yfinance version doesn't actually
        # produce (see module docstring) -- proves the fallback branch isn't dead code
        # that silently bit-rots.
        frame = _flat_frame([100.0, 101.5, 102.25])

        assert live._last_close(frame, "TCS.NS") == Decimal("102.25")

    def test_trailing_nan_is_skipped_for_the_last_real_close(self) -> None:
        frame = _multi_frame({"TCS.NS": [100.0, 101.0, None]})

        assert live._last_close(frame, "TCS.NS") == Decimal("101")

    def test_all_nan_returns_none(self) -> None:
        frame = _multi_frame({"TCS.NS": [None, None]})

        assert live._last_close(frame, "TCS.NS") is None

    def test_unknown_symbol_in_multi_frame_returns_none(self) -> None:
        frame = _multi_frame({"TCS.NS": [100.0]})

        assert live._last_close(frame, "DOESNOTEXIST.NS") is None

    def test_result_is_quantized_to_paisa(self) -> None:
        # yfinance hands back numpy.float64 with more than 2 decimal places on
        # occasion (Yahoo's own float32 storage noise, and plain sub-paisa values) --
        # NSE/BSE equities only ever trade in paisa ticks, so the result must always
        # be exactly 2 decimal places, never a longer "raw" fraction.
        frame = _multi_frame({"TCS.NS": [123.456789]})

        price = live._last_close(frame, "TCS.NS")

        assert price == Decimal("123.46")

    def test_yahoo_float32_precision_noise_is_recovered(self) -> None:
        # Reproduces a real observed value: NSE TCS closed at Rs 2320.10, but Yahoo's
        # backend (confirmed: this value round-trips exactly through float32) reports
        # it as this float64. Quantizing recovers the real tradable price rather than
        # faithfully preserving someone else's binary rounding noise.
        frame = _multi_frame({"TCS.NS": [2320.10009765625]})

        price = live._last_close(frame, "TCS.NS")

        assert price == Decimal("2320.10")

    def test_string_conversion_still_used_ahead_of_quantizing(self) -> None:
        # Decimal(float(...)) can round a half-paisa boundary differently than
        # Decimal(str(...)) does, because float->Decimal picks up the float's full,
        # ugly binary expansion before quantizing ever runs. 2.675 is the textbook
        # case: its float64 bit pattern sits at 2.67499999999999982... (just under
        # the boundary), so Decimal(2.675).quantize(...) rounds DOWN to 2.67 --
        # wrong, since the number this stands for is 2.675, which ROUND_HALF_UP must
        # take to 2.68. str() first, per CLAUDE.md rule 1, is what makes that correct.
        value = 2.675
        assert Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) == Decimal(
            "2.67"
        )  # the wrong answer a float-first conversion would give
        frame = _multi_frame({"TCS.NS": [value]})

        price = live._last_close(frame, "TCS.NS")

        assert price == Decimal("2.68")


class TestFetchLive:
    def test_empty_tickers_returns_empty_without_calling_yfinance(self, monkeypatch) -> None:
        def fail_if_called(*args, **kwargs):
            raise AssertionError("yf.download must not be called for an empty ticker set")

        monkeypatch.setattr("yfinance.download", fail_if_called)

        assert live.fetch_live({}) == {}

    def test_one_batched_call_for_multiple_tickers(self, monkeypatch) -> None:
        calls = []

        def fake_download(symbols, **kwargs):
            calls.append(symbols)
            return _multi_frame({"TCS.NS": [100.0], "INFY.NS": [1500.0]})

        monkeypatch.setattr("yfinance.download", fake_download)

        result = live.fetch_live({"ISIN_TCS": "TCS.NS", "ISIN_INFY": "INFY.NS"})

        assert len(calls) == 1
        assert calls[0] == ["INFY.NS", "TCS.NS"]
        assert result == {"ISIN_TCS": Decimal("100"), "ISIN_INFY": Decimal("1500")}

    def test_single_ticker_request_still_gets_its_price(self, monkeypatch) -> None:
        # The end-to-end version of test_single_symbol_multiindex_frame_is_read_correctly
        # above -- a single-ISIN request is the common case (one holding's bhavcopy
        # lagging while the rest of the portfolio is already priced), and it must not
        # silently come back empty.
        monkeypatch.setattr(
            "yfinance.download", lambda symbols, **kwargs: _multi_frame({"TCS.NS": [250.5]})
        )

        result = live.fetch_live({"ISIN_TCS": "TCS.NS"})

        assert result == {"ISIN_TCS": Decimal("250.5")}

    def test_two_isins_sharing_one_ticker_both_get_the_price(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "yfinance.download", lambda symbols, **kwargs: _multi_frame({"TCS.NS": [99.0]})
        )

        result = live.fetch_live({"ISIN_A": "TCS.NS", "ISIN_B": "TCS.NS"})

        assert result == {"ISIN_A": Decimal("99"), "ISIN_B": Decimal("99")}

    def test_network_failure_returns_empty_dict_never_raises(self, monkeypatch) -> None:
        def raise_error(symbols, **kwargs):
            raise RuntimeError("429 Too Many Requests")

        monkeypatch.setattr("yfinance.download", raise_error)

        assert live.fetch_live({"ISIN_TCS": "TCS.NS"}) == {}

    def test_empty_frame_returns_empty_dict(self, monkeypatch) -> None:
        monkeypatch.setattr("yfinance.download", lambda symbols, **kwargs: pd.DataFrame())

        assert live.fetch_live({"ISIN_TCS": "TCS.NS"}) == {}

    def test_none_frame_returns_empty_dict(self, monkeypatch) -> None:
        monkeypatch.setattr("yfinance.download", lambda symbols, **kwargs: None)

        assert live.fetch_live({"ISIN_TCS": "TCS.NS"}) == {}

    def test_ticker_with_no_usable_close_is_simply_absent(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "yfinance.download",
            lambda symbols, **kwargs: _multi_frame({"TCS.NS": [100.0], "DELISTED.NS": [None]}),
        )

        result = live.fetch_live({"ISIN_TCS": "TCS.NS", "ISIN_DEAD": "DELISTED.NS"})

        assert result == {"ISIN_TCS": Decimal("100")}


@pytest.mark.parametrize(
    ("exchange", "expected_suffix"),
    [("NSE", ".NS"), ("BSE", ".BO"), ("BOTH", ".NS"), (None, ".NS")],
)
def test_resolve_ticker_suffix_table(exchange: str | None, expected_suffix: str) -> None:
    assert live.resolve_ticker("XYZ", exchange).endswith(expected_suffix)
