from fastapi import HTTPException
from google.auth.transport.requests import Request
from google.oauth2 import id_token
import requests


class TimeoutSession(requests.Session):
    def request(self, *args, **kwargs):
        kwargs["timeout"] = 5
        return super().request(*args, **kwargs)


def verify_scheduler(authorization: str, settings) -> None:
    if not settings.scheduler_audience or not settings.scheduler_service_account:
        raise HTTPException(status_code=503, detail="Processamento agendado não configurado.")
    if not authorization.startswith("Bearer ") or len(authorization) > 8192:
        raise HTTPException(status_code=401, detail="Autenticação necessária.")
    try:
        with TimeoutSession() as session:
            claims = id_token.verify_oauth2_token(authorization[7:], Request(session=session), audience=settings.scheduler_audience)
        if claims.get("email") != settings.scheduler_service_account or claims.get("email_verified") is not True:
            raise ValueError("Identidade inválida")
    except Exception:
        raise HTTPException(status_code=401, detail="Identidade agendada inválida.") from None
