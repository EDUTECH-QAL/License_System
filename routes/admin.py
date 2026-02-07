from flask import Blueprint, render_template, redirect, url_for, request, flash, send_from_directory, current_app
from flask_login import login_user, logout_user, login_required, current_user
from models import AdminUser, School, License, Device, SystemLog, BackupVault, SchoolUser, PendingCommand
from extensions import db
from routes.api import log_system_event
from datetime import datetime, timedelta
import uuid
import json
from sqlalchemy import func

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

@admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('admin.dashboard'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = AdminUser.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            if not user.is_active:
                flash('Your account is suspended.')
                return render_template('admin/login.html')
            login_user(user)
            return redirect(url_for('admin.dashboard'))
        else:
            flash('Invalid username or password')
            
    return render_template('admin/login.html')

@admin_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('admin.login'))

@admin_bp.route('/')
@login_required
def dashboard():
    # Date calculations
    now = datetime.utcnow()
    thirty_days_later = now + timedelta(days=30)
    start_of_month = datetime(now.year, now.month, 1)
    
    # Stats
    stats = {
        'schools_count': School.query.count(),
        'active_licenses': License.query.filter_by(status='active').count(),
        'active_devices': Device.query.filter_by(status='active').count(),
        'blocked_devices': Device.query.filter_by(status='blocked').count(),
        'expiring_soon': License.query.filter(
            License.expiry_date <= thirty_days_later,
            License.expiry_date > now,
            License.status == 'active'
        ).count(),
        'activations_this_month': SystemLog.query.filter(
            SystemLog.action == 'activate',
            SystemLog.result == 'success',
            SystemLog.timestamp >= start_of_month
        ).count(),
        'recent_logs': SystemLog.query.order_by(SystemLog.timestamp.desc()).limit(10).all()
    }
    
    return render_template('admin/dashboard.html', stats=stats)

# --- Schools Management ---
@admin_bp.route('/schools')
@login_required
def schools():
    page = request.args.get('page', 1, type=int)
    query = request.args.get('q')
    status = request.args.get('status')
    
    # Start with base query
    schools_query = School.query
    
    # Join with License to filter by status if needed
    if status:
        schools_query = schools_query.join(License).filter(License.status == status)
        
    if query:
        schools_query = schools_query.filter(School.name.contains(query) | School.education_admin.contains(query))
        
    # Order by creation or name
    schools_query = schools_query.order_by(School.created_at.desc())
    
    # Paginate
    schools_pagination = schools_query.paginate(page=page, per_page=10, error_out=False)
    
    return render_template('admin/schools.html', schools=schools_pagination, current_status=status)

@admin_bp.route('/schools/add', methods=['GET', 'POST'])
@login_required
def add_school():
    if request.method == 'POST':
        name = request.form.get('name')
        education_admin = request.form.get('education_admin')
        contact_email = request.form.get('contact_email')
        phone = request.form.get('phone')
        
        # License Info
        license_key = request.form.get('license_key') or str(uuid.uuid4())
        max_devices = int(request.form.get('max_devices', 1))
        expiry_date_str = request.form.get('expiry_date')
        expiry_date = datetime.strptime(expiry_date_str, '%Y-%m-%d')
        
        school = School(name=name, education_admin=education_admin, contact_email=contact_email, phone=phone)
        db.session.add(school)
        db.session.flush() # Get ID
        
        license_obj = License(
            school_id=school.id,
            license_key=license_key,
            max_devices=max_devices,
            expiry_date=expiry_date
        )
        db.session.add(license_obj)
        db.session.commit()
        
        flash('School and License created successfully')
        return redirect(url_for('admin.schools'))
        
    return render_template('admin/school_form.html')

@admin_bp.route('/schools/<int:id>', methods=['GET', 'POST'])
@login_required
def school_detail(id):
    school = School.query.get_or_404(id)
    if request.method == 'POST':
        # Update School logic here if needed
        pass
    return render_template('admin/school_detail.html', school=school)

