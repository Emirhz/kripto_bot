import pandas as pd
from strategies.base import BaseStrategy, Signal, SignalType

_last_signal = {}

def _clean_old_signals():
    global _last_signal
    now = pd.Timestamp.now()
    _last_signal = {
        key: ts for key, ts in _last_signal.items()
        if pd.notna(ts) and (now - pd.Timestamp(ts)).total_seconds() < 18000 # 5 saat cooldown
    }

def _atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    pc = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - pc).abs(),
        (df["low"] - pc).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(n).mean()


# =====================================================================
# STRATEJİ A: 15M Range Discount / Premium & FVG
# =====================================================================
class StrategyA_OrderBlock(BaseStrategy):
    name = "Elit A (15M Range & FVG)"

    def __init__(self, sl_atr_mult: float = 1.5, rr: float = 2.0):
        self.sl_atr_mult = sl_atr_mult
        self.rr = rr

    def analyze(self, df: pd.DataFrame, symbol: str, timeframe: str) -> Signal | None:
        if len(df) < 50: return None
        _clean_old_signals()
        df = df.iloc[:-1].reset_index(drop=True)

        key = f"{symbol}_A"
        cur = df.iloc[-1]
        now_ts = cur["timestamp"] if "timestamp" in cur else pd.Timestamp.now()
        if key in _last_signal and (now_ts - _last_signal[key]).total_seconds() < 10800: return None

        price = float(cur["close"])
        c_open = float(cur["open"])
        atr = float(_atr(df).iloc[-1])
        if pd.isna(atr) or atr <= 0: return None

        recent_high = df["high"].iloc[-20:].max()
        recent_low = df["low"].iloc[-20:].min()
        eq = (recent_high + recent_low) / 2

        if price < eq and price > c_open and float(cur["volume"]) > df["volume"].iloc[-10:-1].mean():
            sl = recent_low - (atr * self.sl_atr_mult)
            risk = price - sl
            if risk <= 0: return None
            tp = price + (risk * self.rr)
            _last_signal[key] = now_ts
            return Signal(type=SignalType.BUY, symbol=symbol, timeframe=timeframe, price=price,
                          strategy_name=self.name, strength=None, stop_loss=sl, take_profit=tp,
                          reason="🟢 Elit A: 15M Discount Bölgesi Tepkisi")
        elif price > eq and price < c_open and float(cur["volume"]) > df["volume"].iloc[-10:-1].mean():
            sl = recent_high + (atr * self.sl_atr_mult)
            risk = sl - price
            if risk <= 0: return None
            tp = price - (risk * self.rr)
            _last_signal[key] = now_ts
            return Signal(type=SignalType.SELL, symbol=symbol, timeframe=timeframe, price=price,
                          strategy_name=self.name, strength=None, stop_loss=sl, take_profit=tp,
                          reason="🔴 Elit A: 15M Premium Bölgesi Tepkisi")
        return None


# =====================================================================
# STRATEJİ B: 15M Impulse & Correction
# =====================================================================
class StrategyB_FVG(BaseStrategy):
    name = "Elit B (15M Impulse Devamı)"

    def __init__(self, sl_atr_mult: float = 1.5, rr: float = 2.0):
        self.sl_atr_mult = sl_atr_mult
        self.rr = rr

    def analyze(self, df: pd.DataFrame, symbol: str, timeframe: str) -> Signal | None:
        if len(df) < 50: return None
        _clean_old_signals()
        df = df.iloc[:-1].reset_index(drop=True)

        key = f"{symbol}_B"
        cur = df.iloc[-1]
        now_ts = cur["timestamp"] if "timestamp" in cur else pd.Timestamp.now()
        if key in _last_signal and (now_ts - _last_signal[key]).total_seconds() < 10800: return None

        c, o = df["close"].values, df["open"].values
        body = abs(c - o)
        avg_body = pd.Series(body).rolling(10).mean().iloc[-1]

        price = float(cur["close"])
        c_open = float(cur["open"])
        atr = float(_atr(df).iloc[-1])
        if pd.isna(atr) or atr <= 0: return None

        if (c[-2] > o[-2]) and (body[-2] > 1.2 * avg_body) and price > c_open:
            sl = float(df["low"].iloc[-2]) - (atr * 0.3)
            risk = price - sl
            if risk <= 0: return None
            tp = price + (risk * self.rr)
            _last_signal[key] = now_ts
            return Signal(type=SignalType.BUY, symbol=symbol, timeframe=timeframe, price=price,
                          strategy_name=self.name, strength=None, stop_loss=sl, take_profit=tp,
                          reason="🟢 Elit B: 15M Impulse Devamı")
        elif (c[-2] < o[-2]) and (body[-2] > 1.2 * avg_body) and price < c_open:
            sl = float(df["high"].iloc[-2]) + (atr * 0.3)
            risk = sl - price
            if risk <= 0: return None
            tp = price - (risk * self.rr)
            _last_signal[key] = now_ts
            return Signal(type=SignalType.SELL, symbol=symbol, timeframe=timeframe, price=price,
                          strategy_name=self.name, strength=None, stop_loss=sl, take_profit=tp,
                          reason="🔴 Elit B: 15M Impulse Düşüşü")
        return None


