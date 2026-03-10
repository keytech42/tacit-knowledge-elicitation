from httpx import AsyncClient

from app.models.user import User
from app.services.auth import create_jwt_token, verify_jwt_token
from tests.conftest import api_key_header, auth_header


class TestJWT:
    async def test_create_and_verify_jwt(self, admin_user: User):
        token = create_jwt_token(admin_user)
        payload = verify_jwt_token(token)
        assert payload["sub"] == str(admin_user.id)
        assert "admin" in payload["roles"]

    async def test_invalid_jwt_rejected(self, client: AsyncClient):
        response = await client.get(
            "/api/v1/users/me", headers={"Authorization": "Bearer invalid-token"}
        )
        assert response.status_code == 401

    async def test_missing_auth_rejected(self, client: AsyncClient):
        response = await client.get("/api/v1/users/me")
        assert response.status_code == 401


class TestAPIKeyAuth:
    async def test_api_key_auth_works(
        self, client: AsyncClient, service_user: tuple[User, str]
    ):
        user, api_key = service_user
        response = await client.get("/api/v1/users/me", headers=api_key_header(api_key))
        assert response.status_code == 200
        assert response.json()["id"] == str(user.id)
        assert response.json()["user_type"] == "service"

    async def test_invalid_api_key_rejected(self, client: AsyncClient):
        response = await client.get(
            "/api/v1/users/me", headers={"X-API-Key": "invalid-key"}
        )
        assert response.status_code == 401


class TestGetMe:
    async def test_get_me_admin(self, client: AsyncClient, admin_user: User):
        response = await client.get("/api/v1/users/me", headers=auth_header(admin_user))
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "admin@test.com"
        role_names = [r["name"] for r in data["roles"]]
        assert "admin" in role_names


class TestRoleManagement:
    async def test_assign_role(
        self, client: AsyncClient, admin_user: User, respondent_user: User
    ):
        response = await client.post(
            f"/api/v1/users/{respondent_user.id}/roles",
            json={"role_name": "reviewer"},
            headers=auth_header(admin_user),
        )
        assert response.status_code == 200
        role_names = [r["name"] for r in response.json()["roles"]]
        assert "reviewer" in role_names

    async def test_non_admin_cannot_assign_roles(
        self, client: AsyncClient, respondent_user: User
    ):
        response = await client.post(
            f"/api/v1/users/{respondent_user.id}/roles",
            json={"role_name": "admin"},
            headers=auth_header(respondent_user),
        )
        assert response.status_code == 403


class TestServiceAccountManagement:
    async def test_create_service_account(self, client: AsyncClient, admin_user: User):
        response = await client.post(
            "/api/v1/service-accounts",
            json={"display_name": "New Agent", "model_id": "claude-sonnet-4-6"},
            headers=auth_header(admin_user),
        )
        assert response.status_code == 201
        assert "api_key" in response.json()
        assert len(response.json()["api_key"]) > 20

    async def test_non_admin_cannot_create(
        self, client: AsyncClient, respondent_user: User
    ):
        response = await client.post(
            "/api/v1/service-accounts",
            json={"display_name": "Bad"},
            headers=auth_header(respondent_user),
        )
        assert response.status_code == 403
