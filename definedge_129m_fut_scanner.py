import os
import sys
import json
import zipfile
import io
import smtplib
import pyotp
import requests
import pytz
import numpy as np
import pandas as pd
from datetime import datetime, timedelta, time as dtime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from tabulate import tabulate
from integrate import ConnectToIntegrate, IntegrateData

# ==============================================================================
# 1. CREDENTIALS & CONFIGURATION
# ==============================================================================
API_TOKEN = os.environ.get("DEFINEDGE_API_TOKEN", "7eb93aac-c746-44bd-9755-18ae6289fdfc").strip()
API_SECRET = os.environ.get("DEFINEDGE_API_SECRET", "snToBptj6e2X/c9c7POM8Q==").strip()
TOTP_SECRET = os.environ.get("DEFINEDGE_TOTP_SECRET", "IJGDEV2EJFUTIQTNHBYG2SZXJ5IXOMBR").strip()

SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "balanisuresh@gmail.com").strip()
RECEIVER_EMAIL = os.environ.get("RECEIVER_EMAIL", "balanisuresh@gmail.com").strip()
APP_PASSWORD = os.environ.get("APP_PASSWORD", "YOUR_GMAIL_APP_PASSWORD").strip()

IST = pytz.timezone("Asia/Kolkata")
MEMORY_FILE = "129m_memory.json"

TIMEFRAME_129M = 129
ATR_PERIOD_129M = 100
BODY_ATR_MULT = 0.67
CONSEC_BARS = 4
HIST_LOOKBACK_DAYS = 95

ST_PERIOD = 10
ST_MULTIPLIER = 2.0
LOOKBACK_DAYS_15M = 15

MAX_NEXT_TRADING_DAYS = 2
ALLOW_SAME_DAY_15M_TRIGGER = True

# Standard F&O Stock Futures Watchlist
fno_stocks = [
    "360ONE", "ABB", "ABBOTINDIA", "ABCAPITAL", "ABFRL", "ACC", "ADANIENT", "ADANIPORTS",
    "ALKEM", "AMBUJACEM", "ANGELONE", "APLAPOLLO", "APOLLOHOSP", "APOLLOTYRE", "ASHOKLEY",
    "ASIANPAINT", "ASTRAL", "ATUL", "AUBANK", "AUROPHARMA", "AXISBANK", "BAJAJ-AUTO",
    "BAJAJFINSV", "BAJFINANCE", "BALKRISIND", "BALRAMCHIN", "BANDHANBNK", "BANKBARODA",
    "BATAINDIA", "BEL", "BERGEPAINT", "BHARTIARTL", "BIOCON", "BOSCHLTD", "BPCL",
    "BRITANNIA", "BSOFT", "CAMS", "CANBK", "CANFINHOME", "CHAMBLFERT", "CHOLAFIN",
    "CIPLA", "COALINDIA", "COFORGE", "COLPAL", "CONCOR", "COROMANDEL", "CROMPTON",
    "CUB", "CUMMINSIND", "DABUR", "DALBHARAT", "DEEPAKNTR", "DELHIVERY", "DIVISLAB",
    "DIXON", "DLF", "DRREDDY", "EICHERMOT", "ESCORTS", "EXIDEIND", "FEDERALBNK",
    "GAIL", "GLENMARK", "GMRAIRPORT", "GNFC", "GODREJCP", "GODREJPROP", "GRASIM",
    "GUJGASLTD", "HAL", "HAVELLS", "HCLTECH", "HDFCAMC", "HDFCBANK", "HDFCLIFE",
    "HEROMOTOCO", "HINDALCO", "HINDCOPPER", "HINDPETRO", "HINDUNILVR", "ICICIBANK",
    "ICICIGI", "ICICIPRULI", "IDEA", "IDFCFIRSTB", "IEX", "IGL", "INDHOTEL",
    "INDIACEM", "INDIAMART", "INDUSINDBK", "INDUSTOWER", "INFY", "IOC", "IPCALAB",
    "ITC", "JINDALSTEL", "JKCEMENT", "JSWSTEEL", "JUBLFOOD", "KOTAKBANK", "LALPATHLAB",
    "LAURUSLABS", "LICHSGFIN", "LICI", "LTIM", "LTTS", "LUPIN", "M&M", "M&MFIN",
    "MANAPPURAM", "MARICO", "MARUTI", "MCX", "METROPOLIS", "MFSL", "MGL", "MOTHERSON",
    "MPHASIS", "MRF", "MUTHOOTFIN", "NAUKRI", "NBCC", "NESTLEIND", "NMDC", "NTPC",
    "OBEROIRLTY", "OFSS", "ONGC", "PAGEIND", "PEL", "PERSISTENT", "PETRONET", "PFC",
    "PIDILITIND", "PIIND", "PNB", "POLYCAB", "POWERGRID", "PVRINOX", "RAMCOCEM",
    "RBLBANK", "RECLTD", "RELIANCE", "SBICARD", "SBILIFE", "SBIN", "SHREECEM",
    "SHRIRAMFIN", "SIEMENS", "SRF", "SUNPHARMA", "SUNTV", "SYNGENE", "TATACHEM",
    "TATACOMM", "TATACONSUM", "TATAMOTORS", "TATAPOWER", "TATASTEEL", "TCS", "TECHM",
    "TITAN", "TORNTPHARM", "TRENT", "TVSMOTOR", "UPL", "VEDL", "VOLTAS", "WIPRO",
    "ZEEL", "ZYDUSLIFE"
]

