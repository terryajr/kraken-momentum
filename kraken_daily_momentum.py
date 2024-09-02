import os
import ccxt
import yfinance as yf
import pandas as pd
import sqlite3
import pandas_ta as ta
from datetime import datetime, timedelta



DB_PATH = os.path.abspath('/Users/malciller/dev/kraken/DioKraken/crypto_data.db')
TAKE_PROFIT_PERCENTAGE = 0.30
TRAILING_STOP_STEP = 0.05  # 5% step for trailing stop
TICKERS = ['SOL-USD', 'XRP-USD', 'BTC-USD', 'ETH-USD']
KRAKEN_PAIRS = {'SOL-USD': 'SOL/USD', 'XRP-USD': 'XRP/USD', 'BTC-USD': 'BTC/USD', 'ETH-USD': 'ETH/USD'}
MIN_TRADE_VOLUME = {'SOL/USD': 0.02, 'XRP/USD': 10.0, 'BTC/USD': 0.0001, 'ETH/USD': 0.002}

kraken = ccxt.kraken({
    'apiKey': os.environ.get('KRAKEN_API_KEY'),
    'secret': os.environ.get('KRAKEN_API_SECRET')
})


def create_tables(conn):
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS crypto_data (
        ticker TEXT,
        timestamp TEXT,
        open REAL,
        high REAL,
        low REAL,
        close REAL,
        volume REAL,
        rsi REAL,
        ema REAL,
        ground_truth_trend TEXT,
        PRIMARY KEY (ticker, timestamp)
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS trade_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT,
        pair TEXT,
        trade_type TEXT,
        price REAL,
        volume REAL,
        timestamp TEXT,
        limit_order INTEGER,
        limit_price REAL,
        filled INTEGER DEFAULT 0,
        filled_at REAL,
        filled_timestamp TEXT,
        trailing_stop_price REAL,
        current_step INTEGER DEFAULT 0
    )
    """)
    conn.commit()

def log_trade(conn, ticker, pair, trade_type, price, volume, limit_order=0, limit_price=None, filled=0, filled_at=None, filled_timestamp=None, trailing_stop_price=None, current_step=0):
    cursor = conn.cursor()
    timestamp = datetime.now().isoformat()
    cursor.execute("""
    INSERT INTO trade_history 
    (ticker, pair, trade_type, price, volume, timestamp, limit_order, limit_price, filled, filled_at, filled_timestamp, trailing_stop_price, current_step)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (ticker, pair, trade_type, price, volume, timestamp, limit_order, limit_price, filled, filled_at, filled_timestamp, trailing_stop_price, current_step))
    conn.commit()

def fetch_ticker_price(pair):
    try:
        return kraken.fetch_ticker(pair)['last']
    except Exception as e:
        print(f"Error fetching ticker price for {pair}: {str(e)}")
        return None

def execute_trade(conn, pair, direction, volume):
    try:
        order = kraken.create_market_order(pair, direction, volume)
        filled_price = fetch_ticker_price(pair)
        if filled_price:
            filled = 1 if direction == 'buy' else 0
            log_trade(conn, pair.replace('/', '-'), pair, direction, filled_price, volume, filled=filled)
            print(f"Successfully placed {direction} order for {volume} of {pair} at price {filled_price}")
            
            # Place take-profit limit sell order immediately after a successful buy
            if direction == 'buy':
                execute_limit_sell(conn, pair, filled_price, volume)
            
            return order
        else:
            print("Order executed, but the ticker price could not be retrieved.")
            return None
    except Exception as e:
        print(f"Exception while placing order: {str(e)}")
        return None

def execute_limit_sell(conn, pair, buy_price, volume):
    limit_price = buy_price * (1 + TAKE_PROFIT_PERCENTAGE)
    try:
        order = kraken.create_limit_sell_order(pair, volume, limit_price)
        log_trade(conn, pair.replace('/', '-'), pair, 'sell', buy_price, volume, limit_order=1, limit_price=limit_price)
        print(f"Limit sell order placed for {volume} of {pair} at price {limit_price}")
        return order
    except Exception as e:
        print(f"Exception while placing limit sell order: {str(e)}")
        return None


