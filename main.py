import asyncio
import os
from strategies.order_block_fvg import OrderBlockFVGStrategy
from core.market_data import MarketData
from core.telegram_notifier import TelegramNotifier
from core.logger import log

async def main():
    log.info("Bot başlatıldı...")
    
    # --- TELEGRAM TEST MESAJI ---
    test_bot = TelegramNotifier()
    try:
        await test_bot.bot.send_message(
            chat_id=os.getenv("TELEGRAM_CHAT_ID"),
            text="✅ TEST BAŞARILI! Bot çalışıyor ve bağlantı kuruldu."
        )
        log.info("Telegram test mesajı gönderildi.")
    except Exception as e:
        log.error(f"TELEGRAM BAĞLANTI HATASI: {e}")
    # ----------------------------
    
    symbols = os.getenv("SYMBOLS", "BTC/USDT").split(",")
    timeframe = os.getenv("TIMEFRAME", "15m")
    
    strategy = OrderBlockFVGStrategy()
    notifier = TelegramNotifier()
    market = MarketData()

    for symbol in symbols:
        symbol = symbol.strip()
        log.info(f"Taranıyor: {symbol}")
        df = await market.fetch_ohlcv(symbol, timeframe)
        if not df.empty:
            signal = strategy.analyze(df, symbol, timeframe)
            if signal:
                log.info(f"SİNYAL BULUNDU: {symbol}")
                await notifier.send(signal)
            else:
                log.info(f"Sinyal yok: {symbol}")
                
    await market.close()
    log.info("Tarama tamamlandı.")

if __name__ == "__main__":
    asyncio.run(main())