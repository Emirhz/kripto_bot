import ccxt
import pandas as pd
from strategies.order_block_fvg import OrderBlockFVGStrategy
from strategies.base import SignalType

def run_backtest():
    symbol = "SOL/USDT" # Test için en hareketli coini seçtik
    timeframe = "30m"
    
    print(f"--- {symbol} {timeframe} BACKTEST BAŞLIYOR ---")
    exchange = ccxt.binance()
    # Son 1000 mumu (yaklaşık 20 gün) çek
    raw = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=1000)
    df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
    
    strategy = OrderBlockFVGStrategy()
    
    wins = 0
    losses = 0
    trades = 0
    
    # EMA 200 için ilk 200 mumu atla, oradan itibaren test et
    for i in range(200, len(df) - 50):
        current_df = df.iloc[:i+1] # O anki mum ve geçmişi
        
        signal = strategy.analyze(current_df, symbol, timeframe)
        
        if signal:
            entry_price = signal.price
            sl = signal.stop_loss
            tp = signal.take_profit
            
            # İşlem sonucunu görmek için ileriki 50 mumu kontrol et
            future_df = df.iloc[i+1 : i+50]
            
            hit_tp = False
            hit_sl = False
            
            for _, row in future_df.iterrows():
                if signal.type == SignalType.BUY:
                    if row['high'] >= tp:
                        hit_tp = True
                        break
                    if row['low'] <= sl:
                        hit_sl = True
                        break
                elif signal.type == SignalType.SELL:
                    if row['low'] <= tp:
                        hit_tp = True
                        break
                    if row['high'] >= sl:
                        hit_sl = True
                        break
            
            if hit_tp:
                wins += 1
                trades += 1
                print(f"✅ KAZANÇ: {signal.type.value} | Fiyat: {entry_price} | Hedef Vuruldu!")
            elif hit_sl:
                losses += 1
                trades += 1
                print(f"❌ KAYIP: {signal.type.value} | Fiyat: {entry_price} | Stop Oldu!")
                
    print("\n--- SONUÇLAR ---")
    if trades > 0:
        win_rate = (wins / trades) * 100
        print(f"Toplam İşlem: {trades}")
        print(f"Kazanan: {wins} | Kaybeden: {losses}")
        print(f"Win Rate (Başarı Oranı): %{win_rate:.2f}")
    else:
        print("Bu periyotta sinyal oluşmadı.")

if __name__ == "__main__":
    run_backtest()