from datetime import datetime, timedelta, timezone
from typing import Optional, Any, Union
import uuid
from jose import JWTError, jwt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from dotenv import load_dotenv
import os
from database import users_collection, refresh_tokens_collection
from bson import ObjectId

# Load environment variables
load_dotenv()

# Configuration
SECRET_KEY = os.getenv("SECRET_KEY", "your-super-secret-key-change-me-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 7

# Encryption for sensitive data at rest (e.g. GitHub OAuth tokens)

from cryptography.fernet import Fernet
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
if not ENCRYPTION_KEY:
    # Fallback to a derived key from SECRET_KEY if ENCRYPTION_KEY is missing
    # In production, this should be a proper 32-byte base64 encoded string.
    import base64
    import hashlib
    # Generate a deterministic 32-byte key from SECRET_KEY
    key_32 = hashlib.sha256(SECRET_KEY.encode()).digest()
    ENCRYPTION_KEY = base64.urlsafe_b64encode(key_32).decode()

cipher_suite = Fernet(ENCRYPTION_KEY.encode())

def encrypt_token(token: str) -> str:
    """Encrypt a string token using Fernet."""
    if not token:
        return ""
    return cipher_suite.encrypt(token.encode()).decode()

def decrypt_token(encrypted_token: str) -> str:
    """Decrypt a Fernet-encrypted string."""
    if not encrypted_token:
        return ""
    try:
        return cipher_suite.decrypt(encrypted_token.encode()).decode()
    except Exception:
        # If decryption fails (e.g. key changed), return empty
        return ""


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/token")

import bcrypt

def verify_password(plain_password, hashed_password):
    if not plain_password or not hashed_password:
        return False
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

def get_password_hash(password):
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "sub": "access"})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def create_refresh_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    jti = str(uuid.uuid4())
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        
    to_encode.update({
        "exp": expire, 
        "sub": "refresh",
        "jti": jti
    })
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt, jti, expire

def decode_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token)
        email: str = payload.get("email")
        type: str = payload.get("sub")
        
        if email is None or type != "access":
            raise credentials_exception
            
        user = await users_collection.find_one({"email": email})
        if user is None:
            raise credentials_exception
            
        # Convert _id to string for convenience
        user["id"] = str(user["_id"])
        return user
    except JWTError:
        raise credentials_exception
    except Exception:
        raise credentials_exception

async def validate_refresh_token(token: str) -> dict:
    """
    Validates a refresh token, checks if it's revoked, and returns the payload if valid.
    """
    try:
        payload = decode_token(token)
        email: str = payload.get("email")
        jti: str = payload.get("jti")
        token_type: str = payload.get("sub")
        
        if email is None or jti is None or token_type != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token structure",
            )
            
        # Check database for jti (Revocation check)
        token_record = await refresh_tokens_collection.find_one({"jti": jti})
        if not token_record:
            # Rejection or potential reuse detection could be added here
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token revoked or expired",
            )
            
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token expired or invalid",
        )


# ── Admin API Key dependency ──────────────────────────────────────────────────
# Used exclusively by write-access model management endpoints
# (e.g. POST /api/v1/models/activate/:version).
#
# Callers must include the header:
#     X-Admin-Key: <value of ADMIN_API_KEY in .env>
#
# Returns HTTP 503 when ADMIN_API_KEY is not configured on the server,
# and HTTP 403 when the provided key doesn't match.

_ADMIN_API_KEY: str = os.getenv("ADMIN_API_KEY", "")


async def require_admin_key(
    x_admin_key: str = Header(..., alias="X-Admin-Key", description="Admin API key for privileged operations"),
) -> None:
    """
    FastAPI dependency that enforces admin-key authentication.

    Raises
    ------
    503  ADMIN_API_KEY env var is not set on this server.
    403  The provided key does not match ADMIN_API_KEY.
    """
    if not _ADMIN_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin key is not configured on this server. Set ADMIN_API_KEY in .env.",
        )
    if x_admin_key != _ADMIN_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid admin key.",
        )
