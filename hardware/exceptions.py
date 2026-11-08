from rest_framework.exceptions import ErrorDetail, ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler


def build_error_response(
    status_code: int,
    code: str,
    message: str,
    details: dict | list | None = None,
) -> Response:
    """Build a standardized JSON error response for all API endpoints."""
    return Response(
        {
            "error": {
                "status_code": status_code,
                "code": code,
                "message": message,
                "details": details if details is not None else {},
            }
        },
        status=status_code,
    )


def _extract_first_error_message(data) -> str | None:
    if isinstance(data, dict):
        for field, value in data.items():
            nested = _extract_first_error_message(value)
            if nested:
                if field == "non_field_errors":
                    return nested
                return f"{field}: {nested}"
    elif isinstance(data, list) and data:
        return _extract_first_error_message(data[0])
    elif isinstance(data, (str, ErrorDetail)):
        return str(data)
    return None


def custom_exception_handler(exc, context):
    """
    Custom DRF exception handler ensuring every error response follows
    the unified format:
    {
        "error": {
            "status_code": <int>,
            "code": "<string>",
            "message": "<human-readable explanation>",
            "details": { ... }
        }
    }
    """
    response = exception_handler(exc, context)

    if response is None:
        return None

    status_code = response.status_code

    if isinstance(exc, ValidationError):
        first_msg = _extract_first_error_message(response.data)
        message = (
            f"Validation error — {first_msg}"
            if first_msg
            else "Invalid input data provided."
        )
        details = response.data if isinstance(response.data, dict) else {"errors": response.data}
        code = "validation_error"
    else:
        code = getattr(exc, "default_code", "error")
        if isinstance(response.data, dict) and "detail" in response.data:
            detail_obj = response.data["detail"]
            message = str(detail_obj)
            code = getattr(detail_obj, "code", code)
            details = {k: v for k, v in response.data.items() if k != "detail"}
        else:
            message = _extract_first_error_message(response.data) or "An error occurred while processing the request."
            details = response.data if isinstance(response.data, dict) else {}

    response.data = {
        "error": {
            "status_code": status_code,
            "code": str(code),
            "message": message,
            "details": details,
        }
    }
    return response
