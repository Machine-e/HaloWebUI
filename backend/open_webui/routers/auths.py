import asyncio
import re
import uuid
import time
import datetime
import logging
from aiohttp import ClientSession

from open_webui.models.auths import (
    AddUserForm,
    ApiKey,
    Auths,
    Token,
    LdapForm,
    SigninForm,
    SigninResponse,
    SignupForm,
    UpdatePasswordForm,
    UpdateProfileForm,
    UserResponse,
)
from open_webui.models.users import Users
from open_webui.models.groups import Groups, GroupUpdateForm

from open_webui.constants import ERROR_MESSAGES, WEBHOOK_MESSAGES
from open_webui.env import (
    WEBUI_AUTH,
    WEBUI_AUTH_TRUSTED_EMAIL_HEADER,
    WEBUI_AUTH_TRUSTED_NAME_HEADER,
    WEBUI_AUTH_COOKIE_SAME_SITE,
    WEBUI_AUTH_COOKIE_SECURE,
    SRC_LOG_LEVELS,
)
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse, Response
from open_webui.config import (
    ENABLE_LDAP,
    ENABLE_OAUTH_LOGIN,
    ENABLE_OAUTH_SIGNUP,
    OAUTH_ALLOWED_DOMAINS,
    OAUTH_CLIENT_ID,
    OAUTH_CLIENT_SECRET,
    OAUTH_MERGE_ACCOUNTS_BY_EMAIL,
    OAUTH_PROVIDER_NAME,
    OAUTH_SCOPES,
    OPENID_END_SESSION_ENDPOINT,
    OPENID_PROVIDER_URL,
    OPENID_REDIRECT_URI,
    load_oauth_providers,
)
from open_webui.config import (
    ENABLE_OAUTH_TOKEN_EXCHANGE,
    OAUTH_TOKEN_EXCHANGE_ISSUER,
    OAUTH_TOKEN_EXCHANGE_JWKS_URI,
    OAUTH_TOKEN_EXCHANGE_AUDIENCE,
)
from pydantic import BaseModel
from open_webui.utils.misc import parse_duration, validate_email_format
from open_webui.utils.encryption import decrypt_token
from open_webui.utils.auth import (
    create_api_key,
    create_token,
    get_admin_user,
    get_verified_user,
    get_current_user,
    get_password_hash,
)
from open_webui.utils.webhook import post_webhook
from open_webui.utils.access_control import get_permissions

from typing import Optional, List

from ssl import CERT_REQUIRED, PROTOCOL_TLS

if ENABLE_LDAP.value:
    from ldap3 import Server, Connection, NONE, Tls
    from ldap3.utils.conv import escape_filter_chars

router = APIRouter()

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["MAIN"])

# Lock to prevent race conditions during first-user (admin) creation
_signup_lock = asyncio.Lock()

############################
# GetSessionUser
############################


class SessionUserResponse(Token, UserResponse):
    expires_at: Optional[int] = None
    permissions: Optional[dict] = None


@router.get("/", response_model=SessionUserResponse)
async def get_session_user(
    request: Request, response: Response, user=Depends(get_current_user)
):
    expires_delta = parse_duration(request.app.state.config.JWT_EXPIRES_IN)
    expires_at = None
    if expires_delta:
        expires_at = int(time.time()) + int(expires_delta.total_seconds())

    token = create_token(
        data={"id": user.id},
        expires_delta=expires_delta,
    )

    datetime_expires_at = (
        datetime.datetime.fromtimestamp(expires_at, datetime.timezone.utc)
        if expires_at
        else None
    )

    # Set the cookie token
    response.set_cookie(
        key="token",
        value=token,
        expires=datetime_expires_at,
        httponly=True,  # Ensures the cookie is not accessible via JavaScript
        samesite=WEBUI_AUTH_COOKIE_SAME_SITE,
        secure=WEBUI_AUTH_COOKIE_SECURE,
    )

    user_permissions = get_permissions(
        user.id, request.app.state.config.USER_PERMISSIONS
    )

    return {
        "token": token,
        "token_type": "Bearer",
        "expires_at": expires_at,
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "role": user.role,
        "profile_image_url": user.profile_image_url,
        "permissions": user_permissions,
    }


############################
# Update Profile
############################


@router.post("/update/profile", response_model=UserResponse)
async def update_profile(
    form_data: UpdateProfileForm, session_user=Depends(get_verified_user)
):
    if session_user:
        user = Users.update_user_by_id(
            session_user.id,
            {"profile_image_url": form_data.profile_image_url, "name": form_data.name},
        )
        if user:
            return user
        else:
            raise HTTPException(400, detail=ERROR_MESSAGES.DEFAULT())
    else:
        raise HTTPException(400, detail=ERROR_MESSAGES.INVALID_CRED)


############################
# Update Password
############################


@router.post("/update/password", response_model=bool)
async def update_password(
    form_data: UpdatePasswordForm, session_user=Depends(get_current_user)
):
    if WEBUI_AUTH_TRUSTED_EMAIL_HEADER:
        raise HTTPException(400, detail=ERROR_MESSAGES.ACTION_PROHIBITED)

    if len(form_data.new_password.encode("utf-8")) > 72:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.PASSWORD_TOO_LONG,
        )

    if session_user:
        user = Auths.authenticate_user(session_user.email, form_data.password)

        if user:
            hashed = get_password_hash(form_data.new_password)
            return Auths.update_user_password_by_id(user.id, hashed)
        else:
            raise HTTPException(400, detail=ERROR_MESSAGES.INVALID_PASSWORD)
    else:
        raise HTTPException(400, detail=ERROR_MESSAGES.INVALID_CRED)