# =====================================================================
# STRATEJİ C: 15M Pinbar / Reversal
# =====================================================================
class StrategyC_TrendBreak(BaseStrategy):
    name = "Elit C (15M Pinbar Reversal)"

    def __init__(self, sl_atr_mult: float = 1.5, rr: float = 2.0):
        self.sl_atr_mult = sl_atr_mult
        self.rr = rr

    def analyze(self, df: pd.DataFrame, symbol: str, timeframe: str) -> Signal | None:
        if len(df) < 50: return None
        _clean_old_signals()
        df = df.iloc[:-1].reset_index(drop=True)

        key = f"{symbol}_C"
        cur = df.iloc[-1]
        now_ts = cur["timestamp"] if "timestamp" in cur else pd.Timestamp.now()
        if key in _last_signal and (now_ts - _last_signal[key]).total_seconds() < 10800: return None

        price = float(cur["close"])
        c_open = float(cur["open"])
        c_high = float(cur["high"])
        c_low = float(cur["low"])
        atr = float(_atr(df).iloc[-1])
        if pd.isna(atr) or atr <= 0: return None

        body = abs(price - c_open)
        total_range = c_high - c_low
        is_pinbar = total_range > (2.0 * body) if body > 0 else False
        vol_spike = float(cur["volume"]) > (df["volume"].iloc[-10:-1].mean() * 1.2)

        if is_pinbar and vol_spike:
            if price > c_open:
                sl = c_low - (atr * 0.3)
                risk = price - sl
                if risk <= 0: return None
                tp = price + (risk * self.rr)
                _last_signal[key] = now_ts
                return Signal(type=SignalType.BUY, symbol=symbol, timeframe=timeframe, price=price,
                              strategy_name=self.name, strength=None, stop_loss=sl, take_profit=tp,
                              reason="🟢 Elit C: 15M Pinbar Dip Dönüşü")
            elif price < c_open:
                sl = c_high + (atr * 0.3)
                risk = sl - price
                if risk <= 0: return None
                tp = price - (risk * self.rr)
                _last_signal[key] = now_ts
                return Signal(type=SignalType.SELL, symbol=symbol, timeframe=timeframe, price=price,
                              strategy_name=self.name, strength=None, stop_loss=sl, take_profit=tp,
                              reason="🔴 Elit C: 15M Pinbar Tepe Dönüşü")
        return None


# =====================================================================
# STRATEJİ D: 15M BOS (Yapı Kırılımı)
# =====================================================================
class StrategyD_MarketStructure(BaseStrategy):
    name = "Elit D (15M BOS Kırılımı)"

    def __init__(self, sl_atr_mult: float = 1.5, rr: float = 2.0):
        self.sl_atr_mult = sl_atr_mult
        self.rr = rr

    def analyze(self, df: pd.DataFrame, symbol: str, timeframe: str) -> Signal | None:
        if len(df) < 50: return None
        _clean_old_signals()
        df = df.iloc[:-1].reset_index(drop=True)

        key = f"{symbol}_D"
        cur = df.iloc[-1]
        now_ts = cur["timestamp"] if "timestamp" in cur else pd.Timestamp.now()
        if key in _last_signal and (now_ts - _last_signal[key]).total_seconds() < 10800: return None

        price = float(cur["close"])
        c_open = float(cur["open"])
        atr = float(_atr(df).iloc[-1])
        if pd.isna(atr) or atr <= 0: return None

        prev_high = df["high"].iloc[-15:-1].max()
        prev_low = df["low"].iloc[-15:-1].min()

        if price > prev_high and price > c_open and float(cur["volume"]) > df["volume"].iloc[-10:-1].mean():
            sl = price - (atr * self.sl_atr_mult)
            risk = price - sl
            if risk <= 0: return None
            tp = price + (risk * self.rr)
            _last_signal[key] = now_ts
            return Signal(type=SignalType.BUY, symbol=symbol, timeframe=timeframe, price=price,
                          strategy_name=self.name, strength=None, stop_loss=sl, take_profit=tp,
                          reason="🟢 Elit D: 15M Boğa BOS Kırılımı")
        elif price < prev_low and price < c_open and float(cur["volume"]) > df["volume"].iloc[-10:-1].mean():
            sl = price + (atr * self.sl_atr_mult)
            risk = sl - price
            if risk <= 0: return None
            tp = price - (risk * self.rr)
            _last_signal[key] = now_ts
            return Signal(type=SignalType.SELL, symbol=symbol, timeframe=timeframe, price=price,
                          strategy_name=self.name, strength=None, stop_loss=sl, take_profit=tp,
                          reason="🔴 Elit D: 15M Ayı BOS Kırılımı")
        return None


