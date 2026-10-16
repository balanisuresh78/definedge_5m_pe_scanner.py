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

# Strategy Parameters (77-Min Timeframe, 4-Bar Compression)
TIMEFRAME_MINS = 77
ATR_PERIOD = 100
BODY_ATR_MULT = 0.67
HIST_LOOKBACK_DAYS = 75

# Exact IST Bar-Close Scan Targets (15 seconds after each 77m bar close)
SCAN_TARGETS_IST = [
    dt_time(10, 32, 15),  # Bar 1 Close
    dt_time(11, 49, 15),  # Bar 2 Close
    dt_time(13, 6, 15),   # Bar 3 Close
    dt_time(14, 23, 15),  # Bar 4 Close
    dt_time(15, 4
