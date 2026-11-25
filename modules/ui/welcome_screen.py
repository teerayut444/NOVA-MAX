import os
import json
import base64
import pandas as pd
import streamlit as st
import streamlit.components.v1 as stc

import user_logger
from modules.services.auth_service import (
    MAX_FAILED_ATTEMPTS,
    authenticate_user,
    build_clear_auth_cookie_js,
    build_set_auth_cookie_js,
    check_lockout,
    check_server_lockout,
    is_admin_username,
    issue_daily_auth_token,
    load_users,
    record_failed_attempt,
    record_server_failed_attempt,
    reset_attempts,
    reset_server_attempts,
)

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@st.cache_resource(show_spinner=False)
def _load_welcome_logos_b64():
    """Load and base64-encode welcome screen logos once per process using absolute paths."""
    app_icon_b64 = ""
    icon_paths = [
        os.path.join(_BASE_DIR, "logo", "app_icon.png"),
        os.path.join(_BASE_DIR, "logo", "logo.png"),
        os.path.join(_BASE_DIR, "assets", "logo.png"),
    ]
    for p in icon_paths:
        if os.path.exists(p):
            try:
                with open(p, "rb") as f_icon:
                    app_icon_b64 = base64.b64encode(f_icon.read()).decode("utf-8")
                if app_icon_b64:
                    break
            except Exception:
                pass

    sam_logo_b64 = ""
    sam_paths = [
        os.path.join(_BASE_DIR, "logo", "logo-main.webp"),
        os.path.join(_BASE_DIR, "assets", "logo-main.webp"),
    ]
    for p in sam_paths:
        if os.path.exists(p):
            try:
                with open(p, "rb") as f_sam:
                    sam_logo_b64 = base64.b64encode(f_sam.read()).decode("utf-8")
                if sam_logo_b64:
                    break
            except Exception:
                pass

    return app_icon_b64, sam_logo_b64

from modules.services.data_loader import (
    load_properties_data,
    get_data_mtime,
    get_cache_builder_version,
    get_static_map_payload_meta,
    precompute_full_map_html,
    get_sam_project_options,
)
from modules.services.geo_service import (
    load_raw_districts_geojson,
    load_raw_subdistricts_geojson,
    get_map_icon_atlas_and_mapping,
    get_leaflet_logo_dict,
)
from modules.views.tab1_bubble import get_cached_bubble_chart_html

def update_welcome_progress(placeholder, pct, status_text):
    """Renders a sleek luxury tech progress bar with live percentage on the welcome screen."""
    placeholder.html(f"""
    <div style="width: 350px; margin: 10px auto 6px auto; text-align: center; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Noto Sans Thai', 'Outfit', sans-serif;">
        <div style="display: flex; justify-content: space-between; align-items: center; gap: 8px; font-size: 0.76rem; font-weight: 700; color: #064e3b; margin-bottom: 6px; letter-spacing: 0.2px; white-space: nowrap;">
            <span id="welcome-status-text" style="color: {'#059669' if pct >= 100 else '#475569'}; font-weight: {'700' if pct >= 100 else '600'}; overflow: hidden; text-overflow: ellipsis;">{status_text}</span>
            <span id="welcome-pct-text" style="color: #059669; font-weight: 800; flex-shrink: 0;">{pct}%</span>
        </div>
        <div style="width: 100%; height: 6px; background: rgba(16, 185, 129, 0.14); border-radius: 9999px; overflow: hidden; box-shadow: inset 0 1px 2px rgba(0,0,0,0.06);">
            <div id="welcome-progress-bar" style="width: {pct}%; height: 100%; background: linear-gradient(90deg, #10b981 0%, #059669 100%); border-radius: 9999px; transition: width 0.3s ease;"></div>
        </div>
    </div>
    """)


@st.cache_resource(show_spinner=False, max_entries=2)
def _load_prewarmer_inline_scripts(builder_ver=""):
    """Reads d3.js and map_cache_builder.js once per builder_ver so the welcome prewarmer never 404s or serves stale JS."""
    scripts = []
    for rel in ("static/d3.js", "static/map_cache_builder.js"):
        p = os.path.join(_BASE_DIR, rel)
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    scripts.append(f.read())
            except Exception:
                pass
    return "\n".join(scripts)


def _render_browser_map_prewarmer(data_mtime, builder_ver, payload_meta, is_from_reset=False):
    """Renders a hidden 0px runner that warms window.parent.__NOVA_MAP_CACHE__ from the tokenized .gz payload."""
    mtime_token = f"{payload_meta['mtime']}|{payload_meta['th_date']}"
    payload_url = payload_meta["url"]
    inline_core_js = _load_prewarmer_inline_scripts(str(builder_ver or ""))
    fast_enter_delay_ms = 500 if is_from_reset else 40
    done_enter_delay_ms = 450 if is_from_reset else 80
    ready_status_text = "✓ รีเซ็ตตัวกรองเรียบร้อย พร้อมใช้งาน" if is_from_reset else "✓ โหลดข้อมูลและแผนที่พร้อมใช้งาน"
    prewarm_html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body>
