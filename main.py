# This file is used as an entry point for gunicorn
# Import the app from app.py to make it available to gunicorn
from app import app

# Make sure database tables are created
with app.app_context():
    from app import db
    db.create_all()