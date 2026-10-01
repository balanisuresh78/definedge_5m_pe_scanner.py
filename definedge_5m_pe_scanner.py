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
API_TOKEN = os.environ.get("7eb93aac-c746-44bd-9755-18ae6289fdfc", "")
API_SECRET = os.environ.get("snToBptj6e2X/c9c7POM8Q==", "")
TOTP_SECRET = os.environ.get("IJGDEV2EJFUTIQTNHBYG2SZXJ5IXOMBR", "")

SENDER_EMAIL = "balanisuresh@gmail.com"
RECEIVER_EMAIL = "balanisuresh@gmail.com"
APP_PASSWORD = os.environ.get("APP_PASSWORD")

# Strategy Parameters
TF_MINUTES = 77               # Target Timeframe: 77-minute candles
STOCH_K = 5                   # Stochastic %K period
STOCH_D = 3                   # Stochastic %D smoothing period
STOCH_THRESHOLD = 31.0        # Crosses below 31
STRICT_CROSSOVER = True       # True: prev >= 31 and curr < 31
LL_PERIOD = 34                # 34-bar Lowest Low lookback

HIST_LOOKBACK_DAYS = 15       # 15 calendar days ensures enough data for 34 bars of 77m
STRIKE_BAND_PCT = 0.15        # Scan PE strikes within +/- 15% of spot

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

def get_second_highest_oi_put(ic, conn, stock_symbol, pe_contracts, spot_ltp=None):
    candidates = []
    for sym in pe_contracts:
        try:
            strike_val = float(sym.get("strike", 0))
            if spot_ltp and strike_val > spot_ltp * 20:
                strike_val = strike_val / 100.0
        except (ValueError, TypeError):
            strike_val = 0.0

        if spot_ltp and spot_ltp > 0 and strike_val > 0:
            if not (spot_ltp * (1 - STRIKE_BAND_PCT) <= strike_val <= spot_ltp * (1 + STRIKE_BAND_PCT)):
                continue
        candidates.append((sym, strike_val))

    if len(candidates) < 2:
        candidates = [(sym, float(sym.get("strike", 0))) for sym in pe_contracts]

    oi_list = []
    for sym, strike_val in candidates:
        tsym = sym["trading_symbol"]
        try:
            q = ic.quotes(exchange=conn.EXCHANGE_TYPE_NFO, trading_symbol=tsym)
            if not isinstance(q, dict): continue
            oi = float(q.get("oi") or q.get("open_interest") or q.get("OI") or 0)
            ltp = float(q.get("ltp") or q.get("lp") or q.get("last_traded_price") or 0)
            if oi > 0:
                oi_list.append({"trading_symbol": tsym, "strike": strike_val, "oi": int(oi), "ltp": ltp})
        except Exception:
            continue

    if len(oi_list) < 2: return None
    oi_list.sort(key=lambda x: x["oi"], reverse=True)
    return oi_list[1] 

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
    df_tf.set_index("Datetime", inplace=True)
    return df_tf

def calculate_stoch_d(df, k_period=5, d_period=3):
    low_min = df["Low"].rolling(window=k_period).min()
    high_max = df["High"].rolling(window=k_period).max()
    denom = (high_max - low_min).replace(0, np.nan)
    stoch_k = 100.0 * ((df["Close"] - low_min) / denom)
    return stoch_k.rolling(window=d_period).mean()