<script>
{inline_core_js}
</script>
<script>
(function () {{
  const MTIME_TOKEN = {json.dumps(mtime_token)};
  const BUILDER_VER = {json.dumps(str(builder_ver))};
  const PAYLOAD_URL = {json.dumps(payload_url)};
  const IS_FROM_RESET = {'true' if is_from_reset else 'false'};
  const FAST_ENTER_DELAY_MS = {int(fast_enter_delay_ms)};
  const DONE_ENTER_DELAY_MS = {int(done_enter_delay_ms)};
  const READY_STATUS_TEXT = {json.dumps(ready_status_text, ensure_ascii=False)};
  const STALL_TIMEOUT_MS = 25000;
  const MAX_TOTAL_TIMEOUT_MS = 90000;
  let enterRequested = false;
  let enterTimer = null;
  let stallTimer = null;
  let maxTimer = null;

  function clearTimers() {{
    if (stallTimer) {{
      clearTimeout(stallTimer);
      stallTimer = null;
    }}
    if (maxTimer) {{
      clearTimeout(maxTimer);
      maxTimer = null;
    }}
  }}

  function stopEnterRetry() {{
    if (enterTimer) {{
      clearInterval(enterTimer);
      enterTimer = null;
    }}
  }}

  window.addEventListener('pagehide', () => {{
    clearTimers();
    stopEnterRetry();
  }});
  window.addEventListener('beforeunload', () => {{
    clearTimers();
    stopEnterRetry();
  }});

  if (IS_FROM_RESET) {{
    try {{
      const pWin = window.parent;
      if (pWin) {{
        if (pWin.location && pWin.location.search) {{
          const cleanU = new URL(pWin.location.href);
          pWin.history.replaceState({{}}, '', cleanU.origin + cleanU.pathname);
        }}
        if (pWin.localStorage) {{
          for (let i = pWin.localStorage.length - 1; i >= 0; i--) {{
            const k = pWin.localStorage.key(i);
            if (k && k.indexOf('nova_saved_reference_coords') === 0) {{
              pWin.localStorage.removeItem(k);
            }}
          }}
        }}
        if (typeof pWin.__NOVA_TAB_LISTENER_CLEANUP__ === 'function') {{
          pWin.__NOVA_TAB_LISTENER_CLEANUP__();
          pWin.__NOVA_TAB_LISTENER_CLEANUP__ = null;
        }}
        pWin.__NOVA_MAP_CACHE__ = null;
        pWin.__NOVA_MAP_CACHE_PROMISE__ = null;
        pWin.__NOVA_MAP_CACHE_PROMISE_KEY__ = '';
        pWin.__NOVA_TAB5_CACHE__ = null;
        pWin.__NOVA_TAB2_TOKEN_EXPIRED__ = null;
        pWin.__NOVA_TAB2_ALIVE_TS__ = 0;
      }}
    }} catch (_e) {{}}
  }}

  function updateParentProgress(pct, text) {{
    try {{
      const pdoc = window.parent && window.parent.document;
      if (!pdoc) return;
      const barEl = pdoc.getElementById('welcome-progress-bar');
      const pctEl = pdoc.getElementById('welcome-pct-text');
      const txtEl = pdoc.getElementById('welcome-status-text');
      if (barEl) barEl.style.width = pct + '%';
      if (pctEl) pctEl.textContent = pct + '%';
      if (txtEl) {{
        txtEl.textContent = text;
        if (pct >= 100) {{
          txtEl.style.color = '#059669';
          txtEl.style.fontWeight = '700';
        }}
      }}
    }} catch (_e) {{}}
  }}

  function triggerPortalEnter() {{
    if (enterRequested) return;
    enterRequested = true;
    clearTimers();

    let clickCount = 0;
    let lastClickAt = 0;
    let sawButton = false;

    const attemptClick = () => {{
      try {{
        const pdoc = window.parent && window.parent.document;
        if (!pdoc) return;
        const btn = pdoc.querySelector('.st-key-btn_welcome_enter_portal button');
        if (!btn) {{
          // Button unmounted after navigating into main portal
          if (sawButton) stopEnterRetry();
          return;
        }}
        sawButton = true;
        if (clickCount >= 10) {{
          stopEnterRetry();
          return;
        }}
        const now = Date.now();
        if (clickCount > 0) {{
          if (now - lastClickAt < 1400) return;
          if (pdoc.querySelector('[data-testid="stStatusWidget"]')) return;
        }}
        lastClickAt = now;
        clickCount += 1;
        btn.click();
      }} catch (_e) {{}}
    }};

    attemptClick();
    enterTimer = setInterval(attemptClick, 250);
  }}

  function onTimeoutFallback(reason) {{
    if (enterRequested) return;
    console.warn('Browser map prewarm timeout fallback:', reason);
    updateParentProgress(100, '✓ กำลังเข้าสู่หน้าหลัก...');
    triggerPortalEnter();
  }}

  function bumpStallTimer() {{
    if (enterRequested) return;
    if (stallTimer) clearTimeout(stallTimer);
    stallTimer = setTimeout(() => onTimeoutFallback('stall'), STALL_TIMEOUT_MS);
  }}

  function loadScript(src) {{
    const cands = (typeof window.resolveStaticUrlCandidates === 'function' && String(src).includes('app/static'))
      ? window.resolveStaticUrlCandidates(src)
      : [src];
    return (async () => {{
      for (let i = 0; i < cands.length; i++) {{
        const ok = await new Promise((resolve) => {{
          const s = document.createElement('script');
          s.src = cands[i];
          s.async = true;
          s.onload = () => resolve(true);
          s.onerror = () => resolve(false);
          document.head.appendChild(s);
        }});
        if (ok) return true;
      }}
      return false;
    }})();
  }}

  function hasValidParentCacheFast() {{
    try {{
      if (window.NovaMapCache && typeof window.NovaMapCache.getValidParentCache === 'function') {{
        return !!window.NovaMapCache.getValidParentCache(MTIME_TOKEN, PAYLOAD_URL);
      }}
      const c = window.parent && window.parent.__NOVA_MAP_CACHE__;
      if (!(c && c.data && c.data.length > 0 && c.spatialGrid && c.projIndex && String(c.mtime || '') === MTIME_TOKEN)) {{
        return false;
      }}
      if (PAYLOAD_URL && c.payloadUrl && String(c.payloadUrl) !== String(PAYLOAD_URL)) {{
        return false;
      }}
      return true;
    }} catch (_e) {{
      return false;
    }}
  }}

  function startBasemapTilePreload() {{
    try {{
      if (window.NovaMapCache && typeof window.NovaMapCache.preloadBasemapTiles === 'function') {{
        return window.NovaMapCache.preloadBasemapTiles('google_hybrid', {{
          lon: 100.5,
          lat: 13.5,
          zoom: 5.2,
          height: 870,
          concurrency: 16
        }}).catch(() => null);
      }}
    }} catch (_e) {{}}
    return Promise.resolve(null);
  }}

  async function waitBrieflyForTiles(tilePromise, maxWaitMs) {{
    if (!tilePromise) return;
    let settled = false;
    tilePromise.then(() => {{ settled = true; }}).catch(() => {{ settled = true; }});
    await new Promise((resolve) => setTimeout(resolve, 0));
    if (settled) return;
    updateParentProgress(99, 'กำลังเตรียมภาพแผนที่เริ่มต้น (Google Hybrid)...');
    bumpStallTimer();
    await Promise.race([
      tilePromise,
      new Promise((resolve) => setTimeout(resolve, maxWaitMs))
    ]);
  }}

  bumpStallTimer();
  maxTimer = setTimeout(() => onTimeoutFallback('max_total'), MAX_TOTAL_TIMEOUT_MS);

  async function run() {{
    try {{
      if (!window.NovaMapCache) {{
        await Promise.all([
          loadScript('/app/static/d3.js'),
          loadScript('/app/static/map_cache_builder.js?v=' + encodeURIComponent(BUILDER_VER))
        ]);
      }}

      // Start warming initial Thailand basemap tiles (z=6 + z=5 fallback) in parallel immediately
      const tilePreloadPromise = startBasemapTilePreload();

      if (hasValidParentCacheFast()) {{
        await waitBrieflyForTiles(tilePreloadPromise, 1500);
        clearTimers();
        updateParentProgress(100, READY_STATUS_TEXT);
        setTimeout(triggerPortalEnter, FAST_ENTER_DELAY_MS);
        return;
      }}

      if (window.NovaMapCache && typeof window.NovaMapCache.fetchAndBuildParentCache === 'function' && PAYLOAD_URL) {{
        await window.NovaMapCache.fetchAndBuildParentCache(
          MTIME_TOKEN,
          PAYLOAD_URL,
          (pct, msg) => {{
            bumpStallTimer();
            updateParentProgress(pct, msg);
          }}
        );
      }}

      // Tiles usually finish well before the 35 MB CSV finishes parsing; wait up to 1.5s if still finishing
      await waitBrieflyForTiles(tilePreloadPromise, 1500);

      clearTimers();
      updateParentProgress(
        100,
        hasValidParentCacheFast() ? READY_STATUS_TEXT : '✓ กำลังเข้าสู่หน้าหลัก...'
      );
      setTimeout(triggerPortalEnter, DONE_ENTER_DELAY_MS);
    }} catch (err) {{
      console.warn('Browser map prewarm fallback:', err);
      clearTimers();
      updateParentProgress(100, 'กำลังเข้าสู่หน้าหลัก...');
      triggerPortalEnter();
    }}
  }}

  run();
}})();
</script>
</body>
</html>"""
    from modules.config.constants import rewrite_static_paths
    stc.html(rewrite_static_paths(prewarm_html), height=0)

def _render_welcome_login_card():
    """Renders the Light Luxury glassmorphism login form and handles authentication + user_logger."""
    _, users_err = load_users()

    with st.container(key="welcome_login_card"):
        st.html("""
        <div style="text-align: center; margin-bottom: 10px;">
            <div style="display: inline-flex; align-items: center; gap: 7px; background: rgba(16, 185, 129, 0.10); border: 1px solid rgba(16, 185, 129, 0.25); border-radius: 9999px; padding: 4px 12px; font-family: 'Noto Sans Thai', 'Outfit', sans-serif; font-size: 0.74rem; font-weight: 700; color: #047857; margin-bottom: 6px;">
                <i class="fa-solid fa-shield-halved"></i> เข้าสู่ระบบเพื่อใช้งานแดชบอร์ด
            </div>
        </div>
        """)

        if users_err == "missing_file":
            st.warning(
                "ไม่พบไฟล์ `users.txt` สำหรับตรวจสอบสิทธิ์ กรุณาสร้างไฟล์ `users.txt` ที่โฟลเดอร์หลักของโปรเจกต์ (ดูรูปแบบจาก `users.example.txt`)",
                icon=":material/warning:",
            )
        elif users_err == "empty_users":
            st.warning(
                "ไฟล์ `users.txt` ยังไม่มีรายการผู้ใช้งานที่ถูกต้อง กรุณาเพิ่ม `username:password` อย่างน้อย 1 บัญชี",
                icon=":material/warning:",
            )
        elif users_err == "read_error":
            st.error("ไม่สามารถอ่านไฟล์ `users.txt` ได้ กรุณาตรวจสอบสิทธิ์การเข้าถึงไฟล์", icon=":material/error:")

        with st.form("welcome_login_form", clear_on_submit=False):
            username_input = st.text_input(
                "ชื่อผู้ใช้งาน",
                key="welcome_login_username",
                placeholder="Username...",
            )
            password_input = st.text_input(
                "รหัสผ่าน",
                type="password",
                key="welcome_login_password",
                placeholder="Password...",
            )
            submitted = st.form_submit_button(
                "เข้าสู่ระบบ",
                icon=":material/login:",
                type="primary",
                width="stretch",
            )

        if submitted:
            attempt_state = st.session_state.get("_login_attempts")
            clean_u = (username_input or "").strip()
            client_ip = user_logger.get_client_ip()
            clean_ip = user_logger._extract_clean_ip(client_ip) or client_ip
            srv_lock_key = f"{clean_ip}|{clean_u.lower() or '__blank__'}"
            remaining_lock = max(
                check_lockout(attempt_state),
                check_server_lockout("login", srv_lock_key),
                check_server_lockout("login_ip", clean_ip or "unknown"),
            )

            if remaining_lock > 0:
                try:
                    user_logger.log_auth_event(
                        "login_locked",
                        username=clean_u,
                        details=f"Blocked during {remaining_lock}s cooldown",
                    )
                except Exception:
                    pass
                st.error(
                    f"กรอกรหัสผ่านผิดเกินกำหนด กรุณารออีก {remaining_lock} วินาทีแล้วลองใหม่อีกครั้ง",
                    icon=":material/lock_clock:",
                )
                return

            auth_res = authenticate_user(clean_u, password_input or "")
            if auth_res["ok"]:
                reset_server_attempts("login", srv_lock_key)
                reset_server_attempts("login_ip", clean_ip or "unknown")
                st.session_state["authenticated"] = True
                st.session_state["auth_username"] = auth_res["username"]
                st.session_state["auth_display_name"] = auth_res["display_name"]
                st.session_state["user_name"] = auth_res["logger_user_name"]
                st.session_state["_login_attempts"] = reset_attempts()
                st.session_state["_auth_via_token"] = False
                st.session_state["_auth_cookie_checked"] = True
                st.session_state.pop("welcome_login_password", None)
                try:
                    token_info = issue_daily_auth_token(
                        auth_res["username"],
                        ip=client_ip,
                        user_agent=user_logger.get_user_agent(),
                    )
                    if token_info:
                        st.session_state["_auth_token_hash"] = token_info["token_hash"]
                        st.session_state["_pending_auth_cookie_set"] = (
                            token_info["token"],
                            token_info["max_age"],
                        )
                except Exception:
                    pass
                if is_admin_username(auth_res["username"]):
                    st.session_state["_log_auth"] = True
                    st.session_state["_admin_manual_lock"] = False
                try:
                    user_logger.log_auth_event(
                        "login_success",
                        username=auth_res["username"],
                        user_name=auth_res["logger_user_name"],
                        details="Login via welcome screen",
                    )
                    user_logger.log_visit(user_name=auth_res["logger_user_name"])
                    st.session_state["_visitor_logged"] = True
                except Exception:
                    pass
                st.rerun()

            reason = auth_res.get("reason")
            if reason == "empty_input":
                st.warning("กรุณากรอกชื่อผู้ใช้งานและรหัสผ่านให้ครบถ้วน", icon=":material/info:")
                return
            if reason in ("missing_file", "empty_users", "read_error"):
                try:
                    user_logger.log_auth_event(
                        "login_failed",
                        username=clean_u,
                        details=f"Auth config error: {reason}",
                    )
                except Exception:
                    pass
                st.error("ไม่สามารถเข้าสู่ระบบได้เนื่องจากยังไม่ได้ตั้งค่าไฟล์ `users.txt`", icon=":material/error:")
                return

            new_state, sess_locked_for = record_failed_attempt(attempt_state)
            srv_state, srv_locked_for = record_server_failed_attempt("login", srv_lock_key)
            _ip_state, ip_locked_for = record_server_failed_attempt(
                "login_ip",
                clean_ip or "unknown",
                max_attempts=15,
                lockout_seconds=120,
            )
            locked_for = max(sess_locked_for, srv_locked_for, ip_locked_for)
            st.session_state["_login_attempts"] = new_state
            if locked_for > 0:
                try:
                    user_logger.log_auth_event(
                        "login_locked",
                        username=auth_res.get("username") or clean_u,
                        user_name=auth_res.get("logger_user_name", ""),
                        details=f"Locked {locked_for}s after {MAX_FAILED_ATTEMPTS} failed attempts",
                    )
                except Exception:
                    pass
                st.error(
                    f"ชื่อผู้ใช้งานหรือรหัสผ่านไม่ถูกต้อง — ระบบล็อคชั่วคราว {locked_for} วินาที",
                    icon=":material/gpp_bad:",
                )
            else:
                attempts_used = max(int(new_state.get("count", 0)), int(srv_state.get("count", 0)))
                attempts_left = max(0, MAX_FAILED_ATTEMPTS - attempts_used)
                try:
                    user_logger.log_auth_event(
                        "login_failed",
                        username=auth_res.get("username") or clean_u,
                        user_name=auth_res.get("logger_user_name", ""),
                        details=f"Invalid credentials ({attempts_used}/{MAX_FAILED_ATTEMPTS})",
                    )
                except Exception:
                    pass
                st.error(
                    f"ชื่อผู้ใช้งานหรือรหัสผ่านไม่ถูกต้อง (เหลือโอกาสอีก {attempts_left} ครั้ง)",
                    icon=":material/gpp_bad:",
                )

    st.html("""
    <div style="text-align: center; margin-top: 14px; margin-bottom: 10px;">
        <div style="display: inline-flex; align-items: center; gap: 7px; background: rgba(255, 255, 255, 0.70); backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px); border: 1px solid rgba(16, 185, 129, 0.22); border-radius: 9999px; padding: 6px 16px; font-family: 'Noto Sans Thai', 'Outfit', sans-serif; font-size: 0.78rem; font-weight: 600; color: #047857; box-shadow: 0 4px 14px rgba(6, 78, 59, 0.06);">
            <i class="fa-solid fa-circle-info" style="color: #059669; font-size: 0.82rem;"></i>
            <span>หากยังไม่มีบัญชีเข้าใช้งาน กรุณาติดต่อฝ่าย กอ.</span>
        </div>
    </div>
    """)


def render_welcome_screen():
    """Renders elegant light luxury Welcome Portal with login gate before data preload, 3D levitating icon, live loading progress %, and auto-enter."""
    is_authenticated = bool(st.session_state.get("authenticated", False))
    app_icon_b64, sam_logo_b64 = _load_welcome_logos_b64()

    sam_badge_html = ""
    if sam_logo_b64:
        sam_badge_html = f'''
        <div class="sam-welcome-badge" style="position: fixed; top: 22px; left: 32px; display: flex; align-items: center; gap: 14px; z-index: 999; background: transparent;">
            <img src="data:image/webp;base64,{sam_logo_b64}" style="height: 48px; width: auto; object-fit: contain; border-radius: 6px; filter: drop-shadow(0 2px 8px rgba(6, 78, 59, 0.12));" alt="SAM Logo" />
            <div style="display: flex; flex-direction: column; text-align: left; justify-content: center;">
                <span class="sam-welcome-th" style="font-family: 'Noto Sans Thai', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 1.18rem; font-weight: 800; color: #064e3b; letter-spacing: 0.2px; line-height: 1.25;">บริษัท บริหารสินทรัพย์สุขุมวิท จำกัด</span>
                <span class="sam-welcome-en" style="font-family: 'Outfit', sans-serif; font-size: 0.70rem; font-weight: 700; color: #059669; letter-spacing: 1.2px;">SUKHUMVIT ASSET MANAGEMENT</span>
            </div>
        </div>
        '''

    preload_links_html = ""
    cur_mtime = None
    builder_ver = ""
    payload_meta = None
    if is_authenticated:
        cur_mtime = get_data_mtime()
        builder_ver = get_cache_builder_version()
        payload_meta = get_static_map_payload_meta(data_mtime=cur_mtime)
        preload_links_html = ""

    from modules.config.theme import get_inlined_fa_local_css
    fa_inlined_css = get_inlined_fa_local_css()

    stage_w, stage_h, img_size, title_size, title_margin = (
        ("320px", "310px", "300px", "5.2rem", "18px 0 4px 16px")
        if is_authenticated
        else ("220px", "205px", "190px", "4.0rem", "10px 0 2px 14px")
    )
    overflow_css = "hidden" if is_authenticated else "auto"
    container_height_css = (
        "height: 100vh !important; height: 100dvh !important;"
        if is_authenticated
        else "min-height: 100vh !important; min-height: 100dvh !important; height: auto !important; padding: 24px 12px !important;"
    )

    from modules.config.constants import rewrite_static_paths
    st.html(rewrite_static_paths(f"""