############################
# LDAP Authentication
############################
@router.post("/ldap", response_model=SessionUserResponse)
async def ldap_auth(request: Request, response: Response, form_data: LdapForm):
    ENABLE_LDAP = request.app.state.config.ENABLE_LDAP
    LDAP_SERVER_LABEL = request.app.state.config.LDAP_SERVER_LABEL
    LDAP_SERVER_HOST = request.app.state.config.LDAP_SERVER_HOST
    LDAP_SERVER_PORT = request.app.state.config.LDAP_SERVER_PORT
    LDAP_ATTRIBUTE_FOR_MAIL = request.app.state.config.LDAP_ATTRIBUTE_FOR_MAIL
    LDAP_ATTRIBUTE_FOR_USERNAME = request.app.state.config.LDAP_ATTRIBUTE_FOR_USERNAME
    LDAP_SEARCH_BASE = request.app.state.config.LDAP_SEARCH_BASE
    LDAP_SEARCH_FILTERS = request.app.state.config.LDAP_SEARCH_FILTERS
    LDAP_APP_DN = request.app.state.config.LDAP_APP_DN
    LDAP_APP_PASSWORD = request.app.state.config.LDAP_APP_PASSWORD
    LDAP_USE_TLS = request.app.state.config.LDAP_USE_TLS
    LDAP_CA_CERT_FILE = request.app.state.config.LDAP_CA_CERT_FILE
    LDAP_CIPHERS = (
        request.app.state.config.LDAP_CIPHERS
        if request.app.state.config.LDAP_CIPHERS
        else "ALL"
    )

    if not ENABLE_LDAP:
        raise HTTPException(400, detail="LDAP authentication is not enabled")

    try:
        tls = Tls(
            validate=CERT_REQUIRED,
            version=PROTOCOL_TLS,
            ca_certs_file=LDAP_CA_CERT_FILE,
            ciphers=LDAP_CIPHERS,
        )
    except Exception as e:
        log.error(f"TLS configuration error: {str(e)}")
        raise HTTPException(400, detail="Failed to configure TLS for LDAP connection.")

    try:
        server = Server(
            host=LDAP_SERVER_HOST,
            port=LDAP_SERVER_PORT,
            get_info=NONE,
            use_ssl=LDAP_USE_TLS,
            tls=tls,
            connect_timeout=10,
        )
        connection_app = Connection(
            server,
            LDAP_APP_DN,
            LDAP_APP_PASSWORD,
            auto_bind="NONE",
            authentication="SIMPLE" if LDAP_APP_DN else "ANONYMOUS",
            receive_timeout=10,
        )
        if not connection_app.bind():
            raise HTTPException(400, detail="Application account bind failed")

        search_success = connection_app.search(
            search_base=LDAP_SEARCH_BASE,
            search_filter=f"(&({LDAP_ATTRIBUTE_FOR_USERNAME}={escape_filter_chars(form_data.user.lower())}){LDAP_SEARCH_FILTERS})",
            attributes=[
                f"{LDAP_ATTRIBUTE_FOR_USERNAME}",
                f"{LDAP_ATTRIBUTE_FOR_MAIL}",
                "cn",
                f"{request.app.state.config.LDAP_GROUP_ATTRIBUTE}",
            ],
        )

        if not search_success:
            raise HTTPException(400, detail="User not found in the LDAP server")

        entry = connection_app.entries[0]
        username = str(entry[f"{LDAP_ATTRIBUTE_FOR_USERNAME}"]).lower()
        email = entry[f"{LDAP_ATTRIBUTE_FOR_MAIL}"].value  # retrive the Attribute value
        if not email:
            raise HTTPException(400, "User does not have a valid email address.")
        elif isinstance(email, str):
            email = email.lower()
        elif isinstance(email, list):
            email = email[0].lower()
        else:
            email = str(email).lower()

        cn = str(entry["cn"])
        user_dn = entry.entry_dn

        if username == form_data.user.lower():
            connection_user = Connection(
                server,
                user_dn,
                form_data.password,
                auto_bind="NONE",
                authentication="SIMPLE",
                receive_timeout=10,
            )
            if not connection_user.bind():
                raise HTTPException(400, "Authentication failed.")

            user = Users.get_user_by_email(email)
            if not user:
                try:
                    user_count = Users.get_num_users()

                    role = (
                        "admin"
                        if user_count == 0
                        else request.app.state.config.DEFAULT_USER_ROLE
                    )

                    user = Auths.insert_new_auth(
                        email=email,
                        password=str(uuid.uuid4()),
                        name=cn,
                        role=role,
                    )

                    if not user:
                        raise HTTPException(
                            500, detail=ERROR_MESSAGES.CREATE_USER_ERROR
                        )

                except HTTPException:
                    raise
                except Exception as err:
                    log.error(f"LDAP user creation error: {str(err)}")
                    raise HTTPException(
                        500, detail="Internal error occurred during LDAP user creation."
                    )

            user = Auths.authenticate_user_by_trusted_header(email)

            # LDAP Group Sync
            if user and request.app.state.config.ENABLE_LDAP_GROUP_SYNC:
                try:
                    group_attr = request.app.state.config.LDAP_GROUP_ATTRIBUTE
                    ldap_groups = []
                    if group_attr in entry:
                        raw = entry[group_attr].values
                        # memberOf returns full DNs like "cn=devs,ou=groups,dc=..."
                        # Extract the CN portion as the group name
                        for dn_or_name in (raw if isinstance(raw, list) else [raw]):
                            dn_str = str(dn_or_name)
                            if dn_str.lower().startswith("cn="):
                                name = dn_str.split(",")[0].split("=", 1)[1]
                            else:
                                name = dn_str
                            ldap_groups.append(name)

                    if ldap_groups:
                        current_groups = Groups.get_groups_by_member_id(user.id)
                        all_groups = Groups.get_groups()

                        # Remove user from groups no longer in LDAP
                        for grp in current_groups:
                            if grp.name not in ldap_groups:
                                user_ids = [
                                    uid for uid in grp.user_ids if uid != user.id
                                ]
                                Groups.update_group_by_id(
                                    id=grp.id,
                                    form_data=GroupUpdateForm(
                                        name=grp.name,
                                        description=grp.description,
                                        permissions=grp.permissions or {},
                                        user_ids=user_ids,
                                    ),
                                    overwrite=False,
                                )

                        # Add user to matching groups
                        for grp in all_groups:
                            if grp.name in ldap_groups and not any(
                                g.name == grp.name for g in current_groups
                            ):
                                user_ids = grp.user_ids + [user.id]
                                Groups.update_group_by_id(
                                    id=grp.id,
                                    form_data=GroupUpdateForm(
                                        name=grp.name,
                                        description=grp.description,
                                        permissions=grp.permissions or {},
                                        user_ids=user_ids,
                                    ),
                                    overwrite=False,
                                )

                        log.debug(f"LDAP group sync: {ldap_groups}")
                except Exception as e:
                    log.warning(f"LDAP group sync error (non-fatal): {e}")

            if user:
                token = create_token(
                    data={"id": user.id},
                    expires_delta=parse_duration(
                        request.app.state.config.JWT_EXPIRES_IN
                    ),
                )

                # Set the cookie token
                response.set_cookie(
                    key="token",
                    value=token,
                    httponly=True,  # Ensures the cookie is not accessible via JavaScript
                )

                user_permissions = get_permissions(
                    user.id, request.app.state.config.USER_PERMISSIONS
                )

                return {
                    "token": token,
                    "token_type": "Bearer",
                    "id": user.id,
                    "email": user.email,
                    "name": user.name,
                    "role": user.role,
                    "profile_image_url": user.profile_image_url,
                    "permissions": user_permissions,
                }
            else:
                raise HTTPException(400, detail=ERROR_MESSAGES.INVALID_CRED)
        else:
            raise HTTPException(400, "User record mismatch.")
    except Exception as e:
        log.error(f"LDAP authentication error: {str(e)}")
        raise HTTPException(400, detail="LDAP authentication failed.")