def send_email_alert(results_df, timestamp):
    if not APP_PASSWORD: return
    msg = EmailMessage()
    msg["Subject"] = f"🎯 77m Stock PE Alert: %D < 31 on Minus 2 Bar ({timestamp})"
    msg["From"] = SENDER_EMAIL
    msg["To"] = RECEIVER_EMAIL

    html_table = results_df.to_html(index=False, justify="center")
    body = (
        f"<h3>77-Minute Stock PUT (2nd Highest OI) Scan at {timestamp}</h3>"
        f"<ul>"
        f"<li>%D (5,3) crossed below 31 on the <b>Minus 2 Bar</b>.</li>"
        f"<li>Price is currently ABOVE the lowest low of the last 34 completed candles.</li>"
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

# ==========================================
# 3. MAIN SCANNER ENGINE
# ==========================================
def run_definedge_77m_scan():
    ist_tz = pytz.timezone("Asia/Kolkata")
    now_ist = datetime.now(ist_tz)
    now_ist_str = now_ist.strftime("%d-%b %H:%M:%S")
    print(f"[{now_ist_str}] Logging into Definedge Integrate API for 77m Scan...")

    conn = ConnectToIntegrate()
    try:
        current_totp = pyotp.TOTP(TOTP_SECRET.replace(" ", "")).now()
        conn.login(api_token=API_TOKEN.strip(), api_secret=API_SECRET.strip(), totp=current_totp)
        ic = IntegrateData(conn)
        print("✅ Logged in! Grouping NFO Stock PUT contracts...")
    except Exception as auth_err:
        print(f"❌ Definedge Login Failed: {auth_err}")
        return

    today_date = now_ist.date()
    stock_set = set(fno_stocks)
    pe_by_stock = {}
    eq_symbol_map = {}

    for sym in conn.symbols:
        seg = sym.get("segment")
        base_sym = sym.get("symbol")
        if base_sym not in stock_set: continue

        if seg == conn.EXCHANGE_TYPE_NSE and sym.get("instrument_type") == "EQ":
            eq_symbol_map[base_sym] = sym.get("trading_symbol")
        elif seg == conn.EXCHANGE_TYPE_NFO and sym.get("instrument_type") == "OPTSTK" and sym.get("option_type") == "PE":
            exp_date = parse_expiry_date(sym.get("expiry"))
            if exp_date and exp_date >= today_date:
                pe_by_stock.setdefault(base_sym, []).append((exp_date, sym))

    results = []
    end_time = now_ist.replace(tzinfo=None)
    start_time = end_time - timedelta(days=HIST_LOOKBACK_DAYS)

    for idx, stock in enumerate(fno_stocks, 1):
        print(f"Scanning {stock} ({idx}/{len(fno_stocks)})...", flush=True)
        if stock not in pe_by_stock: continue

        all_entries = pe_by_stock[stock]
        nearest_expiry = min(exp for exp, _ in all_entries)
        nearest_pe_contracts = [sym for exp, sym in all_entries if exp == nearest_expiry]

        spot_ltp = None
        if stock in eq_symbol_map:
            try:
                eq_q = ic.quotes(exchange=conn.EXCHANGE_TYPE_NSE, trading_symbol=eq_symbol_map[stock])
                if isinstance(eq_q, dict): spot_ltp = float(eq_q.get("ltp") or eq_q.get("lp") or 0)
            except Exception:
                spot_ltp = None

        target_put = get_second_highest_oi_put(ic, conn, stock, nearest_pe_contracts, spot_ltp)
        if not target_put: continue

        option_tsym = target_put["trading_symbol"]

        try:
            hist_gen = ic.historical_data(
                exchange=conn.EXCHANGE_TYPE_NFO,
                trading_symbol=option_tsym,
                timeframe=conn.TIMEFRAME_TYPE_MIN,
                start=start_time,
                end=end_time,
            )
            df_1m = parse_historical_to_df(hist_gen)
            if df_1m.empty: continue

            df_77m = resample_1m_to_custom_tf(df_1m, now_ist, TF_MINUTES)
            
            min_bars_needed = max(STOCH_K + STOCH_D, LL_PERIOD) + 2
            if len(df_77m) < min_bars_needed: continue

            df_77m["Stoch_D"] = calculate_stoch_d(df_77m, STOCH_K, STOCH_D)

            curr_close = float(df_77m["Close"].iloc[-1])
            minus_1_d = float(df_77m["Stoch_D"].iloc[-1])
            minus_2_d = float(df_77m["Stoch_D"].iloc[-2])
            minus_3_d = float(df_77m["Stoch_D"].iloc[-3])
            
            if pd.isna(minus_2_d) or pd.isna(minus_3_d): continue

            stoch_crossed_on_minus_2 = (minus_3_d >= STOCH_THRESHOLD and minus_2_d < STOCH_THRESHOLD) if STRICT_CROSSOVER else (minus_2_d < STOCH_THRESHOLD)
            
            lowest_low_34 = float(df_77m["Low"].iloc[-LL_PERIOD:].min())
            price_held_above = curr_close > lowest_low_34

            if stoch_crossed_on_minus_2 and price_held_above:
                minus_2_time_str = df_77m.index[-2].strftime("%d-%b %H:%M")
                print(f"  ✅ MATCH: {option_tsym} | %D Crossed at {minus_2_time_str} | Close {curr_close} > LL {lowest_low_34}")
                results.append({
                    "Stock": stock,
                    "Option (2nd OI)": option_tsym,
                    "Minus 2 Bar": minus_2_time_str,
                    "Minus 3 %D": round(minus_3_d, 1),
                    "Minus 2 %D": round(minus_2_d, 1),
                    "Live %D": round(minus_1_d, 1),
                    "34-Bar Low": round(lowest_low_34, 2),
                    "Live Close": round(curr_close, 2)
                })

        except Exception:
            continue

    if results:
        res_df = pd.DataFrame(results).sort_values(by="Minus 2 %D", ascending=True).reset_index(drop=True)
        print("\n🎯 Matches found! Sending email notification...")
        print(tabulate(res_df, headers="keys", tablefmt="psql", showindex=False))
        send_email_alert(res_df, now_ist_str)
    else:
        print("\nNo setups matched both %D < 31 on Minus 2 Bar and the 34-Bar price hold.")

if __name__ == "__main__":
    run_definedge_77m_scan()
