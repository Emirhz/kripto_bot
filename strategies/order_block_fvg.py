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
        df = df.copy()
        # Timestamp formatı ne olursa olsun datetime'a çevir (Sessiz hataları önler)
        if not pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
            if df["timestamp"].dtype in ['int64', 'float64']:
                df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            else:
                df["timestamp"] = pd.to_datetime(df["timestamp"])

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
# STRATEJİ A: Discount / Premium & FVG Likidite Avı
# =====================================================================
class StrategyA_OrderBlock(BaseStrategy):
    name = "Elit A (Discount/Premium & FVG)"

    def __init__(self, sl_atr_mult: float = 1.8, rr: float = 2.5):
        self.sl_atr_mult = sl_atr_mult
        self.rr = rr

    def analyze(self, df: pd.DataFrame, symbol: str, timeframe: str) -> Signal | None:
        if len(df) < 100: return None
        _clean_old_signals()
        df = df.iloc[:-1].reset_index(drop=True)
        d1 = _resample_closed(df, "1h", pd.Timedelta(hours=1))
        if len(d1) < 20: return None

        key = f"{symbol}_A"
        cur = df.iloc[-1]
        now_ts = cur["timestamp"]
        if key in _last_signal and (now_ts - _last_signal[key]).total_seconds() < 3600: return None # 1 saat cooldown

        price = float(cur["close"])
        c_open, c_high, c_low = float(cur["open"]), float(cur["high"]), float(cur["low"])
        eq = (d1["high"].iloc[-20:].max() + d1["low"].iloc[-20:].min()) / 2

        h, l, n = d1["high"].values, d1["low"].values, len(d1)
        fvg_zone = None
        for i in range(max(2, n - 10), n):
            if l[i] > h[i - 2]: fvg_zone = {"dir": "bullish", "top": l[i], "bottom": h[i - 2]}
            elif h[i] < l[i - 2]: fvg_zone = {"dir": "bearish", "top": l[i - 2], "bottom": h[i]}
        if not fvg_zone: return None

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
# STRATEJİ B: Impulse & Correction Bitişi
# =====================================================================
class StrategyB_FVG(BaseStrategy):
    name = "Elit B (Impulse & Correction Bitişi)"

    def __init__(self, sl_atr_mult: float = 1.8, rr: float = 2.5):
        self.sl_atr_mult = sl_atr_mult
        self.rr = rr

    def analyze(self, df: pd.DataFrame, symbol: str, timeframe: str) -> Signal | None:
        if len(df) < 100: return None
        _clean_old_signals()
        df = df.iloc[:-1].reset_index(drop=True)
        d1 = _resample_closed(df, "1h", pd.Timedelta(hours=1))
        if len(d1) < 15: return None

        key = f"{symbol}_B"
        cur = df.iloc[-1]
        now_ts = cur["timestamp"]
        if key in _last_signal and (now_ts - _last_signal[key]).total_seconds() < 3600: return None

        c, o = d1["close"].values, d1["open"].values
        body = abs(c - o)
        avg_body = pd.Series(body).rolling(10).mean().iloc[-1]

        is_imp_bull = (c[-2] > o[-2]) and (body[-2] > 1.05 * avg_body)
        is_imp_bear = (c[-2] < o[-2]) and (body[-2] > 1.05 * avg_body)
        price = float(cur["close"])
        atr = float(_atr(d1).iloc[-1])
        if pd.isna(atr) or atr <= 0: return None

        vol_avg = df["volume"].iloc[-10:-1].mean()
        is_vol = float(cur["volume"]) > (vol_avg * 1.05)

        if is_imp_bull and price > o[-2] and is_vol and price > float(cur["open"]):
            sl = float(d1["low"].iloc[-2]) - (atr * 0.4)
            risk = price - sl
            if risk <= 0: return None
            tp = price + (risk * self.rr)
            _last_signal[key] = now_ts
            return Signal(type=SignalType.BUY, symbol=symbol, timeframe=timeframe, price=price,
                          strategy_name=self.name, strength=None, stop_loss=sl, take_profit=tp,
                          reason="🟢 Elit B: Impulse Devamı + Correction Sona Erdi")
        elif is_imp_bear and price < o[-2] and is_vol and price < float(cur["open"]):
            sl = float(d1["high"].iloc[-2]) + (atr * 0.4)
            risk = sl - price
            if risk <= 0: return None
            tp = price - (risk * self.rr)
            _last_signal[key] = now_ts
            return Signal(type=SignalType.SELL, symbol=symbol, timeframe=timeframe, price=price,
                          strategy_name=self.name, strength=None, stop_loss=sl, take_profit=tp,
                          reason="🔴 Elit B: Impulse Düşüşü + Correction Sona Erdi")
        return None


