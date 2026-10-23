import os
import sys
import time
import json
import zipfile
import io
import smtplib
import subprocess
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
# 1. CREDENTIALS & CONFIGURATION (LOADED SECURELY FROM GITHUB SECRETS)
# ==============================================================================
API_TOKEN = os.environ.get("DEFINEDGE_API_TOKEN", "").strip()
API_SECRET = os.environ.get("DEFINEDGE_API_SECRET", "").strip()
TOTP_SECRET = os.environ.get("DEFINEDGE_TOTP_SECRET", "").strip()

SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "balanisuresh@gmail.com").strip()
RECEIVER_EMAIL = os.environ.get("RECEIVER_EMAIL", "balanisuresh@gmail.com").strip()
APP_PASSWORD = os.environ.get("APP_PASSWORD", "").strip()

IST = pytz.timezone("Asia/Kolkata")
MEMORY_FILE = "daily_memory.json"
MEMORY_BRANCH = "daily-memory-state"

ATR_PERIOD_DAILY = 100
BODY_ATR_MULT = 0.67
CONSEC_BARS = 3
HIST_LOOKBACK_DAYS_1M = 75
HIST_LOOKBACK_DAYS_EOD = 220

ST_PERIOD = 10
ST_MULTIPLIER = 2.0
LOOKBACK_DAYS_15M = 30

MAX_NEXT_TRADING_DAYS = 2
ALLOW_SAME_DAY_15M_TRIGGER = True

