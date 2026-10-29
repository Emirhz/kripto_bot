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


# =====================================================================
# STRATEJİ A: Discount / Premium & FVG Likidite Avı (Daha Esnek)
# =====================================================================
class StrategyA_OrderBlock(BaseStrategy):
    name = "Elit A (Discount/Premium & FVG)"

    def __init__(self, sl_atr_mult: float = 1.8, rr: float = 2.5):
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

        key = f"{symbol}_A"
        cur = df.iloc[-1]
        now_ts = cur["timestamp"]
        # Cooldown süresini 2 saate indirdik (7200 saniye)
        if key in _last_signal and (now_ts - _last_signal[key]).total_seconds() < 7200:
            return None

        price = float(cur["close"])
        c_open = float(cur["open"])
        c_high = float(cur["high"])
        c_low = float(cur["low"])

        recent_high = d1["high"].iloc[-25:].max()
        recent_low = d1["low"].iloc[-25:].min()
        eq = (recent_high + recent_low) / 2

        h = d1["high"].values
        l = d1["low"].values
        n = len(d1)
        fvg_zone = None
        for i in range(max(2, n - 12), n):
            if l[i] > h[i - 2]:
                fvg_zone = {"dir": "bullish", "top": l[i], "bottom": h[i - 2]}
            elif h[i] < l[i - 2]:
                fvg_zone = {"dir": "bearish", "top": l[i - 2], "bottom": h[i]}

        if not fvg_zone:
            return None

        atr = float(_atr(d1).iloc[-1])
        if pd.isna(atr) or atr <= 0: return None

        top, bottom, direction = fvg_zone["top"], fvg_zone["bottom"], fvg_zone["dir"]
        
        if direction == "bullish" and price < eq and c_low <= top and c_high >= bottom and price > c_open:
            sl = bottom - (atr * self.sl_atr_mult)
            risk = price - sl
            if risk <= 0: return None
            tp = price + (risk * self.rr)
            _last_signal[key] = now_ts
            return Signal(type=SignalType.BUY, symbol=symbol, timeframe=timeframe, price=price,
                          strategy_name=self.name, strength=None, stop_loss=sl, take_profit=tp,
                          reason="🟢 Elit A: Discount Bölgesi + FVG Likidite Tepkisi")

        elif direction == "bearish" and price > eq and c_low <= top and c_high >= bottom and price < c_open:
            sl = top + (atr * self.sl_atr_mult)
            risk = sl - price
            if risk <= 0: return None
            tp = price - (risk * self.rr)
            _last_signal[key] = now_ts
            return Signal(type=SignalType.SELL, symbol=symbol, timeframe=timeframe, price=price,
                          strategy_name=self.name, strength=None, stop_loss=sl, take_profit=tp,
                          reason="🔴 Elit A: Premium Bölgesi + FVG Likidite Tepkisi")
        return None


