"""
multi_strategy.py
15 dakikalık 6 strateji (A-F) + mevcut ICT stratejisi tek çatı altında.
Sinyal mesajında hangi stratejiden geldiği yazar (ör. "Strateji A+D").

  A: Range & FVG (Premium/Discount)
  B: Impulse Devamı
  C: Pinbar Reversal
  D: BOS Kırılımı (hacimli)
  E: Likidite Sweep
  F: EMA-20 Pullback

Kurallar:
  - Aynı coinde iki strateji ZIT yön verirse sinyal verilmez.
  - Aynı yönde birden fazla strateji varsa tek sinyal çıkar, isimleri birleşir
    (ör. "A+E") ve güç puanı artar.
  - Her strateji ayrı ayrı açılıp kapatılabilir (ENABLED).
"""

import pandas as pd
from strategies.base import BaseStrategy, Signal, SignalType

# ---------------- AYARLAR ----------------
# Bir stratejiyi kapatmak için False yap (ör. "C": False)
ENABLED = {"A": True, "B": True, "C": True, "D": True, "E": True, "F": True}
USE_ICT = True            # mevcut ICT stratejisi de çalışsın mı
RR = 2.0                  # TP = risk x RR
SL_BUFFER_ATR = 0.3       # SL, yapının ötesine bu kadar ATR pay bırakır
MIN_RISK_ATR = 0.8        # SL mesafesi en az bu kadar ATR olsun (çok sıkı stop olmasın)
MAX_RISK_PCT = 0.03       # SL mesafesi fiyatın %3'ünden büyükse sinyal verme
COOLDOWN_HOURS = 3        # aynı coin + aynı strateji için bekleme süresi
SYMBOL_COOLDOWN_HOURS = 3 # aynı coine (A-F için) en fazla bu aralıkla sinyal gelsin
MIN_STRENGTH = 0.8        # güç puanı bunun altındaysa sinyal verme (1.0 = en güçlü)
# -----------------------------------------

SHORT_NAMES = {
    "A": "Range & FVG",
    "B": "Impulse Devamı",
    "C": "Pinbar Reversal",
    "D": "BOS Kırılımı",
    "E": "Likidite Sweep",
    "F": "EMA-20 Pullback",
    "ICT": "ICT 4H/1H",
}

_last = {}      # {(symbol, kod): zaman}
_last_sym = {}  # {symbol: zaman}


def _atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    pc = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - pc).abs(),
        (df["low"] - pc).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(n).mean()


class _X:
    """Kapanmış mumlardan hesaplanan ortak veriler."""

    def __init__(self, d: pd.DataFrame):
        self.o = d["open"].values.astype(float)
        self.h = d["high"].values.astype(float)
        self.l = d["low"].values.astype(float)
        self.c = d["close"].values.astype(float)
        self.v = d["volume"].values.astype(float)
        self.n = len(d)
        self.body = abs(self.c - self.o)
        self.atr = float(_atr(d).iloc[-1])
        cs = pd.Series(self.c)
        self.ema20 = cs.ewm(span=20, adjust=False).mean().values
        self.ema50 = cs.ewm(span=50, adjust=False).mean().values
        self.body_avg = pd.Series(self.body).rolling(20).mean().shift(1).values
        self.vol_avg = pd.Series(self.v).rolling(20).mean().shift(1).values

    def vol_ok(self, mult: float = 1.0) -> bool:
        va = self.vol_avg[-1]
        return not pd.isna(va) and self.v[-1] > mult * va


def _cand(side: str, sl: float, strength: float, note: str) -> dict:
    return {"side": side, "sl": float(sl), "strength": min(strength, 1.0), "note": note}


