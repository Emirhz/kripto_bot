import pandas as pd
from strategies.base import BaseStrategy, Signal, SignalType
from strategies.ict_utils import detect_fvgs, detect_order_blocks, atr_series

class OrderBlockFVGStrategy(BaseStrategy):
    name = "Trend Korumalı FVG & OB Teması"

    def __init__(self, sl_atr_mult: float = 1.0, rr: float = 2.0):
        self.sl_atr_mult = sl_atr_mult
        self.rr = rr

    def analyze(self, df: pd.DataFrame, symbol: str, timeframe: str) -> Signal | None:
        if len(df) < 100: return None
        
        # ANLIK VERİ
        cur = df.iloc[-1]
        price = float(cur["close"])
        cur_high = float(cur["high"])
        cur_low = float(cur["low"])
        
        atr = atr_series(df)
        cur_atr = float(atr.iloc[-1])
        if pd.isna(cur_atr) or cur_atr <= 0: return None

        # --- 1. MAKRO TREND (4 SAATLİK EMA 200) ---
        df_4h = df.resample('4H', on='timestamp').agg({
            'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
        }).dropna()
        
        # Eğer yeterli 4 saatlik veri yoksa işlem yapma
        if len(df_4h) < 50: return None
        
        ema200_4h = df_4h["close"].ewm(span=200, adjust=False).mean().iloc[-1]
        
        # Yön Belirleme: Fiyat 4H EMA 200'ün üzerinde mi altında mı?
        macro_trend_up = price > ema200_4h
        macro_trend_down = price < ema200_4h

        # --- 2. BÖLGELERİ BUL ---
        fvgs_15m = detect_fvgs(df, lookback=100)
        obs_15m = detect_order_blocks(df, impulse_mult=1.5, lookback=100)
        
        fvgs_4h = detect_fvgs(df_4h, lookback=50)
        obs_4h = detect_order_blocks(df_4h, impulse_mult=1.5, lookback=50)

        # Tüm bölgeleri birleştir (15m ve 4H)
        all_zones = fvgs_15m + obs_15m + fvgs_4h + obs_4h
        all_zones.sort(key=lambda x: x.start_idx, reverse=True)

        for zone in all_zones:
            # Fiyat bölgeye değdi mi? (Anlık temas)
            if cur_low <= zone.top and cur_high >= zone.bottom:
                
                # --- ALIŞ (LONG) ŞARTLARI ---
                # Sadece 4 Saatlik Trend YUKARI ise ve bölge Boğa (Bullish) ise
                if macro_trend_up and zone.direction == "bullish":
                    sl = zone.bottom - (cur_atr * self.sl_atr_mult)
                    risk = price - sl
                    if risk > 0:
                        tp = price + (risk * self.rr)
                        return Signal(
                            type=SignalType.BUY, symbol=symbol, timeframe=timeframe,
                            price=price, strategy_name=self.name, strength=0.90,
                            stop_loss=sl, take_profit=tp,
                            reason=f"🟢 4H Trend Yukarı + {zone.kind} Teması ({zone.bottom:.4g})"
                        )
                
                # --- SATIŞ (SHORT) ŞARTLARI ---
                # Sadece 4 Saatlik Trend AŞAĞI ise ve bölge Ayı (Bearish) ise
                if macro_trend_down and zone.direction == "bearish":
                    sl = zone.top + (cur_atr * self.sl_atr_mult)
                    risk = sl - price
                    if risk > 0:
                        tp = price - (risk * self.rr)
                        return Signal(
                            type=SignalType.SELL, symbol=symbol, timeframe=timeframe,
                            price=price, strategy_name=self.name, strength=0.90,
                            stop_loss=sl, take_profit=tp,
                            reason=f"🔴 4H Trend Aşağı + {zone.kind} Teması ({zone.top:.4g})"
                        )

        return None