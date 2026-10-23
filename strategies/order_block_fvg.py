import pandas as pd
from strategies.base import BaseStrategy, Signal, SignalType
from strategies.ict_utils import detect_order_blocks, atr_series, first_touch

class OrderBlockFVGStrategy(BaseStrategy):
    name = "Saf OB Tepki Stratejisi"

    def __init__(self, sl_atr_mult: float = 1.0, rr: float = 2.0):
        self.sl_atr_mult = sl_atr_mult
        self.rr = rr

    def analyze(self, df: pd.DataFrame, symbol: str, timeframe: str) -> Signal | None:
        if len(df) < 50: return None
        
        # ANLIK FİYAT (Mum kapanışını beklemiyoruz, tepkiyi kaçırmamak için)
        cur_idx = len(df) - 1
        cur = df.iloc[-1]
        price = float(cur["close"])
        cur_high = float(cur["high"])
        cur_low = float(cur["low"])
        cur_open = float(cur["open"])
        
        # ATR (Stop mesafesi için)
        atr = atr_series(df)
        cur_atr = float(atr.iloc[-1])
        if pd.isna(cur_atr) or cur_atr <= 0: return None

        # Son 100 mumdaki Order Block'ları bul
        obs = detect_order_blocks(df, impulse_mult=1.5, lookback=100)

        for zone in obs:
            # Bölge çok eski olmasın (son 50 mum içinde oluşsun)
            if (cur_idx - zone.start_idx) > 50:
                continue
                
            # Bölge daha önce test EDİLMEMİŞ olsun (İlk dokunuş)
            if not first_touch(df, zone, cur_idx):
                continue

            # --- ALIŞ (Bullish OB) ---
            if zone.direction == "bullish":
                # Fiyat bölgeye bastı mı? (Bölgenin içine girdi mi)
                if cur_low <= zone.top and cur_high >= zone.bottom:
                    # Tepki var mı? (Anlık mum yeşil dönüyor mu?)
                    if price > cur_open:
                        sl = zone.bottom - (cur_atr * self.sl_atr_mult)
                        risk = price - sl
                        if risk > 0:
                            tp = price + (risk * self.rr)
                            return Signal(
                                type=SignalType.BUY, symbol=symbol, timeframe=timeframe,
                                price=price, strategy_name=self.name, strength=0.90,
                                stop_loss=sl, take_profit=tp,
                                reason=f"🟢 OB'ye Bastı ve Tepki Verdi ({zone.bottom:.4g} - {zone.top:.4g})"
                            )

            # --- SATIŞ (Bearish OB) ---
            if zone.direction == "bearish":
                # Fiyat bölgeye bastı mı?
                if cur_high >= zone.bottom and cur_low <= zone.top:
                    # Tepki var mı? (Anlık mum kırmızı dönüyor mu?)
                    if price < cur_open:
                        sl = zone.top + (cur_atr * self.sl_atr_mult)
                        risk = sl - price
                        if risk > 0:
                            tp = price - (risk * self.rr)
                            return Signal(
                                type=SignalType.SELL, symbol=symbol, timeframe=timeframe,
                                price=price, strategy_name=self.name, strength=0.90,
                                stop_loss=sl, take_profit=tp,
                                reason=f"🔴 OB'ye Bastı ve Tepki Verdi ({zone.bottom:.4g} - {zone.top:.4g})"
                            )

        return None