from flask import Flask, render_template, redirect, url_for, request, jsonify, session, flash
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm
from wtforms import StringField, DateField, TextAreaField, DecimalField, SelectField, SubmitField, HiddenField, BooleanField, PasswordField, FileField
from werkzeug.utils import secure_filename
from wtforms.validators import DataRequired, NumberRange, Optional, Email, EqualTo, Length, ValidationError
from datetime import datetime, date, timedelta
from decimal import Decimal
import os
import math
import logging
import secrets
from sqlalchemy import select
from werkzeug.security import generate_password_hash, check_password_hash
import smtplib
from email.message import EmailMessage
from app.geo import haversine
from flask_migrate import Migrate

db = SQLAlchemy()
logger = logging.getLogger("mileage")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

login_attempts = {}

class Trip(db.Model):
    __tablename__ = "trips"

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, index=True)
    trip_type = db.Column(db.String(20), nullable=False, default="business")
    vehicle = db.Column(db.String(50), nullable=False)
    start_odometer = db.Column(db.Numeric(10, 1), nullable=True)
    end_odometer = db.Column(db.Numeric(10, 1), nullable=True)
    miles = db.Column(db.Numeric(10, 2), nullable=True)
    purpose = db.Column(db.Text, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    tracking_session_id = db.Column(db.Integer, nullable=True)
    recorded_unit = db.Column(db.String(10), nullable=False, default="km")
    user_id = db.Column(db.Integer, nullable=True)
    photo_path = db.Column(db.String(255), nullable=True)

    def __repr__(self):
        return f"<Trip {self.id} {self.date} {self.vehicle} {self.miles}mi>"

class TrackingSession(db.Model):
    __tablename__ = "tracking_sessions"

    id = db.Column(db.Integer, primary_key=True)
    vehicle = db.Column(db.String(50), nullable=False)
    note = db.Column(db.Text, nullable=True)
    trip_type = db.Column(db.String(20), nullable=False, default="business")
    start_time = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    end_time = db.Column(db.DateTime, nullable=True)
    total_meters = db.Column(db.Numeric(12, 3), default=Decimal("0"), nullable=False)
    status = db.Column(db.String(20), default="active", nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    points = db.relationship("TrackingPoint", backref="session", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<TrackingSession {self.id} {self.vehicle} {self.status}>"

class TrackingPoint(db.Model):
    __tablename__ = "tracking_points"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("tracking_sessions.id"), nullable=False)
    latitude = db.Column(db.Numeric(10, 7), nullable=False)
    longitude = db.Column(db.Numeric(10, 7), nullable=False)
    accuracy = db.Column(db.Numeric(10, 2), nullable=True)
    recorded_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<TrackingPoint {self.session_id} {self.latitude},{self.longitude}>"

class TripForm(FlaskForm):
    trip_type = SelectField(
        "Trip Type",
        choices=[("personal", "Personal"), ("business", "Business"), ("medical", "Medical"), ("charity", "Charity")],
        default="personal",
    )
    vehicle = StringField("Vehicle", validators=[DataRequired()])
    start_odometer = DecimalField("Start Odometer", places=1, validators=[Optional(), NumberRange(min=0)], render_kw={"inputmode": "decimal"})
    end_odometer = DecimalField("End Odometer", places=1, validators=[Optional(), NumberRange(min=0)], render_kw={"inputmode": "decimal"})
    miles = DecimalField("Distance", places=2, validators=[Optional(), NumberRange(min=0)], render_kw={"inputmode": "decimal"})
    date = DateField("Date", default=date.today, validators=[DataRequired()])
    purpose = TextAreaField("Purpose", validators=[Optional()])
    notes = TextAreaField("Notes", validators=[Optional()])
    photo = FileField("Photo", validators=[Optional()])
    submit = SubmitField("Save Trip")

class TripSearchForm(FlaskForm):
    from_date = DateField("From", validators=[Optional()])
    to_date = DateField("To", validators=[Optional()])
    vehicle = StringField("Vehicle", validators=[Optional()])
    search = StringField("Search", validators=[Optional()])
    submit = SubmitField("Search")

class DeleteForm(FlaskForm):
    id = HiddenField("ID", validators=[DataRequired()])
    submit = SubmitField("Delete")

class SettingsForm(FlaskForm):
    unit = SelectField("Measurement Unit", choices=[("mi", "Miles"), ("km", "Kilometers")])
    submit = SubmitField("Save Settings")

class ChangePasswordForm(FlaskForm):
    current_password = PasswordField("Current Password", validators=[DataRequired(), Length(min=6, max=128)])
    new_password = PasswordField("New Password", validators=[DataRequired(), Length(min=6, max=128)])
    confirm_password = PasswordField("Confirm New Password", validators=[DataRequired(), EqualTo("new_password")])
    submit = SubmitField("Change Password")

class ProfileForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired(), Length(min=3, max=30)])
    email = StringField("Email", validators=[DataRequired(), Email()])
    submit = SubmitField("Update Profile")

class AdminLoginForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired()])
    password = StringField("Password", validators=[DataRequired()])
    submit = SubmitField("Login")

class AdminSettingsForm(FlaskForm):
    smtp_host = StringField("SMTP Host", validators=[Optional()])
    smtp_port = StringField("SMTP Port", validators=[Optional()])
    smtp_user = StringField("SMTP User", validators=[Optional()])
    smtp_password = PasswordField("SMTP Password", validators=[Optional()])
    smtp_from = StringField("From Email", validators=[Optional(), Email()])
    enable_email = BooleanField("Enable Email Notifications")
    submit = SubmitField("Save Admin Settings")

class ForgotForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])
    submit = SubmitField("Send Reset Link")

