from flask import Flask, render_template, request
import pandas as pd
import re

app = Flask(__name__)

# Google Sheet info from your link
SHEET_ID = "1oI9tL1Utn7O3OxJNmn2GAl0xINh10bYIcd7XNqMuPXg"
GID = "0"
CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={GID}"

# Change these only if your sheet column names are different
POSSIBLE_COLUMNS = {
    "name": ["Name", "Client Name", "Full Name", "Family Name", "CLIENT'S NAME"],
    "race": ["Race/Ethnicity", "Race / Ethnicity", "Race", "Ethnicity", "RACE / ETHNICITY"],
    "zip": ["Zip", "Zip Code", "ZIP", "ZIP CODE", "Zipcode", "Postal Code"],
    "gender": ["Gender", "GENDER", "Sex"],
    "dob": ["DOB", "Date of Birth", "DATE OF BIRTH", "DATE OF BI", "Birth Date"],
    "age": ["Age"],
    "language": ["Language", "Languages", "LANGUAGES", "Primary Language", "Preferred Language"],
}

SF_ZIPS = [
    "94101", "94102", "94103", "94104", "94105", "94106", "94107", "94108", "94109", "94110",
    "94111", "94112", "94113", "94114", "94115", "94116", "94117", "94118", "94121", "94122",
    "94123", "94124", "94127", "94129", "94130", "94131", "94132", "94133", "94134", "94158"
]

RACE_CATEGORIES = [
    "African American/Black",
    "American Indian/Alaskan Native",
    "Asian/Pacific Islander",
    "Latinx",
    "Other/Multi racial",
    "White",
    "Decline to Answer/Not Specified",
]
GENDER_CATEGORIES = ["Female", "Male", "Non-binary", "Transgender", "Unknown"]
AGE_CATEGORIES = ["18-24", "25-35", "35-50", "50-99", "Unknown"]
LANGUAGE_CATEGORIES = [
    "English", "Spanish", "Cantonese", "Mandarin", "Filipino", "Russian", "Arabic",
    "Mayan", "Mam", "Tongan", "Portuguese", "Other", "None Specified",
    "Two or More Languages", "Three or more languages"
]


def find_col(df, keys):
    normalized = {str(c).strip().lower(): c for c in df.columns}
    for key in keys:
        if key.strip().lower() in normalized:
            return normalized[key.strip().lower()]
    for c in df.columns:
        c_low = str(c).strip().lower()
        for key in keys:
            if key.strip().lower() in c_low or c_low in key.strip().lower():
                return c
    return None


def clean_text(value):
    if pd.isna(value):
        return ""
    return str(value).strip()


def classify_race(value):
    v = clean_text(value).lower()
    if not v or v in ["nan", "none", "unknown", "decline", "declined", "n/a", "na"]:
        return "Decline to Answer/Not Specified"

    # Order matters: this returns ONE category per record, so totals do not double-count.
    if any(x in v for x in ["latinx", "latino", "latina", "hispanic", "hispano", "mexican", "central american", "salvador", "guatemala", "nicaragua"]):
        return "Latinx"
    if any(x in v for x in ["black", "african american", "african-american"]):
        return "African American/Black"
    if any(x in v for x in ["american indian", "alaskan", "native american", "indigenous"]):
        return "American Indian/Alaskan Native"
    if any(x in v for x in ["asian", "pacific", "api", "filipino", "chinese", "vietnamese", "samoan"]):
        return "Asian/Pacific Islander"
    if "white" in v:
        return "White"
    if any(x in v for x in ["multi", "mixed", "mix", "other"]):
        return "Other/Multi racial"
    return "Other/Multi racial"


def classify_gender(value):
    v = clean_text(value).lower()
    if not v or v in ["nan", "unknown", "n/a", "na", "none"]:
        return "Unknown"
    if "trans" in v:
        return "Transgender"
    if "non" in v or v == "nb" or "nonbinary" in v:
        return "Non-binary"
    if v.startswith("f") or "female" in v or "woman" in v:
        return "Female"
    if v.startswith("m") or "male" in v or "man" in v:
        return "Male"
    return "Unknown"


