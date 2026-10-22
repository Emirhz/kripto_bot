import pandas as pd
from strategies.base import BaseStrategy, Signal, SignalType
from strategies.ict_utils import atr_series

class OrderBlockFVGStrategy(BaseStrategy):
    name = "EMA Kesisimi + Hacim + RSI (Momentum Scalp)"

    def __init__(self, sl_atr_mult: float = 1.0, rr: float = 1.5):
        self.sl_atr_mult = sl_atr_mult
        self.rr = rr

    def analyze(self, df: pd.DataFrame, symbol: str, timeframe: str) -> Signal | None:
        if len(df) < 30: return None
        
        # Son kapanan mumu al (iloc[-2])
        cur = df.iloc[-2]
        prev = df.iloc[-3]
        
        price = float(cur["close"])
        cur_volume = float(cur["volume"])
        
        # 1. EMA Hesaplamaları
        ema9 = df["close"].ewm(span=9, adjust=False).mean()
        ema21 = df["close"].ewm(span=21, adjust=False).mean()
        
        # 2. RSI Hesaplaması
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        current_rsi = rsi.iloc[-2]
        
        # 3. Hacim Ortalaması (Son 20 mum)
        vol_ma = df["volume"].rolling(window=20).mean().iloc[-2]
        
        # ATR (Stop Loss için)
        atr = atr_series(df)
        cur_atr = float(atr.iloc[-2])
        if pd.isna(cur_atr) or cur_atr <= 0: return None

        # --- SİNYAL KONTROLLERİ ---
        cross_up = (ema9.iloc[-3] <= ema21.iloc[-3]) and (ema9.iloc[-2] > ema21.iloc[-2])
        cross_down = (ema9.iloc[-3] >= ema21.iloc[-3]) and (ema9.iloc[-2] < ema21.iloc[-2])
        volume_spike = cur_volume > (vol_ma * 1.5)

        # ---------- BUY KURULUMU ----------
        if cross_up and volume_spike and current_rsi > 50:
            sl = price - (cur_atr * self.sl_atr_mult)
            risk = price - sl
            tp = price + (risk * self.rr)
            
            return Signal(
                type=SignalType.BUY, symbol=symbol, timeframe=timeframe,
                price=price, strategy_name=self.name,
                strength=0.85,
                stop_loss=sl, take_profit=tp,
                reason=f"EMA 9/21 Yukarı Kesti + Hacim Patlaması (RSI: {current_rsi:.1f})"
            )

        # ---------- SELL KURULUMU ----------
        if cross_down and volume_spike and current_rsi < 50:
            sl = price + (cur_atr * self.sl_atr_mult)
            risk = sl - price
            tp = price - (risk * self.rr)
            
            return Signal(
                type=SignalType.SELL, symbol=symbol, timeframe=timeframe,
                price=price, strategy_name=self.name,
                strength=0.85,
                stop_loss=sl, take_profit=tp,
                reason=f"EMA 9/21 Aşağı Kesti + Hacim Patlaması (RSI: {current_rsi:.1f})"
            )
                
        return None