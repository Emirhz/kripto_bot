from dataclasses import dataclass
from enum import Enum
import pandas as pd

class SignalType(Enum):
    BUY = "BUY"
    SELL = "SELL"
    NONE = "NONE"

@dataclass
class Signal:
    type: SignalType
    symbol: str
    timeframe: str
    price: float
    strategy_name: str
    strength: float = 1.0
    stop_loss: float | None = None
    take_profit: float | None = None
    reason: str = ""

class BaseStrategy:
    name: str = "base"
    def analyze(self, df: pd.DataFrame, symbol: str, timeframe: str) -> Signal | None:
        raise NotImplementedError