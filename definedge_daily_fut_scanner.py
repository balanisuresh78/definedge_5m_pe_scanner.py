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
STOCH_K = 5                    
STOCH_D = 3                    
HIST_LOOKBACK_DAYS = 120       

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

def calculate_stoch_d(df, k_period=5, d_period=3):
    low_min = df["Low"].rolling(window=k_period).min()
    high_max = df["High"].rolling(window=k_period).max()
    denom = (high_max - low_min).replace(0, np.nan)
    raw_k = 100.0 * ((df["Close"] - low_min) / denom)
    stoch_k_smoothed = raw_k.rolling(window=3).mean() 
    return stoch_k_smoothed.rolling(window=d_period).mean()

def calculate_atr(df, period=2):
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
    
    # 1. Condition 1 & 2: Two consecutive bars of price dropping but Stoch rising
    if not (curr_c < prev_c and curr_d > prev_d): return False
    if not (prev_c < m2_c and prev_d > m2_d): return False

    # 2. Trace back to find the Impulse Peak
    search_window = df.loc[max(0, current_idx - 40):current_idx-2]
    if search_window.empty: return False
    peak_idx = search_window['Close'].idxmax()
    if peak_idx >= current_idx - 1 or peak_idx == max(0, current_idx - 40): 
        return False
        
    trough_window = df.loc[max(0, peak_idx - 40):peak_idx]
    if trough_window.empty: return False
    trough_idx = trough_window['Close'].idxmin()
    if trough_idx >= peak_idx or trough_idx == max(0, peak_idx - 40): 
        return False
        
    impulse_df = df.loc[trough_idx:peak_idx]
    correction_df = df.loc[peak_idx:current_idx]
    
    # 3. Target UP bars in impulse for Ref ATR
    up_bars = impulse_df[impulse_df['Close'] > impulse_df['Open']]
    if len(up_bars) == 0: return False
        
    atr_values = up_bars['ATR2'].sort_values(ascending=False)
    top_n = max(1, len(atr_values) // 2)
    ref_atr = atr_values.head(top_n).mean()
    
    # 4. Check Body Size for all correction DOWN bars (< 75% Ref ATR)
    down_bars = correction_df[correction_df['Close'] < correction_df['Open']]
    if len(down_bars) == 0: return False 
    
    bodies = (down_bars['Open'] - down_bars['Close']).abs()
    if not all(bodies < (0.75 * ref_atr)):
        return False
        
    # Calculate separate divergences for display
    live_div = curr_d - prev_d
    minus1_div = prev_d - m2_d
    
    return {
        "Signal": "Bull Div 🟢",
        "Ref ATR": round(ref_atr, 2),
        "Max Body": round(bodies.max(), 2),
        "Live Div": f"+{live_div:.2f}",
        "Minus1 Div": f"+{minus1_div:.2f}"
    }

def evaluate_bearish_divergence(df, current_idx):
    curr_c = df.loc[current_idx, 'Close']
    prev_c = df.loc[current_idx-1, 'Close']
    m2_c = df.loc[current_idx-2, 'Close']
    
    curr_d = df.loc[current_idx, 'Stoch_D']
    prev_d = df.loc[current_idx-1, 'Stoch_D']
    m2_d = df.loc[current_idx-2, 'Stoch_D']
    
    # 1. Condition 1 & 2: Two consecutive bars of price rising but Stoch dropping
    if not (curr_c > prev_c and curr_d < prev_d): return False
    if not (prev_c > m2_c and prev_d < m2_d): return False

    # 2. Trace back to find the Impulse Trough
    search_window = df.loc[max(0, current_idx - 40):current_idx-2]
    if search_window.empty: return False
    trough_idx = search_window['Close'].idxmin()
    if trough_idx >= current_idx - 1 or trough_idx == max(0, current_idx - 40): 
        return False
        
    peak_window = df.loc[max(0, trough_idx - 40):trough_idx]
    if peak_window.empty: return False
    peak_idx = peak_window['Close'].idxmax()
    if peak_idx >= trough_idx or peak_idx == max(0, trough_idx - 40): 
        return False
        
    impulse_df = df.loc[peak_idx:trough_idx]
    correction_df = df.loc[trough_idx:current_idx]
    
    # 3. Target DOWN bars in impulse for Ref ATR
    down_bars = impulse_df[impulse_df['Close'] < impulse_df['Open']]
    if len(down_bars) == 0: return False
        
    atr_values = down_bars['ATR2'].sort_values(ascending=False)
    top_n = max(1, len(atr_values) // 2)
    ref_atr = atr_values.head(top_n).mean()
    
    # 4. Check Body Size for all correction UP bars (< 75% Ref ATR)
    up_bars = correction_df[correction_df['Close'] > correction_df['Open']]
    if len(up_bars) == 0: return False 
    
    bodies = (up_bars['Close'] - up_bars['Open']).abs()
    if not all(bodies < (0.75 * ref_atr)):
        return False
        
    # Calculate separate divergences for display
    live_div = curr_d - prev_d
    minus1_div = prev_d - m2_d
    
    return {
        "Signal": "Bear Div 🔴",
        "Ref ATR": round(ref_atr, 2),
        "Max Body": round(bodies.max(), 2),
        "Live Div": f"{live_div:.2f}",
        "Minus1 Div": f"{minus1_div:.2f}"
    }

# ==========================================
# 4. NOTIFICATION & MAIN ENGINE
# ==========================================
def send_email_alert(results_df, timestamp):
    if not APP_PASSWORD: return
    msg = EmailMessage()
    msg["Subject"] = f"🎯 Daily Divergence Alert: 2-Bar Setup ({timestamp})"
    msg["From"] = SENDER_EMAIL
    msg["To"] = RECEIVER_EMAIL

    html_table = results_df.to_html(index=False, justify="center")
    body = (
        f"<h3>Daily Futures Divergence Scan at {timestamp}</h3>"
        f"<ul>"
        f"<li>Setup requires two consecutive bars of Price & Stochastic (5,3,3) diverging.</li>"
        f"<li>Corrective bodies are strictly < 75% of Reference ATR.</li>"
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

    today_date = now_ist.date()
    stock_set = set(fno_stocks)
    fut_by_stock = {}

    for sym in conn.symbols:
        if sym.get("segment") == conn.EXCHANGE_TYPE_NFO and sym.get("instrument_type") == "FUTSTK":
            base_sym = sym.get("symbol")
            if base_sym in stock_set:
                exp_date = parse_expiry_date(sym.get("expiry"))
                if exp_date and exp_date >= today_date:
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
            hist_gen = ic.historical_data(
                exchange=conn.EXCHANGE_TYPE_NFO,
                trading_symbol=fut_tsym,
                timeframe=conn.TIMEFRAME_TYPE_DAY,
                start=start_time,
                end=end_time,
            )
            df_daily = parse_historical_to_df(hist_gen)
            if df_daily.empty: continue

            # If scanning intraday (before 15:30), drop the incomplete forming daily candle
            if now_ist.time() < datetime.strptime("15:30", "%H:%M").time():
                df_daily = df_daily.iloc[:-1]

            if len(df_daily) < 60: continue 

            df_daily["Stoch_D"] = calculate_stoch_d(df_daily, STOCH_K, STOCH_D)
            df_daily["ATR2"] = calculate_atr(df_daily, 2)

            current_idx = len(df_daily) - 1
            
            # Check both Divergence logic engines
            bull_data = evaluate_bullish_divergence(df_daily, current_idx)
            bear_data = evaluate_bearish_divergence(df_daily, current_idx)
            
            match_data = bull_data if bull_data else bear_data
            
            if match_data:
                time_str = df_daily.loc[current_idx, 'Datetime'].strftime("%d-%b-%Y")
                
                print(f"  ✅ MATCH: {fut_tsym} | {match_data['Signal']} | Live Div: {match_data['Live Div']} | -1 Div: {match_data['Minus1 Div']}")
                
                results.append({
                    "Stock": stock,
                    "Setup": match_data["Signal"],
                    "Bar Date": time_str,
                    "Live Div": match_data["Live Div"],
                    "Minus1 Div": match_data["Minus1 Div"],
                    "Ref ATR": match_data["Ref ATR"],
                    "Max Body": match_data["Max Body"]
                })

        except Exception:
            continue

    if results:
        res_df = pd.DataFrame(results).sort_values(by="Stock", ascending=True).reset_index(drop=True)
        print("\n🎯 Matches found! Sending email notification...")
        print(tabulate(res_df, headers="keys", tablefmt="psql", showindex=False))
        send_email_alert(res_df, now_ist_str)
    else:
        print("\nNo setups matched the Daily Divergence strategy.")

if __name__ == "__main__":
    run_definedge_daily_scan()
