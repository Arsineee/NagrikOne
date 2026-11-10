import os
import sqlite3
import uuid
import json
import secrets
from storage_provider import CloudStorageManager
from functools import wraps
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask import Flask, render_template, request, redirect, url_for, session, flash, abort, send_from_directory


app = Flask(__name__)
app.secret_key = "nagrikone_super_secure_college_project_key_2026"

# Cloud Security & Session Hardening
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,       # Prevents XSS scripts from accessing session cookies
    SESSION_COOKIE_SAMESITE="Lax",      # Defends against cross-site timing and CSRF attacks
    PERMANENT_SESSION_LIFETIME=1800     # 30-minute idle session timeout
)

# CSRF Token Generator & Assigner
def get_or_create_csrf_token():
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_hex(32)
    return session["_csrf_token"]

# Make csrf_token() callable in all Jinja templates
app.jinja_env.globals["csrf_token"] = get_or_create_csrf_token

# CSRF Protection & Pre-session Middleware
@app.before_request
def csrf_protect():
    # Guarantee session cookie is populated on first GET load
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_hex(32)

    if request.method == "POST":
        token = request.form.get("csrf_token")
        expected_token = session.get("_csrf_token")
        if not expected_token or not token or not secrets.compare_digest(token, expected_token):
            abort(403)

# Directory & Upload Configuration
DB_FILE = os.path.join(app.root_path, "nagrikone.db")
UPLOAD_FOLDER = os.path.join(app.root_path, "static", "uploads")
ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg"}
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5MB
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
storage_manager = CloudStorageManager(UPLOAD_FOLDER)

