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
HIST_LOOKBACK_DAYS = 250       
