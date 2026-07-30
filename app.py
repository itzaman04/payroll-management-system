from functools import wraps
from datetime import date
from io import BytesIO

from flask import (
    Flask, render_template, request, redirect, url_for, session, flash, send_file
)
from werkzeug.security import generate_password_hash, check_password_hash
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

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
    total_departments = conn.execute(
        "SELECT COUNT(DISTINCT department) c FROM employees WHERE role != 'admin'"
    ).fetchone()["c"]

    today = date.today().isoformat()
    present_today = conn.execute(
        "SELECT COUNT(*) c FROM attendance WHERE date = ? AND status = 'present'",
        (today,),
    ).fetchone()["c"]
    marked_today = conn.execute(
        "SELECT COUNT(*) c FROM attendance WHERE date = ?", (today,)
    ).fetchone()["c"]
    attendance_today_percent = (
        round((present_today / marked_today) * 100, 1) if marked_today else 0
    )
    absent_today = marked_today - present_today

    # For the "Employees by Department" chart
    dept_rows = conn.execute(
        """SELECT department, COUNT(*) c FROM employees
           WHERE role != 'admin' GROUP BY department ORDER BY department"""
    ).fetchall()
    dept_labels = [r["department"] for r in dept_rows]
    dept_counts = [r["c"] for r in dept_rows]

    # For the "Payroll Distribution" chart (base salary per employee)
    payroll_rows = conn.execute(
        """SELECT name, base_salary FROM employees
           WHERE role != 'admin' ORDER BY base_salary DESC LIMIT 10"""
    ).fetchall()
    payroll_labels = [r["name"] for r in payroll_rows]
    payroll_values = [r["base_salary"] for r in payroll_rows]

    conn.close()

    return render_template(
        "dashboard.html",
        total_employees=total_employees,
        total_managers=total_managers,
        total_payroll=total_payroll,
        total_departments=total_departments,
        attendance_today_percent=attendance_today_percent,
        present_today=present_today,
        absent_today=absent_today,
        dept_labels=dept_labels,
        dept_counts=dept_counts,
        payroll_labels=payroll_labels,
        payroll_values=payroll_values,
    )


# ---------- Employees ----------

@app.route("/employees")
@login_required
@admin_required
def employees():
    query = request.args.get("q", "").strip()
    conn = get_db()
    if query:
        like = f"%{query}%"
        rows = conn.execute(
            """SELECT * FROM employees
               WHERE role != 'admin'
               AND (name LIKE ? OR email LIKE ? OR department LIKE ?)
               ORDER BY name""",
            (like, like, like),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM employees WHERE role != 'admin' ORDER BY name"
        ).fetchall()
    conn.close()
    return render_template("employees.html", employees=rows, query=query)


@app.route("/employees/<int:emp_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def edit_employee(emp_id):
    conn = get_db()

    if request.method == "POST":
        name = request.form["name"].strip()
        email = request.form["email"].strip().lower()
        department = request.form["department"].strip()
        role = request.form["role"]
        base_salary = float(request.form["base_salary"])
        team_size = int(request.form.get("team_size") or 0)
        new_password = request.form.get("password", "").strip()

        try:
            if new_password:
                conn.execute(
                    """UPDATE employees
                       SET name=?, email=?, department=?, role=?,
                           base_salary=?, team_size=?, password_hash=?
                       WHERE id=?""",
                    (name, email, department, role, base_salary, team_size,
                     generate_password_hash(new_password), emp_id),
                )
            else:
                conn.execute(
                    """UPDATE employees
                       SET name=?, email=?, department=?, role=?,
                           base_salary=?, team_size=?
                       WHERE id=?""",
                    (name, email, department, role, base_salary, team_size, emp_id),
                )
            conn.commit()
            flash(f"Employee {name} updated.")
        except Exception as e:
            flash(f"Error: {e}")
        finally:
            conn.close()
        return redirect(url_for("employees"))

    row = conn.execute("SELECT * FROM employees WHERE id = ?", (emp_id,)).fetchone()
    conn.close()
    if not row:
        flash("Employee not found.")
        return redirect(url_for("employees"))
    return render_template("edit_employee.html", employee=row)


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


def _generate_payslip_pdf(name, role, department, attendance_percent, salary_breakdown):
    """Builds a payslip PDF in memory and returns a BytesIO buffer."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=30 * mm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "Title", parent=styles["Heading1"], alignment=1, spaceAfter=6
    )
    sub_style = ParagraphStyle(
        "Sub", parent=styles["Normal"], alignment=1, textColor=colors.grey
    )

    elements = [
        Paragraph("PayrollSys Pvt. Ltd.", title_style),
        Paragraph("Employee Salary Slip", sub_style),
        Spacer(1, 16),
    ]

    month_year = date.today().strftime("%B %Y")

    info_data = [
        ["Employee Name", name, "Pay Period", month_year],
        ["Role", role.title(), "Department", department],
        ["Attendance", f"{attendance_percent}%", "", ""],
    ]
    info_table = Table(info_data, colWidths=[100, 140, 100, 120])
    info_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.grey),
        ("TEXTCOLOR", (2, 0), (2, -1), colors.grey),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 20))

    salary_data = [
        ["Component", "Amount (₹)"],
        ["Base Salary", f"{salary_breakdown['base_salary']:.2f}"],
        ["Deduction (attendance)", f"- {salary_breakdown['deduction']:.2f}"],
        ["Bonus", f"+ {salary_breakdown['bonus']:.2f}"],
        ["Net Salary", f"{salary_breakdown['net_salary']:.2f}"],
    ]
    salary_table = Table(salary_data, colWidths=[300, 160])
    salary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#313244")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#e6f4ea")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    elements.append(salary_table)
    elements.append(Spacer(1, 24))
    elements.append(Paragraph(
        "This is a system-generated payslip and does not require a signature.",
        sub_style
    ))

    doc.build(elements)
    buffer.seek(0)
    return buffer


@app.route("/payroll/<int:emp_id>/payslip")
@login_required
def download_payslip(emp_id):
    # Admins can download anyone's payslip; employees only their own
    if session.get("role") != "admin" and session.get("user_id") != emp_id:
        flash("You can only download your own payslip.")
        return redirect(url_for("dashboard"))

    conn = get_db()
    row = conn.execute("SELECT * FROM employees WHERE id = ?", (emp_id,)).fetchone()
    conn.close()

    if not row or row["role"] == "admin":
        flash("Employee not found.")
        return redirect(url_for("dashboard"))

    attendance_percent = get_attendance_percent(row["id"])
    row_dict = dict(row)
    row_dict["attendance_percent"] = attendance_percent
    emp_obj = build_employee_object(row_dict)
    salary_breakdown = emp_obj.calculate_salary()

    pdf_buffer = _generate_payslip_pdf(
        row["name"], row["role"], row["department"], attendance_percent, salary_breakdown
    )

    month_tag = date.today().strftime("%B_%Y")
    filename = f"Salary_{row['name'].replace(' ', '_')}_{month_tag}.pdf"

    return send_file(
        pdf_buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