fno_stocks = [
    "360ONE", "ABB", "ABBOTINDIA", "ABCAPITAL", "ABFRL", "ACC", "ADANIENSOL", "ADANIENT",
    "ADANIGREEN", "ADANIPORTS", "ALKEM", "AMBER", "AMBUJACEM", "ANGELONE", "APLAPOLLO",
    "APOLLOHOSP", "APOLLOTYRE", "ASHOKLEY", "ASIANPAINT", "ASTRAL", "ATGL", "ATUL",
    "AUBANK", "AUROPHARMA", "AXISBANK", "BAJAJ-AUTO", "BAJAJFINSV", "BAJFINANCE",
    "BALKRISIND", "BALRAMCHIN", "BANDHANBNK", "BANKBARODA", "BANKINDIA", "BATAINDIA",
    "BDL", "BEL", "BERGEPAINT", "BHARATFORG", "BHARTIARTL", "BHEL", "BIOCON", "BOSCHLTD",
    "BPCL", "BRITANNIA", "BSE", "BSOFT", "CAMS", "CANBK", "CANFINHOME", "CDSL", "CESC",
    "CGPOWER", "CHAMBLFERT", "CHOLAFIN", "CIPLA", "COALINDIA", "COCHINSHIP", "COFORGE",
    "COLPAL", "CONCOR", "COROMANDEL", "CROMPTON", "CUB", "CUMMINSIND", "CYIENT", "DABUR",
    "DALBHARAT", "DEEPAKNTR", "DELHIVERY", "DIVISLAB", "DIXON", "DLF", "DMART", "DRREDDY",
    "EICHERMOT", "ESCORTS", "EXIDEIND", "FEDERALBNK", "FORTIS", "GAIL", "GLENMARK",
    "GMRAIRPORT", "GNFC", "GODREJCP", "GODREJPROP", "GRANULES", "GRASIM", "GUJGASLTD",
    "HAL", "HAVELLS", "HCLTECH", "HDFCAMC", "HDFCBANK", "HDFCLIFE", "HEROMOTOCO",
    "HFCL", "HINDALCO", "HINDCOPPER", "HINDPETRO", "HINDUNILVR", "HUDCO", "ICICIBANK",
    "ICICIGI", "ICICIPRULI", "IDEA", "IDFCFIRSTB", "IEX", "IGL", "IIFL", "INDHOTEL",
    "INDIACEM", "INDIAMART", "INDIANB", "INDIGO", "INDUSINDBK", "INDUSTOWER", "INFY",
    "INOXWIND", "IOC", "IPCALAB", "IRB", "IRCTC", "IREDA", "IRFC", "ITC", "JINDALSTEL",
    "JIOFIN", "JKCEMENT", "JSL", "JSWENERGY", "JSWSTEEL", "JUBLFOOD", "KALYANKJIL",
    "KAYNES", "KEI", "KFINTECH", "KOTAKBANK", "KPITTECH", "LALPATHLAB", "LAURUSLABS",
    "LICHSGFIN", "LICI", "LODHA", "LT", "LTF", "LTIM", "LTTS", "LUPIN", "M&M", "M&MFIN",
    "MANAPPURAM", "MANKIND", "MARICO", "MARUTI", "MAXHEALTH", "MAZDOCK", "MCX",
    "METROPOLIS", "MFSL", "MGL", "MOTHERSON", "MPHASIS", "MRF", "MUTHOOTFIN",
    "NATIONALUM", "NAUKRI", "NAVINFLUOR", "NBCC", "NCC", "NESTLEIND", "NHPC", "NMDC",
    "NTPC", "NYKAA", "OBEROIRLTY", "OFSS", "OIL", "ONGC", "PAGEIND", "PATANJALI",
    "PAYTM", "PEL", "PERSISTENT", "PETRONET", "PFC", "PHOENIXLTD", "PIDILITIND", "PIIND",
    "PNB", "PNBHOUSING", "POLICYBZR", "POLYCAB", "POONAWALLA", "POWERGRID", "PPLPHARMA",
    "PRESTIGE", "PVRINOX", "RAMCOCEM", "RBLBANK", "RECLTD", "RELIANCE", "RVNL", "SAIL",
    "SBICARD", "SBILIFE", "SBIN", "SHREECEM", "SHRIRAMFIN", "SIEMENS", "SJVN",
    "SOLARINDS", "SONACOMS", "SRF", "SUNPHARMA", "SUNTV", "SUPREMEIND", "SYNGENE",
    "TATACHEM", "TATACOMM", "TATACONSUM", "TATAELXSI", "TATAMOTORS", "TATAPOWER",
    "TATASTEEL", "TATATECH", "TCS", "TECHM", "TIINDIA", "TITAGARH", "TITAN",
    "TORNTPHARM", "TORNTPOWER", "TRENT", "TVSMOTOR", "ULTRACEMCO", "UNIONBANK",
    "UNITDSPR", "UPL", "VBL", "VEDL", "VOLTAS", "WIPRO", "YESBANK", "ZEEL", "ZOMATO",
    "ZYDUSLIFE"
]

# ==============================================================================
# 2. PERSISTENT MEMORY MANAGEMENT (REAL-TIME SYNC TO daily-memory-state BRANCH)
# ==============================================================================
def load_memory():
    if not os.path.exists(MEMORY_FILE):
        return {"last_harvested_daily_bar": "", "stocks": {}}
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if "stocks" not in data:
                data = {"last_harvested_daily_bar": "", "stocks": {}}
            return data
    except Exception as e:
        print(f"⚠️ Could not read {MEMORY_FILE}, starting fresh: {e}")
        return {"last_harvested_daily_bar": "", "stocks": {}}

