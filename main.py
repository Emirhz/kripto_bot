import asyncio
import os
import threading
from dotenv import load_dotenv
from flask import Flask

# .env dosyasını yükle (Eğer bilgisayarda çalıştırırsan diye)
load_dotenv()

# Yeni 3 stratejimizi içe aktarıyoruz
from strategies.order_block_fvg import (
    StrategyA_OrderBlock,
    StrategyB_FVG,
    StrategyC_TrendBreak
)
from core.market_data import MarketData
from core.telegram_notifier import TelegramNotifier
from core.logger import log
from market_regime import get_btc_regime, signal_allowed

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
    
    # 3 ayrı stratejimizi burada bir listeye (pakete) koyuyoruz
    strategies = [
        StrategyA_OrderBlock(),
        StrategyB_FVG(),
        StrategyC_TrendBreak()
    ]
    
    notifier = TelegramNotifier()
    market = MarketData()

    # BTC yönünü bir kez hesapla (tüm coinler için ortak filtre)
    btc_regime = "NEUTRAL"
    try:
        btc_df = await market.fetch_ohlcv("BTC/USDT", timeframe)
        if not btc_df.empty:
            btc_regime = get_btc_regime(btc_df)
    except Exception as e:
        log.error(f"BTC yönü alınamadı: {e}")
    log.info(f"BTC yönü: {btc_regime}")

    for symbol in symbols:
        symbol = symbol.strip()
        log.info(f"Taranıyor: {symbol}")
        try:
            df = await market.fetch_ohlcv(symbol, timeframe)
            if not df.empty:
                signal_found = False
                # Her coin için 3 stratejiyi sırayla denetle
                for strategy in strategies:
                    signal = strategy.analyze(df, symbol, timeframe)
                    if signal:
                        if not signal_allowed(signal, btc_regime):
                            log.info(f"Sinyal engellendi ({strategy.name} | BTC {btc_regime}): {symbol}")
                        else:
                            log.info(f"SİNYAL BULUNDU ({strategy.name}): {symbol}")
                            await notifier.send(signal)
                            signal_found = True
                            break # Aynı turda aynı coinden birden fazla sinyal çıkmasını engeller
                
                if not signal_found:
                    log.info(f"Sinyal yok: {symbol}")
                    
        except Exception as e:
            log.error(f"Hata ({symbol}): {e}")
                
    await market.close()
    log.info("Tarama tamamlandı.")

if __name__ == "__main__":
    # Arka planda web sunucusunu başlat (Render portu açık kalsın diye)
    threading.Thread(target=run_web_server, daemon=True).start()
    
    # Botun hiç durmaması için sonsuz döngü
    async def run_forever():
        while True:
            await main()
            log.info("Tarama bitti, 5 dakika bekleniyor...")
            await asyncio.sleep(300) # 300 saniye = 5 dakika bekle, sonra tekrar tara

    asyncio.run(run_forever())
