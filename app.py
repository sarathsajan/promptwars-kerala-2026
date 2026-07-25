import os
import uuid
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from database import get_db, init_db, auto_assign_caregiver, update_caregiver_inactivity_status, get_caregiver_assigned_count, get_caregiver_rating_info
from auth import auth_bp, login_required, role_required

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "super-secret-recovery-key-2026")
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 31536000  # 1 year static asset caching
app.register_blueprint(auth_bp)

# Ensure database tables are created on startup
with app.app_context():
    init_db()

@app.route('/')
def index():
    return render_template('index.html')

# ================================
# INDIVIDUAL USER DASHBOARD & ROUTES
# ================================

@app.route('/dashboard/individual')
@role_required('individual')
def dashboard_individual():
    user_id = session['user_id']
    update_caregiver_inactivity_status()
    conn = get_db()
    cursor = conn.cursor()

    # User profile
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()

    # Emergency Contacts
    cursor.execute("SELECT * FROM emergency_contacts WHERE user_id = ? ORDER BY created_at ASC", (user_id,))
    contacts = cursor.fetchall()

    # Assigned Caregiver with rating info
    cursor.execute("""
        SELECT u.id, u.name, u.email, u.phone, u.location, cp.education, cp.qualification
        FROM assignments a
        JOIN users u ON a.caregiver_id = u.id
        JOIN caregiver_profiles cp ON u.id = cp.user_id
        WHERE a.individual_id = ?
    """, (user_id,))
    caregiver = cursor.fetchone()

    caregiver_rating = None
    existing_review = None
    if caregiver:
        caregiver_rating = get_caregiver_rating_info(caregiver['id'])
        cursor.execute("SELECT * FROM reviews WHERE individual_id = ? AND caregiver_id = ?", (user_id, caregiver['id']))
        existing_review = cursor.fetchone()

    # If no caregiver assigned, try auto-assigning
    if not caregiver:
        assigned_id = auto_assign_caregiver(user_id)
        if assigned_id:
            cursor.execute("""
                SELECT u.id, u.name, u.email, u.phone, u.location, cp.education, cp.qualification
                FROM assignments a
                JOIN users u ON a.caregiver_id = u.id
                JOIN caregiver_profiles cp ON u.id = cp.user_id
                WHERE a.individual_id = ?
            """, (user_id,))
            caregiver = cursor.fetchone()
            if caregiver:
                caregiver_rating = get_caregiver_rating_info(caregiver['id'])

    # Stage 2: Mood Logs History (recent 10)
    cursor.execute("SELECT * FROM mood_logs WHERE user_id = ? ORDER BY created_at DESC LIMIT 10", (user_id,))
    mood_logs = cursor.fetchall()

    conn.close()
    return render_template(
        'dashboard_user.html',
        user=user,
        contacts=contacts,
        caregiver=caregiver,
        caregiver_rating=caregiver_rating,
        existing_review=existing_review,
        mood_logs=mood_logs
    )

# STAGE 2: Mood Tracking Endpoint
@app.route('/mood/log', methods=['POST'])
@role_required('individual')
def log_mood():
    user_id = session['user_id']
    mood_type = request.form.get('mood_type', '').strip()
    notes = request.form.get('notes', '').strip()

    if not mood_type:
        flash("Please select a mood option.", "warning")
        return redirect(url_for('dashboard_individual'))

    log_id = str(uuid.uuid4())
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO mood_logs (id, user_id, mood_type, notes) VALUES (?, ?, ?, ?)",
        (log_id, user_id, mood_type, notes)
    )
    conn.commit()
    conn.close()

    flash(f"Logged your mood as '{mood_type}'. Stay strong!", "success")
    return redirect(url_for('dashboard_individual'))

