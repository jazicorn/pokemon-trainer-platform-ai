"""Local admin web UI — tenant management dashboard (ROADMAP.md Phase 16).

Operator-only: this surface can see and act on every tenant's account
(deactivate, rotate keys, and — behind a re-check — their real
`platform_db_url`). That's a different trust level than the public
trade-advisor API entirely, so it's a separate app/process
(`admin_server.py`), bound to 127.0.0.1 by default, gated by its own
`ADMIN_TOKEN`, never given a public route.

Session auth is cookie-based, not header-based like the public API's
`X-API-Key` — this is a browser UI with a login form, which can't easily
attach a custom header. See `admin.sessions` for the session/CSRF design.
"""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from admin.sessions import SESSION_COOKIE_NAME, create_session, destroy_session, get_csrf_token
from api.tenants import TenantDetail, create_tenant, deactivate_tenant, get_tenant_by_id, list_tenants, rotate_api_key
from config import config

app = FastAPI(title="Tenant Admin", docs_url=None, redoc_url=None)
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def _require_admin_token_configured() -> str:
    """ADMIN_TOKEN must be set for this app to do anything meaningful — fail
    loudly at the point of use, same pattern as api.tenants._get_fernet().
    """
    token = config.admin_token
    if not token:
        raise RuntimeError(
            "ADMIN_TOKEN is not set. Generate one with:\n"
            '  uv run python -c "import secrets; print(secrets.token_urlsafe(32))"'
        )
    return token


def _session_csrf_or_redirect(request: Request) -> str:
    """GET-route dependency: a valid session, or send the browser to /login.

    Returns the session's CSRF token, for rendering into the page's forms.
    """
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    csrf_token = get_csrf_token(session_id)
    if csrf_token is None:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return csrf_token


def _require_valid_csrf(request: Request, csrf_token: Annotated[str | None, Form()] = None) -> None:
    """POST-route dependency: a valid session AND a matching CSRF token.

    403, not a redirect — this is a real rejected request (a stale/forged
    form), not a "please log in" situation the session dependency covers.
    csrf_token is Optional here (rather than a required Form field) so a
    request that omits it entirely still reaches this check and gets a
    clean 403, instead of FastAPI's own body validation intercepting it
    first with a generic 422.
    """
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    expected = get_csrf_token(session_id)
    if expected is None or csrf_token is None or not secrets.compare_digest(csrf_token, expected):
        raise HTTPException(status_code=403, detail="Invalid or missing CSRF token")


def _mask_db_url(url: str) -> str:
    """host[:port]/database only — credentials redacted, for the detail
    page's default (pre-reveal) display.
    """
    parts = urlsplit(url)
    port = f":{parts.port}" if parts.port else ""
    return f"{parts.scheme}://{parts.hostname or ''}{port}{parts.path}"


def _tenant_or_404(tenant_id: str) -> TenantDetail:
    tenant = get_tenant_by_id(tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant


@app.get("/login", response_class=HTMLResponse)
async def login_form(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "login.html", {})


@app.post("/login", response_model=None)
async def login_submit(request: Request, token: Annotated[str, Form()]) -> HTMLResponse | RedirectResponse:
    expected = _require_admin_token_configured()
    if not secrets.compare_digest(token, expected):
        return templates.TemplateResponse(request, "login.html", {"error": "Invalid admin token"}, status_code=401)

    session_id, _csrf_token = create_session()
    response = RedirectResponse(url="/", status_code=303)
    # secure=True works over this app's plain-http://127.0.0.1 default too —
    # both Chrome and Firefox treat 127.0.0.1/localhost as a "potentially
    # trustworthy origin" regardless of TLS, so Secure cookies aren't
    # dropped there. Not conditional on scheme: matches ROADMAP.md Phase
    # 16's explicit requirement, and stays correct if this is ever run
    # behind real TLS instead.
    response.set_cookie(
        SESSION_COOKIE_NAME,
        session_id,
        httponly=True,
        secure=True,
        samesite="strict",
    )
    return response


@app.post("/logout")
async def logout(request: Request) -> RedirectResponse:
    destroy_session(request.cookies.get(SESSION_COOKIE_NAME))
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response


@app.get("/", response_class=HTMLResponse)
async def tenant_list_page(
    request: Request, csrf_token: Annotated[str, Depends(_session_csrf_or_redirect)]
) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "tenant_list.html", {"tenants": list_tenants(), "csrf_token": csrf_token}
    )


