# Crypto Trading Bot - Kraken Crpyto Exchange API

## Overview

This Python script implements an automated crypto trading bot that uses a combination of trend analysis and a trailing stop strategy to make trading decisions. The bot fetches historical data for specified cryptocurrencies, analyzes trends, executes trades, and manages open positions with a dynamic trailing stop mechanism.

## Features

- Fetches and processes historical cryptocurrency data from Yahoo Finance
- Stores data in a SQLite database for efficient retrieval and analysis
- Implements a trend-following strategy based on 50-day and 200-day moving averages
- Executes market buy and limit sell orders through the Kraken exchange API
- Utilizes a dynamic trailing stop strategy to maximize profits and minimize losses
- Supports multiple cryptocurrency pairs (currently configured for SOL/USD and XRP/USD)

## Requirements

- Python 3.7+
- ccxt
- yfinance
- pandas
- pandas_ta
- sqlite3

## Installation

1. Clone this repository:
   ```
   git clone https://github.com/terryajr/kraken-momentum
   cd /kraken-momentum
   ```

2. Create a virtual environment:
   ```
   python3 -m venv venv
   ```

3. Activate the virtual environment:
   ```
   source venv/bin/activate
   ```

4. Install the required Python packages:
   ```
   pip install ccxt yfinance pandas pandas_ta
   ```

5. Set up your Kraken API credentials (see "Generating Kraken API Credentials" section below).

## Configuration

### Environment Variables

This project uses environment variables to securely store API credentials. Before running the bot, set the following environment variables:

- `KRAKEN_API_KEY`: Your Kraken API key
- `KRAKEN_API_SECRET`: Your Kraken API secret

You can set these variables in your shell, add them to your `~/.bashrc` file, or include them in the virtual environment activation script. For example:

```bash
export KRAKEN_API_KEY='your_api_key_here'
export KRAKEN_API_SECRET='your_api_secret_here'
```

Never commit these values to version control. If you're using Git, add any files containing these variables to your `.gitignore` file.

### Trading Parameters

The script uses several constants that you can modify according to your trading preferences:

- `DB_PATH`: Path to the SQLite database file
- `TAKE_PROFIT_PERCENTAGE`: The percentage increase at which to place the limit sell order (default: 30%)
- `TRAILING_STOP_STEP`: The percentage step for the trailing stop (default: 5%)
- `TICKERS`: List of cryptocurrency tickers to trade
- `KRAKEN_PAIRS`: Mapping of Yahoo Finance tickers to Kraken trading pairs
- `MIN_TRADE_VOLUME`: Minimum trade volume for each cryptocurrency

You can adjust these parameters in the script file before running the bot.

## Generating Kraken API Credentials

To use this trading bot, you need to generate API credentials from your Kraken account. Follow these steps:

1. Log in to your Kraken account at https://www.kraken.com
2. Navigate to the API section in your account settings
3. Click on "Generate New Key"
4. Set the key description (e.g., "Trading Bot")
5. Select the following permissions:
   - Query Funds
   - Query Open Orders & Trades
   - Query Closed Orders & Trades
   - Modify Orders
   - Create Closing Orders
6. Click "Generate Key"
7. Save the API Key and Private Key securely. You will need these to set up your environment variables.

IMPORTANT: Never share your API credentials or commit them to version control. Keep them secure at all times.

## Usage

To run the trading bot manually:

```
python <script-name>.py
```

To run the bot using a shell script and schedule it:

1. Create a new file named `run_trading_bot.sh` with the following content:

```bash
#!/bin/bash

# Navigate to the directory containing your script
cd /path/to/your/script/directory

# Activate the virtual environment
source venv/bin/activate

# Run the trading bot script
python <script-name>.py

# Deactivate the virtual environment
deactivate
```

2. Make the shell script executable:
```
chmod +x run_trading_bot.sh
```

3. Set up a cron job to run the script daily:
   Open your crontab file:
   ```
   crontab -e
   ```
   Add the following line to run the script every day at 1:00 AM:
   ```
   0 1 * * * /path/to/your/run_trading_bot.sh >> /path/to/logfile.log 2>&1
   ```

   Replace `/path/to/your/run_trading_bot.sh` with the actual path to your shell script, and `/path/to/logfile.log` with the path where you want to store the log file.
## How It Works

### Data Processing
- The script fetches historical data for each configured cryptocurrency using the yfinance library.
- It calculates technical indicators such as RSI and EMA, as well as 50-day and 200-day moving averages.
- The processed data is stored in the SQLite database for future reference and analysis.

### Trading Strategy
- The bot identifies trends by comparing the 50-day and 200-day moving averages.
- When a bullish trend is detected, the bot places a market buy order.
- Simultaneously, it places a limit sell order at 30% above the buy price.

