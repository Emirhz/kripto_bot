import pandas as pd
from strategies.base import BaseStrategy, Signal, SignalType
from strategies.ict_utils import detect_order_blocks, detect_fvgs, atr_series, first_touch

class OrderBlockFVGStrategy(BaseStrategy):
    name = "Anlık Temas (15m OB + 4H FVG)"

    def __init__(self, sl_atr_mult: float = 1.0, rr: float = 2.0):
        self.sl_atr_mult = sl_atr_mult
        self.rr = rr

    def analyze(self, df: pd.DataFrame, symbol: str, timeframe: str) -> Signal | None:
        if len(df) < 100: return None
        
        # ANLIK FİYAT VE MUM (Kapanmasını beklemiyoruz!)
        cur_idx = len(df) - 1
        cur = df.iloc[-1]
        price = float(cur["close"])
        cur_high = float(cur["high"])
        cur_low = float(cur["low"])
        
        # ATR (Stop mesafesi için)
        atr = atr_series(df)
        cur_atr = float(atr.iloc[-1])
        if pd.isna(cur_atr) or cur_atr <= 0: return None

        # ==========================================
        # 1. KONTROL: 15 DAKİKALIK ORDER BLOCK (OB) TEMASI
        # ==========================================
        obs_15m = detect_order_blocks(df, impulse_mult=2.0, lookback=100)

        for zone in obs_15m:
            # Bölge son 50 mum içinde oluşmuş olsun (taze)
            if (cur_idx - zone.start_idx) > 50: continue
            # Bölgeye daha önce değilmemiş olsun (ilk temas)
            if not first_touch(df, zone, cur_idx): continue

            # FİYAT BÖLGEYE DEĞDİ Mİ? (Mumun dibi bölgenin üstünden küçükse VEYA mumun tepesi bölgenin dibinden büyükse)
            # Yani fiyat o kutunun içine girdiyse...
            if cur_low <= zone.top and cur_high >= zone.bottom:
                
                # Eğer yön yukarıysa AL
                if zone.direction == "bullish":
                    sl = zone.bottom - (cur_atr * self.sl_atr_mult)
                    risk = price - sl
                    if risk > 0:
                        tp = price + (risk * self.rr)
                        return Signal(
                            type=SignalType.BUY, symbol=symbol, timeframe=timeframe,
                            price=price, strategy_name=self.name, strength=0.90,
                            stop_loss=sl, take_profit=tp,
                            reason=f"🟢 15m OB'ye ANLIK Temas ({zone.bottom:.4g} - {zone.top:.4g})"
                        )
                
                # Eğer yön aşağıysa SAT
                if zone.direction == "bearish":
                    sl = zone.top + (cur_atr * self.sl_atr_mult)
                    risk = sl - price
                    if risk > 0:
                        tp = price - (risk * self.rr)
                        return Signal(
                            type=SignalType.SELL, symbol=symbol, timeframe=timeframe,
                            price=price, strategy_name=self.name, strength=0.90,
                            stop_loss=sl, take_profit=tp,
                            reason=f"🔴 15m OB'ye ANLIK Temas ({zone.bottom:.4g} - {zone.top:.4g})"
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
            # FİYAT 4 SAATLİK FVG'YE DEĞDİ Mİ?
            if cur_low <= fvg.top and cur_high >= fvg.bottom:
                
                # Boğa FVG ise AL
                if fvg.direction == "bullish":
                    sl = fvg.bottom - (cur_atr * self.sl_atr_mult)
                    risk = price - sl
                    if risk > 0:
                        tp = price + (risk * self.rr)
                        return Signal(
                            type=SignalType.BUY, symbol=symbol, timeframe=timeframe,
                            price=price, strategy_name=self.name, strength=0.95,
                            stop_loss=sl, take_profit=tp,
                            reason=f"🚀 4H Bullish FVG'ye ANLIK Temas ({fvg.bottom:.4g} - {fvg.top:.4g})"
                        )

                # Ayı FVG ise SAT
                if fvg.direction == "bearish":
                    sl = fvg.top + (cur_atr * self.sl_atr_mult)
                    risk = sl - price
                    if risk > 0:
                        tp = price - (risk * self.rr)
                        return Signal(
                            type=SignalType.SELL, symbol=symbol, timeframe=timeframe,
                            price=price, strategy_name=self.name, strength=0.95,
                            stop_loss=sl, take_profit=tp,
                            reason=f"🔥 4H Bearish FVG'ye ANLIK Temas ({fvg.bottom:.4g} - {fvg.top:.4g})"
                        )

        return None