"""K12 workspace re-login service.

Flow A — email OTP (default, no password stored):
  1. _platform_authorize(email) — start PKCE session
  2. _authorize_continue_login(email) — advance login with email  [login flow only]
  3. _send_passwordless_otp() — trigger OTP email               [login flow only]
  4. wait_for_code(mailbox) — poll inbox for 6-digit code
  5. validate_otp(session, device_id, code) — submit OTP, get continue_url
  6. workspace/select — POST the target workspace_id into the consent flow
  7. exchange_tokens_from_continue_url — get access/refresh/id tokens
  8. account_service.update_account — write tokens back to the account

Flow B — password + TOTP MFA (used when account.password AND account.mfa_secret are set):
  1. _platform_authorize(email) — start PKCE session
  2. _authorize_continue_login(email) — submit email
  3. _submit_password(password) — POST /api/accounts/password/verify
  4. _handle_mfa_challenge(continue_url, mfa_secret) — if MFA required, issue + verify TOTP
  5–8. same as Flow A steps 6–8
"""

from __future__ import annotations

import re
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from services.account_service import account_service
from services.register.openai_register import (
    PlatformRegistrar,
    create_mailbox,
    exchange_tokens_from_continue_url,
    validate_otp,
    wait_for_code,
    _response_json,
    auth_base,
    _headers_with_clearance,
    _header_fingerprint,
    common_headers,
    _make_trace_headers,
    request_with_local_retry,
)


_progress_store: dict[str, dict[str, Any]] = {}
_progress_lock = threading.Lock()


def _new_progress(total: int) -> str:
    pid = str(uuid.uuid4())
    with _progress_lock:
        _progress_store[pid] = {
            "total": total,
            "processed": 0,
            "success": 0,
            "failed": 0,
            "errors": [],
            "done": False,
            "error": None,
        }
    return pid


def get_progress(pid: str) -> dict[str, Any] | None:
    with _progress_lock:
        return dict(_progress_store.get(pid) or {})


def _update_progress(pid: str, *, success: bool, error: str = "") -> None:
    with _progress_lock:
        p = _progress_store.get(pid)
        if not p:
            return
        p["processed"] += 1
        if success:
            p["success"] += 1
        else:
            p["failed"] += 1
            if error:
                p["errors"].append(error)
        if p["processed"] >= p["total"]:
            p["done"] = True


def _finish_progress(pid: str, error: str = "") -> None:
    with _progress_lock:
        p = _progress_store.get(pid)
        if not p:
            return
        p["done"] = True
        if error:
            p["error"] = error


def _submit_password(registrar: PlatformRegistrar, password: str) -> dict:
    """POST password to /api/accounts/password/verify. Returns response JSON."""
    url = f"{auth_base}/api/accounts/password/verify"
    headers = _header_fingerprint(common_headers, registrar.fingerprint)
    headers["referer"] = f"{auth_base}/log-in/password"
    headers["oai-device-id"] = registrar.device_id
    headers.update(_make_trace_headers())
    headers = _headers_with_clearance(headers, url, registrar.proxy, registrar.clearance_user_agent)
    resp, error = request_with_local_retry(
        registrar.session,
        "post",
        url,
        json={"password": password},
        headers=headers,
        allow_redirects=False,
        verify=False,
    )
    if resp is None or resp.status_code != 200:
        body = ""
        try:
            body = (resp.text or "")[:300] if resp is not None else ""
        except Exception:
            pass
        raise RuntimeError(error or f"密码验证失败 HTTP {getattr(resp, 'status_code', '?')}: {body}")
    return _response_json(resp)


def _handle_mfa_challenge(registrar: PlatformRegistrar, continue_url: str, mfa_secret: str) -> str:
    """Issue and verify TOTP MFA challenge if the continue_url contains a challenge ID.

    Returns the updated continue_url after successful MFA verification.
    """
    m = re.search(r"/mfa-challenge/([a-f0-9]+)", continue_url)
    if not m:
        return continue_url
    challenge_id = m.group(1)

    def _make_headers(target_url: str) -> dict:
        h = _header_fingerprint(common_headers, registrar.fingerprint)
        h["oai-device-id"] = registrar.device_id
        h.update(_make_trace_headers())
        return _headers_with_clearance(h, target_url, registrar.proxy, registrar.clearance_user_agent)

    # Issue challenge (non-fatal — some accounts don't require this call)
    url_issue = f"{auth_base}/api/accounts/mfa/issue_challenge"
    request_with_local_retry(
        registrar.session,
        "post",
        url_issue,
        json={"id": challenge_id, "type": "totp", "force_fresh_challenge": False},
        headers=_make_headers(url_issue),
        verify=False,
    )

    # Generate TOTP code and verify
    import pyotp  # lazy import — only needed for MFA flow
    totp_code = pyotp.TOTP(mfa_secret).now()

    url_verify = f"{auth_base}/api/accounts/mfa/verify"
    resp, error = request_with_local_retry(
        registrar.session,
        "post",
        url_verify,
        json={"id": challenge_id, "type": "totp", "code": totp_code},
        headers=_make_headers(url_verify),
        verify=False,
    )
    if resp is None or resp.status_code != 200:
        body = ""
        try:
            body = (resp.text or "")[:300] if resp is not None else ""
        except Exception:
            pass
        raise RuntimeError(error or f"MFA 验证失败 HTTP {getattr(resp, 'status_code', '?')}: {body}")

    data = _response_json(resp)
    new_url = str(data.get("continue_url") or "").strip()
    return new_url or continue_url


