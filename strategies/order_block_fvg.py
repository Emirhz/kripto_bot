import pandas as pd
from strategies.base import BaseStrategy, Signal, SignalType

AGG = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
_last_signal = {}

def _clean_old_signals():
    """Bellek sızıntısını önlemek için eski sinyal kayıtlarını temizler."""
    global _last_signal
    now = pd.Timestamp.now()
    _last_signal = {
        key: ts for key, ts in _last_signal.items()
        if pd.notna(ts) and (now - pd.Timestamp(ts)).total_seconds() < 86400
    }

def _resample_closed(df: pd.DataFrame, rule: str, delta: pd.Timedelta) -> pd.DataFrame:
    """15m veriden üst zaman dilimi üretir, kapanmamış son mumu atar."""
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
# STRATEJİ A: Order Block & Likidite Süpürmesi
# ==========================================
class StrategyA_OrderBlock(BaseStrategy):
    name = "Strateji A (OB & Likidite Sweep)"

    def __init__(self, sl_atr_mult: float = 1.5, rr: float = 2.0):
        self.sl_atr_mult = sl_atr_mult
        self.rr = rr

    def analyze(self, df: pd.DataFrame, symbol: str, timeframe: str) -> Signal | None:
        if len(df) < 200:
            return None
        _clean_old_signals()
        
        df = df.iloc[:-1].reset_index(drop=True)
        d1 = _resample_closed(df, "1h", pd.Timedelta(hours=1))
        if len(d1) < 40:
            return None

        # Cooldown kontrolü (Strateji bazlı)
        key = f"{symbol}_A"
        cur = df.iloc[-1]
        now_ts = cur["timestamp"]
        if key in _last_signal and (now_ts - _last_signal[key]).total_seconds() < 14400: # 4 saat
            return None

        price = float(cur["close"])
        c_open = float(cur["open"])
        c_high = float(cur["high"])
        c_low = float(cur["low"])

        # 1H Order Block Tespiti
        o = d1["open"].values
        h = d1["high"].values
        l = d1["low"].values
        c = d1["close"].values
        n = len(d1)
        
        ob_zone = None
        for i in range(max(2, n - 30), n):
            body = abs(c[i] - o[i])
            avg_body = pd.Series(abs(c - o)).rolling(20).mean().iloc[i]
            if not pd.isna(avg_body) and body > 1.4 * avg_body:
                if c[i - 1] < o[i - 1] and c[i] > h[i - 1]: # Bullish OB
                    ob_zone = {"dir": "bullish", "top": h[i-1], "bottom": l[i-1]}
                elif c[i - 1] > o[i - 1] and c[i] < l[i - 1]: # Bearish OB
                    ob_zone = {"dir": "bearish", "top": h[i-1], "bottom": l[i-1]}

        if not ob_zone:
            return None

        atr = float(_atr(d1).iloc[-1])
        if pd.isna(atr) or atr <= 0:
            return None

        # Fiyat OB bölgesine değdi mi ve tepki verdi mi?
        top, bottom, direction = ob_zone["top"], ob_zone["bottom"], ob_zone["dir"]
        if not (c_low <= top and c_high >= bottom):
            return None

        if direction == "bullish" and price > c_open:
            sl = bottom - (atr * self.sl_atr_mult)
            risk = price - sl
            if risk <= 0: return None
            tp = price + (risk * self.rr)
            _last_signal[key] = now_ts
            return Signal(type=SignalType.BUY, symbol=symbol, timeframe=timeframe, price=price,
                          strategy_name=self.name, strength=0.8, stop_loss=sl, take_profit=tp,
                          reason="🟢 Strateji A: 1H Order Block & Boğa Tepkisi")

        elif direction == "bearish" and price < c_open:
            sl = top + (atr * self.sl_atr_mult)
            risk = sl - price
            if risk <= 0: return None
            tp = price - (risk * self.rr)
            _last_signal[key] = now_ts
            return Signal(type=SignalType.SELL, symbol=symbol, timeframe=timeframe, price=price,
                          strategy_name=self.name, strength=0.8, stop_loss=sl, take_profit=tp,
                          reason="🔴 Strateji A: 1H Order Block & Ayı Tepkisi")
        return None


