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
# STRATEJİ A: Discount / Premium & FVG Likidite Avı
# =====================================================================
class StrategyA_OrderBlock(BaseStrategy):
    name = "Elit A (Discount/Premium & FVG)"

    def __init__(self, sl_atr_mult: float = 1.8, rr: float = 2.5):
        self.sl_atr_mult = sl_atr_mult
        self.rr = rr

    def analyze(self, df: pd.DataFrame, symbol: str, timeframe: str) -> Signal | None:
        if len(df) < 200: return None
        _clean_old_signals()
        df = df.iloc[:-1].reset_index(drop=True)
        d1 = _resample_closed(df, "1h", pd.Timedelta(hours=1))
        if len(d1) < 40: return None

        key = f"{symbol}_A"
        cur = df.iloc[-1]
        now_ts = cur["timestamp"]
        if key in _last_signal and (now_ts - _last_signal[key]).total_seconds() < 7200: return None

        price = float(cur["close"])
        c_open, c_high, c_low = float(cur["open"]), float(cur["high"]), float(cur["low"])
        eq = (d1["high"].iloc[-25:].max() + d1["low"].iloc[-25:].min()) / 2

        h, l, n = d1["high"].values, d1["low"].values, len(d1)
        fvg_zone = None
        for i in range(max(2, n - 12), n):
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
        if len(df) < 200: return None
        _clean_old_signals()
        df = df.iloc[:-1].reset_index(drop=True)
        d1 = _resample_closed(df, "1h", pd.Timedelta(hours=1))
        if len(d1) < 25: return None

        key = f"{symbol}_B"
        cur = df.iloc[-1]
        now_ts = cur["timestamp"]
        if key in _last_signal and (now_ts - _last_signal[key]).total_seconds() < 7200: return None

        c, o = d1["close"].values, d1["open"].values
        body = abs(c - o)
        avg_body = pd.Series(body).rolling(15).mean().iloc[-1]

        is_imp_bull = (c[-2] > o[-2]) and (body[-2] > 1.2 * avg_body)
        is_imp_bear = (c[-2] < o[-2]) and (body[-2] > 1.2 * avg_body)
        price = float(cur["close"])
        atr = float(_atr(d1).iloc[-1])
        if pd.isna(atr) or atr <= 0: return None

        vol_avg = df["volume"].iloc[-15:-1].mean()
        is_vol = float(cur["volume"]) > (vol_avg * 1.2)

        if is_imp_bull and price > o[-2] and is_vol and price > float(cur["open"]):
            sl = float(d1["low"].iloc[-2]) - (atr * 0.5)
            risk = price - sl
            if risk <= 0: return None
            tp = price + (risk * self.rr)
            _last_signal[key] = now_ts
            return Signal(type=SignalType.BUY, symbol=symbol, timeframe=timeframe, price=price,
                          strategy_name=self.name, strength=None, stop_loss=sl, take_profit=tp,
                          reason="🟢 Elit B: Impulse Devamı + Correction Sona Erdi")
        elif is_imp_bear and price < o[-2] and is_vol and price < float(cur["open"]):
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
# STRATEJİ C: Volume Profile POC Seviye Tepkisi
# =====================================================================
class StrategyC_TrendBreak(BaseStrategy):
    name = "Elit C (Volume Profile POC Tepkisi)"

    def __init__(self, sl_atr_mult: float = 2.0, rr: float = 3.0):
        self.sl_atr_mult = sl_atr_mult
        self.rr = rr

    def analyze(self, df: pd.DataFrame, symbol: str, timeframe: str) -> Signal | None:
        if len(df) < 200: return None
        _clean_old_signals()
        df = df.iloc[:-1].reset_index(drop=True)
        d1 = _resample_closed(df, "1h", pd.Timedelta(hours=1))
        if len(d1) < 40: return None

        key = f"{symbol}_C"
        cur = df.iloc[-1]
        now_ts = cur["timestamp"]
        if key in _last_signal and (now_ts - _last_signal[key]).total_seconds() < 7200: return None

        poc = ((d1["high"] + d1["low"] + d1["close"]) / 3 * d1["volume"]).sum() / d1["volume"].sum()
        price = float(cur["close"])
        atr = float(_atr(d1).iloc[-1])
        if pd.isna(atr) or atr <= 0: return None

        if abs(price - poc) / poc < 0.015 and float(cur["volume"]) > (df["volume"].iloc[-15:-1].mean() * 1.25):
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


