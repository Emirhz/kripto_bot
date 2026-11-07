"""
stock_strategy.py  ->  strategies/stock_strategy.py
Günlük mumlu 8 hisse stratejisi (sadece AL). Sinyalde hangi stratejiden geldiği yazar.
Backtest sonrası en iyi 5'i bırakmak için ENABLED içinde diğerlerini False yap.
"""
import os
import numpy as np
import pandas as pd
from strategies.base import BaseStrategy, Signal, SignalType

ENABLED = {
    "RSI(2) Dip Alımı": True,
    "Trend Geri Çekilme": True,
    "Donchian Kırılım": True,
    "EMA 20/50 Kesişim": True,
    "Bollinger Dip Dönüşü": True,
    "3 Gün Düşüş Dönüşü": True,
    "Hacimli Kırılım": True,
    "52 Hafta Zirvesi": True,
}
STOP_ATR = float(os.getenv("STOP_ATR", "2.5"))  # stop = kapanış - STOP_ATR x günlük ATR

_sent = {}  # {(hisse, strateji): mum tarihi} -> aynı sinyal tekrar gitmesin


def _rsi(c, n):
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def _atr(df, n=14):
    pc = df.close.shift(1)
    tr = pd.concat([df.high - df.low, (df.high - pc).abs(), (df.low - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def _rsi2(df):
    c = df.close
    return (c > c.rolling(200).mean()) & (_rsi(c, 2) < 10)


def _pullback(df):
    c = df.close
    up = (c > c.rolling(200).mean()) & (c.rolling(50).mean() > c.rolling(200).mean())
    return up & (_rsi(c, 14) < 40)


def _donchian(df):
    return df.close > df.high.rolling(55).max().shift(1)


def _ema_cross(df):
    c = df.close
    a, b = c.ewm(span=20, adjust=False).mean(), c.ewm(span=50, adjust=False).mean()
    return (a > b) & (a.shift(1) <= b.shift(1)) & (c > c.rolling(200).mean())


def _bollinger(df):
    c = df.close
    m, sd = c.rolling(20).mean(), c.rolling(20).std()
    return (c < m - 2 * sd) & (c > c.rolling(200).mean())


def _3down(df):
    c = df.close
    dn = (c < c.shift(1)) & (c.shift(1) < c.shift(2)) & (c.shift(2) < c.shift(3))
    return dn & (c > c.rolling(200).mean())


def _volbreak(df):
    c = df.close
    brk = (c > df.high.rolling(20).max().shift(1)) & (df.volume > 1.5 * df.volume.rolling(20).mean())
    return brk & (c > c.rolling(50).mean())


def _52w(df):
    return df.close > df.high.rolling(252).max().shift(1)


# ad: (giriş fonksiyonu, çıkış kuralı metni)
STRATS = {
    "RSI(2) Dip Alımı": (_rsi2, "5 günlük ortalamanın üstüne kapanınca sat"),
    "Trend Geri Çekilme": (_pullback, "RSI(14) 65'i geçince sat"),
    "Donchian Kırılım": (_donchian, "20 günlük dibin altına kapanınca sat"),
    "EMA 20/50 Kesişim": (_ema_cross, "EMA20 EMA50'nin altına inince sat"),
    "Bollinger Dip Dönüşü": (_bollinger, "20 günlük ortalamanın üstüne kapanınca sat"),
    "3 Gün Düşüş Dönüşü": (_3down, "önceki günün zirvesini geçince sat"),
    "Hacimli Kırılım": (_volbreak, "EMA10 altına kapanınca sat"),
    "52 Hafta Zirvesi": (_52w, "50 günlük ortalamanın altına kapanınca sat"),
}


class StockStrategy(BaseStrategy):
    name = "Hisse Stratejileri (günlük)"

    def analyze(self, df: pd.DataFrame, symbol: str, timeframe: str) -> Signal | None:
        # Bugünkü (henüz kapanmamış olabilecek) mumu at, sadece kapanmış günleri kullan
        today = pd.Timestamp.utcnow().tz_localize(None).normalize()
        d = df[df["timestamp"] < today].reset_index(drop=True)
        if len(d) < 300:
            return None
        bar = d["timestamp"].iloc[-1]
        hits = []
        for name, (fn, exit_txt) in STRATS.items():
            if not ENABLED.get(name, False) or _sent.get((symbol, name)) == bar:
                continue
            try:
                if bool(fn(d).fillna(False).iloc[-1]):
                    hits.append((name, exit_txt))
            except Exception:
                continue
        if not hits:
            return None

        a = _atr(d).iloc[-1]
        price = float(d["close"].iloc[-1])
        if pd.isna(a) or a <= 0:
            return None
        for name, _ in hits:
            _sent[(symbol, name)] = bar
        names = " + ".join(n for n, _ in hits)
        return Signal(
            type=SignalType.BUY, symbol=symbol, timeframe=timeframe, price=price,
            strategy_name=names, strength=min(0.7 + 0.1 * (len(hits) - 1), 1.0),
            stop_loss=price - STOP_ATR * a, take_profit=None,
            reason=f"🟢 {names} | Ertesi gün açılışta al. Çıkış: {hits[0][1]}",
        )
