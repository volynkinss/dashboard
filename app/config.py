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
    keycloak_groups_prefix: str = ""
    keycloak_roles_client_id: str | None = None
    admin_email: str = ""
    dashy_config_path: str = "/app/data/dashy.yaml"

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

    trusted_hosts: str = "*"
    trusted_proxy_networks: str = "127.0.0.0/8,::1/128"
    internal_networks: str = "10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,127.0.0.0/8,::1/128,fc00::/7,fe80::/10"
    internal_only_category_names: str = "Корпоративные Web-приложения,Corporate Web Applications"
    internal_only_category_slugs: str = ""
    audit_enabled: bool = True
    audit_retention_days: int = Field(default=30, ge=1)
    audit_catalog_view_min_interval_seconds: int = Field(default=300, ge=0)
    activity_log_enabled: bool = True
    activity_log_file_path: str = "logs/catalog_activity.log"
    activity_log_backup_count: int = Field(default=10, ge=1)
    db_maintenance_enabled: bool = True
    db_maintenance_interval_seconds: int = Field(default=300, ge=30)
    session_ttl_seconds: int = Field(default=0, ge=0)
    session_expired_grace_seconds: int = Field(default=0, ge=0)
    session_last_seen_update_interval_seconds: int = Field(default=120, ge=0)
    log_level: str = "INFO"

    @property
    def trusted_hosts_list(self) -> list[str]:
        hosts = [item.strip() for item in self.trusted_hosts.split(",") if item.strip()]
        if "*" in hosts:
            return ["*"]
        return hosts

    @property
    def trusted_proxy_networks_list(self) -> list[str]:
        return [item.strip() for item in self.trusted_proxy_networks.split(",") if item.strip()]

    @property
    def internal_networks_list(self) -> list[str]:
        return [item.strip() for item in self.internal_networks.split(",") if item.strip()]

    @property
    def internal_only_category_names_list(self) -> list[str]:
        return [item.strip() for item in self.internal_only_category_names.split(",") if item.strip()]

    @property
    def internal_only_category_slugs_list(self) -> list[str]:
        return [item.strip() for item in self.internal_only_category_slugs.split(",") if item.strip()]

    @property
    def scopes_list(self) -> list[str]:
        return [item.strip() for item in self.keycloak_scopes.split() if item.strip()]

    @property
    def admin_email_normalized(self) -> str | None:
        value = self.admin_email.strip().casefold()
        return value or None

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
