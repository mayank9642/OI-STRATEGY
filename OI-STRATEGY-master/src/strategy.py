import pandas as pd
import datetime
import time
import logging
import schedule
import json
import os
import pytz
from src.fyers_api_utils import (
    get_fyers_client, place_market_order, modify_order, exit_position,
    place_limit_order, place_sl_order, place_sl_limit_order, 
    get_order_status, get_historical_data, start_market_data_websocket
)
from src.nse_data_new import get_nifty_option_chain
from src.config import load_config
from src.token_helper import ensure_valid_token
import threading

# Setup logging
logging.basicConfig(
    filename='logs/strategy.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class OpenInterestStrategy:
    def __init__(self):
        self.config = load_config()
        self.fyers = get_fyers_client()
        self.active_trade = None
        self.highest_put_oi_strike = None
        self.highest_call_oi_strike = None
        self.put_premium_at_9_20 = None
        self.call_premium_at_9_20 = None
        self.entry_time = None
        self.order_id = None
        self.stop_loss_order_id = None
        self.target_order_id = None
        self.data_socket = None
        self.trade_history = []
        
        # Load existing trade history if available
        try:
            if os.path.exists('logs/trade_history.csv'):
                self.trade_history = pd.read_csv('logs/trade_history.csv').to_dict('records')
                logging.info(f"Loaded {len(self.trade_history)} historical trades")
        except Exception as e:
            logging.warning(f"Could not load trade history: {str(e)}")
        
    def initialize_day(self):
        """Reset variables for a new trading day"""
        # Check for valid token before starting the trading day
        try:
            access_token = ensure_valid_token()
            if access_token:
                self.fyers = get_fyers_client(check_token=False)  # Token already checked
                logging.info("Authentication verified for today's trading session")
            else:
                logging.error("Failed to obtain valid access token for today's session")
                return False
                
            # Close any existing websocket connection
            if self.data_socket:
                try:
                    self.data_socket.close_connection()
                    logging.info("Closed previous websocket connection")
                except:
                    pass
                    
            self.data_socket = None
            
            # Reset trading variables
            self.active_trade = None
            self.highest_put_oi_strike = None
            self.highest_call_oi_strike = None
            self.put_premium_at_9_20 = None
            self.call_premium_at_9_20 = None
            self.entry_time = None
            self.order_id = None
            self.stop_loss_order_id = None
            self.target_order_id = None
            self.trade_history = []
            
            logging.info("Strategy initialized for a new trading day")
            return True
            
        except Exception as e:
            logging.error(f"Error initializing day: {str(e)}")
            return False

    def identify_high_oi_strikes(self):
        """Identify strikes with highest open interest at 9:20 AM"""
        try:
            # Check if markets are open today
            today = datetime.datetime.now()
            if today.weekday() > 4:  # Saturday or Sunday
                logging.warning("Markets are closed today (weekend). Skipping analysis.")
                return False
            
            # Check if it's a market holiday (simplified check)
            # In a production system, you would have a list of market holidays
            holiday_names = ["Republic Day", "Independence Day", "Gandhi Jayanti", "Christmas"]
            holiday_dates = ["26/01", "15/08", "02/10", "25/12"]
            current_date = today.strftime("%d/%m")
            
            if current_date in holiday_dates:
                holiday_name = holiday_names[holiday_dates.index(current_date)]
                logging.warning(f"Markets are closed today ({holiday_name}). Skipping analysis.")
                return False
                
            # Get Nifty option chain data with proper expiry
            logging.info("Fetching option chain data for analysis...")
            option_chain = get_nifty_option_chain()
            
            if option_chain.empty:
                logging.error("Empty option chain returned - markets may be closed or there's a connection issue")
                return False
                
            # Find the put strike with highest OI
            put_data = option_chain[option_chain['option_type'] == 'PE']
            if put_data.empty:
                logging.error("No put options found in option chain")
                return False
                
            self.highest_put_oi_strike = put_data.loc[put_data['openInterest'].idxmax()]['strikePrice']
            self.put_premium_at_9_20 = put_data[put_data['strikePrice'] == self.highest_put_oi_strike]['lastPrice'].values[0]
            self.highest_put_oi_symbol = put_data[put_data['strikePrice'] == self.highest_put_oi_strike]['symbol'].values[0]
            
            # Find the call strike with highest OI
            call_data = option_chain[option_chain['option_type'] == 'CE']
            if call_data.empty:
                logging.error("No call options found in option chain")
                return False
                
            self.highest_call_oi_strike = call_data.loc[call_data['openInterest'].idxmax()]['strikePrice']
            self.call_premium_at_9_20 = call_data[call_data['strikePrice'] == self.highest_call_oi_strike]['lastPrice'].values[0]
            self.highest_call_oi_symbol = call_data[call_data['strikePrice'] == self.highest_call_oi_strike]['symbol'].values[0]
            
            logging.info(f"Highest PUT OI Strike: {self.highest_put_oi_strike}, Premium: {self.put_premium_at_9_20}")
            logging.info(f"Highest CALL OI Strike: {self.highest_call_oi_strike}, Premium: {self.call_premium_at_9_20}")
            
            # Calculate breakout levels (10% increase)
            self.put_breakout_level = round(self.put_premium_at_9_20 * 1.10, 1)
            self.call_breakout_level = round(self.call_premium_at_9_20 * 1.10, 1)
            
            logging.info(f"PUT Breakout Level: {self.put_breakout_level}")
            logging.info(f"CALL Breakout Level: {self.call_breakout_level}")
            
            return True
        except Exception as e:
            logging.error(f"Error identifying high OI strikes: {str(e)}")
            return False
    
    def monitor_for_breakout(self):
        """Continuously monitor option premiums for breakout (every second) until trade is exited"""
        try:
            def monitor_loop():
                while not self.active_trade:
                    try:
                        option_chain = get_nifty_option_chain()
                        # Check for PUT breakout
                        current_put_premium = option_chain[(option_chain['strikePrice'] == self.highest_put_oi_strike) & 
                                                         (option_chain['option_type'] == 'PE')]['lastPrice'].values[0]
                        # Check for CALL breakout
                        current_call_premium = option_chain[(option_chain['strikePrice'] == self.highest_call_oi_strike) & 
                                                          (option_chain['option_type'] == 'CE')]['lastPrice'].values[0]
                        logging.info(f"Current PUT premium: {current_put_premium}, Breakout level: {self.put_breakout_level}")
                        logging.info(f"Current CALL premium: {current_call_premium}, Breakout level: {self.call_breakout_level}")
                        # Check for PUT breakout
                        if current_put_premium >= self.put_breakout_level:
                            self.entry_time = self.get_ist_datetime()
                            symbol = self.highest_put_oi_symbol
                            logging.info(f"PUT BREAKOUT DETECTED: {symbol} at premium {current_put_premium}")
                            self.execute_trade(symbol, "BUY", current_put_premium)
                            break
                        # Check for CALL breakout
                        if current_call_premium >= self.call_breakout_level:
                            self.entry_time = self.get_ist_datetime()
                            symbol = self.highest_call_oi_symbol
                            logging.info(f"CALL BREAKOUT DETECTED: {symbol} at premium {current_call_premium}")
                            self.execute_trade(symbol, "BUY", current_call_premium)
                            break
                    except Exception as e:
                        logging.error(f"Error in continuous breakout monitoring: {str(e)}")
                    time.sleep(1)  # Check every second
            # Start the monitoring loop in the main thread (blocking until trade is entered)
            monitor_loop()
        except Exception as e:
            logging.error(f"Error monitoring for breakout: {str(e)}")
            return None
    
    def execute_trade(self, symbol, side, entry_price):
        """Execute the option trade with correct lot size for Nifty options"""
        try:
            # Use correct lot size for Nifty options
            qty = 75  # Nifty lot size (update if changed by exchange)
            
            # Calculate notional value and fixed risk metrics
            notional_value = entry_price * qty
            
            # Log trade setup info
            logging.info(f"Paper Trading Setup - Symbol: {symbol}, Price: {entry_price}")
            logging.info(f"Trade Size: {qty} lots, Notional Value: {notional_value}")
            
            # Place order using Fyers API (or simulate for paper trading)
            order_response = place_market_order(self.fyers, symbol, qty, side)
            
            if order_response and order_response.get('s') == 'ok':
                self.order_id = order_response.get('id')
                # Calculate the exit time (30 min after entry)
                exit_time = self.entry_time + datetime.timedelta(minutes=30)
                
                self.active_trade = {
                    'symbol': symbol,
                    'quantity': qty,
                    'entry_price': entry_price,
                    'entry_time': self.entry_time,
                    'stoploss': round(entry_price * 0.8, 1),  # 20% stoploss
                    'target': round(entry_price * 1.2, 1),    # 20% profit (1:2 risk-reward)
                    'exit_time': exit_time  # 30-min time limit
                }
                
                # Log trade details with better formatting
                logging.info(f"=== NEW PAPER TRADE EXECUTED ===")
                logging.info(f"Symbol: {symbol}")
                logging.info(f"Entry Price: {entry_price}")
                logging.info(f"Quantity: {qty} lots")
                logging.info(f"Entry Time: {self.entry_time.strftime('%Y-%m-%d %H:%M:%S')}")
                logging.info(f"Stoploss: {self.active_trade['stoploss']}")
                logging.info(f"Target: {self.active_trade['target']}")
                logging.info(f"Exit Time Limit: {self.active_trade['exit_time'].strftime('%Y-%m-%d %H:%M:%S')}")
                logging.info(f"========================")
                
                # Store trade information for reporting
                self.trade_history.append({
                    'date': self.entry_time.strftime('%Y-%m-%d'),
                    'symbol': symbol,
                    'entry_time': self.entry_time.strftime('%H:%M:%S'),
                    'entry_price': entry_price,
                    'quantity': qty,
                    'status': 'OPEN',
                    'exit_price': None,
                    'pnl': None,
                    'exit_reason': None,
                    'paper_trade': True  # Mark as paper trade
                })
                
                return self.active_trade
            else:
                logging.error(f"Order placement failed: {order_response}")
                return None
        except Exception as e:
            logging.error(f"Error executing trade: {str(e)}")
            return None
    
    def manage_position(self):
        """Manage active position and check for exit conditions with enhanced reporting"""
        if not self.active_trade:
            return
            
        try:
            # Get current market data
            symbol = self.active_trade['symbol']
            entry_price = self.active_trade['entry_price']
            quantity = self.active_trade['quantity']
            current_time = self.get_ist_datetime()
            option_chain = get_nifty_option_chain()
            
            # Parse strike and option type from symbol
            # Extract strike price from symbol (format: NSE:NIFTY25JUN19500CE)
            # The symbol format should be standardized in our get_nifty_option_chain function
            symbol_parts = symbol.split(':')[1]  # Remove 'NSE:'
            strike = None
            option_type = 'CE' if symbol.endswith('CE') else 'PE'
            
            # Parse the strike price from the symbol
            # It's a fixed width field in Fyers API format
            numeric_part = ''.join(filter(str.isdigit, symbol_parts))
            # Skip the date part (YYMMMDD) which should be the first 5-7 characters
            # and get the strike price
            strike = int(numeric_part[5:]) if len(numeric_part) > 5 else None
            
            if not strike:
                logging.error(f"Could not parse strike price from symbol: {symbol}")
                # Try to get the last traded price directly
                current_price = 0
                for idx, row in option_chain.iterrows():
                    if row['symbol'] == symbol:
                        current_price = row['lastPrice']
                        break
            else:
                # Get current price from option chain
                matching_options = option_chain[(option_chain['strikePrice'] == strike) & 
                                             (option_chain['option_type'] == option_type)]
                
                if matching_options.empty:
                    logging.error(f"Could not find option with strike {strike} and type {option_type}")
                    # Try direct symbol match
                    matching_options = option_chain[option_chain['symbol'] == symbol]
                    
                if not matching_options.empty:
                    current_price = matching_options['lastPrice'].values[0]
                else:
                    logging.error("Could not find the current option price")
                    return None
            
            # Calculate current P&L
            entry_value = entry_price * quantity
            current_value = current_price * quantity
            unrealized_pnl = current_value - entry_value
            unrealized_pnl_pct = (unrealized_pnl / entry_value) * 100 if entry_value > 0 else 0
            
            logging.info(f"Managing position: {symbol}, Current price: {current_price}, " +
                        f"P&L: {unrealized_pnl:.2f} ({unrealized_pnl_pct:.2f}%)")
            
            # Check exit conditions:
            exit_type = None
            exit_price = None
            
            # 1. Stoploss hit
            if current_price <= self.active_trade['stoploss']:
                exit_type = "STOPLOSS"
                exit_price = current_price
                logging.info(f"STOPLOSS HIT: Exiting {symbol} at {current_price}")
                
            # 2. Target hit
            elif current_price >= self.active_trade['target']:
                exit_type = "TARGET"
                exit_price = current_price
                logging.info(f"TARGET HIT: Exiting {symbol} at {current_price}")
                
            # 3. Time-based exit
            elif current_time >= self.active_trade['exit_time']:
                exit_type = "TIME"
                exit_price = current_price
                logging.info(f"TIME EXIT: Exiting {symbol} at {current_price}")
            
            # Process exit if conditions are met
            if exit_type:
                # Execute the exit trade
                exit_response = exit_position(self.fyers, self.active_trade['symbol'], quantity, "SELL")
                
                if exit_response and exit_response.get('s') == 'ok':
                    # Calculate P&L
                    entry_value = entry_price * quantity
                    exit_value = exit_price * quantity
                    realized_pnl = exit_value - entry_value
                    realized_pnl_pct = (realized_pnl / entry_value) * 100 if entry_value > 0 else 0
                    
                    # Log detailed exit information
                    logging.info(f"=== PAPER TRADE CLOSED ===")
                    logging.info(f"Symbol: {symbol}")
                    logging.info(f"Exit Type: {exit_type}")
                    logging.info(f"Entry Price: {entry_price}")
                    logging.info(f"Exit Price: {exit_price}")
                    logging.info(f"Quantity: {quantity}")
                    logging.info(f"P&L: {realized_pnl:.2f} ({realized_pnl_pct:.2f}%)")
                    logging.info(f"Trade Duration: {(current_time - self.active_trade['entry_time']).total_seconds() / 60:.1f} minutes")
                    logging.info(f"===================")
                    
                    # Update trade history
                    for trade in self.trade_history:
                        if (trade['symbol'] == symbol and 
                            trade['entry_time'] == self.active_trade['entry_time'].strftime('%H:%M:%S') and 
                            trade['status'] == 'OPEN'):
                            
                            trade['status'] = 'CLOSED'
                            trade['exit_price'] = exit_price
                            trade['exit_time'] = current_time.strftime('%H:%M:%S')
                            trade['pnl'] = realized_pnl
                            trade['pnl_pct'] = realized_pnl_pct
                            trade['exit_reason'] = exit_type
                            break
                    
                    # Save trade history to CSV for reporting
                    try:
                        trade_df = pd.DataFrame(self.trade_history)
                        trade_df.to_csv('logs/trade_history.csv', index=False)
                        logging.info("Trade history saved to logs/trade_history.csv")
                    except Exception as csv_err:
                        logging.error(f"Error saving trade history: {str(csv_err)}")
                    
                    # Reset active trade
                    self.active_trade = None
                    return exit_type
                else:
                    logging.error(f"Exit order failed: {exit_response}")
            
            return None
        except Exception as e:
            logging.error(f"Error managing position: {str(e)}")
            return None
    
    def generate_daily_report(self):
        """Generate a summary report for today's trading activity"""
        # Get today's date in IST
        today = self.get_ist_datetime().strftime("%Y-%m-%d")
        
        # Filter trades for today
        todays_trades = [trade for trade in self.trade_history 
                         if trade.get('date') == today]
        
        if not todays_trades:
            logging.info("No trades executed today.")
            return
            
        # Calculate daily statistics
        num_trades = len(todays_trades)
        profitable_trades = [t for t in todays_trades 
                            if t.get('status') == 'CLOSED' and t.get('pnl', 0) > 0]
        losing_trades = [t for t in todays_trades 
                        if t.get('status') == 'CLOSED' and t.get('pnl', 0) <= 0]
        open_trades = [t for t in todays_trades if t.get('status') == 'OPEN']
        
        total_pnl = sum(t.get('pnl', 0) for t in todays_trades 
                       if t.get('status') == 'CLOSED')
        
        # Generate report
        report = [
            "=" * 50,
            f"DAILY TRADING REPORT - {today}",
            "=" * 50,
            f"Total Trades: {num_trades}",
            f"Completed Trades: {len(profitable_trades) + len(losing_trades)}",
            f"Profitable Trades: {len(profitable_trades)}",
            f"Losing Trades: {len(losing_trades)}",
            f"Open Trades: {len(open_trades)}",
            f"Total P&L: {total_pnl:.2f}",
            "-" * 50,
            "TRADE DETAILS:",
            "-" * 50
        ]
        
        # Add details for each trade
        for i, trade in enumerate(todays_trades, 1):
            status = trade.get('status', 'UNKNOWN')
            pnl = trade.get('pnl', 0)
            pnl_str = f"{pnl:.2f}" if pnl is not None else "N/A"
            
            trade_info = [
                f"Trade #{i}:",
                f"  Symbol: {trade.get('symbol', 'N/A')}",
                f"  Entry Time: {trade.get('entry_time', 'N/A')}",
                f"  Entry Price: {trade.get('entry_price', 'N/A')}",
                f"  Quantity: {trade.get('quantity', 'N/A')}",
                f"  Status: {status}"
            ]
            
            if status == 'CLOSED':
                trade_info.extend([
                    f"  Exit Time: {trade.get('exit_time', 'N/A')}",
                    f"  Exit Price: {trade.get('exit_price', 'N/A')}",
                    f"  P&L: {pnl_str}",
                    f"  Exit Reason: {trade.get('exit_reason', 'N/A')}"
                ])
                
            report.extend(trade_info)
            report.append("-" * 30)
            
        # Log the report
        for line in report:
            logging.info(line)
            
        # Save report to file
        report_dir = "logs/reports"
        os.makedirs(report_dir, exist_ok=True)
        
        with open(f"{report_dir}/report_{today}.txt", "w") as f:
            f.write("\n".join(report))
            
        logging.info(f"Daily report saved to {report_dir}/report_{today}.txt")
        return True

    def get_ist_datetime(self):
        """Get current time in Indian Standard Time (IST)"""
        # Define the time zones
        ist_tz = pytz.timezone('Asia/Kolkata')
        
        # Get current time in UTC and convert to IST
        utc_now = datetime.datetime.now(pytz.UTC)
        ist_now = utc_now.astimezone(ist_tz)
        
        return ist_now
        
    def run_strategy(self, force_analysis=False):
        """Main function to run the strategy"""
        try:
            # Get current time in IST
            ist_now = self.get_ist_datetime()
            current_time = ist_now.time()
            
            # Market hours in IST
            market_open_time = datetime.time(9, 15)
            market_close_time = datetime.time(15, 30)
            
            # Log IST time for debugging
            logging.info(f"Current IST time: {ist_now.strftime('%Y-%m-%d %H:%M:%S')}")
            
            # Check if market is open
            if current_time < market_open_time:
                logging.info("Waiting for market to open (IST time)...")
                return
            
            # For market close: generate daily report and exit
            if current_time >= market_close_time:
                # Check if we're within 5 minutes after market close
                if (current_time.hour == market_close_time.hour and
                    current_time.minute < market_close_time.minute + 5):
                    logging.info("Market closed (IST time). Generating daily report...")
                    self.generate_daily_report()
                    
                logging.info("Market closed (IST time). Strategy will resume next trading day.")
                return
            
            # Check if today is a weekday (0=Monday, 4=Friday, 5=Saturday, 6=Sunday)
            today = ist_now.weekday()
            if today > 4:  # Weekend check
                logging.info(f"Today is {'Saturday' if today == 5 else 'Sunday'} in IST. Market closed.")
                return
                
            # Step 1: Around 9:20, identify high OI strikes
            analysis_time = datetime.time(9, 20)
            # Give it a 1-minute window to ensure the job runs (9:20 to 9:21)
            if force_analysis or (
                current_time.hour == analysis_time.hour and 
                current_time.minute >= analysis_time.minute and 
                current_time.minute < analysis_time.minute + 1):
                
                logging.info("Performing OI analysis (manual trigger or scheduled)...")
                self.identify_high_oi_strikes()
                
            # Step 2: After 9:20, monitor for breakouts
            if self.highest_put_oi_strike and self.highest_call_oi_strike:
                if not self.active_trade:
                    self.monitor_for_breakout()
                    
            # Step 3: Manage existing position
            if self.active_trade:
                self.manage_position()
                
        except Exception as e:
            logging.error(f"Error in run_strategy: {str(e)}")

# Current run_strategy method belongs to the OpenInterestStrategy class
# We need a standalone function for our simulation

def run_strategy(simulated=False):
    """
    Standalone function to run the strategy once for testing or simulation
    
    Args:
        simulated: Boolean indicating if this is a simulation run
    
    Returns:
        Dictionary with strategy results
    """
    try:
        logging.info(f"Running {'simulated' if simulated else 'real'} strategy...")
        
        # Initialize strategy
        strategy = OpenInterestStrategy()
        
        # For simulation, we'll run a condensed version of the strategy
        # Step 1: Identify high OI strikes (9:20 AM analysis)
        success = strategy.identify_high_oi_strikes()
        if not success:
            logging.error("Failed to identify high OI strikes")
            return {"success": False, "message": "Failed to identify high OI strikes"}
        
        # Step 2: Check for breakouts (which would trigger trades)
        result = strategy.monitor_for_breakout()
        
        if result:
            message = f"Trade triggered: {strategy.active_trade['symbol']}"
            return {
                "success": True, 
                "trade_triggered": True,
                "symbol": strategy.active_trade['symbol'],
                "entry_price": strategy.active_trade['entry_price'],
                "stoploss": strategy.active_trade['stoploss'],
                "target": strategy.active_trade['target']
            }
        else:
            return {
                "success": True, 
                "trade_triggered": False,
                "message": "No breakout detected",
                "put_premium": strategy.put_premium_at_9_20,
                "put_breakout_level": strategy.put_breakout_level,
                "call_premium": strategy.call_premium_at_9_20,
                "call_breakout_level": strategy.call_breakout_level
            }
            
    except Exception as e:
        logging.error(f"Error in run_strategy: {str(e)}")
        return {"success": False, "error": str(e)}