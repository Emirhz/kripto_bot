import pandas as pd
from strategies.base import BaseStrategy, Signal, SignalType
from strategies.ict_utils import atr_series

class OrderBlockFVGStrategy(BaseStrategy):
    name = "15M Liquidity Sweep + MSS + OB Retest"

    def __init__(self, lookback: int = 30, sl_atr_mult: float = 0.5, rr: float = 2.0):
        self.lookback = lookback
        self.sl_atr_mult = sl_atr_mult
        self.rr = rr

    def analyze(self, df: pd.DataFrame, symbol: str, timeframe: str) -> Signal | None:
        if len(df) < self.lookback + 10: return None
        
        # 15 Dakikalık mumun kapanmasını bekle
        cur_idx = len(df) - 2
        cur = df.iloc[-2]
        price = float(cur["close"])
        
        # ATR
        atr = atr_series(df)
        cur_atr = float(atr.iloc[-2])
        if pd.isna(cur_atr) or cur_atr <= 0: return None

        # Son 30 mumun en yüksek ve en düşük seviyeleri
        recent_low = df["low"].iloc[-self.lookback:-1].min()
        recent_high = df["high"].iloc[-self.lookback:-1].max()

        # --- 1. LİKİDİTE SÜPÜRMESİ (SWEEP) KONTROLÜ ---
        # Fiyat son 30 mumun dibinin altına fitil attı mı ama üstünde kapattı mı?
        sweep_buy = cur["low"] < recent_low and cur["close"] > recent_low
        sweep_sell = cur["high"] > recent_high and cur["close"] < recent_high

        # --- 2. MSS (PIYASA YAPISI DEĞİŞİMİ) KONTROLÜ ---
        # Sweep olduktan sonra, fiyat son 10 mumun zirvesini/dibini kırdı mı?
        # (Basitleştirilmiş MSS: Anlık mumun yönü ve gücü)
        mss_buy = sweep_buy and cur["close"] > cur["open"] and cur["close"] > df["high"].iloc[-5:-1].max()
        mss_sell = sweep_sell and cur["close"] < cur["open"] and cur["close"] < df["low"].iloc[-5:-1].min()

        # --- 3. ORDER BLOCK (OB) RETEST ---
        # Eğer Sweep ve MSS olduysa, bu bir OB (Order Block) oluşturur. 
        # Fiyatın o OB'ye geri gelip onay vermesi (şu anki mumun o bölgede kapanması)
        
        if mss_buy:
            # Alış yönünde sinyal
            sl = cur["low"] - (cur_atr * self.sl_atr_mult)
            risk = price - sl
            tp = price + (risk * self.rr)
            
            return Signal(
                type=SignalType.BUY, symbol=symbol, timeframe=timeframe,
                price=price, strategy_name=self.name, strength=0.95,
                stop_loss=sl, take_profit=tp,
                reason=f"🔥 Likidite Süpürüldü + MSS Yukarı Kırıldı ({recent_low:.4g})"
            )

        if mss_sell:
            # Satış yönünde sinyal
            sl = cur["high"] + (cur_atr * self.sl_atr_mult)
            risk = sl - price
            tp = price - (risk * self.rr)
            
            return Signal(
                type=SignalType.SELL, symbol=symbol, timeframe=timeframe,
                price=price, strategy_name=self.name, strength=0.95,
                stop_loss=sl, take_profit=tp,
                reason=f"🔥 Likidite Süpürüldü + MSS Aşağı Kırıldı ({recent_high:.4g})"
            )
                
        return None