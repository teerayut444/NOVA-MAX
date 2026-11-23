# Tab 2 Interactive Map View - Tokenized Static Payload, Single-Pass Placeholder Escaping & Per-Session Custom Cache
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
    get_base_map_html,
    get_cache_builder_version,
    get_data_mtime,
    get_data_mtime_token,
    get_precomputed_map_payload,
    get_static_map_payload_meta,
    precompute_full_map_html,
)
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


def _render_map_html_component(html_str, height=870):
    """Renders map HTML via sandboxed stc.html iframe (never falls back to unscoped st.html)."""
    try:
        reset_nonce = int(st.session_state.get("_nova_reset_nonce", 0))
        force_fresh_map = bool(st.session_state.pop("_nova_just_reset_map", False))
        out_html = html_str
        if force_fresh_map:
            reset_flag_script = "<script>window.__NOVA_FORCE_FRESH_RESET__ = true;</script>"
            if "<head>" in out_html:
                out_html = out_html.replace("<head>", f"<head>\n    {reset_flag_script}", 1)
            else:
                out_html = reset_flag_script + out_html
        if reset_nonce > 0:
            out_html = f"{out_html}\n<!-- reset-nonce:{reset_nonce} -->"
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
            active_ref_radius = min(50.0, max(0.5, rad_raw)) if math.isfinite(rad_raw) else 5.0
        except (ValueError, TypeError):
            active_ref_radius = 5.0

        # Check if reference property ID came from map search, click, or query params
        q_comp = st.query_params.get("map_compare_ids")
        if q_comp and str(q_comp).strip():
            st.session_state["tab2_compare_ids"] = [x.strip() for x in str(q_comp).split(",") if x.strip()]
        q_id = st.query_params.get("map_ref_id")
        search_prop_id = q_id or st.session_state.get("tab2_search_prop_id", "")

        if search_prop_id and str(search_prop_id).strip():
            clean_id = str(search_prop_id).strip()
            if active_ref_prop is None or str(active_ref_prop.get('รหัสทรัพย์', '')).strip().lower() != clean_id.lower():
                if df_raw is not None and not df_raw.empty and 'รหัสทรัพย์' in df_raw.columns:
                    s_codes = df_raw['รหัสทรัพย์'].astype(str).str.strip().str.lower()
                    clean_id_lower = clean_id.lower()
                    match_df = df_raw[s_codes == clean_id_lower]
                    if match_df.empty:
                        match_df = df_raw[s_codes.str.startswith(clean_id_lower + '_')]
                    if not match_df.empty:
                        r0 = match_df.iloc[0]
                        if _is_valid_thai_coord(r0.get('ละติจูด'), r0.get('ลองจิจูด')):
                            active_ref_prop = r0.to_dict()
                            active_ref_lat = float(r0.get('ละติจูด'))
                            active_ref_lon = float(r0.get('ลองจิจูด'))
                            st.session_state["tab2_ref_lat"] = active_ref_lat
                            st.session_state["tab2_ref_lon"] = active_ref_lon
                            st.session_state["tab2_ref_prop"] = active_ref_prop
                            st.session_state["tab2_search_prop_id"] = clean_id
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
            if price_prop_id:
                clean_price_id = price_prop_id.strip()
                if active_price_ref_prop is None or str(active_price_ref_prop.get('รหัสทรัพย์', '')).strip().lower() != clean_price_id.lower():
                    if df_raw is not None and not df_raw.empty and 'รหัสทรัพย์' in df_raw.columns:
                        s_codes = df_raw['รหัสทรัพย์'].astype(str).str.strip().str.lower()
                        m_p = df_raw[s_codes == clean_price_id.lower()]
                        if m_p.empty:
                            m_p = df_raw[s_codes.str.startswith(clean_price_id.lower() + '_')]
                        if not m_p.empty:
                            active_price_ref_prop = m_p.iloc[0].to_dict()
                            st.session_state["tab2_price_ref_prop"] = active_price_ref_prop
                            st.session_state["tab2_price_center_id"] = clean_price_id
                elif active_price_ref_prop is not None:
                    st.session_state["tab2_price_center_id"] = clean_price_id
            else:
                active_price_ref_prop = None
                st.session_state["tab2_price_ref_prop"] = None
                st.session_state["tab2_price_center_id"] = ""

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

        if is_nationwide_default and (
            "cached_map_html_base" not in st.session_state
            or st.session_state.get("cached_map_tmpl_mtime") != _tmpl_mtime
            or st.session_state.get("cached_map_data_mtime") != _cur_data_mtime
            or st.session_state.get("cached_map_builder_ver") != _cur_builder_ver
            or st.session_state.get("cached_map_th_date") != _cur_day_str
            or st.session_state.get("cached_map_payload_url") != _payload_meta["url"]
            or not os.path.exists(_payload_meta["path"])
            or not os.path.isdir(_payload_meta["details_dir_path"])
        ):
            precompute_full_map_html(_cur_data_mtime)

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
                            "MAP_PAYLOAD_URL_PLACEHOLDER": "",
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
                    payload_url="",
                    invariant_runtime=True,
                )
                if progress_bar:
                    progress_bar.progress(100, text="เรนเดอร์แผนที่สำเร็จแล้ว (100%)")
                    progress_bar.empty()

                _render_map_html_component(html_content, height=870)

        # ----------------- BELOW MAP: ANALYTICS CARDS & NEARBY ASSET LISTING -----------------
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
