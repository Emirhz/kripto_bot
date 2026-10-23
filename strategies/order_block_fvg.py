import pandas as pd
from strategies.base import BaseStrategy, Signal, SignalType
from strategies.ict_utils import detect_order_blocks, detect_fvgs, atr_series, first_touch

class OrderBlockFVGStrategy(BaseStrategy):
    name = "15m OB + 4H FVG (Bağımsız Sinyaller)"

    def __init__(self, sl_atr_mult: float = 1.0, rr: float = 2.0):
        self.sl_atr_mult = sl_atr_mult
        self.rr = rr

    def analyze(self, df: pd.DataFrame, symbol: str, timeframe: str) -> Signal | None:
        if len(df) < 100: return None
        
        # Anlık fiyat
        cur_idx = len(df) - 1
        cur = df.iloc[-1]
        price = float(cur["close"])
        cur_high = float(cur["high"])
        cur_low = float(cur["low"])
        cur_open = float(cur["open"])
        
        # ATR
        atr = atr_series(df)
        cur_atr = float(atr.iloc[-1])
        if pd.isna(cur_atr) or cur_atr <= 0: return None

        # ==========================================
        # 1. KONTROL: 15 DAKİKALIK ORDER BLOCK (OB) TEPKİSİ
        # ==========================================
        obs_15m = detect_order_blocks(df, impulse_mult=2.0, lookback=100)

        for zone in obs_15m:
            if (cur_idx - zone.start_idx) > 50: continue
            if not first_touch(df, zone, cur_idx): continue

            # ALIŞ OB
            if zone.direction == "bullish" and cur_low <= zone.top and cur_high >= zone.bottom and price > cur_open:
                sl = zone.bottom - (cur_atr * self.sl_atr_mult)
                risk = price - sl
                if risk > 0:
                    tp = price + (risk * self.rr)
                    return Signal(
                        type=SignalType.BUY, symbol=symbol, timeframe=timeframe,
                        price=price, strategy_name=self.name, strength=0.90,
                        stop_loss=sl, take_profit=tp,
                        reason=f"🟢 15m OB Tepkisi ({zone.bottom:.4g} - {zone.top:.4g})"
                    )

            # SATIŞ OB
            if zone.direction == "bearish" and cur_high >= zone.bottom and cur_low <= zone.top and price < cur_open:
                sl = zone.top + (cur_atr * self.sl_atr_mult)
                risk = sl - price
                if risk > 0:
                    tp = price - (risk * self.rr)
                    return Signal(
                        type=SignalType.SELL, symbol=symbol, timeframe=timeframe,
                        price=price, strategy_name=self.name, strength=0.90,
                        stop_loss=sl, take_profit=tp,
                        reason=f"🔴 15m OB Tepkisi ({zone.bottom:.4g} - {zone.top:.4g})"
                    )

        # ==========================================
        # 2. KONTROL: 4 SAATLİK FVG TEMASI (Bağımsız)
        # ==========================================
        # 15 dakikalık veriyi 4 saatlik mumlara çevir
        df_4h = df.resample('4H', on='timestamp').agg({
            'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
        }).dropna()
        
        # Son 50 tane 4 saatlik mumdaki FVG'leri bul
        fvgs_4h = detect_fvgs(df_4h, lookback=50) 

        for fvg in fvgs_4h:
            # ALIŞ FVG (Fiyat 4H Boğa FVG'sine değdi ve tepki verdi)
            if fvg.direction == "bullish" and cur_low <= fvg.top and cur_high >= fvg.bottom and price > cur_open:
                sl = fvg.bottom - (cur_atr * self.sl_atr_mult)
                risk = price - sl
                if risk > 0:
                    tp = price + (risk * self.rr)
                    return Signal(
                        type=SignalType.BUY, symbol=symbol, timeframe=timeframe,
                        price=price, strategy_name=self.name, strength=0.95,
                        stop_loss=sl, take_profit=tp,
                        reason=f"🚀 4H Bullish FVG Teması ({fvg.bottom:.4g} - {fvg.top:.4g})"
                    )

            # SATIŞ FVG (Fiyat 4H Ayı FVG'sine değdi ve tepki verdi)
            if fvg.direction == "bearish" and cur_high >= fvg.bottom and cur_low <= fvg.top and price < cur_open:
                sl = fvg.top + (cur_atr * self.sl_atr_mult)
                risk = sl - price
                if risk > 0:
                    tp = price - (risk * self.rr)
                    return Signal(
                        type=SignalType.SELL, symbol=symbol, timeframe=timeframe,
                        price=price, strategy_name=self.name, strength=0.95,
                        stop_loss=sl, take_profit=tp,
                        reason=f"🔥 4H Bearish FVG Teması ({fvg.bottom:.4g} - {fvg.top:.4g})"
                    )

        return None