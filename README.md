# 🏪 Roshan General Store – Udhaar Khata

A production-ready Streamlit web app for managing daily shop credit (Udhaar / Khata).  
Works fully **offline** with local CSV storage. Optional Google Sheets sync for cloud backup.

---

## ✨ Features

- 📌 **Dashboard** — total pending balance across all customers at a glance
- 🔍 **Instant search** — type a name, see balance + last 3 transactions instantly
- ✍️ **Add entries** — credit (udhaar) and payment (jama) with running balance
- 👤 **Customer Khata** — full history with colour-coded credit/payment rows
- 📱 **WhatsApp reminder** — one-click message with pending details pre-filled
- 📊 **Reports** — pending summary table + bar chart, downloadable CSVs
- 🛡️ **PIN-protected delete** — with full audit trail of deleted entries
- ☁️ **Google Sheets sync** — automatic backup on every transaction (optional)
- 💯 **Decimal math** — zero floating-point errors (uses Python `decimal.Decimal`)

---

## 🚀 Quick Start (Local)

### Prerequisites

- Python 3.9 or newer
- pip

### Install & Run

```bash
# 1. Go to the app folder
cd roshan-udhaar-khata

# 2. (Recommended) Create a virtual environment
python -m venv venv

# Windows
venv\Scripts\activate

# Mac / Linux
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run the app
streamlit run app.py
```

The app opens automatically at **http://localhost:8501**

---

## 📱 Local Wi-Fi Hosting (Access from Any Phone on the Same Network)

This lets everyone in the shop — or family members — access the ledger from their phones without any internet.

### Step 1 – Find Your Computer's Local IP Address

**Windows:**
```cmd
ipconfig
```
Look for **IPv4 Address** under your Wi-Fi adapter, e.g., `192.168.1.105`

**Mac / Linux:**
```bash
ifconfig | grep "inet "
# or
hostname -I
```

### Step 2 – Run Streamlit on All Interfaces

```bash
streamlit run app.py --server.address 0.0.0.0 --server.port 8501
```

### Step 3 – Open on Phone

On any phone connected to the **same Wi-Fi**, open a browser and go to:
```
http://192.168.1.105:8501
```
(replace with your actual IP)

> **Firewall note (Windows):** If the phone can't connect, allow port 8501 in Windows Firewall:  
> Control Panel → Windows Defender Firewall → Advanced Settings → Inbound Rules → New Rule → Port 8501

---

## 📲 Add to Phone Home Screen (Mobile App Feel)

### Android (Chrome)
1. Open the app URL in Chrome
2. Tap the **⋮ menu → Add to Home screen**
3. Confirm — it appears as an app icon

### iPhone (Safari)
1. Open the app URL in Safari
2. Tap **Share button (□↑) → Add to Home Screen**
3. Confirm — it appears as an app icon

---

## ☁️ Deploy on Streamlit Community Cloud (Free Hosting)

This makes the app accessible from **anywhere on the internet**.

### Step 1 – Push to GitHub

```bash
git init
git add app.py requirements.txt README.md credentials_setup.md
# DO NOT add credentials.json — it's sensitive!
echo "credentials.json" >> .gitignore
git commit -m "Initial commit: Roshan Udhaar Khata"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/roshan-udhaar-khata.git
git push -u origin main
```

### Step 2 – Deploy on Streamlit

1. Go to [https://share.streamlit.io/](https://share.streamlit.io/)
2. Sign in with GitHub
3. Click **New app**
4. Select your repository and set **Main file path** to `app.py`
5. Click **Deploy!**

### Step 3 – Add Secrets (for Google Sheets + PIN)

1. In your deployed app dashboard, click **⋮ → Settings → Secrets**
2. Paste your secrets in TOML format (see `credentials_setup.md` for the full template)
3. Click **Save** — the app restarts automatically

> **Note on CSV data:** Streamlit Community Cloud does **not** persist files between restarts.  
> For permanent cloud storage, enable Google Sheets sync. The Google Sheet becomes your database.

---

## ☁️ Google Sheets Setup (Summary)

For the full guide, see [`credentials_setup.md`](credentials_setup.md).

Quick steps:
1. Create a Google Cloud project, enable Sheets + Drive APIs
2. Create a Service Account, download `credentials.json`
3. Create a Google Sheet, copy its ID from the URL
4. Share the sheet with the service account email as **Editor**
5. Place `credentials.json` next to `app.py` (local) OR add to Streamlit secrets (cloud)
6. Set `SPREADSHEET_ID` in `spreadsheet_id.txt` or `secrets.toml`

---

## 📂 File Structure

```
roshan-udhaar-khata/
├── app.py                        # Main Streamlit application
├── requirements.txt              # Python dependencies
├── README.md                     # This file
├── credentials_setup.md          # Google Sheets setup guide
├── credentials.json              # (optional, do NOT commit to git)
├── spreadsheet_id.txt            # (optional, your Google Sheet ID)
├── .streamlit/
│   └── secrets.toml              # (optional, local secrets file)
├── roshan_all_transactions.csv   # Auto-created on first transaction
├── roshan_customer_totals.csv    # Auto-created on first transaction
└── roshan_deleted_log.csv        # Auto-created when entries are deleted
```

---

## 🔐 Security & PIN

The **Manage / Delete** tab is PIN-protected (default: `1234`).

To change the PIN:
- **Local:** Create `.streamlit/secrets.toml`:
  ```toml
  ADMIN_PIN = "9876"
  ```
- **Cloud:** Add `ADMIN_PIN = "9876"` in the Streamlit Cloud secrets dashboard.

---

## ❓ FAQ & Troubleshooting

**Q: The app won't start — `ModuleNotFoundError`**  
A: Run `pip install -r requirements.txt` again inside your virtual environment.

**Q: Google Sheets sync shows "Not configured"**  
A: Make sure `credentials.json` is in the app folder AND `spreadsheet_id.txt` has your sheet ID, OR both are configured in secrets.

**Q: Phone can't reach the app on Wi-Fi**  
A: Check Windows Firewall — allow port 8501 for inbound connections. Also confirm both devices are on the same Wi-Fi network.

**Q: Data disappeared after Streamlit Cloud restart**  
A: Streamlit Cloud has an ephemeral filesystem. Enable Google Sheets sync — your data will persist there even when the server restarts.

**Q: Running balance looks wrong after deleting an entry**  
A: The app automatically recalculates running balances for the affected customer when you delete a transaction.

**Q: Can I change ₹ to another currency?**  
A: Search for `fmt_inr` in `app.py` and update the `₹` symbol and formatting logic.

**Q: I forgot the PIN**  
A: Default is `1234`. If you've set a custom one via secrets, check `.streamlit/secrets.toml` or the Streamlit Cloud secrets dashboard.

---

## 🛠️ Tech Stack

| Library     | Purpose                              |
|-------------|--------------------------------------|
| Streamlit   | Web UI framework                     |
| Pandas      | CSV data handling                    |
| gspread     | Google Sheets API client             |
| google-auth | OAuth2 credentials for Google APIs   |
| openpyxl    | Excel file support (optional export) |
| decimal     | Precise financial arithmetic         |

---

Made with ❤️ for Roshan General Store.