# STAGE 2: Caregiver Rating & Review Endpoint
@app.route('/caregiver/review', methods=['POST'])
@role_required('individual')
def submit_caregiver_review():
    user_id = session['user_id']
    caregiver_id = request.form.get('caregiver_id')
    rating = request.form.get('rating')
    review_text = request.form.get('review_text', '').strip()

    if not caregiver_id or not rating:
        flash("Rating selection is required.", "danger")
        return redirect(url_for('dashboard_individual'))

    try:
        rating = int(rating)
        if rating < 1 or rating > 5:
            raise ValueError()
    except ValueError:
        flash("Rating must be between 1 and 5 stars.", "danger")
        return redirect(url_for('dashboard_individual'))

    conn = get_db()
    cursor = conn.cursor()
    
    # Check if review already exists for this pair
    cursor.execute("SELECT id FROM reviews WHERE individual_id = ? AND caregiver_id = ?", (user_id, caregiver_id))
    existing = cursor.fetchone()

    if existing:
        cursor.execute(
            "UPDATE reviews SET rating = ?, review_text = ?, created_at = CURRENT_TIMESTAMP WHERE id = ?",
            (rating, review_text, existing['id'])
        )
        flash("Your review has been updated.", "success")
    else:
        review_id = str(uuid.uuid4())
        cursor.execute(
            "INSERT INTO reviews (id, individual_id, caregiver_id, rating, review_text) VALUES (?, ?, ?, ?, ?)",
            (review_id, user_id, caregiver_id, rating, review_text)
        )
        flash("Thank you! Your rating & feedback have been recorded.", "success")

    conn.commit()
    conn.close()
    return redirect(url_for('dashboard_individual'))

@app.route('/emergency-contacts/add', methods=['POST'])
@role_required('individual')
def add_emergency_contact():
    user_id = session['user_id']
    name = request.form.get('name', '').strip()
    phone = request.form.get('phone', '').strip()
    relationship = request.form.get('relationship', '').strip()

    if not (name and phone and relationship):
        flash("Name, phone, and relationship are required.", "danger")
        return redirect(url_for('dashboard_individual'))

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as count FROM emergency_contacts WHERE user_id = ?", (user_id,))
    contact_count = cursor.fetchone()['count']

    if contact_count >= 2:
        conn.close()
        flash("Maximum limit of 2 emergency contacts reached.", "warning")
        return redirect(url_for('dashboard_individual'))

    contact_id = str(uuid.uuid4())
    cursor.execute(
        "INSERT INTO emergency_contacts (id, user_id, name, phone, relationship) VALUES (?, ?, ?, ?, ?)",
        (contact_id, user_id, name, phone, relationship)
    )
    conn.commit()
    conn.close()

    flash("Emergency contact added successfully.", "success")
    return redirect(url_for('dashboard_individual'))

@app.route('/emergency-contacts/delete/<contact_id>', methods=['POST'])
@role_required('individual')
def delete_emergency_contact(contact_id):
    user_id = session['user_id']
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM emergency_contacts WHERE id = ? AND user_id = ?", (contact_id, user_id))
    conn.commit()
    conn.close()
    flash("Emergency contact deleted.", "info")
    return redirect(url_for('dashboard_individual'))

# ================================
# PUBLIC & AUTHENTICATED PANIC BUTTON
# ================================

@app.route('/panic')
def panic_button():
    user_id = session.get('user_id')
    user_role = session.get('user_role')
    conn = get_db()
    cursor = conn.cursor()

    contacts = []
    caregiver = None
    individual_user = None

    if user_id and user_role == 'individual':
        cursor.execute("SELECT * FROM emergency_contacts WHERE user_id = ?", (user_id,))
        contacts = cursor.fetchall()

        cursor.execute("""
            SELECT u.name, u.phone, u.email
            FROM assignments a
            JOIN users u ON a.caregiver_id = u.id
            WHERE a.individual_id = ?
        """, (user_id,))
        caregiver = cursor.fetchone()

    elif user_id and user_role == 'caregiver':
        target_individual_id = request.args.get('user_id')
        if target_individual_id:
            cursor.execute("SELECT * FROM users WHERE id = ?", (target_individual_id,))
            individual_user = cursor.fetchone()
            cursor.execute("SELECT * FROM emergency_contacts WHERE user_id = ?", (target_individual_id,))
            contacts = cursor.fetchall()

    conn.close()
    return render_template(
        'panic.html',
        contacts=contacts,
        caregiver=caregiver,
        individual_user=individual_user
    )

# ================================
# CAREGIVER DASHBOARD & CASE REPORTS
# ================================

