import ccxt.async_support as ccxt
import pandas as pd
import os
from core.logger import log

class MarketData:
    def __init__(self):
        exchange_cls = getattr(ccxt, os.getenv("EXCHANGE", "binance"))
        self.exchange = exchange_cls({"enableRateLimit": True})

    async def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 1000) -> pd.DataFrame:
        try:
            raw = await self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
            df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
            return df
        except Exception as e:
            log.error(f"Hata: {e}")
            return pd.DataFrame()

    async def close(self):
        await self.exchange.close()