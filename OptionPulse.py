import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import plotly.express as px

# --- SETTINGS ---
st.set_page_config(page_title="VolSight Scanner", layout="wide", page_icon="⚡")

st.title("⚡ VolSight: Unusual Options Flow")

# --- HELP MENU (EXPANDER) ---
with st.expander("📖 How to Read This Scanner & Column Definitions", expanded=False):
    st.markdown("""
    ### 🕵️‍♂️ How to find "The Smart Money"
    You are looking for huge bets placed by institutions or insiders. Look for rows where the **🚨 Vol/OI** is extremely high (e.g., over 5.0), and the **💰 Premium** is massive (e.g., $100k+). This means someone put serious cash on the line for the stock to move before the **⏱️ DTE** (Days to Expiration) runs out.
    
    ### 📊 Column Glossary
    *   **🚨 Vol/OI (Most Important!):** Volume divided by Open Interest. A ratio of 5.0 means 5x the normal amount of contracts were traded today. 
    *   **💰 Premium:** (Volume × Last Price × 100). The estimated total dollar amount spent on this contract today. Use this to filter out cheap retail lottery tickets!
    *   **📈 Type:** Call (Betting stock goes UP) vs. Put (Betting stock goes DOWN).
    *   **🎯 Moneyness (%):** How aggressive the bet is. If this is 15%, the stock needs to move 15% for the bet to break even.
    *   **⏱️ DTE:** Days to Expiration. How much time the bet has to play out. Low DTE (1-14 days) implies an immediate expected catalyst.
    *   **Volume:** Total contracts traded *today*.
    *   **openInterest:** Contracts that were sitting open *before* today.
    *   **Spot Price:** The current actual price of the stock.
    *   **strike:** The target price the option is betting on.
    """)

# --- SIDEBAR CONFIGURATION ---
st.sidebar.header("Scan Parameters")

