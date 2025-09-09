from flask import Flask, render_template, request, redirect, url_for, flash, session
import sqlite3
import os
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "secret123"

# ---- DB Setup ----
def init_db():
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fullname TEXT NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    role TEXT NOT NULL)''')
    conn.commit()
    conn.close()

init_db()

# ---- Routes ----
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/signup", methods=["POST"])
def signup():
    fullname = request.form["fullname"]
    email = request.form["email"]
    
    password = request.form["password"]
    
    hashed_password=generate_password_hash(password)
    role = request.form["role"]

    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (fullname, email, password, role) VALUES (?, ?, ?, ?)",
                  (fullname, email, hashed_password, role))
        conn.commit()
    except sqlite3.IntegrityError:
        flash("⚠️ Username already exists!")
        conn.close()
        return redirect(url_for("home"))
    conn.close()

    flash("✅ Signup successful! Please login.")
    return redirect(url_for("home"))

@app.route("/login", methods=["POST"])
def login():
    email = request.form["email"]
    password = request.form["password"]
    role = request.form["role"]

    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute("SELECT id, password FROM users WHERE email=? AND role=?", (email, role))
    user = c.fetchone()
    conn.close()

    if user and check_password_hash(user[1],password):
        session["user"] = email
        session["role"] = role
        session["user_id"] = user[0]   # Save user id from users.db

        if role == "customer":
            return redirect(url_for("dashboard"))
        elif role == "worker":
            # Link to worker_data
            conn = sqlite3.connect("workers.db")
            c = conn.cursor()
            c.execute("SELECT id FROM worker_data WHERE email=?", (email,))
            worker = c.fetchone()
            conn.close()

            if worker:
                # already filled details → dashboard
                return redirect(url_for("dashboard"))
            else:
                # first time → fill worker form
                return redirect(url_for("worker_form_view"))
    else:
        flash("❌ Invalid credentials")
        return redirect(url_for("home"))
    
    
@app.route("/worker_form")
def worker_form():
    if "user" not in session:
        return redirect(url_for("home"))
    return render_template("worker_form.html")

@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("home"))


##################################################

UPLOAD_FOLDER = "static/photos"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

DB_FILE = "workers.db"

# Initialize DB
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS worker_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            worker_id INTEGER,
            fullname TEXT,
            email TEXT,
            phone TEXT,
            location TEXT,
            photo TEXT,
            skills TEXT,
            rate INTEGER ,
            avalability TEXT,
            FOREIGN KEY(worker_id) REFERENCES users(id)
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# Worker form route
@app.route("/worker_form", methods=["GET", "POST"])
def worker_form_view():
    
    if "user_id" not in session or session.get("role") != "worker":
        return redirect(url_for("home"))

    worker_id = session["user_id"]

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Check if worker already filled form
    c.execute("SELECT id FROM worker_data WHERE worker_id=?", (worker_id,))
    worker_exists = c.fetchone()
    conn.close()

    # If already filled → redirect to dashboard
    if worker_exists:
        return redirect(url_for("dashboard"))
   

    if request.method == "POST":
        name=request.form['name']
        phone=request.form["phone"]
        email =request.form["email"]
        location = request.form["location"]
        skills = ",".join(request.form.getlist("skills"))
        
        

        photo_file = request.files.get("photo")
        photo_filename = None
        
        if photo_file and photo_file.filename !="":
            photo_filename = photo_file.filename
            
            photo_file.save(os.path.join("static/photos", photo_filename))

        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''
            INSERT INTO worker_data (fullname, email, phone, location, photo, skills, rate, avalability)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (name,email, phone, location, photo_filename, skills,1000,"yes"))
        conn.commit()
        conn.close()

        return redirect("/dashboard")  # after submission

    return render_template("worker_form.html")




@app.route("/dashboard")
def dashboard():
    
    
    # Get filter values from the URL query parameters
    search_query = request.args.get('search', '')
    service_type = request.args.get('service', 'all')
    location = request.args.get('location', 'all')
    
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # --- Fetch top 10 workers based on skills and location ---
    # Assuming 'rate' in your db represents a rating score.
    # This query selects the top 10 workers ordered by rate.
    top_workers_query = "SELECT * FROM worker_data ORDER BY rate DESC LIMIT 10"
    c.execute(top_workers_query)
    top_workers = c.fetchall()

    # --- Build the main query for the full worker list ---
    sql_query = "SELECT * FROM worker_data WHERE 1=1"
    params = []

    # Add filters to the main query
    if search_query:
        sql_query += " AND (LOWER(fullname) LIKE ? OR LOWER(skills) LIKE ? OR LOWER(location) LIKE ?)"
        params.append(f"%{search_query.lower()}%")
        params.append(f"%{search_query.lower()}%")
        params.append(f"%{search_query.lower()}%")
    if service_type != 'all':
        sql_query += " AND skills LIKE ?"
        params.append(f"%{service_type}%")
        
    if location != 'all':
        sql_query += " AND location LIKE ?"
        params.append(f"%{location}%")

    sql_query += " ORDER BY id DESC"

    c.execute(sql_query, params)
    filtered_workers = c.fetchall()
    
    user_email = session.get("user")
    current_worker_photo = None
    if session.get("role") == "worker":
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        c.execute("SELECT photo FROM worker_data WHERE email=?", (user_email,))
        worker_data = c.fetchone()
        
        for worker in worker_data:
            current_worker_photo =  worker
    
    conn.close()
    

    return render_template("dashboard.html", 
        
        workers=filtered_workers,
        top_workers=top_workers,
        current_worker_photo=current_worker_photo,
        current_service=request.args.get("service", "all"),
        current_location=request.args.get("location", "all"),
        current_search=request.args.get("search", ""))
        
    
    


@app.route("/profile", methods=["GET", "POST"])
def profile():
    if "user" not in session:
        return redirect(url_for("home"))

    email = session["user"]

    # Get worker_id
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE email=?", (email,))
    user = c.fetchone()
    conn.close()

    if not user:
        flash("⚠️ Worker not found")
        return redirect(url_for("dashboard"))

    worker_id = user[0]

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    if request.method == "POST":
        name = request.form["fullname"]
        phone = request.form["phone"]
        location = request.form["location"]
        rate = request.form["rate"]
        availability = request.form["availability"]

        # Handle photo update
        photo_file = request.files.get("photo")
        photo_filename = None
        if photo_file and photo_file.filename:
            photo_filename = os.path.join(app.config['UPLOAD_FOLDER'], photo_file.filename)
            photo_file.save(photo_filename)

            c.execute("""UPDATE worker_data 
                         SET fullname=?, phone=?, location=?, rate=?, avalability=?, photo=?
                         WHERE worker_id=?""",
                      (name, phone, location, rate, availability, photo_filename, worker_id))
        else:
            c.execute("""UPDATE worker_data 
                         SET fullname=?, phone=?, location=?, rate=?, avalability=?
                         WHERE worker_id=?""",
                      (name, phone, location, rate, availability, worker_id))

        conn.commit()

    # Fetch worker data
    c.execute("SELECT fullname, email, phone, location, photo, skills, rate, avalability FROM worker_data WHERE worker_id=?", (worker_id,))
    user_email = session.get("user")
    c.execute("SELECT photo FROM worker_data WHERE email=?", (user_email,))
    worker_data = c.fetchone()
        
    for worker in worker_data:
        current_worker_photo =  worker
    
    
    
    worker = c.fetchone()
    conn.close()

    return render_template("profile.html", worker=worker,current_worker_photo=current_worker_photo)

@app.route("/worker_details/<int:worker_id>")
def worker_details(worker_id):
    
    conn = sqlite3.connect("workers.db")
    conn.row_factory = sqlite3.Row  # Use this to access columns by name
    c = conn.cursor()

    # Get the specific worker's details using their ID
    c.execute("SELECT * FROM worker_data WHERE id=?", (worker_id,))
    worker = c.fetchone()
    conn.close()

    if worker:
        return render_template("worker_home.html", worker=worker)
    else:
        flash("Worker not found.")
        return redirect(url_for("dashboard"))
    
    


if __name__ == "__main__":
    app.run(debug=True)