@app.route('/dashboard/caregiver')
@role_required('caregiver')
def dashboard_caregiver():
    user_id = session['user_id']
    update_caregiver_inactivity_status()
    conn = get_db()
    cursor = conn.cursor()

    # Caregiver profile
    cursor.execute("""
        SELECT u.id, u.name, u.email, u.phone, u.location, cp.education, cp.qualification, cp.experience, cp.is_verified, cp.is_active, cp.last_login
        FROM users u
        JOIN caregiver_profiles cp ON u.id = cp.user_id
        WHERE u.id = ?
    """, (user_id,))
    caregiver = cursor.fetchone()

    # Caregiver average rating
    rating_info = get_caregiver_rating_info(user_id)

    # Assigned Individuals (max 5)
    cursor.execute("""
        SELECT u.id, u.name, u.email, u.phone, u.location, a.assigned_at,
               (SELECT COUNT(*) FROM case_reports cr WHERE cr.individual_id = u.id) as case_report_count
        FROM assignments a
        JOIN users u ON a.individual_id = u.id
        WHERE a.caregiver_id = ?
        ORDER BY a.assigned_at DESC
    """, (user_id,))
    assigned_users = cursor.fetchall()
    assigned_count = len(assigned_users)

    conn.close()
    return render_template(
        'dashboard_caregiver.html',
        caregiver=caregiver,
        rating_info=rating_info,
        assigned_users=assigned_users,
        assigned_count=assigned_count
    )

# STAGE 2: Case Reports System for Caregivers
@app.route('/case-reports/<individual_id>')
@role_required('caregiver')
def view_case_reports(individual_id):
    caregiver_id = session['user_id']
    conn = get_db()
    cursor = conn.cursor()

    # Fetch individual user details
    cursor.execute("SELECT * FROM users WHERE id = ? AND role = 'individual'", (individual_id,))
    individual = cursor.fetchone()

    if not individual:
        conn.close()
        flash("Individual user not found.", "danger")
        return redirect(url_for('dashboard_caregiver'))

    # Fetch all case reports (written by any caregiver assigned to this individual)
    cursor.execute("""
        SELECT cr.id, cr.report_text, cr.created_at, cg.name as caregiver_name
        FROM case_reports cr
        JOIN users cg ON cr.caregiver_id = cg.id
        WHERE cr.individual_id = ?
        ORDER BY cr.created_at DESC
    """, (individual_id,))
    reports = cursor.fetchall()

    conn.close()
    return render_template('case_reports.html', individual=individual, reports=reports)

@app.route('/case-reports/add', methods=['POST'])
@role_required('caregiver')
def add_case_report():
    caregiver_id = session['user_id']
    individual_id = request.form.get('individual_id')
    report_text = request.form.get('report_text', '').strip()

    if not individual_id or not report_text:
        flash("Case report details cannot be empty.", "danger")
        return redirect(url_for('dashboard_caregiver'))

    report_id = str(uuid.uuid4())
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO case_reports (id, individual_id, caregiver_id, report_text) VALUES (?, ?, ?, ?)",
        (report_id, individual_id, caregiver_id, report_text)
    )
    conn.commit()
    conn.close()

    flash("Case report logged successfully.", "success")
    return redirect(url_for('view_case_reports', individual_id=individual_id))

# ================================
# DIRECT CHAT SYSTEM
# ================================

@app.route('/chat/<recipient_id>')
@login_required
def chat(recipient_id):
    current_user_id = session['user_id']
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE id = ?", (recipient_id,))
    recipient = cursor.fetchone()

    if not recipient:
        conn.close()
        flash("Recipient user not found.", "danger")
        return redirect(url_for('index'))

    # Fetch initial message history
    cursor.execute("""
        SELECT cm.*, u.name as sender_name
        FROM chat_messages cm
        JOIN users u ON cm.sender_id = u.id
        WHERE (sender_id = ? AND receiver_id = ?)
           OR (sender_id = ? AND receiver_id = ?)
        ORDER BY created_at ASC
    """, (current_user_id, recipient_id, recipient_id, current_user_id))
    messages = cursor.fetchall()

    conn.close()
    return render_template('chat.html', recipient=recipient, messages=messages)

