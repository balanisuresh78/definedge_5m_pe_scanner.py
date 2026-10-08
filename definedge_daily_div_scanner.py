import os
import smtplib
from email.message import EmailMessage
from datetime import datetime, timedelta
import pytz
import pyotp
import numpy as np
import pandas as pd
from tabulate import tabulate
from integrate import ConnectToIntegrate, IntegrateData
import warnings

warnings.simplefilter(action='ignore', category=FutureWarning)

# ==========================================
# 1. CONFIGURATION
# ==========================================
API_TOKEN = "7eb93aac-c746-44bd-9755-18ae6289fdfc"
API_SECRET = "snToBptj6e2X/c9c7POM8Q=="
TOTP_SECRET = "IJGDEV2EJFUTIQTNHBYG2SZXJ5IXOMBR"

SENDER_EMAIL = "balanisuresh@gmail.com"
RECEIVER_EMAIL = "balanisuresh@gmail.com"
APP_PASSWORD = os.environ.get("APP_PASSWORD")

# Strategy Parameters
STOCH_K_PERIOD = 5             
STOCH_SMOOTH_K = 3             
STOCH_D_PERIOD = 3             
HIST_LOOKBACK_DAYS = 250       

fno_stocks = [
    '360ONE', 'ABB', 'ABCAPITAL', 'ADANIENSOL', 'ADANIENT', 'ADANIGREEN', 'ADANIPORTS', 
    'ADANIPOWER', 'ALKEM', 'AMBER', 'AMBUJACEM', 'ANGELONE', 'APLAPOLLO', 'APOLLOHOSP', 
    'ASHOKLEY', 'ASIANPAINT', 'ASTRAL', 'ATHERENERG', 'AUBANK', 'AUROPHARMA', 'AXISBANK', 
    'BAJAJ-AUTO', 'BAJAJFINSV', 'BAJAJHLDNG', 'BAJFINANCE', 'BANDHANBNK', 'BANKBARODA', 
    'BANKINDIA', 'BDL', 'BEL', 'BHARATFORG', 'BHARTIARTL', 'BHEL', 'BIOCON', 
    'BLUESTARCO', 'BOSCHLTD', 'BPCL', 'BRITANNIA', 'BSE', 'CAMS', 'CANBK', 'CDSL', 
    'CGPOWER', 'CHOLAFIN', 'CIPLA', 'COALINDIA', 'COCHINSHIP', 'COFORGE', 'COLPAL', 
    'CONCOR', 'CROMPTON', 'CUMMINSIND', 'DABUR', 'DELHIVERY', 'DIVISLAB', 'DIXON', 
    'DLF', 'DMART', 'DRREDDY', 'EICHERMOT', 'ETERNAL', 'FEDERALBNK', 'FORCEMOT', 'FORTIS', 
    'GAIL', 'GLENMARK', 'GMRAIRPORT', 'GODFRYPHLP', 'GODREJCP', 'GODREJPROP', 'GRASIM', 
    'GVT&D', 'HAL', 'HAVELLS', 'HCLTECH', 'HDFCAMC', 'HDFCBANK', 'HDFCLIFE', 'HEROMOTOCO', 
    'HINDALCO', 'HINDPETRO', 'HINDUNILVR', 'HINDZINC', 'HYUNDAI', 'ICICIBANK', 'ICICIGI', 
    'ICICIPRULI', 'IDEA', 'IDFCFIRSTB', 'IEX', 'INDHOTEL', 'INDIANB', 'INDIGO', 
    'INDUSINDBK', 'INDUSTOWER', 'INFY', 'INOXWIND', 'IOC', 'IREDA', 'IRFC', 'ITC', 
    'JINDALSTEL', 'JIOFIN', 'JSWENERGY', 'JSWSTEEL', 'JUBLFOOD', 'KALYANKJIL', 'KAYNES', 
    'KEI', 'KFINTECH', 'KOTAKBANK', 'KPITTECH', 'LAURUSLABS', 'LICHSGFIN', 'LICI', 
    'LODHA', 'LT', 'LTF', 'LTM', 'LUPIN', 'M&M', 'MAHABANK', 'MANAPPURAM', 'MANKIND', 
    'MARICO', 'MARUTI', 'MAXHEALTH', 'MAZDOCK', 'MCX', 'MFSL', 'MOTHERSON', 'MOTILALOFS', 
    'MPHASIS', 'MUTHOOTFIN', 'NAM-INDIA', 'NATIONALUM', 'NAUKRI', 'NBCC', 'NESTLEIND', 
    'NHPC', 'NMDC', 'NTPC', 'NYKAA', 'OBEROIRLTY', 'OFSS', 'OIL', 'ONGC', 
    'PAGEIND', 'PATANJALI', 'PAYTM', 'PERSISTENT', 'PETRONET', 'PFC', 'PGEL', 'PHOENIXLTD', 
    'PIDILITIND', 'PIIND', 'PNB', 'PNBHOUSING', 'POLICYBZR', 'POLYCAB', 'POWERGRID', 
    'POWERINDIA', 'PREMIERENE', 'PRESTIGE', 'RADICO', 'RBLBANK', 'RECLTD', 'RELIANCE', 
    'RVNL', 'SAGILITY', 'SAIL', 'SBICARD', 'SBILIFE', 'SBIN', 'SHREECEM', 'SHRIRAMFIN', 
    'SIEMENS', 'SOLARINDS', 'SONACOMS', 'SRF', 'SUNPHARMA', 'SUPREMEIND', 'SUZLON', 
    'SWIGGY', 'TATACONSUM', 'TATAELXSI', 'TATAPOWER', 'TATASTEEL', 'TCS', 'TECHM', 
    'TIINDIA', 'TITAN', 'TMPV', 'TORNTPHARM', 'TRENT', 'TVSMOTOR', 'ULTRACEMCO', 
    'UNIONBANK', 'UNITDSPR', 'UNOMINDA', 'UPL', 'VBL', 'VEDL', 'VMM', 'VOLTAS', 
    'WAAREEENER', 'WIPRO', 'YESBANK', 'ZYDUSLIFE'
]

