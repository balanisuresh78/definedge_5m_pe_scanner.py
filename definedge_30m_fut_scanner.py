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
TF_MINUTES = 30               
STOCH_K = 5                   
STOCH_D = 3                   
HIST_LOOKBACK_DAYS = 25       

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
        try:
            df["Datetime"] = pd.to_datetime(df["Datetime"], format="%d%m%Y%H%M")
        except Exception:
            df["Datetime"] = pd.to_datetime(df["Datetime"], errors="coerce")

    df.dropna(subset=["Datetime", "Close"], inplace=True)
    df.sort_values("Datetime", inplace=True)
    return df.reset_index(drop=True)

def resample_1m_to_custom_tf(df_1m, now_ist, tf_minutes):
    if df_1m.empty: return pd.DataFrame()
    df = df_1m.copy()
    mins_from_open = (df["Datetime"].dt.hour - 9) * 60 + df["Datetime"].dt.minute - 15
    valid_mask = (mins_from_open >= 0) & (mins_from_open < 375)
    df = df.loc[valid_mask].copy()
    if df.empty: return pd.DataFrame()

    df["Date_Only"] = df["Datetime"].dt.date
    df["Bin"] = ((df["Datetime"].dt.hour - 9) * 60 + df["Datetime"].dt.minute - 15) // tf_minutes

    grouped = df.groupby(["Date_Only", "Bin"])
    df_tf = grouped.agg(
        Datetime=("Datetime", "first"),
        Open=("Open", "first"),
        High=("High", "max"),
        Low=("Low", "min"),
        Close=("Close", "last"),
        Volume=("Volume", "sum")
    ).reset_index()

    last_row = df_tf.iloc[-1]
    last_date = last_row["Date_Only"]
    last_bin = int(last_row["Bin"])
    end_mins_from_open = min((last_bin + 1) * tf_minutes, 375)
    bin_close_dt = datetime.combine(last_date, datetime.min.time()) + timedelta(hours=9, minutes=15 + end_mins_from_open)

    now_naive_ist = now_ist.replace(tzinfo=None)
    if now_naive_ist < bin_close_dt:
        df_tf = df_tf.iloc[:-1]

    df_tf.drop(columns=["Date_Only", "Bin"], inplace=True)
    return df_tf.reset_index(drop=True)

def calculate_stoch_d(df, k_period=5, d_period=3):
    low_min = df["Low"].rolling(window=k_period).min()
    high_max = df["High"].rolling(window=k_period).max()
    denom = (high_max - low_min).replace(0, np.nan)
    stoch_k = 100.0 * ((df["Close"] - low_min) / denom)
    return stoch_k.rolling(window=d_period).mean()

