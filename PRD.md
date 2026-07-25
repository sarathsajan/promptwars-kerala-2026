# Product Requirements Document (PRD)
## Recovery & Prevention Platform (Staged Development Roadmap)

---

## 1. Executive Summary
The **Recovery and Prevention Platform** is a web-based digital health solution designed for individuals navigating substance use disorders and their caregivers. Development is structured into a clear **4-Stage Progressive Implementation Plan**, prioritizing core user authentication, caregiver verification, panic interventions, live chat, and cloud deployment in Stage 1, followed by case reporting, voice/journaling, and Generative AI zero-typing interventions in subsequent stages.

---

## 2. Phased Feature Roadmap & Requirements

### 🚀 STAGE 1: Core Necessities & Foundation (Immediate Focus)

#### 1.1 Registration & Authentication (RBAC)
- **Individual Users**: Self-signup with Name, Phone Number, Location, Email ID, Password. Primary key is an auto-generated UUID (`CHAR(36)`).
- **Caregiver Users**: Self-signup with basic details (Name, Phone, Location) and advanced credentials (Education, Professional Qualification, Experience). Starts as **Unverified / Inactive**. Requires Admin review to activate.
- **Admin Users**: Initial Admin details seeded/hardcoded in database (Name, Phone, Location, Email, Password, UUID).
- **Caregiver Active & Availability Logic**:
  - A Caregiver is considered **Active & Available** ONLY if:
    1. Verified by Admin (`is_verified = 1`).
    2. Logged in within the last 30 days (automated check; >30 days without login sets status to inactive until Admin re-verifies).
    3. Assigned user count is strictly **< 5 individual users** (`current_assigned_users < 5`).
- **Admin Capabilities**:
  - Verify, activate, modify, or delete Caregiver user accounts.
  - Modify or delete Individual user accounts.
  - Add, modify, or delete Administrator user accounts.

#### 1.2 Core Safety & Caregiver Interaction
- **Emergency Contacts & Panic Button**:
  - Individual users can add up to 2 emergency contacts.
  - **Quick Access Panic Button**: Accessible by both the Individual user and their assigned Caregiver for acute crisis or delirious situations. Displays immediate emergency contact details, panic protocol, and one-click help alert.
- **Direct Caregiver Chat System**:
  - Replaces ad-hoc session booking with a real-time/direct **Chat-Based System** connecting Individual users directly to their assigned Caregiver (max 5 assigned users per Caregiver).
- **Educational Hub**:
  - Access to curated resources, helpline directories, harm reduction guidelines, and recovery modules.
- **Cloud Deployment**:
  - Full production-ready deployment on Render / Vercel with a live public URL for judge evaluations.

---

### 🌿 STAGE 2: Enhancements, Case Management & Feedback

#### 2.1 Caregiver Case Reporting
- Caregivers can create and update detailed **Case Reports** for their assigned Individual users.
- Case reports are visible to all current Caregivers and any Caregiver assigned to that user in the future.

#### 2.2 Mood Tracker
- Instant mood tracking button with historical mood logs and visualization.

#### 2.3 Caregiver Rating & Reviews
- Individual users can rate (1-5 stars) and submit qualitative reviews for their assigned Caregiver post-chat/support sessions.

---

### 🎙️ STAGE 3: Voice & Private Journaling

#### 3.1 Private Voice & Journaling
- **Voice Recording & Speech-to-Text**: Voice note recorder with browser-native Web Speech API / Whisper STT conversion.
- **Strictly Private Journal**: User-only journal entries. Private logs are strictly inaccessible to Caregivers and Administrators.

---

### 🤖 STAGE 4: Generative AI Zero-Typing Crisis Interventions

#### 4.1 GenAI Integration Engine
*(Note: GenAI integration begins strictly after Stage 1 core functionalities are stable)*
- **Zero-Typing Interventions**: Dynamic button triggers (e.g., "Severe Craving", "Panic", "Relapse Risk") generating personalized emergency scripts and contextual safety guidance.
- **AI-Enhanced Coping Suggestions**: Dynamic LLM-backed coping strategies generated based on mood logs and user prompts.

---

## 3. Database Schema Blueprint (SQLite)

- `users` (id UUID, role ENUM('individual','caregiver','admin'), name, email, phone, location, password_hash, created_at)
- `caregiver_profiles` (user_id UUID, education, qualification, experience, is_verified, is_active, last_login)
- `assignments` (id UUID, individual_id UUID, caregiver_id UUID, assigned_at)
- `emergency_contacts` (id UUID, user_id UUID, name, phone, relationship)
- `chat_messages` (id UUID, sender_id UUID, receiver_id UUID, message, timestamp)
- `case_reports` (id UUID, individual_id UUID, caregiver_id UUID, content, created_at)
- `mood_logs` (id UUID, user_id UUID, mood_type, created_at)
- `reviews` (id UUID, individual_id UUID, caregiver_id UUID, rating, review_text, created_at)
- `journals` (id UUID, user_id UUID, content, audio_path, transcript, created_at)
