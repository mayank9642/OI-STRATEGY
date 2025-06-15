import dash
from dash import dcc, html
from dash.dependencies import Input, Output
import pandas as pd
import os
import plotly.graph_objs as go
import plotly.express as px
from datetime import datetime, timedelta
import logging

# Configure logging
logging.basicConfig(
    filename='logs/dashboard.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Initialize the Dash app
app = dash.Dash(__name__)

# Define the app layout
app.layout = html.Div([
    html.H1("OI Strategy Paper Trading Dashboard"),
    
    html.Div([
        html.Div([
            html.H3("Strategy Settings"),
            html.Div(id='strategy-settings'),
        ], className='dashboard-card'),
        
        html.Div([
            html.H3("Today's Statistics"),
            html.Div(id='todays-stats'),
        ], className='dashboard-card'),
    ], style={'display': 'flex', 'justify-content': 'space-between'}),
    
    html.Div([
        html.H3("Trade History"),
        dcc.Graph(id='pnl-chart'),
    ], className='dashboard-card'),
    
    html.Div([
        html.H3("Trade Details"),
        html.Div(id='trade-table'),
    ], className='dashboard-card'),
    
    dcc.Interval(
        id='interval-component',
        interval=30*1000,  # Update every 30 seconds
        n_intervals=0
    )
])

@app.callback(
    [Output('strategy-settings', 'children'),
     Output('todays-stats', 'children'),
     Output('pnl-chart', 'figure'),
     Output('trade-table', 'children')],
    [Input('interval-component', 'n_intervals')]
)
def update_dashboard(n):
    # Load strategy settings
    strategy_settings = load_strategy_settings()
    
    # Load trade data
    trade_data = load_trade_data()
    
    # Get today's statistics
    today_stats = calculate_today_stats(trade_data)
    
    # Create PnL chart
    pnl_chart = create_pnl_chart(trade_data)
    
    # Create trade table
    trade_table = create_trade_table(trade_data)
    
    return strategy_settings, today_stats, pnl_chart, trade_table

def load_strategy_settings():
    try:
        # Check if config.yaml exists and parse it
        config_path = 'config/config.yaml'
        
        if not os.path.exists(config_path):
            return html.Div([html.P("Configuration file not found.")])
            
        # For a simple display, we'll just show the last modified time
        mod_time = datetime.fromtimestamp(os.path.getmtime(config_path))
          return html.Div([
            html.P(f"Config Last Updated: {mod_time.strftime('%Y-%m-%d %H:%M:%S')}"),
            html.P("Mode: Paper Trading (Simulated)", style={'fontWeight': 'bold'}),
            html.P("Position Size: 1 lot (fixed)"),
            html.P("Breakout Threshold: 10%"),
            html.P("Stop Loss: 20%"),
            html.P("Take Profit: 20%"),
            html.P("Time-Based Exit: 30 minutes"),
        ])
    except Exception as e:
        logging.error(f"Error loading strategy settings: {str(e)}")
        return html.Div([html.P("Error loading strategy settings.")])

def load_trade_data():
    try:
        # Check if trade history CSV exists
        trade_path = 'logs/trade_history.csv'
        
        if not os.path.exists(trade_path):
            return pd.DataFrame()
            
        # Load trade history from CSV
        df = pd.read_csv(trade_path)
        
        # Convert date/time columns to datetime
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])
        
        if 'entry_time' in df.columns and 'date' in df.columns:
            # Combine date and time
            df['entry_datetime'] = df.apply(
                lambda row: pd.to_datetime(f"{row['date'].strftime('%Y-%m-%d')} {row['entry_time']}"),
                axis=1
            )
            
        if 'exit_time' in df.columns and 'date' in df.columns:
            # Only process rows where exit_time is not NaN
            df['exit_datetime'] = df.apply(
                lambda row: pd.to_datetime(f"{row['date'].strftime('%Y-%m-%d')} {row['exit_time']}")
                if pd.notna(row['exit_time']) else pd.NaT,
                axis=1
            )
        
        return df
    except Exception as e:
        logging.error(f"Error loading trade data: {str(e)}")
        return pd.DataFrame()

def calculate_today_stats(df):
    try:
        if df.empty:
            return html.Div([
                html.P("No trades executed today."),
                html.P("Waiting for trading signals...")
            ])
            
        # Filter for today's date
        today = datetime.now().strftime('%Y-%m-%d')
        today_df = df[df['date'] == today] if 'date' in df.columns else pd.DataFrame()
        
        if today_df.empty:
            return html.Div([
                html.P("No trades executed today."),
                html.P("Waiting for trading signals...")
            ])
            
        # Calculate statistics
        total_trades = len(today_df)
        closed_trades = len(today_df[today_df['status'] == 'CLOSED'])
        open_trades = len(today_df[today_df['status'] == 'OPEN'])
        
        win_trades = len(today_df[(today_df['status'] == 'CLOSED') & (today_df['pnl'] > 0)])
        loss_trades = len(today_df[(today_df['status'] == 'CLOSED') & (today_df['pnl'] <= 0)])
        
        win_rate = (win_trades / closed_trades * 100) if closed_trades > 0 else 0
        
        total_pnl = today_df[today_df['status'] == 'CLOSED']['pnl'].sum()
        
        return html.Div([
            html.P(f"Date: {today}"),
            html.P(f"Total Trades: {total_trades}"),
            html.P(f"Completed Trades: {closed_trades}"),
            html.P(f"Open Trades: {open_trades}"),
            html.P(f"Win Rate: {win_rate:.1f}%"),
            html.P(f"Total P&L: {total_pnl:.2f}", style={'color': 'green' if total_pnl > 0 else 'red'}),
        ])
    except Exception as e:
        logging.error(f"Error calculating today's stats: {str(e)}")
        return html.Div([html.P("Error calculating statistics.")])