############################
# SignIn
############################


@router.post("/signin", response_model=SessionUserResponse)
async def signin(request: Request, response: Response, form_data: SigninForm):
    if WEBUI_AUTH_TRUSTED_EMAIL_HEADER:
        if WEBUI_AUTH_TRUSTED_EMAIL_HEADER not in request.headers:
            raise HTTPException(400, detail=ERROR_MESSAGES.INVALID_TRUSTED_HEADER)

        trusted_email = request.headers[WEBUI_AUTH_TRUSTED_EMAIL_HEADER].lower()
        trusted_name = trusted_email
        if WEBUI_AUTH_TRUSTED_NAME_HEADER:
            trusted_name = request.headers.get(
                WEBUI_AUTH_TRUSTED_NAME_HEADER, trusted_email
            )
        if not Users.get_user_by_email(trusted_email.lower()):
            await signup(
                request,
                response,
                SignupForm(
                    email=trusted_email, password=str(uuid.uuid4()), name=trusted_name
                ),
            )
        user = Auths.authenticate_user_by_trusted_header(trusted_email)
    elif WEBUI_AUTH == False:
        admin_email = "admin@localhost"
        user = Users.get_user_by_email(admin_email.lower())

        if user is None:
            user = Users.get_first_user()

        if user is None:
            user = Auths.insert_new_auth(
                admin_email.lower(),
                get_password_hash(str(uuid.uuid4())),
                "User",
                "/user.png",
                "admin",
            )
    else:
        user = Auths.authenticate_user(form_data.email.lower(), form_data.password)

    if user:

        expires_delta = parse_duration(request.app.state.config.JWT_EXPIRES_IN)
        expires_at = None
        if expires_delta:
            expires_at = int(time.time()) + int(expires_delta.total_seconds())

        token = create_token(
            data={"id": user.id},
            expires_delta=expires_delta,
        )

        datetime_expires_at = (
            datetime.datetime.fromtimestamp(expires_at, datetime.timezone.utc)
            if expires_at
            else None
        )

        # Set the cookie token
        response.set_cookie(
            key="token",
            value=token,
            expires=datetime_expires_at,
            httponly=True,  # Ensures the cookie is not accessible via JavaScript
            samesite=WEBUI_AUTH_COOKIE_SAME_SITE,
            secure=WEBUI_AUTH_COOKIE_SECURE,
        )

        user_permissions = get_permissions(
            user.id, request.app.state.config.USER_PERMISSIONS
        )

        return {
            "token": token,
            "token_type": "Bearer",
            "expires_at": expires_at,
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "role": user.role,
            "profile_image_url": user.profile_image_url,
            "permissions": user_permissions,
        }
    else:
        raise HTTPException(400, detail=ERROR_MESSAGES.INVALID_CRED)


