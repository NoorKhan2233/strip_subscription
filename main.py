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

def to_dt(ts):
    if not ts:
        return None
    return datetime.datetime.fromtimestamp(int(ts), datetime.timezone.utc)

def to_iso(dt):
    if not dt:
        return None
    return dt.isoformat().replace("+00:00", "Z")


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


# ---------------- INVOICE FETCH ----------------

def _fetch_all_invoices_for_subscription(subscription_id, headers):
    print(f"Fetching all invoices for subscription: {subscription_id}")
    all_invoices = []
    starting_after = None
    has_more = True
    INVOICE_BASE_URL = "https://api.stripe.com/v1/invoices"
    page_count = 0

    while has_more:
        page_count += 1
        params = [("subscription", subscription_id), ("limit", PAGE_LIMIT)]
        if starting_after:
            params.append(("starting_after", starting_after))

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = requests.get(INVOICE_BASE_URL, headers=headers, params=params, timeout=TIMEOUT)
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
        all_invoices.extend(items)
        print(f"  Fetched invoice page {page_count} ({len(items)} items) for {subscription_id}. Total invoices so far: {len(all_invoices)}")

        has_more = data.get("has_more", False)
        starting_after = items[-1]["id"] if has_more and items else None

    print(f"Finished fetching invoices for {subscription_id}. Total: {len(all_invoices)}")
    return all_invoices


# ---------------- SUBSCRIPTION FETCH ----------------

def fetch_all_subscriptions(headers):
    print("Starting to fetch all subscriptions...")
    all_subs = []
    starting_after = None
    has_more = True
    page_count = 0

    while has_more:
        page_count += 1
        params = [("status", "active"), ("limit", PAGE_LIMIT), ("expand[]", "data.customer")]
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
        print(f"Fetched subscription page {page_count} ({len(items)} items). Total subscriptions so far: {len(all_subs)}")

        has_more = data.get("has_more", False)
        starting_after = items[-1]["id"] if has_more and items else None

    print(f"Finished fetching all subscriptions. Total: {len(all_subs)}")
    return all_subs


# ---------------- INTERVAL HELPERS ----------------

def get_interval_info(s):
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

    return interval, interval_count


# ---------------- MAIN ROUTE ----------------

@app.get("/subscriptions")
def get_subscriptions():
    headers = get_headers()
    subs = fetch_all_subscriptions(headers)
    normalized = []

    for i, s in enumerate(subs):
        print(f"Processing subscription {i+1}/{len(subs)}: {s.get('id')}")

        # -------- CUSTOMER --------
        customer = s.get("customer") or {}
        customer_id = customer.get("id")
        email = customer.get("email")
        name = (customer.get("name") or "").strip()
        first = name.split(" ", 1)[0] if name else None
        last = name.split(" ", 1)[1] if name and len(name.split(" ", 1)) > 1 else None

        # -------- START DATE --------
        start_ts = s.get("start_date") or s.get("created")
        start_iso = to_iso(to_dt(start_ts))

        # -------- INTERVAL --------
        interval, interval_count = get_interval_info(s)

        # -------- PRICE --------
        price_id, nickname, amount, amount_decimal, currency = safe_get_price_info(s)
        exp = currency_exponent(currency)
        formatted_amount = format_currency_amount_from_minor(amount, currency, exp, amount_decimal)

        # -------- INVOICES --------
        all_invoices = _fetch_all_invoices_for_subscription(s["id"], headers)
        processed_periods = set()

        if not all_invoices:
            # Fallback to subscription's current_period_start/end
            cps = to_dt(s.get("current_period_start"))
            cpe = to_dt(s.get("current_period_end"))
            if cps and cpe:
                reminder_48 = cpe - datetime.timedelta(hours=48)
                reminder_24 = cpe - datetime.timedelta(hours=24)
                normalized.append({
                    "Subscription Id": s.get("id"),
                    "Customer Id": customer_id,
                    "Customer Email": email,
                    "Customer First Name": first,
                    "Customer Last Name": last,
                    "Start Date Iso": start_iso,
                    "Current Period End Iso": to_iso(cpe),
                    "Plan Interval": interval,
                    "Plan Interval Count": interval_count,
                    "Price Id": price_id,
                    "Price Nickname": nickname,
                    "Subscription Amount": formatted_amount,
                    "Subscription Amount Raw (minor unit)": amount,
                    "Subscription Amount Decimal (minor unit string)": amount_decimal,
                    "Subscription Currency": currency.upper() if currency else None,
                    "48 hour reminder date": to_iso(reminder_48),
                    "24 hour reminder date": to_iso(reminder_24),
                })
        else:
            for invoice in all_invoices:
                lines = invoice.get("lines", {}).get("data", [])
                for line in lines:
                    period = line.get("period") or {}
                    start_period_ts = period.get("start")
                    end_ts = period.get("end")

                    current_period_key = (start_period_ts, end_ts)

                    if start_period_ts and end_ts and current_period_key not in processed_periods:
                        cpe = to_dt(end_ts)
                        if cpe:
                            reminder_48 = cpe - datetime.timedelta(hours=48)
                            reminder_24 = cpe - datetime.timedelta(hours=24)
                            normalized.append({
                                "Subscription Id": s.get("id"),
                                "Customer Id": customer_id,
                                "Customer Email": email,
                                "Customer First Name": first,
                                "Customer Last Name": last,
                                "Start Date Iso": start_iso,
                                "Current Period End Iso": to_iso(cpe),
                                "Plan Interval": interval,
                                "Plan Interval Count": interval_count,
                                "Price Id": price_id,
                                "Price Nickname": nickname,
                                "Subscription Amount": formatted_amount,
                                "Subscription Amount Raw (minor unit)": amount,
                                "Subscription Amount Decimal (minor unit string)": amount_decimal,
                                "Subscription Currency": currency.upper() if currency else None,
                                "48 hour reminder date": to_iso(reminder_48),
                                "24 hour reminder date": to_iso(reminder_24),
                            })
                            processed_periods.add(current_period_key)

    return {"totalCount": len(normalized), "subscriptions": normalized}


# ---------------- HEALTH ----------------

@app.get("/")
def root():
    return {"status": "Stripe Subscription API Running"}