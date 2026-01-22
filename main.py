# from fastapi import FastAPI, HTTPException
# import requests
# import datetime
# import calendar
# import os
# import time
# from decimal import Decimal
# from dotenv import load_dotenv
# load_dotenv()

# app = FastAPI()

# # ---------------- CONFIG ----------------

# BASE_URL = "https://api.stripe.com/v1/subscriptions"
# PAGE_LIMIT = 100
# TIMEOUT = 30
# MAX_RETRIES = 5

# def get_headers():
#     stripe_secret = os.environ.get("STRIPE_SECRET")
#     if not stripe_secret:
#         raise HTTPException(status_code=500, detail="Missing STRIPE_SECRET in environment")
#     return {"Authorization": f"Bearer {stripe_secret}"}

# # ---------------- HELPERS ----------------

# def add_months(dt, months):
#     year = dt.year + (dt.month - 1 + months) // 12
#     month = (dt.month - 1 + months) % 12 + 1
#     day = min(dt.day, calendar.monthrange(year, month)[1])
#     return datetime.datetime(year, month, day, dt.hour, dt.minute, dt.second, tzinfo=dt.tzinfo)

# def to_iso_from_ts(ts):
#     if ts is None:
#         return None
#     try:
#         dt = datetime.datetime.fromtimestamp(int(ts), datetime.timezone.utc)
#         return dt.isoformat().replace("+00:00", "Z")
#     except Exception:
#         return None

# def to_dt_from_ts(ts):
#     if ts is None:
#         return None
#     try:
#         return datetime.datetime.fromtimestamp(int(ts), datetime.timezone.utc)
#     except Exception:
#         return None

# _CURRENCY_EXPONENTS = {
#     0: {"BIF","CLP","DJF","GNF","JPY","KMF","KRW","MGA","PYG","RWF","UGX","VND","VUV","XAF","XOF","XPF"},
#     3: {"BHD","IQD","JOD","KWD","LYD","OMR","TND"}
# }

# def currency_exponent(currency_code):
#     if not currency_code:
#         return 2
#     c = currency_code.upper()
#     for exp, codes in _CURRENCY_EXPONENTS.items():
#         if c in codes:
#             return exp
#     return 2

# _CURRENCY_SYMBOLS = {
#     "USD":"$", "EUR":"€", "GBP":"£", "JPY":"¥", "CAD":"$", "AUD":"$",
#     "CHF":"CHF ", "INR":"₹", "PKR":"Rs ", "CNY":"¥"
# }

# def format_currency_amount_from_minor(minor_amount, currency_code, exponent, as_decimal_str=None):
#     try:
#         if as_decimal_str:
#             minor = Decimal(str(as_decimal_str))
#         else:
#             minor = Decimal(int(minor_amount))
#     except Exception:
#         return None

#     scale = Decimal(10) ** Decimal(exponent)
#     major = (minor / scale).normalize()
#     major_str = format(major, "f")

#     if "." in major_str:
#         int_part, frac = major_str.split(".", 1)
#         frac = frac.ljust(exponent, "0")[:exponent]
#         major_str = f"{int_part}.{frac}" if exponent > 0 else int_part
#     else:
#         if exponent > 0:
#             major_str = major_str + "." + ("0" * exponent)

#     sym = _CURRENCY_SYMBOLS.get((currency_code or "").upper())
#     return f"{sym}{major_str}" if sym else f"{currency_code.upper()} {major_str}"

# def safe_get_price_info(sub):
#     price_id = None
#     nickname = None
#     amount = None
#     amount_decimal = None
#     currency = None

#     items = sub.get("items", {}).get("data") or []
#     if items:
#         price = items[0].get("price") or {}
#         price_id = price.get("id")
#         nickname = price.get("nickname")
#         amount = price.get("unit_amount")
#         amount_decimal = price.get("unit_amount_decimal")
#         currency = price.get("currency")

#     if not currency:
#         invoice = sub.get("latest_invoice")
#         if isinstance(invoice, dict):
#             currency = invoice.get("currency")

#     return price_id, nickname, amount, amount_decimal, currency

# # ---------------- STRIPE FETCH ----------------

# def fetch_all_subscriptions():
#     headers = get_headers()

#     all_subs = []
#     has_more = True
#     starting_after = None

