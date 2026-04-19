from __future__ import annotations

from typing import Any, Iterable, Literal

from fastapi import HTTPException, Request, status
from jwt import InvalidTokenError, PyJWKClient, decode as jwt_decode
from pydantic import BaseModel, Field

from app.settings import Settings


class AuthenticatedUser(BaseModel):
    subject: str = Field(min_length=1, max_length=160)
    email: str | None = Field(default=None, max_length=320)
    name: str | None = Field(default=None, max_length=160)
    roles: list[str] = Field(default_factory=list)
    auth_mode: Literal["disabled", "api_key", "oidc"]

    def has_any_role(self, allowed_roles: Iterable[str]) -> bool:
        allowed = {role.strip().lower() for role in allowed_roles if role.strip()}
        granted = {role.strip().lower() for role in self.roles if role.strip()}
        return bool(allowed.intersection(granted))


class AuthenticationService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._jwk_client = (
            PyJWKClient(self.settings.effective_auth_oidc_jwks_url)
            if self.settings.auth_mode == "oidc" and self.settings.effective_auth_oidc_jwks_url
            else None
        )

    def authenticate_request(self, request: Request) -> AuthenticatedUser:
        mode = self.settings.auth_mode
        if mode == "disabled":
            return AuthenticatedUser(
                subject="local-operator",
                name="Local Operator",
                roles=list(dict.fromkeys(self.settings.auth_admin_roles)),
                auth_mode="disabled",
            )
        if mode == "api_key":
            return self._authenticate_api_key(request)
        if mode == "oidc":
            return self._authenticate_oidc(request)
        raise self._unauthorized("Unsupported authentication mode.")

    def _authenticate_api_key(self, request: Request) -> AuthenticatedUser:
        configured_api_key = self.settings.auth_api_key
        provided_api_key = request.headers.get(self.settings.auth_api_key_header_name)
        if configured_api_key and provided_api_key == configured_api_key:
            return AuthenticatedUser(
                subject="api-key-user",
                name="API Key User",
                roles=list(dict.fromkeys(self.settings.auth_admin_roles)),
                auth_mode="api_key",
            )

        token = _extract_bearer_token(request)
        if token:
            profile = self.settings.auth_bearer_tokens.get(token)
            if profile is not None:
                return _user_from_profile(profile, auth_mode="api_key")

        raise self._unauthorized("Authentication credentials were missing or invalid.")

    def _authenticate_oidc(self, request: Request) -> AuthenticatedUser:
        token = _extract_bearer_token(request)
        if token is None:
            raise self._unauthorized("Bearer token was missing or invalid.")
        if self._jwk_client is None:
            raise self._unauthorized("OIDC verification is not configured.")

        try:
            signing_key = self._jwk_client.get_signing_key_from_jwt(token)
            decode_kwargs: dict[str, Any] = {
                "algorithms": ["RS256", "RS384", "RS512"],
                "issuer": self.settings.auth_oidc_issuer_url,
            }
            if self.settings.auth_oidc_audience:
                decode_kwargs["audience"] = self.settings.auth_oidc_audience
            else:
                decode_kwargs["options"] = {"verify_aud": False}

            claims = jwt_decode(token, signing_key.key, **decode_kwargs)
        except InvalidTokenError as exc:
            raise self._unauthorized("Bearer token verification failed.") from exc
        except Exception as exc:  # pragma: no cover - defensive path for network/JWKS failures
            raise self._unauthorized("OIDC verification failed.") from exc

        roles = _extract_claim_path(claims, self.settings.auth_role_claim_path)
        if not isinstance(roles, list):
            roles = []

        return AuthenticatedUser(
            subject=str(claims.get("sub") or claims.get("preferred_username") or "unknown-user"),
            email=_optional_string(claims.get("email")),
            name=_optional_string(claims.get("name") or claims.get("preferred_username")),
            roles=[str(role).strip() for role in roles if str(role).strip()],
            auth_mode="oidc",
        )

    @staticmethod
    def _unauthorized(detail: str) -> HTTPException:
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )


def _extract_bearer_token(request: Request) -> str | None:
    authorization = request.headers.get("Authorization", "").strip()
    if not authorization:
        return None

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def _extract_claim_path(payload: dict[str, Any], claim_path: str) -> Any:
    value: Any = payload
    for segment in claim_path.split("."):
        if not segment:
            continue
        if not isinstance(value, dict) or segment not in value:
            return []
        value = value[segment]
    return value


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _user_from_profile(profile: dict[str, Any], *, auth_mode: Literal["api_key", "oidc"]) -> AuthenticatedUser:
    roles = profile.get("roles", [])
    if not isinstance(roles, list):
        roles = []

    return AuthenticatedUser(
        subject=str(profile.get("subject") or profile.get("email") or "configured-user"),
        email=_optional_string(profile.get("email")),
        name=_optional_string(profile.get("name")),
        roles=[str(role).strip() for role in roles if str(role).strip()],
        auth_mode=auth_mode,
    )