############################
# SignUp
############################


@router.post("/signup", response_model=SessionUserResponse)
async def signup(request: Request, response: Response, form_data: SignupForm):

    if not validate_email_format(form_data.email.lower()):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail=ERROR_MESSAGES.INVALID_EMAIL_FORMAT
        )

    if len(form_data.password.encode("utf-8")) > 72:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.PASSWORD_TOO_LONG,
        )

    # Use lock to prevent race condition where multiple concurrent requests
    # could each see user_count==0 and all create admin accounts
    async with _signup_lock:
        if WEBUI_AUTH:
            if (
                not request.app.state.config.ENABLE_SIGNUP
                or not request.app.state.config.ENABLE_LOGIN_FORM
            ):
                raise HTTPException(
                    status.HTTP_403_FORBIDDEN, detail=ERROR_MESSAGES.ACCESS_PROHIBITED
                )
        else:
            if Users.get_num_users() != 0:
                raise HTTPException(
                    status.HTTP_403_FORBIDDEN, detail=ERROR_MESSAGES.ACCESS_PROHIBITED
                )

        user_count = Users.get_num_users()

        if Users.get_user_by_email(form_data.email.lower()):
            raise HTTPException(400, detail=ERROR_MESSAGES.EMAIL_TAKEN)

        try:
            role = (
                "admin"
                if user_count == 0
                else request.app.state.config.DEFAULT_USER_ROLE
            )

            if user_count == 0:
                # Disable signup after the first user is created
                request.app.state.config.ENABLE_SIGNUP = False

            hashed = get_password_hash(form_data.password)
            user = Auths.insert_new_auth(
                form_data.email.lower(),
                hashed,
                form_data.name,
                form_data.profile_image_url,
                role,
            )

            if user:
                expires_delta = parse_duration(request.app.state.config.JWT_EXPIRES_IN)
                expires_at = None
                if expires_delta:
                    expires_at = int(time.time()) + int(expires_delta.total_seconds())

                token = create_token(
                    data={"id": user.id},
                    expires_delta=expires_delta,
                )

                datetime_expires_at = (
                    datetime.datetime.fromtimestamp(expires_at, datetime.timezone.utc)
                    if expires_at
                    else None
                )

                # Set the cookie token
                response.set_cookie(
                    key="token",
                    value=token,
                    expires=datetime_expires_at,
                    httponly=True,  # Ensures the cookie is not accessible via JavaScript
                    samesite=WEBUI_AUTH_COOKIE_SAME_SITE,
                    secure=WEBUI_AUTH_COOKIE_SECURE,
                )

                if request.app.state.config.WEBHOOK_URL:
                    post_webhook(
                        request.app.state.WEBUI_NAME,
                        request.app.state.config.WEBHOOK_URL,
                        WEBHOOK_MESSAGES.USER_SIGNUP(user.name),
                        {
                            "action": "signup",
                            "message": WEBHOOK_MESSAGES.USER_SIGNUP(user.name),
                            "user": user.model_dump_json(exclude_none=True),
                        },
                    )

                user_permissions = get_permissions(
                    user.id, request.app.state.config.USER_PERMISSIONS
                )

                return {
                    "token": token,
                    "token_type": "Bearer",
                    "expires_at": expires_at,
                    "id": user.id,
                    "email": user.email,
                    "name": user.name,
                    "role": user.role,
                    "profile_image_url": user.profile_image_url,
                    "permissions": user_permissions,
                }
            else:
                raise HTTPException(500, detail=ERROR_MESSAGES.CREATE_USER_ERROR)
        except Exception as err:
            log.error(f"Signup error: {str(err)}")
            raise HTTPException(500, detail="An internal error occurred during signup.")


@router.get("/signout")
async def signout(request: Request, response: Response):
    response.delete_cookie("token")

    if ENABLE_OAUTH_SIGNUP.value:
        encrypted_token = request.cookies.get("oauth_id_token")
        if encrypted_token:
            oauth_id_token = decrypt_token(encrypted_token) or encrypted_token
            try:
                # Use custom end_session_endpoint if configured (e.g. AWS Cognito),
                # otherwise discover from OIDC provider's well-known config.
                logout_url = OPENID_END_SESSION_ENDPOINT or None
                if not logout_url:
                    async with ClientSession() as session:
                        async with session.get(OPENID_PROVIDER_URL.value) as resp:
                            if resp.status == 200:
                                openid_data = await resp.json()
                                logout_url = openid_data.get("end_session_endpoint")
                            else:
                                raise HTTPException(
                                    status_code=resp.status,
                                    detail="Failed to fetch OpenID configuration",
                                )
                if logout_url:
                    response.delete_cookie("oauth_id_token")
                    return RedirectResponse(
                        headers=response.headers,
                        url=f"{logout_url}?id_token_hint={oauth_id_token}",
                    )
            except Exception as e:
                log.error(f"OpenID signout error: {str(e)}")
                raise HTTPException(
                    status_code=500,
                    detail="Failed to sign out from the OpenID provider.",
                )

    return {"status": True}


############################
# AddUser
############################


