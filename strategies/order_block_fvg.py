import pandas as pd
from strategies.base import BaseStrategy, Signal, SignalType
from strategies.ict_utils import atr_series

class OrderBlockFVGStrategy(BaseStrategy):
    name = "Yapı Kırılımı (BOS) + Retest"

    def __init__(self, sl_atr_mult: float = 1.0, rr: float = 2.0):
        self.sl_atr_mult = sl_atr_mult
        self.rr = rr

    def analyze(self, df: pd.DataFrame, symbol: str, timeframe: str) -> Signal | None:
        if len(df) < 50: return None
        
        cur = df.iloc[-2] # Mum kapanışını bekle (Sahte kırılımları engeller)
        price = float(cur["close"])
        
        # 1. Pivot (Zirve ve Dip) Noktalarını Bulma (Senin çizgi çektiğin noktalar)
        # Son 30 mumun en belirgin 3 tepe ve 3 dip noktasını buluyoruz
        recent_highs = df["high"].iloc[-30:-1].nlargest(3).values
        recent_lows = df["low"].iloc[-30:-1].nsmallest(3).values
        
        # Ortalama bir direnç ve destek çizgisi (Trendline) oluştur
        resistance_line = sum(recent_highs) / len(recent_highs)
        support_line = sum(recent_lows) / len(recent_lows)
        
        # ATR
        atr = atr_series(df)
        cur_atr = float(atr.iloc[-2])
        if pd.isna(cur_atr) or cur_atr <= 0: return None

        # --- ALIŞ KURULUMU (Direnç Çizgisi Kırılımı) ---
        # Fiyat direnç çizgisini yukarı kırdı mı? VE geri test mi ediyor?
        if price > resistance_line:
            # Fiyat çizgiyi kırdıktan sonra çok mu uzaklaştı? (Geri çekilme payı)
            if (price - resistance_line) < (cur_atr * 1.5):
                
                sl = support_line - (cur_atr * self.sl_atr_mult)
                # Eğer stop çok uzaksa, daha makul bir stop (Kırılan çizginin altı)
                if (price - sl) > (cur_atr * 3):
                    sl = resistance_line - (cur_atr * self.sl_atr_mult)
                    
                risk = price - sl
                tp = price + (risk * self.rr)
                
                return Signal(
                    type=SignalType.BUY, symbol=symbol, timeframe=timeframe,
                    price=price, strategy_name=self.name, strength=0.90,
                    stop_loss=sl, take_profit=tp,
                    reason=f"📈 Direnç Çizgisi Kırıldı + Geri Test ({resistance_line:.4g})"
                )

        # --- SATIŞ KURULUMU (Destek Çizgisi Kırılımı) ---
        # Fiyat destek çizgisini aşağı kırdı mı? VE geri test mi ediyor?
        if price < support_line:
            if (support_line - price) < (cur_atr * 1.5):
                
                sl = resistance_line + (cur_atr * self.sl_atr_mult)
                if (sl - price) > (cur_atr * 3):
                    sl = support_line + (cur_atr * self.sl_atr_mult)
                    
                risk = sl - price
                tp = price - (risk * self.rr)
                
                return Signal(
                    type=SignalType.SELL, symbol=symbol, timeframe=timeframe,
                    price=price, strategy_name=self.name, strength=0.90,
                    stop_loss=sl, take_profit=tp,
                    reason=f"📉 Destek Çizgisi Kırıldı + Geri Test ({support_line:.4g})"
                )

        return None