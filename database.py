import sqlite3
import uuid
import os
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash

DB_PATH = os.path.join(os.path.dirname(__file__), "platform.db")

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    return conn

def init_db():
    conn = get_db()
    with open(os.path.join(os.path.dirname(__file__), "schema.sql"), "r") as f:
        schema_sql = f.read()
    conn.executescript(schema_sql)
    
    # Seed default Admin user if not exists
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE role = 'admin'")
    admin = cursor.fetchone()
    if not admin:
        admin_id = str(uuid.uuid4())
        admin_pass = generate_password_hash("AdminSecret123!")
        cursor.execute(
            "INSERT INTO users (id, role, name, email, phone, location, password_hash) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (admin_id, "admin", "System Administrator", "admin@recoveryplatform.org", "+1-800-555-0199", "Kerala, IN", admin_pass)
        )
    
    # Seed Educational Resources if empty
    cursor.execute("SELECT COUNT(*) as count FROM educational_resources")
    if cursor.fetchone()["count"] == 0:
        seed_resources = [
            (
                str(uuid.uuid4()),
                "Understanding Craving Triggers",
                "Coping Strategies",
                "Learn how to identify physical and emotional triggers that lead to substance cravings.",
                "Craving triggers can be environmental, emotional, or social. Recognizing your specific triggers allows you to build proactive defense mechanisms. Practice the HALT check: Hunger, Anger, Loneliness, Tiredness."
            ),
            (
                str(uuid.uuid4()),
                "Emergency Grounding Techniques (5-4-3-2-1)",
                "Crisis Intervention",
                "A step-by-step sensory exercise to de-escalate severe distress or panic.",
                "1. Acknowledge 5 things you see around you.\n2. Acknowledge 4 things you can touch.\n3. Acknowledge 3 things you hear.\n4. Acknowledge 2 things you can smell.\n5. Acknowledge 1 thing you can taste."
            ),
            (
                str(uuid.uuid4()),
                "Caregiver Support & Burnout Prevention",
                "Caregiver Resources",
                "Guidance for caregivers managing loved ones navigating recovery.",
                "Caregiving can be emotionally demanding. Maintain healthy boundaries, seek peer support groups, and ensure you prioritize self-care to prevent burnout while assisting others."
            ),
            (
                str(uuid.uuid4()),
                "Substance Use Helpline Directory",
                "Emergency",
                "National emergency assistance line and crisis intervention support numbers.",
                "National Substance Recovery Helpline: 1800-11-0031 (Toll-Free 24/7). Emergency Medical Services: 112."
            )
        ]
        cursor.executemany(
            "INSERT INTO educational_resources (id, title, category, description, content) VALUES (?, ?, ?, ?, ?)",
            seed_resources
        )

    conn.commit()
    conn.close()
    print("Database initialized successfully.")

def update_caregiver_inactivity_status():
    """Automatically marks caregivers inactive if they haven't logged in for >30 days."""
    conn = get_db()
    cursor = conn.cursor()
    thirty_days_ago = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        "UPDATE caregiver_profiles SET is_active = 0 WHERE last_login < ?",
        (thirty_days_ago,)
    )
    conn.commit()
    conn.close()

def get_caregiver_assigned_count(caregiver_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(*) as count FROM assignments WHERE caregiver_id = ?",
        (caregiver_id,)
    )
    count = cursor.fetchone()["count"]
    conn.close()
    return count

def get_available_caregivers():
    """Returns caregivers who are verified, logged in within 30 days, and have < 5 assigned users."""
    update_caregiver_inactivity_status()
    conn = get_db()
    cursor = conn.cursor()
    query = """
        SELECT * FROM (
            SELECT u.id, u.name, u.email, u.phone, u.location, cp.education, cp.qualification, cp.experience,
                   (SELECT COUNT(*) FROM assignments a WHERE a.caregiver_id = u.id) as assigned_count
            FROM users u
            JOIN caregiver_profiles cp ON u.id = cp.user_id
            WHERE u.role = 'caregiver'
              AND cp.is_verified = 1
              AND cp.is_active = 1
        ) WHERE assigned_count < 5
        ORDER BY assigned_count ASC
    """
    cursor.execute(query)
    caregivers = cursor.fetchall()
    conn.close()
    return caregivers


def get_caregiver_rating_info(caregiver_id):
    """Calculates average rating score (1-5) and total review count for a caregiver."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT AVG(rating) as avg_rating, COUNT(*) as review_count
        FROM reviews
        WHERE caregiver_id = ?
    """, (caregiver_id,))
    row = cursor.fetchone()
    conn.close()
    
    avg_score = round(row['avg_rating'], 1) if row['avg_rating'] else None
    return {
        'avg_rating': avg_score,
        'review_count': row['review_count']
    }

def auto_assign_caregiver(individual_id):
    """Assigns an individual to an available caregiver with space (<5 capacity). Returns caregiver_id or None."""
    available = get_available_caregivers()
    if not available:
        return None
    
    selected_caregiver = available[0]
    caregiver_id = selected_caregiver["id"]
    
    conn = get_db()
    cursor = conn.cursor()
    # Check if already assigned
    cursor.execute("SELECT * FROM assignments WHERE individual_id = ?", (individual_id,))
    existing = cursor.fetchone()
    if not existing:
        assignment_id = str(uuid.uuid4())
        cursor.execute(
            "INSERT INTO assignments (id, individual_id, caregiver_id) VALUES (?, ?, ?)",
            (assignment_id, individual_id, caregiver_id)
        )
        conn.commit()
    conn.close()
    return caregiver_id

if __name__ == "__main__":
    init_db()
