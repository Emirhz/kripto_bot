import asyncio
import pandas as pd
from core.logger import log

# timeframe -> (yfinance interval, period)
_TF = {"1d": ("1d", "3y"), "1h": ("60m", "730d"), "15m": ("15m", "60d")}


class MarketData:
    """Hisse verisi (yfinance). Kripto MarketData ile aynı arayüz: fetch_ohlcv + close."""

    async def fetch_ohlcv(self, symbol: str, timeframe: str = "1d", limit: int = 600) -> pd.DataFrame:
        try:
            return await asyncio.to_thread(self._fetch, symbol, timeframe, limit)
        except Exception as e:
            log.error(f"Hata ({symbol}): {e}")
            return pd.DataFrame()

    def _fetch(self, symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
        import yfinance as yf
        interval, period = _TF.get(timeframe, _TF["1d"])
        d = yf.Ticker(symbol).history(period=period, interval=interval, auto_adjust=True)
        if d is None or d.empty:
            return pd.DataFrame()
        d = d.reset_index()
        d = d.rename(columns={d.columns[0]: "timestamp", "Open": "open", "High": "high",
                              "Low": "low", "Close": "close", "Volume": "volume"})
        d["timestamp"] = pd.to_datetime(d["timestamp"]).dt.tz_localize(None)
        d = d[["timestamp", "open", "high", "low", "close", "volume"]].dropna()
        return d.tail(limit).reset_index(drop=True)

    async def close(self):
        pass
