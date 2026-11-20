"""Tab 2 map-iframe synchronization bridge, Price Center reset callback, and filter state resolution."""

import json
import streamlit as st

from modules.views.tab2_metrics import (
    _INVALID_LOC_TOKENS,
    _is_valid_thai_coord,
    _safe_float,
)


def _reset_price_center_callback():
    """on_click callback safely clearing price-center state BEFORE widgets render on the next rerun."""
    st.session_state["tab2_just_reset_price_center"] = True
    st.session_state["tab2_inject_clear_price_center_js"] = True
    st.session_state["tab2_price_center_id"] = ""
    st.session_state.pop("tab2_price_ref_prop", None)
    try:
        st.query_params.pop("map_price_ref_id", None)
    except Exception:
        pass
    # Safe to mutate widget-backed session_state inside on_click callback (runs before widget instantiation)
    raw_bridge = st.session_state.get("map_sync_bridge_payload")
    if raw_bridge:
        try:
            p_obj = json.loads(str(raw_bridge))
            if isinstance(p_obj, dict):
                p_obj["price_center_id"] = ""
                cleaned_str = json.dumps(p_obj, ensure_ascii=False)
                st.session_state["map_sync_bridge_payload"] = cleaned_str
                st.session_state["_tab2_last_processed_sync_raw"] = cleaned_str
        except Exception:
            pass


def _sync_num_filter(payload_obj, payload_key, state_key, qp_key=None):
    """Updates a numeric filter in session_state and keeps query_params aligned when explicitly cleared to 0."""
    if payload_key in payload_obj:
        val = max(0.0, _safe_float(payload_obj.get(payload_key), 0.0))
        st.session_state[state_key] = val
        if qp_key:
            try:
                if val > 0:
                    st.query_params[qp_key] = str(val)
                else:
                    st.query_params.pop(qp_key, None)
            except Exception:
                pass


def _read_num_filter(state_key, qp_key=None):
    """Reads numeric filter preferring session_state once initialized so clearing to 0 is never resurrected by URL."""
    if state_key in st.session_state:
        return max(0.0, _safe_float(st.session_state.get(state_key), 0.0))
    if qp_key:
        return max(0.0, _safe_float(st.query_params.get(qp_key), 0.0))
    return 0.0