@app.route('/api/chat/<recipient_id>/messages')
@login_required
def get_chat_messages(recipient_id):
    current_user_id = session['user_id']
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT cm.id, cm.sender_id, cm.receiver_id, cm.message, cm.created_at, u.name as sender_name
        FROM chat_messages cm
        JOIN users u ON cm.sender_id = u.id
        WHERE (sender_id = ? AND receiver_id = ?)
           OR (sender_id = ? AND receiver_id = ?)
        ORDER BY created_at ASC
    """, (current_user_id, recipient_id, recipient_id, current_user_id))
    messages = cursor.fetchall()
    conn.close()

    result = []
    for msg in messages:
        result.append({
            'id': msg['id'],
            'sender_id': msg['sender_id'],
            'receiver_id': msg['receiver_id'],
            'message': msg['message'],
            'created_at': msg['created_at'],
            'sender_name': msg['sender_name'],
            'is_me': (msg['sender_id'] == current_user_id)
        })

    return jsonify({'status': 'success', 'messages': result})

@app.route('/api/chat/send', methods=['POST'])
@login_required
def send_chat_message():
    current_user_id = session['user_id']
    recipient_id = request.form.get('recipient_id')
    message_text = request.form.get('message', '').strip()

    if not recipient_id or not message_text:
        return jsonify({'status': 'error', 'message': 'Missing recipient or message text.'}), 400

    msg_id = str(uuid.uuid4())
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO chat_messages (id, sender_id, receiver_id, message) VALUES (?, ?, ?, ?)",
        (msg_id, current_user_id, recipient_id, message_text)
    )
    conn.commit()
    conn.close()

    return jsonify({'status': 'success', 'message_id': msg_id})

# ================================
# STAGE 3: PRIVATE JOURNAL & VOICE NOTES (Individual-Only)
# ================================

@app.route('/journal')
@role_required('individual')
def journal():
    user_id = session['user_id']
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM journals WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,)
    )
    entries = cursor.fetchall()
    conn.close()
    return render_template('journal.html', entries=entries)

@app.route('/journal/save', methods=['POST'])
@role_required('individual')
def save_journal():
    user_id = session['user_id']
    title = request.form.get('title', '').strip() or 'Untitled Entry'
    content = request.form.get('content', '').strip()
    transcript = request.form.get('transcript', '').strip()

    if not content and not transcript:
        flash("Journal entry cannot be empty.", "warning")
        return redirect(url_for('journal'))

    entry_id = str(uuid.uuid4())
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO journals (id, user_id, title, content, transcript) VALUES (?, ?, ?, ?, ?)",
        (entry_id, user_id, title, content, transcript)
    )
    conn.commit()
    conn.close()

    flash("Journal entry saved privately.", "success")
    return redirect(url_for('journal'))

@app.route('/journal/delete/<entry_id>', methods=['POST'])
@role_required('individual')
def delete_journal(entry_id):
    user_id = session['user_id']
    conn = get_db()
    cursor = conn.cursor()
    # Strict ownership check: only delete if it belongs to this user
    cursor.execute(
        "DELETE FROM journals WHERE id = ? AND user_id = ?",
        (entry_id, user_id)
    )
    conn.commit()
    conn.close()
    flash("Journal entry deleted.", "info")
    return redirect(url_for('journal'))

# ================================
# EDUCATIONAL RESOURCES HUB
# ================================

@app.route('/resources')
def resources():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM educational_resources ORDER BY category ASC, title ASC")
    items = cursor.fetchall()
    conn.close()

    categorized = {}
    for item in items:
        cat = item['category']
        if cat not in categorized:
            categorized[cat] = []
        categorized[cat].append(item)

    return render_template('resources.html', categorized_resources=categorized)

# ================================
# ADMIN DASHBOARD & ACTIONS
# ================================

@app.route('/dashboard/admin')
@role_required('admin')
def dashboard_admin():
    update_caregiver_inactivity_status()
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT u.id, u.name, u.email, u.phone, u.location, u.created_at,
               cp.education, cp.qualification, cp.experience, cp.is_verified, cp.is_active, cp.last_login,
               (SELECT COUNT(*) FROM assignments a WHERE a.caregiver_id = u.id) as assigned_count
        FROM users u
        JOIN caregiver_profiles cp ON u.id = cp.user_id
        WHERE u.role = 'caregiver'
        ORDER BY cp.is_verified ASC, u.created_at DESC
    """)
    caregivers = cursor.fetchall()

    caregiver_ratings = {}
    for cg in caregivers:
        caregiver_ratings[cg['id']] = get_caregiver_rating_info(cg['id'])

    cursor.execute("""
        SELECT u.id, u.name, u.email, u.phone, u.location, u.created_at,
               cg.name as caregiver_name
        FROM users u
        LEFT JOIN assignments a ON u.id = a.individual_id
        LEFT JOIN users cg ON a.caregiver_id = cg.id
        WHERE u.role = 'individual'
        ORDER BY u.created_at DESC
    """)
    individuals = cursor.fetchall()

    cursor.execute("SELECT * FROM users WHERE role = 'admin' ORDER BY created_at ASC")
    admins = cursor.fetchall()

    conn.close()
    return render_template(
        'dashboard_admin.html',
        caregivers=caregivers,
        caregiver_ratings=caregiver_ratings,
        individuals=individuals,
        admins=admins
    )