def update_trailing_stop(conn, order_id, new_stop_price, new_step):
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE trade_history
    SET trailing_stop_price = ?, current_step = ?
    WHERE id = ?
    """, (new_stop_price, new_step, order_id))
    conn.commit()

def check_and_update_trailing_stop(conn, ticker, current_price):
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, price, trailing_stop_price, current_step, limit_price
    FROM trade_history
    WHERE ticker = ? AND limit_order = 1 AND filled = 0
    """, (ticker,))
    open_orders = cursor.fetchall()

    for order_id, buy_price, trailing_stop_price, current_step, limit_price in open_orders:
        price_increase = (current_price - buy_price) / buy_price
        num_steps = int(price_increase / TRAILING_STOP_STEP)

        if num_steps > current_step and num_steps < 6:  # 6 steps to reach 30%
            new_stop_price = buy_price * (1 + (num_steps * TRAILING_STOP_STEP))
            update_trailing_stop(conn, order_id, new_stop_price, num_steps)
            print(f"Updated trailing stop for {ticker} order {order_id} to {new_stop_price} (Step {num_steps})")

def check_order_fill(conn, ticker, current_price):
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, limit_price, trailing_stop_price, current_step
    FROM trade_history
    WHERE ticker = ? AND limit_order = 1 AND filled = 0
    """, (ticker,))
    open_orders = cursor.fetchall()

    for order_id, limit_price, trailing_stop_price, current_step in open_orders:
        if current_price >= limit_price:
            fill_order(conn, order_id, current_price, "limit price")
        elif trailing_stop_price and current_step > 0 and current_price <= trailing_stop_price:
            fill_order(conn, order_id, current_price, f"trailing stop (Step {current_step})")

def fill_order(conn, order_id, fill_price, fill_type):
    cursor = conn.cursor()
    filled_timestamp = datetime.now().isoformat()
    cursor.execute("""
    UPDATE trade_history
    SET filled = 1, filled_at = ?, filled_timestamp = ?
    WHERE id = ?
    """, (fill_price, filled_timestamp, order_id))
    conn.commit()
    print(f"Order {order_id} filled at {fill_price} due to {fill_type}.")

def fetch_and_process_data(ticker, start_date, end_date):
    data = yf.download(ticker, start=start_date, end=end_date, interval='1d')
    if data.empty:
        print(f"No data available for {ticker}")
        return pd.DataFrame()

    df = data.rename(columns={'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close', 'Volume': 'volume'})
    df['timestamp'] = df.index.strftime('%Y-%m-%d %H:%M:%S')
    df['rsi'] = ta.rsi(df['close'], length=14)
    df['ema'] = ta.ema(df['close'], length=20)
    df['50_MA'] = df['close'].rolling(window=50).mean()
    df['200_MA'] = df['close'].rolling(window=200).mean()
    df['ground_truth_trend'] = df.apply(lambda row: 'Bullish' if row['50_MA'] > row['200_MA'] else 'Bearish', axis=1)
    return df.drop(columns=['50_MA', '200_MA'])

def store_data(conn, ticker, df):
    df['ticker'] = ticker
    
    data = df[['ticker', 'timestamp', 'open', 'high', 'low', 'close', 'volume', 'rsi', 'ema', 'ground_truth_trend']]
    
    records = data.to_records(index=False)
    
    upsert_query = """
    INSERT OR REPLACE INTO crypto_data 
    (ticker, timestamp, open, high, low, close, volume, rsi, ema, ground_truth_trend)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    
    cursor = conn.cursor()
    try:
        cursor.executemany(upsert_query, records)
        conn.commit()
        print(f"Successfully stored/updated {len(records)} records for {ticker}")
    except sqlite3.Error as e:
        print(f"An error occurred while storing data for {ticker}: {e}")
        conn.rollback()
    finally:
        cursor.close()

