import pandas as pd
from strategies.base import BaseStrategy, Signal, SignalType
from strategies.ict_utils import (
    atr_series, detect_order_blocks, detect_fvgs, detect_ifvgs,
    zone_intact, first_touch, overlapping_fvg,
)

class OrderBlockFVGStrategy(BaseStrategy):
    name = "OB + FVG + Likidite + RSI (Pro Max)"

    def __init__(self, lookback: int = 120, impulse_mult: float = 1.5, max_zone_age: int = 60,
                 proximity_atr: float = 0.5, sl_atr_mult: float = 0.5, rr: float = 2.0, min_strength: float = 0.40):
        self.lookback = lookback
        self.impulse_mult = impulse_mult
        self.max_zone_age = max_zone_age
        self.proximity_atr = proximity_atr
        self.sl_atr_mult = sl_atr_mult
        self.rr = rr
        self.min_strength = min_strength

    def analyze(self, df: pd.DataFrame, symbol: str, timeframe: str) -> Signal | None:
        if len(df) < 200: return None
        atr = atr_series(df)
        cur_atr = float(atr.iloc[-2])
        if pd.isna(cur_atr) or cur_atr <= 0: return None

        # KRİTİK: Mum kapanışını beklemek için son kapanan mumu (iloc[-2]) kullanıyoruz. 
        # Böylece 5 dakikada bir kontrol etse bile, 15 dakikalık mum kapanmadan sahte sinyal üretmez.
        cur_idx = len(df) - 2
        cur = df.iloc[-2]
        price, cur_high, cur_low, cur_open = float(cur["close"]), float(cur["high"]), float(cur["low"]), float(cur["open"])

        obs = detect_order_blocks(df, self.impulse_mult, self.lookback)
        fvgs = detect_fvgs(df, self.lookback)
        ifvgs = detect_ifvgs(df, fvgs)
        entry_zones = obs + ifvgs
        proximity = self.proximity_atr * cur_atr

        # EMA 200 Trend Filtresi
        ema200 = df["close"].ewm(span=200, adjust=False).mean().iloc[-2]
        
        # RSI 14 Filtresi (Aşırı alım/satım koruması)
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        current_rsi = rsi.iloc[-2]

        # ---------- BUY KURULUMU (EMA 200 ÜSTÜ + RSI 50 ALTI) ----------
        if price > ema200 and current_rsi < 50:
            buy_signal = self._check_setup(df, [z for z in entry_zones if z.direction == "bullish"], fvgs, cur_idx, cur_atr, proximity, cur_low, cur_high, float(cur["close"]), cur_open, price, "buy")
            if buy_signal:
                return Signal(SignalType.BUY, symbol, timeframe, price, self.name, buy_signal["strength"], buy_signal["sl"], buy_signal["tp"], buy_signal["reason"])

        # ---------- SELL KURULUMU (EMA 200 ALTI + RSI 50 ÜSTÜ) ----------
        if price < ema200 and current_rsi > 50:
            sell_signal = self._check_setup(df, [z for z in entry_zones if z.direction == "bearish"], fvgs, cur_idx, cur_atr, proximity, cur_low, cur_high, float(cur["close"]), cur_open, price, "sell")
            if sell_signal:
                return Signal(SignalType.SELL, symbol, timeframe, price, self.name, sell_signal["strength"], sell_signal["sl"], sell_signal["tp"], sell_signal["reason"])
                
        return None

    def _check_setup(self, df, zones, fvgs, cur_idx, cur_atr, proximity, cur_low, cur_high, cur_close, cur_open, price, side):
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

        if side == "buy":
            touched = cur_low <= zone.top + proximity and cur_low >= zone.bottom - proximity
            body_confirm = cur_close > cur_open
            recent_low = df["low"].iloc[-10:-1].min()
            sweep_confirmed = cur_low < recent_low and cur_close > recent_low
        else:
            touched = cur_high >= zone.bottom - proximity and cur_high <= zone.top + proximity
            body_confirm = cur_close < cur_open
            recent_high = df["high"].iloc[-10:-1].max()
            sweep_confirmed = cur_high > recent_high and cur_close < recent_high

        if not (touched and body_confirm and sweep_confirmed): return None
        if not first_touch(df, zone, cur_idx): return None

        strength = 0.5
        if zone.kind == "OB": strength += 0.15
        elif zone.kind == "IFVG": strength += 0.10
        strength += 0.20 # Likidite bonusu
        if overlapping_fvg("bullish" if side == "buy" else "bearish", fvgs, zone.top, zone.bottom): strength += 0.10
        
        strength = min(1.0, strength)
        if strength < self.min_strength: return None

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

        reason = f"🔥 Süpürme + {zone.kind} {zone.direction} (RSI Onaylı İlk Dokunuş)"
        return {"strength": strength, "sl": sl, "tp": tp, "reason": reason}