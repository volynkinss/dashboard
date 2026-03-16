from __future__ import annotations

import hmac
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from urllib.parse import urlencode

import httpx
from jose import JWTError, jwt

from app.config import Settings, get_settings
from app.security.session_store import PrincipalData


class OIDCError(RuntimeError):
    pass


@dataclass(slots=True)
class OIDCClaims:
    id_claims: dict
    access_claims: dict


class KeycloakOIDCClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.issuer_url = settings.keycloak_issuer_url.rstrip("/")
        self.client_id = settings.keycloak_client_id
        self.client_secret = settings.keycloak_client_secret
        self.roles_client_id = settings.roles_client_id
        self._metadata: dict | None = None
        self._jwks: dict | None = None

    async def _get_metadata(self) -> dict:
        if self._metadata is not None:
            return self._metadata

        url = f"{self.issuer_url}/.well-known/openid-configuration"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                self._metadata = response.json()
        except httpx.HTTPError as exc:
            raise OIDCError("Failed to load OIDC metadata") from exc

        return self._metadata

    async def _get_jwks(self) -> dict:
        if self._jwks is not None:
            return self._jwks

        metadata = await self._get_metadata()
        jwks_uri = metadata["jwks_uri"]
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(jwks_uri)
                response.raise_for_status()
                self._jwks = response.json()
        except httpx.HTTPError as exc:
            raise OIDCError("Failed to load JWKS") from exc

        return self._jwks

    async def build_authorization_url(self, state: str, nonce: str) -> str:
        metadata = await self._get_metadata()
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.settings.keycloak_redirect_uri,
            "scope": " ".join(self.settings.scopes_list),
            "state": state,
            "nonce": nonce,
        }
        return f"{metadata['authorization_endpoint']}?{urlencode(params)}"

    async def build_logout_url(self) -> str:
        metadata = await self._get_metadata()
        endpoint = metadata.get("end_session_endpoint")
        if not endpoint:
            return self.settings.keycloak_post_logout_redirect_uri

        params = {
            "client_id": self.client_id,
            "post_logout_redirect_uri": self.settings.keycloak_post_logout_redirect_uri,
        }
        return f"{endpoint}?{urlencode(params)}"

    async def exchange_code_for_tokens(self, code: str) -> dict:
        metadata = await self._get_metadata()
        token_endpoint = metadata["token_endpoint"]
        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.settings.keycloak_redirect_uri,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(token_endpoint, data=payload)
            if response.status_code >= 400:
                raise OIDCError("Token exchange failed")
            data = response.json()

        if "id_token" not in data or "access_token" not in data:
            raise OIDCError("Token response missing required fields")

        return data

    async def _get_userinfo(self, access_token: str) -> dict:
        metadata = await self._get_metadata()
        userinfo_endpoint = metadata.get("userinfo_endpoint")
        if not isinstance(userinfo_endpoint, str) or not userinfo_endpoint:
            return {}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    userinfo_endpoint,
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                response.raise_for_status()
                data = response.json()
                return data if isinstance(data, dict) else {}
        except (httpx.HTTPError, ValueError):
            return {}

    @staticmethod
    def _claim_to_string_set(raw_claim: object) -> set[str]:
        if isinstance(raw_claim, str):
            claim = raw_claim.strip()
            return {claim} if claim else set()
        if isinstance(raw_claim, list):
            return {str(value).strip() for value in raw_claim if isinstance(value, str) and str(value).strip()}
        return set()

    async def _decode_token(
        self,
        token: str,
        *,
        audience: str | None,
        verify_audience: bool,
        access_token: str | None = None,
    ) -> dict:
        try:
            header = jwt.get_unverified_header(token)
            kid = header.get("kid")
        except JWTError as exc:
            raise OIDCError("Invalid token header") from exc

        if not kid:
            raise OIDCError("Token missing kid")

        jwks = await self._get_jwks()
        key = next((item for item in jwks.get("keys", []) if item.get("kid") == kid), None)
        if key is None:
            self._jwks = None
            jwks = await self._get_jwks()
            key = next((item for item in jwks.get("keys", []) if item.get("kid") == kid), None)
        if key is None:
            raise OIDCError("Signing key not found")

        metadata = await self._get_metadata()
        issuer_candidates: list[str] = [self.issuer_url]
        metadata_issuer = metadata.get("issuer")
        if isinstance(metadata_issuer, str):
            normalized_issuer = metadata_issuer.rstrip("/")
            if normalized_issuer and normalized_issuer not in issuer_candidates:
                issuer_candidates.append(normalized_issuer)

        options = {"verify_aud": verify_audience}
        last_error: JWTError | None = None
        for issuer in issuer_candidates:
            try:
                claims = jwt.decode(
                    token,
                    key,
                    algorithms=[header.get("alg", "RS256")],
                    audience=audience,
                    issuer=issuer,
                    options=options,
                    access_token=access_token,
                )
                return claims
            except JWTError as exc:
                last_error = exc

        if last_error is None:
            raise OIDCError("Token verification failed")

        issuer_info = ", ".join(issuer_candidates)
        raise OIDCError(f"Token verification failed (issuers tried: {issuer_info}): {last_error}") from last_error

    async def verify_and_parse(self, token_response: dict, expected_nonce: str) -> PrincipalData:
        id_claims = await self._decode_token(
            token_response["id_token"],
            audience=self.client_id,
            verify_audience=True,
            access_token=token_response["access_token"],
        )

        nonce = id_claims.get("nonce")
        if not isinstance(nonce, str) or not hmac.compare_digest(nonce, expected_nonce):
            raise OIDCError("Nonce verification failed")

        access_claims = await self._decode_token(
            token_response["access_token"],
            audience=None,
            verify_audience=False,
        )

        aud = access_claims.get("aud")
        azp = access_claims.get("azp")
        aud_values: set[str] = set()
        if isinstance(aud, str):
            aud_values.add(aud)
        elif isinstance(aud, list):
            aud_values.update(str(value) for value in aud)

        if self.client_id not in aud_values and azp != self.client_id:
            raise OIDCError(
                "Access token audience mismatch "
                f"(expected client_id={self.client_id}, aud={sorted(aud_values)}, azp={azp})"
            )

        user_sub = id_claims.get("sub")
        username = id_claims.get("preferred_username") or id_claims.get("name") or user_sub
        if not isinstance(user_sub, str) or not isinstance(username, str):
            raise OIDCError("Identity claims are incomplete")

        expires_at = access_claims.get("exp")
        if not isinstance(expires_at, int):
            raise OIDCError("Access token expiration is missing")

        resource_access = access_claims.get("resource_access", {})
        client_access = {}
        if isinstance(resource_access, dict):
            raw_client_access = resource_access.get(self.roles_client_id, {})
            if isinstance(raw_client_access, dict):
                client_access = raw_client_access

        raw_roles = client_access.get("roles", [])
        roles = {str(value) for value in raw_roles if isinstance(value, str)}

        group_claim_name = self.settings.keycloak_groups_claim
        groups = self._claim_to_string_set(access_claims.get(group_claim_name))
        if not groups:
            groups = self._claim_to_string_set(id_claims.get(group_claim_name))
        if not groups:
            userinfo_claims = await self._get_userinfo(token_response["access_token"])
            groups = self._claim_to_string_set(userinfo_claims.get(group_claim_name))

        if self.settings.keycloak_groups_prefix:
            prefix = self.settings.keycloak_groups_prefix
            groups = {group for group in groups if group.startswith(prefix)}

        return PrincipalData(
            user_sub=user_sub,
            username=username,
            email=id_claims.get("email") if isinstance(id_claims.get("email"), str) else None,
            roles=roles,
            groups=groups,
            expires_at=datetime.fromtimestamp(expires_at, tz=timezone.utc),
        )


@lru_cache(maxsize=1)
def get_oidc_client() -> KeycloakOIDCClient:
    return KeycloakOIDCClient(get_settings())
