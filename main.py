import asyncio
import os
import threading
from dotenv import load_dotenv
from flask import Flask

# .env dosyasını yükle (Eğer bilgisayarda çalıştırırsan diye)
load_dotenv()

from strategies.order_block_fvg import OrderBlockFVGStrategy
from core.market_data import MarketData
from core.telegram_notifier import TelegramNotifier
from core.logger import log

# --- RENDER İÇİN WEB SUNUCUSU (BOTU UYUTMAZ) ---
app = Flask(__name__)

@app.route('/')
def health_check():
    return "Bot is alive!", 200

def run_web_server():
    # Render genellikle PORT değişkenini otomatik atar
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
# ----------------------------------------------

async def main():
    log.info("Bot başlatıldı...")
    symbols = os.getenv("SYMBOLS", "BTC/USDT").split(",")
    timeframe = os.getenv("TIMEFRAME", "15m")
    
    strategy = OrderBlockFVGStrategy()
    notifier = TelegramNotifier()
    market = MarketData()

    for symbol in symbols:
        symbol = symbol.strip()
        log.info(f"Taranıyor: {symbol}")
        try:
            df = await market.fetch_ohlcv(symbol, timeframe)
            if not df.empty:
                signal = strategy.analyze(df, symbol, timeframe)
                if signal:
                    log.info(f"SİNYAL BULUNDU: {symbol}")
                    await notifier.send(signal)
                else:
                    log.info(f"Sinyal yok: {symbol}")
        except Exception as e:
            log.error(f"Hata ({symbol}): {e}")
                
    await market.close()
    log.info("Tarama tamamlandı.")

if __name__ == "__main__":
    # Arka planda web sunucusunu başlat (Render uyumasın diye)
    threading.Thread(target=run_web_server, daemon=True).start()
    
    # Botun ana döngüsünü çalıştır
    asyncio.run(main())