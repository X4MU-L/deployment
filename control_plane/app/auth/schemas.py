from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    username: str
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    is_active: bool

    model_config = {"from_attributes": True}

# ── User profile ──────────────────────────────────────────────────────────────
class RegisterPasswordRequest(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=8, max_length=128)


class LoginPasswordRequest(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=8, max_length=128)


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class UserProfileResponse(BaseModel):
    user_id: str
    email: str | None = None
    password_login_enabled: bool
    linked_social_providers: list[str]


class AuthSessionResponse(BaseModel):
    """Full session response: tokens + user profile."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserProfileResponse





class MeResponse(BaseModel):
    user_id: str
    tenant_id: str


class SocialProviderLoginRequest(BaseModel):
    """Internal schema used by UserAuthService — not exposed as a public endpoint."""

    provider: str = Field(pattern="^(facebook|google|github)$")
    provider_user_id: str = Field(min_length=2)
    email: str | None = None
    email_verified: bool = True


# Fix forward reference
AuthSessionResponse.model_rebuild()