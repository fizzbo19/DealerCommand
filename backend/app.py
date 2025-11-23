# app.py
import os
import json
import uuid
from datetime import datetime
from flask import Flask, request, jsonify
from sheet_utils import (
    append_to_google_sheet,
    upsert_to_sheet,
    get_sheet_data
)

app = Flask(__name__)

# Environment
SPREADSHEET_NAME = os.environ.get("SPREADSHEET_NAME", "DealerCommand_DB")

# -------------------------
# Helper functions
# -------------------------
def generate_id():
    return str(uuid.uuid4())

def now_iso():
    return datetime.utcnow().isoformat()

def save_record(email, record_type, data_dict, record_id=None):
    """Upsert a record in the unified DB."""
    payload = {
        "ID": record_id or generate_id(),
        "Email": email.lower(),
        "Record_Type": record_type,
        "Data_JSON": json.dumps(data_dict),
        "Created_At": now_iso(),
        "Updated_At": now_iso()
    }
    return upsert_to_sheet(
        sheet_name=SPREADSHEET_NAME,
        key_col="ID",
        data_dict=payload
    )

def get_records(email=None, record_type=None):
    df = get_sheet_data(SPREADSHEET_NAME)
    if df.empty:
        return []
    if email:
        df = df[df["Email"].astype(str).str.lower() == email.lower()]
    if record_type:
        df = df[df["Record_Type"].astype(str) == record_type]
    # parse Data_JSON
    records = []
    for _, row in df.iterrows():
        data = json.loads(row.get("Data_JSON") or "{}")
        data.update({
            "ID": row["ID"],
            "Email": row["Email"],
            "Record_Type": row["Record_Type"],
            "Created_At": row["Created_At"],
            "Updated_At": row["Updated_At"]
        })
        records.append(data)
    return records

# -------------------------
# Routes
# -------------------------

# Ping
@app.route("/ping", methods=["GET"])
def ping():
    return jsonify({"success": True, "message": "DealerCommand API is alive"}), 200

# -------------------------
# Dealership Profile
# -------------------------
@app.route("/dealership/profile", methods=["GET", "POST"])
def dealership_profile():
    email = request.args.get("email") or request.json.get("email")
    if not email:
        return jsonify({"success": False, "error": "Missing email"}), 400

    if request.method == "POST":
        profile_data = request.json.get("profile", {})
        success = save_record(email=email, record_type="Dealership_Profile", data_dict=profile_data)
        return jsonify({"success": success})

    # GET
    profiles = get_records(email=email, record_type="Dealership_Profile")
    if profiles:
        return jsonify({"success": True, "profile": profiles[-1]})
    return jsonify({"success": True, "profile": {}})

# -------------------------
# Inventory
# -------------------------
@app.route("/inventory", methods=["GET", "POST"])
def inventory():
    email = request.args.get("email") or request.json.get("email")
    if not email:
        return jsonify({"success": False, "error": "Missing email"}), 400

    if request.method == "POST":
        inventory_item = request.json.get("item", {})
        record_id = inventory_item.get("ID")  # for update
        success = save_record(email=email, record_type="Inventory", data_dict=inventory_item, record_id=record_id)
        return jsonify({"success": success})

    # GET
    items = get_records(email=email, record_type="Inventory")
    return jsonify({"success": True, "inventory": items})

# -------------------------
# User Activity
# -------------------------
@app.route("/user/activity", methods=["POST"])
def user_activity():
    email = request.json.get("email")
    action = request.json.get("action")
    details = request.json.get("details", {})
    if not email or not action:
        return jsonify({"success": False, "error": "Missing email or action"}), 400

    record = {"Action": action, "Details": details, "Timestamp": now_iso()}
    success = save_record(email=email, record_type="User_Activity", data_dict=record)
    return jsonify({"success": success})

# -------------------------
# Trial Usage
# -------------------------
@app.route("/trial/usage", methods=["POST"])
def trial_usage():
    email = request.json.get("email")
    usage_count = request.json.get("usage_count", 1)
    last_used = now_iso()
    record = {"Usage_Count": usage_count, "Last_Used": last_used}
    success = save_record(email=email, record_type="Trial_Usage", data_dict=record)
    return jsonify({"success": success})

# -------------------------
# Platinum Usage
# -------------------------
@app.route("/platinum/usage", methods=["POST"])
def platinum_usage():
    email = request.json.get("email")
    data = request.json.get("usage", {})
    record = {
        "Listings_Used": data.get("Listings_Used", 0),
        "Scripts_Used": data.get("Scripts_Used", 0),
        "Dashboard_Exported": data.get("Dashboard_Exported", 0),
        "Last_Reset": now_iso()
    }
    success = save_record(email=email, record_type="Platinum_Usage", data_dict=record)
    return jsonify({"success": success})

# -------------------------
# Social Media
# -------------------------
@app.route("/social/media", methods=["GET", "POST"])
def social_media():
    email = request.args.get("email") or request.json.get("email")

    if request.method == "POST":
        data = request.json.get("social", {})
        success = save_record(email=email, record_type="Social_Media", data_dict=data)
        return jsonify({"success": success})

    # GET
    posts = get_records(email=email, record_type="Social_Media")
    return jsonify({"success": True, "posts": posts})

# -------------------------
# Custom Reports
# -------------------------
@app.route("/custom/report", methods=["POST"])
def custom_report():
    email = request.json.get("email")
    report_data = request.json.get("report")
    if not email or not report_data:
        return jsonify({"success": False, "error": "Missing email or report"}), 400

    success = save_record(email=email, record_type="Custom_Report", data_dict=report_data)
    return jsonify({"success": success})

# -------------------------
# AI Scripts
# -------------------------
@app.route("/ai/script", methods=["POST"])
def ai_script():
    email = request.json.get("email")
    script_data = request.json.get("script")
    if not email or not script_data:
        return jsonify({"success": False, "error": "Missing email or script"}), 400

    success = save_record(email=email, record_type="AI_Script", data_dict=script_data)
    return jsonify({"success": success})

# -------------------------
# Performance / Metrics
# -------------------------
@app.route("/performance", methods=["POST"])
def performance():
    email = request.json.get("email")
    metric_data = request.json.get("metric")
    if not email or not metric_data:
        return jsonify({"success": False, "error": "Missing email or metric"}), 400

    success = save_record(email=email, record_type="Performance", data_dict=metric_data)
    return jsonify({"success": success})

# -------------------------
# Run Flask
# -------------------------
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
