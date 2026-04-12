import sqlite3
import json
import numpy as np
import os
import math
from sentence_transformers import SentenceTransformer

# Docker-safe paths - Adjusting to the root of your shared volume
COMMUNITY_DB = "app/community.db"
PRIORITY_DB = "app/priority_engine.db"
MODEL_CACHE_PATH = "/models/sentence-transformers_all-MiniLM-L6-v2"

print("Loading local SentenceTransformer model...")
model = SentenceTransformer(MODEL_CACHE_PATH)

CENSUS = {"age_range": 0.15, "disability_status": 0.12, "profession_category": 0.20}

def cosine_similarity(a, b):
    # Added tiny epsilon to prevent division by zero for empty tags
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9)

def run_priority_sync():
    print("🔄 Syncing Priority Engine with Habermasian weights...")
    policy_emb = model.encode("housing mobility climate")
    
    conn_prio = sqlite3.connect(PRIORITY_DB)
    prio_cursor = conn_prio.cursor()
    prio_cursor.execute("""
        CREATE TABLE IF NOT EXISTS analytics (
            phone TEXT PRIMARY KEY,
            first_name TEXT,
            last_name TEXT,
            priority_score INTEGER,
            priority_tier TEXT,
            stratum_tags TEXT,
            rationale TEXT
        )
    """)

    if not os.path.exists(COMMUNITY_DB):
        print(f"⚠️ {COMMUNITY_DB} not found.")
        return

    conn_comm = sqlite3.connect(COMMUNITY_DB)
    conn_comm.row_factory = sqlite3.Row
    citizens = conn_comm.execute("SELECT * FROM citizens").fetchall()

    for c in citizens:
        citizen = dict(c)
        tags = []
        
        # 1. Stratum Tags
        if citizen.get("profession_category"):
            tags.append(citizen["profession_category"].lower())

        age_val = citizen.get("age_range")
        if age_val:
            try:
                str_age = str(age_val).split('-')[0] if '-' in str(age_val) else str(age_val)
                base_age = int(str_age)
                if base_age < 25: tags.append("youth")
                elif base_age > 60: tags.append("elderly")
            except: pass

        if citizen.get("disability_status") and str(citizen["disability_status"]).lower() != "none":
            tags.append("disability")

        # 2. Impact Alignment
        tag_str = " ".join(tags) if tags else "resident"
        citizen_emb = model.encode(tag_str)
        impact_alignment = max(0, min(1, cosine_similarity(citizen_emb, policy_emb)))

        # 3. Representation Gap
        rep_gap = 0
        if CENSUS["age_range"] > 0.10 and "youth" in tags: rep_gap += 0.33
        if CENSUS["disability_status"] > 0.10 and "disability" in tags: rep_gap += 0.33
        if CENSUS["profession_category"] > 0.10: rep_gap += 0.33
        representation_gap = min(1, rep_gap)

        # 4. Accessibility
        accessibility = 1.0
        if str(citizen.get("digital_access")).lower() == "low": accessibility *= 1.4
        if "disability" in tags: accessibility *= 1.2
        if citizen.get("language_spoken") not in ["de", "en"]: accessibility *= 1.15

        # 5. Fatigue
        participation = citizen.get("past_participation_count") or 0
        fatigue = 1 / math.sqrt(float(participation) + 1)

        # --- FINAL FORMULA ---
        raw_score = ((impact_alignment * 0.4) + (representation_gap * 0.6)) * accessibility * fatigue
        priority_score = int(min(100, round(raw_score * 100)))
        tier = "high" if priority_score >= 70 else "medium" if priority_score >= 40 else "low"
        
        # Safe execute with .get() to avoid KeyError for missing columns
        prio_cursor.execute("""
            INSERT OR REPLACE INTO analytics 
            (phone, first_name, last_name, priority_score, priority_tier, stratum_tags, rationale)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            str(citizen.get("phone", "0000")), 
            citizen.get("first_name", "Resident"), 
            citizen.get("last_name", ""), 
            priority_score, 
            tier, 
            json.dumps(tags), 
            f"Equity: {accessibility:.1f}x boost"
        ))

    conn_prio.commit()
    conn_comm.close()
    conn_prio.close()
    print(f"✅ Priority Engine DB updated ({len(citizens)} records).")

if __name__ == "__main__":
    run_priority_sync()