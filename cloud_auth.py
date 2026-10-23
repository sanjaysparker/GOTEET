"""Supabase account sessions. Only public project configuration leaves the backend."""
import base64
import hashlib
import json
import secrets
import threading
import time
from urllib.parse import urlencode, urlparse
import httpx
import keyring
from cloud_public import URL, PUBLISHABLE_KEY

SERVICE = 'in.droneos.goteet.cloud'
LOCK = threading.RLock()
PENDING = {}

def _request(method, path, *, token=None, value=None):
    headers = {'apikey': PUBLISHABLE_KEY}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    try:
        r = httpx.request(method, URL + path, headers=headers, json=value, timeout=20)
    except httpx.HTTPError:
        raise ValueError('Cloud connection unavailable. Check your network and try again.') from None
    if not r.is_success:
        # Do not expose response bodies that could include credentials or user data.
        raise ValueError(f'Cloud request failed ({r.status_code}). Retry or sign in again.')
    return r.json() if r.content else {}

def _read():
    raw = keyring.get_password(SERVICE, 'account-session')
    return json.loads(raw) if raw else None

def _save(session):
    session['expires_at'] = time.time() + session.get('expires_in', 3600)
    # Provider tokens are not needed for identity or workspace access.
    clean = {k: session[k] for k in ('access_token','refresh_token','expires_at','user') if k in session}
    keyring.set_password(SERVICE, 'account-session', json.dumps(clean))
    return clean

def _session():
    session = _read()
    if session and session.get('expires_at', 0) < time.time() + 60:
        session = _save(_request('POST', '/auth/v1/token?grant_type=refresh_token',
                                value={'refresh_token': session['refresh_token']}))
    return session

def status():
    with LOCK:
        session = _session()
        if not session:
            provider = _request('GET', '/auth/v1/settings').get('external', {}).get('google', False)
            return {'connected': False, 'ready': bool(provider)}
        user = _request('GET', '/auth/v1/user', token=session['access_token'])
        meta = user.get('user_metadata') or {}
        return {'connected': True, 'ready': True, 'profile': {
            'id': user['id'], 'email': user.get('email'), 'name': meta.get('full_name', '')}}

def start(callback):
    parsed = urlparse(callback)
    if parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or parsed.path != '/api/cloud/callback':
        raise ValueError('Cloud sign-in requires the local desktop callback.')
    if not _request('GET', '/auth/v1/settings').get('external', {}).get('google'):
        raise ValueError('Cloud Google sign-in needs its Web OAuth client configured in Supabase first. Your existing Google imports are unchanged.')
    with LOCK:
        PENDING.clear()
        state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
        PENDING[state] = (verifier, time.monotonic())
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    return {'url': URL + '/auth/v1/authorize?' + urlencode({
        'provider': 'google', 'redirect_to': callback + '?state=' + state,
        'code_challenge': challenge, 'code_challenge_method': 's256', 'prompt': 'select_account'})}

def finish(code, state):
    with LOCK:
        pending = PENDING.pop(state, None)
        if not pending or time.monotonic() - pending[1] > 600 or not code:
            raise ValueError('Sign-in expired or was not started here. Return to GOTEET and retry.')
        session = _request('POST', '/auth/v1/token?grant_type=pkce',
                           value={'auth_code': code, 'code_verifier': pending[0]})
        user = _request('GET', '/auth/v1/user', token=session['access_token'])
        session['user'] = user
        _save(session)
        import settings
        profile_name=(user.get('user_metadata') or {}).get('full_name') or user.get('email') or 'Local user'
        settings.save({'display_name':profile_name[:200]})
        return {'email': user.get('email'), 'name': (user.get('user_metadata') or {}).get('full_name', '')}

def logout():
    with LOCK:
        session = _read()
        warning = ''
        if session:
            try:
                _request('POST', '/auth/v1/logout?scope=local', token=session['access_token'])
            except ValueError:
                warning = 'Signed out on this Mac. Server session revocation could not be confirmed.'
            keyring.delete_password(SERVICE, 'account-session')
        PENDING.clear()
        return {'connected': False, 'warning': warning}

def workspaces():
    with LOCK:
        session = _session()
        if not session:
            raise ValueError('Sign in to your GOTEET cloud account first.')
        return _request('GET', '/rest/v1/team_workspaces?select=id,name,created_at&order=created_at', token=session['access_token'])
