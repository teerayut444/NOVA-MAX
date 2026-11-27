# Tab 2 Interactive Map View - Tokenized Static Payload, Single-Pass Placeholder Escaping & Per-Session Custom Cache
import gzip
import html
import json
import math
import os
import re
import pandas as pd
import streamlit as st
import streamlit.components.v1 as stc

from modules.services.geo_service import (
    get_boundary_geojson_features,
    get_map_icon_atlas_and_mapping,
    get_leaflet_logo_dict,
)
from modules.services.data_loader import (
    _replace_placeholders_single_pass,
    _resolve_root_file,
    _safe_json_inline,
    _today_th_str,
    build_map_payload_from_df,
    find_property_row_by_code,
    get_base_map_html,
    get_cache_builder_version,
    get_data_mtime,
    get_data_mtime_token,
    get_precomputed_map_payload,
    get_static_map_payload_meta,
    get_valid_coord_properties_data,
    precompute_full_map_html,
)
from modules.views.tab2_batch_reference import render_tab2_batch_reference_panel
from modules.views.tab2_fragment import render_tab2_reference_analytics_fragment


def _build_custom_company_colors_str():
    """Serializes user-imported custom company colors safely for embedding inside a JS object literal."""
    imported_cos = st.session_state.get("imported_custom_companies", {})
    default_imp_color = _safe_json_inline(str(st.session_state.get("imported_custom_color", "#6366f1")))
    custom_color_entries = [f'"ไฟล์นำเข้า": {default_imp_color}']
    if isinstance(imported_cos, dict):
        for co_n, co_inf in imported_cos.items():
            if isinstance(co_inf, dict) and "color" in co_inf:
                custom_color_entries.append(
                    f'{_safe_json_inline(str(co_n))}: {_safe_json_inline(str(co_inf["color"]))}'
                )
    custom_co = st.session_state.get("imported_custom_company")
    custom_color = st.session_state.get("imported_custom_color", "#6366f1")
    if (
        custom_co
        and custom_co != "ไฟล์นำเข้า"
        and custom_co != "(ตามข้อมูลในไฟล์)"
        and (not isinstance(imported_cos, dict) or custom_co not in imported_cos)
    ):
        custom_color_entries.append(
            f'{_safe_json_inline(str(custom_co))}: {_safe_json_inline(str(custom_color))}'
        )
    return ",\n        ".join(custom_color_entries)