# =====================================================================
# STRATEJİ D (YENİ): Market Structure Break (BOS / ChoCH Yapı Kırılımı)
# =====================================================================
class StrategyD_MarketStructure(BaseStrategy):
    name = "Elit D (BOS & Yapı Kırılımı)"

    def __init__(self, sl_atr_mult: float = 1.8, rr: float = 2.5):
        self.sl_atr_mult = sl_atr_mult
        self.rr = rr

    def analyze(self, df: pd.DataFrame, symbol: str, timeframe: str) -> Signal | None:
        if len(df) < 200: return None
        _clean_old_signals()
        df = df.iloc[:-1].reset_index(drop=True)
        d1 = _resample_closed(df, "1h", pd.Timedelta(hours=1))
        if len(d1) < 30: return None

        key = f"{symbol}_D"
        cur = df.iloc[-1]
        now_ts = cur["timestamp"]
        if key in _last_signal and (now_ts - _last_signal[key]).total_seconds() < 7200: return None

        price = float(cur["close"])
        atr = float(_atr(d1).iloc[-1])
        if pd.isna(atr) or atr <= 0: return None

        # Son 20 mumun en yüksek ve düşük seviyelerinin kırılması (Break of Structure)
        prev_high = d1["high"].iloc[-21:-1].max()
        prev_low = d1["low"].iloc[-21:-1].min()

        vol_avg = df["volume"].iloc[-15:-1].mean()
        is_vol = float(cur["volume"]) > (vol_avg * 1.3)

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
# STRATEJİ E (YENİ): Liquidity Sweep & Stop Hunt (Likidite Avı)
# =====================================================================
class StrategyE_LiquiditySweep(BaseStrategy):
    name = "Elit E (Likidite Sweep / Stop Avı)"

    def __init__(self, sl_atr_mult: float = 1.8, rr: float = 2.5):
        self.sl_atr_mult = sl_atr_mult
        self.rr = rr

    def analyze(self, df: pd.DataFrame, symbol: str, timeframe: str) -> Signal | None:
        if len(df) < 200: return None
        _clean_old_signals()
        df = df.iloc[:-1].reset_index(drop=True)
        d1 = _resample_closed(df, "1h", pd.Timedelta(hours=1))
        if len(d1) < 30: return None

        key = f"{symbol}_E"
        cur = df.iloc[-1]
        now_ts = cur["timestamp"]
        if key in _last_signal and (now_ts - _last_signal[key]).total_seconds() < 7200: return None

        price = float(cur["close"])
        c_high, c_low = float(cur["high"]), float(cur["low"])
        atr = float(_atr(d1).iloc[-1])
        if pd.isna(atr) or atr <= 0: return None

        # Son 20 mumun tepe ve diplerinin iğne ile alınıp içeri fiyatın geri çekilmesi
        recent_high = d1["high"].iloc[-21:-1].max()
        recent_low = d1["low"].iloc[-21:-1].min()

        # Boğa Sweep: Fiyat dip altını iğneleyip (sweep) hızlıca yukarı kapattıysa
        if c_low < recent_low and price > recent_low and price > float(cur["open"]):
            sl = c_low - (atr * 0.5)
            risk = price - sl
            if risk <= 0: return None
            tp = price + (risk * self.rr)
            _last_signal[key] = now_ts
            return Signal(type=SignalType.BUY, symbol=symbol, timeframe=timeframe, price=price,
                          strategy_name=self.name, strength=None, stop_loss=sl, take_profit=tp,
                          reason="🟢 Elit E: Dip Likiditesi Süpürüldü (Sweep) + Dönüş")
        # Ayı Sweep: Fiyat tepe üstünü iğneleyip aşağı kapattıysa
        elif c_high > recent_high and price < recent_high and price < float(cur["open"]):
            sl = c_high + (atr * 0.5)
            risk = sl - price
            if risk <= 0: return None
            tp = price - (risk * self.rr)
            _last_signal[key] = now_ts
            return Signal(type=SignalType.SELL, symbol=symbol, timeframe=timeframe, price=price,
                          strategy_name=self.name, strength=None, stop_loss=sl, take_profit=tp,
                          reason="🔴 Elit E: Tepe Likiditesi Süpürüldü (Sweep) + Dönüş")
        return None


# =====================================================================
# STRATEJİ F (YENİ): EMA-50 Trend Pullback (Dinamik Destek/Direnç)
# =====================================================================
class StrategyF_TrendBounce(BaseStrategy):
    name = "Elit F (EMA-50 Trend Pullback)"

    def __init__(self, sl_atr_mult: float = 2.0, rr: float = 3.0):
        self.sl_atr_mult = sl_atr_mult
        self.rr = rr

    def analyze(self, df: pd.DataFrame, symbol: str, timeframe: str) -> Signal | None:
        if len(df) < 200: return None
        _clean_old_signals()
        df = df.iloc[:-1].reset_index(drop=True)
        d1 = _resample_closed(df, "1h", pd.Timedelta(hours=1))
        if len(d1) < 60: return None

        key = f"{symbol}_F"
        cur = df.iloc[-1]
        now_ts = cur["timestamp"]
        if key in _last_signal and (now_ts - _last_signal[key]).total_seconds() < 7200: return None

        price = float(cur["close"])
        ema50 = float(d1["close"].ewm(span=50, adjust=False).mean().iloc[-1])
        atr = float(_atr(d1).iloc[-1])
        if pd.isna(atr) or atr <= 0: return None

        # Fiyat EMA-50'ye çok yakınsa (%0.4 içinde) ve oradan tepki alıyorsa
        dist = abs(price - ema50) / ema50
        is_near_ema = dist < 0.004

        vol_avg = df["volume"].iloc[-15:-1].mean()
        is_vol = float(cur["volume"]) > (vol_avg * 1.2)

        if is_near_ema and is_vol:
            if price > ema50 and price > float(cur["open"]):
                sl = price - (atr * self.sl_atr_mult)
                risk = price - sl
                if risk <= 0: return None
                tp = price + (risk * self.rr)
                _last_signal[key] = now_ts
                return Signal(type=SignalType.BUY, symbol=symbol, timeframe=timeframe, price=price,
                              strategy_name=self.name, strength=None, stop_loss=sl, take_profit=tp,
                              reason="🟢 Elit F: EMA-50 Trend Desteğinden Tepki")
            elif price < ema50 and price < float(cur["open"]):
                sl = price + (atr * self.sl_atr_mult)
                risk = sl - price
                if risk <= 0: return None
                tp = price - (risk * self.rr)
                _last_signal[key] = now_ts
                return Signal(type=SignalType.SELL, symbol=symbol, timeframe=timeframe, price=price,
                              strategy_name=self.name, strength=None, stop_loss=sl, take_profit=tp,
                              reason="🔴 Elit F: EMA-50 Trend Direncinden Tepki")
        return None
