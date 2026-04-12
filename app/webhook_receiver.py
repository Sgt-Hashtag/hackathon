from flask import Flask, request, jsonify
import pandas as pd
import sqlite3
import os
from sync_equity import run_priority_sync  # Ensure this matches your filename

app = Flask(__name__)

# Use absolute paths for Docker stability
DB_PATH = "community.db"

@app.route('/register', methods=['POST'])
@app.route('/ingest', methods=['POST'])
def handle_data():
    data = request.json
    if not data:
        return jsonify({"error": "No data received"}), 400

    # Convert to DataFrame
    df = pd.DataFrame([data] if isinstance(data, dict) else data)
    
    # --- DATA CLEANING ---
    # Ensure phone numbers stay as strings (prevents scientific notation)
    if 'phone' in df.columns:
        df['phone'] = df['phone'].astype(str)
    
    # Flatten stratum_tags if it arrives as a list (for community.db storage)
    if 'stratum_tags' in df.columns:
        df['stratum_tags'] = df['stratum_tags'].apply(
            lambda x: ", ".join(x) if isinstance(x, list) else x
        )

    # 💾 Save to Identity Vault (community.db)
    try:
        conn = sqlite3.connect(DB_PATH)
        df.to_sql('citizens', conn, if_exists='append', index=False)
        conn.close()
        print(f"📥 Logged new data for: {data.get('first_name', 'Unknown')}")
    except Exception as e:
        print(f"❌ Database Error: {e}")
        return jsonify({"error": "Failed to save to community.db"}), 500

    # 🔥 TRIGGER THE EQUITY ENGINE
    # This recalculates the priority_engine.db based on the new data
    try:
        run_priority_sync()
        print("🚀 Priority Engine sync successful.")
    except Exception as e:
        print(f"⚠️ Sync Warning: {e}")
        # We still return 200 because the data was saved, but notify about the sync issue
        return jsonify({"status": "Data saved, but priority sync failed"}), 200

    return jsonify({"status": "Success", "message": "Data saved and priority scores updated"}), 200

if __name__ == '__main__':
    # host='0.0.0.0' is required for Docker to expose the port
    app.run(host='0.0.0.0', port=5000)