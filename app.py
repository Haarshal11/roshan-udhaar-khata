"""
Roshan General Store - Credit Ledger (Udhaar Website)
A production-ready Streamlit app for managing shop credit (Udhaar Khata).
Local CSV storage with automatic 2-way Google Sheets cloud recovery & sync.
"""

import streamlit as st
import pandas as pd
import uuid
import os
import json
import urllib.parse
from decimal import Decimal, ROUND_HALF_UP
from datetime import date, datetime

# ─────────────────────────────────────────────
# PAGE CONFIG (must be first Streamlit call)
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Roshan's Store - Udhaar Khata",
    page_icon="🏪",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────
TRANSACTIONS_FILE = "roshan_all_transactions.csv"
TOTALS_FILE = "roshan_customer_totals.csv"
DELETED_LOG_FILE = "roshan_deleted_log.csv"
DEFAULT_PIN = "1234"

TRANSACTIONS_COLUMNS = [
    "transaction_id",
    "customer_name",
    "phone_number",
    "date",
    "product_details",
    "transaction_type",
    "amount",
    "running_balance",
    "timestamp",
]

TOTALS_COLUMNS = [
    "customer_name",
    "phone_number",
    "total_credit",
    "total_paid",
    "net_pending",
    "last_updated",
]

DELETED_COLUMNS = TRANSACTIONS_COLUMNS + ["deleted_at"]

