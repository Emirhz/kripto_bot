import pandas as pd
from strategies.base import BaseStrategy, Signal, SignalType

# Sinyal için gereken minimum puan (en fazla 10).
# Çok sinyal geliyorsa yükselt (7-8), hiç gelmiyorsa düşür (5).
MIN_SCORE = 7

# Aynı coine tekrar sinyal gelmemesi için bekleme süresi (saat)
COOLDOWN_HOURS = 4

# --- TREND FİLTRESİ ---
TREND_FILTER = True
TREND_EMA = 50
NEUTRAL_BAND = 0.003

# Bellek sızıntısını (Memory Leak) önlemek için global sözlük yerine yönetim
_last_signal = {}

AGG = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}


def _clean_old_signals():
    """Bellekte biriken eski sinyal zamanlarını temizler."""
    global _last_signal
    now = pd.Timestamp.now(tz=None)
    _last_signal = {
        sym: ts for sym, ts in _last_signal.items()
        if pd.notna(ts) and (now - pd.Timestamp(ts)).total_seconds() < 86400  # Son 24 saat
    }


def _atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    pc = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - pc).abs(),
        (df["low"] - pc).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(n).mean()


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


def _trend_ok(d1: pd.DataFrame, price: float, want: str) -> bool:
    """1H EMA'ya göre sinyal yönü trendle uyumlu mu?"%"""
    if not TREND_FILTER or len(d1) < TREND_EMA + 10:
        return True
    
    ema = float(d1["close"].ewm(span=TREND_EMA, adjust=False).mean().iloc[-1])
    if ema <= 0:
        return True
    
    dist = (price - ema) / ema
    if abs(dist) <= NEUTRAL_BAND:
        return True
    if want == "bullish" and dist < 0:
        return False
    if want == "bearish" and dist > 0:
        return False
    return True


def _bias(d4: pd.DataFrame) -> int:
    """4H piyasa yapısı: son kırılım yukarıysa 1, aşağıysa -1."""
    if len(d4) < 10:
        return 0
    h = d4["high"].values
    l = d4["low"].values
    c = d4["close"].values
    bias = 0
    last_sh = None
    last_sl = None
    
    for i in range(len(c)):
        j = i - 2
        if j >= 2 and j + 2 < len(h):
            if h[j] > max(h[j - 2:j]) and h[j] > max(h[j + 1:j + 3]):
                last_sh = h[j]
            if l[j] < min(l[j - 2:j]) and l[j] < min(l[j + 1:j + 3]):
                last_sl = l[j]
        if last_sh is not None and c[i] > last_sh:
            bias = 1
            last_sh = None
        elif last_sl is not None and c[i] < last_sl:
            bias = -1
            last_sl = None
    return bias


def _build_zones(d: pd.DataFrame, delta: pd.Timedelta) -> list:
    """1H grafikte OB, FVG ve IFVG bölgelerini bulur."""
    if len(d) < 30:
        return []
    
    idx = d.index
    o = d["open"].values
    h = d["high"].values
    l = d["low"].values
    c = d["close"].values
    n = len(d)
    body = abs(c - o)
    avg = pd.Series(body).rolling(20).mean().values

    found = []
    for i in range(max(2, n - 60), n):
        # FVG
        if l[i] > h[i - 2]:
            found.append(("FVG", "bullish", l[i], h[i - 2], i))
        elif h[i] < l[i - 2]:
            found.append(("FVG", "bearish", l[i - 2], h[i], i))
        
        # Order Block (son ters mum + güçlü itme mumu)
        if not pd.isna(avg[i]) and body[i] > 1.4 * avg[i]:
            if c[i - 1] < o[i - 1] and c[i] > h[i - 1]:
                found.append(("OB", "bullish", h[i - 1], l[i - 1], i))
            elif c[i - 1] > o[i - 1] and c[i] < l[i - 1]:
                found.append(("OB", "bearish", h[i - 1], l[i - 1], i))

    zones = []
    for kind, direction, top, bottom, i in found:
        k_kind, k_dir = kind, direction
        valid_from = i
        alive = True
        for k in range(i + 1, n):
            if k_dir == "bullish" and c[k] < bottom:
                if k_kind == "FVG":
                    k_kind, k_dir, valid_from = "IFVG", "bearish", k
                else:
                    alive = False
                    break
            elif k_dir == "bearish" and c[k] > top:
                if k_kind == "FVG":
                    k_kind, k_dir, valid_from = "IFVG", "bullish", k
                else:
                    alive = False
                    break
        if alive and valid_from < len(idx):
            zones.append({
                "kind": k_kind,
                "direction": k_dir,
                "top": float(top),
                "bottom": float(bottom),
                "valid_from": idx[valid_from] + delta,
            })
    return zones