@admin_bp.route('/licenses/<int:id>/update', methods=['POST'])
@login_required
def update_license(id):
    license_obj = License.query.get_or_404(id)
    license_obj.status = request.form.get('status')
    license_obj.max_devices = int(request.form.get('max_devices'))
    expiry_date_str = request.form.get('expiry_date')
    if expiry_date_str:
        license_obj.expiry_date = datetime.strptime(expiry_date_str, '%Y-%m-%d')
    
    db.session.commit()
    flash('License updated')
    return redirect(url_for('admin.school_detail', id=license_obj.school_id))

@admin_bp.route('/devices/<int:id>/toggle', methods=['POST'])
@login_required
def toggle_device(id):
    device = Device.query.get_or_404(id)
    device.status = 'blocked' if device.status == 'active' else 'active'
    db.session.commit()
    flash(f'Device {device.device_name} is now {device.status}')
    return redirect(url_for('admin.school_detail', id=device.license.school_id))

@admin_bp.route('/devices/<int:id>/delete', methods=['POST'])
@login_required
def delete_device(id):
    device = Device.query.get_or_404(id)
    school_id = device.license.school_id
    db.session.delete(device)
    db.session.commit()
    flash('Device deleted/reset successfully')
    return redirect(url_for('admin.school_detail', id=school_id))

@admin_bp.route('/licenses/<int:id>/renew', methods=['POST'])
@login_required
def renew_license(id):
    license_obj = License.query.get_or_404(id)
    # Add 1 year to current expiry or today if expired
    now = datetime.utcnow()
    if license_obj.expiry_date < now:
        license_obj.expiry_date = now + timedelta(days=365)
    else:
        license_obj.expiry_date = license_obj.expiry_date + timedelta(days=365)
    
    license_obj.status = 'active'
    db.session.commit()
    flash('License renewed for 1 year')
    return redirect(url_for('admin.school_detail', id=license_obj.school_id))

@admin_bp.route('/devices/<int:id>/request_backup', methods=['POST'])
@login_required
def request_device_backup(id):
    device = Device.query.get_or_404(id)
    device.pending_command = 'request_backup'
    db.session.commit()
    flash(f'Backup requested from device {device.device_name}. It will be uploaded automatically when online.')
    return redirect(url_for('admin.school_detail', id=device.license.school_id))

@admin_bp.route('/devices/<int:id>/factory_reset', methods=['POST'])
@login_required
def request_factory_reset(id):
    device = Device.query.get_or_404(id)
    device.pending_command = 'factory_reset'
    db.session.commit()
    log_system_event(device.license_id, device.id, 'command', 'sent', 'Factory Reset Requested', request.remote_addr)
    flash(f'Factory Reset command sent to {device.device_name}. All data will be wiped when device connects.')
    return redirect(url_for('admin.school_detail', id=device.license.school_id))


# --- Backups ---
@admin_bp.route('/backups')
@login_required
def backups():
    backups_list = BackupVault.query.all()
    return render_template('admin/backups.html', backups=backups_list)

@admin_bp.route('/backups/download/<int:id>')
@login_required
def download_backup(id):
    backup = BackupVault.query.get_or_404(id)
    return send_from_directory(current_app.config['BACKUP_FOLDER'], backup.file_path, as_attachment=True)

# --- Logs ---
@admin_bp.route('/logs')
@login_required
def logs():
    page = request.args.get('page', 1, type=int)
    logs_pagination = SystemLog.query.order_by(SystemLog.timestamp.desc()).paginate(page=page, per_page=50)
    return render_template('admin/logs.html', logs=logs_pagination)

# --- User Management ---
@admin_bp.route('/users')
@login_required
def users():
    users_list = AdminUser.query.all()
    return render_template('admin/users.html', users=users_list)

@admin_bp.route('/users/add', methods=['GET', 'POST'])
@login_required
def add_user():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if AdminUser.query.filter_by(username=username).first():
            flash('Username already exists')
            return redirect(url_for('admin.add_user'))
            
        user = AdminUser(username=username)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        flash('User created successfully')
        return redirect(url_for('admin.users'))
        
    return render_template('admin/user_form.html')

