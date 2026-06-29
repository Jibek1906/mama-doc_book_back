from __future__ import annotations


RESPONSE_DESCRIPTIONS = {
    "200": "OK",
    "201": "Created",
    "204": "No Content",
    "400": "validation_error: Невалидные данные",
    "401": "not_authenticated: Не авторизован",
    "403": "forbidden: Нет доступа",
    "404": "not_found: Не найдено",
    "409": "conflict: Конфликт",
    "429": "too_many_requests: Слишком много запросов",
    "500": "server_error: Ошибка сервера",
}


def _schema_ref_name(schema: dict | None) -> str | None:
    if not isinstance(schema, dict):
        return None
    ref = schema.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
        return ref.split("/")[-1]
    return None


def _extract_request_schema(operation: dict) -> str | None:
    rb = operation.get("requestBody")
    if not isinstance(rb, dict):
        return None
    content = rb.get("content") or {}
    # Prefer JSON
    for ct in ("application/json", "application/x-www-form-urlencoded", "multipart/form-data"):
        if ct in content and isinstance(content[ct], dict):
            schema = (content[ct].get("schema") or {})
            name = _schema_ref_name(schema)
            if name:
                return name
    return None


def _extract_response_schema(operation: dict, status_code: str = "200") -> str | None:
    responses = operation.get("responses") or {}
    resp = responses.get(status_code)
    if not isinstance(resp, dict):
        return None
    content = resp.get("content") or {}
    json_ct = content.get("application/json")
    if isinstance(json_ct, dict):
        schema = json_ct.get("schema") or {}
        return _schema_ref_name(schema)
    return None


def _auth_note(*, operation: dict, default_security: object | None) -> str:
    security = operation.get("security")
    # OpenAPI semantics:
    # - operation.security == []          -> explicitly public operation
    # - operation.security is None/missing -> inherit global security (if any)
    # - operation.security is non-empty   -> explicitly protected
    if security == []:
        return "Auth: не требуется"

    # If operation has no explicit security and the schema has no global security,
    # treat it as public.
    if security is None and not default_security:
        return "Auth: не требуется"

    return "Auth: Bearer token"


def postprocess_schema(result: dict, generator, request, public: bool):
    """Enrich Swagger schema with human-readable descriptions.

    Adds:
    - per-operation description (summary + auth + error format)
    - response descriptions when missing
    """

    default_security = result.get("security")

    for _, methods in result.get("paths", {}).items():
        for _, operation in methods.items():
            # Always enrich description (but keep existing, if provided)
            summary = operation.get("summary") or operation.get("operationId") or ""
            req_schema = _extract_request_schema(operation)
            resp_schema = _extract_response_schema(operation, "200") or _extract_response_schema(operation, "201")

            generated = []
            if summary:
                generated.append(summary)
            generated.append(_auth_note(operation=operation, default_security=default_security))
            if req_schema:
                generated.append(f"Request body schema: {req_schema}")
            if resp_schema:
                generated.append(f"Success response schema: {resp_schema}")
            generated.append("Errors format: {error, message, details}")
            generated_text = "\n".join([n for n in generated if n])

            if operation.get("description"):
                # Append only if our key hints are missing
                if "Errors format" not in operation["description"]:
                    operation["description"] = operation["description"].rstrip() + "\n\n" + generated_text
            else:
                operation["description"] = generated_text

            responses = operation.get("responses", {})
            for code, response in responses.items():
                if not response.get("description"):
                    response["description"] = RESPONSE_DESCRIPTIONS.get(str(code), "Ответ")

    return result