# =====================================================================
# STRATEJİ E: 15M Liquidity Sweep (Stop Avı)
# =====================================================================
class StrategyE_LiquiditySweep(BaseStrategy):
    name = "Elit E (15M Likidite Sweep)"

    def __init__(self, sl_atr_mult: float = 1.5, rr: float = 2.0):
        self.sl_atr_mult = sl_atr_mult
        self.rr = rr

    def analyze(self, df: pd.DataFrame, symbol: str, timeframe: str) -> Signal | None:
        if len(df) < 50: return None
        _clean_old_signals()
        df = df.iloc[:-1].reset_index(drop=True)

        key = f"{symbol}_E"
        cur = df.iloc[-1]
        now_ts = cur["timestamp"] if "timestamp" in cur else pd.Timestamp.now()
        if key in _last_signal and (now_ts - _last_signal[key]).total_seconds() < 10800: return None

        price = float(cur["close"])
        c_open = float(cur["open"])
        c_high = float(cur["high"])
        c_low = float(cur["low"])
        atr = float(_atr(df).iloc[-1])
        if pd.isna(atr) or atr <= 0: return None

        recent_high = df["high"].iloc[-15:-1].max()
        recent_low = df["low"].iloc[-15:-1].min()

        if c_low < recent_low and price >= recent_low and price > c_open:
            sl = c_low - (atr * 0.3)
            risk = price - sl
            if risk <= 0: return None
            tp = price + (risk * self.rr)
            _last_signal[key] = now_ts
            return Signal(type=SignalType.BUY, symbol=symbol, timeframe=timeframe, price=price,
                          strategy_name=self.name, strength=None, stop_loss=sl, take_profit=tp,
                          reason="🟢 Elit E: 15M Dip Likiditesi Süpürüldü")
        elif c_high > recent_high and price <= recent_high and price < c_open:
            sl = c_high + (atr * self.sl_atr_mult)
            risk = sl - price
            if risk <= 0: return None
            tp = price - (risk * self.rr)
            _last_signal[key] = now_ts
            return Signal(type=SignalType.SELL, symbol=symbol, timeframe=timeframe, price=price,
                          strategy_name=self.name, strength=None, stop_loss=sl, take_profit=tp,
                          reason="🔴 Elit E: 15M Tepe Likiditesi Süpürüldü")
        return None


# =====================================================================
# STRATEJİ F: 15M EMA-20 Trend Pullback
# =====================================================================
class StrategyF_TrendBounce(BaseStrategy):
    name = "Elit F (15M EMA-20 Pullback)"

    def __init__(self, sl_atr_mult: float = 1.5, rr: float = 2.0):
        self.sl_atr_mult = sl_atr_mult
        self.rr = rr

    def analyze(self, df: pd.DataFrame, symbol: str, timeframe: str) -> Signal | None:
        if len(df) < 50: return None
        _clean_old_signals()
        df = df.iloc[:-1].reset_index(drop=True)

        key = f"{symbol}_F"
        cur = df.iloc[-1]
        now_ts = cur["timestamp"] if "timestamp" in cur else pd.Timestamp.now()
        if key in _last_signal and (now_ts - _last_signal[key]).total_seconds() < 10800: return None

        price = float(cur["close"])
        c_open = float(cur["open"])
        ema20 = float(df["close"].ewm(span=20, adjust=False).mean().iloc[-1])
        atr = float(_atr(df).iloc[-1])
        if pd.isna(atr) or atr <= 0: return None

        dist = abs(price - ema20) / ema20
        if dist < 0.003:
            if price > ema20 and price > c_open:
                sl = price - (atr * self.sl_atr_mult)
                risk = price - sl
                if risk <= 0: return None
                tp = price + (risk * self.rr)
                _last_signal[key] = now_ts
                return Signal(type=SignalType.BUY, symbol=symbol, timeframe=timeframe, price=price,
                              strategy_name=self.name, strength=None, stop_loss=sl, take_profit=tp,
                              reason="🟢 Elit F: 15M EMA-20 Desteğinden Tepki")
            elif price < ema20 and price < c_open:
                sl = price + (atr * self.sl_atr_mult)
                risk = sl - price
                if risk <= 0: return None
                tp = price - (risk * self.rr)
                _last_signal[key] = now_ts
                return Signal(type=SignalType.SELL, symbol=symbol, timeframe=timeframe, price=price,
                              strategy_name=self.name, strength=None, stop_loss=sl, take_profit=tp,
                              reason="🔴 Elit F: 15M EMA-20 Direncinden Tepki")
        return None