def push_memory_to_git():
    """Immediately persists daily_memory.json to daily-memory-state without touching main."""
    if not os.environ.get("GITHUB_ACTIONS"):
        return
    try:
        cmds = [
            f"cp {MEMORY_FILE} /tmp/{MEMORY_FILE}_backup.json",
            'git config user.name "github-actions[bot]"',
            'git config user.email "github-actions[bot]@users.noreply.github.com"',
            f"git checkout -B {MEMORY_BRANCH}",
            f"cp /tmp/{MEMORY_FILE}_backup.json {MEMORY_FILE}",
            f"git add {MEMORY_FILE}",
            f'git commit -m "Update {MEMORY_FILE}" || true',
            f"git push -f origin {MEMORY_BRANCH}",
            "git checkout -f main",
            f"cp /tmp/{MEMORY_FILE}_backup.json {MEMORY_FILE}"
        ]
        subprocess.run(" && ".join(cmds), shell=True, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        print(f"⚠️ Git memory sync warning: {e}")

def save_memory(memory_data):
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(memory_data, f, indent=2, sort_keys=True)
    print(f"💾 Memory saved to {MEMORY_FILE} ({len(memory_data.get('stocks', {}))} active stocks).")
    push_memory_to_git()

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
    eq_map = {}

    if conn is not None and hasattr(conn, "symbols") and conn.symbols:
        for sym in conn.symbols:
            seg = sym.get("segment")
            inst = sym.get("instrument_type")
            und = str(sym.get("symbol", "")).strip()
            if seg == "NSE" and inst == "EQ":
                eq_map[und] = str(sym.get("trading_symbol", "")).strip()
            elif seg == "NFO" and inst == "FUTSTK":
                exp_date = parse_expiry_date(sym.get("expiry"))
                if exp_date and exp_date >= today:
                    records.append({
                        "underlying": und,
                        "trading_symbol": str(sym.get("trading_symbol", "")).strip(),
                        "token": str(sym.get("token", "")).strip(),
                        "expiry": exp_date
                    })

    if not records or not eq_map:
        url = "https://app.definedgesecurities.com/public/allmaster.zip"
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()

        with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
            csv_name = z.namelist()[0]
            with z.open(csv_name) as f:
                df = pd.read_csv(f, header=None, dtype=str, low_memory=False)

        eq_df = df[(df[0] == "NSE") & (df[4] == "EQ")]
        for _, row in eq_df.iterrows():
            eq_map[str(row[2]).strip()] = str(row[3]).strip()

        if not records:
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
    fut_list = df_fut.to_dict("records")
    for f in fut_list:
        f["eq_trading_symbol"] = eq_map.get(f["underlying"], f["underlying"])
    return fut_list

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

def fetch_eod_df(conn, ic, exchange, trading_symbol, start_dt, end_dt):
    hist = ic.historical_data(
        exchange=exchange,
        trading_symbol=trading_symbol,
        timeframe=conn.TIMEFRAME_TYPE_DAY,
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
# 4. DAILY (09:15 - 15:40 CAS CLOSE) ATR(100) & 3-BAR COMPRESSION LOGIC
# ==============================================================================
DAILY_OPEN_TIME = dtime(9, 15)
DAILY_CAS_CLOSE_TIME = dtime(15, 40)

def get_latest_completed_daily_start(now_ist):
    if now_ist.time() >= DAILY_CAS_CLOSE_TIME:
        return DAILY_OPEN_TIME
    return None

def build_daily_cas_df(df_1m, df_eod_backfill, now_ist):
    """
    Resamples NFO 1m bars (09:15 to 15:40 CAS close) into Daily bars and
    backfills older trading days prior to the NFO contract start so ATR(100)
    always has 100+ completed Daily bars.
    """
    df = df_1m.copy().between_time("09:15", "15:40")
    if df.empty:
        return pd.DataFrame()

    daily_rows = []
    for trade_date, group in df.groupby(df.index.date):
        bar_dt = IST.localize(datetime.combine(trade_date, DAILY_OPEN_TIME))
        daily_rows.append({
            "datetime": bar_dt,
            "open": float(group["open"].iloc[0]),
            "high": float(group["high"].max()),
            "low": float(group["low"].min()),
            "close": float(group["close"].iloc[-1]),
            "volume": float(group["volume"].sum())
        })

    df_daily_nfo = pd.DataFrame(daily_rows).set_index("datetime").sort_index()

    if df_eod_backfill is not None and not df_eod_backfill.empty:
        first_nfo_date = df_daily_nfo.index[0].date()
        older = df_eod_backfill[df_eod_backfill.index.date < first_nfo_date].copy()
        if not older.empty:
            older_rows = []
            for trade_date, group in older.groupby(older.index.date):
                bar_dt = IST.localize(datetime.combine(trade_date, DAILY_OPEN_TIME))
                older_rows.append({
                    "datetime": bar_dt,
                    "open": float(group["open"].iloc[0]),
                    "high": float(group["high"].max()),
                    "low": float(group["low"].min()),
                    "close": float(group["close"].iloc[-1]),
                    "volume": float(group["volume"].sum())
                })
            df_older = pd.DataFrame(older_rows).set_index("datetime").sort_index()
            df_daily_nfo = pd.concat([df_older, df_daily_nfo]).sort_index()

    today_date = now_ist.date()
    latest_completed_start = get_latest_completed_daily_start(now_ist)

    if (df_daily_nfo.index.date == today_date).any():
        if latest_completed_start is None:
            df_daily_nfo = df_daily_nfo[df_daily_nfo.index.date < today_date]
        else:
            cutoff_dt = IST.localize(datetime.combine(today_date, latest_completed_start))
            df_daily_nfo = df_daily_nfo[df_daily_nfo.index <= cutoff_dt]

    return df_daily_nfo

def calculate_atr_sma(df, period=100):
    """Simple Moving Average ATR(100) used by the Daily 3-Bar Compression scanner."""
    high = df["high"]
    low = df["low"]
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)
    min_p = min(period, max(20, len(df) - CONSEC_BARS - 1))
    return tr.rolling(window=period, min_periods=min_p).mean()

def calculate_atr_wilder(df, period=10):
    """Wilder's RMA ATR used by standard Definedge / TradingView SuperTrend(10, 2)."""
    high = df["high"]
    low = df["low"]
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()

def evaluate_3bar_compression(df_daily):
    if len(df_daily) < CONSEC_BARS + 2:
        return None

    df = df_daily.copy()
    df["body"] = (df["close"] - df["open"]).abs()
    df["atr"] = calculate_atr_sma(df, ATR_PERIOD_DAILY)

    last_bar = df.iloc[-1]
    ref_atr = last_bar["atr"]
    if pd.isna(ref_atr) or ref_atr <= 0:
        return None

    last3 = df.iloc[-CONSEC_BARS:]
    max_allowed_body = BODY_ATR_MULT * ref_atr
    if not (last3["body"] < max_allowed_body).all():
        return None

    closes = df["close"].iloc[-(CONSEC_BARS + 1):].values
    is_bull_setup = all(closes[i] < closes[i - 1] for i in range(1, CONSEC_BARS + 1))
    is_bear_setup = all(closes[i] > closes[i - 1] for i in range(1, CONSEC_BARS + 1))

    if not (is_bull_setup or is_bear_setup):
        return None

    live_body = float(last_bar["body"])
    max_3b_body = float(last3["body"].max())
    ratio = round(float(ref_atr) / live_body, 2) if live_body > 0 else 999.0

    prev_bar = df.iloc[-(CONSEC_BARS + 1)]
    roc_pct = ((last_bar["close"] - prev_bar["close"]) / prev_bar["close"]) * 100.0

    bar_start_dt = last3.index[-1]
    bar_close_dt = bar_start_dt.replace(hour=15, minute=40, second=0)

    return {
        "signal": "Bull Setup 🟢" if is_bull_setup else "Bear Setup 🔴",
        "group": "BUY" if is_bull_setup else "SELL",
        "bar_time": bar_start_dt.strftime("%d-%b Daily"),
        "comp_bar_close_iso": bar_close_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "last_checked_15m_iso": "",
        "added_trade_date": bar_start_dt.strftime("%Y-%m-%d"),
        "close": round(float(last_bar["close"]), 2),
        "atr": round(float(ref_atr), 2),
        "max_body": round(max_3b_body, 2),
        "live_body": round(live_body, 2),
        "body_atr_ratio": ratio,
        "roc_pct": round(float(roc_pct), 2)
    }

# ==============================================================================
# 5. 15-MINUTE SUPERTREND (10, 2) SNIPER (WILDER ATR + CLOSED-BAR VERIFICATION)
# ==============================================================================
def resample_to_15m(df_1m, now_ist):
    df = df_1m.copy().between_time("09:15", "15:29")
    if df.empty:
        return pd.DataFrame()

    last_1m_ts = df.index[-1]
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
            (ts.date() < today_date)
            or (now_ist >= ts + timedelta(minutes=15) and last_1m_ts >= ts + timedelta(minutes=14))
            for ts in df_15m.index
        ]
        df_15m = df_15m[completed_mask]

    return df_15m

