import schedule
import time
import logging
import datetime
import os
import sys

# Add the parent directory to the system path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Use direct imports instead of relative imports with 'src.'
from strategy import OpenInterestStrategy
from config import load_config
from token_helper import ensure_valid_token
from auth import generate_access_token

# Ensure logs directory exists
os.makedirs('logs', exist_ok=True)

# Setup logging
logging.basicConfig(
    filename='logs/main.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def job():
    """Run the strategy job at specified intervals"""
    try:
        strategy = strategy_instance
        strategy.run_strategy()
    except Exception as e:
        logging.error(f"Error in scheduled job: {str(e)}")

if __name__ == "__main__":
    try:
        logging.info("Starting Open Interest Option Buying Strategy...")
        
        # Ensure we have a valid access token before starting
        logging.info("Checking authentication status...")
        access_token = ensure_valid_token()
        
        if not access_token:
            logging.warning("No valid access token found. Attempting to generate one...")
            access_token = generate_access_token()
            
            if not access_token:
                logging.error("Failed to generate access token. Please run auth.py separately.")
                raise Exception("Authentication failed")
        
        logging.info("Authentication successful. Creating strategy instance...")
        
        # Create strategy instance
        strategy_instance = OpenInterestStrategy()
        
        # Initialize strategy for the day
        if not strategy_instance.initialize_day():
            logging.error("Failed to initialize strategy. Exiting.")
            raise Exception("Strategy initialization failed")
            
        logging.info("Strategy initialized successfully.")
        
        # Schedule jobs
        # Run every minute during market hours
        # schedule.every().monday.to.friday.at("09:15").do(strategy_instance.initialize_day)  # This syntax is incorrect
        
        # Correct way to schedule for weekdays at 9:15 AM
        for day in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday']:
            schedule.every().__getattribute__(day).at("09:15").do(strategy_instance.initialize_day)
        
        # Run the job every minute during market hours
        # Note: The between method may not be available in this version of the schedule module
        schedule.every(1).minutes.do(job)
        
        logging.info("Strategy scheduled. Running main loop...")
        
        # Main loop
        while True:
            schedule.run_pending()
            time.sleep(1)
            
    except KeyboardInterrupt:
        logging.info("Strategy execution stopped by user.")
    except Exception as e:
        logging.critical(f"Unhandled exception: {str(e)}")