@router.post("/add", response_model=SigninResponse)
async def add_user(form_data: AddUserForm, user=Depends(get_admin_user)):
    if not validate_email_format(form_data.email.lower()):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail=ERROR_MESSAGES.INVALID_EMAIL_FORMAT
        )

    if Users.get_user_by_email(form_data.email.lower()):
        raise HTTPException(400, detail=ERROR_MESSAGES.EMAIL_TAKEN)

    try:
        hashed = get_password_hash(form_data.password)
        user = Auths.insert_new_auth(
            form_data.email.lower(),
            hashed,
            form_data.name,
            form_data.profile_image_url,
            form_data.role,
        )

        if user:
            token = create_token(data={"id": user.id})
            return {
                "token": token,
                "token_type": "Bearer",
                "id": user.id,
                "email": user.email,
                "name": user.name,
                "role": user.role,
                "profile_image_url": user.profile_image_url,
            }
        else:
            raise HTTPException(500, detail=ERROR_MESSAGES.CREATE_USER_ERROR)
    except Exception as err:
        log.error(f"Add user error: {str(err)}")
        raise HTTPException(
            500, detail="An internal error occurred while adding the user."
        )


############################
# GetAdminDetails
############################


@router.get("/admin/details")
async def get_admin_details(request: Request, user=Depends(get_current_user)):
    if request.app.state.config.SHOW_ADMIN_DETAILS:
        admin_email = request.app.state.config.ADMIN_EMAIL
        admin_name = None

        log.info(f"Admin details - Email: {admin_email}, Name: {admin_name}")

        if admin_email:
            admin = Users.get_user_by_email(admin_email)
            if admin:
                admin_name = admin.name
        else:
            admin = Users.get_first_user()
            if admin:
                admin_email = admin.email
                admin_name = admin.name

        return {
            "name": admin_name,
            "email": admin_email,
        }
    else:
        raise HTTPException(400, detail=ERROR_MESSAGES.ACTION_PROHIBITED)


############################
# ToggleSignUp
############################


def _strip_string(value: Optional[str]) -> str:
    return value.strip() if isinstance(value, str) else ""


def _build_oauth_redirect_uri(webui_url: Optional[str]) -> str:
    base_url = _strip_string(webui_url)
    if not base_url:
        return ""
    return f"{base_url.rstrip('/')}/oauth/oidc/callback"


def _join_oauth_allowed_domains(value) -> str:
    if isinstance(value, list):
        return ", ".join([str(item).strip() for item in value if str(item).strip()])
    value = _strip_string(value)
    return value or "*"


def _parse_oauth_allowed_domains(value: Optional[str]) -> list[str]:
    domains = [
        domain.strip()
        for domain in _strip_string(value or "*").split(",")
        if domain.strip()
    ]
    return domains or ["*"]


def _is_oidc_config_complete() -> bool:
    return bool(
        _strip_string(OAUTH_CLIENT_ID.value)
        and _strip_string(OAUTH_CLIENT_SECRET.value)
        and _strip_string(OPENID_PROVIDER_URL.value)
    )


def _is_oauth_login_enabled() -> bool:
    if ENABLE_OAUTH_LOGIN.value is not None:
        return bool(ENABLE_OAUTH_LOGIN.value)
    return _is_oidc_config_complete()


def _get_oauth_provider_name_for_admin() -> str:
    provider_name = _strip_string(OAUTH_PROVIDER_NAME.value)
    if provider_name and (provider_name != "SSO" or _is_oidc_config_complete()):
        return provider_name
    return "Authentik"


def _get_oauth_admin_config(request: Request) -> dict:
    redirect_uri = _strip_string(
        OPENID_REDIRECT_URI.value
    ) or _build_oauth_redirect_uri(request.app.state.config.WEBUI_URL)
    return {
        "ENABLE_OAUTH_LOGIN": _is_oauth_login_enabled(),
        "OAUTH_PROVIDER_NAME": _get_oauth_provider_name_for_admin(),
        "OPENID_PROVIDER_URL": _strip_string(OPENID_PROVIDER_URL.value),
        "OPENID_REDIRECT_URI": redirect_uri,
        "OAUTH_CLIENT_ID": _strip_string(OAUTH_CLIENT_ID.value),
        "OAUTH_CLIENT_SECRET": "",
        "OAUTH_CLIENT_SECRET_CONFIGURED": bool(
            _strip_string(OAUTH_CLIENT_SECRET.value)
        ),
        "OAUTH_SCOPES": _strip_string(OAUTH_SCOPES.value) or "openid email profile",
        "ENABLE_OAUTH_SIGNUP": bool(ENABLE_OAUTH_SIGNUP.value),
        "OAUTH_MERGE_ACCOUNTS_BY_EMAIL": bool(OAUTH_MERGE_ACCOUNTS_BY_EMAIL.value),
        "OAUTH_ALLOWED_DOMAINS": _join_oauth_allowed_domains(
            OAUTH_ALLOWED_DOMAINS.value
        ),
    }