# Preset Market Universes
MARKET_UNIVERSES = {
    "Top 20 Market Leaders": ["SPY", "QQQ", "IWM", "AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "META", "GOOGL", "AMD", "NFLX", "AVGO", "SMCI", "PLTR", "COIN", "MARA", "UBER", "DIS", "BA"],
    "Financials & Banks": ["JPM", "BAC", "GS", "MS", "C", "WFC", "V", "MA", "PYPL", "SQ"],
    "Healthcare & Pharma": ["UNH", "JNJ", "LLY", "MRK", "ABBV", "PFE", "AMGN", "GILD"],
    "High Volatility / Meme": ["GME", "AMC", "RIVN", "LCID", "SOFI", "HOOD", "CVNA", "UPST"],
    "Custom List": []
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
min_premium = st.sidebar.number_input("Minimum Premium Spent ($)", min_value=0, value=10000, step=5000, help="Filters out cheap penny options. 10000 = $10,k minimum spent today.")
max_dte = st.sidebar.number_input("Max Days to Expiration (DTE)", min_value=1, value=60, step=7)
otm_only = st.sidebar.checkbox("Only Show Out-of-the-Money (OTM)", value=True)
max_expirations = st.sidebar.slider("Max Expirations to Check per Ticker", 1, 10, 4)

# --- HELPER FUNCTIONS ---
@st.cache_data(ttl=300) 
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
            exp_date = datetime.strptime(exp, "%Y-%m-%d").date()
            today = datetime.today().date()
            dte = (exp_date - today).days
            
            if dte > max_dte:
                continue
                
            try:
                opt_chain = ticker.option_chain(exp)
                calls = opt_chain.calls
                puts = opt_chain.puts
                
                calls['Type'] = 'Call'
                puts['Type'] = 'Put'
                
                chain = pd.concat([calls, puts], ignore_index=True)
                
                if chain.empty:
                    continue
                
                # Data cleanup & calculations
                chain['Ticker'] = ticker_sym
                chain['Spot Price'] = spot_price
                chain['DTE'] = dte
                chain['Expiration'] = exp
                
                chain['lastPrice'] = chain['lastPrice'].fillna(0)
                chain['volume'] = chain['volume'].fillna(0)
                
                # Calculate Premium (Volume * Price * 100 shares per contract)
                chain['Est. Premium ($)'] = chain['volume'] * chain['lastPrice'] * 100
                
                chain['Vol/OI'] = chain['volume'] / chain['openInterest'].clip(lower=1)
                
                chain['Moneyness (%)'] = np.where(
                    chain['Type'] == 'Call',
                    (chain['strike'] - chain['Spot Price']) / chain['Spot Price'] * 100,
                    (chain['Spot Price'] - chain['strike']) / chain['Spot Price'] * 100
                )
                
                chain['Is_OTM'] = chain['Moneyness (%)'] > 0
                all_data.append(chain)
            except Exception:
                pass
                
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
                # Apply Filters (including the new Premium filter)
                filtered_df = df[
                    (df['volume'] >= min_vol) & 
                    (df['Vol/OI'] >= min_vol_oi_ratio) &
                    (df['Est. Premium ($)'] >= min_premium)
                ]
                
                if otm_only:
                    filtered_df = filtered_df[filtered_df['Is_OTM'] == True]
                
                if filtered_df.empty:
                    st.warning("No options matched your filters. Try lowering the Minimum Premium or Vol/OI.")
                else:
                    # Rename columns to add Emojis
                    filtered_df = filtered_df.rename(columns={
                        'Vol/OI': '🚨 Vol/OI',
                        'Type': '📈 Type',
                        'Moneyness (%)': '🎯 Moneyness (%)',
                        'DTE': '⏱️ DTE',
                        'Est. Premium ($)': '💰 Premium'
                    })
                    
                    display_cols = ['Ticker', '📈 Type', 'Expiration', '⏱️ DTE', 'strike', 'Spot Price', 
                                    '🎯 Moneyness (%)', 'lastPrice', 'volume', 'openInterest', '🚨 Vol/OI', '💰 Premium']
                    
                    final_df = filtered_df[display_cols].sort_values(by='💰 Premium', ascending=False).reset_index(drop=True)
                    
                    # Rounding
                    final_df['🎯 Moneyness (%)'] = final_df['🎯 Moneyness (%)'].round(2)
                    final_df['🚨 Vol/OI'] = final_df['🚨 Vol/OI'].round(2)
                    
                    # Calculate largest premium for metrics
                    max_premium_str = f"${final_df['💰 Premium'].max():,.0f}"
                    
                    # --- METRICS DASHBOARD ---
                    st.subheader("📊 Flow Overview")
                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric("Total Unusual Contracts", len(final_df))
                    col2.metric("Highest Vol/OI", final_df['🚨 Vol/OI'].max())
                    col3.metric("Largest Single Bet", max_premium_str)
                    col4.metric("Bull/Bear Skew", f"{len(final_df[final_df['📈 Type'] == 'Call'])} Calls / {len(final_df[final_df['📈 Type'] == 'Put'])} Puts")

                    # --- VISUALIZATION ---
                    st.subheader("🌌 Options Flow Map (Bubble size = Premium Spent)")
                    fig = px.scatter(
                        final_df, 
                        x="⏱️ DTE", 
                        y="strike", 
                        size="💰 Premium",  # Now sizing by money spent instead of raw volume
                        color="🚨 Vol/OI",
                        hover_name="Ticker",
                        hover_data=["📈 Type", "Expiration", "🎯 Moneyness (%)", "openInterest"],
                        symbol="📈 Type",
                        color_continuous_scale=px.colors.sequential.YlOrRd,
                        title="Unusual Activity: Strike vs. Days to Expiration (Sized by $ Premium)"
                    )
                    fig.update_layout(xaxis_title="Days to Expiration (DTE)", yaxis_title="Strike Price ($)", template="plotly_dark")
                    st.plotly_chart(fig, use_container_width=True)

                    # --- DATA TABLE ---
                    st.subheader("🔥 Unusual Options Activity Ledger")
                    
                    # Custom Pandas Styling
                    def style_dataframe(row):
                        styles = [''] * len(row)
                        
                        vol_oi_idx = row.index.get_loc('🚨 Vol/OI')
                        type_idx = row.index.get_loc('📈 Type')
                        
                        # 1. Color Vol/OI
                        val = row['🚨 Vol/OI']
                        if val > 10:
                            styles[vol_oi_idx] = 'background-color: rgba(255, 50, 50, 0.6); color: white; font-weight: bold'
                        elif val > 5:
                            styles[vol_oi_idx] = 'background-color: rgba(255, 165, 0, 0.5); font-weight: bold'
                        else:
                            styles[vol_oi_idx] = 'background-color: rgba(255, 255, 255, 0.1); font-weight: bold'
                            
                        # 2. Color code Call (Green) / Put (Red)
                        if row['📈 Type'] == 'Call':
                            styles[type_idx] = 'color: #00FF00; font-weight: bold'
                        else:
                            styles[type_idx] = 'color: #FF0000; font-weight: bold'
                            
                        return styles

                    # Apply styling and formatting
                    styled_df = final_df.style.apply(style_dataframe, axis=1) \
                                        .format({
                                            'Spot Price': '${:.2f}', 
                                            'strike': '${:.2f}', 
                                            'lastPrice': '${:.2f}',
                                            '💰 Premium': '${:,.0f}'  # Formats with commas and no decimals!
                                        })

                    st.dataframe(styled_df, use_container_width=True, height=600)
