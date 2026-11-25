"""Tab 2 map-iframe synchronization bridge, Price Center reset callback, and filter state resolution."""

import json
import streamlit as st

from modules.services.data_loader import find_property_row_by_code
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
    """Updates a numeric filter in session_state (browser URL is already updated silently by JS replaceState)."""
    if payload_key in payload_obj:
        val = max(0.0, _safe_float(payload_obj.get(payload_key), 0.0))
        st.session_state[state_key] = val


def _read_num_filter(state_key, qp_key=None):
    """Reads numeric filter preferring session_state once initialized so clearing to 0 is never resurrected by URL."""
    if state_key in st.session_state:
        return max(0.0, _safe_float(st.session_state.get(state_key), 0.0))
    if qp_key:
        return max(0.0, _safe_float(st.query_params.get(qp_key), 0.0))
    return 0.0


def _parse_multi_filter_param(raw, limit=64):
    """Parses JSON-array serialized multi-filter values cleanly, falling back to comma split."""
    if raw is None:
        return []
    if isinstance(raw, (list, tuple, set)):
        return [str(x).strip() for x in list(raw)[:limit] if str(x).strip()]
    s = str(raw).strip()
    if not s:
        return []
    if s.startswith("["):
        try:
            parsed = json.loads(s)
            if isinstance(parsed, list):
                return [str(x).strip() for x in parsed[:limit] if str(x).strip()]
        except Exception:
            pass
    return [x.strip() for x in s.split(",") if x.strip()][:limit]


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
        if clean_bridge_str and len(clean_bridge_str) <= 32_768:
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
                else:
                    prov_explicitly_cleared = True
                    st.session_state["tab2_filter_provinces"] = []
                    st.session_state["tab2_filter_districts"] = []
                    st.session_state["tab2_filter_subdistricts"] = []
                    st.session_state["tab2_search_prop_id"] = ""
                    st.session_state.pop("tab2_ref_prop", None)

            dist_explicitly_cleared = prov_explicitly_cleared
            if "dist" in payload_obj and not prov_explicitly_cleared:
                p_dist = str(payload_obj.get("dist", "")).strip()
                if st.session_state.get("tab2_filter_provinces") and p_dist and p_dist not in ("ALL", "__ALL__", "all", "-"):
                    st.session_state["tab2_filter_districts"] = [p_dist]
                else:
                    dist_explicitly_cleared = True
                    st.session_state["tab2_filter_districts"] = []
                    st.session_state["tab2_filter_subdistricts"] = []

            if "subdist" in payload_obj and not dist_explicitly_cleared:
                p_subdist = str(payload_obj.get("subdist", "")).strip()
                if st.session_state.get("tab2_filter_provinces") and st.session_state.get("tab2_filter_districts") and p_subdist and p_subdist not in ("ALL", "__ALL__", "all", "-"):
                    st.session_state["tab2_filter_subdistricts"] = [p_subdist]
                else:
                    st.session_state["tab2_filter_subdistricts"] = []

            if "proj_list" in payload_obj and isinstance(payload_obj["proj_list"], list):
                st.session_state["tab2_filter_projects"] = _parse_multi_filter_param(payload_obj["proj_list"], limit=50)
            elif "proj" in payload_obj:
                p_proj = str(payload_obj.get("proj", "")).strip()
                if p_proj and p_proj not in ("ALL", "__ALL__", "all", "-"):
                    st.session_state["tab2_filter_projects"] = _parse_multi_filter_param(p_proj, limit=50)
                else:
                    st.session_state["tab2_filter_projects"] = []

            if "compare_ids" in payload_obj:
                raw_cids = payload_obj.get("compare_ids", [])
                if isinstance(raw_cids, list):
                    st.session_state["tab2_compare_ids"] = [str(x).strip() for x in raw_cids if str(x).strip()][:200]
                elif isinstance(raw_cids, str):
                    st.session_state["tab2_compare_ids"] = [x.strip() for x in raw_cids.split(",") if x.strip()][:200]

            if "batch_ref" in payload_obj:
                b_ref = payload_obj.get("batch_ref")
                if isinstance(b_ref, dict) and str(b_ref.get("code") or "").strip():
                    st.session_state["tab2_batch_active_ref"] = {
                        "บริษัท": str(b_ref.get("company") or "ทรัพย์อ้างอิง").strip(),
                        "รหัสทรัพย์": str(b_ref.get("code") or "").strip(),
                        "ประเภททรัพย์": str(b_ref.get("prop_type") or "-").strip(),
                        "ชื่อโครงการ": str(b_ref.get("project") or "").strip(),
                        "ราคา": _safe_float(b_ref.get("price"), 0.0),
                        "ละติจูด": _safe_float(b_ref.get("lat"), 0.0),
                        "ลองจิจูด": _safe_float(b_ref.get("lon"), 0.0),
                    }
                    active_ref_prop = st.session_state["tab2_batch_active_ref"]
                    st.session_state["tab2_ref_prop"] = active_ref_prop
                else:
                    st.session_state.pop("tab2_batch_active_ref", None)

            if "id" in payload_obj:
                p_id = str(payload_obj.get("id", "")).strip()
                if p_id:
                    st.session_state["tab2_search_prop_id"] = p_id
                    found_row = find_property_row_by_code(df_raw, p_id, include_led_prefix=True)
                    if found_row is not None:
                        active_ref_prop = found_row
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

            if "price_center_id" in payload_obj:
                if st.session_state.get("tab2_just_reset_price_center"):
                    p_price_id = ""
                else:
                    p_price_id = str(payload_obj.get("price_center_id", "")).strip()
                if p_price_id:
                    st.session_state["tab2_price_center_id"] = p_price_id
                    found_pr = find_property_row_by_code(df_raw, p_price_id)
                    if found_pr is not None:
                        active_price_ref_prop = found_pr
                        st.session_state["tab2_price_ref_prop"] = active_price_ref_prop
                else:
                    st.session_state["tab2_price_center_id"] = ""
                    st.session_state.pop("tab2_price_ref_prop", None)
                    active_price_ref_prop = None

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
                else:
                    active_ref_lat = None
                    active_ref_lon = None
                    st.session_state["tab2_ref_lat"] = 0.0
                    st.session_state["tab2_ref_lon"] = 0.0
                    for sk in ("tab2_compared_lat", "tab2_compared_lon"):
                        st.session_state.pop(sk, None)

            if "radius" in payload_obj and payload_obj.get("radius"):
                rad_v = _safe_float(payload_obj.get("radius"), 0.0)
                if rad_v > 0:
                    active_ref_radius = min(50.0, max(0.05, rad_v))
                    st.session_state["tab2_ref_radius"] = active_ref_radius

            if "mode" in payload_obj and payload_obj.get("mode"):
                st.session_state["tab2_pin_mode"] = str(payload_obj.get("mode")).strip()

            if "cos" in payload_obj and isinstance(payload_obj["cos"], list):
                st.session_state["tab2_map_filter_cos"] = [str(x).strip() for x in payload_obj["cos"][:64]]
            if "types" in payload_obj and isinstance(payload_obj["types"], list):
                st.session_state["tab2_map_filter_types"] = [str(x).strip() for x in payload_obj["types"][:64]]
            if "sales" in payload_obj and isinstance(payload_obj["sales"], list):
                st.session_state["tab2_map_filter_sales"] = [str(x).strip() for x in payload_obj["sales"][:64]]

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
            _sync_num_filter(payload_obj, "min_fl", "tab2_map_filter_min_fl", "map_filter_min_fl")
            _sync_num_filter(payload_obj, "max_fl", "tab2_map_filter_max_fl", "map_filter_max_fl")
            _sync_num_filter(payload_obj, "max_age", "tab2_map_filter_max_age", "map_filter_max_age")

            if "only_with_proj" in payload_obj:
                st.session_state["tab2_map_filter_only_proj"] = bool(payload_obj["only_with_proj"])

            if "include_centroids" in payload_obj:
                _inc_c = bool(payload_obj["include_centroids"])
                st.session_state["tab2_include_centroids"] = _inc_c

            if "floors" in payload_obj and isinstance(payload_obj["floors"], list):
                st.session_state["tab2_map_filter_floors"] = [str(x).strip() for x in payload_obj["floors"][:64]]
            if "beds" in payload_obj and isinstance(payload_obj["beds"], list):
                st.session_state["tab2_map_filter_beds"] = [str(x).strip() for x in payload_obj["beds"][:64]]
            if "baths" in payload_obj and isinstance(payload_obj["baths"], list):
                st.session_state["tab2_map_filter_baths"] = [str(x).strip() for x in payload_obj["baths"][:64]]
            if "pkgs" in payload_obj and isinstance(payload_obj["pkgs"], list):
                st.session_state["tab2_map_filter_pkgs"] = [str(x).strip() for x in payload_obj["pkgs"][:64]]

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
                prop_row = find_property_row_by_code(df_raw, clean_id, include_led_prefix=True)
                if prop_row is not None:
                    active_ref_prop = prop_row
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

    # 1. Recovery of reference coordinates & radius from session_state (or initial query_params before first bridge sync)
    has_bridge_synced = bool(st.session_state.get("_tab2_last_processed_sync_raw"))

    if not has_bridge_synced and st.query_params.get("map_ref_cleared") == "1":
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
    elif "tab2_ref_lat" in st.session_state or "tab2_ref_lon" in st.session_state:
        s_lat = _safe_float(st.session_state.get("tab2_ref_lat"), 0.0)
        s_lon = _safe_float(st.session_state.get("tab2_ref_lon"), 0.0)
        if _is_valid_thai_coord(s_lat, s_lon):
            active_ref_lat = s_lat
            active_ref_lon = s_lon
        else:
            active_ref_lat = None
            active_ref_lon = None
    else:
        q_lat = st.query_params.get("map_ref_lat")
        q_lon = st.query_params.get("map_ref_lon")
        if q_lat and q_lon and _is_valid_thai_coord(q_lat, q_lon):
            active_ref_lat = float(q_lat)
            active_ref_lon = float(q_lon)
            st.session_state["tab2_ref_lat"] = active_ref_lat
            st.session_state["tab2_ref_lon"] = active_ref_lon

    if not _is_valid_thai_coord(active_ref_lat, active_ref_lon):
        active_ref_lat = None
        active_ref_lon = None

    if "tab2_ref_radius" in st.session_state:
        active_ref_radius = _safe_float(st.session_state.get("tab2_ref_radius"), 5.0)
    else:
        q_rad = st.query_params.get("map_ref_radius")
        if q_rad:
            rad_v = _safe_float(q_rad, 0.0)
            if rad_v > 0:
                active_ref_radius = min(50.0, max(0.05, rad_v))
                st.session_state["tab2_ref_radius"] = active_ref_radius
    active_ref_radius = _safe_float(active_ref_radius, 0.0)
    active_ref_radius = min(50.0, max(0.05, active_ref_radius if active_ref_radius > 0 else 5.0))

    if "tab2_compare_ids" not in st.session_state:
        q_comp = st.query_params.get("map_compare_ids")
        if q_comp and str(q_comp).strip():
            st.session_state["tab2_compare_ids"] = [x.strip() for x in str(q_comp).split(",") if x.strip()]

    # Auto-resolve active_ref_prop
    if "tab2_search_prop_id" in st.session_state:
        q_id = st.session_state.get("tab2_search_prop_id")
    else:
        q_id = st.query_params.get("map_ref_id")
    if q_id and df_raw is not None and not df_raw.empty and 'รหัสทรัพย์' in df_raw.columns:
        clean_id = str(q_id).strip()
        if active_ref_prop is None or str(active_ref_prop.get('รหัสทรัพย์', '')).strip().lower() != clean_id.lower():
            found_row = find_property_row_by_code(df_raw, clean_id, include_led_prefix=True)
            if found_row is not None:
                active_ref_prop = found_row
                st.session_state["tab2_ref_prop"] = active_ref_prop
                st.session_state["tab2_search_prop_id"] = clean_id
    elif not q_id:
        st.session_state["tab2_search_prop_id"] = ""
        batch_ref_state = st.session_state.get("tab2_batch_active_ref")
        if (
            isinstance(batch_ref_state, dict)
            and active_ref_lat is not None
            and active_ref_lon is not None
        ):
            active_ref_prop = batch_ref_state
            st.session_state["tab2_ref_prop"] = active_ref_prop
        else:
            active_ref_prop = None
            st.session_state.pop("tab2_ref_prop", None)
            st.session_state.pop("tab2_batch_active_ref", None)

    # Auto-resolve active_price_ref_prop
    if st.session_state.get("tab2_just_reset_price_center"):
        st.session_state["tab2_just_reset_price_center"] = False
        active_price_ref_prop = None
        st.session_state["tab2_price_center_id"] = ""
        st.session_state.pop("tab2_price_ref_prop", None)
    else:
        if "tab2_price_center_id" in st.session_state:
            q_price_id = st.session_state.get("tab2_price_center_id")
        else:
            q_price_id = st.query_params.get("map_price_ref_id")
        if q_price_id and df_raw is not None and not df_raw.empty and 'รหัสทรัพย์' in df_raw.columns:
            clean_price_id = str(q_price_id).strip()
            if active_price_ref_prop is None or str(active_price_ref_prop.get('รหัสทรัพย์', '')).strip().lower() != clean_price_id.lower():
                found_p_row = find_property_row_by_code(df_raw, clean_price_id)
                if found_p_row is not None:
                    active_price_ref_prop = found_p_row
                    st.session_state["tab2_price_ref_prop"] = active_price_ref_prop
                    st.session_state["tab2_price_center_id"] = clean_price_id
        elif not q_price_id:
            active_price_ref_prop = None
            st.session_state["tab2_price_center_id"] = ""
            st.session_state.pop("tab2_price_ref_prop", None)

    # 2. Extract and resolve all current map filters (preferring session_state once initialized)
    if "tab2_filter_provinces" in st.session_state:
        active_prov = st.session_state.get("tab2_filter_provinces", [])
    else:
        q_prov = st.query_params.get("map_prov", None)
        if q_prov and str(q_prov).strip() not in ("ALL", "__ALL__", "all", "", "-"):
            active_prov = [str(q_prov).strip()]
            st.session_state["tab2_filter_provinces"] = active_prov
        else:
            active_prov = []
            st.session_state["tab2_filter_provinces"] = []

    if "tab2_filter_districts" in st.session_state:
        active_dist = st.session_state.get("tab2_filter_districts", []) if active_prov else []
    else:
        q_dist = st.query_params.get("map_dist", None)
        if active_prov and q_dist and str(q_dist).strip() not in ("ALL", "__ALL__", "all", "", "-"):
            active_dist = [str(q_dist).strip()]
            st.session_state["tab2_filter_districts"] = active_dist
        else:
            active_dist = []
            st.session_state["tab2_filter_districts"] = []

    if "tab2_filter_subdistricts" in st.session_state:
        active_subdist = st.session_state.get("tab2_filter_subdistricts", []) if (active_prov and active_dist) else []
    else:
        q_subdist = st.query_params.get("map_subdist", None)
        if active_prov and active_dist and q_subdist and str(q_subdist).strip() not in ("ALL", "__ALL__", "all", "", "-"):
            active_subdist = [str(q_subdist).strip()]
            st.session_state["tab2_filter_subdistricts"] = active_subdist
        else:
            active_subdist = []
            st.session_state["tab2_filter_subdistricts"] = []

    if "tab2_filter_projects" in st.session_state:
        proj_list = st.session_state.get("tab2_filter_projects", [])
        active_proj = ",".join(proj_list) if proj_list else None
    else:
        q_proj = st.query_params.get("map_proj", None)
        if q_proj and str(q_proj).strip() not in ("ALL", "__ALL__", "all", ""):
            proj_list = _parse_multi_filter_param(q_proj, limit=50)
            st.session_state["tab2_filter_projects"] = proj_list
            active_proj = ",".join(proj_list) if proj_list else None
        else:
            active_proj = None
            st.session_state["tab2_filter_projects"] = []

    if "tab2_map_filter_cos" in st.session_state:
        map_cos = st.session_state.get("tab2_map_filter_cos", [])
    else:
        map_cos = _parse_multi_filter_param(st.query_params.get("map_filter_cos", ""))

    if "tab2_map_filter_only_proj" in st.session_state:
        q_only_proj = bool(st.session_state.get("tab2_map_filter_only_proj", False))
    else:
        q_only_proj = st.query_params.get("map_filter_only_proj", "0") in ("1", "true", "True")

    if "tab2_include_centroids" in st.session_state:
        include_centroids = bool(st.session_state.get("tab2_include_centroids", False))
    else:
        include_centroids = st.query_params.get("map_include_centroids", "0") in ("1", "true", "True")
        st.session_state["tab2_include_centroids"] = include_centroids

    if "tab2_map_filter_types" in st.session_state:
        map_types = st.session_state.get("tab2_map_filter_types", [])
    else:
        map_types = _parse_multi_filter_param(st.query_params.get("map_filter_types", ""))

    if "tab2_map_filter_sales" in st.session_state:
        map_sales = st.session_state.get("tab2_map_filter_sales", [])
    else:
        map_sales = _parse_multi_filter_param(st.query_params.get("map_filter_sales", ""))

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

    if "tab2_map_filter_floors" in st.session_state:
        map_floors = st.session_state.get("tab2_map_filter_floors", [])
    else:
        map_floors = _parse_multi_filter_param(st.query_params.get("map_filter_floors", ""))
    map_min_fl = _read_num_filter("tab2_map_filter_min_fl", "map_filter_min_fl")
    map_max_fl = _read_num_filter("tab2_map_filter_max_fl", "map_filter_max_fl")
    if "tab2_map_filter_beds" in st.session_state:
        map_beds = st.session_state.get("tab2_map_filter_beds", [])
    else:
        map_beds = _parse_multi_filter_param(st.query_params.get("map_filter_beds", ""))
    if "tab2_map_filter_baths" in st.session_state:
        map_baths = st.session_state.get("tab2_map_filter_baths", [])
    else:
        map_baths = _parse_multi_filter_param(st.query_params.get("map_filter_baths", ""))
    if "tab2_map_filter_pkgs" in st.session_state:
        map_pkgs = st.session_state.get("tab2_map_filter_pkgs", [])
    else:
        map_pkgs = _parse_multi_filter_param(st.query_params.get("map_filter_pkgs", ""))
    map_max_age = _read_num_filter("tab2_map_filter_max_age", "map_filter_max_age")

    pin_mode = st.session_state.get("tab2_pin_mode") or st.query_params.get("map_pin_mode", "radius")
    has_ref_point = _is_valid_thai_coord(active_ref_lat, active_ref_lon)
    has_loc_filter = bool(active_prov or active_dist or active_subdist or active_proj)
    active_compare_ids = st.session_state.get("tab2_compare_ids", [])

    is_province_only = bool(
        active_prov
        and not active_dist
        and not active_subdist
        and not active_proj
        and not has_ref_point
        and active_ref_prop is None
        and not active_compare_ids
    )

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
        "include_centroids": include_centroids,
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
        "is_province_only": is_province_only,
        "has_any_filter": has_any_filter,
    }