def calculate_supertrend_15m(df_15m, period=10, multiplier=2.0):
    df = df_15m.copy()
    df["atr"] = calculate_atr_wilder(df, period)
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
    subject = f"🚀 15m ST(10,2) Trigger on Daily 3B Compression ({len(triggered_list)} Matches) - ({now_str})"

    buy_matches = sorted([m for m in triggered_list if m["group"] == "BUY"], key=lambda x: x["body_atr_ratio"], reverse=True)
    sell_matches = sorted([m for m in triggered_list if m["group"] == "SELL"], key=lambda x: x["body_atr_ratio"], reverse=True)

    buy_top5 = ", ".join([m["stock"] for m in buy_matches[:5]]) or "None"
    sell_top5 = ", ".join([m["stock"] for m in sell_matches[:5]]) or "None"
    buy_all = ", ".join([m["stock"] for m in buy_matches]) or "None"
    sell_all = ", ".join([m["stock"] for m in sell_matches]) or "None"

    body_lines = [
        f"Daily (3-Bar Compression) + 15m SuperTrend (10, 2) Breakout Alert at {now_str}",
        f"Remaining Stocks Still Watched in 2-Day Daily Memory: {active_memory_count}\n",
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
        "Stock", "Setup", "Daily Bar", "15m ST Bar",
        "ATR(100)", "Max 3B Body", "Live 15m", "ST(10,2)", "Ratio"
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

# ==============================================================================
# 6. MAIN RUNNER: DAILY HARVESTER + 15m SUPERTREND SNIPER
# ==============================================================================
def run_scanner(force_harvest=False):
    now_ist = datetime.now(IST)

    memory = load_memory()
    conn, ic = login_definedge()

    all_futures = get_current_month_nfo_futures(conn)
    stock_set = set(fno_stocks)
    valid_futures = [f for f in all_futures if f["underlying"] in stock_set]
    fut_map = {f["underlying"]: f["trading_symbol"] for f in valid_futures}

    if not valid_futures:
        print("⚠️ No NFO Stock Futures loaded from watchlist. Exiting.")
        return

    latest_daily_start = get_latest_completed_daily_start(now_ist)
    if latest_daily_start is not None:
        expected_daily_label = f"{now_ist.strftime('%Y-%m-%d')} {latest_daily_start.strftime('%H:%M')}"
    else:
        expected_daily_label = "PREV_DAY"

    should_harvest = (
        (latest_daily_start is not None and memory.get("last_harvested_daily_bar") != expected_daily_label)
        or not memory.get("stocks")
        or force_harvest
    )

    if should_harvest:
        print(f"\n🌾 Running Daily 3-Bar Compression Harvester (Target Bar: {expected_daily_label})...")
        start_dt_1m = (now_ist - timedelta(days=HIST_LOOKBACK_DAYS_1M)).replace(hour=9, minute=15, second=0, microsecond=0)
        start_dt_eod = (now_ist - timedelta(days=HIST_LOOKBACK_DAYS_EOD)).replace(hour=9, minute=15, second=0, microsecond=0)
        new_added = 0
        actual_bar_label = memory.get("last_harvested_daily_bar", "")
        harvested_batch = {}

        for idx, fut in enumerate(valid_futures, 1):
            symbol = fut["underlying"]
            trd_sym = fut["trading_symbol"]
            eq_sym = fut.get("eq_trading_symbol", symbol)
            try:
                df_1m = fetch_1m_df(conn, ic, trd_sym, start_dt_1m, now_ist)
                if df_1m.empty:
                    continue

                df_eod = fetch_eod_df(conn, ic, conn.EXCHANGE_TYPE_NSE, eq_sym, start_dt_eod, now_ist)
                df_daily = build_daily_cas_df(df_1m, df_eod, now_ist)
                if df_daily.empty:
                    continue

                actual_bar_label = df_daily.index[-1].strftime("%Y-%m-%d %H:%M")
                res = evaluate_3bar_compression(df_daily)
                if res:
                    res["stock"] = symbol
                    res["trading_symbol"] = trd_sym
                    harvested_batch[symbol] = res
                    new_added += 1
                    print(f"  ➕ Added/Updated in Daily memory: {symbol} ({res['signal']}) on bar {res['bar_time']} | ATR: {res['atr']} | Ratio: {res['body_atr_ratio']}")
            except Exception as e:
                print(f"⚠️ Error harvesting {symbol}: {e}")

        if harvested_batch:
            sample_bar_time = next(iter(harvested_batch.values()))["bar_time"]
            stale_same_bar = [
                s for s, inf in memory.get("stocks", {}).items()
                if inf.get("bar_time") == sample_bar_time
            ]
            for s in stale_same_bar:
                memory["stocks"].pop(s, None)
            memory["stocks"].update(harvested_batch)

        if latest_daily_start is not None:
            memory["last_harvested_daily_bar"] = expected_daily_label
        elif actual_bar_label:
            memory["last_harvested_daily_bar"] = actual_bar_label
        print(f"🌾 Daily Harvest complete: {new_added} stock(s) shortlisted on bar [{actual_bar_label}].")

    active_stocks = memory.get("stocks", {})
    if not active_stocks:
        print("📭 Daily Memory is currently empty. Saving & exiting.")
        save_memory(memory)
        return

    print(f"\n🎯 Running 15m SuperTrend(10, 2) Sniper on {len(active_stocks)} stock(s) in Daily memory...")
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
                print(f"  🗑️ Expired {symbol} (Added {added_date}, {len(subsequent_trade_days)} trading days elapsed).")
                stocks_to_remove.append(symbol)
                continue

            df_15m = resample_to_15m(df_1m, now_ist)
            if len(df_15m) < ST_PERIOD + 5:
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
                print(f"  🔥 TRIGGERED 15m ST(10,2): {symbol} ({info['group']}) on CLOSED 15m bar {alert_item['st_bar_time']} | Close: {alert_item['live_15m_close']} vs ST: {alert_item['st_level']}!")
            else:
                st_state = "GREEN" if latest_15m_bar["st_dir"] == 1 else "RED"
                print(f"  ⏳ Watching {symbol} ({info['group']} | Added {info['bar_time']} | Day +{len(subsequent_trade_days)}) -> 15m ST is {st_state} ({round(float(latest_15m_bar['st_val']), 2)})")

        except Exception as e:
            print(f"⚠️ Error checking 15m ST for {symbol}: {e}")

    for sym in set(stocks_to_remove):
        memory["stocks"].pop(sym, None)

    save_memory(memory)

    if triggered_alerts:
        send_15m_st_email_alert(triggered_alerts, len(memory["stocks"]))
    else:
        print("ℹ️ No 15m SuperTrend (10,2) flips on Daily memory stocks on this bar. No email sent.")

# ==============================================================================
# 7. FULL-DAY CHAINED MARKET CLOCK (MORNING -> AFTERNOON RELAY)
# ==============================================================================
SCAN_CHECKPOINTS_IST = [
    dtime(9, 30, 12), dtime(9, 45, 12),
    dtime(10, 0, 12), dtime(10, 15, 12), dtime(10, 30, 12), dtime(10, 45, 12),
    dtime(11, 0, 12), dtime(11, 15, 12), dtime(11, 30, 12), dtime(11, 45, 12),
    dtime(12, 0, 12), dtime(12, 15, 12), dtime(12, 30, 12), dtime(12, 45, 12),
    dtime(13, 0, 12), dtime(13, 15, 12), dtime(13, 30, 12), dtime(13, 45, 12),
    dtime(14, 0, 12), dtime(14, 15, 12), dtime(14, 30, 12), dtime(14, 45, 12),
    dtime(15, 0, 12), dtime(15, 15, 12), dtime(15, 30, 12),
    dtime(15, 40, 20),  # Exact Daily CAS Close (09:15-15:40) 3-Bar Compression Harvest
]

def stay_awake_market_clock():
    event_name = os.environ.get("GITHUB_EVENT_NAME", "workflow_dispatch")
    session_mode = os.environ.get("SESSION_MODE", "MORNING")
    now_ist = datetime.now(IST)

    # Outside live market hours (before 05:30 AM or after 03:42 PM): run once & exit
    if now_ist.time() < dtime(5, 30) or now_ist.time() > dtime(15, 42):
        if session_mode == "MORNING":
            print("🚀 Outside live market hours. Executing single harvest/check pass...")
            run_scanner(force_harvest=(event_name == "workflow_dispatch"))
        else:
            print("⏹️ Outside market hours (Afternoon job skipped).")
        return

    # Morning job runs until 11:27 AM IST, then Afternoon job takes over until 15:43 PM IST
    if session_mode == "MORNING":
        if now_ist.time() >= dtime(11, 27):
            print("⏩ Already past 11:27 AM IST. Handing over immediately to Afternoon Session job...")
            return
        session_cutoff = dtime(11, 27)
    else:
        session_cutoff = dtime(15, 43)

    print(f"⏰ [{session_mode}] Daily+15m Market Clock active (Started {now_ist.strftime('%H:%M:%S IST')}, Cutoff: {session_cutoff.strftime('%H:%M IST')}).")

    if dtime(9, 30, 12) <= now_ist.time() <= dtime(15, 42):
        print(f"🔔 Initial catch-up scan at {now_ist.strftime('%H:%M:%S IST')}...")
        try:
            run_scanner(force_harvest=False)
        except Exception as e:
            print(f"⚠️ Error in initial scan: {e}")

    while True:
        now_ist = datetime.now(IST)
        if now_ist.weekday() >= 5 or now_ist.time() >= session_cutoff:
            print(f"⏹️ Reached {session_mode} cutoff ({now_ist.strftime('%H:%M:%S IST')}). Exiting cleanly.")
            break

        today_date = now_ist.date()
        future_points = [
            IST.localize(datetime.combine(today_date, cp))
            for cp in SCAN_CHECKPOINTS_IST
            if cp > now_ist.time() and cp <= session_cutoff
        ]

        if not future_points:
            print(f"✅ All checkpoints for {session_mode} completed ({now_ist.strftime('%H:%M:%S IST')}).")
            break

        next_dt = future_points[0]
        sleep_secs = (next_dt - now_ist).total_seconds()
        print(f"💤 Sleeping {round(sleep_secs / 60, 1)} min until next checkpoint: {next_dt.strftime('%H:%M:%S IST')}...")
        time.sleep(max(1.0, sleep_secs))

        now_ist = datetime.now(IST)
        print(f"\n🔔 Checkpoint reached at {now_ist.strftime('%H:%M:%S IST')}. Running scanner...")
        try:
            run_scanner(force_harvest=False)
        except Exception as e:
            print(f"⚠️ Error during checkpoint scan: {e}")

if __name__ == "__main__":
    stay_awake_market_clock()
