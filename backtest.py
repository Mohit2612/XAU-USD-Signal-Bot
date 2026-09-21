import sys
sys.stdout.reconfigure(encoding='utf-8')
import yfinance as yf
import pandas as pd
import numpy as np
from backtesting import Backtest, Strategy
from backtesting.lib import crossover

# Calculate EMA using pandas
def EMA(values, n):
    return pd.Series(values).ewm(span=n, adjust=False).mean()

# Calculate RSI
def RSI(values, n=14):
    delta = pd.Series(values).diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    ema_up = up.ewm(com=n-1, adjust=False).mean()
    ema_down = down.ewm(com=n-1, adjust=False).mean()
    rs = ema_up / ema_down
    return 100 - (100 / (1 + rs))

# Calculate MACD
def MACD(values, fast=12, slow=26, signal=9):
    fast_ema = EMA(values, fast)
    slow_ema = EMA(values, slow)
    macd_line = fast_ema - slow_ema
    signal_line = EMA(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram

class UltimateStrategy(Strategy):
    # Strategy parameters
    ema_fast_len = 8
    ema_mid_len = 21
    ema_slow_len = 50
    rsi_len = 14
    sl_pct = 0.005 # 0.5% Stop Loss
    tp_pct = 0.0125 # 1.25% Take Profit (1:2.5 RR)

    def init(self):
        # Precompute indicators
        self.ema_fast = self.I(EMA, self.data.Close, self.ema_fast_len)
        self.ema_mid = self.I(EMA, self.data.Close, self.ema_mid_len)
        self.ema_slow = self.I(EMA, self.data.Close, self.ema_slow_len)
        self.rsi = self.I(RSI, self.data.Close, self.rsi_len)
        self.macd_line, self.macd_signal, self.macd_hist = self.I(MACD, self.data.Close)

    def next(self):
        # Skip if trade is already open
        if self.position:
            return

        # Current values
        price = self.data.Close[-1]
        
        # Trend Alignment (EMA 8 > 21 > 50 for Bullish)
        ema_bullish = self.ema_fast[-1] > self.ema_mid[-1] > self.ema_slow[-1]
        ema_bearish = self.ema_fast[-1] < self.ema_mid[-1] < self.ema_slow[-1]
        
        # MACD alignment
        macd_bullish = self.macd_line[-1] > self.macd_signal[-1] and self.macd_hist[-1] > 0
        macd_bearish = self.macd_line[-1] < self.macd_signal[-1] and self.macd_hist[-1] < 0
        
        # RSI alignment
        rsi_bullish = self.rsi[-1] > 50
        rsi_bearish = self.rsi[-1] < 50

        # ENTRY LOGIC
        if ema_bullish and macd_bullish and rsi_bullish:
            sl = price * (1 - self.sl_pct)
            tp = price * (1 + self.tp_pct)
            self.buy(sl=sl, tp=tp, size=0.1)
            
        elif ema_bearish and macd_bearish and rsi_bearish:
            sl = price * (1 + self.sl_pct)
            tp = price * (1 - self.tp_pct)
            self.sell(sl=sl, tp=tp, size=0.1)

def run_backtest(ticker, period="30d", interval="15m"):
    print(f"\n[{ticker}] Fetching {period} of {interval} data for backtesting...")
    data = yf.download(ticker, period=period, interval=interval, progress=False)
    
    # Check if data is MultiIndex (yfinance returns MultiIndex if multiple tickers are passed or sometimes randomly)
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.droplevel(1)
        
    if data.empty:
        print("Failed to fetch data.")
        return

    print("Running strategy simulation...")
    # Initialize backtester with 10k USD, 1% risk per trade
    bt = Backtest(data, UltimateStrategy, cash=10000, commission=.0002, exclusive_orders=True)
    
    # Run the backtest
    stats = bt.run()
    
    # Output Key Metrics
    print("\n" + "="*50)
    print(f"📊 BACKTEST RESULTS: {ticker} ({period} / {interval})")
    print("="*50)
    print(f"Total Trades:     {stats['# Trades']}")
    print(f"Win Rate:         {stats['Win Rate [%]']:.2f}%")
    print(f"Return:           {stats['Return [%]']:.2f}%")
    print(f"Max Drawdown:     {stats['Max. Drawdown [%]']:.2f}%")
    print(f"Sharpe Ratio:     {stats['Sharpe Ratio']:.2f}")
    
    if stats['# Trades'] > 0:
        # Calculate Risk/Reward ratio from average win/loss trades
        avg_win = stats.get('Avg. Trade [%]') if stats.get('Avg. Trade [%]') > 0 else 0
        print(f"Expectancy:       {stats.get('Expectancy [%]', 0):.2f}%")

    print("="*50 + "\n")
    
if __name__ == "__main__":
    # Test on Gold and Bitcoin
    run_backtest("GC=F", period="30d", interval="15m")
    run_backtest("BTC-USD", period="30d", interval="15m")
