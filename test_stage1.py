import pytest
import sqlite3
import os
import uuid
from app import app
from database import get_db, init_db, DB_PATH

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

def test_database_initialization(client):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE role = 'admin'")
    admin = cursor.fetchone()
    assert admin is not None
    assert admin['email'] == 'admin@recoveryplatform.org'
    conn.close()

def test_individual_registration(client):
    response = client.post('/register/individual', data={
        'name': 'Test User',
        'email': 'testuser@example.com',
        'phone': '+919999988888',
        'location': 'Kochi',
        'password': 'UserPassword123!'
    }, follow_redirects=True)
    assert response.status_code == 200

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = 'testuser@example.com'")
    user = cursor.fetchone()
    assert user is not None
    assert user['role'] == 'individual'
    conn.close()

def test_caregiver_verification_and_active_logic(client):
    # Register Caregiver
    client.post('/register/caregiver', data={
        'name': 'Dr. Caregiver',
        'email': 'caregiver@example.com',
        'phone': '+919876543210',
        'location': 'Trivandrum',
        'education': 'M.D. Psychiatry',
        'qualification': 'Licensed Addiction Specialist',
        'experience': '10 Years',
        'password': 'CaregiverPassword123!'
    })

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = 'caregiver@example.com'")
    cg_user = cursor.fetchone()
    cg_id = cg_user['id']

    cursor.execute("SELECT * FROM caregiver_profiles WHERE user_id = ?", (cg_id,))
    profile = cursor.fetchone()
    assert profile['is_verified'] == 0
    assert profile['is_active'] == 0

    # Admin Login & Approve Caregiver
    client.post('/login', data={
        'email': 'admin@recoveryplatform.org',
        'password': 'AdminSecret123!'
    })

    client.post(f'/admin/caregiver/verify/{cg_id}', follow_redirects=True)

    cursor.execute("SELECT * FROM caregiver_profiles WHERE user_id = ?", (cg_id,))
    profile_updated = cursor.fetchone()
    assert profile_updated['is_verified'] == 1
    assert profile_updated['is_active'] == 1
    conn.close()

def test_emergency_contact_limit(client):
    # Register and login user
    email = "limituser@example.com"
    client.post('/register/individual', data={
        'name': 'Limit User',
        'email': email,
        'phone': '+919111111111',
        'location': 'Kozhikode',
        'password': 'Password123!'
    })

    client.post('/login', data={'email': email, 'password': 'Password123!'})

    # Add Contact 1
    client.post('/emergency-contacts/add', data={'name': 'Contact 1', 'phone': '111', 'relationship': 'Parent'})
    # Add Contact 2
    client.post('/emergency-contacts/add', data={'name': 'Contact 2', 'phone': '222', 'relationship': 'Sibling'})
    # Add Contact 3 (Should fail limit 2)
    client.post('/emergency-contacts/add', data={'name': 'Contact 3', 'phone': '333', 'relationship': 'Friend'})

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as count FROM emergency_contacts WHERE user_id = (SELECT id FROM users WHERE email = ?)", (email,))
    count = cursor.fetchone()['count']
    assert count == 2
    conn.close()

if __name__ == '__main__':
    pytest.main(['-v', __file__])
