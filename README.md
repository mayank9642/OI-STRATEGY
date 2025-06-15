# Open Interest Option Buying Strategy

## Overview
This project implements an intraday option buying strategy based on open interest data. The strategy analyzes the Nifty 50 option chain at market open (9:20 AM), identifies strikes with the highest open interest, and enters trades when premium prices breakout by 10% - indicating potential momentum.

## Strategy Details
- **Analysis Time**: 9:20 AM
- **Entry Condition**: 10% increase in premium price from 9:20 AM level
- **Stoploss**: 20% of entry premium
- **Target**: 1:2 risk-reward ratio (2x the risk amount)
- **Maximum Holding Period**: 30 minutes
- **Exit Conditions**: Stoploss hit, Target achieved, or 30-minute time limit

## Setup Instructions

### Prerequisites
- Python 3.8+
- Fyers Trading Account
- Fyers API credentials

### Installation
1. Clone the repository
```bash
git clone https://github.com/mayank9642/open-interest-strategy.git
cd open-interest-strategy