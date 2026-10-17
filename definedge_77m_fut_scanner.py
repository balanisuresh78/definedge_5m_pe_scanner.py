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

# 77-Minute 5-Bar Compression Parameters (09:15-15:40 = 385 mins = 5 bars/day)
TIMEFRAME_MIN = 77
ATR_PERIOD = 100
BODY_ATR_MULT = 0.67
CONSEC_BARS = 5
LOOKBACK_DAYS = 75

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

    # Filter NFO Stock Futures (FUTSTK)
    nfo = df[(df[0] == "NFO") & (df[4] == "FUTSTK")].copy()
    nfo["expiry"] = pd.to_datetime(nfo[8], format="%d%m%Y", errors="coerce")
    today = pd.Timestamp(datetime.now(IST).date())
    nfo = nfo[nfo["expiry"] >= today]

    # Pick nearest expiry per underlying symbol
    nfo = nfo.sort_values("expiry").groupby(2, as_index=False).first()
    nfo = nfo.sort_values(2).reset_index(drop=True)

    futures_list = []
    for _, row in nfo.iterrows():
        futures_list.append({
            "underlying": str(row[2]).strip(),
            "trading_symbol": str(row[3]).strip(),
            "token": str(row[1]).strip()
        })
    return futures_list

# ==============================================================================
# 3. 77-MINUTE RESAMPLING & 5-BAR COMPRESSION LOGIC
# ==============================================================================
# Exact 77m bar boundaries across the 09:15 - 15:40 NFO session:
# Bar 1: 09:15 - 10:32
# Bar 2: 10:32 - 11:49
# Bar 3: 11:49 - 13:06
# Bar 4: 13:06 - 14:23
# Bar 5: 14:23 - 15:40
BAR_CLOSURE_TIMES = [
    (dtime(9, 15), dtime(10, 32)),
    (dtime(10, 32), dtime(11, 49)),
    (dtime(11, 49), dtime(13, 6)),
    (dtime(13, 6), dtime(14, 23)),
    (dtime(14, 23), dtime(15, 40)),
]

def get_latest_completed_bar_start(now_ist):
    """Returns the start time of the most recently completed 77m bar today."""
    current_t = now_ist.time()
    completed_start = None
    for start_t, end_t in BAR_CLOSURE_TIMES:
        if current_t >= end_t:
            completed_start = start_t
    return completed_start

def resample_to_77m(df_1m, now_ist):
    """Resamples 1-minute NFO data into exact 77-minute session bars anchored at 09:15."""
    df = df_1m.copy()
    df = df.between_time("09:15", "15:40")
    if df.empty:
        return pd.DataFrame()

    resampled_chunks = []
    for trade_date, group in df.groupby(df.index.date):
        bars = group.resample(
            f"{TIMEFRAME_MIN}min",
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

        # Keep only the 5 valid session bars starting at or before 14:23
        bars = bars[bars.index.time <= dtime(14, 23)]
        resampled_chunks.append(bars)

    if not resampled_chunks:
        return pd.DataFrame()

    df_77m = pd.concat(resampled_chunks).sort_index()

    # Drop any currently forming (incomplete) bar from today
    today_date = now_ist.date()
    latest_completed_start = get_latest_completed_bar_start(now_ist)

    if latest_completed_start is None:
        # Before 10:32 AM today -> evaluate up to previous trading day's final bar
        df_77m = df_77m[df_77m.index.date < today_date]
    else:
        cutoff_dt = IST.localize(datetime.combine(today_date, latest_completed_start))
        df_77m = df_77m[df_77m.index <= cutoff_dt]

    return df_77m

def calculate_wilder_atr(df, period=100):
    high = df["high"]
    low = df["low"]
    prev_close = df["close"].shift(1)

    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)

    # Wilder's RMA (alpha = 1 / period)
    return tr.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()