def trade_based_on_trend(conn, ticker, pair):
    cursor = conn.cursor()
    cursor.execute("""
    SELECT close, timestamp FROM crypto_data
    WHERE ticker = ?
    ORDER BY timestamp DESC
    LIMIT 200
    """, (ticker,))
    rows = cursor.fetchall()
    
    if len(rows) < 200:
        print(f"Not enough data to trade for {ticker}")
        return

    # Convert to DataFrame for easier manipulation
    df = pd.DataFrame(rows, columns=['close', 'timestamp'])
    df = df.sort_values('timestamp')
    df['close'] = df['close'].astype(float)
    
    # Calculate 50 and 200 day EMAs
    df['50_EMA'] = df['close'].ewm(span=50, adjust=False).mean()
    df['200_EMA'] = df['close'].ewm(span=200, adjust=False).mean()
    
    current_price = df['close'].iloc[-1]
    current_timestamp = df['timestamp'].iloc[-1]
    current_50_ema = df['50_EMA'].iloc[-1]
    current_200_ema = df['200_EMA'].iloc[-1]
    
    # Determine current trend
    current_trend = 'Bullish' if current_50_ema > current_200_ema else 'Bearish'
    
    volume = MIN_TRADE_VOLUME[pair]

    print(f"Trading {ticker} on pair {pair} with volume {volume} at current price {current_price}")
    print(f"Current timestamp: {current_timestamp}")
    print(f"Current trend: {current_trend}")

    # Always attempt to execute a trade based on the current trend
    if current_trend == 'Bullish':
        print(f"Bullish trend detected for {ticker}. Attempting buy order.")
        buy_order = execute_trade(conn, pair, 'buy', volume)
        if buy_order:
            print(f"Buy order placed for {ticker}. Monitoring price for trailing stop placement.")
    elif current_trend == 'Bearish':
        print(f"Bearish trend detected for {ticker}. Attempting sell order.")
        execute_trade(conn, pair, 'sell', volume)

    # Check for existing buy trades and update trailing stops
    cursor.execute("""
    SELECT id, price FROM trade_history
    WHERE ticker = ? AND trade_type = 'buy'
    ORDER BY timestamp DESC
    LIMIT 1
    """, (ticker,))
    buy_trade = cursor.fetchone()

    if buy_trade:
        buy_price = buy_trade[1]
        price_increase = (current_price - buy_price) / buy_price

        print(f"Buy price: {buy_price}, Current price: {current_price}, Price increase: {price_increase:.2%}")

        if price_increase >= 0.06:
            check_and_update_trailing_stop(conn, ticker, current_price)
        else:
            print(f"Current price has not increased by 6% from the buy price for {ticker}. No trailing stop order placed.")
    
    check_order_fill(conn, ticker, current_price)

    
def main():
    print(f"Using database at: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    print("Database connection established.")
    create_tables(conn)
    print("Tables checked/created.")
    
    start_date = '2020-01-01'
    end_date = datetime.now().strftime('%Y-%m-%d')  # Fetch up to and including the current date
    print(f"Start date: {start_date}, End date: {end_date}")

    for ticker in TICKERS:
        print(f"Processing {ticker}")
        df = fetch_and_process_data(ticker, start_date, end_date)
        print(f"Fetched data for {ticker}, data size: {len(df)}")
        if not df.empty:
            store_data(conn, ticker, df)
            print(f"Stored data for {ticker}")
            trade_based_on_trend(conn, ticker, KRAKEN_PAIRS[ticker])
            print(f"Completed trading logic for {ticker}")
        else:
            print(f"No data to store for {ticker}")

    conn.close()
    print("Database connection closed.")
    print("Done.")


if __name__ == "__main__":
    main()
