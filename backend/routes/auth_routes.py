from flask import Blueprint, request, jsonify, session
from database import fetch_one
from core.security import verify_password, get_current_user

auth_bp = Blueprint('auth_bp', __name__)


@auth_bp.post('/api/auth/login')
def login():
    data = request.get_json(force=True) if request.data else {}
    username = (data.get('username') or '').strip().lower()
    password = (data.get('password') or '').strip()

    if not username or not password:
        return jsonify({'error': 'Username and password are required'}), 400

    user = fetch_one('SELECT * FROM users WHERE username = ?', (username,))
    if not user or not verify_password(user['password_hash'], password):
        return jsonify({'error': 'Invalid username or password'}), 401

    session_user = {
        'id': user['id'],
        'username': user['username'],
        'role': user['role'],
        'name': user['name']
    }
    session['user'] = session_user

    return jsonify({
        'status': 'authenticated',
        'user': session_user,
        'token': f"{user['role']}-token"
    })


@auth_bp.post('/api/auth/logout')
def logout():
    session.pop('user', None)
    return jsonify({'status': 'logged_out'})


@auth_bp.get('/api/auth/me')
def me():
    user = get_current_user()
    if not user:
        # Default dev user if not logged in
        return jsonify({
            'authenticated': False,
            'user': {'username': 'guest', 'role': 'viewer', 'name': 'Guest Observer'}
        })
    return jsonify({
        'authenticated': True,
        'user': user
    })

