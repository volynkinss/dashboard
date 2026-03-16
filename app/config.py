from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Secure Service Catalog"
    app_env: str = "development"
    secret_key: str = Field(default="replace-this-secret", min_length=16)

    database_url: str = "postgresql+psycopg://catalog:catalog@db:5432/catalog"

    session_cookie_name: str = "catalog_session"
    session_cookie_secure: bool = False
    session_cookie_samesite: str = "lax"
    session_cookie_domain: str | None = None

    auth_mode: str = "keycloak"

    oidc_temp_cookie_name: str = "oidc_login"
    oidc_temp_cookie_max_age_seconds: int = 300

    keycloak_issuer_url: str = "http://localhost:8080/realms/master"
    keycloak_client_id: str = "catalog"
    keycloak_client_secret: str = "replace-this-client-secret"
    keycloak_redirect_uri: str = "http://localhost:8000/auth/callback"
    keycloak_post_logout_redirect_uri: str = "http://localhost:8000/"
    keycloak_scopes: str = "openid profile email groups"
    keycloak_groups_claim: str = "groups"
    keycloak_groups_prefix: str = "/"
    keycloak_roles_client_id: str | None = None

    mock_user_sub: str = "mock-user-1"
    mock_username: str = "mock.user"
    mock_email: str = "mock.user@example.internal"
    mock_roles: str = "catalog-user"
    mock_groups: str = "/AD/IT/PortalUsers,guacamole-farm-ddt,guacamole-farm-drx,guacamole-farm-kt2,OVPN-Users"
    mock_session_ttl_seconds: int = 36000
    mock_profile_default: str = "restricted"
    mock_public_user_sub: str = "mock-public-1"
    mock_public_username: str = "mock.public"
    mock_public_email: str = "mock.public@example.internal"
    mock_public_roles: str = ""
    mock_public_groups: str = ""

    trusted_hosts: str = "localhost,127.0.0.1,0.0.0.0,::1,host.docker.internal"
    audit_enabled: bool = True
    log_level: str = "INFO"

    @property
    def trusted_hosts_list(self) -> list[str]:
        hosts = [item.strip() for item in self.trusted_hosts.split(",") if item.strip()]
        if "*" in hosts:
            return ["*"]
        return hosts

    @property
    def scopes_list(self) -> list[str]:
        return [item.strip() for item in self.keycloak_scopes.split() if item.strip()]

    @property
    def roles_client_id(self) -> str:
        return self.keycloak_roles_client_id or self.keycloak_client_id

    @property
    def is_mock_auth_mode(self) -> bool:
        return self.auth_mode.strip().lower() == "mock"

    @property
    def mock_roles_list(self) -> list[str]:
        return [item.strip() for item in self.mock_roles.split(",") if item.strip()]

    @property
    def mock_groups_list(self) -> list[str]:
        return [item.strip() for item in self.mock_groups.split(",") if item.strip()]

    @property
    def mock_public_roles_list(self) -> list[str]:
        return [item.strip() for item in self.mock_public_roles.split(",") if item.strip()]

    @property
    def mock_public_groups_list(self) -> list[str]:
        return [item.strip() for item in self.mock_public_groups.split(",") if item.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
