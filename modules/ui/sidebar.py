import os
import html
import datetime
import threading
import pandas as pd
import streamlit as st
import user_logger
from modules.services.auth_service import (
    MAX_FAILED_ATTEMPTS,
    check_server_lockout,
    is_admin_username,
    read_auth_cookie_from_context,
    record_server_failed_attempt,
    reset_server_attempts,
    revoke_daily_auth_token,
    verify_admin_password,
)
from modules.services.data_cleaner import get_dataset_month_year

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_LOGO_BUILD_LOCK = threading.Lock()
_ADMIN_LOGS_LIMIT = 500
_AUTH_LOGS_LIMIT = 300

_fragment_decorator = getattr(st, "fragment", None)
if _fragment_decorator is not None:
    @_fragment_decorator(run_every=60)
    def _render_session_heartbeat_fragment():
        """Periodically update active session duration every 60s without full page rerun."""
        try:
            user_logger.touch_session()
        except Exception:
            pass
else:
    def _render_session_heartbeat_fragment():
        pass


@st.cache_resource(show_spinner=False)
def _get_sidebar_logo_paths():
    """Resolve logo paths strictly under project root and build collapsed icon atomically once."""
    logo_dir = os.path.join(_BASE_DIR, "logo")
    logo_main_path = os.path.join(logo_dir, "logo-main.webp")
    if not os.path.exists(logo_main_path):
        logo_main_path = None

    collapsed_icon_path = os.path.join(logo_dir, "collapsed_sam_house.png")
    if not os.path.exists(collapsed_icon_path):
        with _LOGO_BUILD_LOCK:
            if not os.path.exists(collapsed_icon_path):
                sam_p = os.path.join(logo_dir, "logo-main.webp")
                house_p = os.path.join(logo_dir, "app_icon.png")
                if os.path.exists(sam_p) and os.path.exists(house_p):
                    tmp_path = f"{collapsed_icon_path}.tmp.{os.getpid()}.{threading.get_ident()}"
                    try:
                        from PIL import Image
                        with Image.open(sam_p) as sam_raw, Image.open(house_p) as house_raw:
                            sam_im = sam_raw.convert("RGBA")
                            house_im = house_raw.convert("RGBA")
                        target_h = 120
                        sam_w = max(1, int(target_h * (sam_im.width / max(1, sam_im.height))))
                        sam_res = sam_im.resize((sam_w, target_h), Image.Resampling.LANCZOS)
                        house_res = house_im.resize((target_h, target_h), Image.Resampling.LANCZOS)
                        gap = 24
                        tot_w = sam_w + gap + target_h
                        comb = Image.new("RGBA", (tot_w, target_h), (0, 0, 0, 0))
                        comb.paste(sam_res, (0, 0), sam_res)
                        comb.paste(house_res, (sam_w + gap, 0), house_res)
                        comb.save(tmp_path, "PNG")
                        os.replace(tmp_path, collapsed_icon_path)
                    except Exception:
                        try:
                            if os.path.exists(tmp_path):
                                os.remove(tmp_path)
                        except Exception:
                            pass

    icon_path = collapsed_icon_path if os.path.exists(collapsed_icon_path) else logo_main_path
    return logo_main_path, icon_path


@st.cache_resource(show_spinner=False)
def _get_secret_admin_password():
    """Read optional ADMIN_PASSWORD from Streamlit secrets once (avoiding per-rerun FileNotFound checks)."""
    try:
        if "ADMIN_PASSWORD" in st.secrets:
            return str(st.secrets["ADMIN_PASSWORD"]).strip()
    except Exception:
        pass
    return ""


def _format_ua_compact(ua_str):
    if not ua_str or ua_str == "Unknown":
        return "fa-solid fa-desktop", "ไม่ระบุอุปกรณ์"
    ua = str(ua_str).lower()
    if "iphone" in ua:
        dev, icon = "iPhone", "fa-solid fa-mobile-screen"
    elif "ipad" in ua:
        dev, icon = "iPad", "fa-solid fa-tablet-screen-button"
    elif "android" in ua:
        dev, icon = "Android", "fa-brands fa-android"
    elif "windows" in ua:
        dev, icon = "Windows", "fa-brands fa-windows"
    elif "macintosh" in ua or "mac os" in ua:
        dev, icon = "macOS", "fa-brands fa-apple"
    elif "linux" in ua:
        dev, icon = "Linux", "fa-brands fa-linux"
    else:
        dev, icon = "PC", "fa-solid fa-laptop"

    br = ""
    if "line/" in ua or " line " in ua:
        br = "LINE"
    elif "edg" in ua:
        br = "Edge"
    elif "chrome" in ua or "crios" in ua:
        br = "Chrome"
    elif "safari" in ua and "chrome" not in ua:
        br = "Safari"
    elif "firefox" in ua:
        br = "Firefox"

    return icon, f"{dev} • {br}" if br else dev


