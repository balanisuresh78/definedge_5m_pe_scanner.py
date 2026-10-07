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
STOCH_K_PERIOD = 5             
STOCH_SMOOTH_K = 3             
STOCH_D_PERIOD = 3             
HIST_LOOKBACK_DAYS = 250       # Increased to 250 to calculate ATR(100) + 40 bar impulse search

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
        elif
