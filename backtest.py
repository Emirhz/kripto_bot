import ccxt
import pandas as pd
from strategies.order_block_fvg import OrderBlockFVGStrategy
from strategies.base import SignalType

def run_backtest():
    # Tek coin yerine 5 hareketli coini aynı anda test ediyoruz
    symbols = ["SOL/USDT", "AVAX/USDT", "DOGE/USDT", "LINK/USDT", "INJ/USDT"]
    timeframe = "30m"
    
    exchange = ccxt.binance()
    strategy = OrderBlockFVGStrategy()
    
    total_wins = 0
    total_losses = 0
    total_trades = 0
    
    for symbol in symbols:
        print(f"\n--- {symbol} {timeframe} TESTİ BAŞLIYOR ---")
        try:
            # 1000 değil, 3000 mum (yaklaşık 60 gün) çekiyoruz
            raw1 = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=1000)
            raw2 = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=1000, params={'endTime': raw1[0][0]})
            raw3 = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=1000, params={'endTime': raw2[0][0]})
            raw = raw3 + raw2 + raw1
            
            df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
            
            wins = 0
            losses = 0
            trades = 0
            
            for i in range(200, len(df) - 50):
                current_df = df.iloc[:i+1]
                signal = strategy.analyze(current_df, symbol, timeframe)
                
                if signal:
                    entry_price = signal.price
                    sl = signal.stop_loss
                    tp = signal.take_profit
                    
                    future_df = df.iloc[i+1 : i+50]
                    hit_tp = False
                    hit_sl = False
                    
                    for _, row in future_df.iterrows():
                        if signal.type == SignalType.BUY:
                            if row['high'] >= tp: hit_tp = True; break
                            if row['low'] <= sl: hit_sl = True; break
                        elif signal.type == SignalType.SELL:
                            if row['low'] <= tp: hit_tp = True; break
                            if row['high'] >= sl: hit_sl = True; break
                    
                    if hit_tp:
                        wins += 1
                        trades += 1
                        print(f"✅ KAZANÇ: {signal.type.value} | Fiyat: {entry_price}")
                    elif hit_sl:
                        losses += 1
                        trades += 1
                        print(f"❌ KAYIP: {signal.type.value} | Fiyat: {entry_price}")
            
            total_wins += wins
            total_losses += losses
            total_trades += trades
            print(f"-> {symbol} Sonucu: {trades} İşlem, {wins} Kazanç, {losses} Kayıp.")
            
        except Exception as e:
            print(f"{symbol} verisi çekilirken hata oluştu: {e}")

    print("\n\n=== GENEL BACKTEST SONUÇLARI ===")
    if total_trades > 0:
        win_rate = (total_wins / total_trades) * 100
        print(f"Toplam İşlem: {total_trades}")
        print(f"Kazanan: {total_wins} | Kaybeden: {total_losses}")
        print(f"WIN RATE (Başarı Oranı): %{win_rate:.2f}")
    else:
        print("Maalesef bu 60 günlük periyotta da sinyal oluşmadı. (Filtreler çok katı)")

if __name__ == "__main__":
    run_backtest()