# ==========================================
# STRATEJİ B: FVG & iFVG (Dengesizlik)
# ==========================================
class StrategyB_FVG(BaseStrategy):
    name = "Strateji B (FVG Dengesizlik)"

    def __init__(self, sl_atr_mult: float = 1.5, rr: float = 2.0):
        self.sl_atr_mult = sl_atr_mult
        self.rr = rr

    def analyze(self, df: pd.DataFrame, symbol: str, timeframe: str) -> Signal | None:
        if len(df) < 200:
            return None
        _clean_old_signals()

        df = df.iloc[:-1].reset_index(drop=True)
        d1 = _resample_closed(df, "1h", pd.Timedelta(hours=1))
        if len(d1) < 30:
            return None

        key = f"{symbol}_B"
        cur = df.iloc[-1]
        now_ts = cur["timestamp"]
        if key in _last_signal and (now_ts - _last_signal[key]).total_seconds() < 14400:
            return None

        price = float(cur["close"])
        c_open = float(cur["open"])
        c_high = float(cur["high"])
        c_low = float(cur["low"])

        h = d1["high"].values
        l = d1["low"].values
        n = len(d1)

        fvg_zone = None
        # Son mumlarda FVG arayalım
        for i in range(max(2, n - 20), n):
            if l[i] > h[i - 2]: # Bullish FVG
                fvg_zone = {"dir": "bullish", "top": l[i], "bottom": h[i - 2]}
            elif h[i] < l[i - 2]: # Bearish FVG
                fvg_zone = {"dir": "bearish", "top": l[i - 2], "bottom": h[i]}

        if not fvg_zone:
            return None

        atr = float(_atr(d1).iloc[-1])
        if pd.isna(atr) or atr <= 0: return None

        top, bottom, direction = fvg_zone["top"], fvg_zone["bottom"], fvg_zone["dir"]
        if not (c_low <= top and c_high >= bottom):
            return None

        if direction == "bullish" and price > c_open:
            sl = bottom - (atr * self.sl_atr_mult)
            risk = price - sl
            if risk <= 0: return None
            tp = price + (risk * self.rr)
            _last_signal[key] = now_ts
            return Signal(type=SignalType.BUY, symbol=symbol, timeframe=timeframe, price=price,
                          strategy_name=self.name, strength=0.8, stop_loss=sl, take_profit=tp,
                          reason="🟢 Strateji B: 1H FVG Boşluk Doldurma Tepkisi")

        elif direction == "bearish" and price < c_open:
            sl = top + (atr * self.sl_atr_mult)
            risk = sl - price
            if risk <= 0: return None
            tp = price - (risk * self.rr)
            _last_signal[key] = now_ts
            return Signal(type=SignalType.SELL, symbol=symbol, timeframe=timeframe, price=price,
                          strategy_name=self.name, strength=0.8, stop_loss=sl, take_profit=tp,
                          reason="🔴 Strateji B: 1H FVG Boşluk Doldurma Tepkisi")
        return None


# ==========================================
# STRATEJİ C: 4H Trend & Momentum Devamı
# ==========================================
class StrategyC_TrendBreak(BaseStrategy):
    name = "Strateji C (4H Trend & Momentum)"

    def __init__(self, sl_atr_mult: float = 1.8, rr: float = 2.0):
        self.sl_atr_mult = sl_atr_mult
        self.rr = rr

    def analyze(self, df: pd.DataFrame, symbol: str, timeframe: str) -> Signal | None:
        if len(df) < 200:
            return None
        _clean_old_signals()

        df = df.iloc[:-1].reset_index(drop=True)
        d4 = _resample_closed(df, "4h", pd.Timedelta(hours=4))
        d1 = _resample_closed(df, "1h", pd.Timedelta(hours=1))
        if len(d4) < 15 or len(d1) < 50:
            return None

        key = f"{symbol}_C"
        cur = df.iloc[-1]
        now_ts = cur["timestamp"]
        if key in _last_signal and (now_ts - _last_signal[key]).total_seconds() < 14400:
            return None

        price = float(cur["close"])
        
        # 4H Yapı Kararı (Basit Swing Yönü)
        h4_c = d4["close"].values
        h4_trend = 1 if h4_c[-1] > h4_c[-3] else -1

        # 1H EMA 50 Filtresi
        ema50 = float(d1["close"].ewm(span=50, adjust=False).mean().iloc[-1])
        atr = float(_atr(d1).iloc[-1])
        if pd.isna(atr) or atr <= 0: return None

        # Trend ve Momentum Uyumu
        if h4_trend == 1 and price > ema50 and float(cur["volume"]) > float(df["volume"].iloc[-20:-1].mean() * 1.4):
            sl = price - (atr * self.sl_atr_mult)
            risk = price - sl
            if risk <= 0: return None
            tp = price + (risk * self.rr)
            _last_signal[key] = now_ts
            return Signal(type=SignalType.BUY, symbol=symbol, timeframe=timeframe, price=price,
                          strategy_name=self.name, strength=0.85, stop_loss=sl, take_profit=tp,
                          reason="🟢 Strateji C: 4H Trend Devamı + Hacim Patlaması")

        elif h4_trend == -1 and price < ema50 and float(cur["volume"]) > float(df["volume"].iloc[-20:-1].mean() * 1.4):
            sl = price + (atr * self.sl_atr_mult)
            risk = sl - price
            if risk <= 0: return None
            tp = price - (risk * self.rr)
            _last_signal[key] = now_ts
            return Signal(type=SignalType.SELL, symbol=symbol, timeframe=timeframe, price=price,
                          strategy_name=self.name, strength=0.85, stop_loss=sl, take_profit=tp,
                          reason="🔴 Strateji C: 4H Düşüş Trendi + Hacim Patlaması")
        return None
