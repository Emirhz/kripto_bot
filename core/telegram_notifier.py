import os
from telegram import Bot
from telegram.constants import ParseMode
from core.logger import log
from strategies.base import Signal, SignalType

class TelegramNotifier:
    def __init__(self):
        self.bot = Bot(token=os.getenv("TELEGRAM_BOT_TOKEN"))

    def _format(self, s: Signal) -> str:
        emoji = "🟢" if s.type == SignalType.BUY else "🔴"
        action = "ALIŞ" if s.type == SignalType.BUY else "SATIŞ"
        
        msg = f"{emoji} *{action} SİNYALİ*\n\n"
        msg += f"📊 *Parite:* `{s.symbol}`\n"
        msg += f"⏱ *Zaman:* `{s.timeframe}`\n"
        msg += f"💵 *Fiyat:* `{s.price:.6g}`\n"
        
        if s.stop_loss:
            msg += f"🛑 *Stop:* `{s.stop_loss:.6g}`\n"
        if s.take_profit:
            msg += f"✅ *Hedef:* `{s.take_profit:.6g}`\n"
            
        msg += f"🎯 *Güç:* {s.strength*100:.0f}%\n"
        msg += f"📝 _{s.reason}_"
        return msg

    async def send(self, signal: Signal):
        try:
            await self.bot.send_message(
                chat_id=os.getenv("TELEGRAM_CHAT_ID"),
                text=self._format(signal),
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            log.error(f"Telegram hatası: {e}")