#     while has_more:
#         params = [
#             ("status", "active"),
#             ("limit", PAGE_LIMIT),
#             ("expand[]", "data.customer"),
#             ("expand[]", "data.latest_invoice"),
#         ]
#         if starting_after:
#             params.append(("starting_after", starting_after))

#         for attempt in range(1, MAX_RETRIES + 1):
#             try:
#                 resp = requests.get(BASE_URL, headers=headers, params=params, timeout=TIMEOUT)
#             except Exception:
#                 if attempt == MAX_RETRIES:
#                     raise
#                 time.sleep(1.5 * attempt)
#                 continue

#             if resp.status_code == 200:
#                 data = resp.json()
#                 break
#             elif resp.status_code in (429, 502, 503, 504):
#                 time.sleep(1.5 * (2 ** (attempt - 1)))
#             else:
#                 raise HTTPException(status_code=resp.status_code, detail=resp.text)

#         items = data.get("data", [])
#         all_subs.extend(items)

#         has_more = data.get("has_more", False)
#         starting_after = items[-1]["id"] if has_more and items else None

#     return all_subs

# # ---------------- API ROUTE ----------------

# @app.get("/subscriptions")
# def get_subscriptions():
#     subs = fetch_all_subscriptions()
#     now_utc = datetime.datetime.now(datetime.timezone.utc)

#     normalized = []

#     for s in subs:
#         sub_id = s.get("id")
#         customer = s.get("customer")

#         customer_id = None
#         email = None
#         first = None
#         last = None

#         if isinstance(customer, dict):
#             customer_id = customer.get("id")
#             email = customer.get("email")
#             name = (customer.get("name") or "").strip()
#             if name:
#                 parts = name.split(" ", 1)
#                 first = parts[0]
#                 last = parts[1] if len(parts) > 1 else ""

#         start_ts = s.get("start_date") or s.get("created")
#         start_iso = to_iso_from_ts(start_ts)

#         cpe_ts = s.get("current_period_end")
#         cpe_dt = to_dt_from_ts(cpe_ts)
#         cpe_iso = cpe_dt.isoformat().replace("+00:00", "Z") if cpe_dt else None

#         price_id, nickname, amount, amount_decimal, currency = safe_get_price_info(s)
#         exp = currency_exponent(currency)
#         formatted_amount = format_currency_amount_from_minor(amount, currency, exp, amount_decimal)

#         normalized.append({
#             "Subscription Id": sub_id,
#             "Customer Id": customer_id,
#             "Customer Email": email,
#             "Customer First Name": first,
#             "Customer Last Name": last,
#             "Start Date Iso": start_iso,
#             "Current Period End Iso": cpe_iso,
#             "Price Id": price_id,
#             "Price Nickname": nickname,
#             "Subscription Amount": formatted_amount,
#             "Subscription Currency": currency.upper() if currency else None
#         })

#     return {
#         "totalCount": len(normalized),
#         "subscriptions": normalized
#     }

# # ---------------- HEALTH CHECK ----------------

# @app.get("/")
# def root():
#     return {"status": "Stripe Subscription API Running"}





from fastapi import FastAPI, HTTPException
import requests
import datetime
import calendar
import os
import time
from decimal import Decimal
from dotenv import load_dotenv

load_dotenv()
app = FastAPI()

# ---------------- CONFIG ----------------

BASE_URL = "https://api.stripe.com/v1/subscriptions"
PAGE_LIMIT = 100
TIMEOUT = 30
MAX_RETRIES = 5

# ---------------- HEADERS ----------------

def get_headers():
    stripe_secret = os.environ.get("STRIPE_SECRET")
    if not stripe_secret:
        raise HTTPException(status_code=500, detail="Missing STRIPE_SECRET in environment")
    return {"Authorization": f"Bearer {stripe_secret}"}

# ---------------- TIME HELPERS ----------------

def add_months(dt, months):
    year = dt.year + (dt.month - 1 + months) // 12
    month = (dt.month - 1 + months) % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return datetime.datetime(year, month, day, dt.hour, dt.minute, dt.second, tzinfo=dt.tzinfo)

def to_iso_from_ts(ts):
    if ts is None:
        return None
    try:
        dt = datetime.datetime.fromtimestamp(int(ts), datetime.timezone.utc)
        return dt.isoformat().replace("+00:00", "Z")
    except Exception:
        return None

def to_dt_from_ts(ts):
    if ts is None:
        return None
    try:
        return datetime.datetime.fromtimestamp(int(ts), datetime.timezone.utc)
    except Exception:
        return None

