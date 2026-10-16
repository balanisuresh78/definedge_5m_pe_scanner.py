name: Definedge 77m FUT Scanner

on:
  schedule:
    # Pre-shifted early trigger (01:30 UTC / 07:00 IST) to offset GitHub's cron backlog so the background script wakes up early
    - cron: '30 1 * * 1-5'
    # Bar 1 Close (09:15 - 10:32) -> Runs at 10:33 IST / 05:03 UTC
    - cron: '3 5 * * 1-5'
    # Bar 2 Close (10:32 - 11:49) -> Runs at 11:50 IST / 06:20 UTC
    - cron: '20 6 * * 1-5'
    # Bar 3 Close (11:49 - 13:06) -> Runs at 13:07 IST / 07:37 UTC
    - cron: '37 7 * * 1-5'
    # Bar 4 Close (13:06 - 14:23) -> Runs at 14:24 IST / 08:54 UTC
    - cron: '54 8 * * 1-5'
    # Bar 5 Close (14:23 - 15:40) -> Runs at 15:41 IST / 10:11 UTC
    - cron: '11 10 * * 1-5'
  workflow_dispatch:

# Prevents duplicate runs from overlapping if a background timer is active
concurrency:
  group: definedge-77m-intraday-scanner
  cancel-in-progress: false

jobs:
  run-77m-fut-scan:
    runs-on: ubuntu-latest
    timeout-minutes: 350
    steps:
      - name: Checkout Repository
        uses: actions/checkout@v4

      - name: Set Up Python 3.11
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install Dependencies
        run: pip install pyintegrate pyotp pandas numpy tabulate pytz requests

      - name: Run 77m Definedge Scanner
        env:
          APP_PASSWORD: ${{ secrets.APP_PASSWORD }}
          GITHUB_EVENT_NAME: ${{ github.event_name }}
        run: |
          if [ -f "definedge_77m_fut_scanner.py" ]; then
            python definedge_77m_fut_scanner.py
          elif [ -f "definedge_129m_fut_scanner.py" ]; then
            python definedge_129m_fut_scanner.py
          else
            echo "Error: Scanner python file not found!"
            exit 1
          fi
