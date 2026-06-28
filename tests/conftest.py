import importlib

import pytest


@pytest.fixture()
def app(tmp_path, monkeypatch):
    db_path = tmp_path / "test-ssp.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "Admin@12345")

    app_module = importlib.import_module("app")
    test_app = app_module.create_app()
    test_app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)

    yield test_app

    with test_app.app_context():
        app_module.db.session.remove()
        app_module.db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def app_module(app):
    return importlib.import_module("app")
