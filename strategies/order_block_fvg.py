import pandas as pd
from strategies.base import BaseStrategy, Signal, SignalType
from strategies.ict_utils import detect_order_blocks, detect_fvgs, atr_series, first_touch

class OrderBlockFVGStrategy(BaseStrategy):
    name = "Power of Timeframes (4H Yön + 1H OB/FVG + 15m Giriş)"

    def __init__(self, sl_atr_mult: float = 1.0, rr: float = 2.0):
        self.sl_atr_mult = sl_atr_mult
        self.rr = rr

    def analyze(self, df: pd.DataFrame, symbol: str, timeframe: str) -> Signal | None:
        if len(df) < 100: return None
        
        # Veriyi 4 Saatlik ve 1 Saatlik dilimlere çeviriyoruz
        df_4h = df.resample('4H', on='timestamp').agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}).dropna()
        df_1h = df.resample('1H', on='timestamp').agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}).dropna()
        
        if len(df_4h) < 50 or len(df_1h) < 50: return None

        # --- 1. ADIM: YÖN (4 SAATLİK TREND) ---
        ema200_4h = df_4h["close"].ewm(span=200, adjust=False).mean().iloc[-1]
        price_4h = df_4h["close"].iloc[-1]
        
        trend_up = price_4h > ema200_4h
        trend_down = price_4h < ema200_4h

        # --- 2. ADIM: BÖLGE (1 SAATLİK OB VE FVG) ---
        obs_1h = detect_order_blocks(df_1h, impulse_mult=1.5, lookback=50)
        fvgs_1h = detect_fvgs(df_1h, lookback=50)
        zones_1h = obs_1h + fvgs_1h

        # --- 3. ADIM: GİRİŞ (15 DAKİKALIK LİKİDİTE VE TEPKİ) ---
        cur_idx = len(df) - 1
        cur = df.iloc[-2] # 15m mumun kapanmasını bekle (onay için)
        price = float(cur["close"])
        cur_high = float(cur["high"])
        cur_low = float(cur["low"])
        cur_open = float(cur["open"])
        
        atr = atr_series(df)
        cur_atr = float(atr.iloc[-2])
        if pd.isna(cur_atr) or cur_atr <= 0: return None

        # Likidite süpürmesi (Son 10 mumun dibini/tepesini süpürdü mü?)
        recent_low_15m = df["low"].iloc[-10:-1].min()
        recent_high_15m = df["high"].iloc[-10:-1].max()
        sweep_buy = cur_low < recent_low_15m and cur["close"] > recent_low_15m
        sweep_sell = cur_high > recent_high_15m and cur["close"] < recent_high_15m

        for zone in zones_1h:
            # Bölgeye anlık olarak değdi mi?
            touched = cur_low <= zone.top and cur_high >= zone.bottom
            if not touched: continue
            
            # Aynı bölgeye daha önce değilmişse (İlk dokunuş)
            # 1H verisinde kontrol etmek yerine 15m'de o bölgeye daha önce girilmiş mi bakıyoruz
            # Basitlik için şimdilik sadece anlık temasa odaklanıyoruz.

            # --- ALIŞ KURULUMU ---
            if trend_up and zone.direction == "bullish":
                # Likidite süpürmesi VE Mum onayı (Yeşil mum) VE Bölgeye temas
                if sweep_buy and cur["close"] > cur["open"]:
                    sl = zone.bottom - (cur_atr * self.sl_atr_mult)
                    risk = price - sl
                    if risk > 0:
                        tp = price + (risk * self.rr)
                        return Signal(
                            type=SignalType.BUY, symbol=symbol, timeframe=timeframe,
                            price=price, strategy_name=self.name, strength=0.95,
                            stop_loss=sl, take_profit=tp,
                            reason=f"🟢 4H Trend Yukarı + 1H {zone.kind} Teması + 15m Onay"
                        )

            # --- SATIŞ KURULUMU ---
            if trend_down and zone.direction == "bearish":
                # Likidite süpürmesi VE Mum onayı (Kırmızı mum) VE Bölgeye temas
                if sweep_sell and cur["close"] < cur["open"]:
                    sl = zone.top + (cur_atr * self.sl_atr_mult)
                    risk = sl - price
                    if risk > 0:
                        tp = price - (risk * self.rr)
                        return Signal(
                            type=SignalType.SELL, symbol=symbol, timeframe=timeframe,
                            price=price, strategy_name=self.name, strength=0.95,
                            stop_loss=sl, take_profit=tp,
                            reason=f"🔴 4H Trend Aşağı + 1H {zone.kind} Teması + 15m Onay"
                        )

        return None