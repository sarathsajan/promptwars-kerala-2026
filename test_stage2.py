import pytest
import sqlite3
import os
import uuid
from app import app
from database import get_db, init_db, DB_PATH, get_caregiver_rating_info

@pytest.fixture(autouse=True)
def clean_db():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    init_db()

@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    with app.test_client() as c:
        yield c

def test_mood_logging(client):
    # Register & Login Individual
    client.post('/register/individual', data={
        'name': 'Mood User',
        'email': 'mood@example.com',
        'phone': '1234567890',
        'location': 'Kochi',
        'password': 'Password123!'
    })

    client.post('/login', data={'email': 'mood@example.com', 'password': 'Password123!'})

    # Log Mood
    response = client.post('/mood/log', data={'mood_type': 'Calm', 'notes': 'Feeling serene'}, follow_redirects=True)
    assert response.status_code == 200

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM mood_logs WHERE mood_type = 'Calm'")
    log = cursor.fetchone()
    assert log is not None
    assert log['notes'] == 'Feeling serene'
    conn.close()

def test_caregiver_review_system(client):
    # Register Caregiver
    client.post('/register/caregiver', data={
        'name': 'Dr. Reviewee',
        'email': 'doctor@example.com',
        'phone': '9876543210',
        'location': 'Kollam',
        'education': 'M.D.',
        'qualification': 'Psychiatrist',
        'experience': '8 years',
        'password': 'DocPassword123!'
    })

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE email = 'doctor@example.com'")
    cg_id = cursor.fetchone()['id']
    cursor.execute("UPDATE caregiver_profiles SET is_verified = 1, is_active = 1 WHERE user_id = ?", (cg_id,))
    conn.commit()

    # Register Individual (will be auto-assigned)
    client.post('/register/individual', data={
        'name': 'Reviewer User',
        'email': 'reviewer@example.com',
        'phone': '5554443333',
        'location': 'Kochi',
        'password': 'Password123!'
    })

    client.post('/login', data={'email': 'reviewer@example.com', 'password': 'Password123!'})

    # Submit 5 star review
    client.post('/caregiver/review', data={
        'caregiver_id': cg_id,
        'rating': '5',
        'review_text': 'Great caregiver support!'
    }, follow_redirects=True)

    rating_info = get_caregiver_rating_info(cg_id)
    assert rating_info['avg_rating'] == 5.0
    assert rating_info['review_count'] == 1
    conn.close()

def test_case_report_workflow(client):
    # Register Caregiver
    client.post('/register/caregiver', data={
        'name': 'Dr. CaseWriter',
        'email': 'casewriter@example.com',
        'phone': '9876543210',
        'location': 'Kozhikode',
        'education': 'M.S.W.',
        'qualification': 'Counselor',
        'experience': '5 years',
        'password': 'DocPassword123!'
    })

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE email = 'casewriter@example.com'")
    cg_id = cursor.fetchone()['id']
    cursor.execute("UPDATE caregiver_profiles SET is_verified = 1, is_active = 1 WHERE user_id = ?", (cg_id,))
    conn.commit()

    # Register Individual
    client.post('/register/individual', data={
        'name': 'Patient User',
        'email': 'patient@example.com',
        'phone': '1112223333',
        'location': 'Kochi',
        'password': 'Password123!'
    })

    cursor.execute("SELECT id FROM users WHERE email = 'patient@example.com'")
    ind_id = cursor.fetchone()['id']
    conn.close()

    # Login Caregiver and submit Case Report
    client.post('/login', data={'email': 'casewriter@example.com', 'password': 'DocPassword123!'})

    response = client.post('/case-reports/add', data={
        'individual_id': ind_id,
        'report_text': 'Patient showed significant recovery progress in Session 1.'
    }, follow_redirects=True)
    assert response.status_code == 200

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM case_reports WHERE individual_id = ?", (ind_id,))
    report = cursor.fetchone()
    assert report is not None
    assert 'Session 1' in report['report_text']
    conn.close()

if __name__ == '__main__':
    pytest.main(['-v', __file__])
