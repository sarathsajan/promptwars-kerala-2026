import pytest
import os
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
    with app.test_client() as c:
        yield c

def _register_and_login_individual(client, email="j@example.com", password="Pass123!"):
    client.post('/register/individual', data={
        'name': 'Journal User',
        'email': email,
        'phone': '9999900000',
        'location': 'Kochi',
        'password': password
    })
    client.post('/login', data={'email': email, 'password': password})

def test_journal_page_accessible_to_individual(client):
    _register_and_login_individual(client)
    response = client.get('/journal', follow_redirects=True)
    assert response.status_code == 200

def test_journal_save_text_entry(client):
    _register_and_login_individual(client)
    response = client.post('/journal/save', data={
        'title': 'First Entry',
        'content': 'Today I felt grateful.',
        'transcript': ''
    }, follow_redirects=True)
    assert response.status_code == 200

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM journals WHERE title = 'First Entry'")
    entry = cursor.fetchone()
    assert entry is not None
    assert entry['content'] == 'Today I felt grateful.'
    conn.close()

def test_journal_save_with_transcript(client):
    _register_and_login_individual(client)
    response = client.post('/journal/save', data={
        'title': 'Voice Entry',
        'content': '',
        'transcript': 'I recorded this voice note about my day.'
    }, follow_redirects=True)
    assert response.status_code == 200

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM journals WHERE title = 'Voice Entry'")
    entry = cursor.fetchone()
    assert entry is not None
    assert 'voice note' in entry['transcript']
    conn.close()

def test_journal_private_isolation(client):
    """Verifies caregivers cannot access the journal route"""
    client.post('/register/caregiver', data={
        'name': 'Dr. Test',
        'email': 'cgtest@example.com',
        'phone': '9876500000',
        'location': 'Kochi',
        'education': 'M.D.',
        'qualification': 'Psychiatrist',
        'experience': '5 years',
        'password': 'CgPass123!'
    })
    client.post('/login', data={'email': 'cgtest@example.com', 'password': 'CgPass123!'})

    response = client.get('/journal', follow_redirects=False)
    # Should redirect away (not 200) since role_required('individual') blocks caregiver
    assert response.status_code != 200 or b'Journal' not in response.data

def test_journal_delete_own_entry(client):
    _register_and_login_individual(client)
    client.post('/journal/save', data={
        'title': 'Entry to Delete',
        'content': 'Delete me.',
        'transcript': ''
    })

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM journals WHERE title = 'Entry to Delete'")
    entry_id = cursor.fetchone()['id']
    conn.close()

    response = client.post(f'/journal/delete/{entry_id}', follow_redirects=True)
    assert response.status_code == 200

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM journals WHERE id = ?", (entry_id,))
    assert cursor.fetchone() is None
    conn.close()

if __name__ == '__main__':
    pytest.main(['-v', __file__])
