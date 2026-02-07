from flask import Blueprint, request, jsonify, current_app
from werkzeug.utils import secure_filename
from models import School, License, Device, SystemLog, BackupVault, EmergencyLog, SchoolUser
from extensions import db
from datetime import datetime, timedelta
import os
import jwt
import hashlib
import json
from models import School, License, Device, SystemLog, BackupVault, EmergencyLog, SchoolUser, PendingCommand

api = Blueprint('api', __name__, url_prefix='/api')

@api.route('/report_emergency_usage', methods=['POST'])
def report_emergency_usage():
    data = request.json
    device_id = data.get('device_id')
    code_hash = data.get('code_hash') # Or the code itself to verify
    activated_at_str = data.get('activated_at')
    
    if not all([device_id, code_hash]):
        return jsonify({'status': 'error', 'message': 'Missing fields'}), 400
        
    # Find the log entry
    # Note: If generated offline, we might not find it by hash if logic differs, 
    # but currently we only support server-generated codes so hash must match.
    log = EmergencyLog.query.filter_by(code_hash=code_hash).first()
    
    if not log:
        # Fallback: Maybe search by device_id and recent time if hash mismatch?
        # For now, create a new entry if not found (unexpected but safe)
        log = EmergencyLog(
            device_id=device_id,
            school_name=data.get('school_name', 'Unknown'),
            generated_by='Offline/Unknown',
            reason='Synced from Client',
            code_hash=code_hash,
            created_at=datetime.utcnow() # Approximation
        )
        db.session.add(log)
        
    log.is_used = True
    log.synced_at = datetime.utcnow()
    log.client_ip = request.remote_addr
    
    if activated_at_str:
        try:
            log.used_at = datetime.fromisoformat(activated_at_str)
        except:
            log.used_at = datetime.utcnow()
    else:
        log.used_at = datetime.utcnow()
        
    db.session.commit()
    
    return jsonify({'status': 'success', 'message': 'Emergency usage logged'})

def log_system_event(license_id, device_id, action, result, details=None, ip=None):
    try:
        log = SystemLog(
            license_id=license_id,
            device_id=device_id,
            action=action,
            result=result,
            details=details,
            ip_address=ip
        )
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        print(f"Logging failed: {str(e)}")

def generate_token(license_obj, device_obj):
    payload = {
        'license_id': license_obj.id,
        'device_id': device_obj.id,
        'exp': datetime.utcnow() + timedelta(days=90) # Token valid for check period
    }
    return jwt.encode(payload, current_app.config['SECRET_KEY'], algorithm='HS256')

@api.route('/sync_users', methods=['POST'])
def sync_users():
    data = request.json
    token = data.get('token')
    users_data = data.get('users', [])
    
    if not token:
        return jsonify({'status': 'error', 'message': 'Missing token'}), 400
        
    try:
        payload = jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=['HS256'])
        license_id = payload.get('license_id')
    except jwt.ExpiredSignatureError:
        return jsonify({'status': 'error', 'message': 'Token expired'}), 401
    except jwt.InvalidTokenError:
        return jsonify({'status': 'error', 'message': 'Invalid token'}), 401
        
    license_obj = License.query.get(license_id)
    if not license_obj:
        return jsonify({'status': 'error', 'message': 'License not found'}), 404
        
    school_id = license_obj.school_id
    
    synced_count = 0
    for user_data in users_data:
        username = user_data.get('username')
        if not username:
            continue
            
        user = SchoolUser.query.filter_by(school_id=school_id, username=username).first()
        if not user:
            user = SchoolUser(school_id=school_id, username=username)
            db.session.add(user)
            
        user.email = user_data.get('email')
        user.phone = user_data.get('phone')
        user.role = user_data.get('role', 'teacher')
        user.is_active = user_data.get('is_active', True)
        
        synced_count += 1
        
    db.session.commit()
    
    return jsonify({'status': 'success', 'message': f'Synced {synced_count} users'})

