import pandas as pd
from strategies.base import BaseStrategy, Signal, SignalType
from strategies.ict_utils import atr_series

class OrderBlockFVGStrategy(BaseStrategy):
    name = "Hacim Onaylı Kırılım (Dengeli)"

    def __init__(self, lookback: int = 30, sl_atr_mult: float = 1.0, rr: float = 1.5):
        self.lookback = lookback
        self.sl_atr_mult = sl_atr_mult
        self.rr = rr

    def analyze(self, df: pd.DataFrame, symbol: str, timeframe: str) -> Signal | None:
        if len(df) < self.lookback + 20: return None
        
        # 15 Dakikalık mumun tam kapanmasını bekle (iloc[-2])
        cur = df.iloc[-2]
        price = float(cur["close"])
        cur_high = float(cur["high"])
        cur_low = float(cur["low"])
        cur_volume = float(cur["volume"])
        
        # ATR
        atr = atr_series(df)
        cur_atr = float(atr.iloc[-2])
        if pd.isna(cur_atr) or cur_atr <= 0: return None

        # Son 30 mumun en yüksek ve en düşük seviyeleri
        recent_high = df["high"].iloc[-self.lookback:-1].max()
        recent_low = df["low"].iloc[-self.lookback:-1].min()
        
        # Hacim Ortalaması (Son 20 mum)
        vol_ma = df["volume"].rolling(window=20).mean().iloc[-2]

        # ---------- BUY KURULUMU ----------
        # Direnç kırıldı mı, hacim patladı mı ve mum yeşil mi?
        if price > recent_high and cur_volume > (vol_ma * 1.5):
            if cur["close"] > cur["open"]:
                sl = price - (cur_atr * self.sl_atr_mult)
                risk = price - sl
                tp = price + (risk * self.rr)
                
                return Signal(
                    type=SignalType.BUY, symbol=symbol, timeframe=timeframe,
                    price=price, strategy_name=self.name, strength=0.90,
                    stop_loss=sl, take_profit=tp,
                    reason=f"🚀 Hacimli Direnç Kırılımı ({recent_high:.4g})"
                )

        # ---------- SELL KURULUMU ----------
        # Destek kırıldı mı, hacim patladı mı ve mum kırmızı mı?
        if price < recent_low and cur_volume > (vol_ma * 1.5):
            if cur["close"] < cur["open"]:
                sl = price + (cur_atr * self.sl_atr_mult)
                risk = sl - price
                tp = price - (risk * self.rr)
                
                return Signal(
                    type=SignalType.SELL, symbol=symbol, timeframe=timeframe,
                    price=price, strategy_name=self.name, strength=0.90,
                    stop_loss=sl, take_profit=tp,
                    reason=f"🔥 Hacimli Destek Kırılımı ({recent_low:.4g})"
                )
                
        return None