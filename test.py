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
        self.stop_loss_price = None
        self.current_stop_step = 0

class LimitOrder(Order):
    def __init__(self, ticker, order_type, price, volume, timestamp):
        super().__init__(ticker, order_type, price, volume, timestamp)
        self.stop_loss_price = None
        self.current_stop_step = 0

class CryptoBacktester:
    def __init__(self, db_path, start_date, end_date, initial_balance, asset_starting_balances):
        self.conn = sqlite3.connect(db_path)
        self.start_date = datetime.strptime(start_date, '%Y-%m-%d')
        self.end_date = datetime.strptime(end_date, '%Y-%m-%d')
        self.balance = initial_balance
        self.initial_balance = initial_balance
        self.positions = asset_starting_balances
        self.initial_positions = asset_starting_balances.copy()
        self.open_orders = []
        self.filled_orders = []
        self.skipped_buy_orders = 0
        self.skipped_sell_orders = 0

    def fetch_all_historical_data(self, tickers):
        all_data = {}
        start_date_str = self.start_date.strftime('%Y-%m-%d %H:%M:%S')
        end_date_str = self.end_date.strftime('%Y-%m-%d %H:%M:%S')
        
        for ticker in tickers:
            query = f"""
            SELECT timestamp, close, ground_truth_trend
            FROM crypto_data
            WHERE ticker = '{ticker}'
            AND timestamp BETWEEN '{start_date_str}' AND '{end_date_str}'
            ORDER BY timestamp ASC
            """
            df = pd.read_sql_query(query, self.conn)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
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
                print(f"Buy order executed for {ticker}: {volume} @ ${price:.2f}")
                return True
            else:
                self.skipped_buy_orders += 1
                print(f"Skipped buy order for {ticker} due to insufficient balance")
                return False
        elif order_type == 'sell':
            available_volume = self.get_available_volume(ticker)
            required_volume = MIN_TRADE_VOLUME[TICKER_TO_PAIR[ticker]]
            print(f"Debug - Attempting to sell {ticker}: Available volume: {available_volume}, Required volume: {required_volume}")
            if available_volume >= required_volume:
                self.balance += price * required_volume
                self.positions[ticker] -= required_volume
                order = Order(ticker, order_type, price, required_volume, timestamp)
                order.filled = True
                order.filled_price = price
                order.filled_timestamp = timestamp
                self.filled_orders.append(order)
                print(f"Sell order executed for {ticker}: {required_volume} @ ${price:.2f}")
                return True
            else:
                self.skipped_sell_orders += 1
                print(f"Skipped sell order for {ticker} due to insufficient volume")
                return False

    def place_limit_sell_order(self, ticker, buy_price, volume, timestamp):
        limit_price = buy_price * (1 + TAKE_PROFIT_PERCENTAGE)
        order = LimitOrder(ticker, 'limit_sell', limit_price, volume, timestamp)
        self.open_orders.append(order)
        print(f"Placed limit sell order for {ticker}: {volume} @ ${limit_price:.2f}")

    def update_trailing_stop(self, order, current_price):
        if not hasattr(order, 'stop_loss_price'):
            order.stop_loss_price = None
            order.current_stop_step = 0

        if order.stop_loss_price is None and current_price >= order.price * (1 + TRAILING_STOP_STEPS[0]):
            order.stop_loss_price = order.price * 1.05
            order.current_stop_step = 1
            print(f"Set initial trailing stop for {order.ticker} at ${order.stop_loss_price:.2f}")
        elif order.stop_loss_price is not None:
            for i, step in enumerate(TRAILING_STOP_STEPS[order.current_stop_step:], start=order.current_stop_step):
                if current_price >= order.price * (1 + step):
                    order.stop_loss_price = order.price * (1 + TRAILING_STOP_STEPS[i-1])
                    order.current_stop_step = i
                    print(f"Updated trailing stop for {order.ticker} to ${order.stop_loss_price:.2f}")
                else:
                    break

    def get_available_volume(self, ticker):
        total_volume = self.positions.get(ticker, 0)
        reserved_volume = sum(order.volume for order in self.open_orders if order.ticker == ticker and order.order_type == 'limit_sell')
        available_volume = total_volume - reserved_volume
        print(f"Debug - {ticker}: Total volume: {total_volume}, Reserved volume: {reserved_volume}, Available volume: {available_volume}")
        return available_volume

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
        print(f"Filled limit order for {order.ticker}: {order.volume} @ ${fill_price:.2f}")

    def process_all_assets_for_day(self, day_data):
        for ticker, row in day_data.items():
            self.process_open_orders(ticker, row['close'], row.name)
            
            current_price = row['close']
            timestamp = row.name
            current_trend = row['ground_truth_trend']
            
            print(f"\nProcessing {ticker} on {timestamp}")
            print(f"Current price: ${current_price:.2f}, Current trend: {current_trend}")

            if current_trend == 'Bullish':
                print(f"Bullish trend detected for {ticker}. Attempting buy order.")
                self.place_market_order(ticker, 'buy', current_price, timestamp)
            elif current_trend == 'Bearish':
                print(f"Bearish trend detected for {ticker}. Attempting sell order.")
                self.place_market_order(ticker, 'sell', current_price, timestamp)

            last_buy_order = next((order for order in reversed(self.filled_orders) 
                                   if order.ticker == ticker and order.order_type == 'buy'), None)
            
            if last_buy_order:
                buy_price = last_buy_order.price
                price_increase = (current_price - buy_price) / buy_price

                print(f"Last buy price: ${buy_price:.2f}, Current price: ${current_price:.2f}, Price increase: {price_increase:.2%}")

                if price_increase >= TRAILING_STOP_STEPS[0]:
                    self.update_trailing_stop(last_buy_order, current_price)
                else:
                    print(f"Current price has not increased by {TRAILING_STOP_STEPS[0]:.0%} from the buy price for {ticker}. No trailing stop order placed.")

    def run_backtest(self, tickers):
        all_data = self.fetch_all_historical_data(tickers)
        
        non_empty_data = {ticker: df for ticker, df in all_data.items() if not df.empty}
        
        if not non_empty_data:
            raise ValueError("No data available for the given tickers and date range.")
        
        min_date = max(df.index.min() for df in non_empty_data.values())
        max_date = min(df.index.max() for df in non_empty_data.values())
        
        if pd.isna(min_date) or pd.isna(max_date):
            raise ValueError("Unable to determine valid date range from the data.")
        
        for date in pd.date_range(min_date, max_date):
            day_data = {}
            for ticker, df in non_empty_data.items():
                if date in df.index:
                    day_data[ticker] = df.loc[date]
            
            if day_data:
                print(f"\nProcessing data for {date.date()}")
                self.process_all_assets_for_day(day_data)

    def calculate_performance(self):
        total_value = self.balance
        for ticker, volume in self.positions.items():
            last_price = self.fetch_all_historical_data([ticker])[ticker].iloc[-1]['close']
            total_value += volume * last_price

        initial_total_value = self.initial_balance
        for ticker, volume in self.initial_positions.items():
            first_price = self.fetch_all_historical_data([ticker])[ticker].iloc[0]['close']
            initial_total_value += volume * first_price

        return {
            'final_balance': self.balance,
            'final_positions': self.positions,
            'total_value': total_value,
            'total_trades': len(self.filled_orders),
            'profit_loss': total_value - initial_total_value,
            'initial_total_value': initial_total_value
        }

    def generate_kpi_summary(self):
        performance = self.calculate_performance()
        
        summary = "\n" + "="*50 + "\n"
        summary += "BACKTESTING KPI SUMMARY\n"
        summary += "="*50 + "\n\n"

        summary += "Overall Performance:\n"
        summary += f"  Initial Total Value: ${performance['initial_total_value']:.2f}\n"
        summary += f"  Final Total Value: ${performance['total_value']:.2f}\n"
        summary += f"  Total Profit/Loss: ${performance['profit_loss']:.2f} ({performance['profit_loss']/performance['initial_total_value']*100:.2f}%)\n"
        summary += f"  Final Cash Balance: ${self.balance:.2f}\n\n"

        summary += "Final Asset Holdings:\n"
        for ticker, volume in self.positions.items():
            final_price = self.fetch_all_historical_data([ticker])[ticker].iloc[-1]['close']
            value = volume * final_price
            summary += f"  {ticker}:\n"
            summary += f"    Amount Held: {volume:.6f}\n"
            summary += f"    Value: ${value:.2f}\n"
            summary += f"    Current Price: ${final_price:.2f}\n"
            summary += "\n"

        buy_orders = [order for order in self.filled_orders if order.order_type == 'buy']
        sell_orders = [order for order in self.filled_orders if order.order_type == 'sell']
        limit_sell_orders = [order for order in self.filled_orders if order.order_type == 'limit_sell']

        # Calculate average profit per trade
        total_profit = 0
        total_trades = 0
        for buy_order in buy_orders:
            matching_sells = [order for order in sell_orders + limit_sell_orders 
                            if order.ticker == buy_order.ticker and order.timestamp > buy_order.timestamp]
            for sell_order in matching_sells:
                profit = (sell_order.filled_price - buy_order.filled_price) * min(buy_order.volume, sell_order.volume)
                total_profit += profit
                total_trades += 1

        avg_profit_per_trade = total_profit / total_trades if total_trades > 0 else 0

        summary += "Trading Activity:\n"
        summary += f"  Total Trades: {len(self.filled_orders)}\n"
        summary += f"  Buy Orders: {len(buy_orders)}\n"
        summary += f"  Sell Orders: {len(sell_orders)}\n"
        summary += f"  Limit Sell Orders: {len(limit_sell_orders)}\n"
        summary += f"  Skipped Buy Orders: {self.skipped_buy_orders}\n"
        summary += f"  Skipped Sell Orders: {self.skipped_sell_orders}\n"
        summary += f"  Average Profit per Trade: ${avg_profit_per_trade:.2f}\n"

        return summary

if __name__ == "__main__":
    initial_balance = 100
    asset_starting_balances = {
        'SOL-USD': 0.5,
        'XRP-USD': 500,
        'BTC-USD': 0.001,
        'ETH-USD': 0.1
    }
    
    backtester = CryptoBacktester(
        db_path='crypto_data.db',
        start_date='2020-01-01',
        end_date='2023-12-31',
        initial_balance=initial_balance,
        asset_starting_balances=asset_starting_balances
    )
    
    print("Starting backtest...")
    backtester.run_backtest(['SOL-USD', 'XRP-USD', 'BTC-USD', 'ETH-USD'])
    
    print("\nBacktest completed. Generating KPI summary...")
    kpi_summary = backtester.generate_kpi_summary()
    print(kpi_summary)