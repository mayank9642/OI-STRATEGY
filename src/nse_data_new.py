import requests
import pandas as pd
import logging
import datetime
from io import StringIO
from src.fyers_api_utils import get_fyers_client

def get_nifty_option_chain():
    """
    Fetch the Nifty 50 option chain using Fyers API with the correct symbol format
    
    Returns:
        DataFrame: Option chain data in pandas DataFrame format with proper symbol names
    """
    try:
        # Use Fyers API client to get option chain data
        logging.info("Fetching Nifty option chain data using Fyers API")
        fyers = get_fyers_client()
        
        # If Fyers API client is not available, fall back to alternative method
        if not fyers:
            return _get_nifty_option_chain_fallback()
            
        # Get current date and option expiry
        today = datetime.datetime.now()
        
        # Find next Thursday for weekly expiry (or current Thursday if today is Thursday)
        days_to_thursday = (3 - today.weekday()) % 7
        if days_to_thursday == 0:
            # If today is Thursday, check if market closed (after 3:30 PM)
            if today.hour > 15 or (today.hour == 15 and today.minute >= 30):
                days_to_thursday = 7  # Use next Thursday
        
        expiry_date = today + datetime.timedelta(days=days_to_thursday)
        
        # Create expiry string for symbol format (e.g., 25JUN for June 2025)
        # Format is YYMMMDD - year (2 digits), month (3 letters), day (2 digits)
        expiry_str = f"{expiry_date.strftime('%y%b').upper()}{expiry_date.day}"
        logging.info(f"Using expiry string for symbols: {expiry_str}")
        
        # Convert to timestamp (epoch seconds) for API calls
        expiry_timestamp = int(datetime.datetime(
            expiry_date.year, expiry_date.month, expiry_date.day, 
            15, 30  # 3:30 PM expiry
        ).timestamp())
        
        logging.info(f"Using expiry date: {expiry_date.strftime('%Y-%m-%d')}")
        
        try:
            # Get option chain from Fyers API
            symbol = "NSE:NIFTY50-INDEX"  # Nifty index symbol
            data = {
                "symbol": symbol,
                "strikeCount": 20,  # Get 10 strikes above and below current price
                "timestamp": expiry_timestamp
            }
            
            logging.info(f"Requesting option chain for {symbol} with expiry {expiry_date.strftime('%Y-%m-%d')}")
            response = fyers.optionchain(data=data)
            
            if response.get('s') == 'ok' and response.get('d') and 'optionsChain' in response['d']:
                # Get the entire options chain in the exact format provided by Fyers
                options_chain_data = response['d']['optionsChain']
                
                # Get the underlying spot price
                spot_price = response['d'].get('underlyingLtp', 0)
                logging.info(f"Current Nifty spot price: {spot_price}")
                
                # Process option chain data into a consistent format
                processed_options = []
                
                for option_data in options_chain_data:
                    strike_price = option_data.get('strikePrice', 0)
                    
                    # Format Fyers symbol format: NSE:NIFTY+YY+MMM+DATE+STRIKE+OPTION_TYPE
                    # Example: NSE:NIFTY25JUN1319500CE
                    call_symbol = f"NSE:NIFTY{expiry_str}{strike_price}CE"
                    put_symbol = f"NSE:NIFTY{expiry_str}{strike_price}PE"
                    
                    # Process call option data if available
                    if 'CE' in option_data:
                        ce_data = option_data['CE']
                        processed_options.append({
                            'symbol': call_symbol,
                            'strikePrice': strike_price,
                            'option_type': 'CE',
                            'lastPrice': ce_data.get('lastPrice', 0),
                            'openInterest': ce_data.get('openInterest', 0),
                            'change': ce_data.get('change', 0),
                            'volume': ce_data.get('volume', 0),
                            'bidPrice': ce_data.get('bidPrice', 0),
                            'askPrice': ce_data.get('askPrice', 0),
                            'underlyingValue': spot_price
                        })
                    
                    # Process put option data if available
                    if 'PE' in option_data:
                        pe_data = option_data['PE']
                        processed_options.append({
                            'symbol': put_symbol,
                            'strikePrice': strike_price,
                            'option_type': 'PE',
                            'lastPrice': pe_data.get('lastPrice', 0),
                            'openInterest': pe_data.get('openInterest', 0),
                            'change': pe_data.get('change', 0),
                            'volume': pe_data.get('volume', 0),
                            'bidPrice': pe_data.get('bidPrice', 0),
                            'askPrice': pe_data.get('askPrice', 0),
                            'underlyingValue': spot_price
                        })
                
                # Convert to DataFrame
                options_df = pd.DataFrame(processed_options)
                
                # Log a few sample symbols to verify format
                if not options_df.empty:
                    sample_ce = options_df[options_df['option_type'] == 'CE']['symbol'].iloc[0]
                    sample_pe = options_df[options_df['option_type'] == 'PE']['symbol'].iloc[0]
                    logging.info(f"Sample symbols - CE: {sample_ce}, PE: {sample_pe}")
                
                logging.info(f"Successfully fetched option chain with {len(options_df)} options")
                return options_df
            else:
                logging.error(f"Failed to get option chain: {response}")
                return _get_nifty_option_chain_fallback()
                
        except Exception as e:
            logging.error(f"Error in Fyers API option chain: {str(e)}")
            return _get_nifty_option_chain_fallback()
            
    except Exception as e:
        logging.error(f"Error in option chain retrieval: {str(e)}")
        return pd.DataFrame()  # Return empty DataFrame on error

def _get_nifty_option_chain_fallback():
    """
    Fallback method to fetch Nifty 50 option chain from NSE website
    This is used when Fyers API is not available or fails
    """
    try:
        logging.info("Using fallback method to fetch option chain from NSE")
        url = "https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br"
        }
        
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            records = data['records']['data']
            
            # Get current date for expiry calculation
            today = datetime.datetime.now()
            
            # Find next Thursday for weekly expiry
            days_to_thursday = (3 - today.weekday()) % 7
            if days_to_thursday == 0:
                # If today is Thursday, check if market closed
                if today.hour > 15 or (today.hour == 15 and today.minute >= 30):
                    days_to_thursday = 7
                    
            expiry_date = today + datetime.timedelta(days=days_to_thursday)
            expiry_str = f"{expiry_date.strftime('%y%b').upper()}{expiry_date.day}"
            
            option_chain = []
            for record in records:
                strike_price = record['strikePrice']
                
                # Process CE (Call) data
                if 'CE' in record:
                    ce = record['CE']
                    call_symbol = f"NSE:NIFTY{expiry_str}{strike_price}CE"
                    ce.update({
                        'symbol': call_symbol,
                        'strikePrice': strike_price,
                        'option_type': 'CE'
                    })
                    option_chain.append(ce)
                
                # Process PE (Put) data
                if 'PE' in record:
                    pe = record['PE']
                    put_symbol = f"NSE:NIFTY{expiry_str}{strike_price}PE"
                    pe.update({
                        'symbol': put_symbol,
                        'strikePrice': strike_price,
                        'option_type': 'PE'
                    })
                    option_chain.append(pe)
            
            result_df = pd.DataFrame(option_chain)
            logging.info(f"Fallback: Successfully fetched {len(result_df)} options")
            return result_df
        else:
            logging.error(f"Failed to fetch option chain: Status code {response.status_code}")
            return pd.DataFrame()
            
    except Exception as e:
        logging.error(f"Error fetching Nifty option chain: {str(e)}")
        # Return empty dataframe in case of error
        return pd.DataFrame()
