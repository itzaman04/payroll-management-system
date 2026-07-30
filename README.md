# Employee Payroll Management System

A full-stack web app to manage employees, mark daily attendance, and
auto-calculate monthly payroll — built with Python (Flask), SQLite, and
Bootstrap.

## Features
- Admin & Employee/Manager login (session-based auth, hashed passwords)
- Employee CRUD (add / view / delete)
- Daily attendance marking
- Automatic payroll calculation based on attendance
- OOP-based salary engine: `Employee` base class + `Manager` subclass
  with overridden bonus logic (inheritance + polymorphism)

## Tech Stack
- Backend: Python, Flask
- Database: SQLite (built-in, no server setup needed)
- Frontend: HTML, Bootstrap 5, Jinja2 templates
- Auth: Flask sessions + Werkzeug password hashing

## Run locally
```bash
pip install -r requirements.txt
python app.py
```
Visit `http://localhost:5000`

Default admin login:
- Email: `admin@company.com`
- Password: `admin123`

## Deploy (free, ~10 mins) — Render.com
1. Push this folder to a new GitHub repo.
2. Go to render.com → sign in with GitHub → "New Web Service".
3. Select your repo.
4. Settings:
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn app:app`
5. Click Deploy. You'll get a live URL like `yourapp.onrender.com`.

Note: Render's free tier uses ephemeral storage, so the SQLite file
resets on redeploy/restart — fine for a demo/CV project.