# ==============================================================================
# 2. PERSISTENT MEMORY MANAGEMENT
# ==============================================================================
def load_memory():
    if not os.path.exists(MEMORY_FILE):
        return {"last_harvested_129m_bar": "", "stocks": {}}
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if "stocks" not in data:
                data = {"last_harvested_129m_bar": "", "stocks": {}}
            return data
    except Exception as e:
        print(f"⚠️ Could not read {MEMORY_FILE}, starting fresh: {e}")
        return {"last_harvested_129m_bar": "", "stocks": {}}

def save_memory(memory_data):
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(memory_data, f, indent=2, sort_keys=True)
    print(f"💾 Memory saved to {MEMORY_FILE} ({len(memory_data.get('stocks', {}))} active stocks).")

# ==============================================================================
# 3. DEFINEDGE LOGIN & MASTER SYMBOL FETCH
# ==============================================================================
def login_definedge():
    conn = ConnectToIntegrate()
    totp = pyotp.TOTP(TOTP_SECRET).now()
    conn.login(api_token=API_TOKEN, api_secret=API_SECRET, totp=totp)
    return conn, IntegrateData(conn)

def parse_expiry_date(val):
    if pd.isna(val):
        return None
    s = str(val).strip()
    for fmt in ("%d%m%Y", "%Y-%m-%d", "%d-%b-%Y", "%d%b%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None

def get_current_month_nfo_futures(conn=None):
    today = datetime.now(IST).date()
    records = []

    if conn is not None and hasattr(conn, "symbols") and conn.symbols:
        for sym in conn.symbols:
            if sym.get("segment") == "NFO" and sym.get("instrument_type") == "FUTSTK":
                exp_date = parse_expiry_date(sym.get("expiry"))
                if exp_date and exp_date >= today:
                    records.append({
                        "underlying": str(sym.get("symbol", "")).strip(),
                        "trading_symbol": str(sym.get("trading_symbol", "")).strip(),
                        "token": str(sym.get("token", "")).strip(),
                        "expiry": exp_date
                    })

    if not records:
        url = "https://app.definedgesecurities.com/public/allmaster.zip"
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()

        with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
            csv_name = z.namelist()[0]
            with z.open(csv_name) as f:
                df = pd.read_csv(f, header=None, dtype=str, low_memory=False)

        nfo = df[(df[0] == "NFO") & (df[4] == "FUTSTK")].copy()
        for exp_col in [5, 8, 6, 7]:
            if exp_col in nfo.columns:
                parsed = pd.to_datetime(nfo[exp_col], format="%d%m%Y", errors="coerce")
                if parsed.notna().sum() > 0:
                    nfo["expiry"] = parsed.dt.date
                    break

        nfo = nfo[nfo["expiry"].notna() & (nfo["expiry"] >= today)]
        for _, row in nfo.iterrows():
            records.append({
                "underlying": str(row[2]).strip(),
                "trading_symbol": str(row[3]).strip(),
                "token": str(row[1]).strip(),
                "expiry": row["expiry"]
            })

    if not records:
        return []

    df_fut = pd.DataFrame(records)
    df_fut = df_fut.sort_values("expiry").groupby("underlying", as_index=False).first()
    df_fut = df_fut.sort_values("underlying").reset_index(drop=True)
    return df_fut.to_dict("records")

def fetch_1m_df(conn, ic, trading_symbol, start_dt, end_dt):
    hist = ic.historical_data(
        exchange=conn.EXCHANGE_TYPE_NFO,
        trading_symbol=trading_symbol,
        timeframe=conn.TIMEFRAME_TYPE_MIN,
        start=start_dt,
        end=end_dt
    )
    df = pd.DataFrame(list(hist))
    if df.empty:
        return pd.DataFrame()

    df["datetime"] = pd.to_datetime(df["datetime"])
    if df["datetime"].dt.tz is None:
        df["datetime"] = df["datetime"].dt.tz_localize(IST)
    else:
        df["datetime"] = df["datetime"].dt.tz_convert(IST)

    df = df.set_index("datetime").sort_index()
    for col in ["open", "high", "low", "close", "volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df

# ==============================================================================
# 4. EXACT ORIGINAL ATR(100) & 129M 4-BAR COMPRESSION LOGIC
# ==============================================================================
BAR_CLOSURE_TIMES_129M = [
    (dtime(9, 15), dtime(11, 24)),
    (dtime(11, 24), dtime(13, 33)),
    (dtime(13, 33), dtime(15, 40)),
]

def get_latest_completed_129m_start(now_ist):
    current_t = now_ist.time()
    completed_start = None
    for start_t, end_t in BAR_CLOSURE_TIMES_129M:
        if current_t >= end_t:
            completed_start = start_t
    return completed_start

def resample_to_129m(df_1m, now_ist):
    df = df_1m.copy().between_time("09:15", "15:40")
    if df.empty:
        return pd.DataFrame()

    resampled_chunks = []
    for _, group in df.groupby(df.index.date):
        bars = group.resample(
            f"{TIMEFRAME_129M}min",
            origin="start_day",
            offset="9h15min",
            label="left",
            closed="left"
        ).agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum"
        }).dropna(subset=["open", "close"])

        bars = bars[bars.index.time <= dtime(13, 33)]
        resampled_chunks.append(bars)

    if not resampled_chunks:
        return pd.DataFrame()

    df_129m = pd.concat(resampled_chunks).sort_index()
    today_date = now_ist.date()
    latest_completed_start = get_latest_completed_129m_start(now_ist)

    if (df_129m.index.date == today_date).any():
        if latest_completed_start is None:
            df_129m = df_129m[df_129m.index.date < today_date]
        else:
            cutoff_dt = IST.localize(datetime.combine(today_date, latest_completed_start))
            df_129m = df_129m[df_129m.index <= cutoff_dt]

    return df_129m

