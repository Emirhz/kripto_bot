import pandas as pd
from strategies.base import BaseStrategy, Signal, SignalType
from strategies.ict_utils import atr_series

class OrderBlockFVGStrategy(BaseStrategy):
    name = "Kırılım + RSI & Hacim Onaylı"

    def __init__(self, lookback: int = 30, sl_atr_mult: float = 1.0, rr: float = 2.0):
        self.lookback = lookback
        self.sl_atr_mult = sl_atr_mult
        self.rr = rr

    def analyze(self, df: pd.DataFrame, symbol: str, timeframe: str) -> Signal | None:
        if len(df) < 50: return None
        
        # Mum kapanışını bekle
        cur = df.iloc[-2] 
        price = float(cur["close"])
        
        # 1. Trend ve Destek/Direnç Seviyeleri
        ema200 = df["close"].ewm(span=200, adjust=False).mean().iloc[-2]
        recent_high = df["high"].iloc[-self.lookback:-1].max()
        recent_low = df["low"].iloc[-self.lookback:-1].min()
        
        # 2. RSI (Aşırı Alım/Satım Koruması)
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        current_rsi = rsi.iloc[-2]
        
        # 3. Hacim Onayı (Gerçek Kırılım mı, Fakeout mu?)
        vol_ma = df["volume"].rolling(window=20).mean().iloc[-2]
        cur_vol = cur["volume"]

        # ATR
        atr = atr_series(df)
        cur_atr = float(atr.iloc[-2])
        if pd.isna(cur_atr) or cur_atr <= 0: return None

        # --- ALIŞ KURULUMU ---
        # Trend yukarı, direnç kırıldı, hacim var VE RSI 70'in üzerinde değil (tepeden almayalım)
        if price > ema200 and price > recent_high and cur_vol > (vol_ma * 1.2) and current_rsi < 70:
            # Mumun gövdesi sağlam mı? (Fitil değil)
            if (cur["close"] - cur["open"]) > (cur_atr * 0.3):
                sl = price - (cur_atr * self.sl_atr_mult)
                risk = price - sl
                tp = price + (risk * self.rr)
                
                return Signal(
                    type=SignalType.BUY, symbol=symbol, timeframe=timeframe,
                    price=price, strategy_name=self.name, strength=0.85,
                    stop_loss=sl, take_profit=tp,
                    reason=f"🚀 Kırılım + Hacim + RSI: {current_rsi:.1f} ({recent_high:.4g})"
                )

        # --- SATIŞ KURULUMU ---
        # Trend aşağı, destek kırıldı, hacim var VE RSI 30'un altında değil (dipten satmayalım)
        if price < ema200 and price < recent_low and cur_vol > (vol_ma * 1.2) and current_rsi > 30:
            # Mumun gövdesi sağlam mı? (Fitil değil)
            if (cur["open"] - cur["close"]) > (cur_atr * 0.3):
                sl = price + (cur_atr * self.sl_atr_mult)
                risk = sl - price
                tp = price - (risk * self.rr)
                
                return Signal(
                    type=SignalType.SELL, symbol=symbol, timeframe=timeframe,
                    price=price, strategy_name=self.name, strength=0.85,
                    stop_loss=sl, take_profit=tp,
                    reason=f"📉 Kırılım + Hacim + RSI: {current_rsi:.1f} ({recent_low:.4g})"
                )

        return None