# ─────────────────────────────────────────────
# CUSTOM CSS – Mobile-optimised styling
# ─────────────────────────────────────────────
st.markdown(
    """
    <style>
        /* ── General layout ── */
        .main .block-container { padding-top: 1rem; padding-bottom: 2rem; }

        /* ── Big metric cards ── */
        div[data-testid="metric-container"] {
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            border: 1px solid #0f3460;
            border-radius: 12px;
            padding: 16px 20px;
            color: #e94560;
        }
        div[data-testid="metric-container"] label {
            color: #a8b2d8 !important;
            font-size: 0.85rem !important;
        }
        div[data-testid="metric-container"] [data-testid="stMetricValue"] {
            font-size: 1.8rem !important;
            font-weight: 700 !important;
            color: #e94560 !important;
        }

        /* ── Buttons ── */
        .stButton > button {
            width: 100%;
            border-radius: 10px;
            padding: 0.55rem 1rem;
            font-weight: 600;
        }

        /* ── Success banner ── */
        .success-banner {
            background: #d4edda;
            border: 1px solid #28a745;
            border-radius: 10px;
            padding: 14px 18px;
            color: #155724;
            font-size: 1.1rem;
            font-weight: 600;
            margin: 12px 0;
        }

        /* ── Credit / payment row colours applied via HTML tables ── */
        .credit-row  { background-color: #fff0f0 !important; color: #1a1a1a !important; }
        .payment-row { background-color: #f0fff4 !important; color: #1a1a1a !important; }

        /* ── Total-pending hero ── */
        .hero-pending {
            background: linear-gradient(135deg, #e94560, #0f3460);
            border-radius: 16px;
            padding: 24px 32px;
            text-align: center;
            color: white;
            margin-bottom: 20px;
        }
        .hero-pending h1 { margin: 0; font-size: 3rem; font-weight: 800; color: white; }
        .hero-pending p  { margin: 4px 0 0; font-size: 1rem; opacity: 0.9; color: white; }

        /* ── Tabs ── */
        button[data-baseweb="tab"] { font-size: 0.95rem; font-weight: 600; }

        /* ── Hide Streamlit default footer ── */
        footer { visibility: hidden; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────
# SANITISATION & FORMATTING HELPERS
# ─────────────────────────────────────────────

def to_decimal(value) -> Decimal:
    """Convert any numeric value to a Decimal with 2 decimal places."""
    try:
        if value is None or str(value).strip() == "" or str(value).strip().lower() == "nan":
            return Decimal("0.00")
        clean_val = str(value).replace(",", "").replace("₹", "").strip()
        return Decimal(clean_val).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal("0.00")


def fmt_inr(value) -> str:
    """Format a number in true Indian numbering system (e.g. ₹1,23,456.78)."""
    d = to_decimal(value)
    abs_val = abs(d)
    s = f"{abs_val:.2f}"
    integer_part, decimal_part = s.split(".")
    
    if len(integer_part) > 3:
        last_three = integer_part[-3:]
        other_numbers = integer_part[:-3]
        groups = []
        while len(other_numbers) > 2:
            groups.insert(0, other_numbers[-2:])
            other_numbers = other_numbers[:-2]
        if other_numbers:
            groups.insert(0, other_numbers)
        formatted_int = ",".join(groups) + "," + last_three
    else:
        formatted_int = integer_part

    res = f"₹{formatted_int}.{decimal_part}"
    return res if d >= 0 else f"-{res}"


def normalize_name(name: str) -> str:
    """Convert any customer name into clean Title Case without extra spaces."""
    if not name or str(name).strip().lower() == "nan":
        return ""
    return " ".join(str(name).strip().split()).title()


def clean_phone(phone) -> str:
    """Safely convert phone numbers (including float/int from Sheets/Pandas) into a clean string."""
    if phone is None:
        return ""
    s = str(phone).strip()
    if s.lower() in ("nan", "none", ""):
        return ""
    if s.endswith(".0"):
        s = s[:-2]
    digits = "".join(filter(str.isdigit, s))
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    return digits if digits else s


# ─────────────────────────────────────────────
# GOOGLE SHEETS CLIENT & CLOUD RECOVERY
# ─────────────────────────────────────────────

def get_gspread_client():
    """Try to initialise a gspread client. Returns (client, status_message)."""
    try:
        import gspread
        from google.oauth2.service_account import Credentials

        SCOPES = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]

        creds_dict = None
        if "gcp_service_account" in st.secrets:
            creds_dict = dict(st.secrets["gcp_service_account"])
        elif os.path.exists("credentials.json"):
            with open("credentials.json", "r") as f:
                creds_dict = json.load(f)

        if creds_dict is None:
            return None, "No credentials found"

        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        client = gspread.authorize(creds)
        return client, "OK"
    except ImportError:
        return None, "gspread not installed"
    except Exception as e:
        return None, str(e)


def get_spreadsheet_id() -> str:
    """Return configured spreadsheet ID or empty string."""
    if "SPREADSHEET_ID" in st.secrets:
        return str(st.secrets["SPREADSHEET_ID"]).strip()
    if os.path.exists("spreadsheet_id.txt"):
        with open("spreadsheet_id.txt") as f:
            return f.read().strip()
    return ""


def ensure_worksheet(spreadsheet, title: str, headers: list):
    """Get or create a worksheet and write headers if brand new."""
    try:
        ws = spreadsheet.worksheet(title)
    except Exception:
        ws = spreadsheet.add_worksheet(title=title, rows=1000, cols=max(len(headers), 10))
        ws.append_row(headers)
    return ws


# ─────────────────────────────────────────────
# CSV & DATA HELPERS
# ─────────────────────────────────────────────

def save_transactions(df: pd.DataFrame):
    df.to_csv(TRANSACTIONS_FILE, index=False)


def save_totals(df: pd.DataFrame):
    df.to_csv(TOTALS_FILE, index=False)


def save_deleted_log(df: pd.DataFrame):
    df.to_csv(DELETED_LOG_FILE, index=False)


def recalculate_customer(customer_name: str, all_tx: pd.DataFrame) -> dict:
    """Re-compute totals for a single customer from the transactions dataframe."""
    norm_target = normalize_name(customer_name)
    cust_tx = all_tx[all_tx["customer_name"].apply(normalize_name) == norm_target].copy()
    if cust_tx.empty:
        return None

    total_credit = sum(
        to_decimal(r["amount"])
        for _, r in cust_tx.iterrows()
        if str(r["transaction_type"]).strip().lower() == "credit"
    )
    total_paid = sum(
        to_decimal(r["amount"])
        for _, r in cust_tx.iterrows()
        if str(r["transaction_type"]).strip().lower() == "payment"
    )
    net_pending = total_credit - total_paid

    # Latest non-empty phone number recorded
    phone = ""
    for _, r in cust_tx.iterrows():
        p = clean_phone(r.get("phone_number", ""))
        if p:
            phone = p

    return {
        "customer_name": norm_target,
        "phone_number": phone,
        "total_credit": str(total_credit),
        "total_paid": str(total_paid),
        "net_pending": str(net_pending),
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def rebuild_all_data(all_tx: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Normalise all customer names, clean phone numbers, recalculate running balances
    for every customer, and rebuild the entire SUMMARY totals dataframe from scratch.
    """
    if all_tx.empty:
        empty_tx = pd.DataFrame(columns=TRANSACTIONS_COLUMNS)
        empty_totals = pd.DataFrame(columns=TOTALS_COLUMNS)
        return empty_tx, empty_totals

    for col in TRANSACTIONS_COLUMNS:
        if col not in all_tx.columns:
            all_tx[col] = ""

    all_tx = all_tx[TRANSACTIONS_COLUMNS].copy()
    all_tx["customer_name"] = all_tx["customer_name"].apply(normalize_name)
    all_tx["phone_number"] = all_tx["phone_number"].apply(clean_phone)
    all_tx["transaction_type"] = all_tx["transaction_type"].astype(str).str.strip().str.lower()

    # Remove blank customer rows if any
    all_tx = all_tx[all_tx["customer_name"] != ""].reset_index(drop=True)

    totals_rows = []
    customers = sorted(all_tx["customer_name"].unique().tolist())

    for cname in customers:
        idx = all_tx[all_tx["customer_name"] == cname].index
        cust_rows = all_tx.loc[idx].copy()
        cust_rows["_sort_ts"] = pd.to_datetime(cust_rows["timestamp"], errors="coerce")
        cust_rows = cust_rows.sort_values("_sort_ts")

        balance = Decimal("0.00")
        for i in cust_rows.index:
            amt = to_decimal(all_tx.at[i, "amount"])
            tx_type = all_tx.at[i, "transaction_type"]
            if tx_type == "credit":
                balance += amt
            else:
                balance -= amt
            all_tx.at[i, "amount"] = str(amt)
            all_tx.at[i, "running_balance"] = str(balance)

        t_dict = recalculate_customer(cname, all_tx)
        if t_dict:
            totals_rows.append(t_dict)

    totals_df = pd.DataFrame(totals_rows, columns=TOTALS_COLUMNS) if totals_rows else pd.DataFrame(columns=TOTALS_COLUMNS)
    return all_tx, totals_df


def load_from_google_sheets() -> tuple[bool, str]:
    """
    Pull all transactions from Google Sheets ALL_TRANSACTIONS tab and rebuild local CSVs.
    Prevents data loss when Streamlit Cloud restarts.
    """
    try:
        client, status = get_gspread_client()
        if client is None:
            return False, f"Client not ready: {status}"

        spreadsheet_id = get_spreadsheet_id()
        if not spreadsheet_id:
            return False, "No SPREADSHEET_ID"

        spreadsheet = client.open_by_key(spreadsheet_id)
        try:
            ws_all = spreadsheet.worksheet("ALL_TRANSACTIONS")
        except Exception:
            return False, "ALL_TRANSACTIONS tab not found in Sheet yet."

        raw_values = ws_all.get_all_values()
        if len(raw_values) <= 1:
            return True, "Sheet is empty (0 transactions)."

        headers = raw_values[0]
        data_rows = raw_values[1:]
        df = pd.DataFrame(data_rows, columns=headers)

        all_tx, totals_df = rebuild_all_data(df)
        save_transactions(all_tx)
        save_totals(totals_df)
        return True, f"Restored {len(all_tx)} transactions for {len(totals_df)} customers from Google Sheets."
    except Exception as e:
        return False, str(e)


def load_transactions() -> pd.DataFrame:
    """Load all transactions from CSV, cleaning types on read."""
    if os.path.exists(TRANSACTIONS_FILE):
        try:
            df = pd.read_csv(TRANSACTIONS_FILE, dtype=str).fillna("")
            for col in TRANSACTIONS_COLUMNS:
                if col not in df.columns:
                    df[col] = ""
            df["customer_name"] = df["customer_name"].apply(normalize_name)
            df["phone_number"] = df["phone_number"].apply(clean_phone)
            return df[TRANSACTIONS_COLUMNS]
        except Exception:
            pass
    return pd.DataFrame(columns=TRANSACTIONS_COLUMNS)


def load_totals() -> pd.DataFrame:
    """Load customer totals from CSV, cleaning types on read."""
    if os.path.exists(TOTALS_FILE):
        try:
            df = pd.read_csv(TOTALS_FILE, dtype=str).fillna("")
            for col in TOTALS_COLUMNS:
                if col not in df.columns:
                    df[col] = ""
            df["customer_name"] = df["customer_name"].apply(normalize_name)
            df["phone_number"] = df["phone_number"].apply(clean_phone)
            return df[TOTALS_COLUMNS]
        except Exception:
            pass
    return pd.DataFrame(columns=TOTALS_COLUMNS)


def load_deleted_log() -> pd.DataFrame:
    """Load deleted entries audit log."""
    if os.path.exists(DELETED_LOG_FILE):
        try:
            df = pd.read_csv(DELETED_LOG_FILE, dtype=str).fillna("")
            for col in DELETED_COLUMNS:
                if col not in df.columns:
                    df[col] = ""
            return df[DELETED_COLUMNS]
        except Exception:
            pass
    return pd.DataFrame(columns=DELETED_COLUMNS)


def sync_to_google_sheets() -> tuple[bool, str]:
    """
    Full sync: rebuild clean data and upload all local CSV data to Google Sheets.
    Returns (success: bool, message: str).
    """
    try:
        client, status = get_gspread_client()
        if client is None:
            return False, f"Not configured: {status}"

        spreadsheet_id = get_spreadsheet_id()
        if not spreadsheet_id:
            return False, "SPREADSHEET_ID not configured"

        spreadsheet = client.open_by_key(spreadsheet_id)
        all_tx = load_transactions()
        all_tx, totals = rebuild_all_data(all_tx)
        save_transactions(all_tx)
        save_totals(totals)

        # ── ALL_TRANSACTIONS sheet ──
        ws_all = ensure_worksheet(spreadsheet, "ALL_TRANSACTIONS", TRANSACTIONS_COLUMNS)
        ws_all.clear()
        ws_all.append_row(TRANSACTIONS_COLUMNS)
        if not all_tx.empty:
            ws_all.append_rows(all_tx.fillna("").values.tolist())

        # ── SUMMARY sheet ──
        ws_summary = ensure_worksheet(spreadsheet, "SUMMARY", TOTALS_COLUMNS)
        ws_summary.clear()
        ws_summary.append_row(TOTALS_COLUMNS)
        if not totals.empty:
            ws_summary.append_rows(totals.fillna("").values.tolist())

        # ── Per-customer sheets ──
        customer_headers = [
            "Date", "Product / Details", "Credit (₹)", "Payment (₹)",
            "Running Balance (₹)", "Timestamp",
        ]
        customers = all_tx["customer_name"].dropna().unique()
        active_safe_names = {"ALL_TRANSACTIONS", "SUMMARY", "Sheet1"}

        for cname in customers:
            cust_tx = all_tx[all_tx["customer_name"] == cname].copy()
            cust_tx["_sort_ts"] = pd.to_datetime(cust_tx["timestamp"], errors="coerce")
            cust_tx = cust_tx.sort_values("_sort_ts")

            rows = []
            for _, r in cust_tx.iterrows():
                credit_amt  = r["amount"] if r["transaction_type"] == "credit"  else ""
                payment_amt = r["amount"] if r["transaction_type"] == "payment" else ""
                rows.append([
                    r["date"],
                    r["product_details"],
                    credit_amt,
                    payment_amt,
                    r["running_balance"],
                    r["timestamp"],
                ])

            safe_name = str(cname)[:31].replace("/", "-").replace("\\", "-").replace(":", "-")
            active_safe_names.add(safe_name)
            ws_cust = ensure_worksheet(spreadsheet, safe_name, customer_headers)
            ws_cust.clear()
            ws_cust.append_row(customer_headers)
            if rows:
                ws_cust.append_rows(rows)

        return True, f"Synced {len(all_tx)} transactions across {len(customers)} customer(s)."
    except Exception as e:
        return False, str(e)


# ─────────────────────────────────────────────
# CORE TRANSACTION ACTIONS
# ─────────────────────────────────────────────

def add_transaction(
    customer_name: str,
    phone_number: str,
    tx_date: str,
    product_details: str,
    tx_type: str,  # "credit" or "payment"
    amount: Decimal,
) -> dict:
    """Append a new transaction, normalize names, update totals, and return result dict."""
    norm_name = normalize_name(customer_name)
    cleaned_phone = clean_phone(phone_number)

    all_tx = load_transactions()

    # Keep previous phone if none passed now
    if not cleaned_phone and not all_tx.empty:
        existing_rows = all_tx[all_tx["customer_name"] == norm_name]
        for _, r in existing_rows.iterrows():
            p = clean_phone(r.get("phone_number", ""))
            if p:
                cleaned_phone = p

    tx_id = str(uuid.uuid4())[:8].upper()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    new_row = {
        "transaction_id": tx_id,
        "customer_name": norm_name,
        "phone_number": cleaned_phone,
        "date": tx_date,
        "product_details": product_details.strip() if product_details else "(no details)",
        "transaction_type": tx_type,
        "amount": str(amount),
        "running_balance": "0.00",
        "timestamp": now_str,
    }

    all_tx = pd.concat([all_tx, pd.DataFrame([new_row])], ignore_index=True)

    # If a new phone number was provided, update all records for this customer
    if cleaned_phone:
        all_tx.loc[all_tx["customer_name"] == norm_name, "phone_number"] = cleaned_phone

    all_tx, totals = rebuild_all_data(all_tx)
    save_transactions(all_tx)
    save_totals(totals)

    cust_total_row = totals[totals["customer_name"] == norm_name]
    new_balance = to_decimal(cust_total_row.iloc[0]["net_pending"]) if not cust_total_row.empty else Decimal("0.00")

    return {
        "success": True,
        "customer_name": norm_name,
        "new_balance": new_balance,
        "tx_id": tx_id,
    }


def delete_transaction(tx_id: str) -> bool:
    """Remove a transaction by ID, rebuild running balances & totals, and log deletion."""
    all_tx = load_transactions()
    target = all_tx[all_tx["transaction_id"] == tx_id]
    if target.empty:
        return False

    # Log deletion
    deleted_log = load_deleted_log()
    deleted_row = target.copy()
    deleted_row["deleted_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    deleted_log = pd.concat([deleted_log, deleted_row], ignore_index=True)
    save_deleted_log(deleted_log)

    # Remove from main DF and rebuild
    all_tx = all_tx[all_tx["transaction_id"] != tx_id].reset_index(drop=True)
    all_tx, totals = rebuild_all_data(all_tx)
    save_transactions(all_tx)
    save_totals(totals)
    return True


# ─────────────────────────────────────────────
# WHATSAPP MESSAGE GENERATOR
# ─────────────────────────────────────────────

def generate_whatsapp_url(
    phone: str,
    customer_name: str,
    pending_balance: Decimal,
    cust_tx: pd.DataFrame,
) -> str:
    """Build a WhatsApp URL with a pre-filled payment reminder message."""
    credits = cust_tx[cust_tx["transaction_type"] == "credit"].copy()
    credits["_sort_ts"] = pd.to_datetime(credits["timestamp"], errors="coerce")
    credits = credits.sort_values("_sort_ts", ascending=False).head(5)

    items_lines = ""
    for _, r in credits.iterrows():
        items_lines += (
            f"\n  • {r['date']} | {r['product_details']} | {fmt_inr(r['amount'])}"
        )

    msg = (
        f"🙏 Namaste {customer_name} Ji,\n\n"
        f"This is a gentle reminder from *Roshan General Store*.\n\n"
        f"Recent credit entries:{items_lines}\n\n"
        f"💰 *Total Pending Balance: {fmt_inr(pending_balance)}*\n\n"
        f"Kindly arrange the payment at your earliest convenience.\n\n"
        f"Thank you! 🙏\n"
        f"- Roshan General Store"
    )

    phone_clean = clean_phone(phone)
    if len(phone_clean) == 10:
        phone_clean = "91" + phone_clean

    encoded_msg = urllib.parse.quote(msg)
    return f"https://wa.me/{phone_clean}?text={encoded_msg}"


# ─────────────────────────────────────────────
# SESSION STATE & STARTUP CLOUD RECOVERY
# ─────────────────────────────────────────────

def init_session_state():
    defaults = {
        "pin_verified": False,
        "last_save_msg": None,
        "confirm_delete_id": None,
        "sync_status": None,
        "cloud_bootstrapped": False,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val

    # Auto-restore from Google Sheets on fresh container boot if local CSV is empty/missing
    if not st.session_state["cloud_bootstrapped"]:
        st.session_state["cloud_bootstrapped"] = True
        local_tx = load_transactions()
        if local_tx.empty:
            load_from_google_sheets()
        else:
            # Ensure existing local data is normalized cleanly
            clean_tx, clean_totals = rebuild_all_data(local_tx)
            save_transactions(clean_tx)
            save_totals(clean_totals)


init_session_state()

# ─────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────

st.markdown(
    "<h2 style='text-align:center;margin-bottom:0'>🏪 Roshan General Store</h2>"
    "<p style='text-align:center;color:#888;margin-top:2px'>Credit Ledger – Udhaar Khata</p>",
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────
# TABS
# ─────────────────────────────────────────────

tab_home, tab_khata, tab_reports, tab_manage, tab_sync = st.tabs([
    "🏠 Home / Add Entry",
    "👤 Customer Khata",
    "📊 Summary & Reports",
    "🛡️ Manage / Delete",
    "☁️ Google Sheets Sync",
])

# ══════════════════════════════════════════════
# TAB 1 – HOME / ADD ENTRY
# ══════════════════════════════════════════════
with tab_home:

    all_tx = load_transactions()
    totals = load_totals()

    # ── Hero metric: Total Market Pending ──
    if not totals.empty:
        # Only sum positive pending balances so advances don't artificially hide debt, or sum net
        total_pending = sum(to_decimal(v) for v in totals["net_pending"])
    else:
        total_pending = Decimal("0.00")

    st.markdown(
        f"""
        <div class="hero-pending">
            <p>📌 Total Market Pending (All Customers)</p>
            <h1>{fmt_inr(total_pending)}</h1>
            <p>Across {len(totals)} customer(s)</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Instant Search ──
    st.markdown("### 🔍 Quick Customer Search")
    search_name = st.text_input(
        "Type customer name or phone to see balance",
        placeholder="e.g. Shubham, Ramesh, 98765…",
        key="search_name_input",
    )

    if search_name.strip():
        q = search_name.strip()
        matched = totals[
            totals["customer_name"].str.contains(q, case=False, na=False)
            | totals["phone_number"].str.contains(q, case=False, na=False)
        ]
        if matched.empty:
            st.info("No customer found matching that search.")
        else:
            for _, row in matched.iterrows():
                net = to_decimal(row["net_pending"])
                colour = "#e74c3c" if net > 0 else "#27ae60"
                status_label = "pending" if net >= 0 else "advance (extra paid)"
                st.markdown(
                    f"**{row['customer_name']}** — "
                    f"<span style='color:{colour};font-weight:700'>{fmt_inr(net)} {status_label}</span>",
                    unsafe_allow_html=True,
                )
                cust_tx = all_tx[all_tx["customer_name"] == row["customer_name"]].copy()
                cust_tx["_sort_ts"] = pd.to_datetime(cust_tx["timestamp"], errors="coerce")
                cust_tx = cust_tx.sort_values("_sort_ts", ascending=False).head(3)
                if not cust_tx.empty:
                    for _, t in cust_tx.iterrows():
                        emoji = "🔴" if t["transaction_type"] == "credit" else "🟢"
                        st.markdown(
                            f"&nbsp;&nbsp;{emoji} {t['date']} — {t['product_details']} — "
                            f"{fmt_inr(t['amount'])} (Bal: {fmt_inr(t['running_balance'])})"
                        )
                st.markdown("---")

    st.markdown("### ✍️ Add New Entry")

    # ── Customer selection ──
    customer_list = sorted(totals["customer_name"].dropna().unique().tolist()) if not totals.empty else []
    customer_list_display = ["➕ Add New Customer"] + customer_list

    col_cust, col_new = st.columns([1, 1])
    with col_cust:
        selected_customer_option = st.selectbox(
            "Select Customer",
            customer_list_display,
            key="selected_customer_option",
        )

    is_new_customer = selected_customer_option == "➕ Add New Customer"
    new_customer_name = ""
    new_phone = ""

    with col_new:
        if is_new_customer:
            new_customer_name = st.text_input(
                "Customer Name *",
                placeholder="Full name (auto-matches if already exists)",
                key="new_customer_name",
            )
            new_phone = st.text_input(
                "Phone Number",
                placeholder="10-digit mobile number",
                key="new_phone",
            )
        else:
            existing_phone = ""
            if not totals.empty:
                phone_row = totals[totals["customer_name"] == selected_customer_option]
                if not phone_row.empty:
                    existing_phone = clean_phone(phone_row.iloc[0]["phone_number"])
            new_phone = st.text_input(
                "Phone Number (Update if needed)",
                value=existing_phone,
                placeholder="10-digit mobile number",
                key=f"edit_phone_{selected_customer_option}",
            )

    # ── Transaction form ──
    with st.form("add_entry_form", clear_on_submit=True):
        col_type, col_date = st.columns([1, 1])
        with col_type:
            tx_type_label = st.radio(
                "Transaction Type",
                ["💳 Credit Given (Udhaar)", "✅ Payment Received (Jama)"],
                key="tx_type_radio",
            )
        with col_date:
            tx_date = st.date_input("Date", value=date.today(), key="tx_date")

        product_details = st.text_input(
            "Product / Details",
            placeholder="e.g. Rice 5kg, Sugar 2kg, Cash payment…",
            key="product_details",
        )

        amount_val = st.number_input(
            "Amount (₹)",
            min_value=0.0,
            step=1.0,
            format="%.2f",
            key="amount_val",
        )

        submitted = st.form_submit_button("💾 Save Entry", use_container_width=True)

        if submitted:
            if is_new_customer:
                customer_name = normalize_name(new_customer_name)
                phone = clean_phone(new_phone)
            else:
                customer_name = normalize_name(selected_customer_option)
                phone = clean_phone(new_phone)

            errors = []
            if not customer_name:
                errors.append("Customer name is required.")
            if amount_val <= 0:
                errors.append("Amount must be greater than ₹0.")

            if errors:
                for e in errors:
                    st.error(e)
            else:
                tx_type = "credit" if "Credit" in tx_type_label else "payment"
                amount = to_decimal(amount_val)
                result = add_transaction(
                    customer_name=customer_name,
                    phone_number=phone,
                    tx_date=str(tx_date),
                    product_details=product_details or ("Credit Purchase" if tx_type == "credit" else "Cash / UPI Payment"),
                    tx_type=tx_type,
                    amount=amount,
                )

                final_name = result["customer_name"]
                new_pending = to_decimal(result["new_balance"])
                st.session_state["last_save_msg"] = (
                    f"✅ Saved! {final_name}'s Total Pending is now {fmt_inr(new_pending)}"
                )

                # Auto-sync to Google Sheets
                client, _ = get_gspread_client()
                if client is not None and get_spreadsheet_id():
                    ok, msg = sync_to_google_sheets()
                    if not ok:
                        st.warning(f"☁️ Google Sheets sync warning: {msg}")

                st.rerun()

    # Show save success banner
    if st.session_state.get("last_save_msg"):
        st.markdown(
            f'<div class="success-banner">{st.session_state["last_save_msg"]}</div>',
            unsafe_allow_html=True,
        )
        st.session_state["last_save_msg"] = None

# ══════════════════════════════════════════════
# TAB 2 – CUSTOMER KHATA
# ══════════════════════════════════════════════
with tab_khata:

    all_tx = load_transactions()
    totals = load_totals()

    if totals.empty:
        st.info("📭 No customers yet. Add your first entry in the **Home** tab.")
    else:
        customer_list_khata = sorted(totals["customer_name"].dropna().unique().tolist())
        selected_cust_khata = st.selectbox(
            "Select Customer",
            customer_list_khata,
            key="khata_customer_select",
        )

        cust_row = totals[totals["customer_name"] == selected_cust_khata]
        if cust_row.empty:
            st.warning("Customer not found in totals.")
        else:
            cust_data = cust_row.iloc[0]
            total_credit = to_decimal(cust_data["total_credit"])
            total_paid   = to_decimal(cust_data["total_paid"])
            net_pending  = to_decimal(cust_data["net_pending"])
            phone        = clean_phone(cust_data["phone_number"])

            # ── 3 metric cards ──
            c1, c2, c3 = st.columns(3)
            c1.metric("💳 Total Credit Given", fmt_inr(total_credit))
            c2.metric("✅ Total Paid", fmt_inr(total_paid))
            c3.metric("⏳ Net Pending", fmt_inr(net_pending))

            # ── WhatsApp button ──
            if phone:
                cust_tx_wa = all_tx[all_tx["customer_name"] == selected_cust_khata]
                wa_url = generate_whatsapp_url(phone, selected_cust_khata, net_pending, cust_tx_wa)
                st.markdown(
                    f'<a href="{wa_url}" target="_blank" style="text-decoration:none;">'
                    f'<button style="background:#25D366;color:white;border:none;'
                    f'border-radius:10px;padding:12px 20px;font-size:1rem;font-weight:700;'
                    f'cursor:pointer;width:100%;margin:8px 0">'
                    f'📱 Send WhatsApp Reminder to {selected_cust_khata} ({phone})</button></a>',
                    unsafe_allow_html=True,
                )
            else:
                st.caption("📞 No phone number on record — add their phone number in the Home tab to enable WhatsApp reminders.")

            st.markdown("---")
            st.markdown(f"#### 📋 Full Transaction History — {selected_cust_khata}")

            cust_tx = all_tx[all_tx["customer_name"] == selected_cust_khata].copy()
            cust_tx["_sort_ts"] = pd.to_datetime(cust_tx["timestamp"], errors="coerce")
            cust_tx = cust_tx.sort_values("_sort_ts").reset_index(drop=True)

            if cust_tx.empty:
                st.info("No transactions found for this customer.")
            else:
                html_rows = ""
                for _, r in cust_tx.iterrows():
                    is_credit = r["transaction_type"] == "credit"
                    row_class = "credit-row" if is_credit else "payment-row"
                    credit_col  = fmt_inr(r["amount"]) if is_credit else "—"
                    payment_col = fmt_inr(r["amount"]) if not is_credit else "—"
                    bal = fmt_inr(r["running_balance"])
                    html_rows += (
                        f'<tr class="{row_class}">'
                        f"<td>{r['date']}</td>"
                        f"<td>{r['product_details']}</td>"
                        f"<td style='color:#c0392b;font-weight:600'>{credit_col}</td>"
                        f"<td style='color:#27ae60;font-weight:600'>{payment_col}</td>"
                        f"<td><b>{bal}</b></td>"
                        f"</tr>"
                    )

                table_html = f"""
                <style>
                    .khata-table {{ width:100%; border-collapse:collapse; font-size:0.92rem; }}
                    .khata-table th {{ background:#0f3460; color:white; padding:10px 8px; text-align:left; }}
                    .khata-table td {{ padding:8px; border-bottom:1px solid #ddd; color:#1a1a1a; }}
                    .credit-row  {{ background:#fff0f0; }}
                    .payment-row {{ background:#f0fff4; }}
                </style>
                <table class="khata-table">
                    <thead>
                        <tr>
                            <th>Date</th>
                            <th>Product / Details</th>
                            <th>Credit (₹)</th>
                            <th>Payment (₹)</th>
                            <th>Running Balance (₹)</th>
                        </tr>
                    </thead>
                    <tbody>{html_rows}</tbody>
                </table>
                """
                st.markdown(table_html, unsafe_allow_html=True)

# ══════════════════════════════════════════════
# TAB 3 – SUMMARY & REPORTS
# ══════════════════════════════════════════════
with tab_reports:

    all_tx = load_transactions()
    totals = load_totals()

    st.markdown("### 📊 All Customers – Pending Summary")

    if totals.empty:
        st.info("No data yet. Add entries to see reports.")
    else:
        display_totals = totals.copy()
        display_totals["net_pending_num"] = display_totals["net_pending"].apply(lambda x: float(to_decimal(x)))
        display_totals = display_totals.sort_values("net_pending_num", ascending=False)

        display_df = display_totals.copy()
        display_df["total_credit"] = display_df["total_credit"].apply(fmt_inr)
        display_df["total_paid"] = display_df["total_paid"].apply(fmt_inr)
        display_df["net_pending"] = display_df["net_pending"].apply(fmt_inr)

        display_df = display_df.rename(columns={
            "customer_name": "Customer",
            "phone_number":  "Phone",
            "total_credit":  "Total Credit",
            "total_paid":    "Total Paid",
            "net_pending":   "Net Pending",
            "last_updated":  "Last Updated",
        })

        st.dataframe(
            display_df[["Customer", "Phone", "Total Credit", "Total Paid", "Net Pending", "Last Updated"]],
            use_container_width=True,
            hide_index=True,
        )

        # ── Bar chart ──
        st.markdown("#### 📈 Pending Balance per Customer (₹)")
        chart_data = display_totals[["customer_name", "net_pending_num"]].rename(
            columns={"customer_name": "Customer", "net_pending_num": "Pending (₹)"}
        ).set_index("Customer")
        st.bar_chart(chart_data)

        # ── Download buttons ──
        st.markdown("#### 📥 Download Reports")
        col_dl1, col_dl2 = st.columns(2)

        with col_dl1:
            if os.path.exists(TRANSACTIONS_FILE):
                with open(TRANSACTIONS_FILE, "rb") as f:
                    st.download_button(
                        "📥 Download Full Ledger (CSV)",
                        data=f,
                        file_name="roshan_full_ledger.csv",
                        mime="text/csv",
                        use_container_width=True,
                    )

        with col_dl2:
            if os.path.exists(TOTALS_FILE):
                with open(TOTALS_FILE, "rb") as f:
                    st.download_button(
                        "📥 Download Summary (CSV)",
                        data=f,
                        file_name="roshan_summary.csv",
                        mime="text/csv",
                        use_container_width=True,
                    )

# ══════════════════════════════════════════════
# TAB 4 – MANAGE / DELETE ENTRY
# ══════════════════════════════════════════════
with tab_manage:

    st.markdown("### 🛡️ Manage Transactions (PIN Protected)")

    if not st.session_state["pin_verified"]:
        pin_input = st.text_input(
            "Enter PIN to unlock",
            type="password",
            placeholder="4-digit PIN",
            key="pin_input",
        )
        if st.button("🔓 Unlock", key="pin_unlock_btn"):
            correct_pin = str(st.secrets.get("ADMIN_PIN", DEFAULT_PIN)) \
                if "ADMIN_PIN" in st.secrets else DEFAULT_PIN
            if pin_input == correct_pin:
                st.session_state["pin_verified"] = True
                st.success("✅ PIN correct! Access granted.")
                st.rerun()
            else:
                st.error("❌ Incorrect PIN. Try again.")
    else:
        col_lock, col_repair = st.columns([1, 1])
        with col_lock:
            if st.button("🔒 Lock / Sign Out", key="lock_btn"):
                st.session_state["pin_verified"] = False
                st.session_state["confirm_delete_id"] = None
                st.rerun()
        with col_repair:
            if st.button("🧹 Merge Duplicate Names & Recalculate All", key="repair_btn"):
                tx_df = load_transactions()
                clean_tx, clean_tot = rebuild_all_data(tx_df)
                save_transactions(clean_tx)
                save_totals(clean_tot)
                sync_to_google_sheets()
                st.success("✅ All duplicate names merged into Title Case and synced to Google Sheets!")
                st.rerun()

        all_tx = load_transactions()

        if all_tx.empty:
            st.info("No transactions to show.")
        else:
            st.markdown("#### All Transactions (click 🗑️ to remove)")

            all_tx_sorted = all_tx.copy()
            all_tx_sorted["_sort_ts"] = pd.to_datetime(
                all_tx_sorted["timestamp"], errors="coerce"
            )
            all_tx_sorted = all_tx_sorted.sort_values("_sort_ts", ascending=False)

            for _, row in all_tx_sorted.iterrows():
                tx_id = row["transaction_id"]
                is_credit = row["transaction_type"] == "credit"
                label_color = "#c0392b" if is_credit else "#27ae60"
                label_word  = "CREDIT" if is_credit else "PAYMENT"

                col_info, col_del = st.columns([5, 1])
                with col_info:
                    st.markdown(
                        f"**{row['date']}** — **{row['customer_name']}** — "
                        f"{row['product_details']} — "
                        f"<span style='color:{label_color};font-weight:700'>{label_word} {fmt_inr(row['amount'])}</span> "
                        f"<small style='color:#888'>[{tx_id}]</small>",
                        unsafe_allow_html=True,
                    )
                with col_del:
                    if st.button("🗑️", key=f"del_{tx_id}", help="Delete this transaction"):
                        st.session_state["confirm_delete_id"] = tx_id
                        st.rerun()

                if st.session_state.get("confirm_delete_id") == tx_id:
                    with st.container():
                        st.warning(
                            f"⚠️ Are you sure you want to delete transaction **{tx_id}** "
                            f"({row['customer_name']} — {fmt_inr(row['amount'])})? "
                            f"This cannot be undone."
                        )
                        c_yes, c_no = st.columns(2)
                        with c_yes:
                            if st.button("✅ Yes, Delete", key=f"confirm_yes_{tx_id}"):
                                success = delete_transaction(tx_id)
                                st.session_state["confirm_delete_id"] = None
                                if success:
                                    sync_to_google_sheets()
                                    st.success("Deleted and synced to Google Sheets.")
                                else:
                                    st.error("Could not find that transaction.")
                                st.rerun()
                        with c_no:
                            if st.button("❌ Cancel", key=f"confirm_no_{tx_id}"):
                                st.session_state["confirm_delete_id"] = None
                                st.rerun()

        # ── Audit trail ──
        st.markdown("---")
        st.markdown("#### 🕵️ Audit Trail – Deleted Entries")
        deleted_log = load_deleted_log()
        if deleted_log.empty:
            st.info("No entries have been deleted yet.")
        else:
            st.dataframe(deleted_log, use_container_width=True, hide_index=True)

# ══════════════════════════════════════════════
# TAB 5 – GOOGLE SHEETS SYNC
# ══════════════════════════════════════════════
with tab_sync:

    st.markdown("### ☁️ Google Sheets Sync & Cloud Backup")

    client, status_msg = get_gspread_client()
    spreadsheet_id = get_spreadsheet_id()

    if client is not None and spreadsheet_id:
        st.success("✅ **Connected** — Automatic 2-way Google Sheets sync is active.")
        st.markdown(f"📄 Spreadsheet ID: `{spreadsheet_id}`")
    else:
        st.warning("⚠️ **Not Configured** — Google Sheets sync is disabled.")
        st.markdown(f"Status: `{status_msg}`")

    st.markdown("---")
    col_push, col_pull = st.columns(2)

    with col_push:
        st.markdown("#### ⬆️ Push App Data to Google Sheets")
        if st.button("🔄 Sync App → Google Sheets Now", use_container_width=True):
            with st.spinner("Uploading to Google Sheets…"):
                ok, msg = sync_to_google_sheets()
            if ok:
                st.success(f"✅ Sync complete! {msg}")
            else:
                st.error(f"❌ Sync failed: {msg}")

    with col_pull:
        st.markdown("#### ⬇️ Pull Data from Google Sheets")
        if st.button("📥 Restore Google Sheets → App Now", use_container_width=True):
            with st.spinner("Restoring from Google Sheets…"):
                ok, msg = load_from_google_sheets()
            if ok:
                st.success(f"✅ Restore complete! {msg}")
                st.rerun()
            else:
                st.error(f"❌ Restore failed: {msg}")