def calculate_atr(df, period=100):
    high = df["high"]
    low = df["low"]
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(window=period, min_periods=period).mean()

def evaluate_4bar_compression(df_129m):
    if len(df_129m) < ATR_PERIOD_129M + CONSEC_BARS + 2:
        return None

    df = df_129m.copy()
    df["body"] = (df["close"] - df["open"]).abs()
    df["atr"] = calculate_atr(df, ATR_PERIOD_129M)

    last_bar = df.iloc[-1]
    ref_atr = last_bar["atr"]
    if pd.isna(ref_atr) or ref_atr <= 0:
        return None

    last4 = df.iloc[-CONSEC_BARS:]
    max_allowed_body = BODY_ATR_MULT * ref_atr
    if not (last4["body"] < max_allowed_body).all():
        return None

    closes = df["close"].iloc[-(CONSEC_BARS + 1):].values
    is_bull_setup = all(closes[i] < closes[i - 1] for i in range(1, CONSEC_BARS + 1))
    is_bear_setup = all(closes[i] > closes[i - 1] for i in range(1, CONSEC_BARS + 1))

    if not (is_bull_setup or is_bear_setup):
        return None

    live_body = float(last_bar["body"])
    max_4b_body = float(last4["body"].max())
    ratio = round(float(ref_atr) / live_body, 2) if live_body > 0 else 999.0

    prev_bar = df.iloc[-(CONSEC_BARS + 1)]
    roc_pct = ((last_bar["close"] - prev_bar["close"]) / prev_bar["close"]) * 100.0

    bar_start_dt = last4.index[-1]
    if bar_start_dt.time() == dtime(13, 33):
        bar_close_dt = bar_start_dt + timedelta(minutes=127)
    else:
        bar_close_dt = bar_start_dt + timedelta(minutes=TIMEFRAME_129M)

    return {
        "signal": "Bull Setup 🟢" if is_bull_setup else "Bear Setup 🔴",
        "group": "BUY" if is_bull_setup else "SELL",
        "bar_time": bar_start_dt.strftime("%d-%b %H:%M"),
        "comp_bar_close_iso": bar_close_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "last_checked_15m_iso": "",
        "added_trade_date": bar_start_dt.strftime("%Y-%m-%d"),
        "close": round(float(last_bar["close"]), 2),
        "atr": round(float(ref_atr), 2),
        "max_body": round(max_4b_body, 2),
        "live_body": round(live_body, 2),
        "body_atr_ratio": ratio,
        "roc_pct": round(float(roc_pct), 2)
    }

