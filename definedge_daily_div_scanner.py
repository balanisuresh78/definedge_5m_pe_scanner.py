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
ATR_PERIOD = 100
BODY_ATR_MULT = 0.67
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

def calculate_atr(df, period=100):
    high_low = df['High'] - df['Low']
    high_close = (df['High'] - df['Close'].shift()).abs()
    low_close = (df['Low'] - df['Close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()

# ==========================================
# 3. STRATEGY LOGIC EVALUATORS (3-BAR SETUP)
# ==========================================
def evaluate_3bar_setup(df, current_idx):
    ref_atr = df.loc[current_idx, 'ATR100']
    if pd.isna(ref_atr): 
        return False

    c0 = df.loc[current_idx, 'Close']
    c1 = df.loc[current_idx - 1, 'Close']
    c2 = df.loc[current_idx - 2, 'Close']
    c3 = df.loc[current_idx - 3, 'Close']

    # Check for 3 consecutive down closes (Bullish Pullback) or 3 consecutive up closes (Bearish Rally)
    three_down = (c0 < c1) and (c1 < c2) and (c2 < c3)
    three_up = (c0 > c1) and (c1 > c2) and (c2 > c3)

    if not (three_down or three_up):
        return False

    # Check that ALL THREE bars (0, -1, -2) have bodies strictly < 0.67 * ATR(100)
    bars_to_check = [current_idx, current_idx - 1, current_idx - 2]
    max_3b_body = 0.0

    for idx in bars_to_check:
        body = abs(df.loc[idx, 'Open'] - df.loc[idx, 'Close'])
        max_3b_body = max(max_3b_body, body)
        if body >= (BODY_ATR_MULT * ref_atr):
            return False

    live_body = abs(df.loc[current_idx, 'Open'] - df.loc[current_idx, 'Close'])
    ratio = round(ref_atr / live_body, 2) if live_body > 0 else 999.99

    signal = "Bull Setup 🟢" if three_down else "Bear Setup 🔴"

    return {
        "Signal": signal,
        "Ref ATR": round(ref_atr, 2),
        "Max 3B Body": round(max_3b_body, 2),
        "Live Body": round(live_body, 2),
        "Ratio": ratio
    }

# ==========================================
# 4. NOTIFICATION & MAIN ENGINE
# ==========================================
def send_email_alert(results_df, timestamp):
    if not APP_PASSWORD: return
    msg = EmailMessage()
    msg["Subject"] = f"🎯 Daily 3-Bar Compression Alert - ({timestamp})"
    msg["From"] = SENDER_EMAIL
    msg["To"] = RECEIVER_EMAIL

    # Extract top 5 for Buy and Sell groups
    buy_stocks = results_df[results_df["Setup"] == "Bull Setup 🟢"]["Stock"].head(5).tolist()
    sell_stocks = results_df[results_df["Setup"] == "Bear Setup 🔴"]["Stock"].head(5).tolist()

    buy_str = ", ".join(buy_stocks) if buy_stocks else "None"
    sell_str = ", ".join(sell_stocks) if sell_stocks else "None"

    html_table = results_df.to_html(index=False, justify="center")
    body = (
        f"<h3>Daily Futures 3-Bar Compression Scan at {timestamp}</h3>"
        f"<hr>"
        f"<h4>📋 BUY GROUP - Top 5 (Copy & Paste into Zone):</h4>"
        f"<div style='background-color: #f4f4f4; padding: 10px; font-family: monospace; border: 1px solid #ccc;'>{buy_str}</div>"
        f"<h4>📋 SELL GROUP - Top 5 (Copy & Paste into Zone):</h4>"
        f"<div style='background-color: #f4f4f4; padding: 10px; font-family: monospace; border: 1px solid #ccc;'>{sell_str}</div>"
        f"<hr>"
        f"<ul>"
        f"<li><b>Bull Setup 🟢:</b> 3 Consecutive Lower Closes (Bars 0, -1, -2).</li>"
        f"<li><b>Bear Setup 🔴:</b> 3 Consecutive Higher Closes (Bars 0, -1, -2).</li>"
        f"<li>All 3 bar bodies are strictly &lt; 0.67 * ATR(100).</li>"
        f"<li>Sorted by Ratio (ATR / Live Body) in descending order (Smallest Live Body on top).</li>"
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
    print(f"[{now_ist_str}] Logging into Definedge for Daily 3-Bar Scan...")

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
    # 1-day buffer ensures Definedge returns today's completed EOD candle during evening runs
    end_time_buffer = now_ist.replace(tzinfo=None) + timedelta(days=1)
    start_time = now_ist.replace(tzinfo=None) - timedelta(days=HIST_LOOKBACK_DAYS)

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
                end=end_time_buffer,
            )
            df_daily = parse_historical_to_df(hist_gen)
            if df_daily.empty: continue

            # 2. HYBRID FETCH FIX: Fallback to 1-min data if Daily EOD isn't updated yet
            last_date_in_db = df_daily.loc[df_daily.index[-1], 'Datetime'].date()
            
            if last_date_in_db < today_date_local:
                today_start = datetime.combine(today_date_local, datetime.min.time())
                try:
                    intra_gen = ic.historical_data(
                        exchange=conn.EXCHANGE_TYPE_NFO,
                        trading_symbol=fut_tsym,
                        timeframe=conn.TIMEFRAME_TYPE_MIN,
                        start=today_start,
                        end=now_ist.replace(tzinfo=None),
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
                    pass

            if len(df_daily) < 110: continue

            df_daily["ATR100"] = calculate_atr(df_daily, ATR_PERIOD)
            current_idx = len(df_daily) - 1
            
            if current_idx < 3: continue
            if pd.isna(df_daily.loc[current_idx, 'ATR100']): continue
            
            match_data = evaluate_3bar_setup(df_daily, current_idx)
            
            if match_data:
                time_str = df_daily.loc[current_idx, 'Datetime'].strftime("%d-%b-%Y")
                print(f"  ✅ MATCH: {fut_tsym} | {match_data['Signal']} | Ratio: {match_data['Ratio']}")
                
                results.append({
                    "Stock": stock,
                    "Setup": match_data["Signal"],
                    "Bar Date": time_str,
                    "ATR(100)": match_data["Ref ATR"],
                    "Max 3B Body": match_data["Max 3B Body"],
                    "Live Body": match_data["Live Body"],
                    "Ratio": match_data["Ratio"]
                })

        except Exception:
            continue

    if results:
        res_df = pd.DataFrame(results)
        
        setup_order = ["Bull Setup 🟢", "Bear Setup 🔴"]
        res_df["Setup"] = pd.Categorical(res_df["Setup"], categories=setup_order, ordered=True)
        
        # Sort by Setup (Bull then Bear), then Ratio descending (Smallest Live Body at the top)
        res_df = res_df.sort_values(by=["Setup", "Ratio"], ascending=[True, False]).reset_index(drop=True)
        
        print("\n🎯 Matches found! Sending email notification...")
        print(tabulate(res_df, headers="keys", tablefmt="psql", showindex=False))
        send_email_alert(res_df, now_ist_str)
    else:
        print("\nNo setups matched the Daily 3-Bar Compression strategy.")

if __name__ == "__main__":
    run_definedge_daily_scan()
