from flask import Blueprint, render_template, request, flash, current_app, redirect, url_for
from flask_login import login_required, current_user
from models import EmergencyLog
from extensions import db
import os
import datetime
import base64
import hashlib
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend

emergency_bp = Blueprint('emergency', __name__, url_prefix='/admin/emergency')

def sign_data(data_bytes):
    # Load Private Key
    key_path = os.path.join(current_app.instance_path, 'emergency_private.pem')
    with open(key_path, "rb") as key_file:
        private_key = serialization.load_pem_private_key(
            key_file.read(),
            password=None,
            backend=default_backend()
        )
    
    signature = private_key.sign(
        data_bytes,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH
        ),
        hashes.SHA256()
    )
    return signature

@emergency_bp.route('/', methods=['GET', 'POST'])
@login_required
def index():
    generated_code = None
    
    if request.method == 'POST':
        school_name = request.form.get('school_name')
        device_id = request.form.get('device_id')
        duration = int(request.form.get('duration', 3))
        reason = request.form.get('reason')
        
        # 1. Calculate Expiry
        expires_at = datetime.datetime.utcnow() + datetime.timedelta(days=duration)
        expiry_timestamp = int(expires_at.timestamp())
        
        # 2. Create Payload: DEVICE_ID|EXPIRY|SALT
        salt = os.urandom(8).hex()
        payload = f"{device_id}|{expiry_timestamp}|{salt}"
        payload_bytes = payload.encode('utf-8')
        
        try:
            # 3. Sign
            signature = sign_data(payload_bytes)
            
            # 4. Combine and Encode
            # Format: Payload + Signature (Signature is 256 bytes for 2048 bit key)
            # We separate them by a delimiter or just append. 
            # Appending is safer if we know signature length, but delimiter '::' is easier.
            # Let's use a separator ':::' to avoid confusion
            full_data = base64.b64encode(payload_bytes).decode('utf-8') + ":::" + base64.b64encode(signature).decode('utf-8')
            
            # 5. Log
            log = EmergencyLog(
                device_id=device_id,
                school_name=school_name,
                generated_by=current_user.username,
                reason=reason,
                duration_days=duration,
                code_hash=hashlib.sha256(full_data.encode()).hexdigest(),
                expires_at=expires_at
            )
            db.session.add(log)
            db.session.commit()
            
            generated_code = full_data
            flash("Emergency Code Generated Successfully", "success")
            
        except Exception as e:
            flash(f"Error generating code: {str(e)}", "error")
            
    # Load recent logs
    logs = EmergencyLog.query.order_by(EmergencyLog.created_at.desc()).limit(20).all()
    
    return render_template('admin/emergency.html', generated_code=generated_code, logs=logs)
