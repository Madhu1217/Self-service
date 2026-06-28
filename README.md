# Self Service Portal

Production-oriented Flask application for seven self-service request flows:

- Engage Us
- CAB Request
- Adhoc Batch Execution
- Environment Booking
- Mainframe Deployment
- Raise A Request
- Report Problem

## Run Locally

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Open `http://localhost:5000`.

Default first-run admin:

- Username: `admin`
- Password: `Admin@12345`

Set `ADMIN_USERNAME`, `ADMIN_EMAIL`, and `ADMIN_PASSWORD` before production.

## Run Tests

```powershell
pip install -r requirements.txt -r requirements-dev.txt
pytest -q
```

## Environment Cost Rules

- `DEVE`, `DEVD`, `DEVF`: INR 20,000 per 24 hours
- `EBS01`, `EBS02`, `EBS03`, `DTESF`, `EBS06`: INR 15,000 per 24 hours

Environment Booking calculates and displays cost before submit.

## Docker

```powershell
docker build -t self-service-portal:latest .
docker run -p 5000:5000 -e SECRET_KEY=change-me self-service-portal:latest
```

## Kubernetes

Update these values before deployment:

- `K8s/ingress.yaml`: replace `ssp.example.com`
- `K8s/deployment.yaml`: replace the default image if not deploying through Jenkins
- `K8s/secret.yaml`: replace `SECRET_KEY`

Apply:

```powershell
kubectl apply -f K8s/
```

The included SQLite PVC is suitable for a simple single-replica deployment. For multi-replica production, switch `DATABASE_URL` to PostgreSQL or another managed database.

## Email Export

The admin page can email the request export and admin password resets when SMTP is configured:

- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USER`
- `SMTP_PASSWORD`
- `SMTP_FROM`

Passwords are stored as one-way hashes. The admin page displays the stored hash for audit purposes, not the original password.

## Session Timeout

Logged-in users are automatically logged out after 10 minutes with no activity. This is enforced on the server and also triggered by the browser while a page is left open.

## Jenkins Credentials Expected

- `docker-registry-url`: Docker registry hostname
- `docker-registry-credentials`: Docker registry login credentials
- `kubeconfig`: Kubernetes config file credential
