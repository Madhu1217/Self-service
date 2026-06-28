import os
import secrets
import smtplib
import string
from email.message import EmailMessage
from functools import wraps
from io import BytesIO
from datetime import datetime, timedelta, timezone

from flask import Flask, Response, abort, flash, redirect, render_template, request, session, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash
from openpyxl import Workbook


db = SQLAlchemy()
SESSION_TIMEOUT = timedelta(minutes=10)

ENVIRONMENTS = ["DEVE", "DEVD", "DEVF", "EBS01", "EBS02", "EBS03", "DTESF", "EBS06"]
PRODUCTION_ENVIRONMENTS = ["EBS01", "EBS02", "EBS03", "DTESF", "EBS06"]
TEST_ENVIRONMENTS = ["DEVE", "DEVD", "DEVF"]

ENVIRONMENT_DAILY_COST = {
    "DEVE": 20000,
    "DEVD": 20000,
    "DEVF": 20000,
    "EBS01": 15000,
    "EBS02": 15000,
    "EBS03": 15000,
    "DTESF": 15000,
    "EBS06": 15000,
}

SERVICE_DEFINITIONS = {
    "engage-us": {
        "title": "Engage Us",
        "description": "Share the environment support window and the work summary.",
        "fields": [
            {"name": "requester", "label": "Requester", "type": "text", "required": True},
            {"name": "environment", "label": "Environment Needed", "type": "environment", "required": True},
            {"name": "start_date", "label": "Start Date", "type": "date", "required": True},
            {"name": "end_date", "label": "End Date", "type": "date", "required": True},
            {"name": "short_summary", "label": "Short Summary", "type": "text", "required": True},
            {"name": "description", "label": "Description", "type": "textarea", "required": True},
        ],
    },
    "cab-request": {
        "title": "CAB Request",
        "description": "Submit CAB details, impact, SME contact, and outage information.",
        "fields": [
            {"name": "requester", "label": "Requester", "type": "text", "required": True},
            {"name": "environment", "label": "Environment Needed", "type": "environment", "required": True},
            {"name": "start_date", "label": "Start Date", "type": "date", "required": True},
            {"name": "end_date", "label": "End Date", "type": "date", "required": True},
            {"name": "outage", "label": "Any Outage", "type": "select", "options": ["No", "Yes"], "required": True},
            {"name": "sme_details", "label": "SME Details", "type": "text", "required": True},
            {"name": "environment_impact", "label": "Impact To Any Environment", "type": "textarea", "required": True},
            {"name": "description", "label": "Description", "type": "textarea", "required": True},
        ],
    },
    "adhoc-batch-execution": {
        "title": "Adhoc Batch Execution",
        "description": "Request an application batch run in a specific environment.",
        "fields": [
            {"name": "application", "label": "Application To Run", "type": "text", "required": True},
            {"name": "environment", "label": "Environment", "type": "environment", "required": True},
        ],
    },
    "environment-booking": {
        "title": "Environment Booking",
        "description": "Reserve an environment and preview the calculated booking cost.",
        "show_cost": True,
        "fields": [
            {"name": "requester", "label": "Requester", "type": "text", "required": True},
            {"name": "environment", "label": "Environment Needed", "type": "environment", "required": True},
            {"name": "start_date", "label": "Start Date", "type": "date", "required": True},
            {"name": "end_date", "label": "End Date", "type": "date", "required": True},
            {"name": "short_summary", "label": "Short Summary", "type": "text", "required": True},
            {"name": "description", "label": "Description", "type": "textarea", "required": True},
        ],
    },
    "mainframe-deployment": {
        "title": "Mainframe Deployment",
        "description": "Select the application, target type, and matching environment.",
        "fields": [
            {"name": "application", "label": "Application To Deploy", "type": "text", "required": True},
            {
                "name": "environment_type",
                "label": "Environment Type",
                "type": "select",
                "options": ["Production", "Test"],
                "required": True,
            },
            {"name": "environment", "label": "Environment", "type": "mainframe_environment", "required": True},
        ],
    },
    "raise-a-request": {
        "title": "Raise A Request",
        "description": "Use this when you are not sure which service to select.",
        "fields": [
            {"name": "requester", "label": "Requester", "type": "text", "required": True},
            {"name": "start_date", "label": "Start Date", "type": "date", "required": True},
            {"name": "end_date", "label": "End Date", "type": "date", "required": True},
            {"name": "description", "label": "Description", "type": "textarea", "required": True},
        ],
    },
    "report-problem": {
        "title": "Report Problem",
        "description": "Tell the support team what is broken or blocking your work.",
        "fields": [
            {"name": "requester", "label": "Requester", "type": "text", "required": True},
            {"name": "problem", "label": "Problem", "type": "textarea", "required": True},
        ],
    },
}


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False, unique=True, index=True)
    email = db.Column(db.String(255), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="user")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    requests = db.relationship("ServiceRequest", backref="user", lazy=True)

    @property
    def is_admin(self):
        return self.role == "admin"


class ServiceRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    service_key = db.Column(db.String(80), nullable=False, index=True)
    service_name = db.Column(db.String(120), nullable=False)
    requester = db.Column(db.String(120))
    environment = db.Column(db.String(40))
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    application = db.Column(db.String(120))
    environment_type = db.Column(db.String(40))
    short_summary = db.Column(db.String(255))
    description = db.Column(db.Text)
    outage = db.Column(db.String(20))
    sme_details = db.Column(db.String(255))
    environment_impact = db.Column(db.Text)
    problem = db.Column(db.Text)
    calculated_cost = db.Column(db.Integer)
    status = db.Column(db.String(40), nullable=False, default="Submitted")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-me-in-production")
    os.makedirs(app.instance_path, exist_ok=True)
    database_url = os.environ.get("DATABASE_URL", "sqlite:///ssp.db")
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)

    with app.app_context():
        db.create_all()
        ensure_sqlite_columns()
        ensure_admin_user()

    @app.context_processor
    def inject_current_user():
        return {"current_user": get_current_user()}

    @app.before_request
    def enforce_session_timeout():
        if request.endpoint in {"health", "login", "signup", "static"}:
            return None

        user_id = session.get("user_id")
        last_activity = session.get("last_activity")
        if not user_id:
            return None

        now = datetime.now(timezone.utc)
        if last_activity:
            last_activity_at = datetime.fromisoformat(last_activity)
            if now - last_activity_at > SESSION_TIMEOUT:
                session.clear()
                flash("You were logged out due to 10 minutes of inactivity.", "error")
                return redirect(url_for("login"))

        session["last_activity"] = now.isoformat()
        session.permanent = True
        return None

    @app.get("/")
    @login_required
    def index():
        current_user = get_current_user()
        query = ServiceRequest.query
        if not current_user.is_admin:
            query = query.filter_by(user_id=current_user.id)
        recent_requests = query.order_by(ServiceRequest.created_at.desc()).limit(5).all()
        return render_template(
            "index.html",
            services=SERVICE_DEFINITIONS,
            recent_requests=recent_requests,
        )

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if get_current_user():
            return redirect(url_for("index"))

        if request.method == "POST":
            username_or_email = request.form.get("username_or_email", "").strip()
            password = request.form.get("password", "")
            user = User.query.filter(
                (User.username == username_or_email) | (User.email == username_or_email)
            ).first()

            if user and check_password_hash(user.password_hash, password):
                session.clear()
                session["user_id"] = user.id
                session["last_activity"] = datetime.now(timezone.utc).isoformat()
                session.permanent = True
                flash("Login successful.", "success")
                return redirect(url_for("admin_dashboard" if user.is_admin else "index"))

            flash("Invalid username/email or password.", "error")

        return render_template("login.html")

    @app.route("/signup", methods=["GET", "POST"])
    def signup():
        if get_current_user():
            return redirect(url_for("index"))

        if request.method == "POST":
            username = request.form.get("username", "").strip()
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            confirm_password = request.form.get("confirm_password", "")

            errors = validate_signup(username, email, password, confirm_password)
            if errors:
                for error in errors:
                    flash(error, "error")
            else:
                user = User(
                    username=username,
                    email=email,
                    password_hash=generate_password_hash(password),
                    role="user",
                )
                db.session.add(user)
                db.session.commit()
                flash("Account created. Please login.", "success")
                return redirect(url_for("login"))

        return render_template("signup.html")

    @app.post("/logout")
    @login_required
    def logout():
        session.clear()
        flash("You have been logged out.", "success")
        return redirect(url_for("login"))

    @app.route("/settings", methods=["GET", "POST"])
    @login_required
    def settings():
        current_user = get_current_user()

        if request.method == "POST":
            action = request.form.get("action")
            if action == "profile":
                username = request.form.get("username", "").strip()
                email = request.form.get("email", "").strip().lower()
                errors = validate_profile_update(current_user, username, email)
                if errors:
                    for error in errors:
                        flash(error, "error")
                else:
                    current_user.username = username
                    current_user.email = email
                    db.session.commit()
                    flash("Profile updated successfully.", "success")
                    return redirect(url_for("settings"))

            if action == "password":
                current_password = request.form.get("current_password", "")
                new_password = request.form.get("new_password", "")
                confirm_password = request.form.get("confirm_password", "")
                errors = validate_password_change(current_user, current_password, new_password, confirm_password)
                if errors:
                    for error in errors:
                        flash(error, "error")
                else:
                    current_user.password_hash = generate_password_hash(new_password)
                    db.session.commit()
                    flash("Password changed successfully.", "success")
                    return redirect(url_for("settings"))

        return render_template("settings.html")

    @app.route("/service/<service_key>", methods=["GET", "POST"])
    @login_required
    def service_form(service_key):
        service = SERVICE_DEFINITIONS.get(service_key)
        if not service:
            flash("Requested service was not found.", "error")
            return redirect(url_for("index"))

        if request.method == "POST":
            errors = validate_form(service)
            if errors:
                for error in errors:
                    flash(error, "error")
            else:
                service_request = build_service_request(service_key, service)
                db.session.add(service_request)
                db.session.commit()
                flash(f"{service['title']} submitted successfully. Request ID: {service_request.id}", "success")
                return redirect(url_for("request_detail", request_id=service_request.id))

        return render_template(
            "service_form.html",
            service_key=service_key,
            service=service,
            environments=ENVIRONMENTS,
            production_environments=PRODUCTION_ENVIRONMENTS,
            test_environments=TEST_ENVIRONMENTS,
            environment_costs=ENVIRONMENT_DAILY_COST,
        )

    @app.get("/requests")
    @login_required
    def requests_list():
        current_user = get_current_user()
        query = ServiceRequest.query
        if not current_user.is_admin:
            query = query.filter_by(user_id=current_user.id)
        service_requests = query.order_by(ServiceRequest.created_at.desc()).all()
        return render_template("requests.html", service_requests=service_requests)

    @app.get("/requests/<int:request_id>")
    @login_required
    def request_detail(request_id):
        service_request = ServiceRequest.query.get_or_404(request_id)
        current_user = get_current_user()
        if not current_user.is_admin and service_request.user_id != current_user.id:
            abort(403)
        return render_template("request_detail.html", service_request=service_request)

    @app.get("/admin")
    @admin_required
    def admin_dashboard():
        service_requests = ServiceRequest.query.order_by(ServiceRequest.created_at.desc()).all()
        users = User.query.order_by(User.created_at.desc()).all()
        return render_template("admin.html", service_requests=service_requests, users=users)

    @app.get("/admin/export")
    @admin_required
    def admin_export():
        workbook_data = build_requests_workbook()
        return Response(
            workbook_data,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=self-service-portal-requests.xlsx"},
        )

    @app.post("/admin/email")
    @admin_required
    def admin_email():
        recipient = request.form.get("recipient", "").strip()
        try:
            send_requests_email(recipient)
            flash(f"Request data emailed to {recipient}.", "success")
        except RuntimeError as exc:
            flash(str(exc), "error")
        return redirect(url_for("admin_dashboard"))

    @app.post("/admin/users/<int:user_id>/reset-password")
    @admin_required
    def admin_reset_password(user_id):
        target_user = User.query.get_or_404(user_id)
        temporary_password = generate_temporary_password()

        try:
            send_password_reset_email(target_user, temporary_password)
        except RuntimeError as exc:
            flash(str(exc), "error")
            return redirect(url_for("admin_dashboard"))

        target_user.password_hash = generate_password_hash(temporary_password)
        db.session.commit()
        flash(f"Temporary password was emailed to {target_user.email}.", "success")
        return redirect(url_for("admin_dashboard"))

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post("/session/timeout")
    @login_required
    def session_timeout():
        session.clear()
        flash("You were logged out due to 10 minutes of inactivity.", "error")
        return redirect(url_for("login"))

    return app


