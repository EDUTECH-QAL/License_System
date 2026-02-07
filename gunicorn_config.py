import os

workers = 2
# Bind to PORT env var or default to 8080 (Fly.io default)
port = int(os.environ.get('PORT', 8080))
bind = f'0.0.0.0:{port}'
accesslog = '-'
errorlog = '-'
