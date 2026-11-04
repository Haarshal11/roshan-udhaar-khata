"""
Roshan General Store - Credit Ledger (Udhaar Website)
A production-ready Streamlit app for managing shop credit (Udhaar Khata).
Local CSV storage is primary (always works offline).
Optional Google Sheets sync.
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
    page_title="Roshan General Store - Udhaar Khata",
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
        .credit-row  { background-color: #fff0f0 !important; }
        .payment-row { background-color: #f0fff4 !important; }

        /* ── Total-pending hero ── */
        .hero-pending {
            background: linear-gradient(135deg, #e94560, #0f3460);
            border-radius: 16px;
            padding: 24px 32px;
            text-align: center;
            color: white;
            margin-bottom: 20px;
        }
        .hero-pending h1 { margin: 0; font-size: 3rem; font-weight: 800; }
        .hero-pending p  { margin: 4px 0 0; font-size: 1rem; opacity: 0.85; }

        /* ── Tabs ── */
        button[data-baseweb="tab"] { font-size: 0.95rem; }

        /* ── Hide Streamlit default footer ── */
        footer { visibility: hidden; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────
# DECIMAL HELPERS
# ─────────────────────────────────────────────

def to_decimal(value) -> Decimal:
    """Convert any numeric value to a Decimal with 2 decimal places."""
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal("0.00")


def fmt_inr(value) -> str:
    """Format a number as ₹1,234.56"""
    d = to_decimal(value)
    # Format with Indian comma grouping
    abs_val = abs(d)
    s = f"{abs_val:,.2f}"
    return f"₹{s}" if d >= 0 else f"-₹{s}"

# ─────────────────────────────────────────────
# CSV FILE HELPERS
# ─────────────────────────────────────────────

def load_transactions() -> pd.DataFrame:
    """Load all transactions from CSV, returning an empty DF if not found."""
    if os.path.exists(TRANSACTIONS_FILE):
        df = pd.read_csv(TRANSACTIONS_FILE, dtype=str)
        # Ensure all expected columns exist
        for col in TRANSACTIONS_COLUMNS:
            if col not in df.columns:
                df[col] = ""
        return df[TRANSACTIONS_COLUMNS]
    return pd.DataFrame(columns=TRANSACTIONS_COLUMNS)


def load_totals() -> pd.DataFrame:
    """Load customer totals from CSV."""
    if os.path.exists(TOTALS_FILE):
        df = pd.read_csv(TOTALS_FILE, dtype=str)
        for col in TOTALS_COLUMNS:
            if col not in df.columns:
                df[col] = ""
        return df[TOTALS_COLUMNS]
    return pd.DataFrame(columns=TOTALS_COLUMNS)


def load_deleted_log() -> pd.DataFrame:
    """Load deleted entries audit log."""
    if os.path.exists(DELETED_LOG_FILE):
        df = pd.read_csv(DELETED_LOG_FILE, dtype=str)
        for col in DELETED_COLUMNS:
            if col not in df.columns:
                df[col] = ""
        return df
    return pd.DataFrame(columns=DELETED_COLUMNS)


def save_transactions(df: pd.DataFrame):
    df.to_csv(TRANSACTIONS_FILE, index=False)


def save_totals(df: pd.DataFrame):
    df.to_csv(TOTALS_FILE, index=False)


def save_deleted_log(df: pd.DataFrame):
    df.to_csv(DELETED_LOG_FILE, index=False)

# ─────────────────────────────────────────────
# BUSINESS LOGIC
# ─────────────────────────────────────────────

def recalculate_customer(customer_name: str, all_tx: pd.DataFrame) -> dict:
    """
    Re-compute totals for a single customer from the transactions dataframe.
    Returns a dict suitable for a row in the totals CSV.
    """
    cust_tx = all_tx[all_tx["customer_name"] == customer_name].copy()
    if cust_tx.empty:
        return None

    total_credit = sum(
        to_decimal(r["amount"])
        for _, r in cust_tx.iterrows()
        if r["transaction_type"] == "credit"
    )
    total_paid = sum(
        to_decimal(r["amount"])
        for _, r in cust_tx.iterrows()
        if r["transaction_type"] == "payment"
    )
    net_pending = total_credit - total_paid

    # Latest phone number recorded
    phone = ""
    phone_rows = cust_tx[cust_tx["phone_number"].notna() & (cust_tx["phone_number"] != "")]
    if not phone_rows.empty:
        phone = phone_rows.iloc[-1]["phone_number"]

    return {
        "customer_name": customer_name,
        "phone_number": phone,
        "total_credit": str(total_credit),
        "total_paid": str(total_paid),
        "net_pending": str(net_pending),
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def rebuild_running_balance(customer_name: str, all_tx: pd.DataFrame) -> pd.DataFrame:
    """
    Rebuild running_balance column for a specific customer's transactions
    (sorted by date, then timestamp).
    """
    idx = all_tx[all_tx["customer_name"] == customer_name].index
    cust_rows = all_tx.loc[idx].copy()

    cust_rows["_sort_ts"] = pd.to_datetime(
        cust_rows["timestamp"], errors="coerce"
    )
    cust_rows = cust_rows.sort_values("_sort_ts")

    balance = Decimal("0.00")
    for i in cust_rows.index:
        amt = to_decimal(all_tx.at[i, "amount"])
        tx_type = all_tx.at[i, "transaction_type"]
        if tx_type == "credit":
            balance += amt
        else:
            balance -= amt
        all_tx.at[i, "running_balance"] = str(balance)

    return all_tx


def add_transaction(
    customer_name: str,
    phone_number: str,
    tx_date: str,
    product_details: str,
    tx_type: str,  # "credit" or "payment"
    amount: Decimal,
) -> dict:
    """
    Append a new transaction to CSV, update totals, return result dict.
    """
    all_tx = load_transactions()
    totals = load_totals()

    # Compute running balance for this customer
    cust_tx = all_tx[all_tx["customer_name"] == customer_name]
    if cust_tx.empty:
        prev_balance = Decimal("0.00")
    else:
        last_balance = cust_tx.iloc[-1]["running_balance"]
        prev_balance = to_decimal(last_balance)

    if tx_type == "credit":
        new_balance = prev_balance + amount
    else:
        new_balance = prev_balance - amount

    tx_id = str(uuid.uuid4())[:8].upper()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    new_row = {
        "transaction_id": tx_id,
        "customer_name": customer_name,
        "phone_number": phone_number,
        "date": tx_date,
        "product_details": product_details,
        "transaction_type": tx_type,
        "amount": str(amount),
        "running_balance": str(new_balance),
        "timestamp": now_str,
    }

    new_df = pd.DataFrame([new_row])
    all_tx = pd.concat([all_tx, new_df], ignore_index=True)
    save_transactions(all_tx)

    # Update totals
    totals_dict = recalculate_customer(customer_name, all_tx)
    existing_idx = totals[totals["customer_name"] == customer_name].index
    if len(existing_idx) > 0:
        for key, val in totals_dict.items():
            totals.at[existing_idx[0], key] = val
    else:
        totals = pd.concat(
            [totals, pd.DataFrame([totals_dict])], ignore_index=True
        )
    save_totals(totals)

    return {"success": True, "new_balance": new_balance, "tx_id": tx_id, "row": new_row}


def delete_transaction(tx_id: str):
    """
    Remove a transaction by ID, rebuild running balances, update totals.
    Log the deleted entry to the audit file.
    """
    all_tx = load_transactions()
    totals = load_totals()

    target = all_tx[all_tx["transaction_id"] == tx_id]
    if target.empty:
        return False

    # Log deletion
    deleted_log = load_deleted_log()
    deleted_row = target.copy()
    deleted_row["deleted_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    deleted_log = pd.concat([deleted_log, deleted_row], ignore_index=True)
    save_deleted_log(deleted_log)

    customer_name = target.iloc[0]["customer_name"]

    # Remove from main DF
    all_tx = all_tx[all_tx["transaction_id"] != tx_id].reset_index(drop=True)

    # Rebuild running balance for affected customer
    all_tx = rebuild_running_balance(customer_name, all_tx)
    save_transactions(all_tx)

    # Recalculate totals
    if all_tx[all_tx["customer_name"] == customer_name].empty:
        # No more transactions — remove from totals
        totals = totals[totals["customer_name"] != customer_name]
    else:
        totals_dict = recalculate_customer(customer_name, all_tx)
        existing_idx = totals[totals["customer_name"] == customer_name].index
        if len(existing_idx) > 0:
            for key, val in totals_dict.items():
                totals.at[existing_idx[0], key] = val
        else:
            totals = pd.concat(
                [totals, pd.DataFrame([totals_dict])], ignore_index=True
            )
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
    # Collect recent credit items
    credits = cust_tx[cust_tx["transaction_type"] == "credit"].copy()
    credits["_sort_ts"] = pd.to_datetime(credits["timestamp"], errors="coerce")
    credits = credits.sort_values("_sort_ts", ascending=False).head(5)

    items_lines = ""
    for _, r in credits.iterrows():
        items_lines += (
            f"\n  • {r['date']} | {r['product_details']} | ₹{to_decimal(r['amount'])}"
        )

    msg = (
        f"🙏 Namaste {customer_name} Ji,\n\n"
        f"This is a gentle reminder from *Roshan General Store*.\n\n"
        f"Recent credit entries:{items_lines}\n\n"
        f"💰 *Total Pending Balance: ₹{pending_balance}*\n\n"
        f"Kindly arrange the payment at your earliest convenience.\n\n"
        f"Thank you! 🙏\n"
        f"- Roshan General Store"
    )

    # Sanitise phone
    phone_clean = "".join(filter(str.isdigit, phone or ""))
    if len(phone_clean) == 10:
        phone_clean = "91" + phone_clean  # Assume India

    encoded_msg = urllib.parse.quote(msg)
    return f"https://wa.me/{phone_clean}?text={encoded_msg}"

# ─────────────────────────────────────────────
# GOOGLE SHEETS SYNC
# ─────────────────────────────────────────────

def get_gspread_client():
    """
    Try to initialise a gspread client.
    Returns the client or None if not configured.
    """
    try:
        import gspread
        from google.oauth2.service_account import Credentials

        SCOPES = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]

        creds_dict = None

        # Option 1 – Streamlit secrets
        if "gcp_service_account" in st.secrets:
            creds_dict = dict(st.secrets["gcp_service_account"])

        # Option 2 – local credentials.json
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
        return st.secrets["SPREADSHEET_ID"]
    if os.path.exists("spreadsheet_id.txt"):
        with open("spreadsheet_id.txt") as f:
            return f.read().strip()
    return ""


def ensure_worksheet(spreadsheet, title: str, headers: list):
    """Get or create a worksheet and write headers if brand new."""
    try:
        ws = spreadsheet.worksheet(title)
    except Exception:
        ws = spreadsheet.add_worksheet(title=title, rows=1000, cols=len(headers))
        ws.append_row(headers)
    return ws


def sync_to_google_sheets() -> tuple[bool, str]:
    """
    Full sync: upload all local CSV data to Google Sheets.
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
        totals = load_totals()

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

            # Sanitise sheet name (Sheets doesn't allow some chars)
            safe_name = str(cname)[:31].replace("/", "-").replace("\\", "-").replace(":", "-")
            ws_cust = ensure_worksheet(spreadsheet, safe_name, customer_headers)
            ws_cust.clear()
            ws_cust.append_row(customer_headers)
            if rows:
                ws_cust.append_rows(rows)

        return True, f"Synced {len(all_tx)} transactions for {len(customers)} customers."
    except Exception as e:
        return False, str(e)