# ---------------- CURRENCY HELPERS ----------------

_CURRENCY_EXPONENTS = {
    0: {"BIF","CLP","DJF","GNF","JPY","KMF","KRW","MGA","PYG","RWF","UGX","VND","VUV","XAF","XOF","XPF"},
    3: {"BHD","IQD","JOD","KWD","LYD","OMR","TND"}
}

_CURRENCY_SYMBOLS = {
    "USD":"$", "EUR":"€", "GBP":"£", "JPY":"¥", "CAD":"$", "AUD":"$",
    "CHF":"CHF ", "INR":"₹", "PKR":"Rs ", "CNY":"¥"
}

def currency_exponent(currency_code):
    if not currency_code:
        return 2
    c = currency_code.upper()
    for exp, codes in _CURRENCY_EXPONENTS.items():
        if c in codes:
            return exp
    return 2

def format_currency_amount_from_minor(minor_amount, currency_code, exponent, as_decimal_str=None):
    try:
        if as_decimal_str:
            minor = Decimal(str(as_decimal_str))
        else:
            minor = Decimal(int(minor_amount))
    except Exception:
        return None

    scale = Decimal(10) ** Decimal(exponent)
    major = (minor / scale).normalize()
    major_str = format(major, "f")

    if "." in major_str:
        int_part, frac = major_str.split(".", 1)
        frac = frac.rstrip("0")
        if len(frac) < exponent:
            frac = frac.ljust(exponent, "0")
        major_str = f"{int_part}.{frac}" if exponent > 0 else int_part
    else:
        if exponent > 0:
            major_str = major_str + "." + ("0" * exponent)

    sym = _CURRENCY_SYMBOLS.get((currency_code or "").upper())
    return f"{sym}{major_str}" if sym else f"{currency_code.upper()} {major_str}"

# ---------------- STRIPE PARSER ----------------

def safe_get_price_info(sub):
    price_id = None
    nickname = None
    amount = None
    amount_decimal = None
    currency = None

    items = sub.get("items", {}).get("data") or []
    if items:
        price = items[0].get("price") or items[0].get("plan") or {}
        price_id = price.get("id")
        nickname = price.get("nickname")
        amount = price.get("unit_amount") or price.get("amount")
        amount_decimal = price.get("unit_amount_decimal")
        currency = price.get("currency")

    if not currency:
        invoice = sub.get("latest_invoice")
        if isinstance(invoice, dict):
            currency = invoice.get("currency")

    return price_id, nickname, amount, amount_decimal, currency

# ---------------- STRIPE FETCH ----------------

def fetch_all_subscriptions():
    headers = get_headers()
    all_subs = []
    has_more = True
    starting_after = None

    while has_more:
        params = [
            ("status", "active"),
            ("limit", PAGE_LIMIT),
            ("expand[]", "data.customer"),
            ("expand[]", "data.latest_invoice"),
        ]

        if starting_after:
            params.append(("starting_after", starting_after))

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = requests.get(BASE_URL, headers=headers, params=params, timeout=TIMEOUT)
            except Exception:
                if attempt == MAX_RETRIES:
                    raise
                time.sleep(1.5 * attempt)
                continue

            if resp.status_code == 200:
                data = resp.json()
                break
            elif resp.status_code in (429, 502, 503, 504):
                time.sleep(1.5 * (2 ** (attempt - 1)))
            else:
                raise HTTPException(status_code=resp.status_code, detail=resp.text)

        items = data.get("data", [])
        all_subs.extend(items)

        has_more = data.get("has_more", False)
        starting_after = items[-1]["id"] if has_more and items else None

    return all_subs

# ---------------- MAIN ROUTE ----------------