@app.route('/admin/caregiver/verify/<caregiver_id>', methods=['POST'])
@role_required('admin')
def admin_verify_caregiver(caregiver_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE caregiver_profiles SET is_verified = 1, is_active = 1 WHERE user_id = ?", (caregiver_id,))
    conn.commit()
    conn.close()
    flash("Caregiver verified and activated successfully.", "success")
    return redirect(url_for('dashboard_admin'))

@app.route('/admin/caregiver/toggle-active/<caregiver_id>', methods=['POST'])
@role_required('admin')
def admin_toggle_caregiver_active(caregiver_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT is_active FROM caregiver_profiles WHERE user_id = ?", (caregiver_id,))
    profile = cursor.fetchone()
    if profile:
        new_active = 0 if profile['is_active'] == 1 else 1
        cursor.execute("UPDATE caregiver_profiles SET is_active = ? WHERE user_id = ?", (new_active, caregiver_id))
        conn.commit()
        flash("Caregiver status updated.", "info")
    conn.close()
    return redirect(url_for('dashboard_admin'))

@app.route('/admin/caregiver/delete/<caregiver_id>', methods=['POST'])
@role_required('admin')
def admin_delete_caregiver(caregiver_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE id = ? AND role = 'caregiver'", (caregiver_id,))
    conn.commit()
    conn.close()
    flash("Caregiver account deleted.", "info")
    return redirect(url_for('dashboard_admin'))

@app.route('/admin/user/delete/<user_id>', methods=['POST'])
@role_required('admin')
def admin_delete_individual(user_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE id = ? AND role = 'individual'", (user_id,))
    conn.commit()
    conn.close()
    flash("Individual user account deleted.", "info")
    return redirect(url_for('dashboard_admin'))

@app.route('/admin/add-admin', methods=['POST'])
@role_required('admin')
def admin_add_admin():
    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip().lower()
    phone = request.form.get('phone', '').strip()
    location = request.form.get('location', '').strip()
    password = request.form.get('password', '').strip()

    if not (name and email and phone and location and password):
        flash("All fields are required to create an admin account.", "danger")
        return redirect(url_for('dashboard_admin'))

    from werkzeug.security import generate_password_hash
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
    if cursor.fetchone():
        conn.close()
        flash("Email already registered.", "danger")
        return redirect(url_for('dashboard_admin'))

    admin_id = str(uuid.uuid4())
    pw_hash = generate_password_hash(password)
    cursor.execute(
        "INSERT INTO users (id, role, name, email, phone, location, password_hash) VALUES (?, 'admin', ?, ?, ?, ?, ?)",
        (admin_id, name, email, phone, location, pw_hash)
    )
    conn.commit()
    conn.close()
    flash("New Admin account created successfully.", "success")
    return redirect(url_for('dashboard_admin'))

@app.route('/admin/delete-admin/<admin_id>', methods=['POST'])
@role_required('admin')
def admin_delete_admin(admin_id):
    if admin_id == session['user_id']:
        flash("You cannot delete your own admin account.", "warning")
        return redirect(url_for('dashboard_admin'))

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE id = ? AND role = 'admin'", (admin_id,))
    conn.commit()
    conn.close()
    flash("Admin account deleted.", "info")
    return redirect(url_for('dashboard_admin'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
