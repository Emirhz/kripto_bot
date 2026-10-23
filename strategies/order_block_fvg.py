import pandas as pd
from strategies.base import BaseStrategy, Signal, SignalType

class OrderBlockFVGStrategy(BaseStrategy):
    name = "TEST STRATEJİSİ (Filtresiz)"

    def analyze(self, df: pd.DataFrame, symbol: str, timeframe: str) -> Signal | None:
        if len(df) < 3: return None
        
        # Son iki mumu al
        cur = df.iloc[-1]
        prev = df.iloc[-2]
        
        price = float(cur["close"])
        
        # Eğer anlık mum yeşilse AL
        if cur["close"] > cur["open"]:
            return Signal(
                type=SignalType.BUY, symbol=symbol, timeframe=timeframe,
                price=price, strategy_name=self.name, strength=1.0,
                stop_loss=price * 0.98, take_profit=price * 1.02,
                reason="🧪 TEST: Anlık mum yeşil (Filtreler kapalı)"
            )
            
        # Eğer anlık mum kırmızıysa SAT
        if cur["close"] < cur["open"]:
            return Signal(
                type=SignalType.SELL, symbol=symbol, timeframe=timeframe,
                price=price, strategy_name=self.name, strength=1.0,
                stop_loss=price * 1.02, take_profit=price * 0.98,
                reason="🧪 TEST: Anlık mum kırmızı (Filtreler kapalı)"
            )
                
        return None