class ResetPasswordForm(FlaskForm):
    password = PasswordField("New Password", validators=[DataRequired(), Length(min=6, max=128)])
    confirm_password = PasswordField("Confirm New Password", validators=[DataRequired(), EqualTo("password")])
    submit = SubmitField("Reset Password")

class AppSetting(db.Model):
    __tablename__ = "app_settings"
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.String(50), nullable=True)

class Vehicle(db.Model):
    __tablename__ = "vehicles"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    is_default = db.Column(db.Boolean, default=False, nullable=False)
    odometer = db.Column(db.Numeric(10, 1), nullable=True)

class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    reset_token = db.Column(db.String(120), nullable=True)
    reset_expires = db.Column(db.DateTime, nullable=True)

class LoginForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired()])
    password = PasswordField("Password", validators=[DataRequired()])
    submit = SubmitField("Login")

class RegisterForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired(), Length(min=3, max=30)])
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=6, max=128)])
    confirm_password = PasswordField("Confirm Password", validators=[DataRequired(), EqualTo("password")])
    submit = SubmitField("Register")

class UserForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired()])
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[Optional()])
    is_admin = BooleanField("Admin")
    submit = SubmitField("Save User")

def _get_setting(db, key, default=None):
    row = db.session.execute(select(AppSetting).where(AppSetting.key == key)).scalar_one_or_none()
    return row.value if row is not None else default

def _set_setting(db, key, value):
    row = db.session.execute(select(AppSetting).where(AppSetting.key == key)).scalar_one_or_none()
    if row is None:
        row = AppSetting(key=key, value=value)
        db.session.add(row)
    else:
        row.value = value
    db.session.commit()

def _ensure_admin_credentials(db):
    if not _get_setting(db, "admin_user"):
        _set_setting(db, "admin_user", "admin")
    if not _get_setting(db, "admin_pass"):
        _set_setting(db, "admin_pass", "admin123")

def _clear_attempts(key):
    login_attempts.pop(key, None)

def _check_lockout(identifier):
    data = login_attempts.get(identifier)
    if not data:
        return False
    if data["count"] >= 5 and datetime.utcnow() < data["locked_until"]:
        return True
    if datetime.utcnow() >= data["locked_until"]:
        login_attempts.pop(identifier, None)
        return False
    return False

def _record_failed_attempt(identifier):
    now = datetime.utcnow()
    data = login_attempts.get(identifier)
    if not data or now >= data.get("locked_until", now):
        data = {"count": 0, "locked_until": now}
    data["count"] += 1
    if data["count"] >= 5:
        data["locked_until"] = now + timedelta(minutes=10)
    login_attempts[identifier] = data

def send_test_email(to_email):
    host = _get_setting(db, "smtp_host", "")
    port = _get_setting(db, "smtp_port", "")
    user = _get_setting(db, "smtp_user", "")
    password = _get_setting(db, "smtp_password", "")
    sender = _get_setting(db, "smtp_from", "")
    if not host or not port or not sender:
        return False, "SMTP settings are incomplete."
    msg = EmailMessage()
    msg["Subject"] = "SMTP Test"
    msg["From"] = sender
    msg["To"] = to_email
    msg.set_content("This is a test message from Mileage Tracker.")
    try:
        server = smtplib.SMTP(host, int(port), timeout=20)
        server.ehlo()
        try:
            server.starttls()
            server.ehlo()
        except smtplib.SMTPException as tls_err:
            return False, f"STARTTLS failed: {tls_err}"
        if user and password:
            try:
                server.login(user, password)
            except smtplib.SMTPAuthenticationError as auth_err:
                server.quit()
                return False, f"Login failed: {auth_err}"
        server.send_message(msg)
        server.quit()
        return True, "Test email sent."
    except Exception as e:
        return False, str(e)

def _send_password_reset_email(user, reset_url):
    sender = _get_setting(db, "smtp_from", "")
    host = _get_setting(db, "smtp_host", "")
    port = _get_setting(db, "smtp_port", "")
    smtp_user = _get_setting(db, "smtp_user", "")
    smtp_password = _get_setting(db, "smtp_password", "")
    missing = [k for k, v in {"sender": sender, "host": host, "port": port}.items() if not v]
    if missing:
        return False, f"SMTP settings missing: {', '.join(missing)}"
    msg = EmailMessage()
    msg["Subject"] = "Reset your Mileage Tracker password"
    msg["From"] = sender
    msg["To"] = user.email
    msg.set_content(f"Click the link to reset your password: {reset_url}\nThis link expires in 60 minutes.")
    try:
        server = smtplib.SMTP(host, int(port), timeout=20)
        server.ehlo()
        try:
            server.starttls()
            server.ehlo()
        except smtplib.SMTPException as tls_err:
            server.quit()
            return False, f"STARTTLS failed: {tls_err}"
        if smtp_user and smtp_password:
            try:
                server.login(smtp_user, smtp_password)
            except smtplib.SMTPAuthenticationError as auth_err:
                server.quit()
                return False, f"Login failed: {auth_err}"
        server.send_message(msg)
        server.quit()
        return True, "Password reset email sent."
    except Exception as e:
        return False, str(e)

