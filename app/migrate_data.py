import sqlite3

DB_NAME = "/app/community.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Create citizens table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS citizens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        first_name TEXT,
        phone TEXT,
        profession_category TEXT,
        stratum_tags TEXT,
        age_range TEXT
    )
    """)

    # Insert a test user (matches your phone lookup logic)
    cursor.execute("""
    INSERT INTO citizens (first_name, phone, profession_category, stratum_tags, age_range)
    VALUES (?, ?, ?, ?, ?)
    """, (
        "Max",
        "17688434418",  # store WITHOUT country code for your LIKE query
        "Urban Planner",
        "sustainability,community",
        "30-40"
    ))

    conn.commit()
    conn.close()
    print("✅ Temporary DB initialized with test data.")

if __name__ == "__main__":
    init_db()