def _select_workspace(
    registrar: PlatformRegistrar,
    workspace_id: str,
    continue_url: str,
) -> str | None:
    """POST workspace/select with the given workspace_id.

    Returns the updated continue_url (or None on failure).
    The registrar's session must already hold a valid auth-session cookie.
    """
    url = f"{auth_base}/api/accounts/workspace/select"
    headers = _header_fingerprint(common_headers, registrar.fingerprint)
    headers["referer"] = continue_url
    headers["oai-device-id"] = registrar.device_id
    headers.update(_make_trace_headers())
    headers = _headers_with_clearance(headers, url, registrar.proxy, registrar.clearance_user_agent)
    resp, _err = request_with_local_retry(
        registrar.session,
        "post",
        url,
        json={"workspace_id": workspace_id},
        headers=headers,
        allow_redirects=False,
        verify=False,
    )
    if resp is None:
        return None
    location = str((getattr(resp, "headers", {}) or {}).get("Location") or "").strip()
    if location:
        return location
    data = _response_json(resp)
    if isinstance(data, dict):
        new_url = str(data.get("continue_url") or "").strip()
        if new_url:
            return new_url
    return None


def _relogin_one(
    account: dict[str, Any],
    workspace_id: str,
    proxy: str,
    progress_id: str,
) -> None:
    """Re-login a single account and switch to the K12 workspace.

    Uses Flow B (password + TOTP MFA) when account.password and account.mfa_secret
    are both set; otherwise falls back to Flow A (email OTP).
    """
    email = str(account.get("email") or "").strip()
    access_token = str(account.get("access_token") or "").strip()
    token_label = access_token[:10] + "..." if access_token else email or "?"
    password = str(account.get("password") or "").strip()
    mfa_secret = str(account.get("mfa_secret") or "").strip()

    if not email:
        _update_progress(progress_id, success=False, error=f"{token_label}: 账号缺少 email 字段")
        return

    registrar = PlatformRegistrar(proxy)
    try:
        continue_url: str

        password = str(account.get("password") or "").strip()
        mfa_secret = str(account.get("mfa_secret") or "").strip()
        use_password_flow = bool(password and mfa_secret)

        if use_password_flow:
            # ── Flow B: password + TOTP MFA ───────────────────────────────────
            # Only tried when both password and mfa_secret are stored.
            # _authorize_continue_login reveals whether the account is in native
            # password state; if not (e.g. Microsoft OAuth), we fall through to
            # Flow A below.
            registrar._platform_authorize(email, 0, screen_hint="login_or_signup")
            continue_data = registrar._authorize_continue_login(email, 0)
            page_type = str(((continue_data.get("page") or {}).get("type") or "")).lower()

            if "password" in page_type:
                pwd_data = _submit_password(registrar, password)
                continue_url = str(pwd_data.get("continue_url") or "").strip()
                pwd_page_type = str(((pwd_data.get("page") or {}).get("type") or "")).lower()
                if "mfa" in pwd_page_type or "/mfa-challenge/" in continue_url:
                    continue_url = _handle_mfa_challenge(registrar, continue_url, mfa_secret)
                if not continue_url:
                    continue_url = f"{auth_base}/sign-in-with-chatgpt/platform/consent"

                # workspace select + token exchange follows below
                updated_url = _select_workspace(registrar, workspace_id, continue_url)
                if updated_url:
                    continue_url = updated_url

                errors: list[str] = []
                tokens = exchange_tokens_from_continue_url(
                    registrar.session,
                    registrar.device_id,
                    registrar.code_verifier,
                    continue_url,
                    proxy,
                    registrar.clearance_user_agent,
                    errors,
                    registrar.fingerprint,
                )
                if not tokens:
                    detail = "；".join(errors[-3:]) if errors else "exchange_tokens 未返回 token"
                    raise RuntimeError(f"token 换取失败: {detail}")

                new_access_token = str(tokens.get("access_token") or "").strip()
                if not new_access_token:
                    raise RuntimeError("exchange 返回的 access_token 为空")

                token_data: dict[str, Any] = {"access_token": new_access_token}
                new_refresh_token = str(tokens.get("refresh_token") or "").strip()
                new_id_token = str(tokens.get("id_token") or "").strip()
                if new_refresh_token:
                    token_data["refresh_token"] = new_refresh_token
                if new_id_token:
                    token_data["id_token"] = new_id_token

                final_token = account_service._apply_refreshed_tokens(access_token, token_data, "k12_relogin")
                account_service.update_account(final_token, {"workspace_id": workspace_id}, quiet=True)
                _update_progress(progress_id, success=True)
                return

            # Not in password state (e.g. Microsoft account) — reset and fall
            # through to Flow A so the session is clean.
            registrar._reset_auth_cookies()

        # ── Flow A: email OTP (original working logic, unchanged) ─────────────
        mailbox = create_mailbox(username=email, register_proxy=proxy)
        mailbox["address"] = email
        mailbox["_received_after"] = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
        landed = registrar._platform_authorize(email, 0, screen_hint="login_or_signup")

        resp = None
        if landed == "login":
            # Microsoft account: _authorize_continue_login + _send_passwordless_otp
            for attempt in range(2):
                if attempt:
                    registrar._reset_auth_cookies()
                    mailbox["_received_after"] = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
                    registrar._platform_authorize(email, 0, screen_hint="login_or_signup")

                registrar._authorize_continue_login(email, 0)
                mailbox["_received_after"] = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
                try:
                    registrar._send_passwordless_otp(0)
                except RuntimeError as send_err:
                    msg = str(send_err)
                    if attempt == 0 and ("invalid_state" in msg or "no longer valid" in msg):
                        continue
                    raise

                code = wait_for_code(mailbox, register_proxy=proxy)
                if not code:
                    raise RuntimeError("等待邮箱验证码超时")

                resp, err = validate_otp(registrar.session, registrar.device_id, code, registrar.fingerprint)
                if resp is not None and resp.status_code == 200:
                    break
                if attempt == 0 and registrar._is_passwordless_invalid_state(resp):
                    continue
                body = ""
                try:
                    body = (resp.text or "")[:300] if resp is not None else ""
                except Exception:
                    pass
                raise RuntimeError(err or f"OTP 验证失败 HTTP {getattr(resp, 'status_code', '?')}: {body}")
        else:
            # Native passwordless: _platform_authorize already triggered OTP email
            code = wait_for_code(mailbox, register_proxy=proxy)
            if not code:
                raise RuntimeError("等待邮箱验证码超时")
            resp, err = validate_otp(registrar.session, registrar.device_id, code, registrar.fingerprint)
            if resp is None or resp.status_code != 200:
                body = ""
                try:
                    body = (resp.text or "")[:300] if resp is not None else ""
                except Exception:
                    pass
                raise RuntimeError(err or f"OTP 验证失败 HTTP {getattr(resp, 'status_code', '?')}: {body}")

        data = _response_json(resp)
        continue_url = str(data.get("continue_url") or "").strip()
        if not continue_url:
            continue_url = f"{auth_base}/sign-in-with-chatgpt/platform/consent"

        # Step 6 — select workspace
        updated_url = _select_workspace(registrar, workspace_id, continue_url)
        if updated_url:
            continue_url = updated_url

        # Step 7 — exchange tokens
        errors: list[str] = []
        tokens = exchange_tokens_from_continue_url(
            registrar.session,
            registrar.device_id,
            registrar.code_verifier,
            continue_url,
            proxy,
            registrar.clearance_user_agent,
            errors,
            registrar.fingerprint,
        )
        if not tokens:
            detail = "；".join(errors[-3:]) if errors else "exchange_tokens 未返回 token"
            raise RuntimeError(f"token 换取失败: {detail}")

        # Step 8 — write tokens back via proper token-rotation path
        new_access_token = str(tokens.get("access_token") or "").strip()
        if not new_access_token:
            raise RuntimeError("exchange 返回的 access_token 为空")

        token_data = {"access_token": new_access_token}
        new_refresh_token = str(tokens.get("refresh_token") or "").strip()
        new_id_token = str(tokens.get("id_token") or "").strip()
        if new_refresh_token:
            token_data["refresh_token"] = new_refresh_token
        if new_id_token:
            token_data["id_token"] = new_id_token

        # _apply_refreshed_tokens correctly rotates the key in the accounts dict
        # (deletes old token key, sets alias, stores under new token).
        # update_account cannot do this — it always forces the old token as the key.
        final_token = account_service._apply_refreshed_tokens(access_token, token_data, "k12_relogin")

        # Save workspace_id against the new token key
        account_service.update_account(final_token, {"workspace_id": workspace_id}, quiet=True)
        _update_progress(progress_id, success=True)

    except Exception as exc:
        _update_progress(progress_id, success=False, error=f"{token_label}: {exc}")
    finally:
        registrar.close()


def relogin_accounts_async(
    access_tokens: list[str],
    workspace_id: str,
    proxy: str = "",
) -> str:
    """Start async re-login for a list of accounts. Returns progress_id."""
    accounts = [
        a for a in account_service.list_accounts()
        if str(a.get("access_token") or "").strip() in set(access_tokens)
    ]
    progress_id = _new_progress(len(accounts))

    if not accounts:
        _finish_progress(progress_id)
        return progress_id

    def _run():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(_relogin_one, account, workspace_id, proxy, progress_id)
                for account in accounts
            ]
            for future in futures:
                try:
                    future.result()
                except Exception:
                    pass
        _finish_progress(progress_id)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return progress_id