# Database Helper
def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row  # Access columns by name like a dictionary
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    

    # 1. Roles
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS roles (
            role_id INTEGER PRIMARY KEY AUTOINCREMENT,
            role_name TEXT NOT NULL UNIQUE
        )
    """)
    cursor.executemany("INSERT OR IGNORE INTO roles (role_id, role_name) VALUES (?, ?)", [
        (1, 'CITIZEN'),
        (2, 'OFFICER'),
        (3, 'ADMIN')
    ])
    
    # 2. Users
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            phone TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            role_id INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (role_id) REFERENCES roles(role_id)
        )
    """)
    
    # 3. Services Catalog
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS services (
            service_id INTEGER PRIMARY KEY AUTOINCREMENT,
            service_name TEXT NOT NULL,
            description TEXT,
            processing_fee REAL DEFAULT 0.0,
            is_active INTEGER DEFAULT 1
        )
    """)
    cursor.executemany("INSERT OR IGNORE INTO services (service_id, service_name, description, processing_fee) VALUES (?, ?, ?, ?)", [
        (1, 'Income Certificate', 'Official document certifying annual family income.', 50.00),
        (2, 'Residence Certificate', 'Official proof of permanent residence in the state.', 30.00),
        (3, 'Scholarship Application', 'State post-matric and merit financial assistance scheme.', 0.00)
    ])
    
    # 4. Applications
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS applications (
            application_id INTEGER PRIMARY KEY AUTOINCREMENT,
            application_number TEXT NOT NULL UNIQUE,
            user_id INTEGER NOT NULL,
            service_id INTEGER NOT NULL,
            status TEXT DEFAULT 'SUBMITTED',
            applicant_data TEXT NOT NULL,
            assigned_officer_id INTEGER NULL,
            officer_remarks TEXT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id),
            FOREIGN KEY (service_id) REFERENCES services(service_id),
            FOREIGN KEY (assigned_officer_id) REFERENCES users(user_id)
        )
    """)
    
    # 5. Documents
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS application_documents (
            document_id INTEGER PRIMARY KEY AUTOINCREMENT,
            application_id INTEGER NOT NULL,
            document_type TEXT NOT NULL,
            file_path TEXT NOT NULL,
            file_size_bytes INTEGER NOT NULL,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (application_id) REFERENCES applications(application_id)
        )
    """)
    
    # 6. Audit Trail
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS application_status_history (
            history_id INTEGER PRIMARY KEY AUTOINCREMENT,
            application_id INTEGER NOT NULL,
            previous_status TEXT,
            new_status TEXT NOT NULL,
            changed_by_user_id INTEGER NOT NULL,
            remarks TEXT,
            changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (application_id) REFERENCES applications(application_id),
            FOREIGN KEY (changed_by_user_id) REFERENCES users(user_id)
        )
    """)

    # 7. Citizen In-App Notifications
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            notification_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            application_id INTEGER,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            is_read INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
            FOREIGN KEY (application_id) REFERENCES applications(application_id) ON DELETE SET NULL
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id, is_read);")

    # Seed Default Officer and Admin (Password: Admin@123)
    pwd_hash = generate_password_hash("Admin@123")
    cursor.execute("INSERT OR IGNORE INTO users (user_id, full_name, email, phone, password_hash, role_id) VALUES (?, ?, ?, ?, ?, ?)",
                   (2, 'Officer Ramesh Sharma', 'officer@nagrikone.gov.in', '9876543210', pwd_hash, 2))
    cursor.execute("INSERT OR IGNORE INTO users (user_id, full_name, email, phone, password_hash, role_id) VALUES (?, ?, ?, ?, ?, ?)",
                   (3, 'System Administrator', 'admin@nagrikone.gov.in', '9123456780', pwd_hash, 3))


    # Composite & Foreign Key Indexes for high-performance lookups
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_apps_user ON applications(user_id, status);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_apps_service ON applications(service_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_history_app ON application_status_history(application_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_docs_app ON application_documents(application_id);")

    conn.commit()
    conn.close()

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

# Notification Helper
def create_notification(user_id, title, message, application_id=None):
    """Helper to dispatch in-app notification to a citizen."""
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO notifications (user_id, application_id, title, message)
            VALUES (?, ?, ?, ?)
        """, (user_id, application_id, title, message))
        conn.commit()
        conn.close()
    except Exception as e:
        app.logger.error(f"Failed to create notification: {e}")

# Inject Unread Notification Count into all Jinja templates
@app.context_processor
def inject_notifications():
    user_id = session.get("user_id")
    if not user_id:
        return {"unread_notifications_count": 0}
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) AS cnt FROM notifications WHERE user_id = ? AND is_read = 0", (user_id,))
        row = cursor.fetchone()
        count = row["cnt"] if row else 0
        conn.close()
        return {"unread_notifications_count": count}
    except Exception as e:
        print("Notification fetch error:", e)
        return {"unread_notifications_count": 0}

# Auth Decorators
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

def role_required(allowed_roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if session.get("role_name") not in allowed_roles:
                abort(403)
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# --- Routes ---
@app.route("/")
def index():
    if "user_id" in session:
        role = session.get("role_name")
        if role == "CITIZEN":
            return redirect(url_for("citizen_dashboard"))
        elif role == "OFFICER":
            return redirect(url_for("officer_dashboard"))
        elif role == "ADMIN":
            return redirect(url_for("admin_dashboard"))
    return redirect(url_for("login"))

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password")

        if not full_name or not email or not phone or not password:
            flash("All fields are required.", "danger")
            return redirect(url_for("register"))

        pwd_hash = generate_password_hash(password)
        db = get_db()
        cursor = db.cursor()
        try:
            cursor.execute("SELECT user_id FROM users WHERE email = ?", (email,))
            if cursor.fetchone():
                flash("Email already registered. Please log in.", "warning")
                return redirect(url_for("login"))

            cursor.execute(
                "INSERT INTO users (full_name, email, phone, password_hash, role_id) VALUES (?, ?, ?, ?, 1)",
                (full_name, email, phone, pwd_hash)
            )
            db.commit()
            flash("Account registered successfully! Please log in.", "success")
            return redirect(url_for("login"))
        except Exception as e:
            db.rollback()
            flash(f"Error during registration: {str(e)}", "danger")
        finally:
            db.close()

    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        db = get_db()
        cursor = db.cursor()
        cursor.execute("""
            SELECT u.*, r.role_name 
            FROM users u 
            JOIN roles r ON u.role_id = r.role_id 
            WHERE u.email = ?
        """, (email,))
        user = cursor.fetchone()
        db.close()

        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["user_id"]
            session["full_name"] = user["full_name"]
            session["email"] = user["email"]
            session["role_name"] = user["role_name"]

            if user["role_name"] == "CITIZEN":
                return redirect(url_for("citizen_dashboard"))
            elif user["role_name"] == "OFFICER":
                return redirect(url_for("officer_dashboard"))
            elif user["role_name"] == "ADMIN":
                return redirect(url_for("admin_dashboard"))
        
        flash("Invalid email or password.", "danger")

    return render_template("login.html")

@app.route("/citizen/application/<int:app_id>/delete", methods=["POST"])
@login_required
@role_required(["CITIZEN"])
def delete_application(app_id):
    conn = get_db()
    cursor = conn.cursor()

    # Verify application belongs to the current citizen
    cursor.execute("""
        SELECT application_id, status 
        FROM applications 
        WHERE application_id = ? AND user_id = ?
    """, (app_id, session["user_id"]))
    app_data = cursor.fetchone()

    if not app_data:
        conn.close()
        flash("Application not found or unauthorized.", "danger")
        return redirect(url_for("citizen_dashboard"))

    try:
        # Retrieve all uploaded file paths linked to this application
        cursor.execute("SELECT file_path FROM application_documents WHERE application_id = ?", (app_id,))
        docs = cursor.fetchall()

        # Delete each document from Azure Blob Storage (or local storage fallback)
        for doc in docs:
            storage_manager.delete_document(doc["file_path"])

        # Delete related database records
        cursor.execute("DELETE FROM application_documents WHERE application_id = ?", (app_id,))
        cursor.execute("DELETE FROM application_status_history WHERE application_id = ?", (app_id,))
        cursor.execute("DELETE FROM notifications WHERE application_id = ?", (app_id,))
        cursor.execute("DELETE FROM applications WHERE application_id = ?", (app_id,))

        conn.commit()
        flash("Application and associated cloud documents deleted successfully.", "info")
    except Exception as e:
        conn.rollback()
        flash(f"Failed to delete application: {e}", "danger")
    finally:
        conn.close()

    return redirect(url_for("citizen_dashboard"))

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been signed out.", "info")
    return redirect(url_for("login"))

# --- Citizen Portal ---
@app.route("/citizen/dashboard")
@login_required
@role_required(["CITIZEN"])
def citizen_dashboard():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT a.*, s.service_name 
        FROM applications a
        JOIN services s ON a.service_id = s.service_id
        WHERE a.user_id = ?
        ORDER BY a.created_at DESC
    """, (session["user_id"],))
    applications = cursor.fetchall()
    
    cursor.execute("SELECT * FROM services WHERE is_active = 1")
    services = cursor.fetchall()
    db.close()

    return render_template("citizen_dashboard.html", applications=applications, services=services)

@app.route("/citizen/apply/<int:service_id>", methods=["GET", "POST"])
@login_required
@role_required(["CITIZEN"])
def apply_service(service_id):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM services WHERE service_id = ? AND is_active = 1", (service_id,))
    service = cursor.fetchone()
    if not service:
        conn.close()
        flash("Service not found or currently unavailable.", "danger")
        return redirect(url_for("citizen_dashboard"))

    if request.method == "POST":
        father_name = request.form.get("father_name", "").strip()
        address = request.form.get("address", "").strip()
        declared_income = request.form.get("declared_income", "0").strip()
        doc_file = request.files.get("document")

        if not father_name or not address or not doc_file or doc_file.filename == "":
            flash("Please fill in all details and attach required proof.", "warning")
            return redirect(request.url)

        if not allowed_file(doc_file.filename):
            flash("Invalid file format. Allowed formats: PDF, PNG, JPG.", "danger")
            return redirect(request.url)

        # 1. Prepare sanitized file metadata
        ext = doc_file.filename.rsplit(".", 1)[1].lower()
        unique_filename = f"{uuid.uuid4().hex}.{ext}"
        save_path = os.path.join(app.config["UPLOAD_FOLDER"], unique_filename)

        # 2. Prepare applicant payload
        app_num = f"NO-{uuid.uuid4().hex[:8].upper()}"
        applicant_data = json.dumps({
            "father_name": father_name,
            "address": address,
            "declared_income": declared_income
        })

        # 3. Save via Storage Manager (Handles Local or Azure Blob)
        stored_filename, file_size = storage_manager.upload_document(doc_file, unique_filename)

        # 4. Strict Contextual Transaction Execution
        try:
            # Step A: Insert master application row
            cursor.execute("""
                INSERT INTO applications (application_number, user_id, service_id, status, applicant_data)
                VALUES (?, ?, ?, 'SUBMITTED', ?)
            """, (app_num, session["user_id"], service_id, applicant_data))
            new_app_id = cursor.lastrowid

            # Step B: Insert supporting document metadata linked by foreign key
            cursor.execute("""
                INSERT INTO application_documents (application_id, document_type, file_path, file_size_bytes)
                VALUES (?, ?, ?, ?)
            """, (new_app_id, "Proof of Identity/Address", stored_filename, file_size))

            # Step C: Insert initial audit trail / state transition log
            cursor.execute("""
                INSERT INTO application_status_history (application_id, previous_status, new_status, changed_by_user_id, remarks)
                VALUES (?, NULL, 'SUBMITTED', ?, 'Application lodged by citizen.')
            """, (new_app_id, session["user_id"]))

            # Step D: Create citizen confirmation notification
            cursor.execute("""
                INSERT INTO notifications (user_id, application_id, title, message)
                VALUES (?, ?, ?, ?)
            """, (session["user_id"], new_app_id, "Application Submitted Successfully",
                  f"Application {app_num} has been lodged and sent for verification."))

            # Atomic Commit: All inserts are committed together
            conn.commit()
            flash(f"Application {app_num} submitted successfully!", "success")
            return redirect(url_for("citizen_dashboard"))

        except Exception as e:
            # Atomic Rollback: Undo all DB changes if ANY error occurs
            conn.rollback()

            # Clean up the orphan file so disk space isn't wasted on a failed application
            if os.path.exists(save_path):
                try:
                    os.remove(save_path)
                except OSError:
                    pass

            flash(f"Failed to submit application: {str(e)}", "danger")
            return redirect(request.url)

        finally:
            conn.close()

    conn.close()
    return render_template("apply_service.html", service=service)

# In-App Notifications Center
@app.route("/citizen/notifications")
@login_required
@role_required(["CITIZEN"])
def citizen_notifications():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT notification_id, title, message, is_read, created_at, application_id
        FROM notifications
        WHERE user_id = ?
        ORDER BY created_at DESC
    """, (session["user_id"],))
    notifications = cursor.fetchall()

    # Mark all unread notifications as read when visiting the inbox
    cursor.execute("UPDATE notifications SET is_read = 1 WHERE user_id = ?", (session["user_id"],))
    db.commit()
    db.close()

    return render_template("notifications.html", notifications=notifications)

@app.route("/citizen/notifications/clear", methods=["POST"])
@login_required
def clear_notifications():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("DELETE FROM notifications WHERE user_id = ?", (session["user_id"],))
    db.commit()
    db.close()
    flash("All notifications cleared.", "info")
    return redirect(url_for("citizen_notifications"))


# --- Officer Portal ---
@app.route("/officer/dashboard")
@login_required
@role_required(["OFFICER", "ADMIN"])
def officer_dashboard():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT a.*, u.full_name as citizen_name, u.email as citizen_email, s.service_name 
        FROM applications a
        JOIN users u ON a.user_id = u.user_id
        JOIN services s ON a.service_id = s.service_id
        ORDER BY a.created_at ASC
    """)
    applications = cursor.fetchall()
    db.close()
    return render_template("officer_dashboard.html", applications=applications)