def evaluate_5bar_compression(df_77m):
    if len(df_77m) < ATR_PERIOD + CONSEC_BARS + 2:
        return None

    df = df_77m.copy()
    df["body"] = (df["close"] - df["open"]).abs()
    df["atr"] = calculate_wilder_atr(df, ATR_PERIOD)
    df["max_allowed_body"] = BODY_ATR_MULT * df["atr"]

    last5 = df.iloc[-CONSEC_BARS:]
    if last5["atr"].isna().any():
        return None

    # Condition 1: All 5 bars must have body < 0.67 * ATR(100)
    if not (last5["body"] < last5["max_allowed_body"]).all():
        return None

    # Condition 2: 5 Consecutive Closes (Bullish rising or Bearish falling)
    # closes[0] is bar[-6] (reference close prior to the 5-bar sequence)
    # closes[1..5] are the 5 consecutive compression bars
    closes = df["close"].iloc[-(CONSEC_BARS + 1):].values
    is_bull = all(closes[i] > closes[i - 1] for i in range(1, CONSEC_BARS + 1))
    is_bear = all(closes[i] < closes[i - 1] for i in range(1, CONSEC_BARS + 1))

    if not (is_bull or is_bear):
        return None

    last_bar = last5.iloc[-1]
    prev_bar = df.iloc[-(CONSEC_BARS + 1)]
    roc_pct = ((last_bar["close"] - prev_bar["close"]) / prev_bar["close"]) * 100.0
    max_body_ratio = (last5["body"] / last5["atr"]).max()

    return {
        "signal": "BULL (5 Up Closes)" if is_bull else "BEAR (5 Down Closes)",
        "group": "BUY" if is_bull else "SELL",
        "bar_time": last5.index[-1].strftime("%d-%b %H:%M"),
        "close": round(float(last_bar["close"]), 2),
        "atr": round(float(last_bar["atr"]), 2),
        "max_body": round(float(last5["body"].max()), 2),
        "body_atr_ratio": round(float(max_body_ratio), 2),
        "roc_pct": round(float(roc_pct), 2)
    }

# ==============================================================================
# 4. EMAIL ALERT FUNCTION
# ==============================================================================
def send_email_alert(matches, evaluated_bar_str):
    now_str = datetime.now(IST).strftime("%d-%b %H:%M:%S")
    subject = f"🎯 77m 5-Bar Alert [{evaluated_bar_str}] ({len(matches)} Matches) - ({now_str})"

    buy_matches = sorted([m for m in matches if m["group"] == "BUY"], key=lambda x: x["roc_pct"], reverse=True)
    sell_matches = sorted([m for m in matches if m["group"] == "SELL"], key=lambda x: x["roc_pct"])

    buy_top5 = ", ".join([m["stock"] for m in buy_matches[:5]]) or "None"
    sell_top5 = ", ".join([m["stock"] for m in sell_matches[:5]]) or "None"
    buy_all = ", ".join([m["stock"] for m in buy_matches]) or "None"
    sell_all = ", ".join([m["stock"] for m in sell_matches]) or "None"

    body_lines = [
        f"Futures 77-Min (5-Bar) Compression Scan at {now_str}",
        f"Completed Bar Evaluated: {evaluated_bar_str}\n",
        f"📋 BUY GROUP - Top 5 (Copy & Paste into Zone):\n{buy_top5}\n",
        f"📋 SELL GROUP - Top 5 (Copy & Paste into Zone):\n{sell_top5}\n",
        f"All BUY ({len(buy_matches)}): {buy_all}",
        f"All SELL ({len(sell_matches)}): {sell_all}\n"
    ]

    if matches:
        table_rows = [
            [
                m["stock"],
                m["signal"],
                m["bar_time"],
                m["close"],
                m["atr"],
                m["max_body"],
                m["body_atr_ratio"],
                f"{m['roc_pct']}%"
            ]
            for m in (buy_matches + sell_matches)
        ]
        headers = ["Stock", "Setup", "Bar Start", "Close", "ATR(100)", "Max5Body", "Body/ATR", "5-Bar ROC%"]
        body_lines.append(tabulate(table_rows, headers=headers, tablefmt="grid"))
    else:
        body_lines.append("No stocks matched the 77m 5-bar compression criteria on this bar.")

    msg = MIMEMultipart()
    msg["From"] = SENDER_EMAIL
    msg["To"] = RECEIVER_EMAIL
    msg["Subject"] = subject
    msg.attach(MIMEText("\n".join(body_lines), "plain"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(SENDER_EMAIL, APP_PASSWORD)
        server.send_message(msg)

    print(f"✅ Alert email successfully sent for bar [{evaluated_bar_str}]!")

# ==============================================================================
# 5. MAIN SCANNER EXECUTION
# ==============================================================================
def run_single_scan():
    now_ist = datetime.now(IST)
    print(f"\n🚀 Starting 77m Futures 5-Bar Compression Scan at {now_ist.strftime('%Y-%m-%d %H:%M:%S IST')}")

    ic = login_definedge()
    futures = get_current_month_nfo_futures()
    total = len(futures)
    print(f"Loaded {total} NFO Stock Futures.")

    start_dt = (now_ist - timedelta(days=LOOKBACK_DAYS)).replace(hour=9, minute=15, second=0, microsecond=0)
    matches = []
    evaluated_bar_str = "N/A"

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

            df_77m = resample_to_77m(df, now_ist)
            if df_77m.empty:
                continue

            evaluated_bar_str = df_77m.index[-1].strftime("%d-%b %H:%M")
            res = evaluate_5bar_compression(df_77m)
            if res:
                res["stock"] = symbol
                matches.append(res)

        except Exception as e:
            print(f"⚠️ Error scanning {symbol}: {e}", flush=True)

    send_email_alert(matches, evaluated_bar_str)

if __name__ == "__main__":
    run_single_scan()
