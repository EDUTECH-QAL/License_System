# License Server Deployment Guide

This folder contains the complete License Server application ready for deployment.

## Files Structure
- `app.py`: Flask application entry point (development).
- `wsgi.py`: Entry point for production servers (Gunicorn).
- `config.py`: Configuration settings.
- `requirements.txt`: Python dependencies.
- `Procfile`: Heroku/Render deployment configuration.
- `gunicorn_config.py`: Gunicorn configuration.
- `emergency_public.pem`: The public key clients need to verify emergency codes.
- `instance/`: Contains the database (`license_system.db`) and private key (`emergency_private.pem`).

## Deployment Steps

1. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Environment Variables:**
   Set the following environment variables on your server:
   - `SECRET_KEY`: A long random string.
   - `DATABASE_URL`: (Optional) Connection string if using PostgreSQL/MySQL. Defaults to SQLite in `instance/`.

3. **Run with Gunicorn:**
   ```bash
   gunicorn -c gunicorn_config.py wsgi:app
   ```
   Or simply:
   ```bash
   gunicorn wsgi:app
   ```

## Key Management
- To generate new keys, run:
  ```bash
  python generate_keys.py
  ```
  This will update `instance/emergency_private.pem` and `emergency_public.pem`.
- **IMPORTANT:** If you rotate keys, you must distribute the new `emergency_public.pem` to all client schools.