def validate_form(service):
    errors = []
    form_data = request.form

    for field in service["fields"]:
        value = form_data.get(field["name"], "").strip()
        if field.get("required") and not value:
            errors.append(f"{field['label']} is required.")

    start_date = parse_date(form_data.get("start_date"))
    end_date = parse_date(form_data.get("end_date"))
    if start_date and end_date and end_date < start_date:
        errors.append("End Date must be on or after Start Date.")

    environment = form_data.get("environment")
    if environment and environment not in ENVIRONMENTS:
        errors.append("Selected environment is invalid.")

    environment_type = form_data.get("environment_type")
    if environment_type == "Production" and environment not in PRODUCTION_ENVIRONMENTS:
        errors.append("Production deployments must use a production environment.")
    if environment_type == "Test" and environment not in TEST_ENVIRONMENTS:
        errors.append("Test deployments must use a test environment.")

    return errors


def validate_signup(username, email, password, confirm_password):
    errors = []
    if not username:
        errors.append("Username is required.")
    if not email or "@" not in email:
        errors.append("Valid email is required.")
    if len(password) < 8:
        errors.append("Password must be at least 8 characters.")
    if password != confirm_password:
        errors.append("Passwords do not match.")
    if username and User.query.filter_by(username=username).first():
        errors.append("Username already exists.")
    if email and User.query.filter_by(email=email).first():
        errors.append("Email already exists.")
    return errors


