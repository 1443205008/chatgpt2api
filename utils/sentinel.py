"""OpenAI Sentinel Token (PoW) 生成与请求工具函数。

逆向自: https://sentinel.openai.com/sentinel/20260219f9f6/sdk.js

sentinel token 结构:
  {p: enforcement_token, t: turnstile_proof, c: server_challenge, id: device_id, flow: flow_name}

生成流程:
  1. 收集(伪造)浏览器指纹数据 (25项)
  2. 生成 requirements token (内部 seed, difficulty "0")
  3. POST {p, id, flow} → sentinel backend → 获取 chatReq
  4. 从 chatReq 提取 token(c), proofofwork(seed+difficulty), turnstile(dx), so
  5. 用 server seed 生成 enforcement token (p)
  6. 如有 turnstile.dx, 运行 turnstile VM 生成 proof (t)
  7. 构造 {p, t, c, id, flow}
"""
from __future__ import annotations

import base64
import json
import math
import os
import random
import subprocess
import tempfile
import time
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional

from utils.turnstile import solve_turnstile_token

if TYPE_CHECKING:
    from curl_cffi.requests import Session


# ── 常量 ──────────────────────────────────────────────────────
DEFAULT_SENTINEL_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/142.0.0.0 Safari/537.36"
)
DEFAULT_SENTINEL_SEC_CH_UA = '"Chromium";v="142", "Google Chrome";v="142", "Not/A)Brand";v="99"'

DOCUMENT_KEYS = [
    "location", "referrer", "cookie", "title", "URL", "domain", "body", "head",
    "documentElement", "scripts", "images", "forms", "links", "anchors", "readyState",
    "designMode", "dir", "lastModified", "visibilityState", "hidden", "fullscreenEnabled",
    "activeElement", "styleSheets", "fonts", "characterSet", "compatMode", "contentType",
    "implementation", "defaultView", "firstChild", "lastChild", "childElementCount",
    "textContent", "baseURI", "isConnected", "innerHTML", "outerHTML",
]
WINDOW_KEYS = [
    "location", "navigator", "history", "screen", "document", "window", "self", "top",
    "parent", "frames", "opener", "closed", "length", "name", "status", "origin",
    "performance", "crypto", "fetch", "XMLHttpRequest", "WebSocket", "localStorage",
    "sessionStorage", "console", "alert", "setTimeout", "setInterval", "clearTimeout",
    "clearInterval", "requestAnimationFrame", "postMessage", "addEventListener",
    "removeEventListener", "dispatchEvent", "getComputedStyle", "matchMedia", "open",
    "close", "focus", "blur", "scroll", "scrollX", "scrollY", "innerWidth", "innerHeight",
    "outerWidth", "outerHeight", "devicePixelRatio", "screenX", "screenY",
    "crossOriginIsolated", "isSecureContext",
]
NAVIGATOR_KEYS = [
    "userAgent", "language", "languages", "platform", "vendor", "vendorSub", "product",
    "productSub", "appName", "appVersion", "hardwareConcurrency", "deviceMemory",
    "maxTouchPoints", "cookieEnabled", "onLine", "doNotTrack", "pdfViewerEnabled",
]
SCRIPT_SRCS = [
    "https://sentinel.openai.com/sentinel/20260219f9f6/sdk.js",
    "https://cdn.oaistatic.com/assets/manifest.js",
    "https://cdn.oaistatic.com/assets/vendor.js",
    "https://cdn.oaistatic.com/assets/main.js",
    "https://cdn.oaistatic.com/assets/runtime.js",
]


# ── FNV-1a 32-bit hash ─────────────────────────────────────────
def fnv1a_32(s: str) -> str:
    """FNV-1a 32-bit hash，返回 8 位 hex（与 SDK 中一致）。"""
    h = 2166136261
    for c in s:
        h ^= ord(c)
        h = (h * 16777619) & 0xFFFFFFFF
    h ^= h >> 16
    h = (h * 2246822507) & 0xFFFFFFFF
    h ^= h >> 13
    h = (h * 3266489909) & 0xFFFFFFFF
    h ^= h >> 16
    return f"{h:08x}"