# =====================================================================
# STRATEJİ C: Orderflow Imbalance & Delta Reversal
# =====================================================================
class StrategyC_TrendBreak(BaseStrategy):
    name = "Elit C (Orderflow Imbalance & Delta)"

    def __init__(self, sl_atr_mult: float = 1.8, rr: float = 2.5):
        self.sl_atr_mult = sl_atr_mult
        self.rr = rr

    def analyze(self, df: pd.DataFrame, symbol: str, timeframe: str) -> Signal | None:
        if len(df) < 100: return None
        _clean_old_signals()
        df = df.iloc[:-1].reset_index(drop=True)
        d1 = _resample_closed(df, "1h", pd.Timedelta(hours=1))
        if len(d1) < 15: return None

        key = f"{symbol}_C"
        cur = df.iloc[-1]
        now_ts = cur["timestamp"]
        if key in _last_signal and (now_ts - _last_signal[key]).total_seconds() < 3600: return None

        price = float(cur["close"])
        c_open = float(cur["open"])
        atr = float(_atr(d1).iloc[-1])
        if pd.isna(atr) or atr <= 0: return None

        vol_spike = float(cur["volume"]) > (df["volume"].iloc[-15:-1].mean() * 1.2)
        body_size = abs(price - c_open)
        total_range = float(cur["high"]) - float(cur["low"])
        is_pinbar = total_range > (2.0 * body_size) if body_size > 0 else False

        if vol_spike and is_pinbar:
            if price > c_open:
                sl = float(cur["low"]) - (atr * 0.4)
                risk = price - sl
                if risk <= 0: return None
                tp = price + (risk * self.rr)
                _last_signal[key] = now_ts
                return Signal(type=SignalType.BUY, symbol=symbol, timeframe=timeframe, price=price,
                              strategy_name=self.name, strength=None, stop_loss=sl, take_profit=tp,
                              reason="🟢 Elit C: Orderflow Delta Reversal + Alıcı Baskısı")
            elif price < c_open:
                sl = float(cur["high"]) + (atr * 0.4)
                risk = sl - price
                if risk <= 0: return None
                tp = price - (risk * self.rr)
                _last_signal[key] = now_ts
                return Signal(type=SignalType.SELL, symbol=symbol, timeframe=timeframe, price=price,
                              strategy_name=self.name, strength=None, stop_loss=sl, take_profit=tp,
                              reason="🔴 Elit C: Orderflow Delta Reversal + Satıcı Baskısı")
        return None


# =====================================================================
# STRATEJİ D: Market Structure Break (BOS)
# =====================================================================
class StrategyD_MarketStructure(BaseStrategy):
    name = "Elit D (BOS & Yapı Kırılımı)"

    def __init__(self, sl_atr_mult: float = 1.8, rr: float = 2.5):
        self.sl_atr_mult = sl_atr_mult
        self.rr = rr

    def analyze(self, df: pd.DataFrame, symbol: str, timeframe: str) -> Signal | None:
        if len(df) < 100: return None
        _clean_old_signals()
        df = df.iloc[:-1].reset_index(drop=True)
        d1 = _resample_closed(df, "1h", pd.Timedelta(hours=1))
        if len(d1) < 15: return None

        key = f"{symbol}_D"
        cur = df.iloc[-1]
        now_ts = cur["timestamp"]
        if key in _last_signal and (now_ts - _last_signal[key]).total_seconds() < 3600: return None

        price = float(cur["close"])
        atr = float(_atr(d1).iloc[-1])
        if pd.isna(atr) or atr <= 0: return None

        prev_high = d1["high"].iloc[-15:-1].max()
        prev_low = d1["low"].iloc[-15:-1].min()
        is_vol = float(cur["volume"]) > (df["volume"].iloc[-10:-1].mean() * 1.1)

        if price > prev_high and is_vol and price > float(cur["open"]):
            sl = price - (atr * self.sl_atr_mult)
            risk = price - sl
            if risk <= 0: return None
            tp = price + (risk * self.rr)
            _last_signal[key] = now_ts
            return Signal(type=SignalType.BUY, symbol=symbol, timeframe=timeframe, price=price,
                          strategy_name=self.name, strength=None, stop_loss=sl, take_profit=tp,
                          reason="🟢 Elit D: 1H Boğa Yapı Kırılımı (BOS) + Hacim")
        elif price < prev_low and is_vol and price < float(cur["open"]):
            sl = price + (atr * self.sl_atr_mult)
            risk = sl - price
            if risk <= 0: return None
            tp = price - (risk * self.rr)
            _last_signal[key] = now_ts
            return Signal(type=SignalType.SELL, symbol=symbol, timeframe=timeframe, price=price,
                          strategy_name=self.name, strength=None, stop_loss=sl, take_profit=tp,
                          reason="🔴 Elit D: 1H Ayı Yapı Kırılımı (BOS) + Hacim")
        return None


