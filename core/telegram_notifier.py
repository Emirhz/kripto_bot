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
        return f"{emoji} *{action} SİNYALİ*\n\n📊 *Parite:* `{s.symbol}`\n⏱ *Zaman:* `{s.timeframe}`\n💵 *Fiyat:* `{s.price:.6g}`\n🎯 *Güç:* {s.strength*100:.0f}%\n📝 _{s.reason}_"

    async def send(self, signal: Signal):
        try:
            await self.bot.send_message(
                chat_id=os.getenv("TELEGRAM_CHAT_ID"),
                text=self._format(signal),
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            log.error(f"Telegram hatası: {e}")