### Trailing Stop Mechanism
- After a buy order is executed, the bot implements a dynamic trailing stop strategy.
- The trailing stop is adjusted in 5% increments as the price increases.
- If the price reaches any of the trailing stop levels (5%, 10%, 15%, 20%, 25%) and then decreases, the sell order is executed at that level.
- This mechanism aims to lock in profits while still allowing for potential higher gains up to the 30% limit.

## Database Schema

The script uses two main tables in the SQLite database:

1. `crypto_data`: Stores historical and processed data for each cryptocurrency.
2. `trade_history`: Keeps a record of all executed trades and open positions.

## Running as a Daily Cron Job

To automate the execution of the trading bot, you can set it up as a daily cron job. This will ensure that the script runs automatically at a specified time each day.

### Unix-based Systems (Linux, macOS)

1. Open the terminal and edit your crontab file:
   ```
   crontab -e
   ```

2. Add a line to run the script daily. For example, to run it every day at 1:00 AM:
   ```
   0 1 * * * /usr/bin/python3 /path/to/your/script.py >> /path/to/logfile.log 2>&1
   ```

   Replace `/path/to/your/script.py` with the actual path to your Python script, and `/path/to/logfile.log` with the path where you want to store the log file.

3. Save and exit the editor. The cron job is now set up.

### Windows

On Windows, you can use the Task Scheduler:

1. Open Task Scheduler (you can search for it in the Start menu).
2. Click "Create Basic Task" in the Actions panel.
3. Give your task a name and description, then click "Next".
4. Choose "Daily" for the trigger, then click "Next".
5. Set the start time and recurrence (daily), then click "Next".
6. For the action, choose "Start a program".
7. In the "Program/script" field, enter the path to your Python executable.
8. In the "Add arguments" field, enter the path to your script.
9. Set the "Start in" field to the directory containing your script.
10. Click "Next", review your settings, and click "Finish".

### Important Considerations for Cron Jobs

- Ensure that the script has all necessary permissions to run and access required files/directories.
- Use absolute paths in your script for any file operations.
- Consider implementing robust logging in your script to track its execution and any potential errors.
- Make sure the machine running the cron job has a stable internet connection and is powered on at the scheduled time.
- Be aware of any API rate limits that might affect daily usage.

## Logging

To enhance the script's logging capabilities for scheduled runs, you may want to implement a logging mechanism. Here's a basic example of how you can add logging to your script:

```python
import logging

logging.basicConfig(filename='crypto_bot.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

def main():
    logging.info("Script execution started")
    try:
        # Your existing main function code here
        # ...
    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
    finally:
        logging.info("Script execution completed")

if __name__ == "__main__":
    main()
```

This will create a log file named `crypto_bot.log` in the same directory as your script, recording the start and end times of each execution, as well as any errors that occur.

## Trading Simulation

To test and validate the trading strategy before deploying it in a live environment, a simulation script is provided. This script closely mirrors the logic of the live trading bot, allowing you to assess its performance using historical data.

### Simulation Features

- Simulates trading across multiple cryptocurrency pairs simultaneously
- Uses historical data stored in the SQLite database
- Implements the same trend-following strategy and trailing stop mechanism as the live bot
- Tracks cash balance, asset balances, and overall profitability
- Logs detailed information about trades and periodic profitability assessments

### Running the Simulation

To run the trading simulation:

1. Ensure your SQLite database is populated with historical data for the assets you want to simulate.
2. Update the simulation parameters in the script if needed:
   - `initial_cash_balance`: Starting cash balance for the simulation
   - `initial_asset_usd_value`: Initial USD value of each asset
   - `trade_amount`: USD value of each trade
   - `maker_fee` and `taker_fee`: Trading fees
   - `take_profit_percentage`: The percentage increase at which to place limit sell orders
3. Run the simulation script:
   ```
   python simulation_script.py
   ```
4. Review the `trading_simulation_log.txt` file for detailed logs of the simulation results.

### Interpreting Simulation Results

The simulation provides several key pieces of information:

- Day-by-day breakdown of trades executed
- Periodic (every 30 days) assessment of profitability for each asset
- Final cash balance and asset balances
- Total profit across all assets
- Overall Return on Investment (ROI)

Use these results to assess the effectiveness of your trading strategy and make adjustments as needed before deploying the bot in a live trading environment.

## Disclaimer

This trading bot and simulation are for educational and experimental purposes only. They do not constitute financial advice, and there are significant risks involved in cryptocurrency trading. Always perform thorough testing and consider consulting with a financial advisor before engaging in live trading activities.


## License

MIT License

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## Contributing

malciller
