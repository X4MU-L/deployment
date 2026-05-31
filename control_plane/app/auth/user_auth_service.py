"""
User account service — registration, login, social auth, token refresh, and profile.

Tokens are stateless JWTs issued by ``app.auth.tokens``.
No principal/session table is written on login — just sign the JWT and return it.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.exc import IntegrityError

from app.auth.passwords import hash_password, verify_password
from app.auth.schemas import (
    AuthSessionResponse,
    LoginPasswordRequest,
    RefreshTokenRequest,
    RegisterPasswordRequest,
    SocialProviderLoginRequest,
    UserProfileResponse,
)
from app.auth.tokens import create_access_token, create_refresh_token, decode_token
from app.auth.user_repository import UserAuthRepository
from app.core.exceptions import BadRequestError, ConflictError, UnauthorizedError


class UserAuthService:
    """Handles user account registration, login, social auth, and token refresh.

    repository: session-scoped persistence for users and social identities.
    """

    def __init__(self, repository: UserAuthRepository) -> None:
        self._repository = repository

    # ── Registration & login ──────────────────────────────────────────────────

    async def register_password(self, payload: RegisterPasswordRequest) -> AuthSessionResponse:
        """Create a new password account and return a JWT token pair.

        Blocked if the email already belongs to a social-login-only account.
        payload: email and password for the new account.
        repository: checked for duplicate email before inserting.
        """
        email = payload.email.strip().lower()
        if "@" not in email:
            raise BadRequestError(message="Invalid email format", code="INVALID_EMAIL")

        existing = await self._repository.get_user_by_email(email)
        if existing is not None:
            if existing.password_hash:
                raise ConflictError(
                    message="Email already registered", code="EMAIL_ALREADY_REGISTERED"
                )
            raise ConflictError(
                message="Account already created with social login; password signup is disabled",
                code="EMAIL_MANAGED_BY_SOCIAL_LOGIN",
            )

        try:
            user = await self._repository.create_user(
                email=email, password_hash=hash_password(payload.password)
            )
        except IntegrityError as exc:
            raise ConflictError(
                message="Email already registered", code="EMAIL_ALREADY_REGISTERED"
            ) from exc
        return await self._issue_token_pair(user.user_id)

    async def login_password(self, payload: LoginPasswordRequest) -> AuthSessionResponse:
        """Verify email/password credentials and return a JWT token pair.

        Fails if the account has no password set (social-only account).
        payload: email and plain-text password to verify.
        repository: used to fetch the user and verify the password hash.
        """
        email = payload.email.strip().lower()
        user = await self._repository.get_user_by_email(email)
        if user is None:
            raise UnauthorizedError(message="Invalid email or password", code="INVALID_CREDENTIALS")
        if not user.password_hash:
            raise UnauthorizedError(
                message="This account uses social login only",
                code="PASSWORD_LOGIN_DISABLED",
            )
        if not verify_password(payload.password, user.password_hash):
            raise UnauthorizedError(message="Invalid email or password", code="INVALID_CREDENTIALS")
        return await self._issue_token_pair(user.user_id)

    async def social_login_from_oauth(
        self,
        provider: str,
        provider_user_id: str,
        email: str | None,
        email_verified: bool,
    ) -> AuthSessionResponse:
        """Create or find a user account from real OAuth2 provider data.

        Called after the social OAuth callback has exchanged the code and
        fetched the provider's user info.

        provider: "github", "google", or "facebook".
        provider_user_id: the provider's unique identifier for this user.
        email: the email address returned by the provider (may be None).
        else:
            linked_user = self._repository.get_user_by_social(provider, payload.provider_user_id)
            if linked_user is not None and linked_user.user_id != current_user.user_id:
                raise ConflictError(
                    detail="This social account is already linked to another user",
                    code="SOCIAL_ALREADY_LINKED",
                )
        email_verified: whether the provider considers the email verified.
        """
        payload = SocialProviderLoginRequest(
            provider=provider,
            provider_user_id=provider_user_id,
            email=email,
            email_verified=email_verified,
        )
        return await self.social_login(payload)

    async def social_login(self, payload: SocialProviderLoginRequest) -> AuthSessionResponse:
        """Authenticate via social provider; create an account and link identity if needed.

        If the identity already exists, issues tokens for the linked user.
        If a verified email matches an existing account, links to that account instead.
        payload: provider name, provider_user_id, and optional verified email.
        repository: used to look up/create the user and persist the identity link.
        """
        provider = payload.provider.strip().lower()
        existing_social_user = await self._repository.get_user_by_social(
            provider, payload.provider_user_id
        )
        if existing_social_user is not None:
            return await self._issue_token_pair(existing_social_user.user_id)

        target_user = None
        if payload.email and payload.email_verified:
            target_user = await self._repository.get_user_by_email(payload.email.strip().lower())

        if target_user is None:
            try:
                target_user = await self._repository.create_user(
                    email=payload.email.strip().lower() if payload.email else None,
                    password_hash=None,
                )
            except IntegrityError as exc:
                existing = (
                    await self._repository.get_user_by_email(payload.email.strip().lower())
                    if payload.email
                    else None
                )
                if existing is None:
                    raise ConflictError(
                        message="Email already registered",
                        code="EMAIL_ALREADY_REGISTERED",
                    ) from exc
                target_user = existing

        try:
            await self._repository.link_social_identity(
                user_id=target_user.user_id,
                provider=provider,
                provider_user_id=payload.provider_user_id,
            )
        except IntegrityError as exc:
            linked_user = await self._repository.get_user_by_social(
                provider, payload.provider_user_id
            )
            if linked_user is None:
                raise ConflictError(
                    message="This social account is already linked to another user",
                    code="SOCIAL_ALREADY_LINKED",
                ) from exc
            target_user = linked_user
        else:
            linked_user = await self._repository.get_user_by_social(
                provider, payload.provider_user_id
            )
            if linked_user is not None and linked_user.user_id != target_user.user_id:
                raise ConflictError(
                    message="This social account is already linked to another user",
                    code="SOCIAL_ALREADY_LINKED",
                )
        return await self._issue_token_pair(target_user.user_id)

    async def refresh_tokens(self, payload: RefreshTokenRequest) -> AuthSessionResponse:
        """Exchange a valid refresh token for a new access + refresh token pair.

        The old refresh token is not revoked (stateless) — issue short-lived access tokens
        and rotate refresh tokens to limit exposure.
        payload: the refresh_token JWT string.
        """
        try:
            token_data = decode_token(payload.refresh_token)
        except ValueError as exc:
            raise UnauthorizedError(message=str(exc), code="INVALID_REFRESH_TOKEN") from exc

        if token_data.token_type != "refresh":
            raise UnauthorizedError(message="Expected a refresh token", code="WRONG_TOKEN_TYPE")
        return await self._issue_token_pair(token_data.user_id)

    # ── Social linking ────────────────────────────────────────────────────────

    async def link_social(
        self, user_id: str, payload: SocialProviderLoginRequest
    ) -> UserProfileResponse:
        """Link a social identity to an already-authenticated user account.

        Fails if the social identity is already owned by a different user.
        user_id: UUID of the authenticated user (from the decoded JWT).
        payload: provider name and provider_user_id to attach.
        repository: checked for conflicts and updated with the new link.
        """
        current_user = await self._repository.get_user_by_id(user_id)
        if current_user is None:
            raise UnauthorizedError(message="Invalid session", code="INVALID_SESSION")

        provider = payload.provider.strip().lower()
        linked_user = await self._repository.get_user_by_social(provider, payload.provider_user_id)
        if linked_user is not None and linked_user.user_id != current_user.user_id:
            raise ConflictError(
                message="This social account is already linked to another user",
                code="SOCIAL_ALREADY_LINKED",
            )

        await self._repository.link_social_identity(
            user_id=current_user.user_id,
            provider=provider,
            provider_user_id=payload.provider_user_id,
        )
        linked_user = await self._repository.get_user_by_social(provider, payload.provider_user_id)
        if linked_user is not None and linked_user.user_id != current_user.user_id:
            raise ConflictError(
                message="This social account is already linked to another user",
                code="SOCIAL_ALREADY_LINKED",
            )
        return await self.build_user_profile(current_user.user_id)

    # ── Profile ───────────────────────────────────────────────────────────────

    async def build_user_profile(self, user_id: str) -> UserProfileResponse:
        """Build a full user profile response from DB state.

        user_id: UUID of the user to look up.
        repository: source for email, password status, and linked providers.
        """
        user = await self._repository.get_user_by_id(str(_uuid(user_id)))
        if user is None:
            raise UnauthorizedError(message="User not found", code="USER_NOT_FOUND")
        return UserProfileResponse(
            user_id=user.user_id,
            email=user.email,
            password_login_enabled=bool(user.password_hash),
            linked_social_providers=await self._repository.list_social_providers(user.user_id),
        )

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _issue_token_pair(self, user_id: str) -> AuthSessionResponse:
        """Fetch user, embed email in RS256 tokens, return session response."""
        profile = await self.build_user_profile(user_id)
        email = profile.email or ""
        user_id_str = str(user_id)
        access_token = create_access_token(user_id=user_id_str, email=email, tenant_id="default")
        refresh_token = create_refresh_token(user_id=user_id_str, email=email)
        return AuthSessionResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            user=profile,
        )


def _uuid(id: str) -> UUID:
    """Validate that a id is a well-formed UUID string."""
    try:
        return UUID(id, version=4)
    except ValueError as exc:
        raise UnauthorizedError(message="Invalid user ID in token", code="INVALID_USER_ID") from exc