# ── 浏览器指纹 ─────────────────────────────────────────────────
def _fake_navigator_value(prop: str) -> str:
    values = {
        "userAgent": DEFAULT_SENTINEL_USER_AGENT,
        "language": "en-US",
        "languages": "en-US,en",
        "platform": "Win32",
        "vendor": "Google Inc.",
        "vendorSub": "",
        "product": "Gecko",
        "productSub": "20030107",
        "appName": "Netscape",
        "appVersion": "5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
        "hardwareConcurrency": "8",
        "deviceMemory": "8",
        "maxTouchPoints": "0",
        "cookieEnabled": "true",
        "onLine": "true",
        "doNotTrack": "null",
        "pdfViewerEnabled": "true",
    }
    return values.get(prop, "undefined")


def gather_fingerprint_data(sid: str) -> list:
    """收集浏览器指纹数据 (25 项)，与 SDK initializeAndGatherData() 一致。"""
    now_str = str(datetime.now(timezone.utc).astimezone())
    perf_now = round(time.time() * 1000 - 1_000_000 + random.uniform(1000, 5000), 1)
    time_origin = round(time.time() * 1000 - 50_000, 1)
    nav_prop = random.choice(NAVIGATOR_KEYS)
    nav_val = _fake_navigator_value(nav_prop)
    return [
        1920 + 1080,                            # [0]  screen.width + screen.height
        now_str,                                 # [1]  "" + new Date()
        4294705152,                              # [2]  performance.memory.jsHeapSizeLimit
        0,                                       # [3]  nonce (overwritten by PoW)
        DEFAULT_SENTINEL_USER_AGENT,             # [4]  navigator.userAgent
        random.choice(SCRIPT_SRCS),              # [5]  random script src
        None,                                    # [6]  data-build
        "en-US",                                 # [7]  navigator.language
        "en-US,en",                              # [8]  navigator.languages.join(",")
        0,                                       # [9]  elapsed ms (overwritten by PoW)
        f"{nav_prop}−{nav_val}",            # [10] navigator prop + "−" + value
        random.choice(DOCUMENT_KEYS),            # [11] random document key
        random.choice(WINDOW_KEYS),              # [12] random window key
        perf_now,                                # [13] performance.now()
        sid,                                     # [14] session ID (UUID)
        "",                                      # [15] URL search params keys
        8,                                       # [16] navigator.hardwareConcurrency
        time_origin,                             # [17] performance.timeOrigin
        0, 0, 0, 0, 0, 0, 0,                    # [18-24] window key checks
    ]


def encode_data(data: list) -> str:
    """JSON → UTF-8 → base64（SDK N() 函数）。"""
    return base64.b64encode(json.dumps(data, separators=(",", ":")).encode("utf-8")).decode("ascii")


# ── PoW ────────────────────────────────────────────────────────
def solve_pow(seed: str, difficulty: str, data: list, max_attempts: int = 500_000) -> str:
    """PoW 求解：找到 nonce 使 fnv1a(seed + encode(data))[:len(difficulty)] <= difficulty。"""
    start = time.perf_counter()
    try:
        for i in range(max_attempts):
            data[3] = i
            data[9] = round((time.perf_counter() - start) * 1000)
            encoded = encode_data(data)
            if fnv1a_32(seed + encoded)[:len(difficulty)] <= difficulty:
                return encoded + "~S"
    except Exception as e:
        return "gAAAAAB" + encode_data(str(e))
    return "gAAAAAB" + encode_data("e")