@app.post("/tenants/new", response_class=HTMLResponse)
async def tenants_new(
    request: Request,
    name: Annotated[str, Form()],
    platform_db_url: Annotated[str, Form()],
    _csrf: Annotated[None, Depends(_require_valid_csrf)],
) -> HTMLResponse:
    """No connectivity validation here, deliberately — same admin-override
    trust level as scripts/provision_tenant.py (see that script's own
    docstring). Self-serve registration (POST /v1/accounts/register,
    ROADMAP.md Phase 15) is where that check lives, for callers this UI
    doesn't vouch for directly.
    """
    tenant_id, raw_key = create_tenant(name, platform_db_url)
    return templates.TemplateResponse(
        request,
        "key_reveal.html",
        {
            "heading": "Tenant created",
            "api_key": raw_key,
            "tenant_id": tenant_id,
            "tenant_name": name,
        },
    )


@app.get("/tenants/{tenant_id}", response_class=HTMLResponse)
async def tenant_detail_page(
    request: Request, tenant_id: str, csrf_token: Annotated[str, Depends(_session_csrf_or_redirect)]
) -> HTMLResponse:
    tenant = _tenant_or_404(tenant_id)
    return templates.TemplateResponse(
        request,
        "tenant_detail.html",
        {
            "tenant": tenant,
            "masked_db_url": _mask_db_url(tenant.platform_db_url),
            "revealed_db_url": None,
            "csrf_token": csrf_token,
        },
    )


@app.post("/tenants/{tenant_id}/reveal", response_class=HTMLResponse)
async def tenant_reveal(
    request: Request,
    tenant_id: str,
    admin_token: Annotated[str, Form()],
    _csrf: Annotated[None, Depends(_require_valid_csrf)],
    csrf_token: Annotated[str, Depends(_session_csrf_or_redirect)],
) -> HTMLResponse:
    """A valid session cookie alone isn't enough to see a real DSN with
    credentials — this re-checks ADMIN_TOKEN itself, a step-up check
    independent of the session.
    """
    tenant = _tenant_or_404(tenant_id)
    expected = _require_admin_token_configured()

    revealed_db_url = None
    reveal_error = None
    if secrets.compare_digest(admin_token, expected):
        revealed_db_url = tenant.platform_db_url
    else:
        reveal_error = "Invalid admin token — connection string not revealed."

    return templates.TemplateResponse(
        request,
        "tenant_detail.html",
        {
            "tenant": tenant,
            "masked_db_url": _mask_db_url(tenant.platform_db_url),
            "revealed_db_url": revealed_db_url,
            "reveal_error": reveal_error,
            "csrf_token": csrf_token,
        },
    )


@app.post("/tenants/{tenant_id}/deactivate")
async def tenant_deactivate(
    tenant_id: str,
    _csrf: Annotated[None, Depends(_require_valid_csrf)],
) -> RedirectResponse:
    _tenant_or_404(tenant_id)
    deactivate_tenant(tenant_id)
    return RedirectResponse(url=f"/tenants/{tenant_id}", status_code=303)


@app.post("/tenants/{tenant_id}/rotate-key", response_class=HTMLResponse)
async def tenant_rotate_key(
    request: Request,
    tenant_id: str,
    _csrf: Annotated[None, Depends(_require_valid_csrf)],
) -> HTMLResponse:
    tenant = _tenant_or_404(tenant_id)
    new_key = rotate_api_key(tenant_id)
    return templates.TemplateResponse(
        request,
        "key_reveal.html",
        {
            "heading": "Key rotated",
            "api_key": new_key,
            "tenant_id": tenant_id,
            "tenant_name": tenant.name,
        },
    )