def resolve_tab2_sync_and_filter_state(
    df_raw,
    *,
    active_ref_lat,
    active_ref_lon,
    active_ref_prop,
    active_price_ref_prop,
    active_ref_radius,
):
    """Processes the hidden map-iframe sync bridge and resolves all Tab 2 filters & reference points."""
    # 0. Hidden synchronization bridge between map iframe and Streamlit
    st.markdown("""
    <style>
    .st-key-btn_map_filter_sync,
    div[data-testid="stElementContainer"]:has(.st-key-btn_map_filter_sync),
    div[data-testid="stButton"]:has(.st-key-btn_map_filter_sync),
    .st-key-map_sync_bridge_payload,
    div[data-testid="stElementContainer"]:has(.st-key-map_sync_bridge_payload),
    div[data-testid="stTextInput"]:has(.st-key-map_sync_bridge_payload) {
        position: fixed !important;
        bottom: -9999px !important;
        right: -9999px !important;
        opacity: 0 !important;
        z-index: -9999 !important;
    }
    </style>
    <div id="map-sync-anchor" style="position:fixed; bottom:-9999px; right:-9999px;"></div>
    """, unsafe_allow_html=True)

    sync_bridge_val = st.text_input("map_sync_bridge", key="map_sync_bridge_payload", label_visibility="collapsed")
    sync_btn_clicked = st.button("sync_map_filter", key="btn_map_filter_sync")

    # Process sync payload only when button clicked OR payload text genuinely changed (prevents stale re-application)
    clean_bridge_str = str(sync_bridge_val or "").strip()
    is_new_bridge_payload = bool(
        clean_bridge_str and clean_bridge_str != st.session_state.get("_tab2_last_processed_sync_raw")
    )
    if sync_btn_clicked or is_new_bridge_payload:
        payload_obj = None
        if clean_bridge_str:
            try:
                payload_obj = json.loads(clean_bridge_str)
            except Exception:
                payload_obj = None
            st.session_state["_tab2_last_processed_sync_raw"] = clean_bridge_str

        if payload_obj and isinstance(payload_obj, dict):
            # Guard partial payloads: only mutate prov/dist/subdist when keys are actually present!
            prov_explicitly_cleared = False
            if "prov" in payload_obj:
                p_prov = str(payload_obj.get("prov", "")).strip()
                if p_prov and p_prov not in ("ALL", "__ALL__", "all", "-"):
                    st.session_state["tab2_filter_provinces"] = [p_prov]
                    try:
                        st.query_params["map_prov"] = p_prov
                    except Exception:
                        pass
                else:
                    prov_explicitly_cleared = True
                    st.session_state["tab2_filter_provinces"] = []
                    st.session_state["tab2_filter_districts"] = []
                    st.session_state["tab2_filter_subdistricts"] = []
                    st.session_state["tab2_search_prop_id"] = ""
                    st.session_state.pop("tab2_ref_prop", None)
                    for qk in ("map_prov", "map_dist", "map_subdist", "map_ref_id"):
                        try:
                            st.query_params.pop(qk, None)
                        except Exception:
                            pass

            dist_explicitly_cleared = prov_explicitly_cleared
            if "dist" in payload_obj and not prov_explicitly_cleared:
                p_dist = str(payload_obj.get("dist", "")).strip()
                if st.session_state.get("tab2_filter_provinces") and p_dist and p_dist not in ("ALL", "__ALL__", "all", "-"):
                    st.session_state["tab2_filter_districts"] = [p_dist]
                    try:
                        st.query_params["map_dist"] = p_dist
                    except Exception:
                        pass
                else:
                    dist_explicitly_cleared = True
                    st.session_state["tab2_filter_districts"] = []
                    st.session_state["tab2_filter_subdistricts"] = []
                    for qk in ("map_dist", "map_subdist"):
                        try:
                            st.query_params.pop(qk, None)
                        except Exception:
                            pass

            if "subdist" in payload_obj and not dist_explicitly_cleared:
                p_subdist = str(payload_obj.get("subdist", "")).strip()
                if st.session_state.get("tab2_filter_provinces") and st.session_state.get("tab2_filter_districts") and p_subdist and p_subdist not in ("ALL", "__ALL__", "all", "-"):
                    st.session_state["tab2_filter_subdistricts"] = [p_subdist]
                    try:
                        st.query_params["map_subdist"] = p_subdist
                    except Exception:
                        pass
                else:
                    st.session_state["tab2_filter_subdistricts"] = []
                    try:
                        st.query_params.pop("map_subdist", None)
                    except Exception:
                        pass

            if "proj" in payload_obj:
                p_proj = str(payload_obj.get("proj", "")).strip()
                if p_proj and p_proj not in ("ALL", "__ALL__", "all", "-"):
                    p_list = [x.strip() for x in p_proj.split(",") if x.strip()]
                    st.session_state["tab2_filter_projects"] = p_list
                    try:
                        st.query_params["map_proj"] = p_proj
                    except Exception:
                        pass
                else:
                    st.session_state["tab2_filter_projects"] = []
                    try:
                        st.query_params.pop("map_proj", None)
                    except Exception:
                        pass

            if "compare_ids" in payload_obj:
                raw_cids = payload_obj.get("compare_ids", [])
                if isinstance(raw_cids, list):
                    st.session_state["tab2_compare_ids"] = [str(x).strip() for x in raw_cids if str(x).strip()]
                elif isinstance(raw_cids, str):
                    st.session_state["tab2_compare_ids"] = [x.strip() for x in raw_cids.split(",") if x.strip()]
                try:
                    if st.session_state.get("tab2_compare_ids"):
                        st.query_params["map_compare_ids"] = ",".join(st.session_state["tab2_compare_ids"])
                    else:
                        st.query_params.pop("map_compare_ids", None)
                except Exception:
                    pass

            if "id" in payload_obj:
                p_id = str(payload_obj.get("id", "")).strip()
                if p_id:
                    st.session_state["tab2_search_prop_id"] = p_id
                    try:
                        st.query_params["map_ref_id"] = p_id
                    except Exception:
                        pass
                    if df_raw is not None and not df_raw.empty and 'รหัสทรัพย์' in df_raw.columns:
                        m = df_raw[df_raw['รหัสทรัพย์'].astype(str).str.strip().str.lower() == p_id.lower()]
                        if not m.empty:
                            active_ref_prop = m.iloc[0].to_dict()
                            st.session_state["tab2_ref_prop"] = active_ref_prop
                            prop_p = str(active_ref_prop.get('จังหวัด', '')).strip()
                            prop_d = str(active_ref_prop.get('อำเภอ', '')).strip()
                            prop_s = str(active_ref_prop.get('ตำบล', '')).strip()
                            st.session_state["tab2_filter_provinces"] = [prop_p] if prop_p not in _INVALID_LOC_TOKENS else []
                            st.session_state["tab2_filter_districts"] = [prop_d] if prop_d not in _INVALID_LOC_TOKENS else []
                            st.session_state["tab2_filter_subdistricts"] = [prop_s] if prop_s not in _INVALID_LOC_TOKENS else []
                else:
                    st.session_state["tab2_search_prop_id"] = ""
                    st.session_state.pop("tab2_ref_prop", None)
                    try:
                        st.query_params.pop("map_ref_id", None)
                    except Exception:
                        pass

            if "price_center_id" in payload_obj:
                if st.session_state.get("tab2_just_reset_price_center"):
                    p_price_id = ""
                else:
                    p_price_id = str(payload_obj.get("price_center_id", "")).strip()
                if p_price_id:
                    st.session_state["tab2_price_center_id"] = p_price_id
                    try:
                        st.query_params["map_price_ref_id"] = p_price_id
                    except Exception:
                        pass
                    if df_raw is not None and not df_raw.empty and 'รหัสทรัพย์' in df_raw.columns:
                        m_pr = df_raw[df_raw['รหัสทรัพย์'].astype(str).str.strip().str.lower() == p_price_id.lower()]
                        if not m_pr.empty:
                            active_price_ref_prop = m_pr.iloc[0].to_dict()
                            st.session_state["tab2_price_ref_prop"] = active_price_ref_prop
                else:
                    st.session_state["tab2_price_center_id"] = ""
                    st.session_state.pop("tab2_price_ref_prop", None)
                    active_price_ref_prop = None
                    try:
                        st.query_params.pop("map_price_ref_id", None)
                    except Exception:
                        pass

            if "lat" in payload_obj or "lon" in payload_obj:
                p_lat_f = _safe_float(payload_obj.get("lat"), 0.0)
                p_lon_f = _safe_float(payload_obj.get("lon"), 0.0)
                if _is_valid_thai_coord(p_lat_f, p_lon_f):
                    active_ref_lat = p_lat_f
                    active_ref_lon = p_lon_f
                    st.session_state["tab2_ref_lat"] = active_ref_lat
                    st.session_state["tab2_ref_lon"] = active_ref_lon
                    st.session_state["tab2_compared_lat"] = active_ref_lat
                    st.session_state["tab2_compared_lon"] = active_ref_lon
                    try:
                        st.query_params["map_ref_lat"] = f"{active_ref_lat:.6f}"
                        st.query_params["map_ref_lon"] = f"{active_ref_lon:.6f}"
                    except Exception:
                        pass
                else:
                    active_ref_lat = None
                    active_ref_lon = None
                    for sk in ("tab2_ref_lat", "tab2_ref_lon", "tab2_compared_lat", "tab2_compared_lon"):
                        st.session_state.pop(sk, None)
                    for qk in ("map_ref_lat", "map_ref_lon"):
                        try:
                            st.query_params.pop(qk, None)
                        except Exception:
                            pass

            if "radius" in payload_obj and payload_obj.get("radius"):
                rad_v = _safe_float(payload_obj.get("radius"), 0.0)
                if rad_v > 0:
                    active_ref_radius = min(50.0, max(0.5, rad_v))
                    st.session_state["tab2_ref_radius"] = active_ref_radius
                    try:
                        st.query_params["map_ref_radius"] = str(active_ref_radius)
                    except Exception:
                        pass

            if "mode" in payload_obj and payload_obj.get("mode"):
                st.session_state["tab2_pin_mode"] = str(payload_obj.get("mode")).strip()
                try:
                    st.query_params["map_pin_mode"] = st.session_state["tab2_pin_mode"]
                except Exception:
                    pass

            if "cos" in payload_obj and isinstance(payload_obj["cos"], list):
                st.session_state["tab2_map_filter_cos"] = payload_obj["cos"]
                try:
                    if payload_obj["cos"]:
                        st.query_params["map_filter_cos"] = ",".join(payload_obj["cos"])
                    else:
                        st.query_params.pop("map_filter_cos", None)
                except Exception:
                    pass
            if "types" in payload_obj and isinstance(payload_obj["types"], list):
                st.session_state["tab2_map_filter_types"] = payload_obj["types"]
                try:
                    if payload_obj["types"]:
                        st.query_params["map_filter_types"] = ",".join(payload_obj["types"])
                    else:
                        st.query_params.pop("map_filter_types", None)
                except Exception:
                    pass
            if "sales" in payload_obj and isinstance(payload_obj["sales"], list):
                st.session_state["tab2_map_filter_sales"] = payload_obj["sales"]
                try:
                    if payload_obj["sales"]:
                        st.query_params["map_filter_sales"] = ",".join(payload_obj["sales"])
                    else:
                        st.query_params.pop("map_filter_sales", None)
                except Exception:
                    pass

            _sync_num_filter(payload_obj, "min_p", "tab2_map_filter_min_p", "map_filter_min_p")
            _sync_num_filter(payload_obj, "max_p", "tab2_map_filter_max_p", "map_filter_max_p")
            _sync_num_filter(payload_obj, "min_sqw", "tab2_map_filter_min_sqw", "map_filter_min_sqw")
            _sync_num_filter(payload_obj, "max_sqw", "tab2_map_filter_max_sqw", "map_filter_max_sqw")
            _sync_num_filter(payload_obj, "min_sqm", "tab2_map_filter_min_sqm", "map_filter_min_sqm")
            _sync_num_filter(payload_obj, "max_sqm", "tab2_map_filter_max_sqm", "map_filter_max_sqm")
            _sync_num_filter(payload_obj, "min_puw", "tab2_map_filter_min_puw", "map_filter_min_puw")
            _sync_num_filter(payload_obj, "max_puw", "tab2_map_filter_max_puw", "map_filter_max_puw")
            _sync_num_filter(payload_obj, "min_pum", "tab2_map_filter_min_pum", "map_filter_min_pum")
            _sync_num_filter(payload_obj, "max_pum", "tab2_map_filter_max_pum", "map_filter_max_pum")
            _sync_num_filter(payload_obj, "min_fl", "tab2_map_filter_min_fl")
            _sync_num_filter(payload_obj, "max_fl", "tab2_map_filter_max_fl")
            _sync_num_filter(payload_obj, "max_age", "tab2_map_filter_max_age")

            if "only_with_proj" in payload_obj:
                st.session_state["tab2_map_filter_only_proj"] = bool(payload_obj["only_with_proj"])
                try:
                    if payload_obj["only_with_proj"]:
                        st.query_params["map_filter_only_proj"] = "1"
                    else:
                        st.query_params.pop("map_filter_only_proj", None)
                except Exception:
                    pass

            if "floors" in payload_obj and isinstance(payload_obj["floors"], list):
                st.session_state["tab2_map_filter_floors"] = payload_obj["floors"]
            if "beds" in payload_obj and isinstance(payload_obj["beds"], list):
                st.session_state["tab2_map_filter_beds"] = payload_obj["beds"]
            if "baths" in payload_obj and isinstance(payload_obj["baths"], list):
                st.session_state["tab2_map_filter_baths"] = payload_obj["baths"]
            if "pkgs" in payload_obj and isinstance(payload_obj["pkgs"], list):
                st.session_state["tab2_map_filter_pkgs"] = payload_obj["pkgs"]

            if payload_obj.get("compare_active", True):
                st.session_state["tab2_compared_active"] = True

        elif sync_btn_clicked:
            q_prov = st.query_params.get("map_prov", None)
            if q_prov and str(q_prov).strip() not in ("ALL", "__ALL__", "all", "", "-"):
                st.session_state["tab2_filter_provinces"] = [str(q_prov).strip()]
            elif q_prov in ("ALL", "__ALL__", "all", "-"):
                st.session_state["tab2_filter_provinces"] = []
                st.session_state["tab2_filter_districts"] = []
                st.session_state["tab2_filter_subdistricts"] = []
                st.session_state["tab2_search_prop_id"] = ""
                st.session_state.pop("tab2_ref_prop", None)

            q_dist = st.query_params.get("map_dist", None)
            if st.session_state.get("tab2_filter_provinces") and q_dist and str(q_dist).strip() not in ("ALL", "__ALL__", "all", "", "-"):
                st.session_state["tab2_filter_districts"] = [str(q_dist).strip()]
            elif q_dist in ("ALL", "__ALL__", "all", "-"):
                st.session_state["tab2_filter_districts"] = []

            q_subdist = st.query_params.get("map_subdist", None)
            if st.session_state.get("tab2_filter_provinces") and st.session_state.get("tab2_filter_districts") and q_subdist and str(q_subdist).strip() not in ("ALL", "__ALL__", "all", "", "-"):
                st.session_state["tab2_filter_subdistricts"] = [str(q_subdist).strip()]
            elif q_subdist in ("ALL", "__ALL__", "all", "-"):
                st.session_state["tab2_filter_subdistricts"] = []

            q_lat = st.query_params.get("map_ref_lat")
            q_lon = st.query_params.get("map_ref_lon")
            if q_lat and q_lon and _is_valid_thai_coord(q_lat, q_lon):
                active_ref_lat = float(q_lat)
                active_ref_lon = float(q_lon)
                st.session_state["tab2_ref_lat"] = active_ref_lat
                st.session_state["tab2_ref_lon"] = active_ref_lon
                st.session_state["tab2_compared_active"] = True

            q_id = st.query_params.get("map_ref_id")
            if q_id and df_raw is not None and not df_raw.empty and 'รหัสทรัพย์' in df_raw.columns:
                clean_id = str(q_id).strip()
                st.session_state["tab2_search_prop_id"] = clean_id
                if "map_proj" not in st.query_params:
                    st.session_state["tab2_filter_projects"] = []
                f_prop = df_raw[df_raw['รหัสทรัพย์'].astype(str).str.strip().str.lower() == clean_id.lower()]
                if not f_prop.empty:
                    prop_row = f_prop.iloc[0]
                    active_ref_prop = prop_row.to_dict()
                    st.session_state["tab2_ref_prop"] = active_ref_prop
                    r_prov = str(prop_row.get('จังหวัด', '')).strip()
                    r_dist = str(prop_row.get('อำเภอ', '')).strip()
                    r_subdist = str(prop_row.get('ตำบล', '')).strip()
                    st.session_state["tab2_filter_provinces"] = [r_prov] if r_prov not in _INVALID_LOC_TOKENS else []
                    st.session_state["tab2_filter_districts"] = [r_dist] if r_dist not in _INVALID_LOC_TOKENS else []
                    st.session_state["tab2_filter_subdistricts"] = [r_subdist] if r_subdist not in _INVALID_LOC_TOKENS else []

            has_loc_synced = (
                (q_prov is not None and str(q_prov).strip() not in ("", "ALL", "__ALL__", "all"))
                or (q_dist is not None and str(q_dist).strip() not in ("", "ALL", "__ALL__", "all"))
                or (q_subdist is not None and str(q_subdist).strip() not in ("", "ALL", "__ALL__", "all"))
                or bool(q_id)
            )
            if has_loc_synced:
                st.session_state["tab2_compared_active"] = True

    # 1. Recovery of reference coordinates & radius from query_params or session_state
    q_lat_check = st.query_params.get("map_ref_lat")
    if q_lat_check:
        try:
            if float(q_lat_check) > 0 and "map_ref_cleared" in st.query_params:
                del st.query_params["map_ref_cleared"]
        except (ValueError, TypeError):
            pass

    if st.query_params.get("map_ref_cleared") == "1":
        active_ref_lat = 0.0
        active_ref_lon = 0.0
        active_ref_prop = None
        active_price_ref_prop = None
        st.session_state["tab2_ref_lat"] = 0.0
        st.session_state["tab2_ref_lon"] = 0.0
        st.session_state["tab2_ref_prop"] = None
        st.session_state["tab2_price_ref_prop"] = None
        st.session_state["tab2_price_center_id"] = ""
        st.session_state["tab2_compared_active"] = False
        for qk in ("map_ref_cleared", "map_price_ref_id"):
            try:
                st.query_params.pop(qk, None)
            except Exception:
                pass
    else:
        q_lat = st.query_params.get("map_ref_lat")
        q_lon = st.query_params.get("map_ref_lon")
        if q_lat and q_lon and _is_valid_thai_coord(q_lat, q_lon):
            active_ref_lat = float(q_lat)
            active_ref_lon = float(q_lon)
            st.session_state["tab2_ref_lat"] = active_ref_lat
            st.session_state["tab2_ref_lon"] = active_ref_lon
        q_rad = st.query_params.get("map_ref_radius")
        if q_rad:
            rad_v = _safe_float(q_rad, 0.0)
            if rad_v > 0:
                active_ref_radius = min(50.0, max(0.5, rad_v))
                st.session_state["tab2_ref_radius"] = active_ref_radius

    if not _is_valid_thai_coord(active_ref_lat, active_ref_lon):
        s_lat = _safe_float(st.session_state.get("tab2_ref_lat"), 0.0)
        s_lon = _safe_float(st.session_state.get("tab2_ref_lon"), 0.0)
        if _is_valid_thai_coord(s_lat, s_lon):
            active_ref_lat = s_lat
            active_ref_lon = s_lon
        else:
            active_ref_lat = None
            active_ref_lon = None

    active_ref_radius = _safe_float(active_ref_radius, 0.0)
    if active_ref_radius <= 0:
        active_ref_radius = _safe_float(st.session_state.get("tab2_ref_radius"), 5.0)
    active_ref_radius = min(50.0, max(0.5, active_ref_radius if active_ref_radius > 0 else 5.0))

    q_comp = st.query_params.get("map_compare_ids")
    if q_comp and str(q_comp).strip():
        st.session_state["tab2_compare_ids"] = [x.strip() for x in str(q_comp).split(",") if x.strip()]

    # Auto-resolve active_ref_prop
    q_id = st.query_params.get("map_ref_id") or st.session_state.get("tab2_search_prop_id")
    if q_id and df_raw is not None and not df_raw.empty and 'รหัสทรัพย์' in df_raw.columns:
        clean_id = str(q_id).strip()
        if active_ref_prop is None or str(active_ref_prop.get('รหัสทรัพย์', '')).strip().lower() != clean_id.lower():
            found = df_raw[df_raw['รหัสทรัพย์'].astype(str).str.strip().str.lower() == clean_id.lower()]
            if not found.empty:
                active_ref_prop = found.iloc[0].to_dict()
                st.session_state["tab2_ref_prop"] = active_ref_prop
                st.session_state["tab2_search_prop_id"] = clean_id
    elif not q_id and not st.session_state.get("tab2_search_prop_id"):
        active_ref_prop = None
        st.session_state["tab2_search_prop_id"] = ""
        st.session_state.pop("tab2_ref_prop", None)

    # Auto-resolve active_price_ref_prop
    if st.session_state.get("tab2_just_reset_price_center"):
        st.session_state["tab2_just_reset_price_center"] = False
        active_price_ref_prop = None
        st.session_state["tab2_price_center_id"] = ""
        st.session_state.pop("tab2_price_ref_prop", None)
        try:
            st.query_params.pop("map_price_ref_id", None)
        except Exception:
            pass
    else:
        q_price_id = st.query_params.get("map_price_ref_id") or st.session_state.get("tab2_price_center_id")
        if q_price_id and df_raw is not None and not df_raw.empty and 'รหัสทรัพย์' in df_raw.columns:
            clean_price_id = str(q_price_id).strip()
            if active_price_ref_prop is None or str(active_price_ref_prop.get('รหัสทรัพย์', '')).strip().lower() != clean_price_id.lower():
                found_p = df_raw[df_raw['รหัสทรัพย์'].astype(str).str.strip().str.lower() == clean_price_id.lower()]
                if not found_p.empty:
                    active_price_ref_prop = found_p.iloc[0].to_dict()
                    st.session_state["tab2_price_ref_prop"] = active_price_ref_prop
                    st.session_state["tab2_price_center_id"] = clean_price_id
        elif not q_price_id and not st.session_state.get("tab2_price_center_id"):
            active_price_ref_prop = None
            st.session_state["tab2_price_center_id"] = ""
            st.session_state.pop("tab2_price_ref_prop", None)

    # 2. Extract and resolve all current map filters
    q_prov = st.query_params.get("map_prov", None)
    if q_prov and str(q_prov).strip() not in ("ALL", "__ALL__", "all", "", "-"):
        active_prov = [str(q_prov).strip()]
        st.session_state["tab2_filter_provinces"] = active_prov
    elif q_prov in ("ALL", "__ALL__", "all", "-"):
        active_prov = []
        st.session_state["tab2_filter_provinces"] = []
    else:
        active_prov = st.session_state.get("tab2_filter_provinces", [])

    q_dist = st.query_params.get("map_dist", None)
    if active_prov and q_dist and str(q_dist).strip() not in ("ALL", "__ALL__", "all", "", "-"):
        active_dist = [str(q_dist).strip()]
        st.session_state["tab2_filter_districts"] = active_dist
    elif q_dist in ("ALL", "__ALL__", "all", "-"):
        active_dist = []
        st.session_state["tab2_filter_districts"] = []
    else:
        active_dist = st.session_state.get("tab2_filter_districts", []) if active_prov else []

    q_subdist = st.query_params.get("map_subdist", None)
    if active_prov and active_dist and q_subdist and str(q_subdist).strip() not in ("ALL", "__ALL__", "all", "", "-"):
        active_subdist = [str(q_subdist).strip()]
        st.session_state["tab2_filter_subdistricts"] = active_subdist
    elif q_subdist in ("ALL", "__ALL__", "all", "-"):
        active_subdist = []
        st.session_state["tab2_filter_subdistricts"] = []
    else:
        active_subdist = st.session_state.get("tab2_filter_subdistricts", []) if (active_prov and active_dist) else []

    q_proj = st.query_params.get("map_proj", None)
    if q_proj and str(q_proj).strip() not in ("ALL", "__ALL__", "all", ""):
        active_proj = str(q_proj).strip()
    else:
        proj_list = st.session_state.get("tab2_filter_projects", [])
        active_proj = ",".join(proj_list) if proj_list else None

    if "tab2_map_filter_cos" in st.session_state:
        map_cos = st.session_state.get("tab2_map_filter_cos", [])
    else:
        raw_cos = st.query_params.get("map_filter_cos", "")
        map_cos = [c.strip() for c in raw_cos.split(",") if c.strip()] if raw_cos else []

    if "tab2_map_filter_only_proj" in st.session_state:
        q_only_proj = bool(st.session_state.get("tab2_map_filter_only_proj", False))
    else:
        q_only_proj = st.query_params.get("map_filter_only_proj", "0") in ("1", "true", "True")

    if "tab2_map_filter_types" in st.session_state:
        map_types = st.session_state.get("tab2_map_filter_types", [])
    else:
        raw_types = st.query_params.get("map_filter_types", "")
        map_types = [t.strip() for t in raw_types.split(",") if t.strip()] if raw_types else []

    if "tab2_map_filter_sales" in st.session_state:
        map_sales = st.session_state.get("tab2_map_filter_sales", [])
    else:
        raw_sales = st.query_params.get("map_filter_sales", "")
        map_sales = [s.strip() for s in raw_sales.split(",") if s.strip()] if raw_sales else []

    map_min_p = _read_num_filter("tab2_map_filter_min_p", "map_filter_min_p")
    map_max_p = _read_num_filter("tab2_map_filter_max_p", "map_filter_max_p")
    map_min_sqw = _read_num_filter("tab2_map_filter_min_sqw", "map_filter_min_sqw")
    map_max_sqw = _read_num_filter("tab2_map_filter_max_sqw", "map_filter_max_sqw")
    map_min_sqm = _read_num_filter("tab2_map_filter_min_sqm", "map_filter_min_sqm")
    map_max_sqm = _read_num_filter("tab2_map_filter_max_sqm", "map_filter_max_sqm")
    map_min_puw = _read_num_filter("tab2_map_filter_min_puw", "map_filter_min_puw")
    map_max_puw = _read_num_filter("tab2_map_filter_max_puw", "map_filter_max_puw")
    map_min_pum = _read_num_filter("tab2_map_filter_min_pum", "map_filter_min_pum")
    map_max_pum = _read_num_filter("tab2_map_filter_max_pum", "map_filter_max_pum")

    map_floors = st.session_state.get("tab2_map_filter_floors", [])
    map_min_fl = _read_num_filter("tab2_map_filter_min_fl")
    map_max_fl = _read_num_filter("tab2_map_filter_max_fl")
    map_beds = st.session_state.get("tab2_map_filter_beds", [])
    map_baths = st.session_state.get("tab2_map_filter_baths", [])
    map_pkgs = st.session_state.get("tab2_map_filter_pkgs", [])
    map_max_age = _read_num_filter("tab2_map_filter_max_age")

    pin_mode = st.session_state.get("tab2_pin_mode") or st.query_params.get("map_pin_mode", "radius")
    has_ref_point = _is_valid_thai_coord(active_ref_lat, active_ref_lon)
    has_loc_filter = bool(active_prov or active_dist or active_subdist or active_proj)
    active_compare_ids = st.session_state.get("tab2_compare_ids", [])

    has_any_filter = bool(
        has_ref_point or has_loc_filter or map_cos or q_only_proj or map_types or map_sales
        or (map_min_p > 0) or (map_max_p > 0) or (map_min_sqw > 0) or (map_max_sqw > 0)
        or (map_min_sqm > 0) or (map_max_sqm > 0) or (map_min_puw > 0) or (map_max_puw > 0)
        or (map_min_pum > 0) or (map_max_pum > 0) or map_floors or (map_min_fl > 0) or (map_max_fl > 0)
        or map_beds or map_baths or map_pkgs or (map_max_age > 0)
        or bool(active_compare_ids) or (active_ref_prop is not None)
    )

    return {
        "active_ref_lat": active_ref_lat,
        "active_ref_lon": active_ref_lon,
        "active_ref_radius": active_ref_radius,
        "active_ref_prop": active_ref_prop,
        "active_price_ref_prop": active_price_ref_prop,
        "active_prov": active_prov,
        "active_dist": active_dist,
        "active_subdist": active_subdist,
        "active_proj": active_proj,
        "map_cos": map_cos,
        "q_only_proj": q_only_proj,
        "map_types": map_types,
        "map_sales": map_sales,
        "map_min_p": map_min_p,
        "map_max_p": map_max_p,
        "map_min_sqw": map_min_sqw,
        "map_max_sqw": map_max_sqw,
        "map_min_sqm": map_min_sqm,
        "map_max_sqm": map_max_sqm,
        "map_min_puw": map_min_puw,
        "map_max_puw": map_max_puw,
        "map_min_pum": map_min_pum,
        "map_max_pum": map_max_pum,
        "map_floors": map_floors,
        "map_min_fl": map_min_fl,
        "map_max_fl": map_max_fl,
        "map_beds": map_beds,
        "map_baths": map_baths,
        "map_pkgs": map_pkgs,
        "map_max_age": map_max_age,
        "pin_mode": pin_mode,
        "has_ref_point": has_ref_point,
        "has_loc_filter": has_loc_filter,
        "active_compare_ids": active_compare_ids,
        "has_any_filter": has_any_filter,
    }