def generate_requirements_token(sid: str) -> str:
    """生成 requirements token（内部 seed，difficulty "0"），返回 "gAAAAAC" + payload。"""
    seed = str(random.random())
    data = gather_fingerprint_data(sid)
    return "gAAAAAC" + solve_pow(seed, "0", data)


def generate_enforcement_token(chat_req: dict, sid: str) -> str:
    """生成 enforcement token（服务端 seed+difficulty），返回 "gAAAAAB" + payload。"""
    pow_info = chat_req.get("proofofwork") or {}
    seed = str(pow_info.get("seed") or "")
    difficulty = str(pow_info.get("difficulty") or "0")
    if not seed:
        return "gAAAAAB" + encode_data("e")
    data = gather_fingerprint_data(sid)
    return "gAAAAAB" + solve_pow(seed, difficulty, data)


# ── 向后兼容：保留 SentinelTokenGenerator 类 ──────────────────
class SentinelTokenGenerator:
    """旧版 Sentinel Token 生成器（保留供向后兼容）。"""

    MAX_ATTEMPTS = 500_000
    ERROR_PREFIX = "wQ8Lk5FbGpA2NcR9dShT6gYjU7VxZ4D"

    def __init__(self, device_id: str, ua: str):
        self.device_id = device_id
        self.user_agent = ua
        self.sid = str(uuid.uuid4())

    def generate_requirements_token(self) -> str:
        return generate_requirements_token(self.sid)

    def generate_token(self, seed: str, difficulty: str) -> str:
        data = gather_fingerprint_data(self.sid)
        return "gAAAAAB" + solve_pow(seed, difficulty, data)


# ── Node.js VM（SO token 可选路径）───────────────────────────────
_UTILS_DIR = os.path.dirname(os.path.abspath(__file__))


def _run_vm_via_node(chat_req: dict, xor_key: str, vm_type: str, flow: str = "oauth_create_account") -> Optional[str]:
    """通过 Node.js 运行 sentinel SDK VM，返回 t 或 so。需要 utils/gen_token_jsdom.js。"""
    gen_script = os.path.join(_UTILS_DIR, "gen_token_jsdom.js")
    if not os.path.exists(gen_script):
        return None
    input_data = {
        "chatReq": chat_req,
        "flow": flow,
        "deviceId": str(uuid.uuid4()),
        "cachedProof": xor_key,
    }
    fd, input_file = tempfile.mkstemp(suffix=".json", prefix="sentinel_", dir=_UTILS_DIR)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(input_data, f)
        result = subprocess.run(
            ["node", gen_script, input_file],
            capture_output=True, text=True, timeout=30,
            cwd=_UTILS_DIR,
        )
        output = result.stdout
        marker = "=== JSON_OUTPUT ==="
        if marker in output:
            data = json.loads(output[output.index(marker) + len(marker):].strip())
            return data.get("so" if vm_type == "so" else "t")
        return None
    except Exception:
        return None
    finally:
        try:
            os.unlink(input_file)
        except OSError:
            pass


def run_session_observer_vm_with_key(collector_dx: str, xor_key: str, chat_req: dict = None, flow: str = "oauth_create_account") -> Optional[str]:
    """运行 session observer VM（通过 Node.js）。"""
    if chat_req:
        return _run_vm_via_node(chat_req, xor_key, "so", flow)
    return None


# ── 公开 API：同步构建函数（全项目调用） ───────────────────────────
def _sentinel_post(session: "Session", requirements_token: str, device_id: str, flow: str, ua: str, ch_ua: str) -> dict:
    """POST requirements token 到 sentinel backend，返回 chatReq dict。"""
    resp = session.post(
        "https://sentinel.openai.com/backend-api/sentinel/req",
        data=json.dumps({"p": requirements_token, "id": device_id, "flow": flow}),
        headers={
            "Content-Type": "text/plain;charset=UTF-8",
            "Referer": "https://sentinel.openai.com/backend-api/sentinel/frame.html",
            "Origin": "https://sentinel.openai.com",
            "User-Agent": ua,
            "sec-ch-ua": ch_ua,
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
        },
        timeout=20,
        verify=False,
    )
    try:
        return resp.json() if resp.text else {}
    except Exception:
        return {}


