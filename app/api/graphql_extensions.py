from __future__ import annotations

from typing import Any, Optional

from strawberry.extensions import SchemaExtension


class RestLikeErrorsExtension(SchemaExtension):
    """Expose REST-like errors in `extensions.rest`.

    We keep the GraphQL spec-compliant `errors` array as-is, but also provide a
    convenient summary matching existing REST format:

        {
          "extensions": {
            "rest": {"error": "...", "message": "...", "details": {...}}
          }
        }

    This lets clients reuse existing error-handling logic.
    """

    def get_results(self) -> dict[str, Any]:
        result = self.execution_context.result
        if not result or not result.errors:
            return {}

        # Take the first error as the primary one.
        first = result.errors[0]
        formatted = first.formatted
        ext = formatted.get("extensions") or {}

        error_code = ext.get("error") or ext.get("code") or "server_error"
        message = formatted.get("message") or "Ошибка"
        details = ext.get("details")

        return {
            "rest": {
                "error": error_code,
                "message": message,
                "details": details,
            }
        }


def gql_error(
    *,
    error: str,
    message: str,
    details: Optional[dict[str, Any]] = None,
) -> Exception:
    """Helper to raise StrawberryGraphQLError with REST-like extension payload."""

    from strawberry.exceptions import StrawberryGraphQLError

    return StrawberryGraphQLError(
        message,
        extensions={
            "error": error,
            "message": message,
            "details": details or {},
        },
    )