# =====================================================================
# STRATEJİ E: Liquidity Sweep & Stop Hunt
# =====================================================================
class StrategyE_LiquiditySweep(BaseStrategy):
    name = "Elit E (Likidite Sweep / Stop Avı)"

    def __init__(self, sl_atr_mult: float = 1.8, rr: float = 2.5):
        self.sl_atr_mult = sl_atr_mult
        self.rr = rr

    def analyze(self, df: pd.DataFrame, symbol: str, timeframe: str) -> Signal | None:
        if len(df) < 100: return None
        _clean_old_signals()
        df = df.iloc[:-1].reset_index(drop=True)
        d1 = _resample_closed(df, "1h", pd.Timedelta(hours=1))
        if len(d1) < 15: return None

        key = f"{symbol}_E"
        cur = df.iloc[-1]
        now_ts = cur["timestamp"]
        if key in _last_signal and (now_ts - _last_signal[key]).total_seconds() < 3600: return None

        price = float(cur["close"])
        c_high, c_low = float(cur["high"]), float(cur["low"])
        atr = float(_atr(d1).iloc[-1])
        if pd.isna(atr) or atr <= 0: return None

        recent_high = d1["high"].iloc[-15:-1].max()
        recent_low = d1["low"].iloc[-15:-1].min()

        if c_low < recent_low and price >= recent_low and price > float(cur["open"]):
            sl = c_low - (atr * 0.4)
            risk = price - sl
            if risk <= 0: return None
            tp = price + (risk * self.rr)
            _last_signal[key] = now_ts
            return Signal(type=SignalType.BUY, symbol=symbol, timeframe=timeframe, price=price,
                          strategy_name=self.name, strength=None, stop_loss=sl, take_profit=tp,
                          reason="🟢 Elit E: Dip Likiditesi Süpürüldü (Sweep) + Dönüş")
        elif c_high > recent_high and price <= recent_high and price < float(cur["open"]):
            sl = c_high + (atr * self.sl_atr_mult)
            risk = sl - price
            if risk <= 0: return None
            tp = price - (risk * self.rr)
            _last_signal[key] = now_ts
            return Signal(type=SignalType.SELL, symbol=symbol, timeframe=timeframe, price=price,
                          strategy_name=self.name, strength=None, stop_loss=sl, take_profit=tp,
                          reason="🔴 Elit E: Tepe Likiditesi Süpürüldü (Sweep) + Dönüş")
        return None


# =====================================================================
# STRATEJİ F: Session Open & Mitigation OB
# =====================================================================
class StrategyF_TrendBounce(BaseStrategy):
    name = "Elit F (Session Open & Mitigation OB)"

    def __init__(self, sl_atr_mult: float = 1.8, rr: float = 2.5):
        self.sl_atr_mult = sl_atr_mult
        self.rr = rr

    def analyze(self, df: pd.DataFrame, symbol: str, timeframe: str) -> Signal | None:
        if len(df) < 100: return None
        _clean_old_signals()
        df = df.iloc[:-1].reset_index(drop=True)
        d1 = _resample_closed(df, "1h", pd.Timedelta(hours=1))
        if len(d1) < 15: return None

        key = f"{symbol}_F"
        cur = df.iloc[-1]
        now_ts = cur["timestamp"]
        if key in _last_signal and (now_ts - _last_signal[key]).total_seconds() < 3600: return None

        price = float(cur["close"])
        c_open = float(cur["open"])
        atr = float(_atr(d1).iloc[-1])
        if pd.isna(atr) or atr <= 0: return None

        prev_body_top = max(float(d1["open"].iloc[-2]), float(d1["close"].iloc[-2]))
        prev_body_bot = min(float(d1["open"].iloc[-2]), float(d1["close"].iloc[-2]))

        if price >= prev_body_bot and price <= prev_body_top and price > c_open:
            vol_ok = float(cur["volume"]) > (df["volume"].iloc[-10:-1].mean() * 1.05)
            if vol_ok:
                sl = prev_body_bot - (atr * self.sl_atr_mult)
                risk = price - sl
                if risk <= 0: return None
                tp = price + (risk * self.rr)
                _last_signal[key] = now_ts
                return Signal(type=SignalType.BUY, symbol=symbol, timeframe=timeframe, price=price,
                              strategy_name=self.name, strength=None, stop_loss=sl, take_profit=tp,
                              reason="🟢 Elit F: Seviye Testi (Mitigation OB) + Alış Tepkisi")
        elif price <= prev_body_top and price >= prev_body_bot and price < c_open:
            vol_ok = float(cur["volume"]) > (df["volume"].iloc[-10:-1].mean() * 1.05)
            if vol_ok:
                sl = prev_body_top + (atr * self.sl_atr_mult)
                risk = sl - price
                if risk <= 0: return None
                tp = price - (risk * self.rr)
                _last_signal[key] = now_ts
                return Signal(type=SignalType.SELL, symbol=symbol, timeframe=timeframe, price=price,
                              strategy_name=self.name, strength=None, stop_loss=sl, take_profit=tp,
                              reason="🔴 Elit F: Seviye Testi (Mitigation OB) + Satış Tepkisi")
        return None