def create_pnl_chart(df):
    try:
        if df.empty or 'pnl' not in df.columns:
            return {
                'data': [],
                'layout': go.Layout(title='No trade data available')
            }
            
        # Filter for completed trades
        closed_trades = df[df['status'] == 'CLOSED'].copy()
        
        if closed_trades.empty:
            return {
                'data': [],
                'layout': go.Layout(title='No completed trades yet')
            }
            
        # Create a cumulative P&L series
        closed_trades['cumulative_pnl'] = closed_trades['pnl'].cumsum()
        
        # Create a time series chart
        fig = px.line(
            closed_trades, 
            x='entry_datetime', 
            y='cumulative_pnl',
            title='Cumulative P&L Over Time',
            labels={'entry_datetime': 'Date/Time', 'cumulative_pnl': 'Cumulative P&L'}
        )
        
        # Add individual trade markers
        fig.add_trace(
            go.Scatter(
                x=closed_trades['entry_datetime'],
                y=closed_trades['pnl'],
                mode='markers',
                marker=dict(
                    size=10,
                    color=closed_trades['pnl'].apply(lambda x: 'green' if x > 0 else 'red'),
                ),
                name='Individual Trades'
            )
        )
        
        return fig
    except Exception as e:
        logging.error(f"Error creating P&L chart: {str(e)}")
        return {
            'data': [],
            'layout': go.Layout(title='Error creating P&L chart')
        }

def create_trade_table(df):
    try:
        if df.empty:
            return html.Div([html.P("No trade data available.")])
            
        # Sort by date (most recent first)
        df_sorted = df.sort_values(by=['date', 'entry_time'], ascending=[False, False])
        
        # Limit to last 10 trades for display
        recent_trades = df_sorted.head(10)
        
        # Create table rows
        table_rows = []
          # Header row
        header = html.Tr([
            html.Th("Date"),
            html.Th("Symbol"),
            html.Th("Entry Time"),
            html.Th("Entry Price"),
            html.Th("Exit Time"),
            html.Th("Exit Price"),
            html.Th("P&L"),
            html.Th("Status"),
            html.Th("Exit Reason"),
            html.Th("Paper Trade")
        ])
        
        table_rows.append(header)
        
        # Data rows
        for _, row in recent_trades.iterrows():
            # Format P&L and determine color
            pnl = row.get('pnl', None)
            pnl_style = {'color': 'green'} if pnl and pnl > 0 else {'color': 'red'} if pnl and pnl <= 0 else {}
              # Format the row
            paper_trade = row.get('paper_trade', True)  # Default to True for backward compatibility
            
            table_row = html.Tr([
                html.Td(row.get('date', '')),
                html.Td(row.get('symbol', '')),
                html.Td(row.get('entry_time', '')),
                html.Td(f"{row.get('entry_price', 0):.2f}"),
                html.Td(row.get('exit_time', '-')),
                html.Td(f"{row.get('exit_price', 0):.2f}" if row.get('exit_price') else '-'),
                html.Td(f"{row.get('pnl', 0):.2f}", style=pnl_style),
                html.Td(row.get('status', '')),
                html.Td(row.get('exit_reason', '-')),
                html.Td('Yes' if paper_trade else 'No')
            ])
            
            table_rows.append(table_row)
        
        # Create the table
        table = html.Table(table_rows, style={'width': '100%', 'border-collapse': 'collapse'})
        
        return html.Div([table])
    except Exception as e:
        logging.error(f"Error creating trade table: {str(e)}")
        return html.Div([html.P("Error creating trade table.")])

# Add CSS for better styling
app.index_string = '''
<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>OI Strategy Dashboard</title>
        {%favicon%}
        {%css%}
        <style>
            body {
                font-family: Arial, sans-serif;
                margin: 0;
                padding: 20px;
                background-color: #f5f5f5;
            }
            .dashboard-card {
                background-color: white;
                border-radius: 5px;
                box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
                padding: 15px;
                margin-bottom: 20px;
            }
            h1 {
                color: #2c3e50;
            }
            h3 {
                color: #34495e;
                margin-top: 0;
            }
            table {
                width: 100%;
                border-collapse: collapse;
            }
            th, td {
                padding: 8px;
                text-align: left;
                border-bottom: 1px solid #ddd;
            }
            th {
                background-color: #f2f2f2;
            }
        </style>
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>
'''

# Run the app
if __name__ == '__main__':
    try:
        # Create logs directory if it doesn't exist
        os.makedirs('logs', exist_ok=True)
        
        logging.info("Starting OI Strategy Dashboard")
        app.run_server(debug=True, port=8050)
    except Exception as e:
        logging.error(f"Error starting dashboard: {str(e)}")