@app.get("/subscriptions")
def get_subscriptions():
    subs = fetch_all_subscriptions()
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    normalized = []

    for s in subs:
        # -------- CUSTOMER --------
        customer = s.get("customer")
        customer_id = None
        email = None
        first = None
        last = None

        if isinstance(customer, dict):
            customer_id = customer.get("id")
            email = customer.get("email")
            name = (customer.get("name") or "").strip()
            if name:
                parts = name.split(" ", 1)
                first = parts[0]
                last = parts[1] if len(parts) > 1 else ""

        # -------- START / PERIOD --------
        start_ts = s.get("start_date") or s.get("created")
        start_iso = to_iso_from_ts(start_ts)

        cpe_ts = s.get("current_period_end")
        cpe_dt = to_dt_from_ts(cpe_ts) if cpe_ts else None

        # -------- INTERVAL DETECTION --------
        interval = None
        interval_count = None

        plan = s.get("plan") or {}
        if isinstance(plan, dict):
            interval = plan.get("interval")
            interval_count = plan.get("interval_count")

        items_node = s.get("items", {}).get("data") or []
        if items_node:
            p = items_node[0].get("plan") or items_node[0].get("price") or {}
            if isinstance(p, dict):
                recurring = p.get("recurring") or {}
                interval = interval or recurring.get("interval")
                interval_count = interval_count or recurring.get("interval_count")

        try:
            interval_count = int(interval_count) if interval_count else None
        except Exception:
            interval_count = None

        # -------- REBUILD CURRENT PERIOD END --------
        if not cpe_dt or (start_ts and cpe_dt and to_dt_from_ts(start_ts) >= cpe_dt):
            if start_ts and interval and interval_count:
                try:
                    dt_start = to_dt_from_ts(start_ts)
                    if interval == "day":
                        cpe_dt = dt_start + datetime.timedelta(days=interval_count)
                    elif interval == "week":
                        cpe_dt = dt_start + datetime.timedelta(weeks=interval_count)
                    elif interval == "month":
                        cpe_dt = add_months(dt_start, interval_count)
                    elif interval == "year":
                        cpe_dt = add_months(dt_start, interval_count * 12)
                except Exception:
                    cpe_dt = None

            if not cpe_dt:
                invoice = s.get("latest_invoice")
                if isinstance(invoice, dict):
                    end_ts = invoice.get("period_end") or \
                             (invoice.get("lines", {}).get("data") or [{}])[0].get("period", {}).get("end")
                    if end_ts:
                        cpe_dt = to_dt_from_ts(end_ts)

        cpe_iso = cpe_dt.isoformat().replace("+00:00", "Z") if cpe_dt else None

        # -------- PRICE --------
        price_id, nickname, amount, amount_decimal, currency = safe_get_price_info(s)
        exp = currency_exponent(currency)
        formatted_amount = format_currency_amount_from_minor(amount, currency, exp, amount_decimal)

        # -------- REMINDERS --------
        reminder_48_iso = None
        reminder_24_iso = None

        if cpe_dt:
            start_dt = to_dt_from_ts(start_ts)
            if start_dt:
                duration = cpe_dt - start_dt
                days = duration.total_seconds() / 86400

                if days >= 2.5:
                    rem48 = cpe_dt - datetime.timedelta(hours=48)
                    rem24 = cpe_dt - datetime.timedelta(hours=24)
                elif days >= 2.0:
                    rem48 = start_dt + datetime.timedelta(seconds=duration.total_seconds() * 0.5)
                    rem24 = start_dt + datetime.timedelta(seconds=duration.total_seconds() * 0.75)
                else:
                    rem48 = start_dt + datetime.timedelta(seconds=duration.total_seconds() * 0.33)
                    rem24 = start_dt + datetime.timedelta(seconds=duration.total_seconds() * 0.66)

                if start_dt < rem48 < cpe_dt:
                    reminder_48_iso = rem48.isoformat().replace("+00:00", "Z")
                if start_dt < rem24 < cpe_dt:
                    reminder_24_iso = rem24.isoformat().replace("+00:00", "Z")

        # -------- OUTPUT --------
        normalized.append({
            "Subscription Id": s.get("id"),
            "Customer Id": customer_id,
            "Customer Email": email,
            "Customer First Name": first,
            "Customer Last Name": last,
            "Start Date Iso": start_iso,
            "Current Period End Iso": cpe_iso,
            "Plan Interval": interval,
            "Plan Interval Count": interval_count,
            "Price Id": price_id,
            "Price Nickname": nickname,
            "Subscription Amount": formatted_amount,
            "Subscription Amount Raw (minor unit)": amount,
            "Subscription Amount Decimal (minor unit string)": amount_decimal,
            "Subscription Currency": currency.upper() if currency else None,
            "48 hour reminder date": reminder_48_iso,
            "24 hour reminder date": reminder_24_iso
        })

    return {
        "totalCount": len(normalized),
        "subscriptions": normalized
    }

# ---------------- HEALTH ----------------

@app.get("/")
def root():
    return {"status": "Stripe Subscription API Running"}
