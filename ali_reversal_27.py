import os
import json
import time
import requests
from datetime import datetime, timezone


# ============================================================
# CONFIG
# ============================================================

API_KEY = os.getenv("TWELVE_DATA_API_KEY")

SYMBOL = "XAU/USD"
INTERVAL = "1min"

OUTPUT_FILE = "signal_state.json"

CANDLE_LIMIT = 500

if not API_KEY:
    raise RuntimeError("TWELVE_DATA_API_KEY is not configured")


# ============================================================
# STATE
# ============================================================

DEFAULT_STATE = {
    "last_circle_color": 0,
    "last_shown_red_high": None,
    "last_shown_green_low": None,
    "last_signal_time": None,
    "last_signal_price": None
}


def load_state():
    if not os.path.exists(OUTPUT_FILE):
        return DEFAULT_STATE.copy()

    try:
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        state = DEFAULT_STATE.copy()
        state.update(data)
        return state

    except Exception:
        return DEFAULT_STATE.copy()


def save_state(state):
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# ============================================================
# GET XAU/USD DATA
# ============================================================

def get_candles():

    url = "https://api.twelvedata.com/time_series"

    params = {
        "symbol": SYMBOL,
        "interval": INTERVAL,
        "outputsize": CANDLE_LIMIT,
        "apikey": API_KEY,
        "timezone": "UTC"
    }

    response = requests.get(
        url,
        params=params,
        timeout=20
    )

    response.raise_for_status()

    data = response.json()

    if data.get("status") == "error":
        raise RuntimeError(
            data.get("message", "Twelve Data API error")
        )

    values = data.get("values")

    if not values:
        raise RuntimeError("No candle data received")

    candles = []

    for item in reversed(values):

        candles.append({
            "time": item["datetime"],
            "open": float(item["open"]),
            "high": float(item["high"]),
            "low": float(item["low"]),
            "close": float(item["close"])
        })

    return candles


# ============================================================
# DATE KEY
# ============================================================

def date_key(candle):

    return candle["time"][:10]


# ============================================================
# ALI REVERSAL 27 ENGINE
# ============================================================

