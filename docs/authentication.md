# Authentication

The platform supports three authentication methods, each serving a distinct use case.

## Google OAuth (Production)

For human users in production environments.

### Flow

1. Frontend opens a Google consent popup via `@react-oauth/google` (auth-code flow)
2. User selects an account, Google returns an authorization code to the popup
3. Frontend sends the code to `POST /api/v1/auth/google`
4. Backend exchanges the code with Google for user info (email, name, avatar)
5. Backend finds or creates the user, returns a JWT token

### First-Time Users

New Google users are automatically created with the `respondent` role. If their email matches the `BOOTSTRAP_ADMIN_EMAIL` environment variable, they receive all four roles.

### Setup

Set these environment variables:
```
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
GOOGLE_REDIRECT_URI=http://localhost:5173 (must match GCP authorized redirect URI)
BOOTSTRAP_ADMIN_EMAIL=admin@yourcompany.com
```

## Dev Login (Local Development)

Available when `DEV_LOGIN_ENABLED` is true (the default).

Click **Sign in as Test User** on the login page. The frontend calls `POST /api/v1/auth/dev-login`, which creates (or returns) a `dev@localhost` user with all roles. When Google OAuth is also configured, both options appear on the login page.

This endpoint returns 404 when `DEV_LOGIN_ENABLED` is false, so it can be disabled in production.

## API Key (Service Accounts)

For LLM agents and automated systems.

### Usage

Include the key in the `X-API-Key` header:
```
X-API-Key: kep_a1b2c3d4e5f6...
```

### Lifecycle

1. An admin creates a service account via `POST /api/v1/service-accounts`
2. The response includes the API key — this is shown only once
3. The key is stored as a SHA256 hash in the database
4. Keys can be rotated via `POST /api/v1/service-accounts/{id}/rotate-key`

### Middleware Logging

All write operations (POST, PUT, PATCH, DELETE) from service accounts are automatically logged by the AI logging middleware. Logs capture the endpoint, request body, response status, and latency.

## JWT Token

All authentication methods return a JWT token with this payload:

```json
{
  "sub": "user-uuid",
  "user_type": "human",
  "roles": ["admin", "author"],
  "iat": 1709500000,
  "exp": 1709586400
}
```

- Signed with `JWT_SECRET` using HS256
- Default expiry: 24 hours (configurable via `JWT_EXPIRY_HOURS`)
- Stored in the browser's localStorage

## Authorization

Role checks use FastAPI dependency injection:

```python
@router.post("/questions")
async def create_question(
    user: User = Depends(require_role(RoleName.AUTHOR, RoleName.ADMIN)),
):
    ...
```

The `require_role()` factory returns a dependency that:
1. Extracts the current user (via JWT or API key)
2. Checks that the user has at least one of the specified roles
3. Returns 403 if the check fails

## Token Refresh

Call `POST /api/v1/auth/refresh?token=<current-jwt>` to get a new token. The frontend does not currently auto-refresh — tokens expire after `JWT_EXPIRY_HOURS`.
