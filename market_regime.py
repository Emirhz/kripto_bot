"""
market_regime.py
BTC'nin kısa vadeli yönüne göre sinyalleri filtreler.

  - BTC yukarı yönlüyse  -> SHORT sinyallerini engelle
  - BTC aşağı yönlüyse   -> LONG sinyallerini engelle
  - BTC kararsızsa       -> iki yöne de izin ver
"""

import pandas as pd

# ---------------- AYARLAR ----------------
ENABLED = True          # False yaparsan filtre tamamen kapanır
EMA_PERIOD = 24         # 1H EMA (yaklaşık 1 günlük ortalama)
MOMENTUM_HOURS = 6      # son kaç saatlik değişime bakılsın
MOMENTUM_MIN = 0.003    # %0.3'ten küçük hareketler "kararsız" sayılır
# -----------------------------------------

AGG = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}


def get_btc_regime(btc_df: pd.DataFrame) -> str:
    """'UP', 'DOWN' veya 'NEUTRAL' döner. Veri yetersizse NEUTRAL (engelleme yok)."""
    try:
        df = btc_df.iloc[:-1]  # oluşmakta olan son mumu at
        d1 = df.resample("1h", on="timestamp").agg(AGG).dropna()
        if len(d1) < EMA_PERIOD + MOMENTUM_HOURS + 2:
            return "NEUTRAL"

        close = d1["close"]
        ema = float(close.ewm(span=EMA_PERIOD, adjust=False).mean().iloc[-1])
        last = float(close.iloc[-1])
        past = float(close.iloc[-1 - MOMENTUM_HOURS])
        momentum = (last - past) / past

        if last > ema and momentum > MOMENTUM_MIN:
            return "UP"
        if last < ema and momentum < -MOMENTUM_MIN:
            return "DOWN"
        return "NEUTRAL"
    except Exception:
        return "NEUTRAL"


def signal_allowed(signal, regime: str) -> bool:
    """Sinyal BTC yönüyle çelişmiyorsa True döner."""
    if not ENABLED:
        return True
    name = getattr(signal.type, "name", str(signal.type)).upper()
    is_short = "SELL" in name or "SHORT" in name
    if regime == "UP" and is_short:
        return False
    if regime == "DOWN" and not is_short:
        return False
    return True
