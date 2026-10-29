import pandas as pd
from strategies.base import BaseStrategy, Signal, SignalType

AGG = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
_last_signal = {}

def _clean_old_signals():
    global _last_signal
    now = pd.Timestamp.now()
    _last_signal = {
        key: ts for key, ts in _last_signal.items()
        if pd.notna(ts) and (now - pd.Timestamp(ts)).total_seconds() < 86400
    }

def _resample_closed(df: pd.DataFrame, rule: str, delta: pd.Timedelta) -> pd.DataFrame:
    if "timestamp" not in df.columns or len(df) == 0:
        return pd.DataFrame()
    try:
        res = df.resample(rule, on="timestamp").agg(AGG).dropna()
        if len(res) == 0:
            return res
        last_end = res.index[-1] + delta
        data_end = df["timestamp"].iloc[-1] + pd.Timedelta(minutes=15)
        if data_end < last_end:
            res = res.iloc[:-1]
        return res
    except Exception:
        return pd.DataFrame()

def _atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    pc = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - pc).abs(),
        (df["low"] - pc).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(n).mean()


# ==========================================
# STRATEJİ A: Sertleştirilmiş Order Block & Sweep
# ==========================================
class StrategyA_OrderBlock(BaseStrategy):
    name = "Elit Strateji A (Sert OB & Sweep)"

    def __init__(self, sl_atr_mult: float = 1.8, rr: float = 2.5):
        self.sl_atr_mult = sl_atr_mult
        self.rr = rr

    def analyze(self, df: pd.DataFrame, symbol: str, timeframe: str) -> Signal | None:
        if len(df) < 250:
            return None
        _clean_old_signals()
        
        df = df.iloc[:-1].reset_index(drop=True)
        d1 = _resample_closed(df, "1h", pd.Timedelta(hours=1))
        if len(d1) < 50:
            return None

        # Cooldown süresini 12 saate çıkarıyoruz ki aynı coin sürekli sinyal üretmesin
        key = f"{symbol}_A"
        cur = df.iloc[-1]
        now_ts = cur["timestamp"]
        if key in _last_signal and (now_ts - _last_signal[key]).total_seconds() < 43200: # 12 saat
            return None

        price = float(cur["close"])
        c_open = float(cur["open"])
        c_high = float(cur["high"])
        c_low = float(cur["low"])

        o = d1["open"].values
        h = d1["high"].values
        l = d1["low"].values
        c = d1["close"].values
        n = len(d1)
        
        ob_zone = None
        for i in range(max(2, n - 20), n):
            body = abs(c[i] - o[i])
            avg_body = pd.Series(abs(c - o)).rolling(20).mean().iloc[i]
            # Mum boyutu ortalamanın 1.6 katı olmalı (Daha sert bir kurumsal hareket)
            if not pd.isna(avg_body) and body > 1.6 * avg_body:
                if c[i - 1] < o[i - 1] and c[i] > h[i - 1]:
                    ob_zone = {"dir": "bullish", "top": h[i-1], "bottom": l[i-1]}
                elif c[i - 1] > o[i - 1] and c[i] < l[i - 1]:
                    ob_zone = {"dir": "bearish", "top": h[i-1], "bottom": l[i-1]}

        if not ob_zone:
            return None

        atr = float(_atr(d1).iloc[-1])
        if pd.isna(atr) or atr <= 0:
            return None

        top, bottom, direction = ob_zone["top"], ob_zone["bottom"], ob_zone["dir"]
        if not (c_low <= top and c_high >= bottom):
            return None

        # Hacim filtresi şart (Ortalamanın en az 1.5 katı hacim patlaması)
        vol_avg = df["volume"].iloc[-20:-1].mean()
        if float(cur["volume"]) < vol_avg * 1.5:
            return None

        if direction == "bullish" and price > c_open:
            sl = bottom - (atr * self.sl_atr_mult)
            risk = price - sl
            if risk <= 0: return None
            tp = price + (risk * self.rr)
            _last_signal[key] = now_ts
            return Signal(type=SignalType.BUY, symbol=symbol, timeframe=timeframe, price=price,
                          strategy_name=self.name, strength=0.9, stop_loss=sl, take_profit=tp,
                          reason="🟢 Elit A: Güçlü 1H OB + Hacim Patlaması")

        elif direction == "bearish" and price < c_open:
            sl = top + (atr * self.sl_atr_mult)
            risk = sl - price
            if risk <= 0: return None
            tp = price - (risk * self.rr)
            _last_signal[key] = now_ts
            return Signal(type=SignalType.SELL, symbol=symbol, timeframe=timeframe, price=price,
                          strategy_name=self.name, strength=0.9, stop_loss=sl, take_profit=tp,
                          reason="🔴 Elit A: Güçlü 1H OB + Hacim Patlaması")
        return None


