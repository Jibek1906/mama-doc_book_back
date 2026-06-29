from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings


@dataclass(frozen=True)
class BotAuthResult:
    ok: bool
    reason: str = ""


def is_bot_authorized(request) -> BotAuthResult:
    """Validate service token for GraphQL admin operations.

    Bot must send header:
        X-BOT-TOKEN: <BOT_GRAPHQL_TOKEN>

    Token is configured via env `BOT_GRAPHQL_TOKEN`.
    """

    expected = (getattr(settings, "BOT_GRAPHQL_TOKEN", "") or "").strip()
    if not expected:
        return BotAuthResult(ok=False, reason="bot_token_not_configured")

    provided = (request.headers.get("X-BOT-TOKEN") or "").strip()
    if not provided:
        return BotAuthResult(ok=False, reason="bot_token_missing")

    if provided != expected:
        return BotAuthResult(ok=False, reason="bot_token_invalid")

    return BotAuthResult(ok=True)


def require_admin(info) -> None:
    """Raise GraphQL error if request is not allowed to perform admin mutations."""

    from .graphql_extensions import gql_error

    req = info.context.request
    user = getattr(req, "user", None)

    # Allow staff users (human admins) via JWT.
    if user and getattr(user, "is_authenticated", False) and getattr(user, "is_staff", False):
        return

    bot = is_bot_authorized(req)
    if bot.ok:
        return

    raise gql_error(
        error="forbidden",
        message="Недостаточно прав",
        details={"reason": bot.reason},
    )
