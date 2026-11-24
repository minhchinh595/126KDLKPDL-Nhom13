import hmac
import os

from fastapi import Header, HTTPException, status


def require_prediction_service_secret(
    supplied_secret: str | None = Header(
        default=None,
        alias="X-Prediction-Service-Secret",
    ),
) -> None:
    expected_secret = os.getenv("PREDICTION_SERVICE_SECRET", "")
    if len(expected_secret.encode("utf-8")) < 32:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Prediction service authentication is not configured",
        )
    if supplied_secret is None or not hmac.compare_digest(supplied_secret, expected_secret):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Valid internal service credentials are required",
        )
