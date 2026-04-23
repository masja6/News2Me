import hashlib
import hmac
import secrets as pysecrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from .config import secrets

_basic = HTTPBasic()


def require_admin(credentials: HTTPBasicCredentials = Depends(_basic)) -> str:
    expected_pw = secrets.admin_password
    if not expected_pw:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ADMIN_PASSWORD not configured. Set it in .env to enable the admin UI.",
        )
    user_ok = pysecrets.compare_digest(credentials.username, secrets.admin_user)
    pw_ok = pysecrets.compare_digest(credentials.password, expected_pw)
    if not (user_ok and pw_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


def _unsub_secret() -> bytes:
    key = secrets.unsubscribe_secret or secrets.anthropic_api_key
    return key.encode()


def unsubscribe_token(email: str) -> str:
    return hmac.new(_unsub_secret(), email.encode(), hashlib.sha256).hexdigest()[:24]


def verify_unsubscribe_token(email: str, token: str) -> bool:
    expected = unsubscribe_token(email)
    return pysecrets.compare_digest(expected, token)


def create_session_token(email: str) -> str:
    from itsdangerous import URLSafeSerializer
    serializer = URLSafeSerializer(secrets.session_secret)
    return serializer.dumps({"email": email})


def verify_session_token(token: str) -> str | None:
    from itsdangerous import URLSafeSerializer, BadSignature
    serializer = URLSafeSerializer(secrets.session_secret)
    try:
        data = serializer.loads(token)
        return data.get("email")
    except BadSignature:
        return None
