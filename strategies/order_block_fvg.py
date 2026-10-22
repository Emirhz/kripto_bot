import pandas as pd
from strategies.base import BaseStrategy, Signal, SignalType
from strategies.ict_utils import (
    atr_series, detect_order_blocks, detect_fvgs, detect_ifvgs,
    zone_intact, first_touch
)

class OrderBlockFVGStrategy(BaseStrategy):
    name = "Saf Order Block (Anlık Giriş)"

    def __init__(self, lookback: int = 100, impulse_mult: float = 1.5, max_zone_age: int = 60,
                 proximity_atr: float = 0.3, sl_atr_mult: float = 0.5, rr: float = 2.0):
        self.lookback = lookback
        self.impulse_mult = impulse_mult
        self.max_zone_age = max_zone_age
        self.proximity_atr = proximity_atr
        self.sl_atr_mult = sl_atr_mult
        self.rr = rr

    def analyze(self, df: pd.DataFrame, symbol: str, timeframe: str) -> Signal | None:
        if len(df) < 200: return None
        atr = atr_series(df)
        cur_atr = float(atr.iloc[-1]) # ANLIK ATR
        if pd.isna(cur_atr) or cur_atr <= 0: return None

        # ANLIK FİYATI VE MUMU KULLAN (iloc[-1] yapıldı)
        cur_idx = len(df) - 1
        cur = df.iloc[-1]
        price, cur_high, cur_low, cur_open, cur_close = float(cur["close"]), float(cur["high"]), float(cur["low"]), float(cur["open"]), float(cur["close"])

        obs = detect_order_blocks(df, self.impulse_mult, self.lookback)
        fvgs = detect_fvgs(df, self.lookback)
        ifvgs = detect_ifvgs(df, fvgs)
        entry_zones = obs + ifvgs
        proximity = self.proximity_atr * cur_atr

        # EMA 200 Trend Filtresi (Anlık)
        ema200 = df["close"].ewm(span=200, adjust=False).mean().iloc[-1]

        # ---------- BUY KURULUMU (Trend Yukarı) ----------
        if price > ema200:
            buy_signal = self._check_setup(df, [z for z in entry_zones if z.direction == "bullish"], cur_idx, cur_atr, proximity, cur_low, cur_high, cur_close, cur_open, price, "buy")
            if buy_signal:
                return Signal(SignalType.BUY, symbol, timeframe, price, self.name, 0.80, buy_signal["sl"], buy_signal["tp"], buy_signal["reason"])

        # ---------- SELL KURULUMU (Trend Aşağı) ----------
        if price < ema200:
            sell_signal = self._check_setup(df, [z for z in entry_zones if z.direction == "bearish"], cur_idx, cur_atr, proximity, cur_low, cur_high, cur_close, cur_open, price, "sell")
            if sell_signal:
                return Signal(SignalType.SELL, symbol, timeframe, price, self.name, 0.80, sell_signal["sl"], sell_signal["tp"], sell_signal["reason"])
                
        return None

    def _check_setup(self, df, zones, cur_idx, cur_atr, proximity, cur_low, cur_high, cur_close, cur_open, price, side):
        if not zones: return None

        valid = []
        for z in zones:
            age = cur_idx - z.start_idx
            if age < 2 or age > self.max_zone_age: continue 
            if not zone_intact(df, z, cur_idx): continue 
            valid.append(z)

        if not valid: return None

        if side == "buy":
            candidates = [z for z in valid if z.top <= price + proximity]
            candidates.sort(key=lambda z: abs(z.top - price))
        else:
            candidates = [z for z in valid if z.bottom >= price - proximity]
            candidates.sort(key=lambda z: abs(z.bottom - price))
            
        if not candidates: return None
        zone = candidates[0]

        # Bölgeye değdi mi ve anlık mum yeşil/kırmızı mı?
        if side == "buy":
            touched = cur_low <= zone.top + proximity and cur_low >= zone.bottom - proximity
            body_confirm = cur_close > cur_open
        else:
            touched = cur_high >= zone.bottom - proximity and cur_high <= zone.top + proximity
            body_confirm = cur_close < cur_open

        if not (touched and body_confirm): return None
        
        if not first_touch(df, zone, cur_idx): return None

        if side == "buy":
            sl = zone.bottom - self.sl_atr_mult * cur_atr
            risk = price - sl
            if risk <= 0: return None
            tp = price + self.rr * risk
        else:
            sl = zone.top + self.sl_atr_mult * cur_atr
            risk = sl - price
            if risk <= 0: return None
            tp = price - self.rr * risk

        reason = f"⚡ ANLIK GİRİŞ: OB {zone.direction} ({zone.bottom:.4g} - {zone.top:.4g})"
        return {"sl": sl, "tp": tp, "reason": reason}