def calculate(candles, previous_state):

    if len(candles) < 10:
        return None, previous_state

    state = DEFAULT_STATE.copy()
    state.update(previous_state)

    # --------------------------------------------------------
    # DAILY VARIABLES
    # --------------------------------------------------------

    y_high = None
    y_low = None

    current_day = None

    high_touched = False
    low_touched = False

    high_broken_today = False
    low_broken_today = False

    # --------------------------------------------------------
    # SIGNAL HISTORY
    # --------------------------------------------------------

    last_blue_low = None
    last_yellow_high = None

    last_blue_bar = None
    last_yellow_bar = None

    red_high1 = None
    red_high2 = None

    red_low1 = None
    red_low2 = None

    red_bar2 = None

    green_low1 = None
    green_low2 = None

    green_high1 = None
    green_high2 = None

    green_bar2 = None

    blue_shape_done = False
    yellow_shape_done = False

    last_circle_color = 0

    last_shown_red_high = None
    last_shown_green_low = None

    # --------------------------------------------------------
    # PREVIOUS DAY DATA
    # --------------------------------------------------------

    daily = {}

    for candle in candles:

        d = date_key(candle)

        if d not in daily:
            daily[d] = {
                "high": candle["high"],
                "low": candle["low"]
            }
        else:
            daily[d]["high"] = max(
                daily[d]["high"],
                candle["high"]
            )

            daily[d]["low"] = min(
                daily[d]["low"],
                candle["low"]
            )

    days = sorted(daily.keys())

    # --------------------------------------------------------
    # PROCESS CANDLES
    # --------------------------------------------------------

    signal = None

    for i, candle in enumerate(candles):

        if i == 0:
            previous_candle = candle
        else:
            previous_candle = candles[i - 1]

        day = date_key(candle)

        new_day = (
            current_day is not None
            and day != current_day
        )

        if current_day is None:
            current_day = day

            # No previous day yet
            y_high = None
            y_low = None

        elif new_day:

            # Previous day becomes yesterday
            previous_day = current_day

            y_high = daily[previous_day]["high"]
            y_low = daily[previous_day]["low"]

            current_day = day

            high_touched = False
            low_touched = False

            high_broken_today = False
            low_broken_today = False

            last_blue_low = None
            last_yellow_high = None

            last_blue_bar = None
            last_yellow_bar = None

            red_high1 = None
            red_high2 = None

            red_low1 = None
            red_low2 = None

            red_bar2 = None

            green_low1 = None
            green_low2 = None

            green_high1 = None
            green_high2 = None

            green_bar2 = None

            blue_shape_done = False
            yellow_shape_done = False

            last_circle_color = 0

            last_shown_red_high = None
            last_shown_green_low = None

        # ----------------------------------------------------
        # FIRST TOUCH
        # ----------------------------------------------------

        first_high_touch = (
            y_high is not None
            and not high_touched
            and candle["high"] >= y_high
        )

        first_low_touch = (
            y_low is not None
            and not low_touched
            and candle["low"] <= y_low
        )

        if first_high_touch:
            high_touched = True

        if first_low_touch:
            low_touched = True

        # ----------------------------------------------------
        # YESTERDAY PENETRATION
        # ----------------------------------------------------

        if y_high is not None and candle["high"] >= y_high:
            high_broken_today = True

        if y_low is not None and candle["low"] <= y_low:
            low_broken_today = True

        high_active_zone = (
            high_broken_today
            and y_high is not None
            and candle["high"] >= y_high - 30
        )

        low_active_zone = (
            low_broken_today
            and y_low is not None
            and candle["low"] <= y_low + 30
        )

        active_zone = (
            high_active_zone
            or low_active_zone
        )

        # ----------------------------------------------------
        # CANDLE QUALITY
        # ----------------------------------------------------

        candle_range = (
            candle["high"] - candle["low"]
        )

        body_size = abs(
            candle["close"] - candle["open"]
        )

        lower_wick = (
            min(candle["open"], candle["close"])
            - candle["low"]
        )

        upper_wick = (
            candle["high"]
            - max(candle["open"], candle["close"])
        )

        strong_body = (
            candle_range > 0
            and body_size / candle_range >= 0.30
        )

        valid_lower_wick = (
            candle_range > 0
            and lower_wick / candle_range >= 0.10
        )

        valid_upper_wick = (
            candle_range > 0
            and upper_wick / candle_range >= 0.10
        )

        bull = candle["close"] > candle["open"]
        bear = candle["close"] < candle["open"]

        # ----------------------------------------------------
        # BLUE SIGNAL
        # ----------------------------------------------------

        blue_signal = (
            active_zone
            and candle_range > 0
            and bull
            and candle["low"] < previous_candle["low"]
            and candle["high"] > previous_candle["high"]
            and strong_body
            and valid_lower_wick
        )

        # ----------------------------------------------------
        # YELLOW SIGNAL
        # ----------------------------------------------------

        yellow_signal = (
            active_zone
            and candle_range > 0
            and bear
            and candle["high"] > previous_candle["high"]
            and candle["low"] < previous_candle["low"]
            and strong_body
            and valid_upper_wick
        )

        if blue_signal:
            last_blue_low = candle["low"]
            last_blue_bar = i

        if yellow_signal:
            last_yellow_high = candle["high"]
            last_yellow_bar = i

        # ----------------------------------------------------
        # RED RAW
        # ----------------------------------------------------

        red_big = (
            active_zone
            and last_blue_low is not None
            and last_yellow_bar is not None
            and last_blue_bar is not None
            and last_yellow_bar > last_blue_bar
            and i > last_yellow_bar
            and candle["low"] <= last_blue_low
        )

        # ----------------------------------------------------
        # GREEN RAW
        # ----------------------------------------------------

        green_big = (
            active_zone
            and last_yellow_high is not None
            and last_blue_bar is not None
            and last_yellow_bar is not None
            and last_blue_bar > last_yellow_bar
            and i > last_blue_bar
            and candle["high"] >= last_yellow_high
        )

        # ----------------------------------------------------
        # RED NEW
        # ----------------------------------------------------

        red_new = (
            red_big
            and (
                last_circle_color != 1
                or last_shown_red_high is None
                or candle["high"] > last_shown_red_high
            )
        )

        # ----------------------------------------------------
        # GREEN NEW
        # ----------------------------------------------------

        green_new = (
            green_big
            and (
                last_circle_color != -1
                or last_shown_green_low is None
                or candle["low"] < last_shown_green_low
            )
        )

        # ----------------------------------------------------
        # RED HISTORY
        # ----------------------------------------------------

        if red_big:

            red_high1 = red_high2
            red_low1 = red_low2

            red_high2 = candle["high"]
            red_low2 = candle["low"]

            red_bar2 = i

        # ----------------------------------------------------
        # GREEN HISTORY
        # ----------------------------------------------------

        if green_big:

            green_low1 = green_low2
            green_high1 = green_high2

            green_low2 = candle["low"]
            green_high2 = candle["high"]

            green_bar2 = i

        # ----------------------------------------------------
        # CIRCLE STATE
        # ----------------------------------------------------

        if red_new:

            last_circle_color = 1

            last_shown_red_high = candle["high"]
            last_shown_green_low = None

            signal = {
                "color": "RED",
                "emoji": "🔴",
                "price": candle["close"],
                "time": candle["time"],
                "open": candle["open"],
                "high": candle["high"],
                "low": candle["low"],
                "close": candle["close"]
            }

        elif green_new:

            last_circle_color = -1

            last_shown_green_low = candle["low"]
            last_shown_red_high = None

            signal = {
                "color": "GREEN",
                "emoji": "🟢",
                "price": candle["close"],
                "time": candle["time"],
                "open": candle["open"],
                "high": candle["high"],
                "low": candle["low"],
                "close": candle["close"]
            }

    # --------------------------------------------------------
    # SAVE STATE
    # --------------------------------------------------------

    state["last_circle_color"] = last_circle_color
    state["last_shown_red_high"] = last_shown_red_high
    state["last_shown_green_low"] = last_shown_green_low

    if signal:

        state["last_signal_time"] = signal["time"]
        state["last_signal_price"] = signal["price"]

    return signal, state


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 50)
    print("ALI REVERSAL 27")
    print("XAU/USD - 1 MINUTE")
    print("=" * 50)

    state = load_state()

    candles = get_candles()

    print(f"Candles received: {len(candles)}")

    signal, new_state = calculate(
        candles,
        state
    )

    if signal:

        print()
        print(signal["emoji"], signal["color"])
        print("Price:", signal["price"])
        print("Time:", signal["time"])
        print()

    else:

        print("No new signal.")

    save_state(new_state)

    print("State saved.")


if __name__ == "__main__":
    main()
