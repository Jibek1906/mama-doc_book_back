from __future__ import annotations

from typing import Any

from strawberry.django.views import GraphQLView

from .graphql_auth import get_user_from_request
from .graphql_schema import schema


class MamaDocGraphQLView(GraphQLView):
    """GraphQL endpoint view.

    We keep it separate from DRF views so existing REST endpoints stay untouched.
    """

    schema = schema

    # Let cookies/Authorization headers pass through; context has request.
    def get_context(self, request, response) -> Any:
        # Attach user to request if JWT is present so resolvers can rely on request.user.
        # (DRF does this in APIViews; GraphQLView is a plain Django view.)
        auth = get_user_from_request(request)
        if auth.user is not None:
            request.user = auth.user
        return super().get_context(request, response)