# ==========================================
# 2. HELPER & CALCULATION FUNCTIONS
# ==========================================
def parse_expiry_date(exp_str):
    if not exp_str: return None
    exp_str = str(exp_str).strip()
    for fmt in ("%d%m%Y", "%Y-%m-%d", "%d-%b-%Y", "%d%b%Y"):
        try:
            return datetime.strptime(exp_str, fmt).date()
        except ValueError:
            continue
    return None

def parse_historical_to_df(hist_generator):
    rows = []
    for item in hist_generator:
        if isinstance(item, dict):
            dt_val = item.get("datetime") or item.get("date") or item.get("time")
            o, h, l, c = item.get("open", 0), item.get("high", 0), item.get("low", 0), item.get("close", 0)
            v = item.get("volume", 0)
            rows.append([dt_val, float(o), float(h), float(l), float(c), float(v)])
        elif isinstance(item, (list, tuple)) and len(item) >= 6:
            rows.append([item[0], float(item[1]), float(item[2]), float(item[3]), float(item[4]), float(item[5])])
        elif isinstance(item, str):
            parts = item.strip().split(",")
            if len(parts) >= 6:
                rows.append([parts[0], float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4]), float(parts[5])])

    if not rows: return pd.DataFrame()
    df = pd.DataFrame(rows, columns=["Datetime", "Open", "High", "Low", "Close", "Volume"])
    for col in ["Open", "High", "Low", "Close", "Volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    if not np.issubdtype(df["Datetime"].dtype, np.datetime64):
        df["Datetime"] = pd.to_datetime(df["Datetime"], errors="coerce", dayfirst=True)

    df.dropna(subset=["Datetime", "Close"], inplace=True)
    df.sort_values("Datetime", inplace=True)
    return df.reset_index(drop=True)

def calculate_stoch_533(df, k_period=5, smooth_k=3, d_period=3):
    low_min = df["Low"].rolling(window=k_period).min()
    high_max = df["High"].rolling(window=k_period).max()
    denom = (high_max - low_min).replace(0, np.nan)
    fast_k = 100.0 * ((df["Close"] - low_min) / denom)
    slow_k = fast_k.rolling(window=smooth_k).mean() 
    slow_d = slow_k.rolling(window=d_period).mean()
    return slow_d

def calculate_atr(df, period=100):
    high_low = df['High'] - df['Low']
    high_close = (df['High'] - df['Close'].shift()).abs()
    low_close = (df['Low'] - df['Close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()

# ==========================================
# 3. STRATEGY LOGIC EVALUATORS (DIVERGENCE)
# ==========================================
def evaluate_bullish_divergence(df, current_idx):
    curr_c = df.loc[current_idx, 'Close']
    prev_c = df.loc[current_idx-1, 'Close']
    m2_c = df.loc[current_idx-2, 'Close']
    
    curr_d = df.loc[current_idx, 'Stoch_D']
    prev_d = df.loc[current_idx-1, 'Stoch_D']
    m2_d = df.loc[current_idx-2, 'Stoch_D']
    
    live_div = (curr_c < prev_c) and (curr_d > prev_d)
    m1_div = (prev_c < m2_c) and (prev_d > m2_d)
    
    if not (live_div or m1_div): 
        return False
        
    if live_div and m1_div:
        div_type = "Both"
    elif live_div:
        div_type = "Live Only"
    else:
        div_type = "-1 Only"

    ref_atr = df.loc[current_idx, 'ATR100']
    if pd.isna(ref_atr): return False
    
    bars_to_check = []
    if live_div: bars_to_check.append(current_idx)
    if m1_div: bars_to_check.append(current_idx-1)
    
    max_body = 0
    for idx in bars_to_check:
        body = abs(df.loc[idx, 'Open'] - df.loc[idx, 'Close'])
        max_body = max(max_body, body)
        if body >= (0.67 * ref_atr):
            return False 
        
    live_out = "YES" if live_div else "NO"
    m1_out = "YES" if m1_div else "NO"
    
    return {
        "Signal": "Bull Div 🟢",
        "Div Match": div_type,
        "Ref ATR": round(ref_atr, 2),
        "Max Body": round(max_body, 2),
        "Live Div": live_out,
        "Minus1 Div": m1_out
    }

def evaluate_bearish_divergence(df, current_idx):
    curr_c = df.loc[current_idx, 'Close']
    prev_c = df.loc[current_idx-1, 'Close']
    m2_c = df.loc[current_idx-2, 'Close']
    
    curr_d = df.loc[current_idx, 'Stoch_D']
    prev_d = df.loc[current_idx-1, 'Stoch_D']
    m2_d = df.loc[current_idx-2, 'Stoch_D']
    
    live_div = (curr_c > prev_c) and (curr_d < prev_d)
    m1_div = (prev_c > m2_c) and (prev_d < m2_d)
    
    if not (live_div or m1_div): 
        return False
        
    if live_div and m1_div:
        div_type = "Both"
    elif live_div:
        div_type = "Live Only"
    else:
        div_type = "-1 Only"
    
    ref_atr = df.loc[current_idx, 'ATR100']
    if pd.isna(ref_atr): return False
    
    bars_to_check = []
    if live_div: bars_to_check.append(current_idx)
    if m1_div: bars_to_check.append(current_idx-1)
    
    max_body = 0
    for idx in bars_to_check:
        body = abs(df.loc[idx, 'Open'] - df.loc[idx, 'Close'])
        max_body = max(max_body, body)
        if body >= (0.67 * ref_atr):
            return False 
        
    live_out = "YES" if live_div else "NO"
    m1_out = "YES" if m1_div else "NO"
    
    return {
        "Signal": "Bear Div 🔴",
        "Div Match": div_type,
        "Ref ATR": round(ref_atr, 2),
        "Max Body": round(max_body, 2),
        "Live Div": live_out,
        "Minus1 Div": m1_out
    }

# ==========================================
# 4. NOTIFICATION & MAIN ENGINE
# ==========================================
def send_email_alert(results_df, timestamp):
    if not APP_PASSWORD: return
    msg = EmailMessage()
    msg["Subject"] = f"🎯 Daily Divergence Alert (5,3,3) - ({timestamp})"
    msg["From"] = SENDER_EMAIL
    msg["To"] = RECEIVER_EMAIL

    html_table = results_df.to_html(index=False, justify="center")
    body = (
        f"<h3>Daily Futures Divergence Scan at {timestamp}</h3>"
        f"<ul>"
        f"<li>Filters for Price & Stochastic (5,3,3) diverging on the Live Bar (0 vs -1), -1 Bar (-1 vs -2), or Both.</li>"
        f"<li>Reference ATR uses standard ATR(100).</li>"
        f"<li>Diverging bar bodies are strictly < 0.67 * ATR(100).</li>"
        f"</ul>"
        f"{html_table}"
    )

    msg.set_content(results_df.to_string(index=False))
    msg.add_alternative(body, subtype="html")

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(SENDER_EMAIL, APP_PASSWORD.replace(" ", ""))
            smtp.send_message(msg)
        print("✅ Alert email successfully sent!")
    except Exception as e:
        print(f"❌ Failed to send email: {e}")

def run_definedge_daily_scan():
    ist_tz = pytz.timezone("Asia/Kolkata")
    now_ist = datetime.now(ist_tz)
    now_ist_str = now_ist.strftime("%d-%b %H:%M:%S")
    print(f"[{now_ist_str}] Logging into Definedge for Daily Divergence Scan...")

    conn = ConnectToIntegrate()
    try:
        current_totp = pyotp.TOTP(TOTP_SECRET.replace(" ", "")).now()
        conn.login(api_token=API_TOKEN.strip(), api_secret=API_SECRET.strip(), totp=current_totp)
        ic = IntegrateData(conn)
        print("✅ Logged in! Indexing NFO Stock Futures...")
    except Exception as auth_err:
        print(f"❌ Definedge Login Failed: {auth_err}")
        return

    today_date_local = now_ist.date()
    stock_set = set(fno_stocks)
    fut_by_stock = {}

    for sym in conn.symbols:
        if sym.get("segment") == conn.EXCHANGE_TYPE_NFO and sym.get("instrument_type") == "FUTSTK":
            base_sym = sym.get("symbol")
            if base_sym in stock_set:
                exp_date = parse_expiry_date(sym.get("expiry"))
                if exp_date and exp_date >= today_date_local:
                    fut_by_stock.setdefault(base_sym, []).append((exp_date, sym))

    results = []
    end_time = now_ist.replace(tzinfo=None)
    start_time = end_time - timedelta(days=HIST_LOOKBACK_DAYS)

    for idx, stock in enumerate(fno_stocks, 1):
        print(f"Scanning {stock} ({idx}/{len(fno_stocks)})...", flush=True)
        if stock not in fut_by_stock: continue

        all_entries = fut_by_stock[stock]
        nearest_expiry = min(exp for exp, _ in all_entries)
        fut_contract = next(sym for exp, sym in all_entries if exp == nearest_expiry)
        fut_tsym = fut_contract["trading_symbol"]

        try:
            # 1. Fetch historical daily data
            hist_gen = ic.historical_data(
                exchange=conn.EXCHANGE_TYPE_NFO,
                trading_symbol=fut_tsym,
                timeframe=conn.TIMEFRAME_TYPE_DAY,
                start=start_time,
                end=end_time,
            )
            df_daily = parse_historical_to_df(hist_gen)
            if df_daily.empty: continue

            # 2. HYBRID FETCH FIX: Ensure today's EOD candle is evaluated even if Definedge API delays it.
            last_date_in_db = df_daily.loc[df_daily.index[-1], 'Datetime'].date()
            
            if last_date_in_db < today_date_local:
                # API is lagging. Fetch today's intraday tick data to build the Live Daily Candle.
                today_start = datetime.combine(today_date_local, datetime.min.time())
                try:
                    intra_gen = ic.historical_data(
                        exchange=conn.EXCHANGE_TYPE_NFO,
                        trading_symbol=fut_tsym,
                        timeframe=conn.TIMEFRAME_TYPE_MIN,  # Fetch 1-min data for today only
                        start=today_start,
                        end=end_time,
                    )
                    df_intra = parse_historical_to_df(intra_gen)
                    
                    if not df_intra.empty:
                        new_candle = pd.DataFrame([{
                            "Datetime": pd.to_datetime(today_date_local),
                            "Open": df_intra.iloc[0]['Open'],
                            "High": df_intra['High'].max(),
                            "Low": df_intra['Low'].min(),
                            "Close": df_intra.iloc[-1]['Close'],
                            "Volume": df_intra['Volume'].sum()
                        }])
                        df_daily = pd.concat([df_daily, new_candle], ignore_index=True)
                except Exception:
                    pass # Fallback to whatever the API provided if this fails

            if len(df_daily) < 110: continue 

            df_daily["Stoch_D"] = calculate_stoch_533(df_daily, STOCH_K_PERIOD, STOCH_SMOOTH_K, STOCH_D_PERIOD)
            df_daily["ATR100"] = calculate_atr(df_daily, 100)

            current_idx = len(df_daily) - 1
            
            if current_idx < 2: continue
            if pd.isna(df_daily.loc[current_idx, 'Stoch_D']) or pd.isna(df_daily.loc[current_idx-2, 'Stoch_D']): continue
            if pd.isna(df_daily.loc[current_idx, 'ATR100']): continue
            
            bull_data = evaluate_bullish_divergence(df_daily, current_idx)
            bear_data = evaluate_bearish_divergence(df_daily, current_idx)
            
            match_data = bull_data if bull_data else bear_data
            
            if match_data:
                time_str = df_daily.loc[current_idx, 'Datetime'].strftime("%d-%b-%Y")
                print(f"  ✅ MATCH: {fut_tsym} | {match_data['Signal']} | Match On: {match_data['Div Match']}")
                
                results.append({
                    "Stock": stock,
                    "Setup": match_data["Signal"],
                    "Match On": match_data["Div Match"],
                    "Bar Date": time_str,
                    "Live Div": match_data["Live Div"],
                    "-1 Div": match_data["Minus1 Div"],
                    "ATR(100)": match_data["Ref ATR"],
                    "Max Body": match_data["Max Body"]
                })

        except Exception as e:
            continue

    if results:
        res_df = pd.DataFrame(results)
        
        setup_order = ["Bull Div 🟢", "Bear Div 🔴"]
        match_order = ["Both", "Live Only", "-1 Only"]
        
        res_df["Setup"] = pd.Categorical(res_df["Setup"], categories=setup_order, ordered=True)
        res_df["Match On"] = pd.Categorical(res_df["Match On"], categories=match_order, ordered=True)
        
        res_df = res_df.sort_values(by=["Setup", "Match On", "Stock"]).reset_index(drop=True)
        
        print("\n🎯 Matches found! Sending email notification...")
        print(tabulate(res_df, headers="keys", tablefmt="psql", showindex=False))
        send_email_alert(res_df, now_ist_str)
    else:
        print("\nNo setups matched the Daily Divergence strategy.")

if __name__ == "__main__":
    run_definedge_daily_scan()