@api.route('/activate', methods=['POST'])
def activate_license():
    data = request.json
    license_key = data.get('license_key')
    school_name = data.get('school_name')
    education_admin = data.get('education_admin')
    device_identifier = data.get('device_identifier')
    device_name = data.get('device_name')
    
    ip_address = request.remote_addr
    
    if not all([license_key, school_name, device_identifier]):
        return jsonify({'status': 'error', 'message': 'Missing required fields'}), 400
        
    # 1. Find License
    license_obj = License.query.filter_by(license_key=license_key).first()
    
    if not license_obj:
        log_system_event(None, None, 'activate', 'failed', f"Invalid Key: {license_key}", ip_address)
        return jsonify({'status': 'error', 'message': 'Invalid License Key'}), 404
        
    # 2. Validate School Info
    school = license_obj.school
    if school.name.strip().lower() != school_name.strip().lower():
        log_system_event(license_obj.id, None, 'activate', 'failed', f"School Mismatch: {school_name}", ip_address)
        return jsonify({'status': 'error', 'message': 'School Name mismatch'}), 403
        
    if education_admin and school.education_admin.strip().lower() != education_admin.strip().lower():
         # Optional: Log warning but maybe don't block if strictness not required. Assuming strict for now.
         log_system_event(license_obj.id, None, 'activate', 'failed', f"Admin Mismatch: {education_admin}", ip_address)
         return jsonify({'status': 'error', 'message': 'Education Admin mismatch'}), 403

    # 3. Check License Status and Expiry
    if license_obj.status != 'active':
        log_system_event(license_obj.id, None, 'activate', 'failed', f"License Status: {license_obj.status}", ip_address)
        return jsonify({'status': 'error', 'message': 'License is not active'}), 403
        
    if datetime.utcnow() > license_obj.expiry_date:
        log_system_event(license_obj.id, None, 'activate', 'failed', 'License Expired', ip_address)
        return jsonify({'status': 'error', 'message': 'License has expired'}), 403
        
    # 4. Check Device Limit or Existing Device
    existing_device = Device.query.filter_by(license_id=license_obj.id, device_identifier=device_identifier).first()
    
    if existing_device:
        if existing_device.status == 'blocked':
            log_system_event(license_obj.id, existing_device.id, 'activate', 'denied', 'Device Blocked', ip_address)
            return jsonify({'status': 'error', 'message': 'This device is blocked'}), 403
        # Re-activate (Update name if changed)
        existing_device.device_name = device_name
        existing_device.last_check = datetime.utcnow()
        db.session.commit()
        device_obj = existing_device
        result_msg = 'Device Re-activated'
    else:
        # Check limit
        current_devices = Device.query.filter_by(license_id=license_obj.id, status='active').count()
        if current_devices >= license_obj.max_devices:
            log_system_event(license_obj.id, None, 'activate', 'failed', 'Max Devices Reached', ip_address)
            return jsonify({'status': 'error', 'message': 'Max devices limit reached'}), 403
            
        # Create new device
        device_obj = Device(
            license_id=license_obj.id,
            device_identifier=device_identifier,
            device_name=device_name
        )
        db.session.add(device_obj)
        db.session.commit()
        result_msg = 'New Device Activated'

    # 5. Generate Token
    token = generate_token(license_obj, device_obj)
    
    log_system_event(license_obj.id, device_obj.id, 'activate', 'success', result_msg, ip_address)
    
    return jsonify({
        'status': 'success',
        'token': token,
        'expiry_date': license_obj.expiry_date.strftime('%Y-%m-%d'),
        'check_interval': current_app.config['LICENSE_CHECK_INTERVAL_DAYS']
    })

