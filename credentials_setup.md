# Google Sheets Setup Guide for Roshan Udhaar Khata

This guide walks you through setting up Google Sheets sync so that every transaction is automatically backed up to a Google Spreadsheet you can view from any device.

---

## Step 1 – Create a Google Cloud Project

1. Go to [https://console.cloud.google.com/](https://console.cloud.google.com/)
2. Click the project dropdown at the top → **New Project**
3. Enter a name (e.g., `Roshan Udhaar Khata`) → **Create**
4. Wait for the project to be created, then select it

---

## Step 2 – Enable Required APIs

1. In the left menu go to **APIs & Services → Library**
2. Search for **Google Sheets API** → Click it → **Enable**
3. Go back to Library, search for **Google Drive API** → Click it → **Enable**

---

## Step 3 – Create a Service Account

1. Go to **APIs & Services → Credentials**
2. Click **+ Create Credentials → Service Account**
3. Enter a name (e.g., `udhaar-khata-bot`) → **Create and Continue**
4. For Role, select **Editor** → **Continue** → **Done**
5. Click on the service account you just created
6. Go to the **Keys** tab → **Add Key → Create New Key**
7. Choose **JSON** → **Create**
8. A file `credentials.json` will be downloaded — **keep this safe!**

---

## Step 4 – Create the Google Spreadsheet

1. Go to [https://sheets.google.com/](https://sheets.google.com/)
2. Click **+ Blank** to create a new spreadsheet
3. Name it something like `Roshan Udhaar Khata`
4. Copy the **Spreadsheet ID** from the URL:
   ```
   https://docs.google.com/spreadsheets/d/THIS_PART_IS_THE_ID/edit
   ```

---

## Step 5 – Share the Spreadsheet with the Service Account

1. Open your `credentials.json` file
2. Find the value of `"client_email"` (looks like `udhaar-khata-bot@your-project.iam.gserviceaccount.com`)
3. In your Google Sheet, click **Share** (top right)
4. Paste the service account email → Set permission to **Editor** → **Send**

---

## Step 6a – Local Setup (credentials.json file)

Place your `credentials.json` file in the **same folder** as `app.py`:

```
roshan-udhaar-khata/
├── app.py
├── credentials.json        ← Place here
├── spreadsheet_id.txt      ← Create this file, paste your Spreadsheet ID inside
└── requirements.txt
```

Create `spreadsheet_id.txt` with just your spreadsheet ID:
```
1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms
```

---

## Step 6b – Streamlit Cloud Setup (secrets)

If deploying to Streamlit Community Cloud, **do NOT upload credentials.json** to GitHub.
Instead, use Streamlit Secrets:

1. Deploy your app on [https://share.streamlit.io/](https://share.streamlit.io/)
2. Go to your app → **⋮ menu → Settings → Secrets**
3. Paste the following (replace with your actual values):

```toml
SPREADSHEET_ID = "your_spreadsheet_id_here"
ADMIN_PIN = "1234"

[gcp_service_account]
type = "service_account"
project_id = "your-project-id"
private_key_id = "abc123"
private_key = "-----BEGIN RSA PRIVATE KEY-----\n...\n-----END RSA PRIVATE KEY-----\n"
client_email = "your-sa@your-project.iam.gserviceaccount.com"
client_id = "1234567890"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "https://www.googleapis.com/robot/v1/metadata/x509/your-sa%40your-project.iam.gserviceaccount.com"
```

> **Tip:** Copy the `private_key` from your `credentials.json` exactly, including `\n` characters.  
> In the secrets editor, the `\n` will be treated as literal newlines automatically.

---

## Step 7 – Verify Connection

1. Run the app: `streamlit run app.py`
2. Go to the **☁️ Google Sheets Sync** tab
3. You should see ✅ **Connected**
4. Click **Sync Now** — your spreadsheet will be populated automatically

---

## Sheet Structure (Auto-Created)

The app creates these sheets in your spreadsheet automatically:

| Sheet Name        | Contents                                      |
|-------------------|-----------------------------------------------|
| `ALL_TRANSACTIONS`| Every transaction from all customers          |
| `SUMMARY`         | One row per customer with totals              |
| `Ramesh` (etc.)   | Individual ledger per customer                |

You do **not** need to create any sheets manually.

---

## Security Notes

- **Never commit `credentials.json` to GitHub** — add it to `.gitignore`
- The service account only has access to sheets you explicitly share with it
- Change the default PIN (`1234`) via `ADMIN_PIN` in secrets
