from dataclasses import dataclass
from typing import List, Literal
import pandas as pd

@dataclass
class Zone:
    kind: Literal["OB", "FVG", "IFVG"]
    direction: Literal["bullish", "bearish"]
    top: float
    bottom: float
    start_idx: int
    end_idx: int | None = None

def atr_series(df: pd.DataFrame, period: int = 14) -> pd.Series:
    hl = df["high"] - df["low"]
    hc = (df["high"] - df["close"].shift()).abs()
    lc = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    return tr.rolling(period).mean()

def detect_order_blocks(df: pd.DataFrame, impulse_mult: float = 1.5, lookback: int = 100) -> List[Zone]:
    obs: List[Zone] = []
    atr = atr_series(df)
    start = max(0, len(df) - lookback)
    for i in range(start, len(df) - 3):
        a = atr.iloc[i]
        if pd.isna(a) or a <= 0: continue
        o, c, h, l = df["open"].iloc[i], df["close"].iloc[i], df["high"].iloc[i], df["low"].iloc[i]
        if c < o:
            fut_high = df["high"].iloc[i + 1:i + 4].max()
            if fut_high - c > impulse_mult * a: obs.append(Zone("OB", "bullish", h, l, i))
        if c > o:
            fut_low = df["low"].iloc[i + 1:i + 4].min()
            if c - fut_low > impulse_mult * a: obs.append(Zone("OB", "bearish", h, l, i))
    return obs

def detect_fvgs(df: pd.DataFrame, lookback: int = 100) -> List[Zone]:
    fvgs: List[Zone] = []
    start = max(1, len(df) - lookback)
    for i in range(start, len(df) - 1):
        if df["high"].iloc[i - 1] < df["low"].iloc[i + 1]:
            fvgs.append(Zone("FVG", "bullish", float(df["low"].iloc[i + 1]), float(df["high"].iloc[i - 1]), i))
        if df["low"].iloc[i - 1] > df["high"].iloc[i + 1]:
            fvgs.append(Zone("FVG", "bearish", float(df["low"].iloc[i - 1]), float(df["high"].iloc[i + 1]), i))
    return fvgs

def detect_ifvgs(df: pd.DataFrame, fvgs: List[Zone]) -> List[Zone]:
    ifvgs: List[Zone] = []
    for fvg in fvgs:
        for j in range(fvg.start_idx + 2, len(df)):
            if fvg.direction == "bullish" and df["close"].iloc[j] < fvg.bottom:
                ifvgs.append(Zone("IFVG", "bearish", fvg.top, fvg.bottom, fvg.start_idx, j))
                break
            if fvg.direction == "bearish" and df["close"].iloc[j] > fvg.top:
                ifvgs.append(Zone("IFVG", "bullish", fvg.top, fvg.bottom, fvg.start_idx, j))
                break
    return ifvgs

def zone_intact(df: pd.DataFrame, zone: Zone, current_idx: int) -> bool:
    for j in range(zone.start_idx + 1, current_idx):
        if zone.direction == "bullish" and df["close"].iloc[j] < zone.bottom: return False
        if zone.direction == "bearish" and df["close"].iloc[j] > zone.top: return False
    return True

def first_touch(df: pd.DataFrame, zone: Zone, current_idx: int) -> bool:
    for j in range(zone.start_idx + 1, current_idx):
        if df["low"].iloc[j] <= zone.top and df["high"].iloc[j] >= zone.bottom: return False
    return True

def overlapping_fvg(direction: str, zones: List[Zone], price_top: float, price_bottom: float) -> bool:
    for z in zones:
        if z.direction == direction and z.kind == "FVG":
            if z.bottom <= price_top and z.top >= price_bottom: return True
    return False