# ─────────────────────────────────────────────
# SESSION STATE INIT
# ─────────────────────────────────────────────

def init_session_state():
    defaults = {
        "pin_verified": False,
        "last_save_msg": None,
        "confirm_delete_id": None,
        "sync_status": None,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val

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
        "Type customer name to see balance",
        placeholder="e.g. Ramesh, Suresh…",
        key="search_name_input",
    )

    if search_name.strip():
        matched = totals[
            totals["customer_name"].str.contains(search_name.strip(), case=False, na=False)
        ]
        if matched.empty:
            st.info("No customer found with that name.")
        else:
            for _, row in matched.iterrows():
                net = to_decimal(row["net_pending"])
                colour = "#e74c3c" if net > 0 else "#27ae60"
                st.markdown(
                    f"**{row['customer_name']}** — "
                    f"<span style='color:{colour};font-weight:700'>{fmt_inr(net)} pending</span>",
                    unsafe_allow_html=True,
                )
                # Last 3 transactions
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
                "New Customer Name *",
                placeholder="Full name",
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
                    existing_phone = phone_row.iloc[0]["phone_number"]
            st.markdown(f"📞 Phone: **{existing_phone or 'Not on record'}**")
            new_phone = existing_phone

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
            # Determine actual customer name
            if is_new_customer:
                customer_name = new_customer_name.strip()
                phone = new_phone.strip()
            else:
                customer_name = selected_customer_option
                phone = new_phone.strip()

            # Validation
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
                    product_details=product_details or "(no details)",
                    tx_type=tx_type,
                    amount=amount,
                )

                new_pending = to_decimal(result["new_balance"])
                action_word = "Credit" if tx_type == "credit" else "Payment"
                st.session_state["last_save_msg"] = (
                    f"✅ Saved! {customer_name}'s Total Pending is now {fmt_inr(new_pending)}"
                )

                # Auto-sync to Google Sheets
                client, _ = get_gspread_client()
                if client is not None and get_spreadsheet_id():
                    ok, msg = sync_to_google_sheets()
                    if not ok:
                        st.warning(f"☁️ Google Sheets sync failed: {msg}")

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
            total_credit  = to_decimal(cust_data["total_credit"])
            total_paid    = to_decimal(cust_data["total_paid"])
            net_pending   = to_decimal(cust_data["net_pending"])
            phone         = cust_data["phone_number"]

            # ── 3 metric cards ──
            c1, c2, c3 = st.columns(3)
            c1.metric("💳 Total Credit Given", fmt_inr(total_credit))
            c2.metric("✅ Total Paid", fmt_inr(total_paid))
            pending_color = "normal" if net_pending <= 0 else "off"
            c3.metric("⏳ Net Pending", fmt_inr(net_pending))

            # ── WhatsApp button ──
            if phone and phone.strip():
                cust_tx_wa = all_tx[all_tx["customer_name"] == selected_cust_khata]
                wa_url = generate_whatsapp_url(phone, selected_cust_khata, net_pending, cust_tx_wa)
                st.markdown(
                    f'<a href="{wa_url}" target="_blank">'
                    f'<button style="background:#25D366;color:white;border:none;'
                    f'border-radius:10px;padding:10px 20px;font-size:1rem;'
                    f'cursor:pointer;width:100%;margin:8px 0">'
                    f'📱 Send WhatsApp Reminder to {selected_cust_khata}</button></a>',
                    unsafe_allow_html=True,
                )
            else:
                st.caption("📞 No phone number on record — WhatsApp reminder unavailable.")

            st.markdown("---")
            st.markdown(f"#### 📋 Full Transaction History — {selected_cust_khata}")

            cust_tx = all_tx[all_tx["customer_name"] == selected_cust_khata].copy()
            cust_tx["_sort_ts"] = pd.to_datetime(cust_tx["timestamp"], errors="coerce")
            cust_tx = cust_tx.sort_values("_sort_ts").reset_index(drop=True)

            if cust_tx.empty:
                st.info("No transactions found for this customer.")
            else:
                # Build display table with colour rows
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
                        f"<td style='color:#c0392b'>{credit_col}</td>"
                        f"<td style='color:#27ae60'>{payment_col}</td>"
                        f"<td><b>{bal}</b></td>"
                        f"</tr>"
                    )

                table_html = f"""
                <style>
                    .khata-table {{ width:100%; border-collapse:collapse; font-size:0.9rem; }}
                    .khata-table th {{ background:#0f3460; color:white; padding:8px; text-align:left; }}
                    .khata-table td {{ padding:7px 8px; border-bottom:1px solid #eee; }}
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
        # Sort by net_pending descending
        display_totals = totals.copy()
        display_totals["net_pending_num"] = display_totals["net_pending"].apply(to_decimal)
        display_totals = display_totals.sort_values("net_pending_num", ascending=False)

        # Rename for display
        display_df = display_totals.rename(columns={
            "customer_name": "Customer",
            "phone_number":  "Phone",
            "total_credit":  "Total Credit (₹)",
            "total_paid":    "Total Paid (₹)",
            "net_pending":   "Net Pending (₹)",
            "last_updated":  "Last Updated",
        })

        st.dataframe(
            display_df[["Customer", "Phone", "Total Credit (₹)", "Total Paid (₹)",
                         "Net Pending (₹)", "Last Updated"]],
            use_container_width=True,
            hide_index=True,
        )

        # ── Bar chart ──
        st.markdown("#### 📈 Pending Balance per Customer")
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
            # Check against st.secrets first, then default
            correct_pin = str(st.secrets.get("ADMIN_PIN", DEFAULT_PIN)) \
                if "ADMIN_PIN" in st.secrets else DEFAULT_PIN
            if pin_input == correct_pin:
                st.session_state["pin_verified"] = True
                st.success("✅ PIN correct! Access granted.")
                st.rerun()
            else:
                st.error("❌ Incorrect PIN. Try again.")
        st.caption(f"Default PIN is **{DEFAULT_PIN}**. Change via `st.secrets['ADMIN_PIN']`.")
    else:
        if st.button("🔒 Lock / Sign Out", key="lock_btn"):
            st.session_state["pin_verified"] = False
            st.session_state["confirm_delete_id"] = None
            st.rerun()

        all_tx = load_transactions()

        if all_tx.empty:
            st.info("No transactions to show.")
        else:
            st.markdown("#### All Transactions (click Delete to remove)")

            # Sort newest first
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
                        f"**{row['date']}** — {row['customer_name']} — "
                        f"{row['product_details']} — "
                        f"<span style='color:{label_color}'>{label_word} {fmt_inr(row['amount'])}</span> "
                        f"<small style='color:#888'>[{tx_id}]</small>",
                        unsafe_allow_html=True,
                    )
                with col_del:
                    if st.button("🗑️", key=f"del_{tx_id}", help="Delete this transaction"):
                        st.session_state["confirm_delete_id"] = tx_id
                        st.rerun()

                # Confirmation dialog
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
                                    st.success("Deleted successfully.")
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

    st.markdown("### ☁️ Google Sheets Sync")

    client, status_msg = get_gspread_client()
    spreadsheet_id = get_spreadsheet_id()

    if client is not None and spreadsheet_id:
        st.success(f"✅ **Connected** — Google Sheets sync is active.")
        st.markdown(f"📄 Spreadsheet ID: `{spreadsheet_id}`")
    else:
        st.warning("⚠️ **Not Configured** — Google Sheets sync is disabled.")
        st.markdown(f"Status: `{status_msg}`")

    st.markdown("---")
    st.markdown("#### ▶️ Manual Sync")

    if st.button("🔄 Sync All Data to Google Sheets Now", use_container_width=True):
        with st.spinner("Syncing…"):
            ok, msg = sync_to_google_sheets()
        if ok:
            st.success(f"✅ Sync complete! {msg}")
        else:
            st.error(f"❌ Sync failed: {msg}")

    st.markdown("---")
    st.markdown(
        """
        #### ⚙️ How to Configure Google Sheets Sync

        1. **Create a Google Cloud Project** and enable **Google Sheets API** & **Google Drive API**.
        2. **Create a Service Account** and download `credentials.json`.
        3. **Place `credentials.json`** in the same folder as `app.py`  
           — OR — add its contents to Streamlit secrets as `[gcp_service_account]`.
        4. **Create a Google Sheet**, copy its ID from the URL  
           (`https://docs.google.com/spreadsheets/d/**SPREADSHEET_ID**/edit`).
        5. **Share the sheet** with your service account email (the `client_email` field in `credentials.json`) as **Editor**.
        6. **Set SPREADSHEET_ID**: either add it to `secrets.toml` as `SPREADSHEET_ID = "..."`,  
           or save it in a file called `spreadsheet_id.txt`.

        > See `credentials_setup.md` for the full step-by-step guide.
        """
    )

    st.markdown("---")
    st.markdown("#### 📄 Sample `secrets.toml` (for `.streamlit/secrets.toml`)")
    st.code(
        """
SPREADSHEET_ID = "your_spreadsheet_id_here"
ADMIN_PIN = "1234"

[gcp_service_account]
type = "service_account"
project_id = "your-project-id"
private_key_id = "key-id"
private_key = "-----BEGIN RSA PRIVATE KEY-----\\n...\\n-----END RSA PRIVATE KEY-----\\n"
client_email = "your-sa@your-project.iam.gserviceaccount.com"
client_id = "1234567890"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "https://www.googleapis.com/robot/v1/metadata/x509/your-sa%40your-project.iam.gserviceaccount.com"
        """,
        language="toml",
    )
