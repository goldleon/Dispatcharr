from urllib.parse import parse_qs
from channels.middleware import BaseMiddleware
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.settings import api_settings
import logging

logger = logging.getLogger(__name__)


def _decode_token_no_db(raw_token):
    """
    Validate and decode a JWT token using only cryptographic checks.
    Returns the decoded payload dict, or raises InvalidToken / TokenError.
    This function performs NO database I/O and is safe to call from async code.
    """
    # import here to avoid any module-level side-effects at import time
    from rest_framework_simplejwt.backends import TokenBackend
    from rest_framework_simplejwt.tokens import UntypedToken

    # UntypedToken.__init__ calls verify() which may call check_blacklist().
    # We bypass that by going straight to the backend for cryptographic validation.
    token_backend = TokenBackend(
        algorithm=api_settings.ALGORITHM,
        signing_key=api_settings.SIGNING_KEY,
        verifying_key=api_settings.VERIFYING_KEY,
        audience=api_settings.AUDIENCE,
        issuer=api_settings.ISSUER,
    )
    return token_backend.decode(raw_token)


@database_sync_to_async
def _get_user_by_id(user_id):
    """Fetch a User from the database. Runs in a Django-managed sync thread."""
    from django.db import close_old_connections
    close_old_connections()

    User = get_user_model()
    try:
        return User.objects.get(**{api_settings.USER_ID_FIELD: user_id})
    except User.DoesNotExist:
        logger.warning("JWT WS auth: user_id=%s not found in database.", user_id)
        return AnonymousUser()


async def get_user_from_token(raw_token):
    """
    Fully async JWT token → User resolver for WebSocket connections.

    Steps:
      1. Validate the token cryptographically (no DB, safe in async context).
      2. Extract the user-ID claim from the decoded payload.
      3. Look up the User via a properly threaded DB call.
    """
    try:
        payload = _decode_token_no_db(raw_token)
    except (InvalidToken, TokenError) as e:
        logger.warning("JWT WS auth: invalid token – %s", e)
        return AnonymousUser()
    except Exception as e:
        logger.error("JWT WS auth: unexpected error decoding token – %s", e)
        return AnonymousUser()

    user_id = payload.get(api_settings.USER_ID_CLAIM)
    if user_id is None:
        logger.warning("JWT WS auth: token payload missing user_id claim.")
        return AnonymousUser()

    return await _get_user_by_id(user_id)


class JWTAuthMiddleware(BaseMiddleware):
    """
    WebSocket authentication middleware reading JWT tokens from query parameters (?token=).

    Security Note: Query string tokens are logged by HTTP proxies and web servers.
    HTTPS/WSS should be enforced to protect tokens in transit.
    """

    async def __call__(self, scope, receive, send):
        try:
            query_string = parse_qs(scope["query_string"].decode())
            raw_token = query_string.get("token", [None])[0]

            if raw_token is not None:
                scope["user"] = await get_user_from_token(raw_token)
            else:
                scope["user"] = AnonymousUser()
        except Exception as e:
            logger.error("JWT WS auth middleware error: %s", e)
            scope["user"] = AnonymousUser()

        return await super().__call__(scope, receive, send)