def build_sentinel_token(
    session: "Session",
    device_id: str,
    flow: str,
    *,
    user_agent: str = "",
    sec_ch_ua: str = "",
) -> tuple[str, str]:
    """请求 sentinel token，返回 (sentinel_header_value, oai_sc_cookie_value)。"""
    ua = user_agent or DEFAULT_SENTINEL_USER_AGENT
    ch_ua = sec_ch_ua or DEFAULT_SENTINEL_SEC_CH_UA
    sid = str(uuid.uuid4())

    requirements_token = generate_requirements_token(sid)
    chat_req = _sentinel_post(session, requirements_token, device_id, flow, ua, ch_ua)

    token = str(chat_req.get("token") or "").strip()
    if not token:
        fallback = json.dumps(
            {"p": requirements_token, "t": "", "c": "", "id": device_id, "flow": flow},
            separators=(",", ":"),
        )
        return fallback, ""

    p_value = generate_enforcement_token(chat_req, sid)

    turnstile_data = chat_req.get("turnstile") or {}
    so_token = ""
    if turnstile_data.get("required") and turnstile_data.get("dx"):
        so_token = solve_turnstile_token(str(turnstile_data["dx"]), requirements_token) or ""
        if not so_token:
            raise RuntimeError("sentinel_so_token_failed")

    sentinel_value = json.dumps(
        {"p": p_value, "t": so_token, "c": token, "id": device_id, "flow": flow},
        separators=(",", ":"),
    )
    return sentinel_value, "0" + token


def build_sentinel_with_so_token(
    session: "Session",
    device_id: str,
    flow: str,
    *,
    user_agent: str = "",
    sec_ch_ua: str = "",
) -> tuple[str, str, str]:
    """请求 sentinel token，返回 (sentinel_header_value, so_token_header_value, oai_sc_cookie_value)。"""
    ua = user_agent or DEFAULT_SENTINEL_USER_AGENT
    ch_ua = sec_ch_ua or DEFAULT_SENTINEL_SEC_CH_UA
    sid = str(uuid.uuid4())

    requirements_token = generate_requirements_token(sid)
    chat_req = _sentinel_post(session, requirements_token, device_id, flow, ua, ch_ua)

    token = str(chat_req.get("token") or "").strip()
    if not token:
        fallback = json.dumps(
            {"p": requirements_token, "t": "", "c": "", "id": device_id, "flow": flow},
            separators=(",", ":"),
        )
        return fallback, "", ""

    p_value = generate_enforcement_token(chat_req, sid)

    # Turnstile proof (t 字段)
    turnstile_data = chat_req.get("turnstile") or {}
    so_token = ""
    if turnstile_data.get("required") and turnstile_data.get("dx"):
        time.sleep(5.0)  # 模拟浏览器采集延迟（对齐官方 SDK 行为）
        so_token = solve_turnstile_token(str(turnstile_data["dx"]), requirements_token) or ""
        if not so_token:
            raise RuntimeError("sentinel_so_token_failed")

    sentinel_value = json.dumps(
        {"p": p_value, "t": so_token, "c": token, "id": device_id, "flow": flow},
        separators=(",", ":"),
    )

    # SO token（session observer，可选）
    so_header = ""
    so_info = chat_req.get("so") or {}
    if so_info.get("required") and so_info.get("collector_dx"):
        so_result = run_session_observer_vm_with_key(
            so_info["collector_dx"], requirements_token, chat_req, flow
        )
        if so_result:
            so_header = json.dumps(
                {"so": so_result, "c": token, "id": device_id, "flow": flow},
                separators=(",", ":"),
            )

    return sentinel_value, so_header, "0" + token
