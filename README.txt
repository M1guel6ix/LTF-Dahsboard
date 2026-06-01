LTF Data Dashboard Report

Run:
1. cd ltf_dashboard
2. python3 -m venv venv
3. source venv/bin/activate
4. pip install -r requirements.txt
5. python app.py
6. Open http://127.0.0.1:5001

Notes:
- The dashboard reads the Google Sheet by CSV export.
- If the sheet is private, download the sheet as CSV and upload it on the page.
- This version is cleaner: KPI cards, key findings, charts, Top 10 ZIP codes, and expandable audit tables only.
