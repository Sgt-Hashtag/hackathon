from flask import Flask, request, jsonify
import pandas as pd
import sqlite3
import os
from sync_equity import run_priority_sync 
from sms_service import send_invitation_sms

app = Flask(__name__)

# Use absolute paths for Docker stability
DB_PATH = "app/community.db"
PRIORITY_DB = "app/priority_engine.db"

def upsert_resident(res):
    conn = sqlite3.connect(DB_PATH)
    # Standardize phone format (remove spaces and +)
    phone = str(res.get("phone", "")).replace(" ", "").replace("+", "")
    
    exists = conn.execute("SELECT 1 FROM citizens WHERE phone = ?", (phone,)).fetchone()
    
    added = False
    if not exists:
        # Map frontend keys to DB keys if necessary
        clean_data = {
            "first_name": res.get("first_name"),
            "last_name": res.get("last_name"),
            "phone": phone,
            "profession_category": res.get("occupation"), # occupation from frontend
            "stratum_tags": ",".join(res.get("interests", [])) if res.get("interests") else "",
            "age_range": res.get("birthday") # You can calculate exact age later
        }
        df_temp = pd.DataFrame([clean_data])
        df_temp.to_sql('citizens', conn, if_exists='append', index=False)
        added = True
    
    conn.close()
    return added

@app.route('/register', methods=['POST'])
def handle_registration():
    """Flow 1: Self-signup from Lovable"""
    data = request.json
    if not data: return jsonify({"error": "No data"}), 400

    added = upsert_resident(data)
    run_priority_sync() # Update scores

    # For self-registration, we always send a confirmation SMS
    send_invitation_sms(data.get("first_name"), data.get("phone"))
    
    return jsonify({"status": "Registered", "new_user": added}), 200

@app.route('/ingest', methods=['POST'])
def handle_ingest():
    """Flow 2: Batch import from Policy Provider"""
    data = request.json
    if not data: return jsonify({"error": "No data"}), 400

    residents = data if isinstance(data, list) else [data]
    for res in residents:
        upsert_resident(res)

    run_priority_sync()

    # Dispatch logic: Only high priority gets the SMS
    dispatched = []
    conn_p = sqlite3.connect(PRIORITY_DB)
    conn_p.row_factory = sqlite3.Row
    
    for res in residents:
        phone = str(res.get("phone"))
        status = conn_p.execute("SELECT * FROM analytics WHERE phone = ?", (phone,)).fetchone()
        
        if status and status['priority_tier'] == 'high':
            sid = send_invitation_sms(status['first_name'], status['phone'], status['policy_id'])
            if sid: dispatched.append(status['first_name'])

    conn_p.close()
    return jsonify({"status": "Ingested", "sms_sent_to": dispatched}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)