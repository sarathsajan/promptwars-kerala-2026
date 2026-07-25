import uuid
from datetime import datetime
from functools import wraps
from flask import Blueprint, request, render_template, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from database import get_db, auto_assign_caregiver

auth_bp = Blueprint('auth', __name__)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash("Please log in to access this page.", "warning")
                return redirect(url_for('auth.login'))
            if session.get('user_role') not in roles:
                flash("Unauthorized access.", "danger")
                return redirect(url_for('auth.login'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@auth_bp.route('/register/individual', methods=['POST'])
def register_individual():
    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip().lower()
    phone = request.form.get('phone', '').strip()
    location = request.form.get('location', '').strip()
    password = request.form.get('password', '').strip()

    if not (name and email and phone and location and password):
        flash("All fields are required for individual registration.", "danger")
        return redirect(url_for('auth.login', tab='register-individual'))

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
    if cursor.fetchone():
        conn.close()
        flash("Email address is already registered.", "danger")
        return redirect(url_for('auth.login', tab='register-individual'))

    user_id = str(uuid.uuid4())
    pw_hash = generate_password_hash(password)
    
    cursor.execute(
        "INSERT INTO users (id, role, name, email, phone, location, password_hash) VALUES (?, 'individual', ?, ?, ?, ?, ?)",
        (user_id, name, email, phone, location, pw_hash)
    )
    conn.commit()
    conn.close()

    # Automatically attempt caregiver assignment if active available caregiver exists
    auto_assign_caregiver(user_id)

    flash("Registration successful! Please log in with your credentials.", "success")
    return redirect(url_for('auth.login'))

@auth_bp.route('/register/caregiver', methods=['POST'])
def register_caregiver():
    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip().lower()
    phone = request.form.get('phone', '').strip()
    location = request.form.get('location', '').strip()
    education = request.form.get('education', '').strip()
    qualification = request.form.get('qualification', '').strip()
    experience = request.form.get('experience', '').strip()
    password = request.form.get('password', '').strip()

    if not (name and email and phone and location and education and qualification and experience and password):
        flash("All fields are required for caregiver registration.", "danger")
        return redirect(url_for('auth.login', tab='register-caregiver'))

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
    if cursor.fetchone():
        conn.close()
        flash("Email address is already registered.", "danger")
        return redirect(url_for('auth.login', tab='register-caregiver'))

    user_id = str(uuid.uuid4())
    pw_hash = generate_password_hash(password)
    
    cursor.execute(
        "INSERT INTO users (id, role, name, email, phone, location, password_hash) VALUES (?, 'caregiver', ?, ?, ?, ?, ?)",
        (user_id, name, email, phone, location, pw_hash)
    )
    cursor.execute(
        "INSERT INTO caregiver_profiles (user_id, education, qualification, experience, is_verified, is_active) VALUES (?, ?, ?, ?, 0, 0)",
        (user_id, education, qualification, experience)
    )
    conn.commit()
    conn.close()

    flash("Caregiver registration submitted successfully! Your profile is pending Administrator verification before activation.", "info")
    return redirect(url_for('auth.login'))

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        active_tab = request.args.get('tab', 'login')
        return render_template('login.html', active_tab=active_tab)

    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '').strip()

    if not email or not password:
        flash("Please provide both email and password.", "danger")
        return render_template('login.html', active_tab='login')

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
    user = cursor.fetchone()

    if not user or not check_password_hash(user['password_hash'], password):
        conn.close()
        flash("Invalid email or password.", "danger")
        return render_template('login.html', active_tab='login')

    # Update caregiver last login time
    if user['role'] == 'caregiver':
        cursor.execute("SELECT * FROM caregiver_profiles WHERE user_id = ?", (user['id'],))
        profile = cursor.fetchone()
        now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        if profile and profile['is_verified'] == 1:
            cursor.execute(
                "UPDATE caregiver_profiles SET last_login = ?, is_active = 1 WHERE user_id = ?",
                (now_str, user['id'])
            )
        else:
            cursor.execute(
                "UPDATE caregiver_profiles SET last_login = ? WHERE user_id = ?",
                (now_str, user['id'])
            )
        conn.commit()

    session['user_id'] = user['id']
    session['user_name'] = user['name']
    session['user_email'] = user['email']
    session['user_role'] = user['role']

    conn.close()

    flash(f"Welcome back, {user['name']}!", "success")
    if user['role'] == 'individual':
        return redirect(url_for('dashboard_individual'))
    elif user['role'] == 'caregiver':
        return redirect(url_for('dashboard_caregiver'))
    elif user['role'] == 'admin':
        return redirect(url_for('dashboard_admin'))
    return redirect(url_for('index'))

@auth_bp.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for('auth.login'))
