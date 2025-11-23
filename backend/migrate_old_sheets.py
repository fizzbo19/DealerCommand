# migrate_old_sheets.py
import os
from backend.sheet_utils import migrate_sheet_tab

# Ensure APPS_SCRIPT_URL env is set before running
tabs_to_migrate = [
    ("Dealership_Profiles","Email"),
    ("User_Activity","Email"),
    ("Trail_Usage","Email"),
    ("Platinum_Usage","Email"),
    ("Social Media","Email"),
    ("Performance","Email"),
    ("Inventory","Email"),
    ("Car_Listing","Email"),
    ("Listings","Email")
]

if __name__ == "__main__":
    for tab, email_field in tabs_to_migrate:
        ok, msg = migrate_sheet_tab(tab, email_field)
        print(f"{tab}: {ok} - {msg}")