@app.route("/officer/review/<int:app_id>", methods=["GET", "POST"])
@login_required
@role_required(["OFFICER", "ADMIN"])
def review_application(app_id):
    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
        SELECT a.*, u.full_name as citizen_name, u.email as citizen_email, u.phone as citizen_phone, s.service_name
        FROM applications a
        JOIN users u ON a.user_id = u.user_id
        JOIN services s ON a.service_id = s.service_id
        WHERE a.application_id = ?
    """, (app_id,))
    application = cursor.fetchone()

    if not application:
        db.close()
        abort(404)

    cursor.execute("SELECT * FROM application_documents WHERE application_id = ?", (app_id,))
    documents = cursor.fetchall()

    if request.method == "POST":
        new_status = request.form.get("status")
        remarks = request.form.get("remarks", "").strip()

        allowed_next_states = ["UNDER_REVIEW", "CORRECTION_REQUIRED", "APPROVED", "REJECTED"]
        if new_status not in allowed_next_states:
            flash("Invalid status transition.", "danger")
            return redirect(request.url)

        try:
            cursor.execute("""
                UPDATE applications 
                SET status = ?, officer_remarks = ?, assigned_officer_id = ?, updated_at = CURRENT_TIMESTAMP
                WHERE application_id = ?
            """, (new_status, remarks, session["user_id"], app_id))

            cursor.execute("""
                INSERT INTO application_status_history (application_id, previous_status, new_status, changed_by_user_id, remarks)
                VALUES (?, ?, ?, ?, ?)
            """, (app_id, application["status"], new_status, session["user_id"], remarks))

            # Dispatch notification to the applicant regarding status update
            cursor.execute("""
                INSERT INTO notifications (user_id, application_id, title, message)
                VALUES (?, ?, ?, ?)
            """, (
                application["user_id"],
                app_id,
                f"Application {new_status.replace('_', ' ').title()}",
                f"Your application {application['application_number']} for {application['service_name']} is now {new_status}. Officer Remarks: {remarks or 'None'}"
            ))

            db.commit()
            flash(f"Application updated to {new_status}.", "success")
            return redirect(url_for("officer_dashboard"))
        except Exception as e:
            db.rollback()
            flash(f"Database update failed: {str(e)}", "danger")
        finally:
            db.close()

    db.close()
    applicant_details = json.loads(application["applicant_data"]) if application["applicant_data"] else {}
    return render_template("review_application.html", application=application, documents=documents, applicant_details=applicant_details)

# --- Admin Portal ---
@app.route("/admin/dashboard")
@login_required
@role_required(["ADMIN"])
def admin_dashboard():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT COUNT(*) as total_apps FROM applications")
    total_apps = cursor.fetchone()["total_apps"]

    cursor.execute("SELECT COUNT(*) as total_citizens FROM users WHERE role_id = 1")
    total_citizens = cursor.fetchone()["total_citizens"]

    cursor.execute("SELECT COUNT(*) as total_officers FROM users WHERE role_id = 2")
    total_officers = cursor.fetchone()["total_officers"]

    cursor.execute("""
        SELECT h.*, a.application_number, u.full_name as officer_name 
        FROM application_status_history h
        JOIN applications a ON h.application_id = a.application_id
        JOIN users u ON h.changed_by_user_id = u.user_id
        ORDER BY h.changed_at DESC LIMIT 15
    """)
    logs = cursor.fetchall()
    db.close()

    return render_template("admin_dashboard.html", 
                           total_apps=total_apps, 
                           total_citizens=total_citizens, 
                           total_officers=total_officers, 
                           logs=logs)

# Safe document viewer (Supports Local & Azure SAS token redirection)
@app.route("/documents/<path:filename>")
@login_required
def view_document(filename):
    azure_url = storage_manager.get_document_access_url(filename)
    if azure_url:
        return redirect(azure_url)
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

# --- Official Receipt & Acknowledgment Slip ---
@app.route("/citizen/receipt/<int:app_id>")
@login_required
def view_receipt(app_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT a.*, u.full_name as citizen_name, u.email as citizen_email, u.phone as citizen_phone, s.service_name, s.processing_fee
        FROM applications a
        JOIN users u ON a.user_id = u.user_id
        JOIN services s ON a.service_id = s.service_id
        WHERE a.application_id = ?
    """, (app_id,))
    application = cursor.fetchone()
    db.close()

    if not application:
        abort(404)

    # Insecure Direct Object Reference (IDOR) Protection:
    # Ensure citizens can only access their own receipts unless user is an officer/admin
    if session.get("role_name") == "CITIZEN" and application["user_id"] != session["user_id"]:
        abort(403)

    applicant_data = json.loads(application["applicant_data"]) if application["applicant_data"] else {}
    return render_template("receipt.html", application=application, applicant_data=applicant_data)


if __name__ == "__main__":
    init_db()  # Automatically creates tables & admin/officer accounts on first run!
    app.run(host="127.0.0.1", port=5000, debug=True)