# ============ STRATEJİ A: 15M RANGE & FVG ============
def _strat_a(x: _X):
    n, L = x.n, 64
    hi = x.h[n - L - 1:n - 1].max()
    lo = x.l[n - L - 1:n - 1].min()
    rng = hi - lo
    if rng < 2.5 * x.atr:
        return None
    price = x.c[-1]
    pos = (price - lo) / rng  # 0 = range dibi, 1 = range tepesi

    for i in range(n - 2, n - 22, -1):
        if i < 2:
            break
        if x.l[i] > x.h[i - 2]:
            side, top, bot = "long", x.l[i], x.h[i - 2]
        elif x.h[i] < x.l[i - 2]:
            side, top, bot = "short", x.l[i - 2], x.h[i]
        else:
            continue

        # FVG anlamlı büyüklükte olmalı
        if (top - bot) < 0.3 * x.atr:
            continue
        # Ucuz bölgede long, pahalı bölgede short
        if side == "long" and pos > 0.35:
            continue
        if side == "short" and pos < 0.65:
            continue
        # FVG doldurulmuş / bozulmuş olmasın
        if side == "long" and (x.c[i + 1:n - 1] < bot).any():
            continue
        if side == "short" and (x.c[i + 1:n - 1] > top).any():
            continue
        # Güncel mum bölgeye değmeli ve tepki vermeli
        if not (x.l[-1] <= top and x.h[-1] >= bot):
            continue
        mid = (top + bot) / 2
        if side == "long":
            if not (price > x.o[-1] and price >= mid):
                continue
            sl = min(bot, x.l[-1]) - SL_BUFFER_ATR * x.atr
            zone = "Discount"
        else:
            if not (price < x.o[-1] and price <= mid):
                continue
            sl = max(top, x.h[-1]) + SL_BUFFER_ATR * x.atr
            zone = "Premium"

        strength = 0.7
        if x.vol_ok():
            strength += 0.1
        if (side == "long" and pos < 0.2) or (side == "short" and pos > 0.8):
            strength += 0.1
        return _cand(side, sl, strength, f"{zone} + FVG tepkisi")
    return None


# ============ STRATEJİ B: 15M IMPULSE DEVAMI ============
def _strat_b(x: _X):
    n = x.n
    for i in range(n - 4, n - 14, -1):
        ba, va = x.body_avg[i], x.vol_avg[i]
        if pd.isna(ba) or pd.isna(va):
            continue
        if x.body[i] < 2.0 * ba or x.body[i] < x.atr or x.v[i] < 1.3 * va:
            continue
        imp_hi, imp_lo = x.h[i], x.l[i]
        size = imp_hi - imp_lo
        if size <= 0:
            continue
        pb_lo = x.l[i + 1:n - 1].min()
        pb_hi = x.h[i + 1:n - 1].max()

        if x.c[i] > x.o[i]:  # yukarı itme
            if pb_hi > imp_hi or pb_lo <= imp_lo:
                continue
            retr = (imp_hi - pb_lo) / size
            if not (0.25 <= retr <= 0.65):
                continue
            if x.c[-1] > x.o[-1] and x.c[-1] > x.h[-2]:
                sl = min(pb_lo, x.l[-1]) - SL_BUFFER_ATR * x.atr
                s = 0.7 + (0.1 if x.vol_ok() else 0) + (0.1 if retr < 0.5 else 0)
                return _cand("long", sl, s, "İtme sonrası düzeltme bitti, yukarı devam")
        else:  # aşağı itme
            if pb_lo < imp_lo or pb_hi >= imp_hi:
                continue
            retr = (pb_hi - imp_lo) / size
            if not (0.25 <= retr <= 0.65):
                continue
            if x.c[-1] < x.o[-1] and x.c[-1] < x.l[-2]:
                sl = max(pb_hi, x.h[-1]) + SL_BUFFER_ATR * x.atr
                s = 0.7 + (0.1 if x.vol_ok() else 0) + (0.1 if retr < 0.5 else 0)
                return _cand("short", sl, s, "İtme sonrası düzeltme bitti, aşağı devam")
    return None


# ============ STRATEJİ C: 15M PINBAR REVERSAL ============
def _strat_c(x: _X):
    n = x.n
    rng = x.h[-1] - x.l[-1]
    if rng < 1.0 * x.atr:
        return None
    body = max(abs(x.c[-1] - x.o[-1]), 1e-12)
    upper = x.h[-1] - max(x.o[-1], x.c[-1])
    lower = min(x.o[-1], x.c[-1]) - x.l[-1]
    prev_lo = x.l[n - 21:n - 1].min()
    prev_hi = x.h[n - 21:n - 1].max()

    # Boğa pinbar: uzun alt iğne, son 20 mumun dibine yakın
    if lower >= 2 * body and lower >= 0.6 * rng and x.l[-1] <= prev_lo + 0.3 * x.atr:
        sl = x.l[-1] - SL_BUFFER_ATR * x.atr
        s = 0.7 + (0.1 if x.vol_ok() else 0) + (0.1 if x.c[-1] > x.o[-1] else 0)
        return _cand("long", sl, s, "Dipte boğa pinbar")
    # Ayı pinbar: uzun üst iğne, son 20 mumun tepesine yakın
    if upper >= 2 * body and upper >= 0.6 * rng and x.h[-1] >= prev_hi - 0.3 * x.atr:
        sl = x.h[-1] + SL_BUFFER_ATR * x.atr
        s = 0.7 + (0.1 if x.vol_ok() else 0) + (0.1 if x.c[-1] < x.o[-1] else 0)
        return _cand("short", sl, s, "Tepede ayı pinbar")
    return None