class OrderBlockFVGStrategy(BaseStrategy):
    name = "ICT Puanlı (4H Yapı + 1H OB/FVG/IFVG + 15m Tepki)"

    def __init__(self, sl_atr_mult: float = 1.5, rr: float = 2.0):
        self.sl_atr_mult = sl_atr_mult
        self.rr = rr

    def analyze(self, df: pd.DataFrame, symbol: str, timeframe: str) -> Signal | None:
        if len(df) < 250:
            return None

        _clean_old_signals()

        # Oluşmakta olan son mumu at, sadece kapanmış mumlarla çalış
        df = df.iloc[:-1].reset_index(drop=True)

        d4 = _resample_closed(df, "4h", pd.Timedelta(hours=4))
        d1 = _resample_closed(df, "1h", pd.Timedelta(hours=1))
        if len(d4) < 15 or len(d1) < 30:
            return None

        # 1) YÖN (Bias)
        bias = _bias(d4)
        if bias == 0:
            return None
        want = "bullish" if bias == 1 else "bearish"

        # 2) BÖLGELER
        zones = _build_zones(d1, pd.Timedelta(hours=1))
        zones = [z for z in zones if z["direction"] == want]
        if not zones:
            return None

        # 3) GİRİŞ MUMU
        cur = df.iloc[-1]
        now_ts = cur["timestamp"]
        price = float(cur["close"])
        c_open = float(cur["open"])
        c_high = float(cur["high"])
        c_low = float(cur["low"])

        # 3b) TREND FİLTRESİ (1H EMA)
        if not _trend_ok(d1, price, want):
            return None

        atr_series = _atr(d1)
        if atr_series.empty or pd.isna(atr_series.iloc[-1]):
            return None
        atr = float(atr_series.iloc[-1])
        if atr <= 0:
            return None

        # Cooldown Kontrolü
        last = _last_signal.get(symbol)
        if last is not None and (now_ts - last).total_seconds() < COOLDOWN_HOURS * 3600:
            return None

        recent_low = df["low"].iloc[-11:-1].min()
        recent_high = df["high"].iloc[-11:-1].max()
        
        # Güçlendirilmiş hacim filtresi (Ortalamanın 1.3 katı)
        vol_sma = df["volume"].iloc[-21:-1].mean()
        vol_ok = float(cur["volume"]) > (float(vol_sma) * 1.3) if vol_sma > 0 else False

        best = None
        for z in zones:
            top, bottom = z["top"], z["bottom"]
            mid = (top + bottom) / 2

            # Mum bölgeye değdi mi?
            if not (c_low <= top and c_high >= bottom):
                continue

            # Tepki mumu (renk + bölge ortasının doğru tarafında kapanış)
            if want == "bullish":
                if not (price > c_open and price >= mid):
                    continue
            else:
                if not (price < c_open and price <= mid):
                    continue

            score = 2  # 4H yapı uyumu
            score += 1 if z["kind"] == "FVG" else 2

            # İlk dokunuş mu?
            prior = df[(df["timestamp"] >= z["valid_from"]) & (df["timestamp"] < now_ts)]
            touched_before = ((prior["low"] <= top) & (prior["high"] >= bottom)).any()
            if not touched_before:
                score += 2

            # Confluence (Bölgelerin üst üste binişi)
            for o in zones:
                if o is z:
                    continue
                if o["kind"] != z["kind"] and o["bottom"] <= top and o["top"] >= bottom:
                    score += 2
                    break

            # Likidite süpürmesi (Sweep)
            if want == "bullish" and c_low < recent_low:
                score += 1
            if want == "bearish" and c_high > recent_high:
                score += 1

            if vol_ok:
                score += 1

            if best is None or score > best[0]:
                best = (score, z)

        if best is None or best[0] < MIN_SCORE:
            return None

        score, z = best
        if want == "bullish":
            sl = z["bottom"] - (atr * self.sl_atr_mult)
            risk = price - sl
            if risk <= 0:
                return None
            tp = price + (risk * self.rr)
            sig_type, emoji = SignalType.BUY, "🟢"
        else:
            sl = z["top"] + (atr * self.sl_atr_mult)
            risk = sl - price
            if risk <= 0:
                return None
            tp = price - (risk * self.rr)
            sig_type, emoji = SignalType.SELL, "🔴"

        _last_signal[symbol] = now_ts

        return Signal(
            type=sig_type, symbol=symbol, timeframe=timeframe,
            price=price, strategy_name=self.name,
            strength=min(score / 10, 1.0),
            stop_loss=sl, take_profit=tp,
            reason=f"{emoji} Puan {score}/10 | 4H yapı + 1H {z['kind']} tepkisi"
        )
