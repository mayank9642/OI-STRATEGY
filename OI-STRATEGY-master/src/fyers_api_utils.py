from fyers_apiv3 import fyersModel
from fyers_apiv3.FyersWebsocket import data_ws, order_ws
import logging
import datetime
import time
import pandas as pd
from src.config import load_config
from src.token_helper import ensure_valid_token

def get_fyers_client(check_token=True):
    """
    Create and return authenticated Fyers API client
    
    Args:
        check_token (bool): If True, verify and refresh token if needed
        
    Returns:
        FyersModel: Authenticated Fyers client
    """
    try:
        if check_token:
            access_token = ensure_valid_token()
        else:
            config = load_config()
            access_token = config['fyers']['access_token']
        
        client_id = load_config()['fyers']['client_id']
        
        fyers = fyersModel.FyersModel(client_id=client_id, token=access_token, log_path="logs/")
        
        # Test connection with profile API
        profile_response = fyers.get_profile()
        if profile_response.get('s') == 'ok':
            logging.info(f"Successfully authenticated with Fyers API for user: {profile_response.get('data', {}).get('name')}")
            return fyers
        else:
            logging.error(f"Fyers authentication failed: {profile_response}")
            return None
    except Exception as e:
        logging.error(f"Error creating Fyers client: {str(e)}")
        return None

def place_market_order(fyers, symbol, qty, side):
    """
    Place a market order using Fyers API
    
    Args:
        fyers: Authenticated Fyers client
        symbol: Trading symbol (e.g., "NSE:NIFTY2560619500CE")
        qty: Quantity to trade
        side: "BUY" or "SELL"
        
    Returns:
        Order response from Fyers API
    """
    try:
        order_data = {
            "symbol": symbol,
            "qty": qty,
            "type": 2,  # 2 = Market order
            "side": 1 if side == "BUY" else -1,  # 1 = Buy, -1 = Sell
            "productType": "INTRADAY",
            "validity": "DAY",
            "offlineOrder": False,
            "stopPrice": 0,
            "limitPrice": 0
        }
        
        response = fyers.place_order(data=order_data)
        logging.info(f"Order placed: {symbol} {side} {qty} - Response: {response}")
        return response
    except Exception as e:
        logging.error(f"Error placing order: {str(e)}")
        return None

def modify_order(fyers, order_id, price=None, stop_price=None):
    """Modify an existing order (for SL/target modifications)"""
    try:
        modify_data = {
            "id": order_id
        }
        
        if price is not None:
            modify_data["limitPrice"] = price
            
        if stop_price is not None:
            modify_data["stopPrice"] = stop_price
            
        response = fyers.modify_order(data=modify_data)
        logging.info(f"Order modified: {order_id} - Response: {response}")
        return response
    except Exception as e:
        logging.error(f"Error modifying order: {str(e)}")
        return None

def exit_position(fyers, symbol, qty, side):
    """Exit an existing position"""
    try:
        return place_market_order(fyers, symbol, qty, side)
    except Exception as e:
        logging.error(f"Error exiting position: {str(e)}")
        return None

def get_current_positions(fyers):
    """Get current positions"""
    try:
        positions = fyers.positions()
        return positions
    except Exception as e:
        logging.error(f"Error getting positions: {str(e)}")
        return None

def place_limit_order(fyers, symbol, qty, side, limit_price):
    """
    Place a limit order using Fyers API
    
    Args:
        fyers: Authenticated Fyers client
        symbol: Trading symbol (e.g., "NSE:NIFTY2560619500CE")
        qty: Quantity to trade
        side: "BUY" or "SELL"
        limit_price: Limit price for the order
        
    Returns:
        Order response from Fyers API
    """
    try:
        order_data = {
            "symbol": symbol,
            "qty": qty,
            "type": 1,  # 1 = Limit order
            "side": 1 if side == "BUY" else -1,  # 1 = Buy, -1 = Sell
            "productType": "INTRADAY",
            "validity": "DAY",
            "offlineOrder": False,
            "stopPrice": 0,
            "limitPrice": limit_price
        }
        
        response = fyers.place_order(data=order_data)
        logging.info(f"Limit order placed: {symbol} {side} {qty} @ {limit_price} - Response: {response}")
        return response
    except Exception as e:
        logging.error(f"Error placing limit order: {str(e)}")
        return None

def place_sl_order(fyers, symbol, qty, side, trigger_price):
    """
    Place a stop-loss order using Fyers API
    
    Args:
        fyers: Authenticated Fyers client
        symbol: Trading symbol (e.g., "NSE:NIFTY2560619500CE")
        qty: Quantity to trade
        side: "BUY" or "SELL"
        trigger_price: Stop-loss trigger price
        
    Returns:
        Order response from Fyers API
    """
    try:
        order_data = {
            "symbol": symbol,
            "qty": qty,
            "type": 3,  # 3 = Stop order (SL-M)
            "side": 1 if side == "BUY" else -1,
            "productType": "INTRADAY",
            "validity": "DAY",
            "offlineOrder": False, 
            "stopPrice": trigger_price,
            "limitPrice": 0
        }
        
        response = fyers.place_order(data=order_data)
        logging.info(f"SL order placed: {symbol} {side} {qty} @ trigger {trigger_price} - Response: {response}")
        return response
    except Exception as e:
        logging.error(f"Error placing SL order: {str(e)}")
        return None

