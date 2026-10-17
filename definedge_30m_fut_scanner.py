import os
import sys
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
API_TOKEN = os.environ.get("DEFINEDGE_API_TOKEN", "YOUR_API_TOKEN")
API_SECRET = os.environ.get("DEFINEDGE_API_SECRET", "YOUR_API_SECRET")
TOTP_SECRET = os.environ.get("DEFINEDGE_TOTP_SECRET", "YOUR_TOTP_SECRET")

SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "your_email@gmail.com")
RECEIVER_EMAIL = os.environ.get("RECEIVER_EMAIL", "your_email@gmail.com")
APP_PASSWORD = os.environ.get("APP_PASSWORD", "YOUR_GMAIL_APP_PASSWORD")

IST = pytz.timezone("Asia/Kolkata")

# 30-Minute ATR Retracement + Stochastic (5, 3, 3) Parameters
TIMEFRAME_MIN = 30
STOCH_K = 5
STOCH_SMOOTH_K = 3
STOCH_D = 3
BULL_LEVEL = 31.0
BEAR_LEVEL = 69.0

ATR_PERIOD = 2
REF_ATR_LOOKBACK = 5
BODY_ATR_MULT = 0.70  # Max corrective body < 70% of Ref ATR
LOOKBACK_DAYS = 25

# ==============================================================================
# 2. DEFINEDGE LOGIN & MASTER SYMBOL FETCH
# ==============================================================================
def login_definedge():
    conn = ConnectToIntegrate()
    totp = pyotp.TOTP(TOTP_SECRET).now()
    conn.login(api_token=API_TOKEN, api_secret=API_SECRET, totp=totp)
    return IntegrateData(conn)

def get_current_month_nfo_futures():
    url = "https://app.definedgesecurities.com/public/allmaster.zip"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
        csv_name = z.namelist()[0]
        with z.open(csv_name) as f:
            df = pd.read_csv(f, header=None, low_memory=False)

    nfo = df[(df[0] == "NFO") & (df[4] == "FUTSTK")].copy()
    nfo["expiry"] = pd.to_datetime(nfo[8], format="%d%m%Y", errors="coerce")
    today = pd.Timestamp(datetime.now(IST).date())
    nfo = nfo[nfo["expiry"] >= today]

    nfo = nfo.sort_values("expiry").groupby(2, as_index=False).first()
    nfo = nfo.sort_values(2).reset_index(drop=True)

    return [
        {
            "underlying": str(row[2]).strip(),
            "trading_symbol": str(row[3]).strip(),
            "token": str(row[1]).strip()
        }
        for _, row in nfo.iterrows()
    ]

# ==============================================================================
# 3. 30-MINUTE RESAMPLING & INDICATOR LOGIC
# ==============================================================================
# 30m session bar closures (09:15 to 15:30 IST)
BAR_CLOSURE_TIMES = [
    (dtime(9, 15), dtime(9, 45)),
    (dtime(9, 45), dtime(10, 15)),
    (dtime(10, 15), dtime(10, 45)),
    (dtime(10, 45), dtime(11, 15)),
    (dtime(11, 15), dtime(11, 45)),
    (dtime(11, 45), dtime(12, 15)),
    (dtime(12, 15), dtime(12, 45)),
    (dtime(12, 45), dtime(13, 15)),
    (dtime(13, 15), dtime(13, 45)),
    (dtime(13, 45), dtime(14, 15)),
    (dtime(14, 15), dtime(14, 45)),
    (dtime(14, 45), dtime(15, 15)),
    (dtime(15, 15), dtime(15, 30)),
]

def get_latest_completed_30m_start(now_ist):
    current_t = now_ist.time()
    completed_start = None
    for start_t, end_t in BAR_CLOSURE_TIMES:
        if current_t >= end_t:
            completed_start = start_t
    return completed_start

def resample_to_30m(df_1m, now_ist):
    df = df_1m.copy()
    df = df.between_time("09:15", "15:30")
    if df.empty:
        return pd.DataFrame()

    resampled_chunks = []
    for trade_date, group in df.groupby(df.index.date):
        bars = group.resample(
            "30min",
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

    df_30m = pd.concat(resampled_chunks).sort_index()

    today_date = now_ist.date()
    latest_completed_start = get_latest_completed_30m_start(now_ist)

    if latest_completed_start is None:
        df_30m = df_30m[df_30m.index.date < today_date]
    else:
        cutoff_dt = IST.localize(datetime.combine(today_date, latest_completed_start))
        df_30m = df_30m[df_30m.index <= cutoff_dt]

    return df_30m

def calculate_indicators(df):
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)

    # Wilder's ATR
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)
    df["atr"] = tr.ewm(alpha=1.0 / ATR_PERIOD, min_periods=ATR_PERIOD, adjust=False).mean()

    # Stochastic (5, 3, 3)
    lowest_low = low.rolling(window=STOCH_K).min()
    highest_high = high.rolling(window=STOCH_K).max()
    denom = (highest_high - lowest_low).replace(0, np.nan)
    fast_k = 100.0 * ((close - lowest_low) / denom)
    slow_k = fast_k.rolling(window=STOCH_SMOOTH_K).mean()
    df["stoch_d"] = slow_k.rolling(window=STOCH_D).mean()
    df["body"] = (df["close"] - df["open"]).abs()
    return df