@api.route('/details', methods=['POST'])
def get_license_details():
    data = request.json
    token = data.get('token')
    device_identifier = data.get('device_identifier')
    
    if not token or not device_identifier:
        return jsonify({'status': 'error', 'message': 'Missing token or device ID'}), 400
        
    try:
        # Decode Token
        payload = jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=['HS256'])
        license_id = payload.get('license_id')
        device_id = payload.get('device_id')
        
        # Verify Device
        device = Device.query.filter_by(id=device_id, device_identifier=device_identifier).first()
        if not device:
            return jsonify({'status': 'error', 'message': 'Invalid Device'}), 401
            
        license_obj = License.query.get(license_id)
        if not license_obj:
            return jsonify({'status': 'error', 'message': 'License not found'}), 404
            
        return jsonify({
            'status': 'success',
            'school_name': license_obj.school.name,
            'education_admin': license_obj.school.education_admin,
            'license_key': license_obj.license_key, # Maybe partial mask?
            'start_date': license_obj.created_at.strftime('%Y-%m-%d'),
            'expiry_date': license_obj.expiry_date.strftime('%Y-%m-%d'),
            'max_devices': license_obj.max_devices,
            'current_devices': len(license_obj.devices),
            'license_status': license_obj.status,
            'device_status': device.status,
            'device_id': device.device_identifier
        })
        
    except jwt.ExpiredSignatureError:
        return jsonify({'status': 'error', 'message': 'Token Expired'}), 401
    except jwt.InvalidTokenError:
        return jsonify({'status': 'error', 'message': 'Invalid Token'}), 401
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@api.route('/check', methods=['POST'])
def check_license():
    data = request.json
    token = data.get('token')
    device_identifier = data.get('device_identifier')
    ip_address = request.remote_addr
    
    if not token:
        return jsonify({'status': 'error', 'message': 'Missing Token'}), 400
        
    try:
        payload = jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=['HS256'])
        license_id = payload['license_id']
        device_id = payload['device_id']
        
        license_obj = License.query.get(license_id)
        device_obj = Device.query.get(device_id)
        
        if not license_obj or not device_obj:
            return jsonify({'status': 'error', 'message': 'Invalid Token Data'}), 401
            
        if device_obj.device_identifier != device_identifier:
             return jsonify({'status': 'error', 'message': 'Device Mismatch'}), 401

        # Check Logic
        status = 'active'
        message = 'License Active'
        
        if device_obj.status == 'blocked':
            status = 'blocked'
            message = 'Device is blocked'
            
        # 2. License Status?
        elif license_obj.status != 'active':
            status = 'blocked' # Or suspended
            message = 'License Suspended'
            
        # 3. Expiry Check
        elif datetime.utcnow() > license_obj.expiry_date:
            status = 'expired'
            message = 'License Expired'
            
        # Update Last Check
        device_obj.last_check = datetime.utcnow()
        
        # Check for pending commands (Device Level)
        pending_command = device_obj.pending_command
        if pending_command:
            device_obj.pending_command = None
            
        # Check for pending commands (School Level)
        school_commands = PendingCommand.query.filter_by(school_id=license_obj.school_id, is_delivered=False).all()
        commands_list = []
        for cmd in school_commands:
            commands_list.append({
                'id': cmd.id,
                'type': cmd.command_type,
                'payload': json.loads(cmd.payload)
            })
            cmd.is_delivered = True
            cmd.delivered_at = datetime.utcnow()
            
        db.session.commit()
        
        # Log Check (Maybe sample it to avoid spam?)
        log_system_event(license_id, device_id, 'check', 'success', message, ip_address)
        
        response_data = {
            'status': status,
            'message': message,
            'expiry_date': license_obj.expiry_date.strftime('%Y-%m-%d'),
            'command': pending_command,
            'commands': commands_list
        }
        
        return jsonify(response_data)
        
    except jwt.ExpiredSignatureError:
        return jsonify({'status': 'error', 'message': 'Token Expired'}), 401
    except jwt.InvalidTokenError:
        return jsonify({'status': 'error', 'message': 'Invalid Token'}), 401

@api.route('/upload_backup', methods=['POST'])
def upload_backup():
    token = request.form.get('token')
    if not token:
        return jsonify({'status': 'error', 'message': 'Missing Token'}), 401
        
    try:
        payload = jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=['HS256'])
        license_id = payload['license_id']
        device_id = payload['device_id']
        
        license_obj = License.query.get(license_id)
        if not license_obj:
             return jsonify({'status': 'error', 'message': 'License not found'}), 404

        if 'file' not in request.files:
            return jsonify({'status': 'error', 'message': 'No file part'}), 400
            
        file = request.files['file']
        if file.filename == '':
            return jsonify({'status': 'error', 'message': 'No selected file'}), 400
            
        if file:
            # We save the file as a zip, overwriting any existing backup for this school
            # This implements a "Sync Latest Backup" strategy
            filename = secure_filename(f"backup_school_{license_obj.school.id}.zip")
            backup_folder = current_app.config['BACKUP_FOLDER']
            if not os.path.exists(backup_folder):
                os.makedirs(backup_folder)
                
            file_path = os.path.join(backup_folder, filename)
            file.save(file_path)
            file_size = os.path.getsize(file_path)
            
            # Update or Create Backup Record
            backup = BackupVault.query.filter_by(school_id=license_obj.school.id).first()
            if not backup:
                backup = BackupVault(school_id=license_obj.school.id)
                db.session.add(backup)
            
            backup.file_path = filename
            backup.file_size = file_size
            backup.uploaded_at = datetime.utcnow()
            backup.uploaded_by_device_id = device_id
            
            db.session.commit()
            
            log_system_event(license_id, device_id, 'backup_upload', 'success', f"Size: {file_size}", request.remote_addr)
            
            return jsonify({'status': 'success', 'message': 'Backup uploaded successfully'})
            
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
