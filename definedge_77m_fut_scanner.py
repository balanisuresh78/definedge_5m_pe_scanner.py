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
API_TOKEN = os.environ.get("DEFINEDGE_API_TOKEN", "7eb93aac-c746-44bd-9755-18ae6289fdfc")
API_SECRET = os.environ.get("DEFINEDGE_API_SECRET", "snToBptj6e2X/c9c7POM8Q==")
TOTP_SECRET = os.environ.get("DEFINEDGE_TOTP_SECRET", "IJGDEV2EJFUTIQTNHBYG2SZXJ5IXOMBR")

SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "balanisuresh@gmail.com")
RECEIVER_EMAIL = os.environ.get("RECEIVER_EMAIL", "balanisuresh@gmail.com")
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
    current_t = now_ist.time()
    completed_start = None
    for start_t, end_t in BAR_CLOSURE_TIMES:
        if current_t >= end_t:
            completed_start = start_t
    return completed_start

def resample_to_77m(df_1m, now_ist):
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

        bars = bars[bars.index.time <= dtime(14, 23)]
        resampled_chunks.append(bars)

    if not resampled_chunks:
        return pd.DataFrame()

    df_77m = pd.concat(resampled_chunks).sort_index()

    today_date = now_ist.date()
    latest_completed_start = get_latest_completed_bar_start(now_ist)

    if (df_77m.index.date == today_date).any():
        if latest_completed_start is None:
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

    # Condition 2: 5 Consecutive Pullback Closes
    # 5 Down Closes with narrow body = Bullish pullback -> BUY Group
    # 5 Up Closes with narrow body   = Bearish pullback -> SELL Group
    closes = df["close"].iloc[-(CONSEC_BARS + 1):].values
    is_bull_setup = all(closes[i] < closes[i - 1] for i in range(1, CONSEC_BARS + 1))
    is_bear_setup = all(closes[i] > closes[i - 1] for i in range(1, CONSEC_BARS + 1))

    if not (is_bull_setup or is_bear_setup):
        return None

    last_bar = last5.iloc[-1]
    prev_bar = df.iloc[-(CONSEC_BARS + 1)]
    roc_pct = ((last_bar["close"] - prev_bar["close"]) / prev_bar["close"]) * 100.0
    max_body_ratio = (last5["body"] / last5["atr"]).max()

    return {
        "signal": "BULL (5 Down Closes)" if is_bull_setup else "BEAR (5 Up Closes)",
        "group": "BUY" if is_bull_setup else "SELL",
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

    buy_matches = sorted([m for m in matches if m["group"] == "BUY"], key=lambda x: x["roc_pct"])
    sell_matches = sorted([m for m in matches if m["group"] == "SELL"], key=lambda x: x["roc_pct"], reverse=True)

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

    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as server:
        server.login(SENDER_EMAIL, APP_PASSWORD)
        server.send_message(msg)

    print(f"✅ Alert email successfully sent for bar [{evaluated_bar_str}]!")

# ==============================================================================
# 5. MAIN SCANNER EXECUTION
# ==============================================================================
def run_single_scan():
    now_ist = datetime.now(IST)
    current_t = now_ist.time()
    event_name = os.environ.get("GITHUB_EVENT_NAME", "workflow_dispatch")

    if event_name == "schedule" and (current_t < dtime(10, 25) or current_t > dtime(16, 0)):
        print(f"⏹️ Outside 77m market scan window ({now_ist.strftime('%H:%M:%S IST')}). Exiting to free runner.")
        sys.exit(0)

    print(f"\n🚀 Starting 77m Futures 5-Bar Compression Scan at {now_ist.strftime('%Y-%m-%d %H:%M:%S IST')}")

    conn, ic = login_definedge()
    futures = get_current_month_nfo_futures(conn)
    total = len(futures)
    print(f"Loaded {total} NFO Stock Futures.")

    if total == 0:
        print("⚠️ No NFO Stock Futures found! Exiting without sending blank email.")
        sys.exit(1)

    start_dt = (now_ist - timedelta(days=LOOKBACK_DAYS)).replace(hour=9, minute=15, second=0, microsecond=0)
    matches = []
    evaluated_bar_str = "N/A"

    for idx, fut in enumerate(futures, 1):
        symbol = fut["underlying"]
        trd_sym = fut["trading_symbol"]
        print(f"Scanning {symbol} ({idx}/{total})...", flush=True)

        try:
            hist = ic.historical_data(
                exchange=conn.EXCHANGE_TYPE_NFO,
                trading_symbol=trd_sym,
                timeframe=conn.TIMEFRAME_TYPE_MIN,
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