def evaluate_30m_setup(df_30m):
    if len(df_30m) < 20:
        return None

    df = calculate_indicators(df_30m.copy())
    last_bar = df.iloc[-1]
    prev_bar = df.iloc[-2]

    if pd.isna(last_bar["stoch_d"]) or pd.isna(prev_bar["stoch_d"]) or pd.isna(last_bar["atr"]):
        return None

    prev_d = float(prev_bar["stoch_d"])
    live_d = float(last_bar["stoch_d"])

    # Bullish %D cross at 31 or Bearish %D cross at 69
    is_bull = (prev_d > BULL_LEVEL and live_d <= BULL_LEVEL) or (prev_d < BULL_LEVEL and live_d >= BULL_LEVEL)
    is_bear = (prev_d < BEAR_LEVEL and live_d >= BEAR_LEVEL) or (prev_d > BEAR_LEVEL and live_d <= BEAR_LEVEL)

    if not (is_bull or is_bear):
        return None

    # Reference ATR from impulse phase & Max Body check on retracement bars
    recent_window = df.iloc[-(REF_ATR_LOOKBACK + 2):-1]
    ref_atr = float(recent_window["atr"].max())
    retracement_bars = df.iloc[-3:]
    max_body = float(retracement_bars["body"].max())

    if ref_atr <= 0 or max_body >= (BODY_ATR_MULT * ref_atr):
        return None

    return {
        "setup": "Bullish" if is_bull else "Bearish",
        "bar_time": df.index[-1].strftime("%H:%M"),
        "prev_d": round(prev_d, 2),
        "live_d": round(live_d, 2),
        "ref_atr": round(ref_atr, 2),
        "max_body": round(max_body, 2),
        "ratio": round(ref_atr / max(max_body, 0.01), 2)
    }

# ==============================================================================
# 4. EMAIL ALERT FUNCTION
# ==============================================================================
def send_email_alert(matches):
    now_str = datetime.now(IST).strftime("%d-%b %H:%M:%S")
    subject = f"🎯 30m Futures Alert: ATR Retracement Setup ({now_str})"

    matches_sorted = sorted(matches, key=lambda x: x["ratio"], reverse=True)

    body_lines = [f"30-Minute Stock Futures Scan at {now_str}\n"]
    if matches_sorted:
        table_rows = [
            [
                m["stock"],
                m["setup"],
                m["bar_time"],
                m["prev_d"],
                m["live_d"],
                m["ref_atr"],
                m["max_body"]
            ]
            for m in matches_sorted
        ]
        headers = ["Stock", "Setup", "Bar Time", "Prev %D", "Live %D", "Ref ATR", "Max Body"]
        body_lines.append(tabulate(table_rows, headers=headers, tablefmt="grid"))
    else:
        body_lines.append("No stocks matched the 30m ATR Retracement criteria on this bar.")

    msg = MIMEMultipart()
    msg["From"] = SENDER_EMAIL
    msg["To"] = RECEIVER_EMAIL
    msg["Subject"] = subject
    msg.attach(MIMEText("\n".join(body_lines), "plain"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(SENDER_EMAIL, APP_PASSWORD)
        server.send_message(msg)

    print(f"✅ 30m Alert email sent ({len(matches_sorted)} matches)!")

# ==============================================================================
# 5. MAIN EXECUTION (SINGLE RUN + 15:50 IST HARD CUTOFF)
# ==============================================================================
def run_scan():
    now_ist = datetime.now(IST)
    current_t = now_ist.time()
    event_name = os.environ.get("GITHUB_EVENT_NAME", "workflow_dispatch")

    # Hard cutoff: if triggered by cron schedule outside 09:40 - 15:50 IST, exit immediately
    if event_name == "schedule" and (current_t < dtime(9, 40) or current_t > dtime(15, 50)):
        print(f"⏹️ Outside market scan window ({now_ist.strftime('%H:%M:%S IST')}). Exiting to free runner.")
        sys.exit(0)

    print(f"\n🚀 Starting 30m Futures Scan at {now_ist.strftime('%Y-%m-%d %H:%M:%S IST')}")
    ic = login_definedge()
    futures = get_current_month_nfo_futures()
    total = len(futures)

    start_dt = (now_ist - timedelta(days=LOOKBACK_DAYS)).replace(hour=9, minute=15, second=0, microsecond=0)
    matches = []

    for idx, fut in enumerate(futures, 1):
        symbol = fut["underlying"]
        trd_sym = fut["trading_symbol"]
        print(f"Scanning {symbol} ({idx}/{total})...", flush=True)

        try:
            hist = ic.historical_data(
                exchange="NFO",
                trading_symbol=trd_sym,
                timeframe=ic.TIMEFRAME_TYPE_MIN,
                start=start_dt,
                end=now_ist
            )
            df = pd.DataFrame(list(hist))
            if df.empty:
                continue

            df["datetime"] = pd.to_datetime(df["datetime"])
            if df["datetime"].dt.tz is None:
                df["datetime"] = df["datetime"].dt.tz_localize(IST)
            else:
                df["datetime"] = df["datetime"].dt.tz_convert(IST)

            df = df.set_index("datetime").sort_index()
            for col in ["open", "high", "low", "close", "volume"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")

            df_30m = resample_to_30m(df, now_ist)
            if df_30m.empty:
                continue

            res = evaluate_30m_setup(df_30m)
            if res:
                res["stock"] = symbol
                matches.append(res)

        except Exception as e:
            print(f"⚠️ Error scanning {symbol}: {e}", flush=True)

    if matches:
        send_email_alert(matches)
    else:
        print("ℹ️ No 30m setups matched on this bar.")

if __name__ == "__main__":
    run_scan()