# ==========================================
# STRATEJİ B: Sertleştirilmiş FVG Dengesizlik
# ==========================================
class StrategyB_FVG(BaseStrategy):
    name = "Elit Strateji B (Derin FVG)"

    def __init__(self, sl_atr_mult: float = 1.8, rr: float = 2.5):
        self.sl_atr_mult = sl_atr_mult
        self.rr = rr

    def analyze(self, df: pd.DataFrame, symbol: str, timeframe: str) -> Signal | None:
        if len(df) < 250:
            return None
        _clean_old_signals()

        df = df.iloc[:-1].reset_index(drop=True)
        d1 = _resample_closed(df, "1h", pd.Timedelta(hours=1))
        if len(d1) < 40:
            return None

        key = f"{symbol}_B"
        cur = df.iloc[-1]
        now_ts = cur["timestamp"]
        if key in _last_signal and (now_ts - _last_signal[key]).total_seconds() < 43200:
            return None

        price = float(cur["close"])
        c_open = float(cur["open"])
        c_high = float(cur["high"])
        c_low = float(cur["low"])

        h = d1["high"].values
        l = d1["low"].values
        n = len(d1)

        fvg_zone = None
        for i in range(max(2, n - 15), n):
            if l[i] > h[i - 2]:
                fvg_zone = {"dir": "bullish", "top": l[i], "bottom": h[i - 2]}
            elif h[i] < l[i - 2]:
                fvg_zone = {"dir": "bearish", "top": l[i - 2], "bottom": h[i]}

        if not fvg_zone:
            return None

        atr = float(_atr(d1).iloc[-1])
        if pd.isna(atr) or atr <= 0: return None

        top, bottom, direction = fvg_zone["top"], fvg_zone["bottom"], fvg_zone["dir"]
        if not (c_low <= top and c_high >= bottom):
            return None

        # FVG için de hacim onayı şart
        vol_avg = df["volume"].iloc[-20:-1].mean()
        if float(cur["volume"]) < vol_avg * 1.5:
            return None

        if direction == "bullish" and price > c_open:
            sl = bottom - (atr * self.sl_atr_mult)
            risk = price - sl
            if risk <= 0: return None
            tp = price + (risk * self.rr)
            _last_signal[key] = now_ts
            return Signal(type=SignalType.BUY, symbol=symbol, timeframe=timeframe, price=price,
                          strategy_name=self.name, strength=0.9, stop_loss=sl, take_profit=tp,
                          reason="🟢 Elit B: 1H FVG Boşluk Doldurma + Hacim Onayı")

        elif direction == "bearish" and price < c_open:
            sl = top + (atr * self.sl_atr_mult)
            risk = sl - price
            if risk <= 0: return None
            tp = price - (risk * self.rr)
            _last_signal[key] = now_ts
            return Signal(type=SignalType.SELL, symbol=symbol, timeframe=timeframe, price=price,
                          strategy_name=self.name, strength=0.9, stop_loss=sl, take_profit=tp,
                          reason="🔴 Elit B: 1H FVG Boşluk Doldurma + Hacim Onayı")
        return None


# ==========================================
# STRATEJİ C: 4H Trend & EMA 200 Majör Kırılım
# ==========================================
class StrategyC_TrendBreak(BaseStrategy):
    name = "Elit Strateji C (4H Trend & EMA200)"

    def __init__(self, sl_atr_mult: float = 2.0, rr: float = 3.0):
        self.sl_atr_mult = sl_atr_mult
        self.rr = rr

    def analyze(self, df: pd.DataFrame, symbol: str, timeframe: str) -> Signal | None:
        if len(df) < 250:
            return None
        _clean_old_signals()

        df = df.iloc[:-1].reset_index(drop=True)
        d4 = _resample_closed(df, "4h", pd.Timedelta(hours=4))
        d1 = _resample_closed(df, "1h", pd.Timedelta(hours=1))
        if len(d4) < 20 or len(d1) < 100:
            return None

        key = f"{symbol}_C"
        cur = df.iloc[-1]
        now_ts = cur["timestamp"]
        if key in _last_signal and (now_ts - _last_signal[key]).total_seconds() < 43200:
            return None

        price = float(cur["close"])
        
        # 4H Güçlü Yapı
        h4_c = d4["close"].values
        h4_trend = 1 if h4_c[-1] > h4_c[-4] else -1

        # 1H EMA 200 (Majör Trend Filtresi - Profesyoneller EMA 200 kullanır)
        ema200 = float(d1["close"].ewm(span=200, adjust=False).mean().iloc[-1])
        atr = float(_atr(d1).iloc[-1])
        if pd.isna(atr) or atr <= 0: return None

        vol_avg = df["volume"].iloc[-20:-1].mean()
        is_volume_spike = float(cur["volume"]) > (vol_avg * 1.8)

        # Şartlar çok daha sert: 4H trend + 1H EMA200 üstü/altı + devasa hacim
        if h4_trend == 1 and price > ema200 and is_volume_spike:
            sl = price - (atr * self.sl_atr_mult)
            risk = price - sl
            if risk <= 0: return None
            tp = price + (risk * self.rr)
            _last_signal[key] = now_ts
            return Signal(type=SignalType.BUY, symbol=symbol, timeframe=timeframe, price=price,
                          strategy_name=self.name, strength=0.95, stop_loss=sl, take_profit=tp,
                          reason="🟢 Elit C: 4H Majör Trend + EMA200 + Dev Hacim")

        elif h4_trend == -1 and price < ema200 and is_volume_spike:
            sl = price + (atr * self.sl_atr_mult)
            risk = sl - price
            if risk <= 0: return None
            tp = price - (risk * self.rr)
            _last_signal[key] = now_ts
            return Signal(type=SignalType.SELL, symbol=symbol, timeframe=timeframe, price=price,
                          strategy_name=self.name, strength=0.95, stop_loss=sl, take_profit=tp,
                          reason="🔴 Elit C: 4H Majör Düşüş Trendi + EMA200 + Dev Hacim")
        return None
