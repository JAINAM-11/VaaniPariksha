"""
VaaniPariksha - Database Connection & SQLAlchemy Setup
"""
import os
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base

db = SQLAlchemy()
Base = declarative_base()


def init_db(app):
    """Initialize database with Flask app."""
    db.init_app(app)
    with app.app_context():
        db.create_all()
    return db


def get_engine(db_url: str = None):
    """Create a raw SQLAlchemy engine (for migrations/scripts)."""
    url = db_url or os.getenv("DATABASE_URL", "")
    if not url:
        from backend.config.settings import Config
        url = Config.get_db_url()
    return create_engine(url, pool_pre_ping=True)


def test_connection(app=None):
    """Test DB connection. Returns True if successful."""
    try:
        if app:
            with app.app_context():
                db.session.execute(text("SELECT 1"))
                db.session.commit()
        else:
            engine = get_engine()
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        print(f"[DB] Connection failed: {e}")
        return False
