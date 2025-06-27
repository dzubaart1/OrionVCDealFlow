# AI Startup Radar — GitHub → Google Sheets (free-tier)

Daily ETL that hunts for **pre-seed / seed AI-startup repositories** and
drops the 30 most relevant into a Google Sheet.

---

## 1. Google Cloud / Service Account

1. **Create project** → “Enable APIs & Services” → _Google Sheets API_ ➜ Enable.  
2. **APIs & Services → Credentials**  
   * “Create credentials → Service Account”.  
   * Give it `Viewer` role (Sheets API doesn’t need more).  
   * “Keys → Add Key → JSON”. Save the file.  
3. Copy the **service-account e-mail** (ends with `gserviceaccount.com`).  
4. In your target spreadsheet ➜ **Share** with that e-mail (Editor).

---

## 2. Prepare GitHub secrets

| Secret name       | Value                                             |
|-------------------|---------------------------------------------------|
| `GH_TOKEN`        | **Classic** Personal Access Token with `public_repo` scope (free). |
| `GS_CREDS_JSON`   | Entire contents of the downloaded JSON key file **inline**.        |
| `GSHEET_ID`       | The ID portion of `https://docs.google.com/spreadsheets/d/<ID>/`. |
| `GSHEET_TAB`      | Name of the worksheet/tab to overwrite, e.g. `AI-radar`.           |

_Add them under **Repo → Settings → Secrets → Actions**._

---

## 3. Local test (optional)

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

export GH_TOKEN=ghp_...
export GS_CREDS_JSON="$(cat your-sa-key.json)"
export GSHEET_ID=1abcDEF...
export GSHEET_TAB=AI-radar

python daily_ai_startups.py
