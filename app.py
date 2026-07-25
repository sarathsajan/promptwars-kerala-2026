import os
import uuid
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from database import get_db, init_db, auto_assign_caregiver, update_caregiver_inactivity_status, get_caregiver_assigned_count
from auth import auth_bp, login_required, role_required

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "super-secret-recovery-key-2026")
app.register_blueprint(auth_bp)

# Ensure database tables are created on startup
with app.app_context():
    init_db()

@app.route('/')
def index():
    if 'user_id' in session:
        role = session.get('user_role')
        if role == 'individual':
            return redirect(url_for('dashboard_individual'))
        elif role == 'caregiver':
            return redirect(url_for('dashboard_caregiver'))
        elif role == 'admin':
            return redirect(url_for('dashboard_admin'))
    return redirect(url_for('auth.login'))

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

    # Assigned Caregiver
    cursor.execute("""
        SELECT u.id, u.name, u.email, u.phone, u.location, cp.education, cp.qualification
        FROM assignments a
        JOIN users u ON a.caregiver_id = u.id
        JOIN caregiver_profiles cp ON u.id = cp.user_id
        WHERE a.individual_id = ?
    """, (user_id,))
    caregiver = cursor.fetchone()

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

    conn.close()
    return render_template(
        'dashboard_user.html',
        user=user,
        contacts=contacts,
        caregiver=caregiver
    )

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
# QUICK ACCESS PANIC BUTTON
# ================================

@app.route('/panic')
@login_required
def panic_button():
    user_id = session['user_id']
    user_role = session['user_role']
    conn = get_db()
    cursor = conn.cursor()

    contacts = []
    caregiver = None
    individual_user = None

    if user_role == 'individual':
        cursor.execute("SELECT * FROM emergency_contacts WHERE user_id = ?", (user_id,))
        contacts = cursor.fetchall()

        cursor.execute("""
            SELECT u.name, u.phone, u.email
            FROM assignments a
            JOIN users u ON a.caregiver_id = u.id
            WHERE a.individual_id = ?
        """, (user_id,))
        caregiver = cursor.fetchone()

    elif user_role == 'caregiver':
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
# CAREGIVER DASHBOARD & ROUTES
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

    # Assigned Individuals (max 5)
    cursor.execute("""
        SELECT u.id, u.name, u.email, u.phone, u.location, a.assigned_at
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
        assigned_users=assigned_users,
        assigned_count=assigned_count
    )

# ================================
# DIRECT CHAT SYSTEM
# ================================

@app.route('/chat/<recipient_id>')
@login_required
def chat(recipient_id):
    current_user_id = session['user_id']
    conn = get_db()
    cursor = conn.cursor()

    # Verify relationship (Individual <-> Caregiver)
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
# EDUCATIONAL RESOURCES HUB
# ================================

@app.route('/resources')
@login_required
def resources():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM educational_resources ORDER BY category ASC, title ASC")
    items = cursor.fetchall()
    conn.close()

    # Group by category
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

    # All Caregivers with profile info & assigned user counts
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

    # All Individual Users with assigned caregiver info
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

    # All Admin Users
    cursor.execute("SELECT * FROM users WHERE role = 'admin' ORDER BY created_at ASC")
    admins = cursor.fetchall()

    conn.close()
    return render_template(
        'dashboard_admin.html',
        caregivers=caregivers,
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
