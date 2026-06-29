from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError


@dataclass(frozen=True)
class AuthResult:
    user: object
    token: Optional[object]


def get_user_from_request(request) -> AuthResult:
    """Extract JWT user from Django request.

    Notes:
    - Existing REST endpoints explicitly set authentication_classes where needed.
    - For GraphQL we don't have DRF views, so we manually decode Bearer token.
    - If token is missing/invalid -> AnonymousUser.
    """

    auth = JWTAuthentication()
    try:
        user_auth_tuple = auth.authenticate(request)
    except (InvalidToken, TokenError):
        user_auth_tuple = None

    if not user_auth_tuple:
        return AuthResult(user=AnonymousUser(), token=None)

    user, token = user_auth_tuple
    return AuthResult(user=user, token=token)
