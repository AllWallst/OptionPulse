import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import plotly.express as px

# Set Streamlit Page Configuration
st.set_page_config(page_title="Unusual Options Flow Scanner", layout="wide", page_icon="📈")

st.title("🦅 Ultimate Unusual Options Flow Scanner")
st.markdown("""
Identify unusual options activity by scanning for high **Volume to Open Interest (Vol/OI)** ratios. 
*Note: Yahoo Finance options data may be delayed by 15-20 minutes.*
""")

# --- SIDEBAR CONFIGURATION ---
st.sidebar.header("Scan Parameters")

# Preset Market Universes
MARKET_UNIVERSES = {
    "Custom List": [],
    "Top 20 Market Leaders (Tech & Index)": ["SPY", "QQQ", "IWM", "AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "META", "GOOGL", "AMD", "NFLX", "AVGO", "SMCI", "PLTR", "COIN", "MARA", "UBER", "DIS", "BA"],
    "Financials & Banks": ["JPM", "BAC", "GS", "MS", "C", "WFC", "V", "MA", "PYPL", "SQ"],
    "Healthcare & Pharma": ["UNH", "JNJ", "LLY", "MRK", "ABBV", "PFE", "AMGN", "GILD"],
    "High Volatility / Meme": ["GME", "AMC", "RIVN", "LCID", "SOFI", "HOOD", "CVNA", "UPST"]
}

universe_choice = st.sidebar.selectbox("Select Market Universe to Scan", list(MARKET_UNIVERSES.keys()))

if universe_choice == "Custom List":
    tickers_input = st.sidebar.text_input(
        "Enter Tickers (comma separated)", 
        "NVDA, TSLA, AAPL, SPY"
    )
    tickers = [t.strip().upper() for t in tickers_input.split(",") if t.strip()]
else:
    tickers = MARKET_UNIVERSES[universe_choice]
    st.sidebar.info(f"Scanning {len(tickers)} stocks in this universe.")

# Filters
st.sidebar.subheader("Filters")
min_vol = st.sidebar.number_input("Minimum Volume", min_value=10, value=500, step=100)
min_vol_oi_ratio = st.sidebar.number_input("Minimum Vol/OI Ratio", min_value=0.1, value=2.0, step=0.5)
max_dte = st.sidebar.number_input("Max Days to Expiration (DTE)", min_value=1, value=60, step=7)
otm_only = st.sidebar.checkbox("Only Show Out-of-the-Money (OTM)", value=True)
max_expirations = st.sidebar.slider("Max Expirations to Check per Ticker", 1, 10, 4)

# --- HELPER FUNCTIONS ---
@st.cache_data(ttl=300) # Cache for 5 mins to prevent spamming Yahoo Finance
def get_spot_price(ticker):
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="1d")
        if not hist.empty:
            return hist['Close'].iloc[-1]
    except:
        pass
    return None

def fetch_options_data(tickers, max_exp, min_vol, min_ratio, max_dte, otm_only):
    all_data = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    total_tickers = len(tickers)
    
    for i, ticker_sym in enumerate(tickers):
        status_text.text(f"Scanning {ticker_sym}...")
        ticker = yf.Ticker(ticker_sym)
        spot_price = get_spot_price(ticker_sym)
        
        if spot_price is None:
            continue
            
        try:
            expirations = ticker.options[:max_exp]
        except:
            continue
            
        for exp in expirations:
            # Calculate DTE
            exp_date = datetime.strptime(exp, "%Y-%m-%d").date()
            today = datetime.today().date()
            dte = (exp_date - today).days
            
            if dte > max_dte:
                continue
                
            try:
                opt_chain = ticker.option_chain(exp)
                calls = opt_chain.calls
                puts = opt_chain.puts
                
                # Add metadata
                calls['Type'] = 'Call'
                puts['Type'] = 'Put'
                
                chain = pd.concat([calls, puts], ignore_index=True)
                
                if chain.empty:
                    continue
                
                # Basic cleaning
                chain['Ticker'] = ticker_sym
                chain['Spot Price'] = spot_price
                chain['DTE'] = dte
                chain['Expiration'] = exp
                
                # Calculate Vol/OI Ratio (Avoid division by zero by clipping OI to 1)
                chain['Vol/OI'] = chain['volume'] / chain['openInterest'].clip(lower=1)
                
                # Calculate Moneyness (% out of the money)
                # Calls: (Strike - Spot) / Spot | Puts: (Spot - Strike) / Spot
                chain['Moneyness (%)'] = np.where(
                    chain['Type'] == 'Call',
                    (chain['strike'] - chain['Spot Price']) / chain['Spot Price'] * 100,
                    (chain['Spot Price'] - chain['strike']) / chain['Spot Price'] * 100
                )
                
                # OTM check
                chain['Is_OTM'] = chain['Moneyness (%)'] > 0
                
                all_data.append(chain)
            except Exception as e:
                pass # Skip problematic chains
                
        progress_bar.progress((i + 1) / total_tickers)
        
    status_text.text("Scan Complete!")
    progress_bar.empty()
    
    if all_data:
        df = pd.concat(all_data, ignore_index=True)
        return df
    return pd.DataFrame()