def _prepare_oauth_admin_update(request: Request, form_data) -> Optional[dict]:
    if form_data.ENABLE_OAUTH_LOGIN is None:
        return None

    enabled = bool(form_data.ENABLE_OAUTH_LOGIN)
    webui_url = _strip_string(form_data.WEBUI_URL)
    provider_name = _strip_string(form_data.OAUTH_PROVIDER_NAME) or "Authentik"
    provider_url = _strip_string(form_data.OPENID_PROVIDER_URL)
    client_id = _strip_string(form_data.OAUTH_CLIENT_ID)
    client_secret = _strip_string(form_data.OAUTH_CLIENT_SECRET)
    existing_secret = _strip_string(request.app.state.config.OAUTH_CLIENT_SECRET)
    scopes = _strip_string(form_data.OAUTH_SCOPES) or "openid email profile"
    allowed_domains = _parse_oauth_allowed_domains(form_data.OAUTH_ALLOWED_DOMAINS)
    redirect_uri = _build_oauth_redirect_uri(webui_url)

    if enabled:
        if not webui_url:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="请先填写 WebUI 公开访问地址，再启用第三方登录",
            )
        if not provider_url.startswith(("http://", "https://")):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="服务发现地址不完整，请填写以 http:// 或 https:// 开头的地址",
            )
        if ".well-known/openid-configuration" not in provider_url:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="服务发现地址需要填写到 .well-known/openid-configuration",
            )
        if not client_id:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="客户端 ID 未填写",
            )
        if not client_secret and not existing_secret:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="客户端密钥未填写",
            )

    return {
        "enabled": enabled,
        "provider_name": provider_name,
        "provider_url": provider_url,
        "client_id": client_id,
        "client_secret": client_secret,
        "scopes": scopes,
        "allowed_domains": allowed_domains,
        "redirect_uri": redirect_uri,
        "enable_signup": (
            True
            if form_data.ENABLE_OAUTH_SIGNUP is None
            else bool(form_data.ENABLE_OAUTH_SIGNUP)
        ),
        "merge_accounts_by_email": (
            False
            if form_data.OAUTH_MERGE_ACCOUNTS_BY_EMAIL is None
            else bool(form_data.OAUTH_MERGE_ACCOUNTS_BY_EMAIL)
        ),
    }


def _apply_oauth_admin_update(request: Request, oauth_update: Optional[dict]) -> None:
    if oauth_update is None:
        return

    request.app.state.config.ENABLE_OAUTH_LOGIN = oauth_update["enabled"]
    request.app.state.config.OAUTH_PROVIDER_NAME = oauth_update["provider_name"]
    request.app.state.config.OPENID_PROVIDER_URL = oauth_update["provider_url"]
    request.app.state.config.OAUTH_CLIENT_ID = oauth_update["client_id"]
    if oauth_update["client_secret"]:
        request.app.state.config.OAUTH_CLIENT_SECRET = oauth_update["client_secret"]
    request.app.state.config.OPENID_REDIRECT_URI = oauth_update["redirect_uri"]
    request.app.state.config.OAUTH_SCOPES = oauth_update["scopes"]
    request.app.state.config.ENABLE_OAUTH_SIGNUP = oauth_update["enable_signup"]
    request.app.state.config.OAUTH_MERGE_ACCOUNTS_BY_EMAIL = oauth_update[
        "merge_accounts_by_email"
    ]
    request.app.state.config.OAUTH_ALLOWED_DOMAINS = oauth_update["allowed_domains"]

    load_oauth_providers()
    oauth_manager = getattr(request.app.state, "oauth_manager", None)
    if oauth_manager is not None:
        oauth_manager.refresh()


@router.get("/admin/config")
async def get_admin_config(request: Request, user=Depends(get_admin_user)):
    config = {
        "SHOW_ADMIN_DETAILS": request.app.state.config.SHOW_ADMIN_DETAILS,
        "WEBUI_URL": request.app.state.config.WEBUI_URL,
        "ENABLE_SIGNUP": request.app.state.config.ENABLE_SIGNUP,
        "ENABLE_API_KEY": request.app.state.config.ENABLE_API_KEY,
        "ENABLE_API_KEY_ENDPOINT_RESTRICTIONS": request.app.state.config.ENABLE_API_KEY_ENDPOINT_RESTRICTIONS,
        "API_KEY_ALLOWED_ENDPOINTS": request.app.state.config.API_KEY_ALLOWED_ENDPOINTS,
        "DEFAULT_USER_ROLE": request.app.state.config.DEFAULT_USER_ROLE,
        "JWT_EXPIRES_IN": request.app.state.config.JWT_EXPIRES_IN,
        "ENABLE_COMMUNITY_SHARING": request.app.state.config.ENABLE_COMMUNITY_SHARING,
        "ENABLE_CHANNELS": request.app.state.config.ENABLE_CHANNELS,
        "ENABLE_USER_WEBHOOKS": request.app.state.config.ENABLE_USER_WEBHOOKS,
    }
    config.update(_get_oauth_admin_config(request))
    return config


class AdminConfig(BaseModel):
    SHOW_ADMIN_DETAILS: bool
    WEBUI_URL: str
    ENABLE_SIGNUP: bool
    ENABLE_OAUTH_LOGIN: Optional[bool] = None
    OAUTH_PROVIDER_NAME: Optional[str] = None
    OPENID_PROVIDER_URL: Optional[str] = None
    OAUTH_CLIENT_ID: Optional[str] = None
    OAUTH_CLIENT_SECRET: Optional[str] = None
    OAUTH_SCOPES: Optional[str] = None
    ENABLE_OAUTH_SIGNUP: Optional[bool] = True
    OAUTH_MERGE_ACCOUNTS_BY_EMAIL: Optional[bool] = False
    OAUTH_ALLOWED_DOMAINS: Optional[str] = "*"
    ENABLE_API_KEY: bool
    ENABLE_API_KEY_ENDPOINT_RESTRICTIONS: bool
    API_KEY_ALLOWED_ENDPOINTS: str
    DEFAULT_USER_ROLE: str
    JWT_EXPIRES_IN: str
    ENABLE_COMMUNITY_SHARING: bool
    ENABLE_CHANNELS: bool
    ENABLE_USER_WEBHOOKS: bool


