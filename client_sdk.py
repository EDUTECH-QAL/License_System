import requests
import platform
import uuid
import os
import json
import socket

class LicenseClient:
    def __init__(self, server_url='http://127.0.0.1:5000', storage_file='license_token.json'):
        self.server_url = server_url
        self.storage_file = storage_file
        self.token = None
        self.load_token()

    def get_device_identifier(self):
        """Generates a unique device ID based on hardware and OS user."""
        node = uuid.getnode()
        system = platform.system()
        user = os.getlogin()
        machine = platform.node()
        # Combine to create unique ID
        raw_id = f"{node}-{system}-{user}-{machine}"
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, raw_id))

    def get_device_name(self):
        return socket.gethostname()

    def load_token(self):
        if os.path.exists(self.storage_file):
            try:
                with open(self.storage_file, 'r') as f:
                    data = json.load(f)
                    self.token = data.get('token')
            except:
                pass

    def save_token(self, token, expiry_date):
        with open(self.storage_file, 'w') as f:
            json.dump({'token': token, 'expiry_date': expiry_date}, f)
        self.token = token

    def activate(self, license_key, school_name, education_admin):
        """
        Activates the license for this device.
        """
        device_id = self.get_device_identifier()
        device_name = self.get_device_name()
        
        payload = {
            'license_key': license_key,
            'school_name': school_name,
            'education_admin': education_admin,
            'device_identifier': device_id,
            'device_name': device_name
        }
        
        try:
            response = requests.post(f"{self.server_url}/api/activate", json=payload)
            data = response.json()
            
            if response.status_code == 200 and data.get('status') == 'success':
                self.save_token(data['token'], data['expiry_date'])
                return True, "Activated Successfully"
            else:
                return False, data.get('message', 'Unknown Error')
                
        except Exception as e:
            return False, f"Connection Error: {str(e)}"

    def check_license(self):
        """
        Periodically checks license status.
        Returns: (status, message)
        Status: 'active', 'grace_period', 'expired', 'blocked'
        """
        if not self.token:
            return 'expired', 'No License Found'
            
        device_id = self.get_device_identifier()
        
        payload = {
            'token': self.token,
            'device_identifier': device_id
        }
        
        try:
            response = requests.post(f"{self.server_url}/api/check", json=payload)
            data = response.json()
            
            if response.status_code == 200:
                return data.get('status'), data.get('message')
            elif response.status_code == 401:
                return 'expired', data.get('message', 'Unauthorized')
            else:
                return 'error', data.get('message', 'Server Error')
                
        except Exception as e:
            # Network error -> Check Grace Period locally if needed
            # For now, return error
            return 'error', f"Connection Failed: {str(e)}"

    def upload_backup(self, file_path):
        """
        Uploads an encrypted backup file to the server.
        """
        if not self.token:
            return False, 'No License Found'
            
        if not os.path.exists(file_path):
            return False, 'Backup file not found'
            
        try:
            files = {'file': open(file_path, 'rb')}
            data = {'token': self.token}
            
            response = requests.post(f"{self.server_url}/api/upload_backup", files=files, data=data)
            result = response.json()
            
            if response.status_code == 200:
                return True, result.get('message')
            else:
                return False, result.get('message')
                
        except Exception as e:
            return False, f"Upload Failed: {str(e)}"

# Example Usage
if __name__ == "__main__":
    client = LicenseClient()
    
    # 1. Activate
    # success, msg = client.activate("KEY-123", "My School", "East Admin")
    # print(f"Activation: {msg}")
    
    # 2. Check
    # status, msg = client.check_license()
    # print(f"Status: {status}, Message: {msg}")
