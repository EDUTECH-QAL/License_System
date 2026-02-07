from extensions import db, login_manager
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

@login_manager.user_loader
def load_user(user_id):
    return AdminUser.query.get(int(user_id))

class AdminUser(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    is_active_user = db.Column(db.Boolean, default=True) # Rename to avoid conflict with UserMixin.is_active

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    @property
    def is_active(self):
        return self.is_active_user

class School(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    education_admin = db.Column(db.String(120), nullable=False) # Educational Administration
    contact_email = db.Column(db.String(120))
    phone = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    licenses = db.relationship('License', backref='school', lazy=True)
    backups = db.relationship('BackupVault', backref='school', lazy=True)
    users = db.relationship('SchoolUser', backref='school', lazy=True)

class SchoolUser(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('school.id'), nullable=False)
    username = db.Column(db.String(64), nullable=False)
    email = db.Column(db.String(120))
    phone = db.Column(db.String(20))
    password_hash = db.Column(db.String(128))
    role = db.Column(db.String(20), default='teacher') # admin, principal, teacher, staff
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class License(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('school.id'), nullable=False)
    license_key = db.Column(db.String(64), unique=True, nullable=False)
    status = db.Column(db.String(20), default='active') # active, expired, suspended
    max_devices = db.Column(db.Integer, default=1)
    expiry_date = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    devices = db.relationship('Device', backref='license', lazy=True)
    
    def is_valid(self):
        return self.status == 'active' and self.expiry_date > datetime.utcnow()

class Device(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    license_id = db.Column(db.Integer, db.ForeignKey('license.id'), nullable=False)
    device_identifier = db.Column(db.String(128), nullable=False) # Unique Hardware ID
    device_name = db.Column(db.String(64)) # Hostname
    status = db.Column(db.String(20), default='active') # active, blocked
    last_check = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    pending_command = db.Column(db.String(50), nullable=True) # e.g., 'request_backup'

class SystemLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    license_id = db.Column(db.Integer, db.ForeignKey('license.id'), nullable=True)
    device_id = db.Column(db.Integer, db.ForeignKey('device.id'), nullable=True)
    action = db.Column(db.String(50), nullable=False) # activate, check, backup_upload
    result = db.Column(db.String(20), nullable=False) # success, failed
    details = db.Column(db.Text)
    ip_address = db.Column(db.String(50))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class BackupVault(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('school.id'), nullable=False)
    file_path = db.Column(db.String(255), nullable=False)
    file_size = db.Column(db.Integer) # in bytes
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    uploaded_by_device_id = db.Column(db.Integer, db.ForeignKey('device.id'), nullable=True)

class EmergencyLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.String(128), nullable=False) # Store Device ID string directly as it might be for a non-registered device
    school_name = db.Column(db.String(120))
    generated_by = db.Column(db.String(50)) # client, server
    reason = db.Column(db.String(200))
    code_hash = db.Column(db.String(64)) # To prevent replay if we want
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_used = db.Column(db.Boolean, default=False)
    used_at = db.Column(db.DateTime)
    synced_at = db.Column(db.DateTime)
    client_ip = db.Column(db.String(50))

class PendingCommand(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('school.id'), nullable=False)
    command_type = db.Column(db.String(50), nullable=False) # update_user, delete_user
    payload = db.Column(db.Text, nullable=False) # JSON string
    is_delivered = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    delivered_at = db.Column(db.DateTime)

    school_rel = db.relationship('School', backref='pending_commands', lazy=True)


