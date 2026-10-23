import pandas as pd
from strategies.base import BaseStrategy, Signal, SignalType
from strategies.ict_utils import atr_series

class OrderBlockFVGStrategy(BaseStrategy):
    name = "Saf Fiyat Aksiyonu (Kırılım + Geri Test)"

    def __init__(self, lookback: int = 50, sl_atr_mult: float = 1.0, rr: float = 1.5):
        self.lookback = lookback
        self.sl_atr_mult = sl_atr_mult
        self.rr = rr

    def analyze(self, df: pd.DataFrame, symbol: str, timeframe: str) -> Signal | None:
        if len(df) < self.lookback + 10: return None
        
        # Anlık veriler (Mum kapanışını beklemez)
        cur = df.iloc[-1]
        price = float(cur["close"])
        cur_high = float(cur["high"])
        cur_low = float(cur["low"])
        
        # ATR (Sadece Stop Loss mesafesi için, yön için değil)
        atr = atr_series(df)
        cur_atr = float(atr.iloc[-1])
        if pd.isna(cur_atr) or cur_atr <= 0: return None

        # Son 50 mumun en yüksek ve en düşük seviyelerini bul (Destek/Direnç)
        recent_high = df["high"].iloc[-self.lookback:-1].max()
        recent_low = df["low"].iloc[-self.lookback:-1].min()

        # --- ALIŞ KURULUMU (Direnç Kırılımı ve Geri Test) ---
        # Fiyat son 50 mumun zirvesine değdi veya çok yaklaştı VE anlık mum yeşil mi?
        if cur_low <= recent_high + (cur_atr * 0.2) and price >= recent_high:
            if cur["close"] > cur["open"]: # Anlık mum yeşil (Alıcılar güçlü)
                
                sl = price - (cur_atr * self.sl_atr_mult)
                risk = price - sl
                tp = price + (risk * self.rr)
                
                return Signal(
                    type=SignalType.BUY, symbol=symbol, timeframe=timeframe,
                    price=price, strategy_name=self.name, strength=0.85,
                    stop_loss=sl, take_profit=tp,
                    reason=f"Fiyat Aksiyonu: {recent_high:.4g} Direncine Geri Test"
                )

        # --- SATIŞ KURULUMU (Destek Kırılımı ve Geri Test) ---
        # Fiyat son 50 mumun dibine değdi veya çok yaklaştı VE anlık mum kırmızı mı?
        if cur_high >= recent_low - (cur_atr * 0.2) and price <= recent_low:
            if cur["close"] < cur["open"]: # Anlık mum kırmızı (Satıcılar güçlü)
                
                sl = price + (cur_atr * self.sl_atr_mult)
                risk = sl - price
                tp = price - (risk * self.rr)
                
                return Signal(
                    type=SignalType.SELL, symbol=symbol, timeframe=timeframe,
                    price=price, strategy_name=self.name, strength=0.85,
                    stop_loss=sl, take_profit=tp,
                    reason=f"Fiyat Aksiyonu: {recent_low:.4g} Desteğine Geri Test"
                )
                
        return None