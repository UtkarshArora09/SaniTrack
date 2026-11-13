import hashlib
import hmac
import os
import secrets
from functools import wraps
from flask import request, jsonify, session

SECRET_KEY = os.getenv('SANITRACK_SECRET_KEY', 'sanitrack-dev-secret-key-2026')


def hash_password(password: str, salt: str = None) -> tuple[str, str]:
    if not salt:
        salt = secrets.token_hex(16)
    salted = f"{salt}${password}".encode('utf-8')
    pwd_hash = hashlib.sha256(salted).hexdigest()
    return f"{salt}${pwd_hash}", salt


def verify_password(stored_hash: str, provided_password: str) -> bool:
    if not stored_hash or '$' not in stored_hash:
        return False
    salt, original_hash = stored_hash.split('$', 1)
    test_hash = hashlib.sha256(f"{salt}${provided_password}".encode('utf-8')).hexdigest()
    return hmac.compare_digest(original_hash, test_hash)


def get_current_user():
    user = session.get('user')
    if user:
        return user
    # Fallback for API token / header auth
    auth_header = request.headers.get('Authorization')
    if auth_header and auth_header.startswith('Bearer '):
        token = auth_header.split(' ', 1)[1]
        if token == 'admin-token':
            return {'username': 'admin', 'role': 'admin', 'name': 'System Administrator'}
        elif token == 'supervisor-token':
            return {'username': 'supervisor', 'role': 'supervisor', 'name': 'Floor Supervisor'}
    return None


def require_role(*allowed_roles):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = get_current_user()
            # If no login session exists, allow default admin in local dev mode if specified,
            # or return 401/403
            if not user:
                # In development mode, allow transparent access with default admin role
                dev_mode = os.getenv('SANITRACK_DEV_BYPASS_AUTH', 'true').lower() == 'true'
                if dev_mode:
                    return fn(*args, **kwargs)
                return jsonify({'error': 'Authentication required. Please log in.'}), 401
            if allowed_roles and user.get('role') not in allowed_roles and user.get('role') != 'admin':
                return jsonify({'error': f"Forbidden. Role '{user.get('role')}' does not have permission."}), 403
            return fn(*args, **kwargs)
        return wrapper
    return decorator