def calculate_atr(df, period=2):
    high_low = df['High'] - df['Low']
    high_close = (df['High'] - df['Close'].shift()).abs()
    low_close = (df['Low'] - df['Close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()

# ==========================================
# 3. STRATEGY LOGIC EVALUATORS
# ==========================================
def evaluate_bullish_setup(df, current_idx):
    # 1. Find the recent Closing Peak (Top of the UP impulse)
    # Scan up to 40 bars backwards to find the highest close
    search_window = df.loc[max(0, current_idx - 40):current_idx]
    peak_idx = search_window['Close'].idxmax()
    if peak_idx >= current_idx or peak_idx == max(0, current_idx - 40): 
        return False
        
    # 2. Find the Trough (Bottom of the UP impulse)
    # Scan backwards from the Peak to find the lowest close
    trough_window = df.loc[max(0, peak_idx - 40):peak_idx]
    trough_idx = trough_window['Close'].idxmin()
    if trough_idx >= peak_idx or trough_idx == max(0, peak_idx - 40): 
        return False
        
    # 3. Define Phases
    impulse_df = df.loc[trough_idx:peak_idx]
    correction_df = df.loc[peak_idx:current_idx]
    
    # 4. Impulse Checks (Targeting UP Bars)
    up_bars = impulse_df[impulse_df['Close'] > impulse_df['Open']]
    if len(up_bars) > 10 or len(up_bars) == 0: 
        return False
        
    signal_found = False
    for idx in up_bars.index:
        if idx > 0 and pd.notna(df.loc[idx, 'ATR2']) and pd.notna(df.loc[idx-1, 'ATR2']):
            if df.loc[idx, 'ATR2'] >= 1.33 * df.loc[idx-1, 'ATR2']:
                signal_found = True
                break
    if not signal_found: 
        return False
    
    # 5. Reference ATR
    atr_values = up_bars['ATR2'].sort_values(ascending=False)
    top_n = max(1, len(atr_values) // 2)
    ref_atr = atr_values.head(top_n).mean()
    
    # 6. Correction Checks (Targeting DOWN Bars)
    down_bars = correction_df[correction_df['Close'] < correction_df['Open']]
    if len(down_bars) == 0: 
        return False 
    
    bodies = (down_bars['Open'] - down_bars['Close']).abs()
    if all(bodies < (0.75 * ref_atr)):
        return {"Signal": "Bullish 🟢", "Ref ATR": round(ref_atr, 2), "Max Body": round(bodies.max(), 2)}
    return False


def evaluate_bearish_setup(df, current_idx):
    # 1. Find the recent Closing Trough (Bottom of the DOWN impulse)
    # Scan up to 40 bars backwards to find the lowest close
    search_window = df.loc[max(0, current_idx - 40):current_idx]
    trough_idx = search_window['Close'].idxmin()
    if trough_idx >= current_idx or trough_idx == max(0, current_idx - 40): 
        return False
        
    # 2. Find the Peak (Top of the DOWN impulse)
    # Scan backwards from the Trough to find the highest close
    peak_window = df.loc[max(0, trough_idx - 40):trough_idx]
    peak_idx = peak_window['Close'].idxmax()
    if peak_idx >= trough_idx or peak_idx == max(0, trough_idx - 40): 
        return False
        
    # 3. Define Phases
    impulse_df = df.loc[peak_idx:trough_idx]
    correction_df = df.loc[trough_idx:current_idx]
    
    # 4. Impulse Checks (Targeting DOWN Bars)
    down_bars = impulse_df[impulse_df['Close'] < impulse_df['Open']]
    if len(down_bars) > 10 or len(down_bars) == 0: 
        return False
        
    signal_found = False
    for idx in down_bars.index:
        if idx > 0 and pd.notna(df.loc[idx, 'ATR2']) and pd.notna(df.loc[idx-1, 'ATR2']):
            if df.loc[idx, 'ATR2'] >= 1.33 * df.loc[idx-1, 'ATR2']:
                signal_found = True
                break
    if not signal_found: 
        return False
    
    # 5. Reference ATR
    atr_values = down_bars['ATR2'].sort_values(ascending=False)
    top_n = max(1, len(atr_values) // 2)
    ref_atr = atr_values.head(top_n).mean()
    
    # 6. Correction Checks (Targeting UP Bars)
    up_bars = correction_df[correction_df['Close'] > correction_df['Open']]
    if len(up_bars) == 0: 
        return False 
    
    bodies = (up_bars['Close'] - up_bars['Open']).abs()
    if all(bodies < (0.75 * ref_atr)):
        return {"Signal": "Bearish 🔴", "Ref ATR": round(ref_atr, 2), "Max Body": round(bodies.max(), 2)}
    return False

# ==========================================
# 4. NOTIFICATION & MAIN ENGINE
# ==========================================
def send_email_alert(results_df, timestamp):
    if not APP_PASSWORD: return
    msg = EmailMessage()
    msg["Subject"] = f"🎯 30m Futures Alert: ATR Retracement Setup ({timestamp})"
    msg["From"] = SENDER_EMAIL
    msg["To"] = RECEIVER_EMAIL

    html_table = results_df.to_html(index=False, justify="center")
    body = (
        f"<h3>30-Minute Stock Futures Scan at {timestamp}</h3>"
        f"<ul>"
        f"<li>Setup identified: ATR(2) signal bar found in impulse (<= 10 bars).</li>"
        f"<li>Correction bodies are strictly < 75% of Reference ATR.</li>"
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

def run_definedge_30m_scan():
    ist_tz = pytz.timezone("Asia/Kolkata")
    now_ist = datetime.now(ist_tz)
    now_ist_str = now_ist.strftime("%d-%b %H:%M:%S")
    print(f"[{now_ist_str}] Logging into Definedge for 30m Futures Scan...")

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
                timeframe=conn.TIMEFRAME_TYPE_MIN,
                start=start_time,
                end=end_time,
            )
            df_1m = parse_historical_to_df(hist_gen)
            if df_1m.empty: continue

            df_30m = resample_1m_to_custom_tf(df_1m, now_ist, TF_MINUTES)
            if len(df_30m) < 60: continue 

            df_30m["Stoch_D"] = calculate_stoch_d(df_30m, STOCH_K, STOCH_D)
            df_30m["ATR2"] = calculate_atr(df_30m, 2)

            current_idx = len(df_30m) - 1
            curr_d = df_30m.loc[current_idx, 'Stoch_D']
            prev_d = df_30m.loc[current_idx - 1, 'Stoch_D']
            
            if pd.isna(curr_d) or pd.isna(prev_d): continue

            # ==========================================
            # POINT 1 & POINT 5 TRIGGER DEFINITIONS
            # ==========================================
            stoch_crossed_31_downwards = (prev_d >= 31 and curr_d < 31)
            stoch_crossed_69_upwards = (prev_d <= 69 and curr_d > 69)
            
            match_data = False
            
            if stoch_crossed_31_downwards:
                match_data = evaluate_bullish_setup(df_30m, current_idx)
            elif stoch_crossed_69_upwards:
                match_data = evaluate_bearish_setup(df_30m, current_idx)
            
            if match_data:
                time_str = df_30m.loc[current_idx, 'Datetime'].strftime("%d-%b %H:%M")
                curr_close = df_30m.loc[current_idx, 'Close']
                print(f"  ✅ MATCH: {fut_tsym} | {match_data['Signal']} | Ref ATR: {match_data['Ref ATR']}")
                
                results.append({
                    "Stock": stock,
                    "Setup": match_data["Signal"],
                    "Contract": fut_tsym,
                    "Bar Time": time_str,
                    "Close": round(curr_close, 2),
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
        print("\nNo setups matched the 30m ATR Correction strategy.")

if __name__ == "__main__":
    run_definedge_30m_scan()

