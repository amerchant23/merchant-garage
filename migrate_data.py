
import sqlite3
import streamlit as st
from supabase import create_client

# Connect to Supabase
url = st.secrets["supabase"]["url"]
key = st.secrets["supabase"]["key"]
supabase = create_client(url, key)

# Connect to local SQLite database
conn = sqlite3.connect("my_garage.db")
conn.row_factory = sqlite3.Row

tables = [
    "vehicles",
    "service_records",
    "mileage_readings",
    "app_settings",
]

print("\nStarting Merchant Garage migration...\n")

for table in tables:

    rows = conn.execute(
        f"SELECT * FROM {table}"
    ).fetchall()

    records = [dict(row) for row in rows]

    print(f"{table}: {len(records)} local records found")

    if not records:
        continue

    # Upload records in batches
    for start in range(0, len(records), 100):

        batch = records[start:start + 100]

        # Preserve existing IDs
        supabase.table(table).upsert(
            batch,
            on_conflict="id" if table != "app_settings" else "setting_key"
        ).execute()

    print(f"{table}: migration successful!")

conn.close()

print("\nMerchant Garage migration completed!")
