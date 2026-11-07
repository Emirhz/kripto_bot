import asyncio
import datetime as dt
import os
import threading
from dotenv import load_dotenv
from flask import Flask

load_dotenv()

from strategies.stock_strategy import StockStrategy
from core.market_data_stock import MarketData
from core.telegram_notifier import TelegramNotifier
from core.logger import log

DEFAULT = ("THYAO.IS,ASELS.IS,KCHOL.IS,BIMAS.IS,EREGL.IS,TUPRS.IS,SISE.IS,AKBNK.IS,GARAN.IS,"
           "FROTO.IS,AAPL,MSFT,NVDA,AMZN,GOOGL,META,TSLA,AMD,NFLX,AVGO")
SCAN_HOUR_UTC = int(os.getenv("SCAN_HOUR_UTC", "5"))   # 05:00 UTC = 08:00 TR (borsa açılmadan önce)
INDEX_FILTER = os.getenv("INDEX_FILTER", "1") == "1"   # endeks 200 günlük ortalamanın altındaysa sinyal verme

app = Flask(__name__)


@app.route('/')
def health_check():
    return "Bot is alive!", 200


def run_web_server():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))


async def index_ok(market, cache, symbol):
    if not INDEX_FILTER:
        return True
    idx = "XU100.IS" if symbol.endswith(".IS") else "SPY"
    if idx not in cache:
        df = await market.fetch_ohlcv(idx, "1d", 400)
        if df.empty:
            log.error(f"Endeks verisi alınamadı: {idx} (filtre atlandı)")
            cache[idx] = True
        else:
            cache[idx] = bool(df.close.iloc[-1] > df.close.rolling(200).mean().iloc[-1])
        log.info(f"Endeks {idx} {'YUKARI trend' if cache[idx] else 'AŞAĞI trend (sinyaller engellenir)'}")
    return cache[idx]


async def scan():
    log.info("Hisse taraması başladı...")
    symbols = [s.strip() for s in os.getenv("STOCK_SYMBOLS", DEFAULT).split(",") if s.strip()]
    strategy, notifier, market = StockStrategy(), TelegramNotifier(), MarketData()
    cache = {}
    for symbol in symbols:
        try:
            df = await market.fetch_ohlcv(symbol, "1d", 600)
            if df.empty:
                log.info(f"Veri yok: {symbol}")
                continue
            signal = strategy.analyze(df, symbol, "1d")
            if not signal:
                log.info(f"Sinyal yok: {symbol}")
            elif not await index_ok(market, cache, symbol):
                log.info(f"Sinyal engellendi (endeks düşüşte): {symbol}")
            else:
                log.info(f"SİNYAL BULUNDU: {symbol}")
                await notifier.send(signal)
        except Exception as e:
            log.error(f"Hata ({symbol}): {e}")
    await market.close()
    log.info("Tarama tamamlandı.")


if __name__ == "__main__":
    threading.Thread(target=run_web_server, daemon=True).start()

    async def run_forever():
        last_day = None
        while True:
            now = dt.datetime.utcnow()
            if now.hour >= SCAN_HOUR_UTC and last_day != now.date():
                await scan()
                last_day = now.date()
            await asyncio.sleep(600)

    asyncio.run(run_forever())
