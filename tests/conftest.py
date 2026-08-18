import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from app import create_app, db

@pytest.fixture
def app():
    app = create_app()
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["WTF_CSRF_ENABLED"] = False
    with app.app_context():
        db.drop_all()
        db.create_all()
        from app import _ensure_admin_credentials
        _ensure_admin_credentials(db)
        yield app

@pytest.fixture
def client(app):
    return app.test_client()
