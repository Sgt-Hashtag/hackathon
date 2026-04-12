from flask import Flask, request, jsonify
import pandas as pd
import sqlite3
import os
from sync_equity import run_priority_sync 
from sms_service import send_invitation_sms

app = Flask(__name__)

# Use absolute paths for Docker stability
DB_PATH = "community.db"
PRIORITY_DB = "priority_engine.db"

def upsert_resident(res):
    """Checks if resident exists, adds if new. Returns True if added."""
    conn = sqlite3.connect(DB_PATH)
    phone = str(res.get("phone"))
    exists = conn.execute("SELECT 1 FROM citizens WHERE phone = ?", (phone,)).fetchone()
    
    added = False
    if not exists:
        df_temp = pd.DataFrame([res])
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