@router.post("/admin/config")
async def update_admin_config(
    request: Request, form_data: AdminConfig, user=Depends(get_admin_user)
):
    oauth_update = _prepare_oauth_admin_update(request, form_data)

    request.app.state.config.SHOW_ADMIN_DETAILS = form_data.SHOW_ADMIN_DETAILS
    request.app.state.config.WEBUI_URL = form_data.WEBUI_URL
    request.app.state.config.ENABLE_SIGNUP = form_data.ENABLE_SIGNUP

    request.app.state.config.ENABLE_API_KEY = form_data.ENABLE_API_KEY
    request.app.state.config.ENABLE_API_KEY_ENDPOINT_RESTRICTIONS = (
        form_data.ENABLE_API_KEY_ENDPOINT_RESTRICTIONS
    )
    request.app.state.config.API_KEY_ALLOWED_ENDPOINTS = (
        form_data.API_KEY_ALLOWED_ENDPOINTS
    )

    request.app.state.config.ENABLE_CHANNELS = form_data.ENABLE_CHANNELS

    if form_data.DEFAULT_USER_ROLE in ["pending", "user", "admin"]:
        request.app.state.config.DEFAULT_USER_ROLE = form_data.DEFAULT_USER_ROLE

    pattern = r"^(-1|0|(-?\d+(\.\d+)?)(ms|s|m|h|d|w))$"

    # Check if the input string matches the pattern
    if re.match(pattern, form_data.JWT_EXPIRES_IN):
        request.app.state.config.JWT_EXPIRES_IN = form_data.JWT_EXPIRES_IN

    request.app.state.config.ENABLE_COMMUNITY_SHARING = (
        form_data.ENABLE_COMMUNITY_SHARING
    )

    request.app.state.config.ENABLE_USER_WEBHOOKS = form_data.ENABLE_USER_WEBHOOKS

    _apply_oauth_admin_update(request, oauth_update)

    config = {
        "SHOW_ADMIN_DETAILS": request.app.state.config.SHOW_ADMIN_DETAILS,
        "WEBUI_URL": request.app.state.config.WEBUI_URL,
        "ENABLE_SIGNUP": request.app.state.config.ENABLE_SIGNUP,
        "ENABLE_API_KEY": request.app.state.config.ENABLE_API_KEY,
        "ENABLE_API_KEY_ENDPOINT_RESTRICTIONS": request.app.state.config.ENABLE_API_KEY_ENDPOINT_RESTRICTIONS,
        "API_KEY_ALLOWED_ENDPOINTS": request.app.state.config.API_KEY_ALLOWED_ENDPOINTS,
        "ENABLE_CHANNELS": request.app.state.config.ENABLE_CHANNELS,
        "DEFAULT_USER_ROLE": request.app.state.config.DEFAULT_USER_ROLE,
        "JWT_EXPIRES_IN": request.app.state.config.JWT_EXPIRES_IN,
        "ENABLE_COMMUNITY_SHARING": request.app.state.config.ENABLE_COMMUNITY_SHARING,
        "ENABLE_USER_WEBHOOKS": request.app.state.config.ENABLE_USER_WEBHOOKS,
    }
    config.update(_get_oauth_admin_config(request))
    return config


class LdapServerConfig(BaseModel):
    label: str
    host: str
    port: Optional[int] = None
    attribute_for_mail: str = "mail"
    attribute_for_username: str = "uid"
    app_dn: str
    app_dn_password: str
    search_base: str
    search_filters: str = ""
    use_tls: bool = True
    certificate_path: Optional[str] = None
    ciphers: Optional[str] = "ALL"


@router.get("/admin/config/ldap/server", response_model=LdapServerConfig)
async def get_ldap_server(request: Request, user=Depends(get_admin_user)):
    return {
        "label": request.app.state.config.LDAP_SERVER_LABEL,
        "host": request.app.state.config.LDAP_SERVER_HOST,
        "port": request.app.state.config.LDAP_SERVER_PORT,
        "attribute_for_mail": request.app.state.config.LDAP_ATTRIBUTE_FOR_MAIL,
        "attribute_for_username": request.app.state.config.LDAP_ATTRIBUTE_FOR_USERNAME,
        "app_dn": request.app.state.config.LDAP_APP_DN,
        "app_dn_password": request.app.state.config.LDAP_APP_PASSWORD,
        "search_base": request.app.state.config.LDAP_SEARCH_BASE,
        "search_filters": request.app.state.config.LDAP_SEARCH_FILTERS,
        "use_tls": request.app.state.config.LDAP_USE_TLS,
        "certificate_path": request.app.state.config.LDAP_CA_CERT_FILE,
        "ciphers": request.app.state.config.LDAP_CIPHERS,
    }