def _send_registration_email(user, base_url):
    sender = _get_setting(db, "smtp_from", "")
    host = _get_setting(db, "smtp_host", "")
    port = _get_setting(db, "smtp_port", "")
    smtp_user = _get_setting(db, "smtp_user", "")
    smtp_password = _get_setting(db, "smtp_password", "")
    missing = [k for k, v in {"sender": sender, "host": host, "port": port}.items() if not v]
    if missing:
        return False, f"SMTP settings missing: {', '.join(missing)}"
    msg = EmailMessage()
    msg["Subject"] = "Welcome to Mileage Tracker"
    msg["From"] = sender
    msg["To"] = user.email
    msg.set_content(f"Welcome {user.username}!\n\nYour account was created.\nLogin here: {base_url}/login\n")
    try:
        server = smtplib.SMTP(host, int(port), timeout=20)
        server.ehlo()
        try:
            server.starttls()
            server.ehlo()
        except smtplib.SMTPException as tls_err:
            server.quit()
            return False, f"STARTTLS failed: {tls_err}"
        if smtp_user and smtp_password:
            try:
                server.login(smtp_user, smtp_password)
            except smtplib.SMTPAuthenticationError as auth_err:
                server.quit()
                return False, f"Login failed: {auth_err}"
        server.send_message(msg)
        server.quit()
        return True, "Registration email sent."
    except Exception as e:
        return False, str(e)

def _migrate_users(db):
    try:
        cols = [row[1] for row in db.session.execute(db.text("PRAGMA table_info(users)")).fetchall()]
        if not cols:
            db.session.execute(db.text("CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, username VARCHAR(80) UNIQUE NOT NULL, email VARCHAR(120) UNIQUE NOT NULL, password_hash VARCHAR(255) NOT NULL, is_admin BOOLEAN DEFAULT 0 NOT NULL, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)"))
            db.session.commit()
        if "reset_token" not in cols:
            db.session.execute(db.text("ALTER TABLE users ADD COLUMN reset_token VARCHAR(120)"))
            db.session.commit()
        if "reset_expires" not in cols:
            db.session.execute(db.text("ALTER TABLE users ADD COLUMN reset_expires DATETIME"))
            db.session.commit()
    except Exception:
        db.session.rollback()
        raise

def _migrate_tracking_trip_type(db):
    try:
        cols = [row[1] for row in db.session.execute(db.text("PRAGMA table_info(tracking_sessions)")).fetchall()]
        if "trip_type" not in cols:
            db.session.execute(db.text("ALTER TABLE tracking_sessions ADD COLUMN trip_type VARCHAR(20) NOT NULL DEFAULT 'personal'"))
            db.session.commit()
    except Exception:
        db.session.rollback()
        raise

def _migrate_trip_tracking_session(db):
    try:
        cols = [row[1] for row in db.session.execute(db.text("PRAGMA table_info(trips)")).fetchall()]
        if "tracking_session_id" not in cols:
            db.session.execute(db.text("ALTER TABLE trips ADD COLUMN tracking_session_id INTEGER"))
            db.session.commit()
    except Exception:
        db.session.rollback()
        raise

def _migrate_trip_recorded_unit(db):
    try:
        cols = [row[1] for row in db.session.execute(db.text("PRAGMA table_info(trips)")).fetchall()]
        if "recorded_unit" not in cols:
            db.session.execute(db.text("ALTER TABLE trips ADD COLUMN recorded_unit VARCHAR(10) NOT NULL DEFAULT 'km'"))
            db.session.commit()
    except Exception:
        db.session.rollback()
        raise

def _migrate_trip_user_id(db):
    try:
        cols = [row[1] for row in db.session.execute(db.text("PRAGMA table_info(trips)")).fetchall()]
        if "user_id" not in cols:
            db.session.execute(db.text("ALTER TABLE trips ADD COLUMN user_id INTEGER"))
            db.session.commit()
        if "photo_path" not in cols:
            db.session.execute(db.text("ALTER TABLE trips ADD COLUMN photo_path VARCHAR(255)"))
            db.session.commit()
    except Exception:
        db.session.rollback()
        raise

def _migrate_app_settings(db):
    try:
        cols = [row[1] for row in db.session.execute(db.text("PRAGMA table_info(app_settings)")).fetchall()]
        if not cols:
            db.session.execute(db.text("CREATE TABLE app_settings (id INTEGER PRIMARY KEY AUTOINCREMENT, key VARCHAR(50) UNIQUE NOT NULL, value VARCHAR(50))"))
            db.session.commit()
    except Exception:
        db.session.rollback()
        raise

def _migrate_vehicles(db):
    try:
        cols = [row[1] for row in db.session.execute(db.text("PRAGMA table_info(vehicles)")).fetchall()]
        if not cols:
            db.session.execute(db.text("CREATE TABLE vehicles (id INTEGER PRIMARY KEY AUTOINCREMENT, name VARCHAR(50) UNIQUE NOT NULL, is_default BOOLEAN DEFAULT 0 NOT NULL, odometer NUMERIC(10,1))"))
            db.session.commit()
        elif "odometer" not in cols:
            db.session.execute(db.text("ALTER TABLE vehicles ADD COLUMN odometer NUMERIC(10,1)"))
            db.session.commit()
    except Exception:
        db.session.rollback()
        raise

def _format_distance(value, unit="km"):
    try:
        miles = float(value or 0)
    except Exception:
        return "0.00"
    if unit == "km":
        return f"{miles * 1.60934:.2f}"
    return f"{miles:.2f}"

def _format_distance_raw(value):
    try:
        return f"{float(value or 0):.2f}"
    except Exception:
        return "0.00"