def parse_age(row, age_col, dob_col):
    if age_col and pd.notna(row.get(age_col)):
        try:
            age = int(float(row.get(age_col)))
            if 0 <= age <= 120:
                return age
        except Exception:
            pass
    if dob_col and pd.notna(row.get(dob_col)):
        dob = pd.to_datetime(row.get(dob_col), errors="coerce")
        if pd.notna(dob):
            today = pd.Timestamp.today()
            age = int((today - dob).days // 365.25)
            if 0 <= age <= 120:
                return age
    return None


def classify_age(age):
    if age is None or pd.isna(age):
        return "Unknown"
    if 18 <= age <= 24:
        return "18-24"
    if 25 <= age <= 35:
        return "25-35"
    if 36 <= age <= 50:
        return "35-50"
    if 51 <= age <= 99:
        return "50-99"
    return "Unknown"


def normalize_zip(value):
    v = clean_text(value)
    match = re.search(r"\b(\d{5})\b", v)
    return match.group(1) if match else "Out Of SF or Unknown"


def language_counts(series):
    counts = {k: 0 for k in LANGUAGE_CATEGORIES}
    mapping = {
        "English": ["english", "inglés", "ingles"],
        "Spanish": ["spanish", "español", "espanol"],
        "Cantonese": ["cantonese"],
        "Mandarin": ["mandarin"],
        "Filipino": ["filipino", "tagalog"],
        "Russian": ["russian"],
        "Arabic": ["arabic"],
        "Mayan": ["mayan", "maya"],
        "Mam": ["mam"],
        "Tongan": ["tongan"],
        "Portuguese": ["portuguese"],
    }
    for value in series.fillna(""):
        raw = clean_text(value)
        low = raw.lower()
        if not raw:
            counts["None Specified"] += 1
            continue
        found = []
        for lang, terms in mapping.items():
            if any(t in low for t in terms):
                counts[lang] += 1
                found.append(lang)
        unique_found = set(found)
        if len(unique_found) == 0:
            counts["Other"] += 1
        elif len(unique_found) == 2:
            counts["Two or More Languages"] += 1
        elif len(unique_found) >= 3:
            counts["Three or more languages"] += 1
    return counts


def counts_table(counts, order=None, include_total=True, hide_zeros=False):
    order = order or list(counts.keys())
    rows, total = [], 0
    for item in order:
        value = int(counts.get(item, 0))
        total += value
        if hide_zeros and value == 0:
            continue
        rows.append({"Category": item, "Count": value})
    if include_total:
        rows.append({"Category": "Total", "Count": total})
    return rows


def add_percent(rows, total):
    clean_rows = []
    for row in rows:
        if row["Category"] == "Total":
            continue
        pct = round((row["Count"] / total) * 100, 1) if total else 0
        clean_rows.append({**row, "Percent": pct})
    return clean_rows


def top_rows(rows, limit=10):
    filtered = [r for r in rows if r["Category"] != "Total" and r["Count"] > 0]
    return sorted(filtered, key=lambda x: x["Count"], reverse=True)[:limit]


def build_report(df):
    cols = {k: find_col(df, v) for k, v in POSSIBLE_COLUMNS.items()}
    total_rows = int(len(df))

    if cols["name"]:
        names = df[cols["name"]].dropna().astype(str).str.strip()
        families_served = int(names.replace("", pd.NA).dropna().nunique())
    else:
        families_served = total_rows

    race_series = df[cols["race"]].apply(classify_race) if cols["race"] else pd.Series(["Decline to Answer/Not Specified"] * len(df))
    race_rows = counts_table(race_series.value_counts().to_dict(), RACE_CATEGORIES, include_total=False)
    race_rows = add_percent(race_rows, total_rows)

    zip_series = df[cols["zip"]].apply(normalize_zip) if cols["zip"] else pd.Series(["Out Of SF or Unknown"] * len(df))
    zip_counts = {z: int((zip_series == z).sum()) for z in SF_ZIPS}
    zip_counts["Out Of SF or Unknown"] = int((~zip_series.isin(SF_ZIPS)).sum())
    zip_rows = counts_table(zip_counts, SF_ZIPS + ["Out Of SF or Unknown"], include_total=False, hide_zeros=True)
    zip_rows = add_percent(zip_rows, total_rows)
    top_zip_rows = top_rows(zip_rows, 10)

    gender_series = df[cols["gender"]].apply(classify_gender) if cols["gender"] else pd.Series(["Unknown"] * len(df))
    gender_rows = counts_table(gender_series.value_counts().to_dict(), GENDER_CATEGORIES, include_total=False)
    gender_rows = add_percent(gender_rows, total_rows)

    age_values = df.apply(lambda row: parse_age(row, cols["age"], cols["dob"]), axis=1)
    age_series = age_values.apply(classify_age)
    age_rows = counts_table(age_series.value_counts().to_dict(), AGE_CATEGORIES, include_total=False)
    age_rows = add_percent(age_rows, total_rows)

    lang_counts = language_counts(df[cols["language"]]) if cols["language"] else {k: 0 for k in LANGUAGE_CATEGORIES}
    if not cols["language"]:
        lang_counts["None Specified"] = total_rows
    lang_rows = counts_table(lang_counts, LANGUAGE_CATEGORIES, include_total=False, hide_zeros=True)
    lang_rows = add_percent(lang_rows, total_rows)
    top_lang_rows = top_rows(lang_rows, 10)

    latinx = next((r for r in race_rows if r["Category"] == "Latinx"), {"Count": 0, "Percent": 0})
    female = next((r for r in gender_rows if r["Category"] == "Female"), {"Count": 0, "Percent": 0})
    top_zip = top_zip_rows[0] if top_zip_rows else {"Category": "N/A", "Count": 0, "Percent": 0}
    top_lang = top_lang_rows[0] if top_lang_rows else {"Category": "N/A", "Count": 0, "Percent": 0}

    findings = [
        f"{families_served:,} families served across {total_rows:,} total records.",
        f"Latinx clients represent {latinx['Percent']}% of total records ({latinx['Count']:,}).",
        f"The highest ZIP code concentration is {top_zip['Category']} with {top_zip['Count']:,} records.",
        f"The most common language category is {top_lang['Category']} with {top_lang['Count']:,} records.",
    ]

    return {
        "families_served": families_served,
        "total_rows": total_rows,
        "latinx_percent": latinx["Percent"],
        "female_percent": female["Percent"],
        "columns_found": cols,
        "race_rows": race_rows,
        "gender_rows": gender_rows,
        "age_rows": age_rows,
        "zip_rows": zip_rows,
        "top_zip_rows": top_zip_rows,
        "language_rows": lang_rows,
        "top_language_rows": top_lang_rows,
        "findings": findings,
    }


def load_data():
    uploaded = request.files.get("file") if request.method == "POST" else None
    if uploaded and uploaded.filename:
        return pd.read_csv(uploaded)
    return pd.read_csv(CSV_URL)


@app.route("/", methods=["GET", "POST"])
def dashboard():
    error = None
    report = None
    try:
        df = load_data()
        report = build_report(df)
    except Exception as e:
        error = str(e)
    return render_template("dashboard.html", report=report, error=error)


if __name__ == "__main__":
    app.run(debug=True, port=5001)
