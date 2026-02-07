from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
import os

def generate_keys():
    # Generate private key
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )

    # Serialize private key
    pem_private = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )

    # Serialize public key
    public_key = private_key.public_key()
    pem_public = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )

    # Determine base path (current script directory)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Define paths
    instance_dir = os.path.join(base_dir, 'instance')
    if not os.path.exists(instance_dir):
        os.makedirs(instance_dir)
        
    private_key_path = os.path.join(instance_dir, 'emergency_private.pem')
    public_key_path = os.path.join(base_dir, 'emergency_public.pem')

    # Save Private Key
    with open(private_key_path, 'wb') as f:
        f.write(pem_private)

    # Save Public Key
    with open(public_key_path, 'wb') as f:
        f.write(pem_public)

    print("Keys generated successfully!")
    print(f"Private Key: {private_key_path}")
    print(f"Public Key: {public_key_path}")

if __name__ == '__main__':
    generate_keys()