def place_sl_limit_order(fyers, symbol, qty, side, trigger_price, limit_price):
    """
    Place a stop-loss limit order using Fyers API
    
    Args:
        fyers: Authenticated Fyers client
        symbol: Trading symbol (e.g., "NSE:NIFTY2560619500CE")
        qty: Quantity to trade
        side: "BUY" or "SELL"
        trigger_price: Stop-loss trigger price
        limit_price: Limit price for order execution
        
    Returns:
        Order response from Fyers API
    """
    try:
        order_data = {
            "symbol": symbol,
            "qty": qty,
            "type": 4,  # 4 = Stop limit order (SL-L)
            "side": 1 if side == "BUY" else -1,
            "productType": "INTRADAY",
            "validity": "DAY",
            "offlineOrder": False,
            "stopPrice": trigger_price,
            "limitPrice": limit_price
        }
        
        response = fyers.place_order(data=order_data)
        logging.info(f"SL-L order placed: {symbol} {side} {qty} @ trigger {trigger_price}, limit {limit_price} - Response: {response}")
        return response
    except Exception as e:
        logging.error(f"Error placing SL-L order: {str(e)}")
        return None

def get_order_status(fyers, order_id):
    """Get status of an existing order"""
    try:
        data = {
            "id": order_id
        }
        response = fyers.get_orders(data=data)
        logging.info(f"Order status for {order_id}: {response}")
        return response
    except Exception as e:
        logging.error(f"Error getting order status: {str(e)}")
        return None

def get_historical_data(fyers, symbol, resolution, date_format, range_from, range_to):
    """
    Get historical data for a symbol
    
    Args:
        fyers: Authenticated Fyers client
        symbol: Trading symbol (e.g., "NSE:NIFTY-INDEX")
        resolution: Timeframe resolution (1, 5, 15, 60, 1D, etc.)
        date_format: Date format (1 for epoch)
        range_from: Start date (epoch or datetime format)
        range_to: End date (epoch or datetime format)
        
    Returns:
        DataFrame: Historical data in pandas DataFrame
    """
    try:
        data = {
            "symbol": symbol,
            "resolution": resolution,
            "date_format": date_format,
            "range_from": range_from,
            "range_to": range_to,
            "cont_flag": "1"
        }
        
        response = fyers.get_historical_data(data)
        
        if isinstance(response, dict) and 'candles' in response:
            df = pd.DataFrame(response['candles'], columns=['datetime', 'open', 'high', 'low', 'close', 'volume'])
            if date_format == 1:  # If date is in epoch format
                df['datetime'] = pd.to_datetime(df['datetime'], unit='s')
            return df
        else:
            logging.error(f"Invalid response format: {response}")
            return None
    except Exception as e:
        logging.error(f"Error getting historical data: {str(e)}")
        return None

def get_option_chain(fyers, underlying):
    """
    Get option chain data for an underlying
    
    Args:
        fyers: Authenticated Fyers client
        underlying: Underlying symbol (e.g., "NSE:NIFTY-INDEX")
        
    Returns:
        dict: Option chain data
    """
    try:
        response = fyers.get_option_chain({"symbol": underlying})
        logging.info(f"Option chain fetched for {underlying}")
        return response
    except Exception as e:
        logging.error(f"Error getting option chain: {str(e)}")
        return None

def start_market_data_websocket(symbols, data_type="symbolData"):
    """
    Start a websocket connection for market data
    
    Args:
        symbols: List of symbols to subscribe to
        data_type: Type of data to receive (symbolData, depthData)
        
    Returns:
        WebSocket connection object
    """
    try:
        config = load_config()
        client_id = config['fyers']['client_id']
        access_token = ensure_valid_token()
        
        def on_message(message):
            logging.info(f"WebSocket message: {message}")
            # Process the message here
            
        def on_error(error):
            logging.error(f"WebSocket error: {error}")
            
        def on_close():
            logging.info("WebSocket connection closed")
            
        def on_open():
            logging.info("WebSocket connection opened")
        
        # Initialize WebSocket
        ws_client = data_ws.FyersDataSocket(
            access_token=f"{client_id}:{access_token}",
            log_path="logs/",
            litemode=False,
            write_to_file=False
        )
        
        # Assign callbacks
        ws_client.on_message = on_message
        ws_client.on_error = on_error
        ws_client.on_close = on_close
        ws_client.on_open = on_open
        
        # Subscribe to symbols
        ws_client.subscribe(symbols=symbols, data_type=data_type)
        
        # Connect
        ws_client.connect()
        
        return ws_client
    except Exception as e:
        logging.error(f"Error starting market data WebSocket: {str(e)}")
        return None

def get_nifty_spot_price():
    """
    Fetch the current Nifty spot price using the Fyers quotes API.
    
    Returns:
        float: The current Nifty spot price, or 0 if unavailable.
    """
    try:
        fyers = get_fyers_client()
        if not fyers:
            logging.error("Fyers client not available for spot price fetch.")
            return 0
        data = {"symbols": "NSE:NIFTY50-INDEX"}
        response = fyers.quotes(data=data)
        if response.get('s') == 'ok' and 'd' in response and len(response['d']) > 0:
            spot = response['d'][0].get('v', {}).get('lp', 0)
            logging.info(f"Fetched Nifty spot price from quotes API: {spot}")
            return spot
        else:
            logging.error(f"Failed to fetch Nifty spot price from quotes API: {response}")
            return 0
    except Exception as e:
        logging.error(f"Error fetching Nifty spot price: {str(e)}")
        return 0