# ==============================================================================
# 5. 15-MINUTE SUPERTREND (10, 2) SNIPER
# ==============================================================================
def resample_to_15m(df_1m, now_ist):
    df = df_1m.copy().between_time("09:15", "15:30")
    if df.empty:
        return pd.DataFrame()

    resampled_chunks = []
    for _, group in df.groupby(df.index.date):
        bars = group.resample(
            "15min",
            origin="start_day",
            offset="9h15min",
            label="left",
            closed="left"
        ).agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum"
        }).dropna(subset=["open", "close"])

        bars = bars[bars.index.time <= dtime(15, 15)]
        resampled_chunks.append(bars)

    if not resampled_chunks:
        return pd.DataFrame()

    df_15m = pd.concat(resampled_chunks).sort_index()
    today_date = now_ist.date()
    if (df_15m.index.date == today_date).any():
        completed_mask = [
            (ts.date() < today_date) or (now_ist >= ts + timedelta(minutes=15))
            for ts in df_15m.index
        ]
        df_15m = df_15m[completed_mask]

    return df_15m

def calculate_supertrend_15m(df_15m, period=10, multiplier=2.0):
    df = df_15m.copy()
    df["atr"] = calculate_atr(df, period)
    hl2 = (df["high"] + df["low"]) / 2.0

    basic_ub = (hl2 + multiplier * df["atr"]).values
    basic_lb = (hl2 - multiplier * df["atr"]).values
    close = df["close"].values

    n = len(df)
    final_ub = np.zeros(n)
    final_lb = np.zeros(n)
    st_dir = np.ones(n, dtype=int)
    st_val = np.zeros(n)

    for i in range(n):
        if i == 0 or np.isnan(basic_ub[i]):
            final_ub[i] = basic_ub[i]
            final_lb[i] = basic_lb[i]
            st_dir[i] = 1
            st_val[i] = final_lb[i]
            continue

        if np.isnan(final_ub[i - 1]):
            final_ub[i] = basic_ub[i]
            final_lb[i] = basic_lb[i]
            st_dir[i] = 1
            st_val[i] = final_lb[i]
            continue

        if basic_ub[i] < final_ub[i - 1] or close[i - 1] > final_ub[i - 1]:
            final_ub[i] = basic_ub[i]
        else:
            final_ub[i] = final_ub[i - 1]

        if basic_lb[i] > final_lb[i - 1] or close[i - 1] < final_lb[i - 1]:
            final_lb[i] = basic_lb[i]
        else:
            final_lb[i] = final_lb[i - 1]

        if st_dir[i - 1] == -1 and close[i] > final_ub[i - 1]:
            st_dir[i] = 1
        elif st_dir[i - 1] == 1 and close[i] < final_lb[i - 1]:
            st_dir[i] = -1
        else:
            st_dir[i] = st_dir[i - 1]

        st_val[i] = final_lb[i] if st_dir[i] == 1 else final_ub[i]

    df["st_dir"] = st_dir
    df["st_val"] = st_val
    return df

