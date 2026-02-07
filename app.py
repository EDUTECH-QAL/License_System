from flask import Flask, redirect, url_for
from config import Config
from extensions import db, login_manager
from routes.api import api
from routes.admin import admin_bp
from routes.emergency import emergency_bp
from models import AdminUser
import os

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Initialize Extensions
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'admin.login'

    # Register Blueprints
    app.register_blueprint(api)
    app.register_blueprint(admin_bp)
    app.register_blueprint(emergency_bp)

    @app.route('/')
    def index():
        return redirect(url_for('admin.login'))
        
    # Create DB and Admin User if not exists
    with app.app_context():
        # Ensure backup folder exists
        if not os.path.exists(app.config['BACKUP_FOLDER']):
            os.makedirs(app.config['BACKUP_FOLDER'])
            
        db.create_all()
        
        # Create default admin if none
        if not AdminUser.query.filter_by(username='admin').first():
            admin = AdminUser(username='admin')
            admin.set_password('admin123') # Default password
            db.session.add(admin)
            db.session.commit()
            print("Default Admin User Created: admin / admin123")

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, port=5000)