<link rel="preconnect" href="https://fonts.googleapis.com" referrerpolicy="no-referrer">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin referrerpolicy="no-referrer">
<link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@800;900&family=Outfit:wght@600;700;800;900&family=Noto+Sans+Thai:wght@500;600;700;800&display=swap" rel="stylesheet" referrerpolicy="no-referrer">
<style>
@import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@800;900&family=Outfit:wght@600;700;800;900&family=Noto+Sans+Thai:wght@500;600;700;800&display=swap');
{fa_inlined_css}
header[data-testid="stHeader"] {{
    background: transparent !important;
}}
section[data-testid="stSidebar"] {{
    display: none !important;
}}

html, body {{
    min-height: 100vh !important;
    min-height: 100dvh !important;
    overflow-x: hidden !important;
    overflow-y: {overflow_css} !important;
}}

div[data-testid="stAppViewBlockContainer"],
.main .block-container,
.block-container {{
    padding: 0 !important;
    max-width: 100% !important;
    {container_height_css}
    min-height: 100vh !important;
    min-height: 100dvh !important;
    display: flex !important;
    flex-direction: column !important;
    align-items: center !important;
    justify-content: center !important;
    overflow-x: hidden !important;
    overflow-y: {overflow_css} !important;
    margin: 0 auto !important;
}}