# --- MAIN EXECUTION ---
if st.sidebar.button("🚀 Run Flow Scanner"):
    if not tickers:
        st.warning("Please enter at least one ticker.")
    else:
        with st.spinner("Fetching Options Flow from Yahoo Finance..."):
            df = fetch_options_data(tickers, max_expirations, min_vol, min_vol_oi_ratio, max_dte, otm_only)
            
            if df.empty:
                st.error("No data found. Try expanding your filters or checking your tickers.")
            else:
                # Apply Filters
                filtered_df = df[
                    (df['volume'] >= min_vol) & 
                    (df['Vol/OI'] >= min_vol_oi_ratio)
                ]
                
                if otm_only:
                    filtered_df = filtered_df[filtered_df['Is_OTM'] == True]
                
                if filtered_df.empty:
                    st.warning("No options matched your strict filters. Try lowering minimum volume or Vol/OI.")
                else:
                    # Formatting the final Dataframe
                    display_cols = ['Ticker', 'Type', 'Expiration', 'DTE', 'strike', 'Spot Price', 
                                    'Moneyness (%)', 'lastPrice', 'volume', 'openInterest', 'Vol/OI', 'impliedVolatility']
                    
                    final_df = filtered_df[display_cols].sort_values(by='Vol/OI', ascending=False).reset_index(drop=True)
                    
                    # Rounding and formatting for display
                    final_df['Moneyness (%)'] = final_df['Moneyness (%)'].round(2)
                    final_df['Vol/OI'] = final_df['Vol/OI'].round(2)
                    final_df['impliedVolatility'] = (final_df['impliedVolatility'] * 100).round(2).astype(str) + '%'
                    
                    # --- METRICS DASHBOARD ---
                    st.subheader("📊 Flow Overview")
                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric("Total Unusual Contracts", len(final_df))
                    col2.metric("Highest Vol/OI", final_df['Vol/OI'].max())
                    col3.metric("Call Flow Count", len(final_df[final_df['Type'] == 'Call']))
                    col4.metric("Put Flow Count", len(final_df[final_df['Type'] == 'Put']))

                    # --- VISUALIZATION ---
                    st.subheader("🌌 Options Flow Map (Bubble size = Volume)")
                    
                    # Create scatter plot
                    fig = px.scatter(
                        final_df, 
                        x="DTE", 
                        y="strike", 
                        size="volume", 
                        color="Vol/OI",
                        hover_name="Ticker",
                        hover_data=["Type", "Expiration", "Moneyness (%)", "openInterest"],
                        symbol="Type",
                        color_continuous_scale=px.colors.sequential.YlOrRd,
                        title="Unusual Activity: Strike vs. Days to Expiration"
                    )
                    
                    # Improve chart appearance
                    fig.update_layout(
                        xaxis_title="Days to Expiration (DTE)",
                        yaxis_title="Strike Price ($)",
                        template="plotly_dark"
                    )
                    st.plotly_chart(fig, use_container_width=True)

                    # --- DATA TABLE ---
                    st.subheader("🔥 Unusual Options Activity Ledger")
                    
                    # Pandas styling to highlight extreme Vol/OI ratios
                    def style_dataframe(row):
                        styles = [''] * len(row)
                        # Highlight high Vol/OI
                        if row['Vol/OI'] > 10:
                            styles[row.index.get_loc('Vol/OI')] = 'background-color: rgba(255, 50, 50, 0.4); color: white; font-weight: bold'
                        elif row['Vol/OI'] > 5:
                            styles[row.index.get_loc('Vol/OI')] = 'background-color: rgba(255, 165, 0, 0.4); font-weight: bold'
                        
                        # Color code Call/Put
                        if row['Type'] == 'Call':
                            styles[row.index.get_loc('Type')] = 'color: #00FF00; font-weight: bold' # Green
                        else:
                            styles[row.index.get_loc('Type')] = 'color: #FF0000; font-weight: bold' # Red
                            
                        return styles

                    styled_df = final_df.style.apply(style_dataframe, axis=1) \
                                        .format({'Spot Price': '${:.2f}', 'strike': '${:.2f}', 'lastPrice': '${:.2f}'})

                    st.dataframe(styled_df, use_container_width=True, height=500)
                    

                    st.caption("How to read this: 'Vol/OI' measures how many times the daily trading volume exceeded the existing Open Interest. Values over 1.0 are notable. Values over 5.0 are highly unusual.")