@router.post("/admin/config/ldap/server")
async def update_ldap_server(
    request: Request, form_data: LdapServerConfig, user=Depends(get_admin_user)
):
    required_fields = [
        "label",
        "host",
        "attribute_for_mail",
        "attribute_for_username",
        "app_dn",
        "app_dn_password",
        "search_base",
    ]
    for key in required_fields:
        value = getattr(form_data, key)
        if not value:
            raise HTTPException(400, detail=f"Required field {key} is empty")

    request.app.state.config.LDAP_SERVER_LABEL = form_data.label
    request.app.state.config.LDAP_SERVER_HOST = form_data.host
    request.app.state.config.LDAP_SERVER_PORT = form_data.port
    request.app.state.config.LDAP_ATTRIBUTE_FOR_MAIL = form_data.attribute_for_mail
    request.app.state.config.LDAP_ATTRIBUTE_FOR_USERNAME = (
        form_data.attribute_for_username
    )
    request.app.state.config.LDAP_APP_DN = form_data.app_dn
    request.app.state.config.LDAP_APP_PASSWORD = form_data.app_dn_password
    request.app.state.config.LDAP_SEARCH_BASE = form_data.search_base
    request.app.state.config.LDAP_SEARCH_FILTERS = form_data.search_filters
    request.app.state.config.LDAP_USE_TLS = form_data.use_tls
    request.app.state.config.LDAP_CA_CERT_FILE = form_data.certificate_path
    request.app.state.config.LDAP_CIPHERS = form_data.ciphers

    return {
        "label": request.app.state.config.LDAP_SERVER_LABEL,
        "host": request.app.state.config.LDAP_SERVER_HOST,
        "port": request.app.state.config.LDAP_SERVER_PORT,
        "attribute_for_mail": request.app.state.config.LDAP_ATTRIBUTE_FOR_MAIL,
        "attribute_for_username": request.app.state.config.LDAP_ATTRIBUTE_FOR_USERNAME,
        "app_dn": request.app.state.config.LDAP_APP_DN,
        "app_dn_password": request.app.state.config.LDAP_APP_PASSWORD,
        "search_base": request.app.state.config.LDAP_SEARCH_BASE,
        "search_filters": request.app.state.config.LDAP_SEARCH_FILTERS,
        "use_tls": request.app.state.config.LDAP_USE_TLS,
        "certificate_path": request.app.state.config.LDAP_CA_CERT_FILE,
        "ciphers": request.app.state.config.LDAP_CIPHERS,
    }


@router.get("/admin/config/ldap")
async def get_ldap_config(request: Request, user=Depends(get_admin_user)):
    return {"ENABLE_LDAP": request.app.state.config.ENABLE_LDAP}


class LdapConfigForm(BaseModel):
    enable_ldap: Optional[bool] = None


@router.post("/admin/config/ldap")
async def update_ldap_config(
    request: Request, form_data: LdapConfigForm, user=Depends(get_admin_user)
):
    request.app.state.config.ENABLE_LDAP = form_data.enable_ldap
    return {"ENABLE_LDAP": request.app.state.config.ENABLE_LDAP}


############################
# API Key
############################


# create api key
@router.post("/api_key", response_model=ApiKey)
async def generate_api_key(request: Request, user=Depends(get_current_user)):
    if not request.app.state.config.ENABLE_API_KEY:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail=ERROR_MESSAGES.API_KEY_CREATION_NOT_ALLOWED,
        )

    api_key = create_api_key()
    success = Users.update_user_api_key_by_id(user.id, api_key)

    if success:
        return {
            "api_key": api_key,
        }
    else:
        raise HTTPException(500, detail=ERROR_MESSAGES.CREATE_API_KEY_ERROR)


# delete api key
@router.delete("/api_key", response_model=bool)
async def delete_api_key(user=Depends(get_current_user)):
    success = Users.update_user_api_key_by_id(user.id, None)
    return success


# get api key
@router.get("/api_key", response_model=ApiKey)
async def get_api_key(user=Depends(get_current_user)):
    api_key = Users.get_user_api_key_by_id(user.id)
    if api_key:
        return {
            "api_key": api_key,
        }
    else:
        raise HTTPException(404, detail=ERROR_MESSAGES.API_KEY_NOT_FOUND)


############################
# OAuth Token Exchange (RFC 8693)
############################


class TokenExchangeForm(BaseModel):
    subject_token: str
    subject_token_type: str = "urn:ietf:params:oauth:token-type:jwt"


@router.post("/token/exchange")
async def oauth_token_exchange(form_data: TokenExchangeForm, request: Request):
    if not ENABLE_OAUTH_TOKEN_EXCHANGE:
        raise HTTPException(400, detail="Token exchange is not enabled")

    if not OAUTH_TOKEN_EXCHANGE_JWKS_URI:
        raise HTTPException(500, detail="Token exchange JWKS URI not configured")

    try:
        import jwt as pyjwt
        from jwt import PyJWKClient

        jwks_client = PyJWKClient(OAUTH_TOKEN_EXCHANGE_JWKS_URI)
        signing_key = jwks_client.get_signing_key_from_jwt(form_data.subject_token)

        decode_options = {}
        if OAUTH_TOKEN_EXCHANGE_AUDIENCE:
            decode_options["audience"] = OAUTH_TOKEN_EXCHANGE_AUDIENCE

        claims = pyjwt.decode(
            form_data.subject_token,
            signing_key.key,
            algorithms=["RS256", "ES256"],
            issuer=OAUTH_TOKEN_EXCHANGE_ISSUER or None,
            **decode_options,
        )

        email = claims.get("email", "").lower()
        if not email:
            raise HTTPException(400, detail="Token missing email claim")

        user = Users.get_user_by_email(email)
        if not user:
            raise HTTPException(403, detail="User not found")

        token = create_token(
            data={"id": user.id},
            expires_delta=parse_duration(request.app.state.config.JWT_EXPIRES_IN),
        )

        return {
            "access_token": token,
            "token_type": "Bearer",
            "issued_token_type": "urn:ietf:params:oauth:token-type:access_token",
        }
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Token exchange failed: {e}")
        raise HTTPException(400, detail="Token exchange failed")
