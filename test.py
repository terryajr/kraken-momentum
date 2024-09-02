import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime

MIN_TRADE_VOLUME = {'SOL/USD': 0.02, 'XRP/USD': 10.0, 'BTC/USD': 0.0001, 'ETH/USD': 0.002}
TICKER_TO_PAIR = {'SOL-USD': 'SOL/USD', 'XRP-USD': 'XRP/USD', 'BTC-USD': 'BTC/USD', 'ETH-USD': 'ETH/USD'}
TAKE_PROFIT_PERCENTAGE = 0.30
TRAILING_STOP_STEPS = [0.06, 0.10, 0.15, 0.20, 0.25]

class Order:
    def __init__(self, ticker, order_type, price, volume, timestamp):
        self.ticker = ticker
        self.order_type = order_type
        self.price = price
        self.volume = volume
        self.timestamp = timestamp
        self.filled = False
        self.filled_price = None
        self.filled_timestamp = None

class LimitOrder(Order):
    def __init__(self, ticker, order_type, price, volume, timestamp):
        super().__init__(ticker, order_type, price, volume, timestamp)
        self.stop_loss_price = None
        self.current_stop_step = 0

class CryptoBacktester:
    def __init__(self, db_path, start_date, end_date, initial_balance):
        self.conn = sqlite3.connect(db_path)
        self.start_date = start_date
        self.end_date = end_date
        self.balance = initial_balance
        self.initial_balance = initial_balance
        self.positions = {}
        self.open_orders = []
        self.filled_orders = []
        self.skipped_buy_orders = 0
        self.skipped_sell_orders = 0

    def fetch_all_historical_data(self, tickers):
        all_data = {}
        for ticker in tickers:
            query = f"""
            SELECT * FROM crypto_data
            WHERE ticker = '{ticker}'
            AND timestamp BETWEEN {int(datetime.strptime(self.start_date, '%Y-%m-%d').timestamp())}
            AND {int(datetime.strptime(self.end_date, '%Y-%m-%d').timestamp())}
            ORDER BY timestamp ASC
            """
            df = pd.read_sql_query(query, self.conn)
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
            df.set_index('timestamp', inplace=True)
            all_data[ticker] = df
        return all_data

    def place_market_order(self, ticker, order_type, price, timestamp):
        pair = TICKER_TO_PAIR[ticker]
        volume = MIN_TRADE_VOLUME[pair]
        
        if order_type == 'buy':
            cost = price * volume
            if self.balance >= cost:
                self.balance -= cost
                self.positions[ticker] = self.positions.get(ticker, 0) + volume
                order = Order(ticker, order_type, price, volume, timestamp)
                order.filled = True
                order.filled_price = price
                order.filled_timestamp = timestamp
                self.filled_orders.append(order)
                self.place_limit_sell_order(ticker, price, volume, timestamp)
                return True
            else:
                self.skipped_buy_orders += 1
                return False
        elif order_type == 'sell':
            available_volume = self.get_available_volume(ticker)
            if available_volume >= volume:
                self.balance += price * volume
                self.positions[ticker] -= volume
                order = Order(ticker, order_type, price, volume, timestamp)
                order.filled = True
                order.filled_price = price
                order.filled_timestamp = timestamp
                self.filled_orders.append(order)
                return True
            else:
                self.skipped_sell_orders += 1
                return False

    def place_limit_sell_order(self, ticker, buy_price, volume, timestamp):
        limit_price = buy_price * (1 + TAKE_PROFIT_PERCENTAGE)
        order = LimitOrder(ticker, 'limit_sell', limit_price, volume, timestamp)
        self.open_orders.append(order)

    def update_trailing_stop(self, order, current_price):
        if order.stop_loss_price is None and current_price >= order.price * (1 + TRAILING_STOP_STEPS[0]):
            order.stop_loss_price = order.price * 1.05
            order.current_stop_step = 1
        elif order.stop_loss_price is not None:
            for i, step in enumerate(TRAILING_STOP_STEPS[order.current_stop_step:], start=order.current_stop_step):
                if current_price >= order.price * (1 + step):
                    order.stop_loss_price = order.price * (1 + TRAILING_STOP_STEPS[i-1])
                    order.current_stop_step = i
                else:
                    break

    def get_available_volume(self, ticker):
        total_volume = self.positions.get(ticker, 0)
        reserved_volume = sum(order.volume for order in self.open_orders if order.ticker == ticker and order.order_type == 'limit_sell')
        return total_volume - reserved_volume

    def process_open_orders(self, ticker, current_price, timestamp):
        for order in self.open_orders[:]:
            if order.ticker == ticker:
                if isinstance(order, LimitOrder):
                    self.update_trailing_stop(order, current_price)
                    if current_price >= order.price or (order.stop_loss_price and current_price <= order.stop_loss_price):
                        self.fill_limit_order(order, current_price, timestamp)
                        self.open_orders.remove(order)

    def fill_limit_order(self, order, fill_price, timestamp):
        self.balance += fill_price * order.volume
        self.positions[order.ticker] -= order.volume
        order.filled = True
        order.filled_price = fill_price
        order.filled_timestamp = timestamp
        self.filled_orders.append(order)

    def process_all_assets_for_day(self, day_data):
        for ticker, row in day_data.items():
            self.process_open_orders(ticker, row['close'], row.name)
            
            if row['ground_truth_trend'] == 'Bullish':
                self.place_market_order(ticker, 'buy', row['close'], row.name)
            elif row['ground_truth_trend'] == 'Bearish':
                self.place_market_order(ticker, 'sell', row['close'], row.name)

    def run_backtest(self, tickers):
        all_data = self.fetch_all_historical_data(tickers)
        
        # Ensure all dataframes have the same date range
        min_date = max(df.index.min() for df in all_data.values())
        max_date = min(df.index.max() for df in all_data.values())
        
        for date in pd.date_range(min_date, max_date):
            day_data = {}
            for ticker, df in all_data.items():
                if date in df.index:
                    day_data[ticker] = df.loc[date]
            
            self.process_all_assets_for_day(day_data)

    def calculate_performance(self):
        total_value = self.balance
        for ticker, volume in self.positions.items():
            last_price = self.fetch_all_historical_data([ticker])[ticker].iloc[-1]['close']
            total_value += volume * last_price

        return {
            'final_balance': self.balance,
            'final_positions': self.positions,
            'total_value': total_value,
            'total_trades': len(self.filled_orders),
            'profit_loss': total_value - self.initial_balance
        }

    def generate_summary(self):
        performance = self.calculate_performance()
        
        summary = "\n" + "="*50 + "\n"
        summary += "BACKTESTING SUMMARY\n"
        summary += "="*50 + "\n\n"

        summary += "Initial Balance: ${:.2f}\n".format(self.initial_balance)
        summary += "Final Balance: ${:.2f}\n".format(performance['final_balance'])
        summary += "Total Value: ${:.2f}\n".format(performance['total_value'])
        summary += "Profit/Loss: ${:.2f} ({:.2f}%)\n".format(
            performance['profit_loss'],
            (performance['profit_loss'] / self.initial_balance) * 100
        )
        summary += "\nFinal Positions:\n"
        for ticker, volume in performance['final_positions'].items():
            summary += "  {}: {:.6f}\n".format(ticker, volume)

        summary += "\nTrading Activity:\n"
        summary += "  Total Trades: {}\n".format(performance['total_trades'])
        
        buy_orders = [order for order in self.filled_orders if order.order_type == 'buy']
        sell_orders = [order for order in self.filled_orders if order.order_type == 'sell']
        limit_sell_orders = [order for order in self.filled_orders if order.order_type == 'limit_sell']

        summary += "  Buy Orders: {}\n".format(len(buy_orders))
        summary += "  Sell Orders: {}\n".format(len(sell_orders))
        summary += "  Limit Sell Orders: {}\n".format(len(limit_sell_orders))

        if len(buy_orders) > 0:
            avg_buy_price = np.mean([order.filled_price for order in buy_orders])
            summary += "  Average Buy Price: ${:.2f}\n".format(avg_buy_price)

        if len(sell_orders) > 0:
            avg_sell_price = np.mean([order.filled_price for order in sell_orders])
            summary += "  Average Sell Price: ${:.2f}\n".format(avg_sell_price)

        summary += "\nSkipped Orders:\n"
        summary += "  Skipped Buy Orders: {}\n".format(self.skipped_buy_orders)
        summary += "  Skipped Sell Orders: {}\n".format(self.skipped_sell_orders)

        return summary

# Usage example
if __name__ == "__main__":
    initial_balance = 500  # Set this to your desired starting balance
    backtester = CryptoBacktester('path/to/your/database.db', '2020-01-01', '2023-12-31', initial_balance)
    backtester.run_backtest(['SOL-USD', 'XRP-USD', 'BTC-USD', 'ETH-USD'])
    summary = backtester.generate_summary()
    print(summary)