def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("MILEAGE_SECRET_KEY", "dev-mileage-tracker-2026")
    instance_path = os.environ.get("MILEAGE_INSTANCE_PATH", os.path.join(os.path.dirname(__file__), "..", "instance"))
    os.makedirs(instance_path, exist_ok=True)
    db_path = os.path.join(instance_path, "mileage.db")
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + db_path
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["UPLOAD_FOLDER"] = os.path.join(instance_path, "uploads")
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    db.init_app(app)
    migrate = Migrate(app, db)

    with app.app_context():
        db.create_all()
        _migrate_tracking_trip_type(db)
        _migrate_trip_tracking_session(db)
        _migrate_trip_recorded_unit(db)
        _migrate_trip_user_id(db)
        _migrate_app_settings(db)
        _migrate_vehicles(db)
        _migrate_users(db)
        _ensure_admin_credentials(db)
        app.config["UNIT"] = _get_setting(db, "unit", "km")

    @app.context_processor
    def inject_unit():
        return {"current_unit": app.config.get("UNIT", "km"), "format_distance": _format_distance}

    @app.errorhandler(404)
    def not_found_error(error):
        logger.warning("404 on %s", request.path)
        return render_template("404.html"), 404

    @app.errorhandler(500)
    def internal_error(error):
        logger.exception("500 error: %s", error)
        return render_template("500.html"), 500

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if session.get("user_id"):
            return redirect(url_for("track_page"))
        form = LoginForm()
        if form.validate_on_submit():
            identifier = form.username.data.strip()
            if _check_lockout(identifier):
                flash("Too many failed attempts. Please try again later.", "danger")
                logger.warning("Lockout login attempt: %s", identifier)
                return render_template("login.html", form=form)
            user = db.session.execute(select(User).where(User.username == identifier)).scalar_one_or_none()
            if user and check_password_hash(user.password_hash, form.password.data):
                _clear_attempts(identifier)
                session["user_id"] = user.id
                session["username"] = user.username
                logger.info("User logged in: %s", user.username)
                flash("Welcome back.", "success")
                return redirect(url_for("track_page"))
            _record_failed_attempt(identifier)
            logger.warning("Failed login attempt for user: %s", identifier)
            flash("Invalid username or password.", "danger")
        return render_template("login.html", form=form)

    @app.route("/forgot-password", methods=["GET", "POST"])
    def forgot_password():
        form = ForgotForm()
        if form.validate_on_submit():
            user = db.session.execute(select(User).where(User.email == form.email.data.strip())).scalar_one_or_none()
            if user:
                token = secrets.token_urlsafe(32)
                user.reset_token = token
                user.reset_expires = datetime.utcnow() + timedelta(hours=1)
                db.session.commit()
                base_url = "https://track.sultantech.ca"
                reset_url = f"{base_url}/reset-password/{token}"
                sent, msg = _send_password_reset_email(user, reset_url)
                logger.info("Password reset email sent=%s msg=%s for %s", sent, msg, user.email)
                if sent:
                    flash("If an account exists, a reset link was sent.", "success")
                else:
                    flash(f"Email delivery failed: {msg}", "warning")
            else:
                flash("If an account exists, a reset link was sent.", "success")
            return redirect(url_for("login"))
        return render_template("forgot_password.html", form=form)

    @app.route("/reset-password/<token>", methods=["GET", "POST"])
    def reset_password(token):
        user = db.session.execute(select(User).where(User.reset_token == token)).scalar_one_or_none()
        if not user or user.reset_expires is None or user.reset_expires < datetime.utcnow():
            flash("Invalid or expired reset link.", "danger")
            return redirect(url_for("login"))
        form = ResetPasswordForm()
        if form.validate_on_submit():
            user.password_hash = generate_password_hash(form.password.data)
            user.reset_token = None
            user.reset_expires = None
            db.session.commit()
            logger.info("Password reset completed for user: %s", user.username)
            flash("Password reset successful. Please log in.", "success")
            return redirect(url_for("login"))
        return render_template("reset_password.html", form=form)

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if session.get("user_id"):
            return redirect(url_for("track_page"))
        identifier = request.remote_addr or "anon"
        if _check_lockout(identifier):
            flash("Too many registration attempts. Please try again later.", "danger")
            logger.warning("Lockout register attempt: %s", identifier)
            return render_template("register.html", form=RegisterForm())
        form = RegisterForm()
        if form.validate_on_submit():
            existing = db.session.execute(select(User).where((User.username == form.username.data) | (User.email == form.email.data))).scalar_one_or_none()
            if existing:
                flash("Username or email already exists.", "warning")
                _record_failed_attempt(identifier)
            else:
                user = User(
                    username=form.username.data,
                    email=form.email.data,
                    password_hash=generate_password_hash(form.password.data),
                    is_admin=False,
                )
                db.session.add(user)
                db.session.commit()
                logger.info("User registered: %s", user.username)
                if _get_setting(db, "enable_email", ""):
                    sent, msg = _send_registration_email(user, "https://track.sultantech.ca")
                    logger.info("Registration email sent=%s msg=%s for %s", sent, msg, user.email)
                flash("Registration successful. Please log in.", "success")
                return redirect(url_for("login"))
        return render_template("register.html", form=form)

    @app.route("/logout")
    def logout():
        user = session.get("username")
        session.clear()
        flash("You have been logged out.", "info")
        logger.info("User logged out: %s", user)
        return redirect(url_for("login"))

    @app.route("/")
    def index():
        return redirect(url_for("track_page"))

    @app.route("/trips", methods=["GET", "POST"])
    def trips():
        form = TripForm()
        delete_form = DeleteForm()
        if form.validate_on_submit():
            start = form.start_odometer.data
            end = form.end_odometer.data
            miles = form.miles.data
            if miles is None or miles == 0:
                if start is not None and end is not None and end >= start:
                    miles = float(end) - float(start)
                elif miles is None:
                    miles = Decimal("0")
            else:
                miles = Decimal(miles)
                if app.config.get("UNIT") == "km":
                    miles = Decimal(miles) / Decimal("1.60934")
            trip = Trip(
                date=form.date.data,
                trip_type=form.trip_type.data,
                vehicle=form.vehicle.data.strip(),
                start_odometer=start,
                end_odometer=end,
                miles=miles,
                purpose=form.purpose.data.strip() if form.purpose.data else None,
                notes=form.notes.data.strip() if form.notes.data else None,
                recorded_unit=app.config.get("UNIT", "km"),
                user_id=session.get("user_id"),
            )
            uploaded = request.files.get("photo")
            if uploaded and uploaded.filename:
                filename = f"trip_{int(datetime.utcnow().timestamp())}_{secure_filename(uploaded.filename)}"
                uploaded.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
                trip.photo_path = filename
            db.session.add(trip)
            db.session.commit()
            logger.info("Trip created id=%s by %s", trip.id, session.get("username"))
            return redirect(url_for("trips"))

        page = request.args.get("page", 1, type=int)
        search = request.args.get("search", "", type=str).strip()
        vehicle_filter = request.args.get("vehicle", "", type=str).strip()
        type_filter = request.args.get("type", "", type=str).strip()
        from_date = request.args.get("from_date", "", type=str).strip()
        to_date = request.args.get("to_date", "", type=str).strip()

        query = Trip.query
        user_id = session.get("user_id")
        if user_id:
            query = query.filter(Trip.user_id == user_id)
        else:
            query = query.filter(Trip.id == None)
        if search:
            like = f"%{search}%"
            query = query.filter(
                db.or_(Trip.vehicle.ilike(like), Trip.purpose.ilike(like), Trip.notes.ilike(like))
            )
        if vehicle_filter:
            query = query.filter(Trip.vehicle.ilike(f"%{vehicle_filter}%"))
        if type_filter:
            query = query.filter(Trip.trip_type == type_filter)
        if from_date:
            try:
                query = query.filter(Trip.date >= datetime.strptime(from_date, "%Y-%m-%d").date())
            except Exception:
                pass
        if to_date:
            try:
                query = query.filter(Trip.date <= datetime.strptime(to_date, "%Y-%m-%d").date())
            except Exception:
                pass

        query = query.order_by(Trip.date.desc(), Trip.id.desc())
        pagination = query.paginate(page=page, per_page=20, error_out=False)
        trips = pagination.items
        total_miles = sum(float(t.miles or 0) for t in query.all())

        vehicles = sorted({t.vehicle for t in query.all() if t.vehicle})
        return render_template(
            "index.html",
            form=form,
            delete_form=delete_form,
            trips=trips,
            pagination=pagination,
            total_miles=total_miles,
            search=search,
            vehicle_filter=vehicle_filter,
            type_filter=type_filter,
            from_date=from_date,
            to_date=to_date,
            vehicles=vehicles,
        )

    @app.route("/trip/<int:trip_id>")
    def trip_detail(trip_id):
        trip = db.get_or_404(Trip, trip_id)
        user_id = session.get("user_id")
        if trip.user_id is not None and trip.user_id != user_id:
            return redirect(url_for("trips"))
        delete_form = DeleteForm()
        return render_template("trip_detail.html", trip=trip, delete_form=delete_form)

    @app.route("/trips/<int:trip_id>/delete", methods=["POST"])
    def delete_trip(trip_id):
        trip = db.get_or_404(Trip, trip_id)
        user_id = session.get("user_id")
        if trip.user_id is not None and trip.user_id != user_id:
            return redirect(url_for("trips"))
        db.session.delete(trip)
        db.session.commit()
        logger.info("Trip deleted id=%s by %s", trip_id, session.get("username"))
        return redirect(url_for("trips"))

    @app.route("/export")
    def export_csv():
        query = Trip.query.order_by(Trip.date.asc())
        user_id = session.get("user_id")
        if user_id:
            query = query.filter(Trip.user_id == user_id)
        trips = query.all()
        buf = __import__("io").StringIO()
        writer = __import__("csv").writer(buf)
        writer.writerow(["ID", "Date", "Type", "Vehicle", "Start Odometer", "End Odometer", "Miles", "Purpose", "Notes"])
        for t in trips:
            writer.writerow([
                t.id,
                t.date.isoformat() if t.date else "",
                t.trip_type,
                t.vehicle,
                float(t.start_odometer) if t.start_odometer is not None else "",
                float(t.end_odometer) if t.end_odometer is not None else "",
                float(t.miles) if t.miles is not None else "",
                t.purpose or "",
                t.notes or "",
            ])
        return __import__("flask").Response(
            buf.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=mileage_export.csv"},
        )

    @app.route("/api/trips")
    def api_trips():
        query = Trip.query.order_by(Trip.date.desc())
        user_id = session.get("user_id")
        if user_id:
            query = query.filter(Trip.user_id == user_id)
        trips = query.limit(200).all()
        return __import__("json").jsonify([
            {
                "id": t.id,
                "date": t.date.isoformat() if t.date else None,
                "trip_type": t.trip_type,
                "vehicle": t.vehicle,
                "start_odometer": float(t.start_odometer) if t.start_odometer is not None else None,
                "end_odometer": float(t.end_odometer) if t.end_odometer is not None else None,
                "miles": float(t.miles) if t.miles is not None else None,
                "purpose": t.purpose,
                "notes": t.notes,
                "recorded_unit": t.recorded_unit,
            }
            for t in trips
        ])

    @app.route("/track")
    def track_page():
        if not session.get("user_id"):
            return redirect(url_for("login"))
        session_id = request.args.get("session_id", type=int)
        current_session = None
        if session_id:
            current_session = db.get_or_404(TrackingSession, session_id)
        active_session = TrackingSession.query.filter_by(status="active").first()
        vehicles = Vehicle.query.order_by(Vehicle.name).all()
        default_vehicle = db.session.execute(select(Vehicle).where(Vehicle.is_default == True)).scalar_one_or_none()
        return render_template(
            "track.html",
            active_session=active_session,
            current_session=current_session,
            vehicles=vehicles,
            default_vehicle=default_vehicle,
        )

    @app.route("/api/track/start", methods=["POST"])
    def track_start():
        if not session.get("user_id"):
            return jsonify({"error": "login required"}), 401
        data = request.get_json(silent=True) or {}
        vehicle = (data.get("vehicle") or "").strip() or "Car"
        note = (data.get("note") or "").strip() or None
        trip_type = (data.get("trip_type") or "").strip().lower()
        if trip_type not in ("personal", "business"):
            trip_type = "personal"
        lat = data.get("lat")
        lon = data.get("lon")
        accuracy = data.get("accuracy")

        existing = TrackingSession.query.filter_by(status="active").first()
        if existing:
            return jsonify({"error": "active session already exists", "session_id": existing.id}), 409

        tracking = TrackingSession(vehicle=vehicle, note=note, trip_type=trip_type)
        if lat is not None and lon is not None:
            try:
                point = TrackingPoint(
                    session_id=tracking.id,
                    latitude=Decimal(str(float(lat))),
                    longitude=Decimal(str(float(lon))),
                    accuracy=Decimal(str(float(accuracy))) if accuracy is not None else None,
                )
                tracking.points.append(point)
            except Exception:
                pass
        db.session.add(tracking)
        db.session.commit()
        logger.info("Tracking started session=%s vehicle=%s user=%s", tracking.id, vehicle, session.get("username"))
        return jsonify({"session_id": tracking.id, "status": tracking.status}), 201

    @app.route("/api/track/point", methods=["POST"])
    def track_add_point():
        data = request.get_json(silent=True) or {}
        session_id = data.get("session_id")
        lat = data.get("lat")
        lon = data.get("lon")
        accuracy = data.get("accuracy")

        if session_id is None or lat is None or lon is None:
            return jsonify({"error": "session_id, lat, lon are required"}), 400
        if not session.get("user_id"):
            return jsonify({"error": "login required"}), 401

        tracking = db.get_or_404(TrackingSession, session_id)
        if tracking.status != "active":
            return jsonify({"error": "session is not active"}), 409

        try:
            point = TrackingPoint(
                session_id=tracking.id,
                latitude=Decimal(str(float(lat))),
                longitude=Decimal(str(float(lon))),
                accuracy=Decimal(str(float(accuracy))) if accuracy is not None else None,
            )
            db.session.add(point)
            if tracking.points:
                last = tracking.points[-1]
                meters = haversine(float(last.latitude), float(last.longitude), float(lat), float(lon))
                if meters < 0:
                    meters = 0.0
                elif math.isnan(meters) or math.isinf(meters):
                    meters = 0.0
                else:
                    meters = round(float(meters), 3)
                tracking.total_meters = Decimal(str(float(tracking.total_meters or 0) + meters))
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            return jsonify({"error": str(e)}), 400

        return jsonify({
            "session_id": tracking.id,
            "total_meters": float(tracking.total_meters or 0),
            "points": len(tracking.points),
        })

    @app.route("/api/track/stop", methods=["POST"])
    def track_stop():
        data = request.get_json(silent=True) or {}
        session_id = data.get("session_id")
        if session_id is None:
            return jsonify({"error": "session_id is required"}), 400
        if not session.get("user_id"):
            return jsonify({"error": "login required"}), 401

        tracking = db.get_or_404(TrackingSession, session_id)
        if tracking.status != "active":
            return jsonify({"error": "session is not active"}), 409

        tracking.end_time = datetime.utcnow()
        tracking.status = "completed"
        db.session.commit()

        total_miles = float(tracking.total_meters or 0) / 1609.344
        trip = Trip(
            date=(tracking.start_time or datetime.utcnow()).date(),
            trip_type=tracking.trip_type or "personal",
            vehicle=tracking.vehicle,
            miles=Decimal(str(round(total_miles, 2))),
            purpose=tracking.note,
            notes=f"Live tracking session {tracking.id}",
            tracking_session_id=tracking.id,
            recorded_unit=app.config.get("UNIT", "km"),
            user_id=session.get("user_id"),
        )
        db.session.add(trip)
        db.session.commit()
        logger.info("Tracking stopped session=%s trip=%s user=%s", tracking.id, trip.id, session.get("username"))
        return jsonify({"session_id": tracking.id, "miles": round(total_miles, 2), "trip_id": trip.id})

    @app.route("/api/track/status")
    def track_status():
        session = TrackingSession.query.filter_by(status="active").first()
        if not session:
            return jsonify({"active": False})
        return jsonify({
            "active": True,
            "session_id": session.id,
            "vehicle": session.vehicle,
            "start_time": session.start_time.isoformat() + "Z",
            "total_meters": float(session.total_meters or 0),
            "points": len(session.points),
        })

    @app.route("/api/track/session/<int:session_id>/points")
    def track_session_points(session_id):
        session = db.get_or_404(TrackingSession, session_id)
        pts = [
            {"lat": float(p.latitude), "lon": float(p.longitude)}
            for p in session.points
        ]
        return jsonify({"session_id": session.id, "points": pts})

    @app.route("/about")
    def about():
        return render_template("about.html")

    @app.route("/healthz")
    def healthz():
        return jsonify({"status": "ok"})

    @app.route("/settings", methods=["GET", "POST"])
    def settings():
        app.config["UNIT"] = _get_setting(db, "unit", "km")
        unit = app.config["UNIT"]
        if request.method == "POST":
            unit = request.form.get("unit", "km")
            if unit not in ("mi", "km"):
                unit = "km"
            _set_setting(db, "unit", unit)
            app.config["UNIT"] = unit

            vehicle_name = request.form.get("vehicle_name", "").strip()
            if vehicle_name:
                existing = db.session.execute(select(Vehicle).where(Vehicle.name == vehicle_name)).scalar_one_or_none()
                if existing is None:
                    if request.form.get("set_default"):
                        db.session.query(Vehicle).update({"is_default": False})
                    db.session.add(Vehicle(name=vehicle_name, is_default=bool(request.form.get("set_default"))))
                    db.session.commit()

            vehicle_id = request.form.get("delete_vehicle")
            if vehicle_id:
                v = db.get_or_404(Vehicle, vehicle_id)
                db.session.delete(v)
                db.session.commit()

            default_id = request.form.get("default_vehicle")
            if default_id:
                db.session.query(Vehicle).update({"is_default": False})
                v = db.get_or_404(Vehicle, default_id)
                v.is_default = True
                db.session.commit()

            odometer_vehicle = request.form.get("odometer_vehicle")
            odometer_value = request.form.get("odometer_value")
            if odometer_vehicle is not None and odometer_value is not None:
                try:
                    v = db.get_or_404(Vehicle, int(odometer_vehicle))
                    v.odometer = Decimal(odometer_value) if odometer_value.strip() != "" else None
                    db.session.commit()
                except Exception:
                    db.session.rollback()

            return redirect(url_for("settings"))
        form = SettingsForm(unit=unit)
        vehicles = Vehicle.query.order_by(Vehicle.name).all()
        password_form = ChangePasswordForm()
        user = None
        if session.get("user_id"):
            user = db.get_or_404(User, session.get("user_id"))
        return render_template("settings.html", form=form, password_form=password_form, vehicles=vehicles, user=user)

    @app.route("/settings/password", methods=["POST"])
    def settings_change_password():
        if not session.get("user_id"):
            return redirect(url_for("login"))
        form = ChangePasswordForm()
        user = db.get_or_404(User, session.get("user_id"))
        if form.validate_on_submit():
            if not check_password_hash(user.password_hash, form.current_password.data):
                flash("Current password is incorrect.", "danger")
                logger.warning("Bad current password for user: %s", user.username)
            else:
                user.password_hash = generate_password_hash(form.new_password.data)
                db.session.commit()
                flash("Password updated.", "success")
                logger.info("Password changed for user: %s", user.username)
        else:
            flash("Please check the form.", "warning")
        return redirect(url_for("settings"))

    @app.route("/settings/profile", methods=["GET", "POST"])
    def settings_profile():
        if not session.get("user_id"):
            return redirect(url_for("login"))
        user = db.get_or_404(User, session.get("user_id"))
        form = ProfileForm(obj=user)
        if form.validate_on_submit():
            existing = db.session.execute(select(User).where((User.username == form.username.data) | (User.email == form.email.data))).scalar_one_or_none()
            if existing and existing.id != user.id:
                flash("Username or email already in use.", "warning")
            else:
                user.username = form.username.data.strip()
                user.email = form.email.data.strip()
                db.session.commit()
                session["username"] = user.username
                flash("Profile updated.", "success")
                logger.info("Profile updated for user: %s", user.username)
                return redirect(url_for("settings"))
        return render_template("settings_profile.html", form=form)

    @app.route("/reports")
    def reports():
        month = request.args.get("month", "", type=str).strip()
        trip_type = request.args.get("trip_type", "", type=str).strip()
        query = Trip.query
        user_id = session.get("user_id")
        if user_id:
            query = query.filter(Trip.user_id == user_id)
        else:
            query = query.filter(Trip.id == None)
        if month:
            try:
                start = datetime.strptime(month, "%Y-%m").date()
                if start.month == 12:
                    end = start.replace(year=start.year + 1, month=1)
                else:
                    end = start.replace(month=start.month + 1)
                query = query.filter(Trip.date >= start, Trip.date < end)
            except Exception:
                pass
        if trip_type:
            query = query.filter(Trip.trip_type == trip_type)
        trips = query.order_by(Trip.date.desc()).all()
        total_miles = sum(float(t.miles or 0) for t in trips)
        types = sorted({t.trip_type for t in query.all()})
        return render_template(
            "reports.html",
            trips=trips,
            total_miles=total_miles,
            month=month,
            trip_type=trip_type,
            types=types,
        )

    def _admin_required():
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login"))
        return None

    @app.route("/admin/login", methods=["GET", "POST"])
    def admin_login():
        if session.get("admin_logged_in"):
            return redirect(url_for("admin_dashboard"))
        identifier = "admin_" + (_get_setting(db, "admin_user", "admin") or "admin")
        if _check_lockout(identifier):
            flash("Too many admin login attempts. Please try again later.", "danger")
            logger.warning("Lockout admin login attempt: %s", identifier)
            return render_template("admin_login.html", form=AdminLoginForm())
        form = AdminLoginForm()
        if form.validate_on_submit():
            user = _get_setting(db, "admin_user", "")
            pw = _get_setting(db, "admin_pass", "")
            if user and pw and form.username.data == user and form.password.data == pw:
                _clear_attempts(identifier)
                session["admin_logged_in"] = True
                logger.info("Admin login success")
                return redirect(url_for("admin_dashboard"))
            _record_failed_attempt(identifier)
            logger.warning("Admin login failed")
            flash("Invalid credentials.", "danger")
        return render_template("admin_login.html", form=form)

    @app.route("/admin/logout")
    def admin_logout():
        session.pop("admin_logged_in", None)
        return redirect(url_for("admin_login"))

    @app.route("/admin")
    def admin_dashboard():
        guard = _admin_required()
        if guard is not None:
            return guard
        form = AdminSettingsForm(
            smtp_host=_get_setting(db, "smtp_host", ""),
            smtp_port=_get_setting(db, "smtp_port", ""),
            smtp_user=_get_setting(db, "smtp_user", ""),
            smtp_password=_get_setting(db, "smtp_password", ""),
            smtp_from=_get_setting(db, "smtp_from", ""),
            enable_email=bool(_get_setting(db, "enable_email", "")),
        )
        user_form = UserForm()
        users = User.query.order_by(User.created_at.desc()).all()
        test_email = ""
        return render_template("admin_dashboard.html", form=form, user_form=user_form, users=users, test_email=test_email)

    @app.route("/admin/settings", methods=["POST"])
    def admin_save_settings():
        guard = _admin_required()
        if guard is not None:
            return guard
        form = AdminSettingsForm()
        if form.validate_on_submit():
            _set_setting(db, "smtp_host", form.smtp_host.data.strip() if form.smtp_host.data else "")
            _set_setting(db, "smtp_port", form.smtp_port.data.strip() if form.smtp_port.data else "")
            _set_setting(db, "smtp_user", form.smtp_user.data.strip() if form.smtp_user.data else "")
            smtp_password = form.smtp_password.data.strip() if form.smtp_password.data else ""
            if smtp_password:
                _set_setting(db, "smtp_password", smtp_password)
            _set_setting(db, "smtp_from", form.smtp_from.data.strip() if form.smtp_from.data else "")
            _set_setting(db, "enable_email", "true" if form.enable_email.data else "")
            flash("Settings saved.", "success")
            logger.info("Admin settings updated")
        else:
            flash("Please check the form.", "warning")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/test-smtp", methods=["POST"])
    def admin_test_smtp():
        guard = _admin_required()
        if guard is not None:
            return guard
        to_email = request.form.get("test_email", "").strip()
        if not to_email:
            flash("Please provide a test email address.", "warning")
            return redirect(url_for("admin_dashboard"))
        ok, msg = send_test_email(to_email)
        if ok:
            flash(f"Test email sent to {to_email}.", "success")
            logger.info("SMTP test email sent to %s", to_email)
        else:
            flash(f"Failed to send test email: {msg}", "danger")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/users", methods=["POST"])
    def admin_create_user():
        guard = _admin_required()
        if guard is not None:
            return guard
        form = UserForm()
        if form.validate_on_submit():
            existing = db.session.execute(select(User).where((User.username == form.username.data) | (User.email == form.email.data))).scalar_one_or_none()
            if existing:
                flash("Username or email already exists.", "warning")
            else:
                password = form.password.data or "changeme"
                user = User(
                    username=form.username.data,
                    email=form.email.data,
                    password_hash=generate_password_hash(password),
                    is_admin=bool(form.is_admin.data),
                )
                db.session.add(user)
                db.session.commit()
                flash("User created.", "success")
                logger.info("Admin created user: %s", user.username)
        else:
            flash("Please check the form.", "warning")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/users/toggle/<int:user_id>", methods=["POST"])
    def admin_toggle_user(user_id):
        guard = _admin_required()
        if guard is not None:
            return guard
        user = db.get_or_404(User, user_id)
        user.is_admin = not user.is_admin
        db.session.commit()
        flash("User updated.", "success")
        return redirect(url_for("admin_dashboard", tab="users"))

    @app.route("/admin/users/delete/<int:user_id>", methods=["POST"])
    def admin_delete_user(user_id):
        guard = _admin_required()
        if guard is not None:
            return guard
        user = db.get_or_404(User, user_id)
        if session.get("user_id") == user.id:
            flash("You cannot delete your own account while logged in.", "warning")
            return redirect(url_for("admin_dashboard"))
        db.session.delete(user)
        db.session.commit()
        flash("User deleted.", "success")
        return redirect(url_for("admin_dashboard", tab="users"))

    @app.route("/admin/trips")
    def admin_trips():
        guard = _admin_required()
        if guard is not None:
            return guard
        user_id = request.args.get("user_id", type=int)
        query = Trip.query
        if user_id:
            query = query.filter(Trip.user_id == user_id)
        trips = query.order_by(Trip.date.desc()).all()
        users = User.query.order_by(User.username).all()
        return render_template("admin_trips.html", trips=trips, users=users, selected_user_id=user_id)

    @app.route("/admin/trips/<int:trip_id>/edit", methods=["GET", "POST"])
    def admin_edit_trip(trip_id):
        guard = _admin_required()
        if guard is not None:
            return guard
        trip = db.get_or_404(Trip, trip_id)
        form = TripForm(obj=trip)
        if form.validate_on_submit():
            trip.trip_type = form.trip_type.data
            trip.vehicle = form.vehicle.data.strip()
            trip.start_odometer = form.start_odometer.data
            trip.end_odometer = form.end_odometer.data
            trip.miles = form.miles.data
            trip.date = form.date.data
            trip.purpose = form.purpose.data.strip() if form.purpose.data else None
            trip.notes = form.notes.data.strip() if form.notes.data else None
            db.session.commit()
            flash("Trip updated.", "success")
            logger.info("Admin updated trip %s", trip.id)
            return redirect(url_for("admin_trips"))
        return render_template("admin_edit_trip.html", form=form, trip=trip)

    @app.route("/admin/trips/<int:trip_id>/delete", methods=["POST"])
    def admin_delete_trip(trip_id):
        guard = _admin_required()
        if guard is not None:
            return guard
        trip = db.get_or_404(Trip, trip_id)
        db.session.delete(trip)
        db.session.commit()
        flash("Trip deleted.", "success")
        logger.info("Admin deleted trip %s", trip_id)
        return redirect(url_for("admin_trips"))

    return app