def send_15m_st_email_alert(triggered_list, active_memory_count):
    now_str = datetime.now(IST).strftime("%d-%b %H:%M:%S")
    subject = f"🚀 15m ST(10,2) Trigger on 129m Compression ({len(triggered_list)} Matches) - ({now_str})"

    buy_matches = sorted([m for m in triggered_list if m["group"] == "BUY"], key=lambda x: x["body_atr_ratio"], reverse=True)
    sell_matches = sorted([m for m in triggered_list if m["group"] == "SELL"], key=lambda x: x["body_atr_ratio"], reverse=True)

    buy_top5 = ", ".join([m["stock"] for m in buy_matches[:5]]) or "None"
    sell_top5 = ", ".join([m["stock"] for m in sell_matches[:5]]) or "None"
    buy_all = ", ".join([m["stock"] for m in buy_matches]) or "None"
    sell_all = ", ".join([m["stock"] for m in sell_matches]) or "None"

    body_lines = [
        f"129m (4-Bar Compression) + 15m SuperTrend (10, 2) Breakout Alert at {now_str}",
        f"Remaining Stocks Still Watched in 2-Day Memory: {active_memory_count}\n",
        f"📋 BUY GROUP - Top 5 (Copy & Paste into Zone):\n{buy_top5}\n",
        f"📋 SELL GROUP - Top 5 (Copy & Paste into Zone):\n{sell_top5}\n",
        f"All BUY ({len(buy_matches)}): {buy_all}",
        f"All SELL ({len(sell_matches)}): {sell_all}\n"
    ]

    table_rows = [
        [
            m["stock"], m["signal"], m["bar_time"], m["st_bar_time"],
            m["atr"], m["max_body"], m["live_15m_close"], m["st_level"], m["body_atr_ratio"]
        ]
        for m in (buy_matches + sell_matches)
    ]
    headers = [
        "Stock", "Setup", "Bar Open", "15m ST Bar",
        "ATR(100)", "Max 4B Body", "Live 15m", "ST(10,2)", "Ratio"
    ]
    body_lines.append(tabulate(table_rows, headers=headers, tablefmt="grid"))

    msg = MIMEMultipart()
    msg["From"] = SENDER_EMAIL
    msg["To"] = RECEIVER_EMAIL
    msg["Subject"] = subject
    msg.attach(MIMEText("\n".join(body_lines), "plain"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as server:
        server.login(SENDER_EMAIL, APP_PASSWORD)
        server.send_message(msg)

    print(f"✅ 15m SuperTrend Alert Email sent for {len(triggered_list)} triggered stock(s)!")

def run_scanner():
    now_ist = datetime.now(IST)
    current_t = now_ist.time()
    event_name = os.environ.get("GITHUB_EVENT_NAME", "workflow_dispatch")

    if event_name == "schedule" and (current_t < dtime(9, 20) or current_t > dtime(17, 30)):
        print(f"⏹️ Outside market scan window ({now_ist.strftime('%H:%M:%S IST')}). Exiting.")
        sys.exit(0)

    memory = load_memory()
    conn, ic = login_definedge()
    
    # Fetch current month NFO futures and filter strictly by your fno_stocks watchlist
    all_futures = get_current_month_nfo_futures(conn)
    stock_set = set(fno_stocks)
    valid_futures = [f for f in all_futures if f["underlying"] in stock_set]
    fut_map = {f["underlying"]: f["trading_symbol"] for f in valid_futures}

    if not valid_futures:
        print("⚠️ No NFO Stock Futures loaded from watchlist. Exiting.")
        sys.exit(1)

    latest_129m_start = get_latest_completed_129m_start(now_ist)
    if latest_129m_start is not None:
        expected_129m_label = f"{now_ist.strftime('%Y-%m-%d')} {latest_129m_start.strftime('%H:%M')}"
        target_bar_str = f"{now_ist.strftime('%d-%b')} {latest_129m_start.strftime('%H:%M')}"
    else:
        expected_129m_label = "PREV_DAY"
        target_bar_str = None

    should_harvest = (
        (latest_129m_start is not None and memory.get("last_harvested_129m_bar") != expected_129m_label)
        or event_name == "workflow_dispatch"
    )

    if should_harvest:
        if target_bar_str:
            stale_same_bar = [
                s for s, inf in memory.get("stocks", {}).items()
                if inf.get("bar_time") == target_bar_str
            ]
            for s in stale_same_bar:
                memory["stocks"].pop(s, None)

        print(f"\n🌾 Running 129m 4-Bar Compression Harvester (Target Bar: {expected_129m_label})...")
        start_dt_129m = (now_ist - timedelta(days=HIST_LOOKBACK_DAYS)).replace(hour=9, minute=15, second=0, microsecond=0)
        new_added = 0
        actual_bar_label = memory.get("last_harvested_129m_bar", "")

        for idx, fut in enumerate(valid_futures, 1):
            symbol = fut["underlying"]
            trd_sym = fut["trading_symbol"]
            try:
                df_1m = fetch_1m_df(conn, ic, trd_sym, start_dt_129m, now_ist)
                if df_1m.empty:
                    continue

                df_129m = resample_to_129m(df_1m, now_ist)
                if df_129m.empty:
                    continue

                actual_bar_label = df_129m.index[-1].strftime("%Y-%m-%d %H:%M")
                res = evaluate_4bar_compression(df_129m)
                if res:
                    res["stock"] = symbol
                    res["trading_symbol"] = trd_sym
                    memory["stocks"][symbol] = res
                    new_added += 1
                    print(f"  ➕ Added/Updated in 129m memory: {symbol} ({res['signal']}) on bar {res['bar_time']} | Ratio: {res['body_atr_ratio']}")
            except Exception as e:
                print(f"⚠️ Error harvesting {symbol}: {e}")

        if actual_bar_label:
            memory["last_harvested_129m_bar"] = actual_bar_label
        print(f"🌾 129m Harvest complete: {new_added} stock(s) shortlisted on bar [{actual_bar_label}].")

    active_stocks = memory.get("stocks", {})
    if not active_stocks:
        print("📭 129m Memory is currently empty. Saving & exiting.")
        save_memory(memory)
        return

    print(f"\n🎯 Running 15m SuperTrend(10, 2) Sniper on {len(active_stocks)} stock(s) in 129m memory...")
    start_dt_15m = (now_ist - timedelta(days=LOOKBACK_DAYS_15M)).replace(hour=9, minute=15, second=0, microsecond=0)

    triggered_alerts = []
    stocks_to_remove = []

    for symbol, info in list(active_stocks.items()):
        trd_sym = fut_map.get(symbol, info.get("trading_symbol"))
        if not trd_sym:
            stocks_to_remove.append(symbol)
            continue

        try:
            df_1m = fetch_1m_df(conn, ic, trd_sym, start_dt_15m, now_ist)
            if df_1m.empty:
                continue

            added_date = datetime.strptime(info["added_trade_date"], "%Y-%m-%d").date()
            all_trade_dates = sorted(list(set(df_1m.index.date)))
            subsequent_trade_days = [d for d in all_trade_dates if d > added_date]

            if len(subsequent_trade_days) > MAX_NEXT_TRADING_DAYS:
                stocks_to_remove.append(symbol)
                continue

            df_15m = resample_to_15m(df_1m, now_ist)
            if len(df_15m) < ST_PERIOD + 3:
                continue

            df_st = calculate_supertrend_15m(df_15m, period=ST_PERIOD, multiplier=ST_MULTIPLIER)

            comp_close_dt = IST.localize(datetime.strptime(info["comp_bar_close_iso"], "%Y-%m-%d %H:%M:%S"))
            last_checked_iso = info.get("last_checked_15m_iso", "")
            last_checked_dt = (
                IST.localize(datetime.strptime(last_checked_iso, "%Y-%m-%d %H:%M:%S"))
                if last_checked_iso else None
            )

            triggered_on_bar = None
            for idx_pos in range(1, len(df_st)):
                cur_bar = df_st.iloc[idx_pos]
                prev_bar = df_st.iloc[idx_pos - 1]
                bar_ts = cur_bar.name

                if bar_ts < comp_close_dt:
                    continue
                if not ALLOW_SAME_DAY_15M_TRIGGER and bar_ts.date() <= added_date:
                    continue
                if last_checked_dt is not None and bar_ts <= last_checked_dt:
                    continue

                is_buy_flip = (info["group"] == "BUY") and (prev_bar["st_dir"] == -1 and cur_bar["st_dir"] == 1)
                is_sell_flip = (info["group"] == "SELL") and (prev_bar["st_dir"] == 1 and cur_bar["st_dir"] == -1)

                if is_buy_flip or is_sell_flip:
                    triggered_on_bar = cur_bar
                    break

            latest_15m_bar = df_st.iloc[-1]
            if latest_15m_bar.name >= comp_close_dt:
                info["last_checked_15m_iso"] = latest_15m_bar.name.strftime("%Y-%m-%d %H:%M:%S")

            if triggered_on_bar is not None:
                alert_item = dict(info)
                alert_item["st_bar_time"] = triggered_on_bar.name.strftime("%d-%b %H:%M")
                alert_item["live_15m_close"] = round(float(triggered_on_bar["close"]), 2)
                alert_item["st_level"] = round(float(triggered_on_bar["st_val"]), 2)
                triggered_alerts.append(alert_item)
                stocks_to_remove.append(symbol)
            else:
                st_state = "GREEN" if latest_15m_bar["st_dir"] == 1 else "RED"
                print(f"  ⏳ Watching {symbol} ({info['group']} | Added {info['bar_time']} | Day +{len(subsequent_trade_days)}) -> 15m ST is {st_state}")

        except Exception as e:
            print(f"⚠️ Error checking 15m ST for {symbol}: {e}")

    for sym in set(stocks_to_remove):
        memory["stocks"].pop(sym, None)

    save_memory(memory)

    if triggered_alerts:
        send_15m_st_email_alert(triggered_alerts, len(memory["stocks"]))
    else:
        print("ℹ️ No 15m SuperTrend (10,2) flips on 129m memory stocks on this bar. No email sent.")

if __name__ == "__main__":
    run_scanner()