div[data-testid="stVerticalBlock"] {{
    display: flex !important;
    flex-direction: column !important;
    align-items: center !important;
    justify-content: center !important;
    width: 100% !important;
    gap: 0 !important;
}}

body, .stApp {{
    background: radial-gradient(circle at 50% 40%, #ffffff 0%, #f4fbf7 38%, #e8f7f0 70%, #dcf3e9 100%) !important;
    min-height: 100vh !important;
    min-height: 100dvh !important;
}}

@media (max-width: 900px) {{
    .sam-welcome-badge {{
        position: static !important;
        justify-content: center !important;
        margin: 4px auto 12px auto !important;
        gap: 10px !important;
    }}
    .sam-welcome-badge img {{
        height: 36px !important;
    }}
    .sam-welcome-th {{
        font-size: 0.98rem !important;
    }}
    .sam-welcome-en {{
        font-size: 0.62rem !important;
    }}
    .nova-light-title {{
        font-size: 3.3rem !important;
        letter-spacing: 10px !important;
    }}
    .portal-stage-light {{
        width: 190px !important;
        height: 180px !important;
    }}
    .portal-house-img {{
        width: 165px !important;
        height: 165px !important;
    }}
}}

.portal-stage-light {{
    position: relative;
    width: {stage_w};
    height: {stage_h};
    margin: 0 auto;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
}}

.portal-house-img {{
    width: {img_size};
    height: {img_size};
    object-fit: contain;
    filter: drop-shadow(0 24px 40px rgba(6, 78, 59, 0.18));
    animation: floatLevitate 7s ease-in-out infinite;
    user-select: none;
    -webkit-user-drag: none;
}}

.portal-ground-shadow {{
    width: 180px;
    height: 20px;
    background: radial-gradient(ellipse at center, rgba(16, 185, 129, 0.42) 0%, rgba(5, 150, 105, 0.14) 50%, transparent 75%);
    border-radius: 50%;
    margin-top: 10px;
    animation: shadowPulse 7s ease-in-out infinite;
}}

@keyframes floatLevitate {{
    0%, 100% {{ transform: translateY(0px); }}
    50% {{ transform: translateY(-22px); }}
}}

@keyframes shadowPulse {{
    0%, 100% {{
        transform: scale(1.12);
        opacity: 0.9;
        filter: blur(5px);
    }}
    50% {{
        transform: scale(0.62);
        opacity: 0.22;
        filter: blur(9px);
    }}
}}

.nova-light-title {{
    font-family: 'Montserrat', 'Outfit', sans-serif;
    font-size: {title_size};
    font-weight: 900;
    letter-spacing: 16px;
    background: linear-gradient(180deg, #022c22 0%, #064e3b 38%, #047857 70%, #059669 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin: {title_margin};
    line-height: 1.05;
    text-align: center;
    filter: drop-shadow(0 6px 18px rgba(5, 150, 105, 0.3));
}}

.nova-light-sub {{
    font-family: 'Outfit', sans-serif;
    font-size: 0.90rem;
    font-weight: 700;
    color: #475569;
    letter-spacing: 6px;
    text-transform: uppercase;
    text-align: center;
    margin: 6px 0 10px 6px;
}}

.st-key-welcome_login_card {{
    width: min(390px, 92vw) !important;
    max-width: 390px !important;
    margin: 10px auto 0 auto !important;
    padding: 18px 22px 20px 22px !important;
    background: rgba(255, 255, 255, 0.78) !important;
    backdrop-filter: blur(18px) !important;
    -webkit-backdrop-filter: blur(18px) !important;
    border: 1px solid rgba(16, 185, 129, 0.28) !important;
    border-radius: 18px !important;
    box-shadow: 0 18px 44px rgba(6, 78, 59, 0.12), inset 0 1px 0 rgba(255, 255, 255, 0.9) !important;
}}

.st-key-welcome_login_card [data-testid="stForm"] {{
    border: none !important;
    padding: 0 !important;
    background: transparent !important;
}}

.st-key-welcome_login_card label p {{
    font-family: 'Noto Sans Thai', 'Outfit', sans-serif !important;
    font-weight: 700 !important;
    font-size: 0.84rem !important;
    color: #064e3b !important;
}}

.st-key-welcome_login_card input {{
    background: rgba(255, 255, 255, 0.94) !important;
    border-radius: 10px !important;
    color: #0f172a !important;
}}

.st-key-welcome_login_card button[kind="primaryFormSubmit"],
.st-key-welcome_login_card [data-testid="stFormSubmitButton"] button {{
    background: linear-gradient(135deg, #10b981 0%, #059669 100%) !important;
    border: none !important;
    border-radius: 10px !important;
    color: #ffffff !important;
    font-family: 'Noto Sans Thai', 'Outfit', sans-serif !important;
    font-weight: 700 !important;
    font-size: 0.94rem !important;
    padding: 0.55rem 1rem !important;
    box-shadow: 0 6px 18px rgba(5, 150, 105, 0.28) !important;
    transition: transform 0.15s ease, box-shadow 0.15s ease !important;
}}

.st-key-welcome_login_card [data-testid="stFormSubmitButton"] button:hover {{
    transform: translateY(-1px) !important;
    box-shadow: 0 10px 22px rgba(5, 150, 105, 0.36) !important;
}}

.st-key-btn_welcome_enter_portal,
div[data-testid="stElementContainer"]:has(.st-key-btn_welcome_enter_portal),
div[data-testid="stButton"]:has(.st-key-btn_welcome_enter_portal),
.st-key-welcome_prewarm_host,
div[data-testid="stElementContainer"]:has(.st-key-welcome_prewarm_host) {{
    position: fixed !important;
    bottom: -9999px !important;
    right: -9999px !important;
    width: 1px !important;
    height: 1px !important;
    overflow: hidden !important;
    opacity: 0 !important;
    z-index: -9999 !important;
}}
</style>

{preload_links_html}

{sam_badge_html}
<div style="display: flex; flex-direction: column; align-items: center; justify-content: center; width: 100%; text-align: center;">
    <div class="portal-stage-light">
        <img class="portal-house-img" src="data:image/png;base64,{app_icon_b64}" alt="NOVA House Icon" />
        <div class="portal-ground-shadow"></div>
    </div>
    <div class="nova-light-title">NOVA</div>
    <div class="nova-light-sub">NPA ASSET INTELLIGENCE</div>
</div>
"""))

    if not is_authenticated:
        if st.session_state.pop("_nova_just_logged_out", False):
            st.session_state.pop("_pending_auth_cookie_clear", None)
            st.html(
                """
                <script>
                (function() {
                    try {
                        var pWin = window.parent || window;
                        if (pWin.localStorage) {
                            for (var i = pWin.localStorage.length - 1; i >= 0; i--) {
                                var k = pWin.localStorage.key(i);
                                if (k && k.indexOf('nova_saved_reference_coords') === 0) {
                                    pWin.localStorage.removeItem(k);
                                }
                            }
                        }
                        delete pWin.__NOVA_MAP_CACHE__;
                        delete pWin.__NOVA_BOUNDARY_CACHE__;
                        if (typeof pWin.__NOVA_TAB_LISTENER_CLEANUP__ === 'function') {
                            pWin.__NOVA_TAB_LISTENER_CLEANUP__();
                            pWin.__NOVA_TAB_LISTENER_CLEANUP__ = null;
                        }
                    } catch (_e) {}
                })();
                </script>
                """ + build_clear_auth_cookie_js(),
                unsafe_allow_javascript=True,
            )
        elif st.session_state.pop("_pending_auth_cookie_clear", False):
            st.html(build_clear_auth_cookie_js(), unsafe_allow_javascript=True)
        _render_welcome_login_card()
        return

    progress_slot = st.empty()
    prewarm_slot = st.empty()
    enter_clicked = st.button("enter_portal", key="btn_welcome_enter_portal")
    if enter_clicked:
        prewarm_slot.empty()
        progress_slot.empty()
        st.session_state.pop("_nova_welcome_from_reset", None)
        st.session_state["portal_entered"] = True
        st.rerun()

    is_from_reset = bool(st.session_state.get("_nova_welcome_from_reset", False))
    pts_label = ""
    if not st.session_state.get("preload_done", False):
        import gc
        from modules.ui.kpi_header import precompute_kpi_header
        from modules.views.tab2_fragment import precompute_tab2_default_analytics

        cur_dark_mode = bool(st.session_state.get("app_theme_mode", st.session_state.get("dark_mode", False)))

        # 1. Database & Global KPI Header
        update_welcome_progress(progress_slot, 20, "กำลังโหลดฐานข้อมูลทรัพย์สิน และการ์ดสรุป KPI...")
        df_p = load_properties_data(cur_mtime)
        if df_p is not None and not df_p.empty:
            precompute_kpi_header(df_p, data_mtime=cur_mtime)

        # 2. Tab 1: 3D Glossy Bubble Chart (landing page, lightweight aggregation)
        update_welcome_progress(progress_slot, 40, "กำลังเตรียม Tab 1: กราฟภาพรวม 3D Bubble Chart...")
        if df_p is not None and not df_p.empty:
            try:
                get_cached_bubble_chart_html(
                    df_p,
                    cache_key=(cur_mtime, len(df_p), bool(cur_dark_mode)),
                    is_dark_mode=cur_dark_mode,
                )
            except Exception:
                pass

        # 3. Tab 2: Interactive Map (GeoJSON boundaries lazy-loaded on filter selection)
        pts_label = ""
        if df_p is not None and not df_p.empty:
            try:
                if 'ละติจูด' in df_p.columns and 'ลองจิจูด' in df_p.columns:
                    lat_s = pd.to_numeric(df_p['ละติจูด'], errors='coerce')
                    lon_s = pd.to_numeric(df_p['ลองจิจูด'], errors='coerce')
                    valid_cnt = int((lat_s.notna() & lon_s.notna() & lat_s.between(5, 21) & lon_s.between(97, 106)).sum())
                    pts_label = f" {valid_cnt:,} จุด"
                else:
                    pts_label = f" {len(df_p):,} จุด"
            except Exception:
                pts_label = f" {len(df_p):,} จุด"

        update_welcome_progress(progress_slot, 65, f"กำลังเตรียม Tab 2: พิกัดแผนที่{pts_label}...")
        payload_meta = precompute_full_map_html(cur_mtime, force_refresh=is_from_reset) or payload_meta
        get_map_icon_atlas_and_mapping(include_session_custom=False)
        get_leaflet_logo_dict(include_session_custom=False)
        if df_p is not None and not df_p.empty:
            get_sam_project_options(df_p, cache_key=(cur_mtime, len(df_p), None), return_meta=True)

        # 4. Tab 2: Nationwide Median Analytics & Property Table (Tabs 3, 4, 5 are lazy-loaded on tab click)
        update_welcome_progress(progress_slot, 82, "กำลังเตรียม Tab 2: ตารางวิเคราะห์ราคากลาง (Median)...")
        if df_p is not None and not df_p.empty:
            precompute_tab2_default_analytics(df_p, data_mtime=cur_mtime)

        gc.collect()
        st.session_state["preload_done"] = True

    payload_meta = payload_meta or get_static_map_payload_meta(data_mtime=cur_mtime)
    cached_map_len = int(st.session_state.get("cached_map_data_len", 0) or 0)
    if not pts_label and cached_map_len > 0:
        pts_label = f" {cached_map_len:,} จุด"
    if cached_map_len > 0 and payload_meta and os.path.exists(payload_meta["path"]):
        _pending_cookie = st.session_state.pop("_pending_auth_cookie_set", None)
        if isinstance(_pending_cookie, (tuple, list)) and len(_pending_cookie) == 2:
            st.html(
                build_set_auth_cookie_js(_pending_cookie[0], _pending_cookie[1]),
                unsafe_allow_javascript=True,
            )
        status_90 = (
            "กำลังรีเซ็ตหน้าแผนที่และตัวกรองทั้งหมด..."
            if is_from_reset
            else f"กำลังเตรียมข้อมูลแผนที่บนเบราว์เซอร์{pts_label}..."
        )
        update_welcome_progress(progress_slot, 90, status_90)
        with prewarm_slot.container(key="welcome_prewarm_host"):
            _render_browser_map_prewarmer(cur_mtime, builder_ver, payload_meta, is_from_reset=is_from_reset)
    else:
        import time
        update_welcome_progress(
            progress_slot,
            100,
            "✓ รีเซ็ตตัวกรองเรียบร้อย พร้อมใช้งาน" if is_from_reset else "✓ โหลดข้อมูลพร้อมใช้งาน",
        )
        if is_from_reset:
            time.sleep(0.45)
        prewarm_slot.empty()
        st.session_state.pop("_nova_welcome_from_reset", None)
        st.session_state["portal_entered"] = True
        st.rerun()