def validate_profile_update(user, username, email):
    errors = []
    if not username:
        errors.append("Username is required.")
    if not email or "@" not in email:
        errors.append("Valid email is required.")

    username_owner = User.query.filter_by(username=username).first()
    if username_owner and username_owner.id != user.id:
        errors.append("Username already exists.")

    email_owner = User.query.filter_by(email=email).first()
    if email_owner and email_owner.id != user.id:
        errors.append("Email already exists.")

    return errors


def validate_password_change(user, current_password, new_password, confirm_password):
    errors = []
    if not check_password_hash(user.password_hash, current_password):
        errors.append("Current password is incorrect.")
    if len(new_password) < 8:
        errors.append("New password must be at least 8 characters.")
    if new_password != confirm_password:
        errors.append("New password and confirm password do not match.")
    return errors


def build_service_request(service_key, service):
    form_data = request.form
    environment = form_data.get("environment") or None
    start_date = parse_date(form_data.get("start_date"))
    end_date = parse_date(form_data.get("end_date"))
    calculated_cost = calculate_cost(environment, start_date, end_date) if service.get("show_cost") else None

    return ServiceRequest(
        user_id=session.get("user_id"),
        service_key=service_key,
        service_name=service["title"],
        requester=form_data.get("requester") or None,
        environment=environment,
        start_date=start_date,
        end_date=end_date,
        application=form_data.get("application") or None,
        environment_type=form_data.get("environment_type") or None,
        short_summary=form_data.get("short_summary") or None,
        description=form_data.get("description") or None,
        outage=form_data.get("outage") or None,
        sme_details=form_data.get("sme_details") or None,
        environment_impact=form_data.get("environment_impact") or None,
        problem=form_data.get("problem") or None,
        calculated_cost=calculated_cost,
    )


def get_current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return db.session.get(User, user_id)


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not get_current_user():
            flash("Please login to continue.", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped_view


def admin_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        current_user = get_current_user()
        if not current_user:
            flash("Please login to continue.", "error")
            return redirect(url_for("login"))
        if not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)

    return wrapped_view


def ensure_admin_user():
    username = os.environ.get("ADMIN_USERNAME", "admin")
    email = os.environ.get("ADMIN_EMAIL", "admin@example.com")
    password = os.environ.get("ADMIN_PASSWORD", "Admin@12345")

    existing_admin = User.query.filter_by(role="admin").first()
    if existing_admin:
        return

    existing_user = User.query.filter((User.username == username) | (User.email == email)).first()
    if existing_user:
        existing_user.role = "admin"
        db.session.commit()
        return

    try:
        db.session.add(
            User(
                username=username,
                email=email,
                password_hash=generate_password_hash(password),
                role="admin",
            )
        )
        db.session.commit()
    except IntegrityError:
        db.session.rollback()


