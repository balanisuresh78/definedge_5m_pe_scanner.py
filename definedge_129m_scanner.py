import os
import time
import smtplib
from email.message import EmailMessage
from datetime import datetime, timedelta, time as dt_time
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

# Strategy Parameters (129-Min Timeframe, 4-Bar Compression)
TIMEFRAME_MINS = 129
ATR_PERIOD = 100
BODY_ATR_MULT = 0.67
HIST_LOOKBACK_DAYS = 75  # ~50 trading days = ~150 bars of 129-min candles

# Exact IST Bar-Close Scan Targets (15 seconds after each bar closes)
SCAN_TARGETS_IST = [
    dt_time(11, 24, 15),  # Candle 1 Close (09:15 - 11:24)
    dt_time(13, 33, 15),  # Candle 2 Close (11:24 - 13:33)
    dt_time(15, 40, 15),  # Candle 3 Close (13:33 - 15:40)
]

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
    if not exp_str:
        return None
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

    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=["Datetime", "Open", "High", "Low", "Close", "Volume"])
    for col in ["Open", "High", "Low", "Close", "Volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    if not np.issubdtype(df["Datetime"].dtype, np.datetime64):
        df["Datetime"] = pd.to_datetime(df["Datetime"], errors="coerce", dayfirst=True)

    df.dropna(subset=["Datetime", "Close"], inplace=True)
    df.sort_values("Datetime", inplace=True)
    return df.reset_index(drop=True)

def resample_to_129m(df_1m, now_ist, tf_mins=129):
    """
    Builds exact 129-minute candles anchored to 09:15 AM IST:
    Bucket 0: 09:15 - 11:23 (closes at 11:24)
    Bucket 1: 11:24 - 13:32 (closes at 13:33)
    Bucket 2: 13:33 - 15:40 (closes at 15:40)
    Automatically drops any currently forming (incomplete) bar for today.
    """
    if df_1m.empty:
        return pd.DataFrame()

    times = df_1m["Datetime"].dt.time
    df = df_1m[(times >= dt_time(9, 15)) & (times <= dt_time(15, 40))].copy()
    if df.empty:
        return pd.DataFrame()

    day_open = df["Datetime"].dt.normalize() + pd.Timedelta(hours=9, minutes=15)
    mins_from_open = ((df["Datetime"] - day_open).dt.total_seconds() // 60).astype(int)

    df["TradeDate"] = df["Datetime"].dt.date
    df["Bucket"] = (mins_from_open // tf_mins).clip(lower=0, upper=2)

    df_tf = df.groupby(["TradeDate", "Bucket"], as_index=False).agg(
        Datetime=("Datetime", "first"),
        Open=("Open", "first"),
        High=("High", "max"),
        Low=("Low", "min"),
        Close=("Close", "last"),
        Volume=("Volume", "sum")
    )

    # Drop any bar on today's date that has not finished closing yet
    today_date = now_ist.date()
    curr_time = now_ist.time()

    if curr_time < dt_time(11, 24):
        max_completed_bucket = -1
    elif curr_time < dt_time(13, 33):
        max_completed_bucket = 0
    elif curr_time < dt_time(15, 30):
        max_completed_bucket = 1
    else:
        max_completed_bucket = 2

    df_tf = df_tf[
        (df_tf["TradeDate"] < today_date) |
        ((df_tf["TradeDate"] == today_date) & (df_tf["Bucket"] <= max_completed_bucket))
    ].copy()

    df_tf.sort_values("Datetime", inplace=True)
    return df_tf.drop(columns=["TradeDate", "Bucket"]).reset_index(drop=True)

def calculate_atr(df, period=100):
    high_low = df['High'] - df['Low']
    high_close = (df['High'] - df['Close'].shift()).abs()
    low_close = (df['Low'] - df['Close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()

# ==========================================
# 3. STRATEGY LOGIC EVALUATOR (4-BAR 129M)
# ==========================================
def evaluate_4bar_setup(df, current_idx):
    ref_atr = df.loc[current_idx, 'ATR100']
    if pd.isna(ref_atr):
        return False

    c0 = df.loc[current_idx, 'Close']
    c1 = df.loc[current_idx - 1, 'Close']
    c2 = df.loc[current_idx - 2, 'Close']
    c3 = df.loc[current_idx - 3, 'Close']
    c4 = df.loc[current_idx - 4, 'Close']

    # 4 consecutive lower closes (Bull Setup) or 4 consecutive higher closes (Bear Setup)
    four_down = (c0 < c1) and (c1 < c2) and (c2 < c3) and (c3 < c4)
    four_up = (c0 > c1) and (c1 > c2) and (c2 > c3) and (c3 > c4)

    if not (four_down or four_up):
        return False

    # Check that ALL FOUR bars (0, -1, -2, -3) have bodies strictly < 0.67 * ATR(100)
    bars_to_check = [current_idx, current_idx - 1, current_idx - 2, current_idx - 3]
    max_4b_body = 0.0

    for idx in bars_to_check:
        body = abs(df.loc[idx, 'Open'] - df.loc[idx, 'Close'])
        max_4b_body = max(max_4b_body, body)
        if body >= (BODY_ATR_MULT * ref_atr):
            return False

    live_body = abs(df.loc[current_idx, 'Open'] - df.loc[current_idx, 'Close'])
    ratio = round(ref_atr / live_body, 2) if live_body > 0 else 999.99

    signal = "Bull Setup 🟢" if four_down else "Bear Setup 🔴"

    return {
        "Signal": signal,
        "Ref ATR": round(ref_atr, 2),
        "Max 4B Body": round(max_4b_body, 2),
        "Live Body": round(live_body, 2),
        "Ratio": ratio
    }

# ==========================================
# 4. NOTIFICATION & SCANNER ENGINE
# ==========================================
def send_email_alert(results_df, timestamp, bar_label):
    if not APP_PASSWORD:
        print("❌ ERROR: APP_PASSWORD environment variable is empty! Check GitHub Secrets.")
        return

    msg = EmailMessage()
    msg["From"] = SENDER_EMAIL
    msg["To"] = RECEIVER_EMAIL

    if results_df.empty:
        msg["Subject"] = f"⚪ 129m 4-Bar Scan ({bar_label}): 0 Matches - ({timestamp})"
        body = (
            f"<h3>Futures 129-Min (4-Bar) Scan at {timestamp}</h3>"
            f"<p>Evaluated Bar: <b>{bar_label}</b></p>"
            f"<p>Scan completed across all NFO stocks, but <b>0 setups</b> matched the 4-Bar Compression criteria.</p>"
        )
        msg.set_content(f"Scan completed for {bar_label}. 0 setups matched.")
        msg.add_alternative(body, subtype="html")
    else:
        msg["Subject"] = f"🎯 129m 4-Bar Alert [{bar_label}] ({len(results_df)} Matches) - ({timestamp})"

        buy_stocks = results_df[results_df["Setup"] == "Bull Setup 🟢"]["Stock"].head(5).tolist()
        sell_stocks = results_df[results_df["Setup"] == "Bear Setup 🔴"]["Stock"].head(5).tolist()

        buy_str = ", ".join(buy_stocks) if buy_stocks else "None"
        sell_str = ", ".join(sell_stocks) if sell_stocks else "None"

        html_table = results_df.to_html(index=False, justify="center")
        body = (
            f"<h3>Futures 129-Min (4-Bar) Compression Scan at {timestamp}</h3>"
            f"<p><b>Completed Bar Evaluated:</b> {bar_label}</p>"
            f"<hr>"
            f"<h4>📋 BUY GROUP - Top 5 (Copy & Paste into Zone):</h4>"
            f"<div style='background-color: #f4f4f4; padding: 10px; font-family: monospace; border: 1px solid #ccc;'>{buy_str}</div>"
            f"<h4>📋 SELL GROUP - Top 5 (Copy & Paste into Zone):</h4>"
            f"<div style='background-color: #f4f4f4; padding: 10px; font-family: monospace; border: 1px solid #ccc;'>{sell_str}</div>"
            f"<hr>"
            f"<ul>"
            f"<li><b>Timeframe:</b> 129-Minute Candles (09:15, 11:24, 13:33 IST - Close 15:40).</li>"
            f"<li><b>Bull Setup 🟢:</b> 4 Consecutive Lower Closes (Bars 0, -1, -2, -3).</li>"
            f"<li><b>Bear Setup 🔴:</b> 4 Consecutive Higher Closes (Bars 0, -1, -2, -3).</li>"
            f"<li>All 4 bar bodies are strictly &lt; 0.67 * ATR(100).</li>"
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
        print(f"✅ Alert email successfully sent for bar [{bar_label}]!")
    except Exception as e:
        print(f"❌ Failed to send email: {e}")

def execute_single_scan():
    ist_tz = pytz.timezone("Asia/Kolkata")
    now_ist = datetime.now(ist_tz)
    now_ist_str = now_ist.strftime("%d-%b %H:%M:%S")
    print(f"\n[{now_ist_str}] Logging into Definedge for 129-Min (4-Bar) Scan...", flush=True)

    conn = ConnectToIntegrate()
    try:
        current_totp = pyotp.TOTP(TOTP_SECRET.replace(" ", "")).now()
        conn.login(api_token=API_TOKEN.strip(), api_secret=API_SECRET.strip(), totp=current_totp)
        ic = IntegrateData(conn)
        print("✅ Logged in! Indexing NFO Stock Futures...", flush=True)
    except Exception as auth_err:
        print(f"❌ Definedge Login Failed: {auth_err}", flush=True)
        return None

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
    latest_bar_str = "Latest Completed Bar"

    for idx, stock in enumerate(fno_stocks, 1):
        print(f"Scanning {stock} ({idx}/{len(fno_stocks)})...", flush=True)
        if stock not in fut_by_stock:
            continue

        all_entries = fut_by_stock[stock]
        nearest_expiry = min(exp for exp, _ in all_entries)
        fut_contract = next(sym for exp, sym in all_entries if exp == nearest_expiry)
        fut_tsym = fut_contract["trading_symbol"]

        try:
            intra_gen = ic.historical_data(
                exchange=conn.EXCHANGE_TYPE_NFO,
                trading_symbol=fut_tsym,
                timeframe=conn.TIMEFRAME_TYPE_MIN,
                start=start_time,
                end=end_time,
            )
            df_1m = parse_historical_to_df(intra_gen)
            if df_1m.empty:
                continue

            df_129m = resample_to_129m(df_1m, now_ist, TIMEFRAME_MINS)
            if len(df_129m) < (ATR_PERIOD + 5):
                continue

            df_129m["ATR100"] = calculate_atr(df_129m, ATR_PERIOD)
            current_idx = len(df_129m) - 1

            if current_idx < 4:
                continue
            if pd.isna(df_129m.loc[current_idx, 'ATR100']):
                continue

            bar_time_str = df_129m.loc[current_idx, 'Datetime'].strftime("%d-%b %H:%M")
            latest_bar_str = bar_time_str

            match_data = evaluate_4bar_setup(df_129m, current_idx)

            if match_data:
                print(f"  ✅ MATCH: {fut_tsym} | {match_data['Signal']} | Bar: {bar_time_str} | Ratio: {match_data['Ratio']}", flush=True)

                results.append({
                    "Stock": stock,
                    "Setup": match_data["Signal"],
                    "Bar Open": bar_time_str,
                    "ATR(100)": match_data["Ref ATR"],
                    "Max 4B Body": match_data["Max 4B Body"],
                    "Live Body": match_data["Live Body"],
                    "Ratio": match_data["Ratio"]
                })

        except Exception:
            continue

    if results:
        res_df = pd.DataFrame(results)
        setup_order = ["Bull Setup 🟢", "Bear Setup 🔴"]
        res_df["Setup"] = pd.Categorical(res_df["Setup"], categories=setup_order, ordered=True)
        res_df = res_df.sort_values(by=["Setup", "Ratio"], ascending=[True, False]).reset_index(drop=True)

        print(f"\n🎯 Matches found for [{latest_bar_str}]! Sending email notification...", flush=True)
        print(tabulate(res_df, headers="keys", tablefmt="psql", showindex=False), flush=True)
        send_email_alert(res_df, now_ist_str, latest_bar_str)
    else:
        print(f"\nNo setups matched for [{latest_bar_str}]. Sending 0-match confirmation email...", flush=True)
        send_email_alert(pd.DataFrame(), now_ist_str, latest_bar_str)

    return latest_bar_str

def run_definedge_129m_scheduler():
    ist_tz = pytz.timezone("Asia/Kolkata")
    now_ist = datetime.now(ist_tz)
    event_name = os.environ.get("GITHUB_EVENT_NAME", "manual")

    # 1. Always run an immediate scan if triggered manually OR if a bar has already closed today
    if event_name == "workflow_dispatch" or now_ist.time() >= dt_time(11, 24):
        print(f"Trigger: {event_name} at {now_ist.strftime('%H:%M:%S')} IST -> Running immediate scan...", flush=True)
        execute_single_scan()

    # 2. If it's a weekday during market hours, stay awake for any upcoming 129m bar closes within 4.5 hours
    while True:
        now_ist = datetime.now(ist_tz)
        if now_ist.weekday() >= 5 or now_ist.time() >= dt_time(15, 41):
            print("Market session finished for today. Exiting cleanly.", flush=True)
            break

        upcoming_targets = [
            datetime.combine(now_ist.date(), t, tzinfo=ist_tz)
            for t in SCAN_TARGETS_IST
            if t > now_ist.time()
        ]
        if not upcoming_targets:
            break

        next_target = upcoming_targets[0]
        wait_seconds = (next_target - now_ist).total_seconds()

        # Only wait if the next bar close is within 4.5 hours (prevents GitHub 6h job timeout)
        if wait_seconds > 16200:
            print(f"Next target {next_target.strftime('%H:%M:%S')} is >4.5 hours away. Exiting until next trigger.", flush=True)
            break

        print(f"⏳ Waiting {int(wait_seconds // 60)}m {int(wait_seconds % 60)}s until next 129m bar close at {next_target.strftime('%H:%M:%S')} IST...", flush=True)
        time.sleep(max(1, wait_seconds))
        execute_single_scan()

if __name__ == "__main__":
    run_definedge_129m_scheduler()