# ============ STRATEJİ D: 15M BOS KIRILIMI ============
def _strat_d(x: _X):
    n = x.n
    ba = x.body_avg[-1]
    if pd.isna(ba) or not x.vol_ok(1.5):
        return None
    # Kırılım mumu güçlü gövdeli olmalı
    if x.body[-1] < 1.2 * ba or x.body[-1] < 0.8 * x.atr:
        return None
    price = x.c[-1]
    rng = x.h[-1] - x.l[-1]
    if rng <= 0:
        return None

    # Yukarı kırılım: kırılmamış son swing tepesinin üstünde kapanış
    if (price > x.o[-1] and price > x.ema50[-1] and x.ema20[-1] > x.ema50[-1]
            and price >= x.l[-1] + 0.7 * rng):
        for j in range(n - 5, n - 45, -1):
            if j < 3:
                break
            if x.h[j] > x.h[j - 3:j].max() and x.h[j] > x.h[j + 1:j + 4].max():
                level = x.h[j]
                if (x.c[j + 1:n - 1] > level).any():
                    continue
                if price > level and x.c[-2] <= level:
                    sl = x.l[n - 10:].min() - SL_BUFFER_ATR * x.atr
                    s = 0.8 + (0.1 if x.vol_ok(2.0) else 0)
                    return _cand("long", sl, s, "Hacimli yukarı BOS")
                break
    # Aşağı kırılım
    if (price < x.o[-1] and price < x.ema50[-1] and x.ema20[-1] < x.ema50[-1]
            and price <= x.h[-1] - 0.7 * rng):
        for j in range(n - 5, n - 45, -1):
            if j < 3:
                break
            if x.l[j] < x.l[j - 3:j].min() and x.l[j] < x.l[j + 1:j + 4].min():
                level = x.l[j]
                if (x.c[j + 1:n - 1] < level).any():
                    continue
                if price < level and x.c[-2] >= level:
                    sl = x.h[n - 10:].max() + SL_BUFFER_ATR * x.atr
                    s = 0.8 + (0.1 if x.vol_ok(2.0) else 0)
                    return _cand("short", sl, s, "Hacimli aşağı BOS")
                break
    return None


# ============ STRATEJİ E: 15M LİKİDİTE SWEEP ============
def _strat_e(x: _X):
    n = x.n
    rng = x.h[-1] - x.l[-1]
    if rng <= 0:
        return None
    if not x.vol_ok():
        return None
    ref_lo = x.l[n - 31:n - 1].min()
    ref_hi = x.h[n - 31:n - 1].max()
    price = x.c[-1]

    # Dip süpürme: eski dibin altına iğne, içeri kapanış
    if (x.l[-1] < ref_lo - 0.05 * x.atr and (ref_lo - x.l[-1]) >= 0.2 * x.atr
            and price > ref_lo and price > x.o[-1] and price >= x.l[-1] + 0.5 * rng):
        sl = x.l[-1] - SL_BUFFER_ATR * x.atr
        s = 0.85
        return _cand("long", sl, s, "Dip likidite süpürüldü, içeri döndü")
    # Tepe süpürme
    if (x.h[-1] > ref_hi + 0.05 * x.atr and (x.h[-1] - ref_hi) >= 0.2 * x.atr
            and price < ref_hi and price < x.o[-1] and price <= x.h[-1] - 0.5 * rng):
        sl = x.h[-1] + SL_BUFFER_ATR * x.atr
        s = 0.85
        return _cand("short", sl, s, "Tepe likidite süpürüldü, içeri döndü")
    return None


# ============ STRATEJİ F: 15M EMA-20 PULLBACK ============
def _strat_f(x: _X):
    e20, e50 = x.ema20, x.ema50
    price, atr = x.c[-1], x.atr

    slope = e50[-1] - e50[-11]
    if (e20[-1] - e50[-1]) > 0.5 * atr and slope > 0.3 * atr and price > e50[-1]:
        touched = x.l[-1] <= e20[-1] + 0.1 * atr or x.l[-2] <= e20[-2] + 0.1 * atr
        if (touched and price > e20[-1] and price > x.o[-1] and price > x.c[-2]
                and (price - e20[-1]) < 1.0 * atr):
            sl = x.l[-3:].min() - SL_BUFFER_ATR * atr
            s = 0.7 + (0.1 if x.vol_ok() else 0)
            return _cand("long", sl, s, "EMA-20 desteğinden yukarı devam")
    if (e50[-1] - e20[-1]) > 0.5 * atr and slope < -0.3 * atr and price < e50[-1]:
        touched = x.h[-1] >= e20[-1] - 0.1 * atr or x.h[-2] >= e20[-2] - 0.1 * atr
        if (touched and price < e20[-1] and price < x.o[-1] and price < x.c[-2]
                and (e20[-1] - price) < 1.0 * atr):
            sl = x.h[-3:].max() + SL_BUFFER_ATR * atr
            s = 0.7 + (0.1 if x.vol_ok() else 0)
            return _cand("short", sl, s, "EMA-20 direncinden aşağı devam")
    return None