@admin_bp.route('/users/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_user(id):
    user = AdminUser.query.get_or_404(id)
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username != user.username and AdminUser.query.filter_by(username=username).first():
            flash('Username already exists')
            return redirect(url_for('admin.edit_user', id=id))
            
        user.username = username
        if password:
            user.set_password(password)
            
        db.session.commit()
        flash('User updated successfully')
        return redirect(url_for('admin.users'))
        
    return render_template('admin/user_form.html', user=user)

@admin_bp.route('/users/<int:id>/delete', methods=['POST'])
@login_required
def delete_user(id):
    if id == current_user.id:
        flash('You cannot delete yourself')
        return redirect(url_for('admin.users'))
        
    user = AdminUser.query.get_or_404(id)
    db.session.delete(user)
    db.session.commit()
    flash('User deleted successfully')
    return redirect(url_for('admin.users'))

@admin_bp.route('/users/<int:id>/toggle', methods=['POST'])
@login_required
def toggle_user(id):
    if id == current_user.id:
        flash('You cannot suspend yourself')
        return redirect(url_for('admin.users'))
        
    user = AdminUser.query.get_or_404(id)
    user.is_active_user = not user.is_active_user
    db.session.commit()
    flash(f'User {"activated" if user.is_active_user else "suspended"} successfully')
    return redirect(url_for('admin.users'))

# --- School Users Management ---
@admin_bp.route('/schools/<int:id>/users/add', methods=['POST'])
@login_required
def add_school_user(id):
    school = School.query.get_or_404(id)
    username = request.form.get('username')
    password = request.form.get('password')
    role = request.form.get('role', 'teacher')
    
    if SchoolUser.query.filter_by(school_id=id, username=username).first():
        flash('Username already exists for this school', 'error')
        return redirect(url_for('admin.school_detail', id=id))
        
    user = SchoolUser(school_id=id, username=username, role=role)
    user.set_password(password)
    db.session.add(user)
    
    # Create Command to sync to client
    cmd = PendingCommand(
        school_id=id,
        command_type='create_user',
        payload=json.dumps({
            'username': username,
            'password': password,
            'role': role
        })
    )
    db.session.add(cmd)
    
    db.session.commit()
    
    flash('User added successfully')
    return redirect(url_for('admin.school_detail', id=id))

@admin_bp.route('/school_users/<int:user_id>/delete', methods=['POST'])
@login_required
def delete_school_user(user_id):
    user = SchoolUser.query.get_or_404(user_id)
    school_id = user.school_id
    username = user.username
    db.session.delete(user)
    
    # Create Command to sync to client
    cmd = PendingCommand(
        school_id=school_id,
        command_type='delete_user',
        payload=json.dumps({
            'username': username
        })
    )
    db.session.add(cmd)
    
    db.session.commit()
    flash('User deleted successfully')
    return redirect(url_for('admin.school_detail', id=school_id))

@admin_bp.route('/school_users/<int:user_id>/reset_password', methods=['POST'])
@login_required
def reset_school_user_password(user_id):
    user = SchoolUser.query.get_or_404(user_id)
    new_password = request.form.get('new_password')
    
    if not new_password:
        import random
        import string
        new_password = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
        
    user.set_password(new_password)
    
    # Create Command to sync to client
    cmd = PendingCommand(
        school_id=user.school_id,
        command_type='update_user',
        payload=json.dumps({
            'username': user.username,
            'password': new_password
        })
    )
    db.session.add(cmd)
    
    db.session.commit()
    flash(f'Password reset successfully. New password: {new_password}')
    return redirect(url_for('admin.school_detail', id=user.school_id))

@admin_bp.route('/school_users/<int:user_id>/toggle', methods=['POST'])
@login_required
def toggle_school_user(user_id):
    user = SchoolUser.query.get_or_404(user_id)
    user.is_active = not user.is_active
    
    # Create Command to sync to client
    cmd = PendingCommand(
        school_id=user.school_id,
        command_type='update_user',
        payload=json.dumps({
            'username': user.username,
            'is_active': user.is_active
        })
    )
    db.session.add(cmd)
    
    db.session.commit()
    flash(f"User {user.username} {'activated' if user.is_active else 'deactivated'}")
    return redirect(url_for('admin.school_detail', id=user.school_id))
