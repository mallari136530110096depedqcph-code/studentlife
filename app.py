from flask import Flask, render_template, request, redirect, url_for, session, flash, make_response
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3, csv, io
from functools import wraps
from datetime import datetime
import numpy as np

app = Flask(__name__)
app.secret_key = "change-this-secret-key"
DB = "studentlife.db"

def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with db() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('admin','student')),
            student_id INTEGER
        );
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_name TEXT NOT NULL,
            course TEXT DEFAULT 'BSIT',
            year_level TEXT DEFAULT '1st Year',
            study_hours REAL NOT NULL,
            attendance REAL NOT NULL,
            previous_grade REAL NOT NULL,
            current_grade REAL DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            predicted_grade REAL NOT NULL,
            prediction_level TEXT NOT NULL,
            remark TEXT NOT NULL,
            prediction_date TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(student_id) REFERENCES students(id)
        );
        """)
        admin = con.execute("SELECT id FROM users WHERE username='admin'").fetchone()
        if not admin:
            con.execute("INSERT INTO users(username,password,role) VALUES(?,?,?)",
                        ("admin", generate_password_hash("admin123"), "admin"))

def login_required(role=None):
    def decorator(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("login"))
            if role and session.get("role") != role:
                return redirect(url_for("dashboard"))
            return fn(*args, **kwargs)
        return wrapped
    return decorator

def model_predict(study_hours, attendance, previous_grade):
    # Fit a small ordinary least-squares model from available student records.
    # If the database is empty, use a transparent baseline based on the project inputs.
    with db() as con:
        rows = con.execute("SELECT study_hours, attendance, previous_grade, current_grade FROM students "
                           "WHERE current_grade > 0").fetchall()
    if len(rows) >= 3:
        x = np.array([[r["study_hours"], r["attendance"], r["previous_grade"], 1] for r in rows], dtype=float)
        y = np.array([r["current_grade"] for r in rows], dtype=float)
        weights, *_ = np.linalg.lstsq(x, y, rcond=None)
        result = float(np.dot([study_hours, attendance, previous_grade, 1], weights))
    else:
        result = 0.5 * previous_grade + 0.3 * (study_hours * 10) + 0.2 * attendance
    return round(max(0, min(100, result)), 2)

def grade_level(grade):
    if grade >= 90: return "Excellent", "Excellent"
    if grade >= 80: return "Very Good", "Very Good"
    if grade >= 70: return "Good", "Good"
    if grade >= 60: return "Needs Improvement", "Needs Improvement"
    return "Fail", "Fail"

@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        with db() as con:
            user = con.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        if user and check_password_hash(user["password"], password):
            session.update(user_id=user["id"], username=user["username"], role=user["role"],
                           student_id=user["student_id"])
            return redirect(url_for("dashboard"))
        flash("Invalid username or password.", "error")
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        name = request.form.get("student_name", "").strip()
        if not username or not password or not name:
            flash("Please complete all fields.", "error")
            return render_template("register.html")
        try:
            with db() as con:
                cur = con.execute("INSERT INTO students(student_name,study_hours,attendance,previous_grade) VALUES(?,?,?,?)",
                                  (name, 0, 0, 0))
                sid = cur.lastrowid
                con.execute("INSERT INTO users(username,password,role,student_id) VALUES(?,?,?,?)",
                            (username, generate_password_hash(password), "student", sid))
            flash("Account created. You can now sign in.", "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("That username is already in use.", "error")
    return render_template("register.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/dashboard")
@login_required()
def dashboard():
    if session["role"] == "student":
        return redirect(url_for("student_dashboard"))
    with db() as con:
        total = con.execute("SELECT COUNT(*) n FROM students").fetchone()["n"]
        avg = con.execute("SELECT AVG(current_grade) n FROM students").fetchone()["n"] or 0
        pred_count = con.execute("SELECT COUNT(*) n FROM predictions").fetchone()["n"]
        students = con.execute("SELECT * FROM students ORDER BY id DESC LIMIT 6").fetchall()
        distribution = con.execute("SELECT prediction_level, COUNT(*) n FROM predictions GROUP BY prediction_level").fetchall()
    return render_template("admin_dashboard.html", total=total, avg=round(avg,1),
                           pred_count=pred_count, students=students, distribution=distribution)

@app.route("/students")
@login_required("admin")
def students():
    q = request.args.get("q", "").strip()
    with db() as con:
        rows = con.execute("SELECT * FROM students WHERE student_name LIKE ? ORDER BY student_name",
                           (f"%{q}%",)).fetchall()
    return render_template("students.html", students=rows, q=q)

@app.route("/students/add", methods=["GET", "POST"])
@login_required("admin")
def add_student():
    if request.method == "POST":
        name = request.form.get("student_name", "").strip()
        course = request.form.get("course", "BSIT")
        year = request.form.get("year_level", "1st Year")
        study = float(request.form.get("study_hours", 0))
        attendance = float(request.form.get("attendance", 0))
        previous = float(request.form.get("previous_grade", 0))
        current = float(request.form.get("current_grade", 0))
        if not name or not (0 <= study <= 105 and 0 <= attendance <= 100 and 0 <= previous <= 100 and 0 <= current <= 100):
            flash("Check the name and valid input ranges.", "error")
        else:
            with db() as con:
                con.execute("""INSERT INTO students(student_name,course,year_level,study_hours,attendance,previous_grade,current_grade)
                               VALUES(?,?,?,?,?,?,?)""", (name,course,year,study,attendance,previous,current))
            flash("Student saved.", "success")
            return redirect(url_for("students"))
    return render_template("student_form.html")

@app.route("/students/<int:sid>/delete", methods=["POST"])
@login_required("admin")
def delete_student(sid):
    with db() as con:
        con.execute("DELETE FROM predictions WHERE student_id=?", (sid,))
        con.execute("DELETE FROM users WHERE student_id=?", (sid,))
        con.execute("DELETE FROM students WHERE id=?", (sid,))
    flash("Student record deleted.", "success")
    return redirect(url_for("students"))

@app.route("/predict", methods=["GET", "POST"])
@login_required()
def predict():
    selected = None
    if session["role"] == "student":
        with db() as con:
            selected = con.execute("SELECT * FROM students WHERE id=?", (session.get("student_id"),)).fetchone()
    if request.method == "POST":
        if session["role"] == "admin":
            sid = int(request.form.get("student_id", 0))
            with db() as con:
                selected = con.execute("SELECT * FROM students WHERE id=?", (sid,)).fetchone()
            if not selected:
                flash("Choose a student.", "error")
                return redirect(url_for("predict"))
            study = float(selected["study_hours"]); attendance = float(selected["attendance"])
            previous = float(selected["previous_grade"])
        else:
            sid = session.get("student_id")
            study = float(request.form.get("study_hours", 0))
            attendance = float(request.form.get("attendance", 0))
            previous = float(request.form.get("previous_grade", 0))
            with db() as con:
                con.execute("UPDATE students SET study_hours=?,attendance=?,previous_grade=? WHERE id=?",
                            (study,attendance,previous,sid))
        predicted = model_predict(study, attendance, previous)
        level, remark = grade_level(predicted)
        with db() as con:
            con.execute("INSERT INTO predictions(student_id,predicted_grade,prediction_level,remark) VALUES(?,?,?,?)",
                        (sid,predicted,level,remark))
        return render_template("prediction_result.html", predicted=predicted, level=level, remark=remark)
    with db() as con:
        choices = con.execute("SELECT * FROM students ORDER BY student_name").fetchall() if session["role"] == "admin" else []
    return render_template("predict.html", student=selected, choices=choices)

@app.route("/history")
@login_required()
def history():
    with db() as con:
        if session["role"] == "admin":
            rows = con.execute("""SELECT p.*,s.student_name FROM predictions p JOIN students s ON s.id=p.student_id
                                  ORDER BY p.prediction_date DESC""").fetchall()
        else:
            rows = con.execute("""SELECT p.*,s.student_name FROM predictions p JOIN students s ON s.id=p.student_id
                                  WHERE p.student_id=? ORDER BY p.prediction_date DESC""",
                               (session.get("student_id"),)).fetchall()
    return render_template("history.html", predictions=rows)

@app.route("/ranking")
@login_required()
def ranking():
    with db() as con:
        rows = con.execute("""SELECT s.*, (SELECT MAX(predicted_grade) FROM predictions p WHERE p.student_id=s.id) predicted
                              FROM students s ORDER BY predicted DESC, current_grade DESC""").fetchall()
    return render_template("ranking.html", students=rows)

@app.route("/reports")
@login_required("admin")
def reports():
    with db() as con:
        rows = con.execute("""SELECT s.student_name,s.course,s.year_level,s.current_grade,
                              p.predicted_grade,p.prediction_level,p.remark,p.prediction_date
                              FROM students s LEFT JOIN predictions p ON p.student_id=s.id
                              ORDER BY p.prediction_date DESC""").fetchall()
    return render_template("reports.html", rows=rows)

@app.route("/reports/csv")
@login_required("admin")
def export_csv():
    with db() as con:
        rows = con.execute("""SELECT s.student_name,s.course,s.year_level,s.study_hours,s.attendance,
                              s.previous_grade,s.current_grade,p.predicted_grade,p.prediction_level,p.remark
                              FROM students s LEFT JOIN predictions p ON p.student_id=s.id""").fetchall()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Student","Course","Year Level","Study Hours","Attendance","Previous Grade",
                     "Current Grade","Predicted Grade","Level","Remark"])
    for row in rows: writer.writerow(list(row))
    response = make_response(output.getvalue())
    response.headers["Content-Disposition"] = "attachment; filename=studentlife_report.csv"
    response.headers["Content-Type"] = "text/csv"
    return response

@app.route("/profile")
@login_required()
def profile():
    student = None
    if session["role"] == "student":
        with db() as con:
            student = con.execute("SELECT * FROM students WHERE id=?", (session.get("student_id"),)).fetchone()
    return render_template("profile.html", student=student)


@app.route("/student-dashboard")
@login_required("student")
def student_dashboard():
    with db() as con:
        student = con.execute("SELECT * FROM students WHERE id=?", (session.get("student_id"),)).fetchone()
        latest = con.execute("SELECT predicted_grade,prediction_level FROM predictions WHERE student_id=? ORDER BY prediction_date DESC LIMIT 1",
                             (session.get("student_id"),)).fetchone()
    prediction = latest["predicted_grade"] if latest else None
    level = latest["prediction_level"] if latest else None
    return render_template("student_dashboard.html", student=student, prediction=prediction, level=level)

if __name__ == "__main__":
    init_db()
    app.run(debug=True)