_STRATS = {"A": _strat_a, "B": _strat_b, "C": _strat_c,
           "D": _strat_d, "E": _strat_e, "F": _strat_f}


class MultiStrategy(BaseStrategy):
    name = "Çoklu Strateji (A-F + ICT)"

    def __init__(self):
        self.ict = None
        if USE_ICT:
            try:
                from strategies.order_block_fvg import OrderBlockFVGStrategy
                self.ict = OrderBlockFVGStrategy()
            except Exception:
                self.ict = None

    def analyze(self, df: pd.DataFrame, symbol: str, timeframe: str) -> Signal | None:
        if len(df) < 200:
            return None

        d = df.iloc[:-1].reset_index(drop=True)  # sadece kapanmış mumlar
        x = _X(d)
        if pd.isna(x.atr) or x.atr <= 0:
            return None
        ts = d["timestamp"].iloc[-1]
        price = float(x.c[-1])

        # --- A-F adaylarını topla ---
        cands = {}
        last_any = _last_sym.get(symbol)
        sym_wait = last_any is not None and (ts - last_any).total_seconds() < SYMBOL_COOLDOWN_HOURS * 3600
        for code, fn in _STRATS.items():
            if sym_wait or not ENABLED.get(code, False):
                continue
            last = _last.get((symbol, code))
            if last is not None and (ts - last).total_seconds() < COOLDOWN_HOURS * 3600:
                continue
            try:
                c = fn(x)
            except Exception:
                c = None
            if c is None:
                continue

            # SL düzeltmeleri
            if c["side"] == "long":
                if c["sl"] >= price:
                    continue
                risk = price - c["sl"]
                if risk < MIN_RISK_ATR * x.atr:
                    c["sl"] = price - MIN_RISK_ATR * x.atr
                    risk = MIN_RISK_ATR * x.atr
            else:
                if c["sl"] <= price:
                    continue
                risk = c["sl"] - price
                if risk < MIN_RISK_ATR * x.atr:
                    c["sl"] = price + MIN_RISK_ATR * x.atr
                    risk = MIN_RISK_ATR * x.atr
            if risk / price > MAX_RISK_PCT:
                continue
            c["risk"] = risk
            cands[code] = c

        # --- ICT stratejisi ---
        ict_sig = None
        if self.ict is not None:
            try:
                ict_sig = self.ict.analyze(df, symbol, timeframe)
            except Exception:
                ict_sig = None
        ict_side = None
        if ict_sig is not None:
            nm = getattr(ict_sig.type, "name", str(ict_sig.type)).upper()
            ict_side = "short" if ("SELL" in nm or "SHORT" in nm) else "long"

        # --- Çelişki kontrolü ---
        sides = {c["side"] for c in cands.values()}
        if ict_side:
            sides.add(ict_side)
        if len(sides) != 1:
            return None  # ya sinyal yok ya da zıt yönler var

        side = sides.pop()

        # Sadece ICT varsa, onu olduğu gibi ilet
        if not cands:
            return ict_sig

        # --- Birleştir ---
        group = {k: v for k, v in cands.items() if v["side"] == side}
        base_code = max(group, key=lambda k: group[k]["strength"])
        base = group[base_code]
        codes = sorted(group.keys())
        if ict_side == side:
            codes.append("ICT")
        extra = len(codes) - 1
        strength = min(base["strength"] + 0.1 * extra, 1.0)
        if strength < MIN_STRENGTH:
            return ict_sig if ict_side == side else None

        risk = base["risk"]
        if side == "long":
            sl = price - risk
            tp = price + RR * risk
            sig_type, emoji = SignalType.BUY, "🟢"
        else:
            sl = price + risk
            tp = price - RR * risk
            sig_type, emoji = SignalType.SELL, "🔴"

        notes = [group[k]["note"] for k in sorted(group.keys())]
        names = " + ".join(SHORT_NAMES[k] for k in codes)
        for k in group:
            _last[(symbol, k)] = ts
        _last_sym[symbol] = ts

        label = "+".join(codes)
        return Signal(
            type=sig_type, symbol=symbol, timeframe=timeframe,
            price=price, strategy_name=f"Strateji {label} ({names})",
            strength=strength,
            stop_loss=sl, take_profit=tp,
            reason=f"{emoji} Strateji {label} | {' + '.join(notes)} | Güç {round(strength * 10)}/10",
        )