def ensure_sqlite_columns():
    if not db.engine.url.drivername.startswith("sqlite"):
        return

    inspector = inspect(db.engine)
    if "service_request" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("service_request")}
    if "user_id" not in existing_columns:
        with db.engine.begin() as connection:
            connection.exec_driver_sql("ALTER TABLE service_request ADD COLUMN user_id INTEGER")


def build_requests_workbook():
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Requests"
    sheet.append(
        [
            "ID",
            "Service",
            "Requester",
            "User",
            "User Email",
            "Environment",
            "Start Date",
            "End Date",
            "Application",
            "Environment Type",
            "Summary",
            "Description",
            "Outage",
            "SME Details",
            "Environment Impact",
            "Problem",
            "Cost",
            "Status",
            "Created At",
        ]
    )

    for item in ServiceRequest.query.order_by(ServiceRequest.created_at.desc()).all():
        sheet.append(
            [
                item.id,
                item.service_name,
                item.requester or "",
                item.user.username if item.user else "",
                item.user.email if item.user else "",
                item.environment or "",
                item.start_date.isoformat() if item.start_date else "",
                item.end_date.isoformat() if item.end_date else "",
                item.application or "",
                item.environment_type or "",
                item.short_summary or "",
                item.description or "",
                item.outage or "",
                item.sme_details or "",
                item.environment_impact or "",
                item.problem or "",
                item.calculated_cost or "",
                item.status,
                item.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            ]
        )

    for column_cells in sheet.columns:
        max_length = max(len(str(cell.value or "")) for cell in column_cells)
        sheet.column_dimensions[column_cells[0].column_letter].width = min(max(max_length + 2, 12), 60)

    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    return output.getvalue()


def get_smtp_config():
    smtp_host = os.environ.get("SMTP_HOST")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER")
    smtp_password = os.environ.get("SMTP_PASSWORD")
    sender = os.environ.get("SMTP_FROM", smtp_user)

    if not smtp_host or not sender:
        raise RuntimeError("Email is not configured. Set SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, and SMTP_FROM.")

    return smtp_host, smtp_port, smtp_user, smtp_password, sender


def send_email_message(message):
    smtp_host, smtp_port, smtp_user, smtp_password, _sender = get_smtp_config()
    with smtplib.SMTP(smtp_host, smtp_port) as smtp:
        smtp.starttls()
        if smtp_user and smtp_password:
            smtp.login(smtp_user, smtp_password)
        smtp.send_message(message)


def send_requests_email(recipient):
    if not recipient or "@" not in recipient:
        raise RuntimeError("Enter a valid recipient email address.")

    _smtp_host, _smtp_port, _smtp_user, _smtp_password, sender = get_smtp_config()

    message = EmailMessage()
    message["Subject"] = "Self Service Portal Request Export"
    message["From"] = sender
    message["To"] = recipient
    message.set_content("Attached is the latest Self Service Portal request export.")
    message.add_attachment(
        build_requests_workbook(),
        maintype="application",
        subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="self-service-portal-requests.xlsx",
    )

    send_email_message(message)


def send_password_reset_email(user, temporary_password):
    _smtp_host, _smtp_port, _smtp_user, _smtp_password, sender = get_smtp_config()

    message = EmailMessage()
    message["Subject"] = "Self Service Portal Temporary Password"
    message["From"] = sender
    message["To"] = user.email
    message.set_content(
        f"Hello {user.username},\n\n"
        "Your Self Service Portal password was reset by an administrator.\n\n"
        f"Temporary password: {temporary_password}\n\n"
        "Please login and change this password from Settings immediately.\n"
    )

    send_email_message(message)


def generate_temporary_password(length=14):
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def parse_date(value):
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def calculate_cost(environment, start_date, end_date):
    if not environment or not start_date or not end_date:
        return None
    days = (end_date - start_date).days + 1
    return days * ENVIRONMENT_DAILY_COST[environment]


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