# =====================================================================
# STRATEJİ B: Impulse & Correction Bitişi (Daha Esnek)
# =====================================================================
class StrategyB_FVG(BaseStrategy):
    name = "Elit B (Impulse & Correction Bitişi)"

    def __init__(self, sl_atr_mult: float = 1.8, rr: float = 2.5):
        self.sl_atr_mult = sl_atr_mult
        self.rr = rr

    def analyze(self, df: pd.DataFrame, symbol: str, timeframe: str) -> Signal | None:
        if len(df) < 200:
            return None
        _clean_old_signals()

        df = df.iloc[:-1].reset_index(drop=True)
        d1 = _resample_closed(df, "1h", pd.Timedelta(hours=1))
        if len(d1) < 25:
            return None

        key = f"{symbol}_B"
        cur = df.iloc[-1]
        now_ts = cur["timestamp"]
        if key in _last_signal and (now_ts - _last_signal[key]).total_seconds() < 7200:
            return None

        c = d1["close"].values
        o = d1["open"].values
        body = abs(c - o)
        avg_body = pd.Series(body).rolling(15).mean().iloc[-1]

        # Katsayıyı 1.2 katına çekerek yakalanabilirliği artırdık
        is_impulse_bull = (c[-2] > o[-2]) and (body[-2] > 1.2 * avg_body)
        is_impulse_bear = (c[-2] < o[-2]) and (body[-2] > 1.2 * avg_body)

        price = float(cur["close"])
        atr = float(_atr(d1).iloc[-1])
        if pd.isna(atr) or atr <= 0: return None

        vol_avg = df["volume"].iloc[-15:-1].mean()
        is_volume_ok = float(cur["volume"]) > (vol_avg * 1.2)

        if is_impulse_bull and price > o[-2] and is_volume_ok and price > float(cur["open"]):
            sl = float(d1["low"].iloc[-2]) - (atr * 0.5)
            risk = price - sl
            if risk <= 0: return None
            tp = price + (risk * self.rr)
            _last_signal[key] = now_ts
            return Signal(type=SignalType.BUY, symbol=symbol, timeframe=timeframe, price=price,
                          strategy_name=self.name, strength=None, stop_loss=sl, take_profit=tp,
                          reason="🟢 Elit B: Impulse Devamı + Correction Sona Erdi")

        elif is_impulse_bear and price < o[-2] and is_volume_ok and price < float(cur["open"]):
            sl = float(d1["high"].iloc[-2]) + (atr * 0.5)
            risk = sl - price
            if risk <= 0: return None
            tp = price - (risk * self.rr)
            _last_signal[key] = now_ts
            return Signal(type=SignalType.SELL, symbol=symbol, timeframe=timeframe, price=price,
                          strategy_name=self.name, strength=None, stop_loss=sl, take_profit=tp,
                          reason="🔴 Elit B: Impulse Düşüşü + Correction Sona Erdi")
        return None


# =====================================================================
# STRATEJİ C: Volume Profile POC Seviye Tepkisi (Daha Esnek)
# =====================================================================
class StrategyC_TrendBreak(BaseStrategy):
    name = "Elit C (Volume Profile POC Tepkisi)"

    def __init__(self, sl_atr_mult: float = 2.0, rr: float = 3.0):
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

        key = f"{symbol}_C"
        cur = df.iloc[-1]
        now_ts = cur["timestamp"]
        if key in _last_signal and (now_ts - _last_signal[key]).total_seconds() < 7200:
            return None

        typical_price = (d1["high"] + d1["low"] + d1["close"]) / 3
        volume = d1["volume"]
        poc = (typical_price * volume).sum() / volume.sum()

        price = float(cur["close"])
        atr = float(_atr(d1).iloc[-1])
        if pd.isna(atr) or atr <= 0: return None

        dist_from_poc = abs(price - poc) / poc
        is_near_poc = dist_from_poc < 0.015  # Yakınlık bandını %1.5 yaptık

        vol_avg = df["volume"].iloc[-15:-1].mean()
        is_volume_spike = float(cur["volume"]) > (vol_avg * 1.25)

        if is_near_poc and is_volume_spike:
            if price > float(cur["open"]):
                sl = price - (atr * self.sl_atr_mult)
                risk = price - sl
                if risk <= 0: return None
                tp = price + (risk * self.rr)
                _last_signal[key] = now_ts
                return Signal(type=SignalType.BUY, symbol=symbol, timeframe=timeframe, price=price,
                              strategy_name=self.name, strength=None, stop_loss=sl, take_profit=tp,
                              reason="🟢 Elit C: Volume Profile POC Seviyesinden Sert Tepki")
            elif price < float(cur["open"]):
                sl = price + (atr * self.sl_atr_mult)
                risk = sl - price
                if risk <= 0: return None
                tp = price - (risk * self.rr)
                _last_signal[key] = now_ts
                return Signal(type=SignalType.SELL, symbol=symbol, timeframe=timeframe, price=price,
                              strategy_name=self.name, strength=None, stop_loss=sl, take_profit=tp,
                              reason="🔴 Elit C: Volume Profile POC Seviyesinden Sert Tepki")
        return None