def _format_log_time(ts_str, today_str):
    if not ts_str:
        return "-"
    try:
        parts = str(ts_str).split(" ")
        d_part = parts[0]
        t_part = parts[1][:5] if len(parts) > 1 else ""
        if d_part == today_str:
            return f"วันนี้ {t_part} น."
        sub_parts = d_part.split("-")
        if len(sub_parts) == 3:
            y, m, d = sub_parts
            thai_months = ["", "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]
            m_idx = int(m) if m.isdigit() and 1 <= int(m) <= 12 else 0
            m_thai = thai_months[m_idx] if m_idx else m
            cur_y = today_str.split("-")[0]
            if y.isdigit() and y != cur_y:
                be_short = (int(y) + 543) % 100 if int(y) < 2500 else int(y) % 100
                return f"{int(d)} {m_thai} {be_short:02d} {t_part} น."
            return f"{int(d)} {m_thai} {t_part} น."
        return str(ts_str)
    except Exception:
        return str(ts_str)


def _render_admin_logs_body(is_dark_mode):
    """Renders Auth Logs and Visitor Logs inside a fragment to isolate reruns & avoid eager 99k CSV builds."""
    now_th = datetime.datetime.now(user_logger.TH_TZ)
    today_str = now_th.strftime("%Y-%m-%d")
    today_date_th = now_th.date()
    file_date_tag = now_th.strftime("%Y%m%d")

    admin_log_section = st.radio(
        "ประเภท Log",
        ["ประวัติเข้าใช้งาน (Visitor)", "ประวัติ Login/Logout (Auth)"],
        horizontal=True,
        key="admin_log_section_mode",
        label_visibility="collapsed",
    )

    if admin_log_section == "ประวัติ Login/Logout (Auth)":
        col_aq, col_ae = st.columns([0.55, 0.45])
        with col_aq:
            auth_search_q = st.text_input(
                "ค้นหา Auth Log",
                key="log_auth_search_q",
                placeholder="ค้นหาชื่อผู้ใช้ / IP...",
                label_visibility="collapsed",
            )
        with col_ae:
            auth_evt_label = st.selectbox(
                "ประเภทเหตุการณ์",
                [
                    "ทั้งหมด",
                    "login_success",
                    "token_login",
                    "login_failed",
                    "login_locked",
                    "logout",
                    "admin_login_success",
                    "admin_login_failed",
                    "admin_login_locked",
                    "admin_cache_clear",
                ],
                key="log_auth_evt_filter",
                label_visibility="collapsed",
            )

        auth_evt_param = "" if auth_evt_label == "ทั้งหมด" else auth_evt_label
        try:
            auth_logs_data = user_logger.get_auth_logs(
                query=auth_search_q or "",
                event_type=auth_evt_param,
                limit=_AUTH_LOGS_LIMIT,
            )
        except Exception:
            auth_logs_data = []

        evt_meta = {
            "login_success": ("#10b981", "rgba(16, 185, 129, 0.15)", "เข้าสู่ระบบสำเร็จ"),
            "token_login": ("#14b8a6", "rgba(20, 184, 166, 0.15)", "เข้าซ้ำด้วย Token"),
            "login_failed": ("#ef4444", "rgba(239, 68, 68, 0.15)", "รหัสผ่านผิด"),
            "login_locked": ("#f59e0b", "rgba(245, 158, 11, 0.15)", "ถูกล็อคชั่วคราว"),
            "logout": ("#60a5fa", "rgba(59, 130, 246, 0.15)", "ออกจากระบบ"),
            "admin_login_success": ("#10b981", "rgba(16, 185, 129, 0.15)", "ปลดล็อก Admin"),
            "admin_login_failed": ("#ef4444", "rgba(239, 68, 68, 0.15)", "Admin รหัสผิด"),
            "admin_login_locked": ("#f59e0b", "rgba(245, 158, 11, 0.15)", "Admin ถูกล็อค"),
            "admin_cache_clear": ("#f97316", "rgba(249, 115, 22, 0.15)", "ล้างแคชเซิร์ฟเวอร์"),
        }

        if auth_logs_data:
            card_item_bg = "rgba(255, 255, 255, 0.04)" if is_dark_mode else "#ffffff"
            card_item_border = "rgba(255, 255, 255, 0.08)" if is_dark_mode else "rgba(0, 0, 0, 0.08)"
            sub_text_color = "#94a3b8" if is_dark_mode else "#64748b"
            auth_cards = []
            for a_item in auth_logs_data:
                evt_t = str(a_item.get("event_type", "unknown"))
                c_fg, c_bg, evt_th_raw = evt_meta.get(evt_t, ("#94a3b8", "rgba(148,163,184,0.15)", evt_t))
                evt_th = html.escape(str(evt_th_raw))
                disp_u = html.escape(str(a_item.get("user_name") or a_item.get("username") or "ไม่ระบุ"))
                a_ip = html.escape(str(a_item.get("ip", "Unknown")))
                a_time = html.escape(_format_log_time(a_item.get("event_time", ""), today_str))
                a_det = html.escape(str(a_item.get("details", "") or ""))
                det_line = f'<div style="font-size: 0.65rem; color: {sub_text_color}; margin-top: 2px;">{a_det}</div>' if a_det else ""
                auth_cards.append(
                    f'<div style="background: {card_item_bg}; border: 1px solid {card_item_border}; border-radius: 8px; padding: 7px 10px; margin-bottom: 5px;">'
                    f'<div style="display: flex; justify-content: space-between; align-items: center; gap: 6px;">'
                    f'<span style="font-weight: 700; font-size: 0.79rem; color: {c_fg}; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{disp_u}</span>'
                    f'<span style="background: {c_bg}; color: {c_fg}; font-size: 0.62rem; font-weight: 700; padding: 2px 7px; border-radius: 10px; white-space: nowrap;">{evt_th}</span>'
                    f'</div>'
                    f'<div style="display: flex; justify-content: space-between; font-size: 0.67rem; color: {sub_text_color}; margin-top: 2px;">'
                    f'<span><i class="fa-regular fa-clock" style="margin-right: 3px;"></i>{a_time}</span>'
                    f'<span><i class="fa-solid fa-network-wired" style="margin-right: 3px;"></i>{a_ip}</span>'
                    f'</div>'
                    f'{det_line}'
                    f'</div>'
                )
            auth_feed = f'<div style="max-height: 280px; overflow-y: auto; padding-right: 2px; margin-top: 4px;">{"".join(auth_cards)}</div>'
            st.html(auth_feed)
        else:
            st.info("ไม่พบประวัติ Login/Logout ตามเงื่อนไขที่เลือก", icon=":material/info:")

        a_col1, a_col2 = st.columns(2)
        with a_col1:
            st.download_button(
                "ส่งออก Auth CSV",
                icon=":material/download:",
                data=lambda: user_logger.export_auth_logs_csv() or "id,event_time,event_type,username,user_name,ip,session_id,user_agent,details\n",
                file_name=f"auth_logs_{file_date_tag}.csv",
                mime="text/csv",
                width="stretch",
                key="btn_download_auth_logs",
            )
        with a_col2:
            if st.button("รีเฟรช", icon=":material/refresh:", width="stretch", key="btn_refresh_auth_logs"):
                st.rerun(scope="fragment") if _fragment_decorator is not None else st.rerun()
        return

    # Filter & Search Controls rendered FIRST so KPI cards and log feed stay 100% synchronized in the same run
    col_flt_q, col_flt_d = st.columns([0.58, 0.42])
    with col_flt_q:
        log_search_q = st.text_input(
            "ค้นหา IP / ผู้ใช้งาน",
            key="log_search_ip",
            placeholder="ค้นหาชื่อผู้ใช้ / IP / อุปกรณ์...",
            label_visibility="collapsed",
        )
    with col_flt_d:
        date_preset = st.selectbox(
            "ช่วงเวลา",
            ["ทั้งหมด", "วันนี้", "7 วันล่าสุด", "ระบุวันที่"],
            key="log_date_preset",
            label_visibility="collapsed",
        )

    date_filter = None
    start_date = None
    if date_preset == "วันนี้":
        date_filter = today_str
        ips_sub_label = "วันนี้ / ทั้งหมด"
        sess_mid_label = "วันนี้"
    elif date_preset == "7 วันล่าสุด":
        # 7 calendar days inclusive (today + 6 prior days)
        start_date = (now_th - datetime.timedelta(days=6)).strftime("%Y-%m-%d")
        ips_sub_label = "7 วัน / ทั้งหมด"
        sess_mid_label = "7 วันนี้"
    elif date_preset == "ระบุวันที่":
        custom_date = st.date_input("เลือกวันที่", value=today_date_th, key="log_custom_date")
        if custom_date:
            date_filter = custom_date.strftime("%Y-%m-%d") if isinstance(custom_date, (datetime.date, datetime.datetime)) else str(custom_date)
        ips_sub_label = "เลือก / ทั้งหมด"
        sess_mid_label = "วันที่เลือก"
    else:
        ips_sub_label = "วันนี้ / ทั้งหมด"
        sess_mid_label = "วันนี้"

    try:
        stats = user_logger.get_stats(query=log_search_q or "", date_filter=date_filter, start_date=start_date)
    except Exception:
        stats = {}

    use_period_metric = date_preset in ("7 วันล่าสุด", "ระบุวันที่", "วันนี้")
    curr_users = stats.get("period_unique_users" if use_period_metric else "today_unique_users", 0)
    total_users = stats.get("total_unique_users", 0)
    curr_ips = stats.get("period_unique_ips" if use_period_metric else "today_unique_ips", 0)
    total_ips = stats.get("total_unique_ips", stats.get("unique_ips", 0))
    mid_sessions = stats.get("period_sessions" if use_period_metric else "today_sessions", stats.get("today_visitors", 0))
    total_sessions = stats.get("total_sessions", 0)

    stat_col1_icon = "fa-solid fa-user-shield" if total_users > 0 else "fa-solid fa-network-wired"
    stat_col1_label = "ผู้ใช้" if total_users > 0 else "อุปกรณ์"
    stat_col1_curr = curr_users if total_users > 0 else curr_ips
    stat_col1_total = total_users if total_users > 0 else total_ips

    kpi_bg_ips = "rgba(59, 130, 246, 0.12)" if is_dark_mode else "rgba(59, 130, 246, 0.08)"
    kpi_border_ips = "rgba(59, 130, 246, 0.3)" if is_dark_mode else "rgba(59, 130, 246, 0.2)"
    kpi_num_ips = "#60a5fa" if is_dark_mode else "#2563eb"
    kpi_sub_ips = "#93c5fd" if is_dark_mode else "#3b82f6"

    kpi_bg_today = "rgba(249, 115, 22, 0.12)" if is_dark_mode else "rgba(249, 115, 22, 0.08)"
    kpi_border_today = "rgba(249, 115, 22, 0.3)" if is_dark_mode else "rgba(249, 115, 22, 0.2)"
    kpi_num_today = "#fb923c" if is_dark_mode else "#ea580c"

    kpi_bg_sessions = "rgba(16, 185, 129, 0.12)" if is_dark_mode else "rgba(16, 185, 129, 0.08)"
    kpi_border_sessions = "rgba(16, 185, 129, 0.3)" if is_dark_mode else "rgba(16, 185, 129, 0.2)"
    kpi_num_sessions = "#34d399" if is_dark_mode else "#059669"

    kpi_grid_html = (
        f'<div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 5px; margin: 4px 0 10px 0;">'
        f'<div style="background: {kpi_bg_ips}; border: 1px solid {kpi_border_ips}; border-radius: 8px; padding: 6px 2px; text-align: center; overflow: hidden;">'
        f'<div style="font-size: 0.65rem; color: {kpi_num_ips}; font-weight: 700; display: flex; align-items: center; justify-content: center; gap: 3px;">'
        f'<i class="{stat_col1_icon}" style="font-size: 0.62rem;"></i> {stat_col1_label}'
        f'</div>'
        f'<div style="font-size: 1.12rem; font-weight: 800; line-height: 1.25; margin: 2px 0 1px 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">'
        f'<span style="font-size: 1.15rem; font-weight: 800; color: {kpi_num_ips};">{int(stat_col1_curr):,}</span>'
        f'<span style="font-size: 0.72rem; font-weight: 600; color: #94a3b8; margin: 0 1px;">/</span>'
        f'<span style="font-size: 0.82rem; font-weight: 700; color: {kpi_sub_ips};">{int(stat_col1_total):,}</span>'
        f'</div>'
        f'<div style="font-size: 0.58rem; color: #94a3b8; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">{ips_sub_label}</div>'
        f'</div>'
        f'<div style="background: {kpi_bg_today}; border: 1px solid {kpi_border_today}; border-radius: 8px; padding: 6px 2px; text-align: center; overflow: hidden;">'
        f'<div style="font-size: 0.65rem; color: {kpi_num_today}; font-weight: 700; display: flex; align-items: center; justify-content: center; gap: 3px;">'
        f'<i class="fa-solid fa-calendar-day" style="font-size: 0.62rem;"></i> {sess_mid_label}'
        f'</div>'
        f'<div style="font-size: 1.15rem; font-weight: 800; color: {kpi_num_today}; line-height: 1.25; margin: 2px 0 1px 0;">{int(mid_sessions):,}</div>'
        f'<div style="font-size: 0.58rem; color: #94a3b8;">เซสชัน</div>'
        f'</div>'
        f'<div style="background: {kpi_bg_sessions}; border: 1px solid {kpi_border_sessions}; border-radius: 8px; padding: 6px 2px; text-align: center; overflow: hidden;">'
        f'<div style="font-size: 0.65rem; color: {kpi_num_sessions}; font-weight: 700; display: flex; align-items: center; justify-content: center; gap: 3px;">'
        f'<i class="fa-solid fa-users" style="font-size: 0.62rem;"></i> ทั้งหมด'
        f'</div>'
        f'<div style="font-size: 1.15rem; font-weight: 800; color: {kpi_num_sessions}; line-height: 1.25; margin: 2px 0 1px 0;">{int(total_sessions):,}</div>'
        f'<div style="font-size: 0.58rem; color: #94a3b8;">เซสชัน</div>'
        f'</div>'
        f'</div>'
    )
    st.html(kpi_grid_html)

    try:
        logs_data = user_logger.search_logs(
            query=log_search_q or "",
            date_filter=date_filter,
            start_date=start_date,
            limit=_ADMIN_LOGS_LIMIT,
        )
    except Exception:
        logs_data = []

    col_view_sel, col_cnt_badge = st.columns([0.55, 0.45])
    with col_view_sel:
        log_view_choice = st.radio(
            "รูปแบบมุมมอง",
            ["ฟีดการ์ด", "ตาราง"],
            horizontal=True,
            key="log_view_mode",
            label_visibility="collapsed",
        )
    with col_cnt_badge:
        cnt_label = f"{len(logs_data)}+ (ล่าสุด {_ADMIN_LOGS_LIMIT})" if len(logs_data) >= _ADMIN_LOGS_LIMIT else f"{len(logs_data)} รายการ"
        st.html(
            f'<div style="text-align: right; padding-top: 3px; font-size: 0.72rem; color: #94a3b8; font-weight: 600;">'
            f'<i class="fa-solid fa-list-check" style="color: #10b981; margin-right: 2px;"></i> {cnt_label}</div>'
        )

    if logs_data:
        if log_view_choice == "ฟีดการ์ด":
            card_item_bg = "rgba(255, 255, 255, 0.04)" if is_dark_mode else "#ffffff"
            card_item_border = "rgba(255, 255, 255, 0.08)" if is_dark_mode else "rgba(0, 0, 0, 0.08)"
            user_color = "#34d399" if is_dark_mode else "#065f46"
            badge_bg = "rgba(16, 185, 129, 0.2)" if is_dark_mode else "rgba(16, 185, 129, 0.12)"
            badge_text = "#6ee7b7" if is_dark_mode else "#047857"
            badge_border = "rgba(52, 211, 153, 0.3)" if is_dark_mode else "rgba(16, 185, 129, 0.25)"
            dur_badge_bg = "rgba(59, 130, 246, 0.18)" if is_dark_mode else "rgba(59, 130, 246, 0.10)"
            dur_badge_text = "#93c5fd" if is_dark_mode else "#1d4ed8"
            dur_badge_border = "rgba(96, 165, 250, 0.3)" if is_dark_mode else "rgba(59, 130, 246, 0.25)"
            sub_text_color = "#94a3b8" if is_dark_mode else "#64748b"

            cards_html = []
            for item in logs_data:
                ip = html.escape(str(item.get("ip", "Unknown")))
                raw_uname = str(item.get("user_name", "") or "").strip()
                display_name = html.escape(raw_uname) if raw_uname else ip
                has_domain_user = bool(raw_uname and "\\" in raw_uname)
                user_icon = "fa-solid fa-id-badge" if has_domain_user else "fa-solid fa-circle-user"
                machine_label = user_logger.format_machine_user_label(item.get("machine_user", ""), raw_uname, item.get("ip", ""))
                machine_sub_line = (
                    f'<div style="font-size: 0.65rem; color: {sub_text_color}; opacity: 0.82; padding-left: 17px; margin-top: -1px; margin-bottom: 3px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">'
                    f'ผู้ใช้เครื่อง: {html.escape(machine_label)}'
                    f'</div>'
                ) if machine_label else ""

                v_count = int(item.get("visit_count", 1) or 1)
                dur_label = html.escape(user_logger.format_duration_thai(item.get("duration_seconds", 0) or 0))
                dev_icon, dev_name = _format_ua_compact(item.get("user_agent", ""))
                last_time = html.escape(_format_log_time(item.get("last_seen", ""), today_str))
                ip_sub_line = f'<span><i class="fa-solid fa-network-wired" style="color: #60a5fa; margin-right: 3px;"></i> {ip}</span>' if (raw_uname and raw_uname != ip) else ""

                cards_html.append(
                    f'<div style="background: {card_item_bg}; border: 1px solid {card_item_border}; border-radius: 8px; padding: 7px 10px; margin-bottom: 5px; box-shadow: 0 1px 3px rgba(0,0,0,0.06);">'
                    f'<div style="display: flex; justify-content: space-between; align-items: center; gap: 6px; margin-bottom: 3px;">'
                    f'<span style="font-weight: 700; font-size: 0.82rem; color: {user_color}; font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif; display: flex; align-items: center; gap: 5px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">'
                    f'<i class="{user_icon}" style="color: #10b981; font-size: 0.76rem; flex-shrink: 0;"></i> {display_name}'
                    f'</span>'
                    f'<div style="display: flex; align-items: center; gap: 4px; flex-shrink: 0;">'
                    f'<span style="background: {dur_badge_bg}; color: {dur_badge_text}; font-size: 0.62rem; font-weight: 700; padding: 2px 7px; border-radius: 10px; border: 1px solid {dur_badge_border}; white-space: nowrap;">'
                    f'<i class="fa-regular fa-hourglass-half" style="font-size: 0.55rem; margin-right: 2px;"></i> {dur_label}'
                    f'</span>'
                    f'<span style="background: {badge_bg}; color: {badge_text}; font-size: 0.62rem; font-weight: 700; padding: 2px 7px; border-radius: 10px; border: 1px solid {badge_border}; white-space: nowrap;">'
                    f'<i class="fa-solid fa-arrow-rotate-right" style="font-size: 0.55rem; margin-right: 2px;"></i> {v_count:,} ครั้ง'
                    f'</span>'
                    f'</div>'
                    f'</div>'
                    f'{machine_sub_line}'
                    f'<div style="display: flex; justify-content: space-between; align-items: center; font-size: 0.68rem; color: {sub_text_color}; margin-top: 2px;">'
                    f'<span><i class="fa-regular fa-clock" style="color: #10b981; margin-right: 3px;"></i> {last_time}</span>'
                    f'{ip_sub_line}'
                    f'<span><i class="{dev_icon}" style="margin-right: 3px;"></i> {html.escape(dev_name)}</span>'
                    f'</div>'
                    f'</div>'
                )

            st.html(f'<div style="max-height: 280px; overflow-y: auto; padding-right: 2px; margin-top: 4px;">{"".join(cards_html)}</div>')
        else:
            df_logs_disp = pd.DataFrame(logs_data)
            for col_name, default_val in (("user_name", ""), ("machine_user", ""), ("duration_seconds", 0)):
                if col_name not in df_logs_disp.columns:
                    df_logs_disp[col_name] = default_val
            df_logs_disp["ผู้ใช้งาน"] = df_logs_disp["user_name"].fillna("").apply(lambda u: str(u).strip() or "ไม่ระบุ")
            df_logs_disp["ผู้ใช้เครื่อง"] = [
                user_logger.format_machine_user_label(m, u, ip_v) or "-"
                for m, u, ip_v in zip(df_logs_disp["machine_user"], df_logs_disp["user_name"], df_logs_disp["ip"])
            ]
            df_logs_disp["อุปกรณ์"] = [_format_ua_compact(u)[1] for u in df_logs_disp["user_agent"]]
            df_logs_disp["เข้าล่าสุด"] = [_format_log_time(t, today_str) for t in df_logs_disp["last_seen"]]
            df_logs_disp["ระยะเวลา"] = [user_logger.format_duration_thai(s or 0) for s in df_logs_disp["duration_seconds"].fillna(0)]
            df_logs_disp = df_logs_disp.rename(columns={"ip": "IP Address", "visit_count": "จำนวนครั้ง"})
            display_cols = [c for c in ["ผู้ใช้งาน", "ผู้ใช้เครื่อง", "IP Address", "เข้าล่าสุด", "ระยะเวลา", "จำนวนครั้ง", "อุปกรณ์"] if c in df_logs_disp.columns]
            st.dataframe(df_logs_disp[display_cols], width="stretch", height=240, hide_index=True)
    else:
        st.info("ไม่พบประวัติการเข้าใช้งานตามเงื่อนไขที่เลือก", icon=":material/info:")

    btn_col1, btn_col2 = st.columns(2)
    with btn_col1:
        st.download_button(
            "ส่งออก CSV",
            icon=":material/download:",
            data=lambda: user_logger.export_logs_csv() or "id,user_name,machine_user,ip,session_id,first_seen,last_seen,duration_seconds,duration_minutes,visit_count,user_agent\n",
            file_name=f"access_logs_{file_date_tag}.csv",
            mime="text/csv",
            width="stretch",
            key="btn_download_logs",
        )
    with btn_col2:
        if st.button("รีเฟรช", icon=":material/refresh:", width="stretch", key="btn_refresh_logs"):
            st.rerun(scope="fragment") if _fragment_decorator is not None else st.rerun()


if _fragment_decorator is not None:
    @_fragment_decorator
    def _render_admin_logs_fragment(is_dark_mode):
        _render_admin_logs_body(is_dark_mode)
else:
    def _render_admin_logs_fragment(is_dark_mode):
        _render_admin_logs_body(is_dark_mode)


def _render_admin_panel(is_dark_mode):
    """Renders Admin & Visitor Logs expander with auto-unlock for logged-in `admin` and fail-closed form auth."""
    with st.expander("ระบบผู้ดูแล (Admin & Visitor Logs)", icon=":material/shield_person:", expanded=False):
        logged_in_is_admin = bool(
            st.session_state.get("authenticated", False)
            and is_admin_username(st.session_state.get("auth_username"))
        )
        if logged_in_is_admin and not st.session_state.get("_admin_manual_lock", False):
            st.session_state["_log_auth"] = True
        elif "_log_auth" not in st.session_state:
            st.session_state["_log_auth"] = False

        if not st.session_state["_log_auth"]:
            with st.form("admin_panel_unlock_form", clear_on_submit=True):
                pwd_col, btn_unlock_col = st.columns([0.78, 0.22])
                with pwd_col:
                    pwd_input = st.text_input(
                        "รหัสผ่านผู้ดูแลระบบ (Admin Password)",
                        type="password",
                        key="log_viewer_password",
                        placeholder="รหัสผ่าน Admin...",
                        label_visibility="collapsed",
                    )
                with btn_unlock_col:
                    submitted_unlock = st.form_submit_button(
                        "",
                        icon=":material/lock_open:",
                        width="stretch",
                        help="ปลดล็อคระบบผู้ดูแลด้วยรหัสผ่าน admin (เดียวกับหน้า Login)",
                    )

            if submitted_unlock:
                client_ip = user_logger.get_client_ip()
                lock_key = f"{user_logger._extract_clean_ip(client_ip) or client_ip}|admin"
                remaining_lock = check_server_lockout("admin", lock_key)
                cur_user = st.session_state.get("auth_username", "")
                cur_disp = st.session_state.get("user_name", "")

                if remaining_lock > 0:
                    try:
                        user_logger.log_auth_event(
                            "admin_login_locked",
                            username=cur_user or "admin",
                            user_name=cur_disp,
                            details=f"Admin unlock blocked during {remaining_lock}s cooldown",
                        )
                    except Exception:
                        pass
                    st.error(
                        f"กรอกรหัสผ่านผู้ดูแลผิดเกินกำหนด กรุณารออีก {remaining_lock} วินาที",
                        icon=":material/lock_clock:",
                    )
                else:
                    res = verify_admin_password(
                        pwd_input,
                        secret_password=_get_secret_admin_password(),
                    )
                    if res["ok"]:
                        reset_server_attempts("admin", lock_key)
                        st.session_state["_log_auth"] = True
                        st.session_state["_admin_manual_lock"] = False
                        try:
                            user_logger.log_auth_event(
                                "admin_login_success",
                                username=cur_user or "admin",
                                user_name=cur_disp,
                                details=f"Admin panel unlocked via {res['source']}",
                            )
                        except Exception:
                            pass
                        st.rerun()
                    elif res["reason"] == "unconfigured":
                        st.warning(
                            "ยังไม่ได้ตั้งค่าบัญชี `admin` ใน `users.txt` หรือ `NOVA_ADMIN_PASSWORD` ระบบผู้ดูแลถูกปิดใช้งานเพื่อความปลอดภัย",
                            icon=":material/warning:",
                        )
                    elif res["reason"] == "empty_input":
                        st.warning("กรุณากรอกรหัสผ่านผู้ดูแลระบบ", icon=":material/info:")
                    else:
                        new_state, locked_for = record_server_failed_attempt("admin", lock_key)
                        if locked_for > 0:
                            try:
                                user_logger.log_auth_event(
                                    "admin_login_locked",
                                    username=cur_user or "admin",
                                    user_name=cur_disp,
                                    details=f"Admin panel locked {locked_for}s after {MAX_FAILED_ATTEMPTS} failed attempts",
                                )
                            except Exception:
                                pass
                            st.error(
                                f"รหัสผ่านไม่ถูกต้อง — ล็อคชั่วคราว {locked_for} วินาที",
                                icon=":material/gpp_bad:",
                            )
                        else:
                            used = int(new_state.get("count", 0))
                            left = max(0, MAX_FAILED_ATTEMPTS - used)
                            try:
                                user_logger.log_auth_event(
                                    "admin_login_failed",
                                    username=cur_user or "admin",
                                    user_name=cur_disp,
                                    details=f"Invalid admin password ({used}/{MAX_FAILED_ATTEMPTS})",
                                )
                            except Exception:
                                pass
                            st.error(
                                f"รหัสผ่านไม่ถูกต้อง (เหลือโอกาสอีก {left} ครั้ง)",
                                icon=":material/gpp_bad:",
                            )
            return

        # Unlocked Admin Controls
        col_auth_info, col_logout_btn = st.columns([0.72, 0.28])
        with col_auth_info:
            st.html(
                '<div style="display: flex; align-items: center; gap: 6px; font-size: 0.76rem; font-weight: 700; color: #10b981; padding-top: 5px;">'
                '<i class="fa-solid fa-shield-halved"></i> <span>ผู้ดูแลระบบ (Admin)</span></div>'
            )
        with col_logout_btn:
            if st.button("ล็อค", icon=":material/lock:", key="btn_log_logout", width="stretch", help="ล็อคแผงผู้ดูแลระบบ"):
                st.session_state["_log_auth"] = False
                st.session_state["_admin_manual_lock"] = True
                st.session_state["_confirm_clear_server_cache"] = False
                st.session_state.pop("log_viewer_password", None)
                st.rerun()

        st.markdown(
            """
            <div style="margin-top: 8px; margin-bottom: 6px; padding: 6px 10px; background: rgba(239, 68, 68, 0.08); border: 1px solid rgba(239, 68, 68, 0.2); border-radius: 6px;">
                <span style="font-size: 0.75rem; color: #f87171; font-weight: 700;">
                    <i class="fa-solid fa-server" style="margin-right: 4px;"></i> จัดการแคชเซิร์ฟเวอร์ (Admin Only)
                </span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if st.button(
            "ล้างแคชทั้งระบบ (Clear Server Cache)",
            icon=":material/cleaning_services:",
            key="btn_admin_clear_server_cache",
            width="stretch",
            help="ล้างแคชข้อมูลและทรัพยากรระดับเซิร์ฟเวอร์ทั้งหมด (st.cache_data และ st.cache_resource) โหลดข้อมูลใหม่จากดิสก์",
        ):
            st.session_state["_confirm_clear_server_cache"] = True

        confirm_clear = False
        if st.session_state.get("_confirm_clear_server_cache", False):
            st.warning("⚠️ การล้างแคชเซิร์ฟเวอร์จะส่งผลต่อผู้ใช้งานทุกคนบน LAN ชั่วคราว ต้องการยืนยันหรือไม่?")
            c_cf1, c_cf2 = st.columns(2)
            with c_cf1:
                confirm_clear = st.button("ยืนยันล้างแคช", type="primary", key="btn_confirm_clear_server_cache", width="stretch")
            with c_cf2:
                if st.button("ยกเลิก", key="btn_cancel_clear_server_cache", width="stretch"):
                    st.session_state["_confirm_clear_server_cache"] = False
                    st.rerun()

        if confirm_clear:
            st.session_state["_confirm_clear_server_cache"] = False
            try:
                user_logger.log_auth_event(
                    "admin_cache_clear",
                    username=st.session_state.get("auth_username", "admin"),
                    user_name=st.session_state.get("user_name", ""),
                    details="Admin cleared server-wide cache_data and cache_resource",
                )
            except Exception:
                pass
            st.cache_data.clear()
            st.cache_resource.clear()
            for _cache_k in (
                "cached_map_html_base",
                "cached_map_data_len",
                "cached_map_tmpl_mtime",
                "cached_map_data_mtime",
                "cached_map_builder_ver",
                "cached_map_payload_url",
                "cached_bubble_html_v6",
                "cached_bubble_html_v6_sig",
                "cached_bubble_html_v6_dark",
                "cached_bubble_html_v6_dark_sig",
                "_merged_df_cache",
                "_merged_df_cache_key",
                "_tab2_custom_map_cache",
                "_tab2_custom_map_cache_key",
            ):
                st.session_state.pop(_cache_k, None)
            st.toast("ล้างแคชเซิร์ฟเวอร์เรียบร้อยแล้ว กำลังโหลดข้อมูลล่าสุด...", icon=":material/check_circle:")
            st.rerun()

        st.markdown("<hr style='margin: 10px 0 12px 0; border: none; border-top: 1px solid rgba(52, 211, 153, 0.2);'>", unsafe_allow_html=True)
        _render_admin_logs_fragment(is_dark_mode)


_RESET_PRESERVED_AUTH_KEYS = frozenset({
    "_visitor_logged",
    "_nova_fallback_session_id",
    "authenticated",
    "auth_username",
    "auth_display_name",
    "user_name",
    "_auth_token_hash",
    "_auth_via_token",
    "_auth_cookie_checked",
    "_log_auth",
    "_admin_manual_lock",
    "_login_attempts",
})


def _reset_dashboard_all_callback():
    """on_click callback: resets filters, imported files, theme (Light Mode), active tab (Tab 1), and returns to Welcome screen without re-login."""
    try:
        st.query_params.clear()
    except Exception:
        pass
    next_nonce = int(st.session_state.get("_nova_reset_nonce", 0)) + 1
    for k in list(st.session_state.keys()):
        if k not in _RESET_PRESERVED_AUTH_KEYS:
            st.session_state.pop(k, None)
    st.session_state["portal_entered"] = False
    st.session_state["_nova_welcome_from_reset"] = True
    st.session_state["app_theme_mode"] = False
    st.session_state["_nova_reset_nonce"] = next_nonce
    st.session_state["_nova_just_reset_js"] = True
    st.session_state["_nova_just_reset_map"] = True


def render_sidebar(df_raw):
    """Renders the sidebar: Logo, Theme toggle, User badge/Logout, Data summary, Reset filters, and Admin Panel."""
    if st.session_state.pop("_nova_just_reset_js", False):
        st.html(
            """
            <script>
            (function() {
                function cleanWindow(win) {
                    if (!win) return;
                    try {
                        if (win.location && win.location.search) {
                            var u = new URL(win.location.href);
                            win.history.replaceState({}, '', u.origin + u.pathname);
                        }
                    } catch (_e) {}
                    try {
                        if (win.localStorage) {
                            for (var i = win.localStorage.length - 1; i >= 0; i--) {
                                var k = win.localStorage.key(i);
                                if (k && k.indexOf('nova_saved_reference_coords') === 0) {
                                    win.localStorage.removeItem(k);
                                }
                            }
                        }
                    } catch (_e) {}
                    try {
                        if (typeof win.__NOVA_TAB_LISTENER_CLEANUP__ === 'function') {
                            win.__NOVA_TAB_LISTENER_CLEANUP__();
                            win.__NOVA_TAB_LISTENER_CLEANUP__ = null;
                        }
                    } catch (_e) {}
                    try {
                        // Do NOT clear __NOVA_MAP_CACHE__ here: this script runs AFTER Welcome Screen
                        // has already wiped the old cache and prewarmed the fresh cache for Tab 2.
                        win.__NOVA_TAB5_CACHE__ = null;
                        win.__NOVA_TAB2_TOKEN_EXPIRED__ = null;
                        win.__NOVA_TAB2_ALIVE_TS__ = 0;
                    } catch (_e) {}
                    try {
                        var doc = win.document;
                        if (doc) {
                            var cards = doc.querySelectorAll('.floating-kpi-container .floating-card');
                            cards.forEach(function(card) {
                                card.classList.remove('kpi-synced-map');
                                var defVal = card.getAttribute('data-default-val');
                                var valEl = card.querySelector('.floating-card-value');
                                if (valEl && defVal !== null) valEl.innerText = defVal;
                                var badge = card.querySelector('.kpi-scope-badge');
                                if (badge) { badge.style.display = 'none'; badge.title = ''; }
                            });
                        }
                    } catch (_e) {}
                }
                cleanWindow(window);
                try {
                    if (window.parent && window.parent !== window) {
                        cleanWindow(window.parent);
                    }
                } catch (_e) {}
            })();
            </script>
            """,
            unsafe_allow_javascript=True,
        )

    logo_main_path, icon_path = _get_sidebar_logo_paths()
    if logo_main_path and hasattr(st, "logo"):
        try:
            st.logo(
                image=logo_main_path,
                icon_image=icon_path if icon_path else logo_main_path,
                size="large",
            )
        except Exception:
            pass

    with st.sidebar:
        col_side_title, col_side_theme = st.columns([0.72, 0.28])
        with col_side_title:
            st.markdown(
                """
                <div style="display: flex; flex-direction: column; justify-content: center; margin-bottom: 2px; padding-top: 2px;">
                    <div style="font-size: 1.35rem; font-weight: 800; color: #ffffff; line-height: 1.1; letter-spacing: -0.5px;">NOVA <span style="font-size: 0.72rem; font-weight: 600; color: #a7f3d0; letter-spacing: 0.2px;">v1.3</span></div>
                    <div style="font-size: 0.68rem; font-weight: 700; color: #a7f3d0; letter-spacing: 0.8px;">NPA DASHBOARD</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with col_side_theme:
            col_t1, col_t2 = st.columns([0.65, 0.35])
            with col_t1:
                is_dark_mode = st.toggle(
                    "โหมดมืด",
                    value=False,
                    key="app_theme_mode",
                    label_visibility="collapsed",
                    help="สลับระหว่างโหมดมืดและโหมดสว่าง (Dark / Light Mode)",
                )
            with col_t2:
                st.markdown(
                    f'''<div style="padding-top: 6px; font-size: 1.15rem; color: {'#34d399' if is_dark_mode else '#6ee7b7'};"><i class="fa-solid fa-moon"></i></div>''',
                    unsafe_allow_html=True,
                )

        if st.session_state.get("authenticated"):
            cur_user_display = html.escape(str(st.session_state.get("user_name") or st.session_state.get("auth_username") or "User"))
            cur_user_attr = html.escape(str(st.session_state.get("auth_username") or st.session_state.get("user_name") or ""), quote=True)
            col_user_badge, col_user_logout = st.columns([0.66, 0.34])
            with col_user_badge:
                st.markdown(
                    f"""
                    <div data-nova-user="{cur_user_attr}" style="background: rgba(16, 185, 129, 0.14); border: 1px solid rgba(52, 211, 153, 0.35); border-radius: 8px; padding: 6px 9px; margin-bottom: 6px; display: flex; align-items: center; gap: 6px; overflow: hidden;">
                        <i class="fa-solid fa-circle-user" style="color: #34d399; font-size: 0.9rem; flex-shrink: 0;"></i>
                        <span style="color: #ecfdf5; font-size: 0.77rem; font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="{cur_user_display}">{cur_user_display}</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            with col_user_logout:
                if st.button("ออก", icon=":material/logout:", key="btn_user_logout", width="stretch", help="ออกจากระบบ (Logout)"):
                    try:
                        revoke_daily_auth_token(
                            raw_token=read_auth_cookie_from_context(),
                            token_hash=st.session_state.get("_auth_token_hash"),
                        )
                    except Exception:
                        pass
                    try:
                        user_logger.log_auth_event(
                            "logout",
                            username=st.session_state.get("auth_username", ""),
                            user_name=st.session_state.get("user_name", ""),
                            details="Logout from sidebar",
                        )
                    except Exception:
                        pass
                    try:
                        st.query_params.clear()
                    except Exception:
                        pass
                    # Full session wipe ensures imported_custom_df, export buffers, and admin state never leak across users
                    st.session_state.clear()
                    st.session_state["_nova_just_logged_out"] = True
                    st.session_state["_auth_cookie_checked"] = True
                    st.rerun()

        if df_raw is not None and not df_raw.empty:
            src_name = html.escape(str(getattr(df_raw, "attrs", {}).get("source", "all_assets.parquet")))
            _, exact_date_str = get_dataset_month_year(df_raw, exclude_legal=True)
            safe_date_str = html.escape(str(exact_date_str))
            st.markdown(
                f"""
                <div style="background: rgba(255, 255, 255, 0.08); border: 1px solid rgba(110, 231, 183, 0.25); border-radius: 8px; padding: 7px 10px; margin-top: 5px; margin-bottom: 8px; font-size: 0.8rem; color: #f0fdf4; font-weight: 600;">
                    <i class="fa fa-database" style="color:#34d399;"></i> แหล่งข้อมูล: <code style="background:rgba(0,0,0,0.25); color:#a7f3d0; padding:1px 5px; border-radius:4px;">{src_name}</code><br/>
                    <span style="font-size: 0.75rem; color: #6ee7b7; font-weight: 600;"><i class="fa fa-calendar-check" style="margin-right: 3px; color:#34d399;"></i> ดึงข้อมูล: <b style="color:#ffffff;">{safe_date_str}</b></span>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.button(
            "รีเซ็ตตัวกรอง",
            icon=":material/restart_alt:",
            key="btn_reset_filters_main",
            width="stretch",
            on_click=_reset_dashboard_all_callback,
            help="รีเซ็ตตัวกรองทุกแท็บ ไฟล์นำเข้า พิกัดที่บันทึก ธีม (โหมดสว่าง) และกลับหน้า Welcome เพื่อโหลดเข้าหน้าแรกใหม่โดยไม่ต้องล็อกอินซ้ำ",
        )

        # Log first visit once per session; periodic 60s heartbeat updates active duration
        if "_visitor_logged" not in st.session_state:
            try:
                user_logger.log_visit()
            except Exception:
                pass
            st.session_state["_visitor_logged"] = True

        _render_session_heartbeat_fragment()

        st.markdown(
            """
            <div style="background: rgba(2, 44, 34, 0.85); border: 1px solid rgba(52, 211, 153, 0.35); border-radius: 9px; padding: 10px 12px; margin-top: 6px; margin-bottom: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.2);">
                <div style="display: flex; align-items: center; gap: 7px; margin-bottom: 6px;">
                    <i class="fa-solid fa-comment-dots" style="color: #34d399; font-size: 0.95rem;"></i>
                    <span style="font-weight: 700; font-size: 0.82rem; color: #ffffff;">แบบฟอร์มรับ Feedback</span>
                </div>
                <a href="https://forms.cloud.microsoft/r/TVjpiii28G" target="_blank" rel="noopener noreferrer" class="nova-feedback-link"
                   style="display: flex; flex-direction: column; gap: 3px; background: rgba(16, 185, 129, 0.16); border: 1px solid rgba(52, 211, 153, 0.45); border-radius: 7px; padding: 8px 10px; text-decoration: none !important; transition: all 0.2s ease;">
                    <div style="color: #ffffff; font-weight: 700; font-size: 0.80rem; display: flex; align-items: center; justify-content: space-between;">
                        <span>Feedback ระบบ NOVA – Fill out form</span>
                        <i class="fa-solid fa-arrow-up-right-from-square" style="color: #34d399; font-size: 0.75rem; margin-left: 6px;"></i>
                    </div>
                    <div style="color: #6ee7b7; font-size: 0.70rem; font-weight: 500; word-break: break-all; opacity: 0.95; line-height: 1.25;">
                        https://forms.cloud.microsoft/r/TVjpiii28G
                    </div>
                </a>
            </div>
            """,
            unsafe_allow_html=True,
        )

        _render_admin_panel(is_dark_mode)

    return is_dark_mode
