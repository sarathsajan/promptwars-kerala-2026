-- Recovery & Prevention Platform SQLite Schema

PRAGMA foreign_keys = ON;

-- Users Table
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    role TEXT CHECK(role IN ('individual', 'caregiver', 'admin')) NOT NULL,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    phone TEXT NOT NULL,
    location TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Caregiver Profiles Table
CREATE TABLE IF NOT EXISTS caregiver_profiles (
    user_id TEXT PRIMARY KEY,
    education TEXT NOT NULL,
    qualification TEXT NOT NULL,
    experience TEXT NOT NULL,
    is_verified INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 0,
    last_login DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Individual to Caregiver Assignments Table
CREATE TABLE IF NOT EXISTS assignments (
    id TEXT PRIMARY KEY,
    individual_id TEXT UNIQUE NOT NULL,
    caregiver_id TEXT NOT NULL,
    assigned_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(individual_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY(caregiver_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Emergency Contacts Table (Max 2 per individual user)
CREATE TABLE IF NOT EXISTS emergency_contacts (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    phone TEXT NOT NULL,
    relationship TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Chat Messages Table
CREATE TABLE IF NOT EXISTS chat_messages (
    id TEXT PRIMARY KEY,
    sender_id TEXT NOT NULL,
    receiver_id TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(sender_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY(receiver_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Educational Resources Table
CREATE TABLE IF NOT EXISTS educational_resources (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    description TEXT NOT NULL,
    content TEXT NOT NULL,
    external_link TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
