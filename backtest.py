import os
import time
import ccxt
import pandas as pd
from strategies import order_block_fvg as mod
from strategies.base import SignalType

SYMBOLS = ["FLOW/USDT", "SOL/USDT", "DOGE/USDT", "ETH/USDT"]
DAYS = 30
WINDOW = 1000
MAX_HOLD = 300
START = 600

_orig_atr = mod._atr
_resample = mod._resample_closed


def atr_15m(df, n=14):
    return _orig_atr(df, n)


def atr_1h(df, n=14):
    d1 = _resample(df, "1h", pd.Timedelta(hours=1))
    return _orig_atr(d1, n)


CONFIGS = [
    ("ESKI: 15m ATR x1.0", atr_15m, 1.0),
    ("1H ATR x1.0", atr_1h, 1.0),
    ("1H ATR x1.5", atr_1h, 1.5),
]


def fetch(ex, symbol, days):
    since = ex.milliseconds() - days * 24 * 3600 * 1000
    rows = []
    while True:
        batch = ex.fetch_ohlcv(symbol, "15m", since=since, limit=1000)
        if not batch:
            break
        rows += batch
        since = batch[-1][0] + 1
        if len(batch) < 1000:
            break
        time.sleep(ex.rateLimit / 1000)
    df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df.drop_duplicates("timestamp").reset_index(drop=True)


def simulate(df, symbol, atr_fn, mult):
    mod._atr = atr_fn
    mod._last_signal.clear()
    strat = mod.OrderBlockFVGStrategy(sl_atr_mult=mult)
    out = {"n": 0, "win": 0, "loss": 0, "open": 0, "amb": 0, "R": 0.0}
    n = len(df)
    for i in range(START, n - 2):
        window = df.iloc[max(0, i - WINDOW + 2):i + 2].reset_index(drop=True)
        sig = strat.analyze(window, symbol, "15m")
        if sig is None:
            continue
        out["n"] += 1
        entry, sl, tp = sig.price, sig.stop_loss, sig.take_profit
        is_sell = sig.type == SignalType.SELL
        reward_r = abs(tp - entry) / abs(entry - sl)
        result = None
        for j in range(i + 1, min(n, i + 1 + MAX_HOLD)):
            hi, lo = df["high"].iloc[j], df["low"].iloc[j]
            sl_hit = hi >= sl if is_sell else lo <= sl
            tp_hit = lo <= tp if is_sell else hi >= tp
            if sl_hit and tp_hit:
                out["amb"] += 1
                result = "loss"
                break
            if sl_hit:
                result = "loss"
                break
            if tp_hit:
                result = "win"
                break
        if result == "win":
            out["win"] += 1
            out["R"] += reward_r
        elif result == "loss":
            out["loss"] += 1
            out["R"] -= 1
        else:
            out["open"] += 1
    return out


def main():
    ex = getattr(ccxt, os.getenv("EXCHANGE", "binance"))({"enableRateLimit": True})
    data = {}
    for s in SYMBOLS:
        print(f"{s} verisi cekiliyor...")
        data[s] = fetch(ex, s, DAYS)
        print(f"  {len(data[s])} mum")

    print("\n=== SONUCLAR (toplam, tum coinler) ===")
    print(f"{'Ayar':<22}{'Sinyal':>8}{'Kazanc':>8}{'Kayip':>8}{'Acik':>6}{'Kazanma%':>10}{'Toplam R':>10}")
    for name, fn, mult in CONFIGS:
        tot = {"n": 0, "win": 0, "loss": 0, "open": 0, "amb": 0, "R": 0.0}
        for s in SYMBOLS:
            r = simulate(data[s], s, fn, mult)
            for k in tot:
                tot[k] += r[k]
        closed = tot["win"] + tot["loss"]
        wr = 100 * tot["win"] / closed if closed else 0
        print(f"{name:<22}{tot['n']:>8}{tot['win']:>8}{tot['loss']:>8}{tot['open']:>6}{wr:>9.1f}%{tot['R']:>10.1f}")
    mod._atr = _orig_atr
    print("\nToplam R: +1 = bir stop kadar kazanc. Yuksek olan ayar daha iyi.")


if __name__ == "__main__":
    main()
