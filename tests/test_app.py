from datetime import date


def test_health_check_returns_ok(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_home_requires_login(client):
    response = client.get("/")

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_login_page_renders(client):
    response = client.get("/login")

    assert response.status_code == 200
    assert b"Username Or Email" in response.data
    assert b"Login" in response.data


def test_default_admin_can_login(client):
    response = client.post(
        "/login",
        data={"username_or_email": "admin", "password": "Admin@12345"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin")


def test_signup_creates_user_and_redirects_to_login(client, app, app_module):
    response = client.post(
        "/signup",
        data={
            "username": "madhu",
            "email": "madhu@example.com",
            "password": "Password@123",
            "confirm_password": "Password@123",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]

    with app.app_context():
        user = app_module.User.query.filter_by(username="madhu").one()
        assert user.email == "madhu@example.com"
        assert user.role == "user"


def test_signup_validation_rejects_invalid_data(app, app_module):
    with app.app_context():
        errors = app_module.validate_signup("newuser", "invalid-email", "short", "different")

    assert "Valid email is required." in errors
    assert "Password must be at least 8 characters." in errors
    assert "Passwords do not match." in errors


def test_calculate_cost_counts_inclusive_days(app_module):
    cost = app_module.calculate_cost("DEVE", date(2026, 6, 1), date(2026, 6, 3))

    assert cost == 60000


def test_parse_date_handles_blank_and_valid_values(app_module):
    assert app_module.parse_date("") is None
    assert app_module.parse_date("2026-06-28") == date(2026, 6, 28)
