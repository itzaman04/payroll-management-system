from functools import wraps
from datetime import date

from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash

from database import get_db, init_db, get_attendance_percent
from models import build_employee_object

app = Flask(__name__)
app.secret_key = "change-this-secret-key-before-deploying"  # simple session signing key

init_db()


# ---------- Helpers ----------

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if session.get("role") != "admin":
            flash("Admins only.")
            return redirect(url_for("dashboard"))
        return f(*args, **kwargs)
    return wrapper


# ---------- Auth ----------

@app.route("/")
def index():
    return redirect(url_for("dashboard") if "user_id" in session else url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        conn = get_db()
        user = conn.execute(
            "SELECT * FROM employees WHERE email = ?", (email,)
        ).fetchone()
        conn.close()

        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["name"] = user["name"]
            session["role"] = user["role"]
            return redirect(url_for("dashboard"))

        flash("Invalid email or password.")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------- Dashboard ----------

@app.route("/dashboard")
@login_required
def dashboard():
    conn = get_db()
    total_employees = conn.execute(
        "SELECT COUNT(*) c FROM employees WHERE role != 'admin'"
    ).fetchone()["c"]
    total_managers = conn.execute(
        "SELECT COUNT(*) c FROM employees WHERE role = 'manager'"
    ).fetchone()["c"]
    total_payroll = conn.execute(
        "SELECT COALESCE(SUM(base_salary),0) s FROM employees WHERE role != 'admin'"
    ).fetchone()["s"]
    conn.close()

    return render_template(
        "dashboard.html",
        total_employees=total_employees,
        total_managers=total_managers,
        total_payroll=total_payroll,
    )


# ---------- Employees ----------

@app.route("/employees")
@login_required
@admin_required
def employees():
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM employees WHERE role != 'admin' ORDER BY name"
    ).fetchall()
    conn.close()
    return render_template("employees.html", employees=rows)


@app.route("/employees/add", methods=["GET", "POST"])
@login_required
@admin_required
def add_employee():
    if request.method == "POST":
        name = request.form["name"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        department = request.form["department"].strip()
        role = request.form["role"]
        base_salary = float(request.form["base_salary"])
        team_size = int(request.form.get("team_size") or 0)

        conn = get_db()
        try:
            conn.execute(
                """INSERT INTO employees
                   (name, email, password_hash, department, role, base_salary, team_size)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    name,
                    email,
                    generate_password_hash(password),
                    department,
                    role,
                    base_salary,
                    team_size,
                ),
            )
            conn.commit()
            flash(f"Employee {name} added.")
        except Exception as e:
            flash(f"Error: {e}")
        finally:
            conn.close()
        return redirect(url_for("employees"))

    return render_template("add_employee.html")


@app.route("/employees/<int:emp_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_employee(emp_id):
    conn = get_db()
    conn.execute("DELETE FROM employees WHERE id = ?", (emp_id,))
    conn.commit()
    conn.close()
    flash("Employee removed.")
    return redirect(url_for("employees"))


# ---------- Attendance ----------

@app.route("/attendance", methods=["GET", "POST"])
@login_required
@admin_required
def attendance():
    conn = get_db()
    today = date.today().isoformat()

    if request.method == "POST":
        for key, value in request.form.items():
            if key.startswith("status_"):
                emp_id = key.replace("status_", "")
                conn.execute(
                    """INSERT INTO attendance (employee_id, date, status)
                       VALUES (?, ?, ?)
                       ON CONFLICT(employee_id, date)
                       DO UPDATE SET status = excluded.status""",
                    (emp_id, today, value),
                )
        conn.commit()
        flash(f"Attendance marked for {today}.")

    emp_rows = conn.execute(
        "SELECT id, name, department FROM employees WHERE role != 'admin' ORDER BY name"
    ).fetchall()

    marked_today = {
        r["employee_id"]: r["status"]
        for r in conn.execute(
            "SELECT employee_id, status FROM attendance WHERE date = ?", (today,)
        ).fetchall()
    }
    conn.close()

    return render_template(
        "attendance.html", employees=emp_rows, marked_today=marked_today, today=today
    )


# ---------- Payroll ----------

@app.route("/payroll")
@login_required
@admin_required
def payroll():
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM employees WHERE role != 'admin' ORDER BY name"
    ).fetchall()
    conn.close()

    payslips = []
    for row in rows:
        attendance_percent = get_attendance_percent(row["id"])
        row_dict = dict(row)
        row_dict["attendance_percent"] = attendance_percent

        emp_obj = build_employee_object(row_dict)  # <- polymorphism happens here
        salary_breakdown = emp_obj.calculate_salary()

        payslips.append({
            "id": row["id"],
            "name": row["name"],
            "role": row["role"],
            "department": row["department"],
            "attendance_percent": attendance_percent,
            **salary_breakdown,
        })

    return render_template("payroll.html", payslips=payslips)


# ---------- Own profile (for employee/manager logins) ----------

@app.route("/my-payslip")
@login_required
def my_payslip():
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM employees WHERE id = ?", (session["user_id"],)
    ).fetchone()
    conn.close()

    if not row or row["role"] == "admin":
        return redirect(url_for("dashboard"))

    attendance_percent = get_attendance_percent(row["id"])
    row_dict = dict(row)
    row_dict["attendance_percent"] = attendance_percent
    emp_obj = build_employee_object(row_dict)
    salary_breakdown = emp_obj.calculate_salary()

    return render_template(
        "my_payslip.html",
        name=row["name"],
        attendance_percent=attendance_percent,
        **salary_breakdown,
    )


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