def _safe_js_inner_str(val):
    """Safely encode arbitrary strings for embedding inside a JS double-quoted string literal."""
    encoded = json.dumps(str(val or ""), ensure_ascii=False)[1:-1]
    return (
        encoded.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("'", "\\u0027")
        .replace("/", "\\/")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _safe_float_str(val, default=""):
    if val is None or val == "":
        return default
    try:
        f = float(val)
        if not math.isfinite(f):
            return default
        return f"{f:.6f}".rstrip("0").rstrip(".") or "0"
    except (ValueError, TypeError):
        return default


def _is_valid_thai_coord(lat_val, lon_val):
    try:
        la = float(lat_val)
        lo = float(lon_val)
        return math.isfinite(la) and math.isfinite(lo) and (5.0 <= la <= 21.0) and (97.0 <= lo <= 106.0)
    except (ValueError, TypeError):
        return False


def _inject_dynamic_map_placeholders(
    html_str,
    *,
    is_dark_mode,
    active_ref_lat=None,
    active_ref_lon=None,
    active_ref_radius=5.0,
    search_prop_id="",
    effective_provs=None,
    effective_dists=None,
    effective_subdists=None,
    current_prov_str="",
    payload_url="",
    invariant_runtime=False,
):
    """Injects runtime session/filter placeholders atomically in a single regex pass.

    When invariant_runtime=True (live render path), keeps filter/pin placeholders invariant across
    in-map clicks so Streamlit never reloads the iframe (client JS reads initial state from URL).
    """
    body_cls = "dark-theme" if is_dark_mode else ""
    day_str = _today_th_str()
    mtime_tok = f"{get_data_mtime_token(get_data_mtime())}|{day_str}"

    if invariant_runtime:
        replacements = {
            "BODY_CLASS_PLACEHOLDER": body_cls,
            "INIT_REF_LAT_PLACEHOLDER": "",
            "INIT_REF_LON_PLACEHOLDER": "",
            "INIT_RADIUS_PLACEHOLDER": "5.0",
            "INIT_REF_ID_PLACEHOLDER": "",
            "INIT_PRICE_REF_ID_PLACEHOLDER": "",
            "INIT_COMPARE_IDS_PLACEHOLDER": "[]",
            "BOUNDARY_GEOJSON_PLACEHOLDER": "null",
            "CURRENT_PROV_PLACEHOLDER": "",
            "CUSTOM_COMPANY_COLORS_PLACEHOLDER": _build_custom_company_colors_str(),
            "DATA_MTIME_PLACEHOLDER": _safe_js_inner_str(mtime_tok),
            "CACHE_BUILDER_VER_PLACEHOLDER": _safe_js_inner_str(get_cache_builder_version()),
            "MAP_PAYLOAD_URL_PLACEHOLDER": _safe_js_inner_str(payload_url),
        }
    else:
        init_ref_id = str(
            st.session_state.get("tab2_search_prop_id") or st.query_params.get("map_ref_id") or search_prop_id or ""
        ).strip()
        init_price_ref_id = str(
            st.session_state.get("tab2_price_center_id") or st.query_params.get("map_price_ref_id") or ""
        ).strip()
        active_comp_ids = st.session_state.get("tab2_compare_ids", [])
        comp_ids_json = _safe_json_inline(active_comp_ids)

        boundary_obj = (
            get_boundary_geojson_features(effective_provs, effective_dists, effective_subdists)
            if effective_provs
            else None
        )
        boundary_json = _safe_json_inline(boundary_obj) if boundary_obj else "null"

        replacements = {
            "BODY_CLASS_PLACEHOLDER": body_cls,
            "INIT_REF_LAT_PLACEHOLDER": _safe_float_str(active_ref_lat, ""),
            "INIT_REF_LON_PLACEHOLDER": _safe_float_str(active_ref_lon, ""),
            "INIT_RADIUS_PLACEHOLDER": _safe_float_str(active_ref_radius, "5.0"),
            "INIT_REF_ID_PLACEHOLDER": _safe_js_inner_str(init_ref_id),
            "INIT_PRICE_REF_ID_PLACEHOLDER": _safe_js_inner_str(init_price_ref_id),
            "INIT_COMPARE_IDS_PLACEHOLDER": comp_ids_json,
            "BOUNDARY_GEOJSON_PLACEHOLDER": boundary_json,
            "CURRENT_PROV_PLACEHOLDER": _safe_js_inner_str(current_prov_str),
            "CUSTOM_COMPANY_COLORS_PLACEHOLDER": _build_custom_company_colors_str(),
            "DATA_MTIME_PLACEHOLDER": _safe_js_inner_str(mtime_tok),
            "CACHE_BUILDER_VER_PLACEHOLDER": _safe_js_inner_str(get_cache_builder_version()),
            "MAP_PAYLOAD_URL_PLACEHOLDER": _safe_js_inner_str(payload_url),
        }
    from modules.config.constants import rewrite_static_paths
    return rewrite_static_paths(_replace_placeholders_single_pass(html_str, replacements))


def _reload_tab2_map_callback():
    """on_click callback: refreshes map token/payload and remounts only the Tab 2 iframe without clearing filters or leaving Tab 2."""
    st.session_state["_tab2_map_reload_nonce"] = int(st.session_state.get("_tab2_map_reload_nonce", 0)) + 1
    st.session_state["_tab2_force_map_reload_js"] = True
    st.session_state["_tab2_force_refresh_payload"] = True
    st.session_state["_tab2_show_reload_toast"] = True
    for _k in (
        "cached_map_html_base",
        "cached_map_payload_url",
        "_tab2_custom_map_cache",
    ):
        st.session_state.pop(_k, None)


def _render_tab2_map_auto_heal_watcher():
    """Lightweight parent-window watcher that auto-recovers Tab 2 if its iframe crashes/turns blank or reports a 404 expired token."""
    st.html(
        """
        <script>
        (function() {
            var win = window;
            if (win.__NOVA_TAB2_AUTOHEAL_CLEANUP__) {
                try { win.__NOVA_TAB2_AUTOHEAL_CLEANUP__(); } catch (_e) {}
                win.__NOVA_TAB2_AUTOHEAL_CLEANUP__ = null;
            }

            var MAX_RELOADS_PER_MIN = 2;
            var COOLDOWN_MS = 12000;
            var MOUNT_GRACE_MS = 10000;
            var HEARTBEAT_STALE_MS = 30000;

            if (!Array.isArray(win.__NOVA_TAB2_AUTOHEAL_HISTORY__)) {
                win.__NOVA_TAB2_AUTOHEAL_HISTORY__ = [];
            }

            var trackedIframe = null;
            var trackedSrcdocLen = -1;
            var trackedMountedAt = Date.now();
            var tabVisibleSince = 0;

            function getMapStageAndPanel() {
                var stage = document.querySelector('.st-key-tab2_map_stage') || document.querySelector('.st-key-tab_map');
                if (!stage) return { stage: null, panel: null, visible: false };
                var panel = stage.closest('[role="tabpanel"]');
                if (panel) {
                    if (panel.hasAttribute('hidden') || panel.getAttribute('aria-hidden') === 'true') {
                        return { stage: stage, panel: panel, visible: false };
                    }
                    var pr = panel.getBoundingClientRect();
                    if (pr.width <= 0 || pr.height <= 0) {
                        return { stage: stage, panel: panel, visible: false };
                    }
                }
                return { stage: stage, panel: panel, visible: true };
            }

            function findMapIframe(stage) {
                if (!stage) return null;
                var iframes = stage.querySelectorAll('iframe');
                for (var i = 0; i < iframes.length; i++) {
                    var r = iframes[i].getBoundingClientRect();
                    if (r.height >= 200 && r.width >= 200) return iframes[i];
                }
                return null;
            }

            function canTriggerAutoHeal(now) {
                if (document.visibilityState === 'hidden') return false;
                if (document.querySelector('[data-testid="stStatusWidget"]')) return false;
                var hist = win.__NOVA_TAB2_AUTOHEAL_HISTORY__.filter(function(ts) { return now - ts < 60000; });
                win.__NOVA_TAB2_AUTOHEAL_HISTORY__ = hist;
                if (hist.length >= MAX_RELOADS_PER_MIN) return false;
                var lastAt = hist.length ? hist[hist.length - 1] : 0;
                if (lastAt && (now - lastAt) < COOLDOWN_MS) return false;
                return true;
            }

            function triggerAutoHeal(reason) {
                var now = Date.now();
                if (!canTriggerAutoHeal(now)) return false;
                var btn = document.querySelector('.st-key-btn_tab2_reload_map button');
                if (!btn) return false;
                win.__NOVA_TAB2_AUTOHEAL_HISTORY__.push(now);
                win.__NOVA_TAB2_TOKEN_EXPIRED__ = null;
                win.__NOVA_TAB2_ALIVE_TS__ = 0;
                try {
                    win.__NOVA_MAP_CACHE__ = null;
                    win.__NOVA_MAP_CACHE_PROMISE__ = null;
                    win.__NOVA_MAP_CACHE_PROMISE_KEY__ = '';
                } catch (_e) {}
                console.warn('[NOVA Tab2 Auto-Heal] Reloading map iframe:', reason);
                btn.click();
                return true;
            }

            function checkMapHealth() {
                try {
                    var info = getMapStageAndPanel();
                    if (!info.visible || document.visibilityState === 'hidden') {
                        tabVisibleSince = 0;
                        return;
                    }
                    var now = Date.now();
                    if (!tabVisibleSince) tabVisibleSince = now;

                    // 1. Explicit token-expired (HTTP 404/410) or unrecovered WebGL loss signal from map iframe
                    var exp = win.__NOVA_TAB2_TOKEN_EXPIRED__;
                    if (exp && exp.ts && (now - exp.ts) < 60000) {
                        triggerAutoHeal(exp.reason || 'token_expired');
                        return;
                    }

                    // 2. Inspect the live map iframe for crash / sad-face / blank document
                    var iframe = findMapIframe(info.stage);
                    if (!iframe) return;

                    var curLen = (iframe.getAttribute('srcdoc') || '').length;
                    if (iframe !== trackedIframe || curLen !== trackedSrcdocLen) {
                        trackedIframe = iframe;
                        trackedSrcdocLen = curLen;
                        trackedMountedAt = now;
                        return;
                    }

                    if ((now - trackedMountedAt) < MOUNT_GRACE_MS) return;

                    var iframeDeadReason = '';
                    try {
                        var cw = iframe.contentWindow;
                        var cd = iframe.contentDocument;
                        var href = cw && cw.location ? String(cw.location.href || '') : '';
                        if (href.indexOf('chrome-error://') === 0 || href.indexOf('about:neterror') === 0) {
                            iframeDeadReason = 'iframe_error_page';
                        } else if (!cd) {
                            iframeDeadReason = 'iframe_no_document';
                        } else if (cd.readyState === 'complete' && !cd.getElementById('map')) {
                            iframeDeadReason = 'iframe_missing_map_dom';
                        } else if (cd.readyState === 'complete') {
                            var loaderEl = cd.getElementById('loader');
                            var loaderHidden = !loaderEl || loaderEl.style.display === 'none';
                            var mapEl = cd.getElementById('map');
                            var glCanvas = mapEl && mapEl.querySelector('canvas');
                            var aliveTs = Number(win.__NOVA_TAB2_ALIVE_TS__ || 0);
                            if (
                                aliveTs > 0 &&
                                loaderHidden &&
                                (now - tabVisibleSince) > 12000 &&
                                (now - aliveTs) > HEARTBEAT_STALE_MS &&
                                (!glCanvas || glCanvas.width === 0 || glCanvas.height === 0)
                            ) {
                                iframeDeadReason = 'iframe_stale_canvas';
                            }
                        }
                    } catch (_secErr) {
                        // Cross-origin error accessing same-origin srcdoc iframe => Chromium replaced it with chrome-error:// (sad-face icon)
                        iframeDeadReason = 'iframe_crashed_sad_face';
                    }

                    if (iframeDeadReason) {
                        triggerAutoHeal(iframeDeadReason);
                    }
                } catch (_e) {}
            }

            var intervalId = setInterval(checkMapHealth, 3500);
            var onVisChange = function() {
                if (document.visibilityState === 'visible') {
                    tabVisibleSince = Date.now();
                    setTimeout(checkMapHealth, 900);
                } else {
                    tabVisibleSince = 0;
                }
            };
            var onFocus = function() {
                setTimeout(checkMapHealth, 900);
            };
            document.addEventListener('visibilitychange', onVisChange);
            win.addEventListener('focus', onFocus);

            var panelObserver = null;
            try {
                var initInfo = getMapStageAndPanel();
                if (initInfo.panel && win.MutationObserver) {
                    panelObserver = new MutationObserver(function() {
                        setTimeout(checkMapHealth, 500);
                    });
                    panelObserver.observe(initInfo.panel, {
                        attributes: true,
                        attributeFilter: ['hidden', 'aria-hidden', 'style', 'class']
                    });
                }
            } catch (_e) {}

            win.__NOVA_TAB2_AUTOHEAL_CLEANUP__ = function() {
                clearInterval(intervalId);
                document.removeEventListener('visibilitychange', onVisChange);
                win.removeEventListener('focus', onFocus);
                if (panelObserver) {
                    try { panelObserver.disconnect(); } catch (_e) {}
                    panelObserver = null;
                }
            };
        })();
        </script>
        """,
        unsafe_allow_javascript=True,
    )


def _render_map_html_component(html_str, height=870):
    """Renders map HTML via sandboxed stc.html iframe (never falls back to unscoped st.html)."""
    try:
        reset_nonce = int(st.session_state.get("_nova_reset_nonce", 0))
        reload_nonce = int(st.session_state.get("_tab2_map_reload_nonce", 0))
        force_fresh_map = bool(st.session_state.pop("_nova_just_reset_map", False))
        force_map_reload = bool(st.session_state.pop("_tab2_force_map_reload_js", False))
        out_html = html_str
        inject_flags = []
        if force_fresh_map:
            inject_flags.append("window.__NOVA_FORCE_FRESH_RESET__ = true;")
        if force_map_reload:
            inject_flags.append("window.__NOVA_FORCE_MAP_RELOAD__ = true;")
        if inject_flags:
            flag_script = f"<script>{' '.join(inject_flags)}</script>"
            if "<head>" in out_html:
                out_html = out_html.replace("<head>", f"<head>\n    {flag_script}", 1)
            else:
                out_html = flag_script + out_html
        if reset_nonce > 0:
            out_html = f"{out_html}\n<!-- reset-nonce:{reset_nonce} -->"
        if reload_nonce > 0:
            out_html = f"{out_html}\n<!-- map-reload-nonce:{reload_nonce} -->"
        stc.html(out_html, height=height)
        return True
    except Exception:
        st.error("ไม่สามารถแสดงแผนที่ได้ กรุณาลองรีเฟรชหน้าเว็บ")
        return False


def _build_all_provinces_json(df_raw):
    if df_raw is None or df_raw.empty or 'จังหวัด' not in df_raw.columns:
        return "[]"
    all_provinces_list = sorted(list({
        str(p).strip().strip(" ,;.-'\"")
        for p in df_raw['จังหวัด'].dropna().unique()
        if str(p).strip().strip(" ,;.-'\"")
        and str(p).strip().strip(" ,;.-'\"") not in ('-', 'ไม่มีข้อมูล', 'nan', 'None')
        and not re.search(r'\d', str(p))
        and re.search(r'^[ก-๙]', str(p).strip())
    }))
    return _safe_json_inline(all_provinces_list)


def render_tab2_map_view(df_raw, df_filtered, is_dark_mode):
    """
    Renders Tab 2: Interactive Leaflet Map with Deck.gl point visualization,
    in-map controls, search sync, boundary layers, and reference analytics fragment.
    """
    with st.container(key="tab_map"):
        # Resolve active reference point & radius
        active_ref_prop = st.session_state.get("tab2_ref_prop")
        active_ref_lat = None
        active_ref_lon = None
        try:
            rad_raw = float(st.query_params.get("map_ref_radius", 5.0))
            active_ref_radius = min(50.0, max(0.05, rad_raw)) if math.isfinite(rad_raw) else 5.0
        except (ValueError, TypeError):
            active_ref_radius = 5.0

        # Check if reference property ID came from map search, click, or query params
        q_comp = st.query_params.get("map_compare_ids")
        if q_comp and str(q_comp).strip():
            st.session_state["tab2_compare_ids"] = [x.strip() for x in str(q_comp).split(",") if x.strip()]
        q_id = st.query_params.get("map_ref_id")
        q_ref_co = st.query_params.get("map_ref_co") or st.session_state.get("tab2_ref_company", "")
        search_prop_id = q_id or st.session_state.get("tab2_search_prop_id", "")

        if search_prop_id and str(search_prop_id).strip():
            clean_id = str(search_prop_id).strip()
            clean_ref_co = str(q_ref_co or "").strip()
            _cur_ref_code = str(active_ref_prop.get('รหัสทรัพย์', '')).strip().lower() if active_ref_prop is not None else ""
            _cur_ref_co = str(active_ref_prop.get('บริษัท', '')).strip().lower() if active_ref_prop is not None else ""
            _ref_mismatch = (
                active_ref_prop is None
                or _cur_ref_code != clean_id.lower()
                or (clean_ref_co and _cur_ref_co != clean_ref_co.lower())
            )
            if _ref_mismatch:
                if df_raw is not None and not df_raw.empty and 'รหัสทรัพย์' in df_raw.columns:
                    r0 = find_property_row_by_code(
                        df_raw,
                        clean_id,
                        include_led_prefix=True,
                        company=clean_ref_co or None,
                        lat=active_ref_lat,
                        lon=active_ref_lon,
                    )
                    if r0 is not None:
                        if _is_valid_thai_coord(r0.get('ละติจูด'), r0.get('ลองจิจูด')):
                            active_ref_prop = r0
                            active_ref_lat = float(r0.get('ละติจูด'))
                            active_ref_lon = float(r0.get('ลองจิจูด'))
                            st.session_state["tab2_ref_lat"] = active_ref_lat
                            st.session_state["tab2_ref_lon"] = active_ref_lon
                            st.session_state["tab2_ref_prop"] = active_ref_prop
                            st.session_state["tab2_search_prop_id"] = str(r0.get('รหัสทรัพย์', clean_id)).strip()
                            st.session_state["tab2_ref_company"] = str(r0.get('บริษัท', clean_ref_co)).strip()
                            st.session_state["tab2_filter_projects"] = []
                            try:
                                st.query_params.pop("map_proj", None)
                            except Exception:
                                pass
                            p_prov = str(r0.get('จังหวัด', '')).strip()
                            p_dist = str(r0.get('อำเภอ', '')).strip()
                            p_subdist = str(r0.get('ตำบล', '')).strip()
                            invalid_loc = {'', '-', 'ไม่มีข้อมูล', 'ไม่ระบุ', 'nan', 'None', '<NA>'}
                            if p_prov not in invalid_loc:
                                st.session_state["tab2_filter_provinces"] = [p_prov]
                                st.query_params["map_prov"] = p_prov
                            else:
                                st.session_state["tab2_filter_provinces"] = []
                                try:
                                    st.query_params.pop("map_prov", None)
                                except Exception:
                                    pass
                            # Always overwrite or clear district/subdistrict so stale filters from a previous property never persist
                            if p_dist not in invalid_loc:
                                st.session_state["tab2_filter_districts"] = [p_dist]
                                st.query_params["map_dist"] = p_dist
                            else:
                                st.session_state["tab2_filter_districts"] = []
                                try:
                                    st.query_params.pop("map_dist", None)
                                except Exception:
                                    pass
                            if p_subdist not in invalid_loc:
                                st.session_state["tab2_filter_subdistricts"] = [p_subdist]
                                st.query_params["map_subdist"] = p_subdist
                            else:
                                st.session_state["tab2_filter_subdistricts"] = []
                                try:
                                    st.query_params.pop("map_subdist", None)
                                except Exception:
                                    pass
            else:
                if _is_valid_thai_coord(active_ref_prop.get('ละติจูด'), active_ref_prop.get('ลองจิจูด')):
                    active_ref_lat = float(active_ref_prop.get('ละติจูด'))
                    active_ref_lon = float(active_ref_prop.get('ลองจิจูด'))

        if active_ref_lat is None:
            q_lat = st.query_params.get("map_ref_lat")
            q_lon = st.query_params.get("map_ref_lon")
            if q_lat and q_lon and _is_valid_thai_coord(q_lat, q_lon):
                active_ref_lat = float(q_lat)
                active_ref_lon = float(q_lon)
                if active_ref_prop is not None:
                    try:
                        p_lat = float(active_ref_prop.get('ละติจูด', 0))
                        p_lon = float(active_ref_prop.get('ลองจิจูด', 0))
                        if abs(p_lat - active_ref_lat) > 0.0005 or abs(p_lon - active_ref_lon) > 0.0005:
                            active_ref_prop = None
                            st.session_state["tab2_ref_prop"] = None
                            st.session_state["tab2_search_prop_id"] = ""
                            st.session_state["tab2_input_prop_id"] = ""
                    except (ValueError, TypeError):
                        pass
            elif _is_valid_thai_coord(st.session_state.get("tab2_ref_lat"), st.session_state.get("tab2_ref_lon")):
                active_ref_lat = float(st.session_state["tab2_ref_lat"])
                active_ref_lon = float(st.session_state["tab2_ref_lon"])

        # Resolve active price center property
        if st.session_state.get("tab2_just_reset_price_center"):
            active_price_ref_prop = None
            st.session_state["tab2_price_ref_prop"] = None
            st.session_state["tab2_price_center_id"] = ""
            try:
                st.query_params.pop("map_price_ref_id", None)
            except Exception:
                pass
        else:
            active_price_ref_prop = st.session_state.get("tab2_price_ref_prop")
            price_prop_id = str(st.query_params.get("map_price_ref_id") or st.session_state.get("tab2_price_center_id", "")).strip()
            price_prop_co = str(st.query_params.get("map_price_ref_co") or st.session_state.get("tab2_price_center_company", "")).strip()
            if price_prop_id:
                clean_price_id = price_prop_id.strip()
                _cur_p_code = str(active_price_ref_prop.get('รหัสทรัพย์', '')).strip().lower() if active_price_ref_prop is not None else ""
                _cur_p_co = str(active_price_ref_prop.get('บริษัท', '')).strip().lower() if active_price_ref_prop is not None else ""
                _p_mismatch = (
                    active_price_ref_prop is None
                    or _cur_p_code != clean_price_id.lower()
                    or (price_prop_co and _cur_p_co != price_prop_co.lower())
                )
                if _p_mismatch:
                    found_pr = find_property_row_by_code(
                        df_raw,
                        clean_price_id,
                        include_led_prefix=True,
                        company=price_prop_co or None,
                        lat=active_ref_lat,
                        lon=active_ref_lon,
                    )
                    if found_pr is not None:
                        active_price_ref_prop = found_pr
                        st.session_state["tab2_price_ref_prop"] = active_price_ref_prop
                        st.session_state["tab2_price_center_id"] = str(found_pr.get('รหัสทรัพย์', clean_price_id)).strip()
                        st.session_state["tab2_price_center_company"] = str(found_pr.get('บริษัท', price_prop_co)).strip()
                elif active_price_ref_prop is not None:
                    st.session_state["tab2_price_center_id"] = clean_price_id
            else:
                active_price_ref_prop = None
                st.session_state["tab2_price_ref_prop"] = None
                st.session_state["tab2_price_center_id"] = ""
                st.session_state["tab2_price_center_company"] = ""

        # Read tab2 location filters AFTER property search has updated session_state
        tab2_filtered = pd.DataFrame() if df_filtered is None else df_filtered
        effective_provs = st.session_state.get("tab2_filter_provinces", []) or st.session_state.get("selected_provinces", [])
        effective_dists = st.session_state.get("tab2_filter_districts", []) or st.session_state.get("selected_districts_formatted", [])
        effective_subdists = st.session_state.get("tab2_filter_subdistricts", []) or st.session_state.get("selected_subdistricts_formatted", [])
        current_prov_str = effective_provs[0] if effective_provs else ""

        # Map Rendering (Deck.gl OpenStreetMap Map with dynamic marker mode, compass, and slider)
        has_custom_import = bool(
            "imported_custom_df" in st.session_state
            and st.session_state["imported_custom_df"] is not None
            and not st.session_state["imported_custom_df"].empty
        )
        is_nationwide_default = (
            not has_custom_import
            and (len(tab2_filtered) == len(df_raw) if (df_raw is not None and not df_raw.empty) else True)
        )

        # INSTANT PATH: Use pre-assembled nationwide base HTML + tokenized static .gz payload
        _instant_rendered = False
        _tmpl_path = str(_resolve_root_file("static/map_template.html"))
        _tmpl_mtime = os.path.getmtime(_tmpl_path) if os.path.exists(_tmpl_path) else None
        _cur_data_mtime = get_data_mtime()
        _cur_builder_ver = get_cache_builder_version()
        _cur_day_str = _today_th_str()
        _payload_meta = get_static_map_payload_meta(data_mtime=_cur_data_mtime, th_date=_cur_day_str)
        _force_refresh_payload = bool(st.session_state.pop("_tab2_force_refresh_payload", False))

        if st.session_state.pop("_tab2_show_reload_toast", False):
            st.toast("กำลังโหลดแผนที่และรีเฟรช Token ใหม่ (คงตัวกรองเดิมไว้)...", icon=":material/refresh:")

        if is_nationwide_default and (
            _force_refresh_payload
            or "cached_map_html_base" not in st.session_state
            or st.session_state.get("cached_map_tmpl_mtime") != _tmpl_mtime
            or st.session_state.get("cached_map_data_mtime") != _cur_data_mtime
            or st.session_state.get("cached_map_builder_ver") != _cur_builder_ver
            or st.session_state.get("cached_map_th_date") != _cur_day_str
            or st.session_state.get("cached_map_payload_url") != _payload_meta["url"]
            or not os.path.exists(_payload_meta["path"])
            or not os.path.isdir(_payload_meta["details_dir_path"])
        ):
            precompute_full_map_html(_cur_data_mtime, force_refresh=_force_refresh_payload)

        with st.container(key="tab2_map_stage"):
            st.button(
                "",
                icon=":material/refresh:",
                key="btn_tab2_reload_map",
                on_click=_reload_tab2_map_callback,
                help="โหลดแผนที่ใหม่และรีเฟรช Token (คงตัวกรองและจุดอ้างอิงเดิมไว้)",
            )

            if (
                is_nationwide_default
                and "cached_map_html_base" in st.session_state
                and st.session_state.get("cached_map_tmpl_mtime") == _tmpl_mtime
                and st.session_state.get("cached_map_data_mtime") == _cur_data_mtime
                and st.session_state.get("cached_map_builder_ver") == _cur_builder_ver
                and st.session_state.get("cached_map_th_date") == _cur_day_str
                and st.session_state.get("cached_map_data_len", 0) > 0
            ):
                _instant_html = _inject_dynamic_map_placeholders(
                    st.session_state["cached_map_html_base"],
                    is_dark_mode=is_dark_mode,
                    payload_url=st.session_state.get("cached_map_payload_url", _payload_meta["url"]),
                    invariant_runtime=True,
                )
                _render_map_html_component(_instant_html, height=870)
                _instant_rendered = True

            # FALLBACK / CUSTOM-IMPORT PATH (cached per session so reruns don't re-encode 460k rows)
            if not _instant_rendered:
                custom_sig = (
                    st.session_state.get("_custom_import_fp"),
                    int(st.session_state.get("_custom_import_ver", 0)),
                    len(tab2_filtered),
                    _tmpl_mtime,
                    _cur_data_mtime,
                    _cur_builder_ver,
                    _cur_day_str,
                    is_nationwide_default,
                )
                custom_cache = st.session_state.get("_tab2_custom_map_cache")
                if isinstance(custom_cache, dict) and custom_cache.get("sig") == custom_sig and custom_cache.get("base_html"):
                    base_with_static = custom_cache["base_html"]
                    map_data_empty = False
                    progress_bar = None
                else:
                    progress_bar = None
                    use_delta_custom = (
                        has_custom_import
                        and len(tab2_filtered) == (len(df_raw) if df_raw is not None else 0)
                        and os.path.exists(_payload_meta["path"])
                        and os.path.exists(_payload_meta["sidecar_path"])
                    )
                    delta_csv_b64 = ""
                    delta_lut_b64 = ""
                    payload_url_val = ""
                    csv_base64 = ""
                    lookup_b64 = ""
                    legend_content = ""
                    map_data_empty = False

                    if use_delta_custom:
                        try:
                            with gzip.open(_payload_meta["sidecar_path"], "rb") as _sf:
                                _sidecar = json.loads(_sf.read().decode("utf-8"))
                            base_legend = str(_sidecar.get("legend_content") or _sidecar.get("legend") or "")
                            delta_df = st.session_state["imported_custom_df"]
                            delta_csv_b64, delta_lut_b64, delta_legend, _ = build_map_payload_from_df(
                                delta_df,
                                df_project_source=df_raw,
                                data_mtime=_cur_data_mtime,
                                custom_companies=st.session_state.get("imported_custom_companies", {}),
                                custom_company=st.session_state.get("imported_custom_company"),
                                custom_color=st.session_state.get("imported_custom_color", "#6366f1"),
                            )
                            extra_items = [
                                ln for ln in (delta_legend or "").splitlines()
                                if "class=\"legend-item\"" in ln
                            ]
                            legend_content = (base_legend + "\n" + "\n".join(extra_items)).strip() if extra_items else base_legend
                            payload_url_val = _payload_meta["url"]
                        except Exception:
                            use_delta_custom = False

                    if not use_delta_custom:
                        if is_nationwide_default:
                            csv_base64, lookup_b64, legend_content, map_data_full_len = get_precomputed_map_payload(_cur_data_mtime)
                            map_data_empty = (map_data_full_len == 0)
                        else:
                            progress_bar = st.progress(0, text="กำลังเตรียมข้อมูลแผนที่...")
                            progress_bar.progress(20, text="กำลังกรองจุดพิกัดในประเทศไทย (20%)...")
                            csv_base64, lookup_b64, legend_content, map_data_full_len = build_map_payload_from_df(
                                tab2_filtered,
                                df_project_source=df_raw,
                                data_mtime=_cur_data_mtime,
                                progress_bar=progress_bar,
                                custom_companies=st.session_state.get("imported_custom_companies", {}),
                                custom_company=st.session_state.get("imported_custom_company"),
                                custom_color=st.session_state.get("imported_custom_color", "#6366f1"),
                            )
                            map_data_empty = (map_data_full_len == 0)

                    base_with_static = ""
                    if not map_data_empty:
                        base_tmpl = get_base_map_html((_tmpl_mtime, _cur_builder_ver))
                        atlas_uri, icon_mapping = get_map_icon_atlas_and_mapping(128, include_session_custom=has_custom_import)
                        company_logos_dict = get_leaflet_logo_dict(72, include_session_custom=has_custom_import)
                        base_with_static = _replace_placeholders_single_pass(
                            base_tmpl,
                            {
                                "CSV_BASE64_PLACEHOLDER": csv_base64,
                                "LOOKUP_BASE64_PLACEHOLDER": lookup_b64,
                                "CUSTOM_CSV_BASE64_PLACEHOLDER": delta_csv_b64,
                                "CUSTOM_LOOKUP_BASE64_PLACEHOLDER": delta_lut_b64,
                                "MAP_PAYLOAD_URL_PLACEHOLDER": payload_url_val,
                                "LEGEND_ITEMS_PLACEHOLDER": legend_content,
                                "ATLAS_BASE64_PLACEHOLDER": atlas_uri,
                                "ICON_MAPPING_PLACEHOLDER": _safe_json_inline(icon_mapping),
                                "ALL_PROVINCES_PLACEHOLDER": _build_all_provinces_json(df_raw),
                                "COMPANY_LOGOS_PLACEHOLDER": _safe_json_inline(company_logos_dict),
                            },
                        )
                        st.session_state["_tab2_custom_map_cache"] = {
                            "sig": custom_sig,
                            "base_html": base_with_static,
                        }

                if map_data_empty:
                    if progress_bar:
                        progress_bar.empty()
                    st.warning("ไม่พบพิกัดตำแหน่ง ละติจูด/ลองจิจูด ในรายการทรัพย์สินที่คุณเลือกค้นหา")
                else:
                    html_content = _inject_dynamic_map_placeholders(
                        base_with_static,
                        is_dark_mode=is_dark_mode,
                        payload_url=payload_url_val if not is_nationwide_default and 'payload_url_val' in locals() else "",
                        invariant_runtime=True,
                    )
                    if progress_bar:
                        progress_bar.progress(100, text="เรนเดอร์แผนที่สำเร็จแล้ว (100%)")
                        progress_bar.empty()

                    _render_map_html_component(html_content, height=870)

        _render_tab2_map_auto_heal_watcher()

        # ----------------- BELOW MAP: ANALYTICS CARDS & NEARBY ASSET LISTING -----------------
        if not has_custom_import:
            df_map_valid = get_valid_coord_properties_data(_cur_data_mtime)
        else:
            df_map_valid = df_raw[
                df_raw['ละติจูด'].notna() & df_raw['ลองจิจูด'].notna() &
                df_raw['ละติจูด'].between(5, 21) & df_raw['ลองจิจูด'].between(97, 106)
            ] if df_raw is not None and not df_raw.empty and 'ละติจูด' in df_raw.columns and 'ลองจิจูด' in df_raw.columns else df_raw

        render_tab2_reference_analytics_fragment(
            df_raw=df_map_valid,
            is_dark_mode=is_dark_mode,
            active_ref_lat=active_ref_lat,
            active_ref_lon=active_ref_lon,
            active_ref_prop=active_ref_prop,
            active_price_ref_prop=active_price_ref_prop,
            active_ref_radius=active_ref_radius,
            tab2_types=[],
        )

        # Always-visible Batch Reference Import & Grouped Export panel at the bottom of Tab 2 (outside map)
        render_tab2_batch_reference_panel(df_map_valid, is_dark_mode=is_dark_mode)
