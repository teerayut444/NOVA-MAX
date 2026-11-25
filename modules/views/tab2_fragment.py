"""Tab 2 reference analytics fragment orchestrator.

Delegates metric/unit calculations to ``tab2_metrics``, map-iframe state sync to
``tab2_state``, and table/export rendering to ``tab2_table`` while preserving all
legacy symbol exports for backwards compatibility.
"""

import html
import re
import numpy as np
import pandas as pd
import streamlit as st

from modules.services.geo_service import find_nearby_properties
from modules.services.data_cleaner import (
    to_float_sqwah,
    normalize_project_name,
    parse_listing_age_days,
    parse_sold_date_value,
)
from modules.services.data_loader import get_data_mtime as _get_mtime_t2
from modules.ui.kpi_header import format_price_kpi

from modules.views.tab2_metrics import (
    CONDO_PATTERN,
    _INVALID_LOC_TOKENS,
    _FILENAME_CLEAN_RE,
    _sqw_from_df,
    _sqm_from_df,
    _sqw_rate_from_df,
    _sqm_rate_from_df,
    _safe_float,
    _is_valid_thai_coord,
    _fmt_coord_val,
    _check_pure_land_mask_global,
    _extract_pure_land_pool_global,
    _get_cached_nationwide_pure_land,
    _clean_str_series,
    _match_project_mask,
    _extract_asset_unit_rates,
)
from modules.views.tab2_state import (
    _reset_price_center_callback,
    _sync_num_filter,
    _read_num_filter,
    resolve_tab2_sync_and_filter_state,
)
from modules.views.tab2_table import (
    _compute_df_content_fp,
    _build_tab2_show_df_uncached,
    _build_tab2_show_df_cached,
    precompute_tab2_default_analytics,
    render_tab2_nearby_table_and_export,
)

__all__ = [
    "CONDO_PATTERN",
    "to_float_sqwah",
    "_sqw_from_df",
    "_sqm_from_df",
    "_sqw_rate_from_df",
    "_sqm_rate_from_df",
    "_compute_df_content_fp",
    "_build_tab2_show_df_uncached",
    "_build_tab2_show_df_cached",
    "precompute_tab2_default_analytics",
    "_reset_price_center_callback",
    "render_tab2_reference_analytics_fragment",
]

fragment_decorator = getattr(st, "fragment", lambda f: f)


@st.cache_resource(show_spinner=False, max_entries=2)
def _get_scattered_project_nks_cached(_df, cache_key=None):
    """Cached computation of spatially scattered normalized project keys for Tab 2 'มีโครงการ' parity."""
    from modules.services.data_cleaner import find_spatially_scattered_project_keys
    return find_spatially_scattered_project_keys(
        _df,
        group_col='norm_project_name',
        max_median_km=5.0,
        max_pair_km=10.0,
    )


@fragment_decorator
def render_tab2_reference_analytics_fragment(
    df_raw,
    is_dark_mode,
    active_ref_lat,
    active_ref_lon,
    active_ref_prop,
    active_price_ref_prop=None,
    active_ref_radius=5.0,
    tab2_types=None
):
    """
    Renders the live reference analytics fragment below the Tab 2 Leaflet map:
    - Hidden sync bridge with Leaflet iframe (two-way state syncing)
    - Active filter status chip banner
    - Dynamic median price benchmark cards (Total assets, landed sq.wah, pure land, sq.metre)
    - Detailed comparative dataframe with up/down delta badges
    - CSV/Excel export section
    """
    if active_ref_prop is not None and isinstance(active_ref_prop, pd.Series):
        active_ref_prop = active_ref_prop.to_dict()
    if active_price_ref_prop is not None and isinstance(active_price_ref_prop, pd.Series):
        active_price_ref_prop = active_price_ref_prop.to_dict()

    if st.session_state.pop("tab2_inject_clear_price_center_js", False):
        st.html(
            """
            <script>
            (function() {
                try {
                    var targetOrigin = window.location.origin;
                    var u = new URL(window.parent.location.href);
                    u.searchParams.delete('map_price_ref_id');
                    window.parent.history.replaceState({}, '', u.toString());
                    var iframes = window.parent.document.querySelectorAll('iframe');
                    iframes.forEach(function(f) {
                        try {
                            if (f.contentWindow) {
                                if (typeof f.contentWindow.clearPriceCenter === 'function') {
                                    f.contentWindow.clearPriceCenter();
                                } else {
                                    f.contentWindow.postMessage({ action: 'clear_price_center' }, targetOrigin);
                                }
                            }
                        } catch(e) {}
                    });
                } catch(e) {}
            })();
            </script>
            """,
            unsafe_allow_javascript=True,
        )

    if st.session_state.get("tab2_just_reset_price_center"):
        active_price_ref_prop = None
        st.session_state["tab2_price_center_id"] = ""
        st.session_state.pop("tab2_price_ref_prop", None)
        try:
            st.query_params.pop("map_price_ref_id", None)
        except Exception:
            pass

    # Ensure Tab 2 reference analytics strictly operates on properties with valid coordinates (avoid full copy if all valid)
    if df_raw is not None and not df_raw.empty and 'ละติจูด' in df_raw.columns and 'ลองจิจูด' in df_raw.columns:
        valid_coords_mask = (
            df_raw['ละติจูด'].notna() & df_raw['ลองจิจูด'].notna() &
            df_raw['ละติจูด'].between(5, 21) & df_raw['ลองจิจูด'].between(97, 106)
        )
        if not bool(valid_coords_mask.all()):
            df_raw = df_raw.loc[valid_coords_mask]


    # 0–2. Process map sync bridge and resolve all coordinates, reference props, and active filters
    _state = resolve_tab2_sync_and_filter_state(
        df_raw,
        active_ref_lat=active_ref_lat,
        active_ref_lon=active_ref_lon,
        active_ref_prop=active_ref_prop,
        active_price_ref_prop=active_price_ref_prop,
        active_ref_radius=active_ref_radius,
    )
    active_ref_lat = _state["active_ref_lat"]
    active_ref_lon = _state["active_ref_lon"]
    active_ref_radius = _state["active_ref_radius"]
    active_ref_prop = _state["active_ref_prop"]
    active_price_ref_prop = _state["active_price_ref_prop"]
    active_prov = _state["active_prov"]
    active_dist = _state["active_dist"]
    active_subdist = _state["active_subdist"]
    active_proj = _state["active_proj"]
    map_cos = _state["map_cos"]
    q_only_proj = _state["q_only_proj"]
    map_types = _state["map_types"]
    map_sales = _state["map_sales"]
    map_min_p = _state["map_min_p"]
    map_max_p = _state["map_max_p"]
    map_min_sqw = _state["map_min_sqw"]
    map_max_sqw = _state["map_max_sqw"]
    map_min_sqm = _state["map_min_sqm"]
    map_max_sqm = _state["map_max_sqm"]
    map_min_puw = _state["map_min_puw"]
    map_max_puw = _state["map_max_puw"]
    map_min_pum = _state["map_min_pum"]
    map_max_pum = _state["map_max_pum"]
    map_floors = _state["map_floors"]
    map_min_fl = _state["map_min_fl"]
    map_max_fl = _state["map_max_fl"]
    map_beds = _state["map_beds"]
    map_baths = _state["map_baths"]
    map_pkgs = _state["map_pkgs"]
    map_max_age = _state["map_max_age"]
    pin_mode = _state["pin_mode"]
    has_ref_point = _state["has_ref_point"]
    has_loc_filter = _state["has_loc_filter"]
    active_compare_ids = _state["active_compare_ids"]
    is_province_only = bool(_state.get("is_province_only", False))
    has_any_filter = _state["has_any_filter"]

    # 3. Compute matching DataFrame for Filter Status Bar & Analytics
    status_df = df_raw if df_raw is not None else pd.DataFrame()
    is_comparison_active = False
    if active_compare_ids and df_raw is not None and not df_raw.empty and 'รหัสทรัพย์' in df_raw.columns:
        cids_set = {str(x).strip().lower() for x in active_compare_ids if str(x).strip()}
        if cids_set:
            comp_match = df_raw[df_raw['รหัสทรัพย์'].astype(str).str.strip().str.lower().isin(cids_set)]
            if not comp_match.empty:
                status_df = comp_match.copy()
                is_comparison_active = True

    if not is_comparison_active and has_any_filter and not status_df.empty:
        if active_proj:
            p_list = [p.strip() for p in active_proj.split(",") if p.strip()]
            status_df = status_df[_match_project_mask(status_df, p_list)]
            if active_prov and 'จังหวัด' in status_df.columns:
                status_df = status_df[status_df['จังหวัด'].astype(str).str.strip().isin(active_prov)]
            if active_dist and 'อำเภอ' in status_df.columns:
                clean_target_dists = [d.split(' (')[0].strip() for d in active_dist]
                status_df = status_df[status_df['อำเภอ'].astype(str).str.strip().isin(clean_target_dists)]
            if active_subdist and 'ตำบล' in status_df.columns:
                clean_target_subs = [s.split(' (')[0].strip() for s in active_subdist]
                status_df = status_df[status_df['ตำบล'].astype(str).str.strip().isin(clean_target_subs)]
        elif has_ref_point and (pin_mode == 'radius' or not has_loc_filter):
            status_df = find_nearby_properties(active_ref_lat, active_ref_lon, status_df, active_ref_radius)
        elif active_prov:
            if 'จังหวัด' in status_df.columns:
                status_df = status_df[status_df['จังหวัด'].astype(str).str.strip().isin(active_prov)]
            if active_dist and 'อำเภอ' in status_df.columns:
                clean_target_dists = [d.split(' (')[0].strip() for d in active_dist]
                status_df = status_df[status_df['อำเภอ'].astype(str).str.strip().isin(clean_target_dists)]
            if active_subdist and 'ตำบล' in status_df.columns:
                clean_target_subs = [s.split(' (')[0].strip() for s in active_subdist]
                status_df = status_df[status_df['ตำบล'].astype(str).str.strip().isin(clean_target_subs)]

        if not status_df.empty:
            if map_cos and 'บริษัท' in status_df.columns:
                status_df = status_df[status_df['บริษัท'].isin(map_cos)]
            if map_types and 'ประเภททรัพย์' in status_df.columns:
                status_df = status_df[status_df['ประเภททรัพย์'].isin(map_types)]
            if map_sales:
                col_sale = 'ประเภทการขาย' if 'ประเภทการขาย' in status_df.columns else ('สถานะ' if 'สถานะ' in status_df.columns else None)
                if col_sale:
                    status_df = status_df[status_df[col_sale].isin(map_sales)]
            if (map_min_p > 0 or map_max_p > 0) and 'ราคา' in status_df.columns:
                p_col_num = pd.to_numeric(status_df['ราคา'], errors='coerce')
                p_mask = pd.Series(True, index=status_df.index)
                if map_min_p > 0:
                    p_mask &= (p_col_num >= map_min_p)
                if map_max_p > 0:
                    p_mask &= (p_col_num <= map_max_p)
                status_df = status_df[p_mask]

            if map_min_sqw > 0 or map_max_sqw > 0:
                sqw_s = _sqw_from_df(status_df)
                sqw_mask = pd.Series(True, index=status_df.index)
                if map_min_sqw > 0:
                    sqw_mask &= (sqw_s >= map_min_sqw)
                if map_max_sqw > 0:
                    sqw_mask &= (sqw_s <= map_max_sqw)
                status_df = status_df[sqw_mask]

            if (map_min_sqm > 0 or map_max_sqm > 0) and 'พื้นที่ใช้สอย (ตร.ม.)' in status_df.columns:
                sqm_s = _sqm_from_df(status_df)
                sqm_mask = pd.Series(True, index=status_df.index)
                if map_min_sqm > 0:
                    sqm_mask &= (sqm_s >= map_min_sqm)
                if map_max_sqm > 0:
                    sqm_mask &= (sqm_s <= map_max_sqm)
                status_df = status_df[sqm_mask]

            if map_min_puw > 0 or map_max_puw > 0:
                puw_final = _sqw_rate_from_df(status_df)
                puw_mask = pd.Series(True, index=status_df.index)
                if map_min_puw > 0:
                    puw_mask &= (puw_final >= map_min_puw)
                if map_max_puw > 0:
                    puw_mask &= (puw_final <= map_max_puw)
                status_df = status_df[puw_mask]

            if map_min_pum > 0 or map_max_pum > 0:
                pum_final = _sqm_rate_from_df(status_df)
                pum_mask = pd.Series(True, index=status_df.index)
                if map_min_pum > 0:
                    pum_mask &= (pum_final >= map_min_pum)
                if map_max_pum > 0:
                    pum_mask &= (pum_final <= map_max_pum)
                status_df = status_df[pum_mask]

            if (map_floors or map_min_fl > 0 or map_max_fl > 0) and 'ชั้น' in status_df.columns and not status_df.empty:
                fl_s = status_df['ชั้น']
                fl_num = pd.to_numeric(fl_s, errors='coerce')
                fl_str = fl_s.astype(object).fillna('').astype(str)
                needs_ex = fl_num.isna() & fl_str.str.contains(r'\d', na=False)
                extracted_fl = pd.to_numeric(fl_str[needs_ex].str.extract(r'(\d+(?:\.\d+)?)', expand=False), errors='coerce')
                fl_val = np.where(fl_num.notna() & (fl_num >= 0), fl_num, -1.0)
                if needs_ex.any():
                    fl_val[needs_ex.to_numpy()] = np.where(extracted_fl.notna() & (extracted_fl >= 0), extracted_fl, -1.0)
                fl_series = pd.Series(fl_val, index=status_df.index)

                fl_mask = pd.Series(False, index=status_df.index)
                if map_floors:
                    if 'none' in map_floors:
                        fl_mask |= (fl_series < 0)
                    if '1' in map_floors:
                        fl_mask |= ((fl_series >= 1) & (fl_series < 2))
                    if '2' in map_floors:
                        fl_mask |= ((fl_series >= 2) & (fl_series < 3))
                    if '3' in map_floors:
                        fl_mask |= ((fl_series >= 3) & (fl_series < 4))
                    if '4+' in map_floors:
                        fl_mask |= (fl_series >= 4)
                else:
                    fl_mask = pd.Series(True, index=status_df.index)
                if map_min_fl > 0:
                    fl_mask &= (fl_series >= map_min_fl)
                if map_max_fl > 0:
                    fl_mask &= (fl_series >= 0) & (fl_series <= map_max_fl)
                status_df = status_df[fl_mask]

            if map_beds and 'ห้องนอน' in status_df.columns and not status_df.empty:
                bed_s = status_df['ห้องนอน']
                bed_num = pd.to_numeric(bed_s, errors='coerce')
                is_std = bed_s.astype(object).fillna('').astype(str).str.contains('สตูดิโอ|studio', case=False, na=False)
                bed_val = np.where(is_std, 0.0, np.where(bed_num.notna() & (bed_num >= 0), bed_num, -1.0))
                bed_series = pd.Series(bed_val, index=status_df.index)

                bed_mask = pd.Series(False, index=status_df.index)
                if 'none' in map_beds:
                    bed_mask |= (bed_series < 0)
                if '0' in map_beds:
                    bed_mask |= (bed_series == 0)
                for n in (1, 2, 3, 4):
                    if str(n) in map_beds:
                        bed_mask |= (bed_series.round() == n)
                if '5+' in map_beds:
                    bed_mask |= (bed_series >= 5)
                status_df = status_df[bed_mask]

            if map_baths and 'ห้องน้ำ' in status_df.columns and not status_df.empty:
                bath_num = pd.to_numeric(status_df['ห้องน้ำ'], errors='coerce')
                bath_series = pd.Series(np.where(bath_num.notna() & (bath_num >= 0), bath_num, -1.0), index=status_df.index)

                bath_mask = pd.Series(False, index=status_df.index)
                if 'none' in map_baths:
                    bath_mask |= (bath_series < 0)
                for n in (1, 2, 3, 4):
                    if str(n) in map_baths:
                        bath_mask |= (bath_series.round() == n)
                if '5+' in map_baths:
                    bath_mask |= (bath_series >= 5)
                status_df = status_df[bath_mask]

            if map_pkgs and 'ที่จอดรถ' in status_df.columns and not status_df.empty:
                pkg_num = pd.to_numeric(status_df['ที่จอดรถ'], errors='coerce')
                pkg_series = pd.Series(np.where(pkg_num.notna() & (pkg_num >= 0), pkg_num, -1.0), index=status_df.index)

                pkg_mask = pd.Series(False, index=status_df.index)
                if 'none' in map_pkgs:
                    pkg_mask |= (pkg_series < 0)
                for n in (1, 2, 3):
                    if str(n) in map_pkgs:
                        pkg_mask |= (pkg_series.round() == n)
                if '4+' in map_pkgs:
                    pkg_mask |= (pkg_series >= 4)
                status_df = status_df[pkg_mask]

            if map_max_age > 0 and 'วันประกาศ' in status_df.columns and not status_df.empty:
                u_ann = status_df['วันประกาศ'].dropna().unique()
                age_map = {u: parse_listing_age_days(u) for u in u_ann}
                age_series = status_df['วันประกาศ'].map(age_map).fillna(-1.0).copy()
                if 'วันที่ขาย' in status_df.columns and 'บริษัท' in status_df.columns:
                    is_legal = status_df['บริษัท'].astype(str).str.strip().str.upper().isin(['LED LEGAL', 'LED_LEGAL', 'LED_SOLD'])
                    has_sold = status_df['วันที่ขาย'].notna() & (~status_df['วันที่ขาย'].astype(str).str.strip().isin(['', '-', 'nan', 'None', '<NA>']))
                    l_mask = is_legal & has_sold & status_df['วันประกาศ'].notna()
                    if l_mask.any():
                        sub_pairs = status_df.loc[l_mask, ['วันประกาศ', 'วันที่ขาย']].astype(object).drop_duplicates()
                        l_pair_map = {}
                        for ann_v, sold_v in sub_pairs.itertuples(index=False, name=None):
                            s_dt = parse_sold_date_value(sold_v)
                            if pd.notna(s_dt):
                                d_diff = parse_listing_age_days(ann_v, ref_date=s_dt.date())
                                if d_diff >= 0:
                                    l_pair_map[(ann_v, sold_v)] = float(d_diff)
                        if l_pair_map:
                            l_vals = [
                                l_pair_map.get((a, s))
                                for a, s in zip(status_df.loc[l_mask, 'วันประกาศ'].astype(object), status_df.loc[l_mask, 'วันที่ขาย'].astype(object))
                            ]
                            valid_l = [v is not None for v in l_vals]
                            if any(valid_l):
                                age_series.loc[status_df.loc[l_mask].index[valid_l]] = [v for v in l_vals if v is not None]
                status_df = status_df[(age_series >= 0) & (age_series <= map_max_age)]

            if q_only_proj and 'ชื่อโครงการ' in status_df.columns and not status_df.empty:
                from modules.services.data_cleaner import (
                    is_invalid_project_name,
                    find_spatially_scattered_project_keys,
                )
                proj_col = 'ชื่อโครงการ'
                p_str = status_df[proj_col].astype(object).fillna('').astype(str).str.strip()
                u_p_vals = p_str.unique()
                inv_p_set = {v for v in u_p_vals if not v or v == '-' or is_invalid_project_name(v)}
                valid_proj_mask = status_df[proj_col].notna() & (~p_str.isin(inv_p_set))
                status_df = status_df[valid_proj_mask]

                # Exclude spatially scattered project keys (aligned with Map Project Index)
                if not status_df.empty and 'ละติจูด' in status_df.columns and 'ลองจิจูด' in status_df.columns:
                    if 'norm_project_name' in status_df.columns:
                        _nk_col = status_df['norm_project_name'].astype(object).fillna('').astype(str).str.strip()
                    else:
                        _u_p2 = status_df[proj_col].dropna().unique()
                        _nk_col = status_df[proj_col].map({v: normalize_project_name(v) for v in _u_p2 if v}).fillna('')
                    _scat_src = df_raw if (df_raw is not None and not df_raw.empty and 'norm_project_name' in df_raw.columns) else status_df
                    if 'norm_project_name' in _scat_src.columns:
                        _scat_nks = _get_scattered_project_nks_cached(
                            _scat_src,
                            cache_key=(_get_mtime_t2(), len(_scat_src)),
                        )
                    else:
                        _tmp_sc = pd.DataFrame({'_nk': _nk_col, 'ละติจูด': status_df['ละติจูด'], 'ลองจิจูด': status_df['ลองจิจูด']})
                        _scat_nks = find_spatially_scattered_project_keys(_tmp_sc, group_col='_nk', max_median_km=5.0, max_pair_km=10.0)
                    if _scat_nks:
                        status_df = status_df[~_nk_col.isin(_scat_nks)]

                if map_cos and len(map_cos) >= 2 and 'บริษัท' in status_df.columns and not status_df.empty:
                    df_cos_proj = status_df[status_df['บริษัท'].isin(map_cos)].copy()
                    if 'norm_project_name' in df_cos_proj.columns:
                        norm_p_s = df_cos_proj['norm_project_name'].astype(object).fillna('').astype(str).str.strip()
                    else:
                        norm_p_s = df_cos_proj[proj_col].astype(object).fillna('').astype(str).map(normalize_project_name)
                    # Exclude empty normalized names so non-matching projects never clump under ''
                    df_cos_proj = df_cos_proj[norm_p_s != ''].copy()
                    df_cos_proj['_norm_p'] = norm_p_s[norm_p_s != '']
                    proj_company_counts = df_cos_proj.groupby('_norm_p', observed=False)['บริษัท'].nunique()
                    shared_norms = set(proj_company_counts[proj_company_counts >= 2].index)
                    norm_s = (
                        status_df['norm_project_name'].astype(object).fillna('').astype(str).str.strip()
                        if 'norm_project_name' in status_df.columns
                        else status_df[proj_col].astype(object).fillna('').astype(str).map(normalize_project_name)
                    )
                    status_df = status_df[norm_s.isin(shared_norms)]

        status_df = status_df.copy()

    matched_count = len(status_df)

    # Human-readable labels
    if active_proj:
        loc_str = f"โครงการ: {active_proj}"
        if active_prov:
            clean_d = active_dist[0].split(' (')[0].strip() if active_dist else ""
            clean_s = active_subdist[0].split(' (')[0].strip() if active_subdist else ""
            loc_parts = [f"จ.{active_prov[0]}"]
            if clean_d:
                loc_parts.append(f"อ.{clean_d}")
            if clean_s:
                loc_parts.append(f"ต.{clean_s}")
            loc_str += f" ({' > '.join(loc_parts)})"
    elif has_ref_point and (pin_mode == 'radius' or not has_loc_filter):
        if active_subdist:
            clean_s = active_subdist[0].split(' (')[0].strip()
            clean_d = active_dist[0].split(' (')[0].strip() if active_dist else "-"
            loc_str = f"จุดศูนย์กลาง: จ.{active_prov[0] if active_prov else '-'} > อ.{clean_d} > ต.{clean_s}"
        elif active_dist:
            clean_d = active_dist[0].split(' (')[0].strip()
            loc_str = f"จุดศูนย์กลาง: จ.{active_prov[0] if active_prov else '-'} > อ.{clean_d}"
        elif active_prov:
            loc_str = f"จุดศูนย์กลาง: จ.{active_prov[0]}"
        else:
            loc_str = "ตามพิกัดจุดอ้างอิง (ครอบคลุมตามรัศมี)"
    elif active_subdist:
        clean_s = active_subdist[0].split(' (')[0].strip()
        clean_d = active_dist[0].split(' (')[0].strip() if active_dist else "-"
        loc_str = f"จ.{active_prov[0] if active_prov else '-'} > อ.{clean_d} > ต.{clean_s}"
    elif active_dist:
        clean_d = active_dist[0].split(' (')[0].strip()
        loc_str = f"จ.{active_prov[0] if active_prov else '-'} > อ.{clean_d}"
    elif active_prov:
        loc_str = f"จ.{active_prov[0]}"
    elif q_only_proj and map_cos and len(map_cos) >= 2:
        loc_str = f"โครงการร่วมกัน ({' + '.join(map_cos)}) ทั่วประเทศ"
    else:
        loc_str = "ทุกทำเล (ทั่วประเทศ)"

    if has_ref_point:
        if active_ref_prop is not None:
            rad_str = f"{active_ref_radius:.1f} กม. รอบ [{active_ref_prop.get('บริษัท', '-')}] {active_ref_prop.get('รหัสทรัพย์', '')}"
        else:
            rad_str = f"{active_ref_radius:.1f} กม. ({active_ref_lat:.4f}, {active_ref_lon:.4f})"
    else:
        rad_str = f"รัศมี {active_ref_radius:.1f} กม. (ยังไม่ได้ปักหมุด)"

    if q_only_proj and map_cos and len(map_cos) >= 2:
        cos_str = f"{', '.join(map_cos)} (โครงการร่วมกัน)"
    elif q_only_proj:
        cos_str = f"{', '.join(map_cos)} (เฉพาะมีโครงการ)" if map_cos else "ทุกบริษัท (เฉพาะมีโครงการ)"
    else:
        cos_str = f"{', '.join(map_cos)} ({len(map_cos)} บริษัท)" if map_cos else "ทุกบริษัท"
    types_str = f"{', '.join(map_types)}" if map_types else "ทุกประเภททรัพย์"

    if map_min_p > 0 and map_max_p > 0:
        price_parts = [f"{format_price_kpi(map_min_p)} - {format_price_kpi(map_max_p)}"]
    elif map_min_p > 0:
        price_parts = [f">= {format_price_kpi(map_min_p)}"]
    elif map_max_p > 0:
        price_parts = [f"<= {format_price_kpi(map_max_p)}"]
    else:
        price_parts = []

    if map_min_puw > 0 and map_max_puw > 0:
        price_parts.append(f"{format_price_kpi(map_min_puw)}-{format_price_kpi(map_max_puw)}/ตร.ว.")
    elif map_min_puw > 0:
        price_parts.append(f">= {format_price_kpi(map_min_puw)}/ตร.ว.")
    elif map_max_puw > 0:
        price_parts.append(f"<= {format_price_kpi(map_max_puw)}/ตร.ว.")

    if map_min_pum > 0 and map_max_pum > 0:
        price_parts.append(f"{format_price_kpi(map_min_pum)}-{format_price_kpi(map_max_pum)}/ตร.ม.")
    elif map_min_pum > 0:
        price_parts.append(f">= {format_price_kpi(map_min_pum)}/ตร.ม.")
    elif map_max_pum > 0:
        price_parts.append(f"<= {format_price_kpi(map_max_pum)}/ตร.ม.")

    price_str = " · ".join(price_parts) if price_parts else "ทุกช่วงราคา"

    area_parts = []
    if map_min_sqw > 0 or map_max_sqw > 0:
        area_parts.append(f"{map_min_sqw:,.0f}-{map_max_sqw:,.0f} ตร.ว." if map_max_sqw > 0 else f">= {map_min_sqw:,.0f} ตร.ว.")
    if map_min_sqm > 0 or map_max_sqm > 0:
        area_parts.append(f"{map_min_sqm:,.0f}-{map_max_sqm:,.0f} ตร.ม." if map_max_sqm > 0 else f">= {map_min_sqm:,.0f} ตร.ม.")
    area_str = " / ".join(area_parts) if area_parts else "ทุกขนาด (ทุก Plan)"

    floor_parts = []
    if map_floors:
        fl_map_lbl = {'1': '1 ชั้น', '2': '2 ชั้น', '3': '3 ชั้น', '4+': '4+ ชั้น', 'none': 'ไม่ระบุ'}
        floor_parts.append(", ".join(fl_map_lbl.get(c, c) for c in map_floors))
    if map_min_fl > 0 and map_max_fl > 0:
        floor_parts.append(f"ชั้น {map_min_fl:,.0f}-{map_max_fl:,.0f}")
    elif map_min_fl > 0:
        floor_parts.append(f">= ชั้น {map_min_fl:,.0f}")
    elif map_max_fl > 0:
        floor_parts.append(f"<= ชั้น {map_max_fl:,.0f}")
    floor_str = " / ".join(floor_parts) if floor_parts else "ทุกชั้น"

    spec_parts = []
    if map_beds:
        b_lbl = {'0': 'สตูดิโอ', '1': '1 นอน', '2': '2 นอน', '3': '3 นอน', '4': '4 นอน', '5+': '5+ นอน', 'none': 'นอน(ไม่ระบุ)'}
        spec_parts.append(", ".join(b_lbl.get(b, b) for b in map_beds))
    if map_baths:
        ba_lbl = {'1': '1 น้ำ', '2': '2 น้ำ', '3': '3 น้ำ', '4': '4 น้ำ', '5+': '5+ น้ำ', 'none': 'น้ำ(ไม่ระบุ)'}
        spec_parts.append(", ".join(ba_lbl.get(b, b) for b in map_baths))
    if map_pkgs:
        pk_lbl = {'1': '1 จอด', '2': '2 จอด', '3': '3 จอด', '4+': '4+ จอด', 'none': 'จอด(ไม่ระบุ)'}
        spec_parts.append(", ".join(pk_lbl.get(p, p) for p in map_pkgs))
    spec_str = " · ".join(spec_parts) if spec_parts else "ทุกสเปกห้อง/ที่จอด"

    if map_max_age > 0:
        if map_max_age >= 365:
            age_str = f"<= {map_max_age/365:,.1f} ปี" if map_max_age % 365 != 0 else f"<= {int(map_max_age/365)} ปี"
        else:
            age_str = f"<= {int(map_max_age)} วัน"
    else:
        age_str = "ทุกระยะเวลา"

    is_loc_active = bool(
        active_proj
        or (has_ref_point and (pin_mode == 'radius' or not has_loc_filter))
        or active_subdist
        or active_dist
        or active_prov
        or (q_only_proj and map_cos and len(map_cos) >= 2)
    )
    is_rad_active = bool(has_ref_point and not active_proj and (pin_mode == 'radius' or not has_loc_filter))
    is_co_active = bool(map_cos or q_only_proj)
    is_type_active = bool(map_types)
    is_price_active = bool(price_parts)
    is_area_active = bool(area_parts)
    is_floor_active = bool(floor_parts)
    is_spec_active = bool(spec_parts)
    is_age_active = bool(map_max_age > 0)

    def _chip_attrs(is_active):
        cls = "map-filter-chip" if is_active else "map-filter-chip is-inactive"
        flag = "true" if is_active else "false"
        return f'class="{cls}" data-active="{flag}"'

    mode_badge_lbl = "ตามรัศมี (Radius)" if (has_ref_point and pin_mode == 'radius') else "ตามทำเล (Location)"

    banner_theme = "dark" if is_dark_mode else "light"
    card_bg = "rgba(2, 44, 34, 0.45)" if is_dark_mode else "#f8fafc"
    card_border = "rgba(52, 211, 153, 0.35)" if is_dark_mode else "#e2e8f0"
    chip_border = "rgba(52, 211, 153, 0.25)" if is_dark_mode else "#e2e8f0"

    # --- RENDER FILTER STATUS BANNER ---
    st.markdown(f"""
    <div id='ref-analytics-section' style='height: 0px; margin: 0px; padding: 0px; scroll-margin-top: 80px;'></div>
    <div id="map-active-filters-banner" data-theme="{banner_theme}" style="background: {card_bg}; border: 1.5px solid {card_border}; border-radius: 14px; padding: 12px 16px; margin-top: -18px; margin-bottom: 12px; position: relative; z-index: 10; box-shadow: 0 4px 14px rgba(0,0,0,0.04);">
        <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px; margin-bottom: 10px; padding-bottom: 8px; border-bottom: 1px solid {chip_border};">
            <div style="display: flex; align-items: center; gap: 8px;">
                <span style="background: linear-gradient(135deg, #059669, #10b981); color: #ffffff; padding: 3px 10px; border-radius: 6px; font-size: 0.78rem; font-weight: 800; display: inline-flex; align-items: center; gap: 5px;">
                    <i class="fa-solid fa-sliders"></i> สถานะตัวกรองแผนที่ (Active Map Filters)
                </span>
                <span style="font-size: 0.82rem; font-weight: 700; color: #10b981;" id="active-filter-mode-val">
                    โหมด: <b>{mode_badge_lbl}</b>
                </span>
            </div>
            <div style="font-size: 0.82rem; font-weight: 700; color: #059669; background: rgba(16, 185, 129, 0.12); padding: 3px 10px; border-radius: 20px; display: inline-flex; align-items: center; gap: 5px;" id="active-filter-count-val">
                <i class="fa-solid fa-layer-group"></i> ทรัพย์ที่ตรงเงื่อนไข: <b>{matched_count:,}</b> รายการ
            </div>
        </div>
        <div style="display: flex; flex-wrap: wrap; gap: 6px; align-items: center;">
            <div {_chip_attrs(is_loc_active)} style="max-width: 100%;" title="ทำเล (Location)">
                <i class="fa-solid fa-location-dot" style="color: #10b981;"></i>
                <span id="active-filter-loc-val" class="map-filter-chip-label" style="overflow: hidden; text-overflow: ellipsis; max-width: 320px;">
                    {html.escape(str(loc_str))}
                </span>
            </div>
            <div {_chip_attrs(is_rad_active)} title="รัศมีตรวจ (Radius)">
                <i class="fa-solid fa-bullseye" style="color: #06b6d4;"></i>
                <span id="active-filter-rad-val" class="map-filter-chip-label">
                    {html.escape(str(rad_str))}
                </span>
            </div>
            <div {_chip_attrs(is_co_active)} title="บริษัท (Company)">
                <i class="fa-solid fa-building" style="color: #3b82f6;"></i>
                <span id="active-filter-co-val" class="map-filter-chip-label">
                    {html.escape(str(cos_str))}
                </span>
            </div>
            <div {_chip_attrs(is_type_active)} title="ประเภททรัพย์ (Type)">
                <i class="fa-solid fa-house" style="color: #f59e0b;"></i>
                <span id="active-filter-type-val" class="map-filter-chip-label">
                    {html.escape(str(types_str))}
                </span>
            </div>
            <div {_chip_attrs(is_price_active)} title="ราคา (Price)">
                <i class="fa-solid fa-tag" style="color: #10b981;"></i>
                <span id="active-filter-price-val" class="map-filter-chip-label">
                    {html.escape(str(price_str))}
                </span>
            </div>
            <div {_chip_attrs(is_area_active)} title="ขนาด/Plan (Area)">
                <i class="fa-solid fa-ruler-combined" style="color: #8b5cf6;"></i>
                <span id="active-filter-area-val" class="map-filter-chip-label">
                    {html.escape(str(area_str))}
                </span>
            </div>
            <div {_chip_attrs(is_floor_active)} title="ชั้น (Floor)">
                <i class="fa-solid fa-stairs" style="color: #6366f1;"></i>
                <span id="active-filter-floor-val" class="map-filter-chip-label">
                    {html.escape(str(floor_str))}
                </span>
            </div>
            <div {_chip_attrs(is_spec_active)} title="ห้อง/ที่จอด (Room/Parking)">
                <i class="fa-solid fa-bed" style="color: #ec4899;"></i>
                <span id="active-filter-spec-val" class="map-filter-chip-label">
                    {html.escape(str(spec_str))}
                </span>
            </div>
            <div {_chip_attrs(is_age_active)} title="อายุประกาศ (Age)">
                <i class="fa-solid fa-calendar-days" style="color: #0284c7;"></i>
                <span id="active-filter-age-val" class="map-filter-chip-label">
                    {html.escape(str(age_str))}
                </span>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # 4. Require at least one active location/pin, comparison selection, or in-map filter
    if not has_any_filter:
        st.info("กรุณาปักหมุดบนแผนที่ หรือเลือกตัวกรอง/ทำเล เพื่อเริ่มดูข้อมูล", icon=":material/location_on:")
        return
    if is_province_only:
        st.info("กรุณาเลือกอำเภอ/เขต หรือตำบล/แขวง เพื่อแสดงหมุดและข้อมูลวิเคราะห์", icon=":material/location_on:")
        return

    # 5. Scope Header
    if has_ref_point and (pin_mode == 'radius' or not has_loc_filter) and not active_proj:
        scope_header = f"ในรัศมี {active_ref_radius:.1f} กม. รอบจุดอ้างอิง"
    elif active_proj:
        prov_tag = f" จังหวัด{active_prov[0]}" if active_prov else ""
        scope_header = f"ในโครงการ {active_proj}{prov_tag}"
    else:
        if active_subdist:
            clean_s = active_subdist[0].split(' (')[0].strip()
            clean_d = active_dist[0].split(' (')[0].strip() if active_dist else ""
            scope_header = f"ในทำเล ตำบล{clean_s} อำเภอ{clean_d} จังหวัด{active_prov[0] if active_prov else ''}"
        elif active_dist:
            clean_d = active_dist[0].split(' (')[0].strip()
            scope_header = f"ในทำเล อำเภอ{clean_d} จังหวัด{active_prov[0] if active_prov else ''}"
        elif active_prov:
            scope_header = f"ในทำเล จังหวัด{active_prov[0]}"
        else:
            scope_parts = []
            if map_cos:
                scope_parts.append(f"บริษัท {', '.join(map_cos)}")
            if q_only_proj:
                scope_parts.append("เฉพาะมีโครงการ")
            if map_types:
                scope_parts.append(f"ประเภท {', '.join(map_types)}")
            scope_header = f"({' · '.join(scope_parts)} ทั่วประเทศ)" if scope_parts else "(ภาพรวมทั่วประเทศ)"

    target_type = None
    if active_ref_prop is not None:
        target_type = active_ref_prop.get('ประเภททรัพย์')
    elif tab2_types and len(tab2_types) == 1:
        target_type = tab2_types[0]
    elif map_types and len(map_types) == 1:
        target_type = map_types[0]

    if is_comparison_active:
        scope_header = f"เปรียบเทียบทรัพย์ที่เลือก ({len(status_df)} รายการ)"

    # Header row
    if active_price_ref_prop is not None:
        st.markdown(
            """
            <style>
            .metric-card-pink,
            div.metric-card.metric-card-pink,
            #median-card-1.metric-card-pink,
            #median-card-2.metric-card-pink,
            #median-card-3.metric-card-pink {
                border-top: 3.5px solid #F6BAC0 !important;
                border-top-color: #F6BAC0 !important;
                border-color: rgba(246, 186, 192, 0.6) !important;
                background: rgba(246, 186, 192, 0.12) !important;
                box-shadow: 0 4px 14px rgba(246, 186, 192, 0.2) !important;
            }
            .metric-card-pink:hover,
            div.metric-card.metric-card-pink:hover,
            #median-card-1.metric-card-pink:hover,
            #median-card-2.metric-card-pink:hover,
            #median-card-3.metric-card-pink:hover {
                border-color: #F6BAC0 !important;
                border-top-color: #f43f5e !important;
                box-shadow: 0 10px 26px rgba(244, 63, 94, 0.25) !important;
            }
            .st-key-btn_reset_price_center button {
                border: 1.5px solid rgba(246, 186, 192, 0.7) !important;
                color: #be185d !important;
                font-weight: 600 !important;
            }
            .st-key-btn_reset_price_center button:hover {
                border-color: #F6BAC0 !important;
                background-color: rgba(246, 186, 192, 0.15) !important;
                color: #9f1239 !important;
            }
            </style>
            """,
            unsafe_allow_html=True
        )
        hdr_c1, hdr_c2 = st.columns([0.72, 0.28])
        with hdr_c1:
            ref_cid_disp = active_price_ref_prop.get('รหัสทรัพย์', '-')
            st.markdown(
                f"<div id='median-section-header' style='font-size: 1.25rem; font-weight: 700; margin-bottom: 12px;'><i class='fa-solid fa-scale-balanced' style='color:#e11d48; margin-right:6px;'></i>ผลการวิเคราะห์เทียบราคาทรัพย์อ้างอิงตรง <span style='font-size:0.95rem; color:#be185d; font-weight:800;'>[รหัส: {html.escape(str(ref_cid_disp))}]</span> <span id='median-scope-header-text' style='font-size:0.85rem; font-weight:500; color:#64748b;'>{html.escape(str(scope_header))}</span></div>",
                unsafe_allow_html=True
            )
        with hdr_c2:
            if st.button(
                "รีเซ็ตกลับเป็นราคากลาง (Median)",
                icon=":material/restart_alt:",
                key="btn_reset_price_center",
                on_click=_reset_price_center_callback,
                use_container_width=True,
                help="คลิกเพื่อยกเลิกการเทียบตรง และกลับไปใช้ราคากลาง (Median) ของพื้นที่",
            ):
                st.rerun(scope="fragment")
    else:
        st.markdown(
            f"<div id='median-section-header' style='font-size: 1.25rem; font-weight: 700; margin-bottom: 12px;'><i class='fa-solid fa-chart-simple' style='color:#059669; margin-right:6px;'></i>ผลการวิเคราะห์ราคากลางต่อหน่วย (Median Analysis) <span id='median-scope-header-text'>{html.escape(str(scope_header))}</span></div>",
            unsafe_allow_html=True
        )

    _cur_mtime_t2 = _get_mtime_t2()
    _has_custom_t2 = bool(
        st.session_state.get("imported_custom_df") is not None
        and not st.session_state["imported_custom_df"].empty
    )
    _custom_fp_t2 = st.session_state.get("_custom_import_fp") if _has_custom_t2 else None

    # Use status_df directly without unnecessary 452k-row copy
    filtered_nearby = status_df
    active_cos = map_cos
    active_types = map_types

    # 1. Dedicated Pure Land Calculation (Card 3 / Benchmark) — single 50 km scan + distance slicing
    is_radius_scope = bool(has_ref_point and (pin_mode == 'radius' or not has_loc_filter) and not active_proj)
    source_icon = "fa-circle-dot"
    land_source_desc = ""
    pure_df = pd.DataFrame()
    pure_rates = pd.Series(dtype=float)

    if is_radius_scope:
        land_radius = max(float(active_ref_radius), 1.0)
        source_icon = "fa-circle-dot"
        land_source_desc = f"ตามรัศมี {land_radius:.1f} กม. รอบจุดอ้างอิง"
        cand_raw = find_nearby_properties(active_ref_lat, active_ref_lon, df_raw, land_radius)
        pure_df, pure_rates = _extract_pure_land_pool_global(cand_raw)

        cand_50 = None
        if pure_rates.empty:
            cand_50 = find_nearby_properties(active_ref_lat, active_ref_lon, df_raw, 50.0)
            if not cand_50.empty:
                cand_50_pure, _ = _extract_pure_land_pool_global(cand_50)
                if not cand_50_pure.empty and 'ระยะทาง (กม.)' in cand_50_pure.columns:
                    for exp_r in (10.0, 15.0, 20.0, 30.0, 50.0):
                        if exp_r <= land_radius:
                            continue
                        sub_p = cand_50_pure[cand_50_pure['ระยะทาง (กม.)'] <= exp_r]
                        if not sub_p.empty:
                            pure_df = sub_p
                            pure_rates = sub_p['rate_per_sqw']
                            land_source_desc = f"ที่ดินเปล่าในรัศมี {exp_r:.0f} กม. รอบจุดอ้างอิง"
                            source_icon = "fa-circle-dot"
                            break

        if pure_rates.empty:
            r_dist = str(active_ref_prop.get('อำเภอ', '')).strip() if active_ref_prop else ""
            r_prov = str(active_ref_prop.get('จังหวัด', '')).strip() if active_ref_prop else ""
            if r_dist in _INVALID_LOC_TOKENS or r_prov in _INVALID_LOC_TOKENS:
                if cand_50 is None:
                    cand_50 = find_nearby_properties(active_ref_lat, active_ref_lon, df_raw, 50.0)
                if not cand_50.empty:
                    # Sort by distance ascending so we pick the NEAREST district/province, not arbitrary index 0
                    cand_50_sorted = cand_50.sort_values('ระยะทาง (กม.)', ascending=True) if 'ระยะทาง (กม.)' in cand_50.columns else cand_50
                    if r_dist in _INVALID_LOC_TOKENS and 'อำเภอ' in cand_50_sorted.columns:
                        d_vals = [d.strip() for d in cand_50_sorted['อำเภอ'].dropna().astype(str) if d.strip() not in _INVALID_LOC_TOKENS]
                        if d_vals:
                            r_dist = d_vals[0]
                    if r_prov in _INVALID_LOC_TOKENS and 'จังหวัด' in cand_50_sorted.columns:
                        p_vals = [p.strip() for p in cand_50_sorted['จังหวัด'].dropna().astype(str) if p.strip() not in _INVALID_LOC_TOKENS]
                        if p_vals:
                            r_prov = p_vals[0]

            if r_dist not in _INVALID_LOC_TOKENS and r_prov not in _INVALID_LOC_TOKENS and 'อำเภอ' in df_raw.columns and 'จังหวัด' in df_raw.columns:
                dist_cand = df_raw[
                    (df_raw['อำเภอ'].astype(str).str.strip() == r_dist)
                    & (df_raw['จังหวัด'].astype(str).str.strip() == r_prov)
                ]
                dist_pure, dist_rates = _extract_pure_land_pool_global(dist_cand)
                if not dist_rates.empty:
                    pure_df, pure_rates = dist_pure, dist_rates
                    land_source_desc = f"ที่ดินเปล่าใน อ.{r_dist} จ.{r_prov}"
                    source_icon = "fa-location-dot"

            if pure_rates.empty and r_prov not in _INVALID_LOC_TOKENS and 'จังหวัด' in df_raw.columns:
                prov_cand = df_raw[df_raw['จังหวัด'].astype(str).str.strip() == r_prov]
                prov_pure, prov_rates = _extract_pure_land_pool_global(prov_cand)
                if not prov_rates.empty:
                    pure_df, pure_rates = prov_pure, prov_rates
                    land_source_desc = f"ที่ดินเปล่าใน จ.{r_prov}"
                    source_icon = "fa-location-dot"

    elif active_proj:
        source_icon = "fa-mountain-sun"
        p_list = [p.strip() for p in active_proj.split(",") if p.strip()]
        proj_df = df_raw[_match_project_mask(df_raw, p_list)].copy() if (df_raw is not None and not df_raw.empty) else pd.DataFrame()
        # Apply active location scope to proj_df so Card 3 matches status_df location filter
        if not proj_df.empty:
            if active_prov and 'จังหวัด' in proj_df.columns:
                proj_df = proj_df[proj_df['จังหวัด'].astype(str).str.strip().isin(active_prov)]
            if active_dist and 'อำเภอ' in proj_df.columns:
                clean_td = [d.split(' (')[0].strip() for d in active_dist]
                proj_df = proj_df[proj_df['อำเภอ'].astype(str).str.strip().isin(clean_td)]
            if active_subdist and 'ตำบล' in proj_df.columns:
                clean_ts = [s.split(' (')[0].strip() for s in active_subdist]
                proj_df = proj_df[proj_df['ตำบล'].astype(str).str.strip().isin(clean_ts)]

        pure_df, pure_rates = _extract_pure_land_pool_global(proj_df)
        if not pure_rates.empty:
            land_source_desc = f"ในโครงการ: {active_proj}"
        else:
            proj_lats = pd.to_numeric(proj_df.get('ละติจูด', pd.Series(dtype=float)), errors='coerce').dropna()
            proj_lons = pd.to_numeric(proj_df.get('ลองจิจูด', pd.Series(dtype=float)), errors='coerce').dropna()
            if not proj_lats.empty and not proj_lons.empty and _is_valid_thai_coord(proj_lats.median(), proj_lons.median()):
                c_lat = float(proj_lats.median())
                c_lon = float(proj_lons.median())
                cand_30 = find_nearby_properties(c_lat, c_lon, df_raw, 30.0)
                if not cand_30.empty:
                    cand_30_pure, _ = _extract_pure_land_pool_global(cand_30)
                    if not cand_30_pure.empty and 'ระยะทาง (กม.)' in cand_30_pure.columns:
                        for r_dist_val in (5.0, 10.0, 15.0, 20.0, 30.0):
                            sub_p = cand_30_pure[cand_30_pure['ระยะทาง (กม.)'] <= r_dist_val]
                            if len(sub_p) >= 2 or (r_dist_val == 30.0 and len(sub_p) > 0):
                                pure_df = sub_p
                                pure_rates = sub_p['rate_per_sqw']
                                land_source_desc = f"ที่ดินเปล่ารอบโครงการ (รัศมี {r_dist_val:.0f} กม.)"
                                break

            p_dists = [d.split(' (')[0].strip() for d in proj_df['อำเภอ'].dropna().astype(str).unique() if d.strip() not in _INVALID_LOC_TOKENS] if 'อำเภอ' in proj_df.columns else []
            p_provs = [p.strip() for p in proj_df['จังหวัด'].dropna().astype(str).unique() if p.strip() not in _INVALID_LOC_TOKENS] if 'จังหวัด' in proj_df.columns else []
            if pure_rates.empty and p_dists and 'อำเภอ' in df_raw.columns:
                cand = df_raw[df_raw['อำเภอ'].astype(str).str.strip().isin(p_dists)]
                if p_provs and 'จังหวัด' in cand.columns:
                    cand = cand[cand['จังหวัด'].astype(str).str.strip().isin(p_provs)]
                cand_pure, cand_rates = _extract_pure_land_pool_global(cand)
                if not cand_rates.empty:
                    pure_df, pure_rates = cand_pure, cand_rates
                    d_lbl = p_dists[0]
                    p_lbl = p_provs[0] if p_provs else ""
                    land_source_desc = f"ที่ดินเปล่ารอบโครงการ (อ.{d_lbl} จ.{p_lbl})"

            if pure_rates.empty and p_provs and 'จังหวัด' in df_raw.columns:
                cand = df_raw[df_raw['จังหวัด'].astype(str).str.strip().isin(p_provs)]
                cand_pure, cand_rates = _extract_pure_land_pool_global(cand)
                if not cand_rates.empty:
                    pure_df, pure_rates = cand_pure, cand_rates
                    land_source_desc = f"ที่ดินเปล่ารอบโครงการ (จ.{p_provs[0]})"

    else:
        source_icon = "fa-location-dot"
        if active_subdist and not df_raw.empty and 'ตำบล' in df_raw.columns:
            clean_target_subs = [s.split(' (')[0].strip() for s in active_subdist]
            clean_target_dists = [d.split(' (')[0].strip() for d in active_dist] if active_dist else []
            sub_cand = df_raw[df_raw['ตำบล'].astype(str).str.strip().isin(clean_target_subs)]
            if clean_target_dists and 'อำเภอ' in sub_cand.columns:
                sub_cand = sub_cand[sub_cand['อำเภอ'].astype(str).str.strip().isin(clean_target_dists)]
            if active_prov and 'จังหวัด' in sub_cand.columns:
                sub_cand = sub_cand[sub_cand['จังหวัด'].astype(str).str.strip().isin(active_prov)]
            pure_sub, rates_sub = _extract_pure_land_pool_global(sub_cand)
            if not rates_sub.empty:
                pure_df, pure_rates = pure_sub, rates_sub
                clean_s_name = active_subdist[0].split(' (')[0].strip()
                clean_d_name = active_dist[0].split(' (')[0].strip() if active_dist else ""
                land_source_desc = f"ตามทำเล ต.{clean_s_name} อ.{clean_d_name}"

        if pure_rates.empty and active_dist and not df_raw.empty and 'อำเภอ' in df_raw.columns:
            clean_target_dists = [d.split(' (')[0].strip() for d in active_dist]
            dist_cand = df_raw[df_raw['อำเภอ'].astype(str).str.strip().isin(clean_target_dists)]
            if active_prov and 'จังหวัด' in dist_cand.columns:
                dist_cand = dist_cand[dist_cand['จังหวัด'].astype(str).str.strip().isin(active_prov)]
            pure_dist, rates_dist = _extract_pure_land_pool_global(dist_cand)
            if not rates_dist.empty:
                pure_df, pure_rates = pure_dist, rates_dist
                clean_d_name = active_dist[0].split(' (')[0].strip()
                clean_p_name = active_prov[0] if active_prov else ""
                land_source_desc = f"ที่ดินเปล่าใน อ.{clean_d_name} จ.{clean_p_name}"

        if pure_rates.empty and active_prov and not df_raw.empty and 'จังหวัด' in df_raw.columns:
            prov_cand = df_raw[df_raw['จังหวัด'].astype(str).str.strip().isin(active_prov)]
            pure_prov, rates_prov = _extract_pure_land_pool_global(prov_cand)
            if not rates_prov.empty:
                pure_df, pure_rates = pure_prov, rates_prov
                land_source_desc = f"ที่ดินเปล่าใน จ.{active_prov[0]}"

    # Final nationwide fallback if still empty
    if pure_rates.empty and df_raw is not None and not df_raw.empty:
        if _has_custom_t2 and not _custom_fp_t2:
            pure_all, rates_all = _extract_pure_land_pool_global(df_raw)
        else:
            pure_all, rates_all = _get_cached_nationwide_pure_land(
                df_raw, cache_key=(_cur_mtime_t2, len(df_raw), _custom_fp_t2)
            )
        if not rates_all.empty:
            pure_df, pure_rates = pure_all, rates_all
            land_source_desc = "ที่ดินเปล่า ภาพรวมทั่วประเทศ"
            source_icon = "fa-globe"

    # Prioritize filtered companies if matching pure land exists
    if active_cos and not active_proj and not pure_df.empty and 'บริษัท' in pure_df.columns:
        co_pure = pure_df[pure_df['บริษัท'].isin(active_cos)]
        co_rates = co_pure['rate_per_sqw'].dropna()
        co_rates = co_rates[co_rates > 0]
        if not co_rates.empty:
            pure_df = co_pure
            pure_rates = co_rates

    has_raw_land = False
    median_raw_land = min_raw_land = max_raw_land = 0.0
    count_raw_land = 0
    if not pure_rates.empty:
        median_raw_land = float(pure_rates.median())
        min_raw_land = float(pure_rates.min())
        max_raw_land = float(pure_rates.max())
        count_raw_land = len(pure_rates)
        has_raw_land = True

    is_fn_pure_land = (
        _check_pure_land_mask_global(filtered_nearby['ประเภททรัพย์'])
        if (not filtered_nearby.empty and 'ประเภททรัพย์' in filtered_nearby.columns)
        else pd.Series(False, index=filtered_nearby.index)
    )
    user_filtered_pure_land = bool(
        active_types
        and all(('ที่ดิน' in t and not any(k in t for k in ('บ้าน', 'อาคาร', 'ทาวน์', 'คอนโด', 'ตึก', 'โรงงาน', 'พาณิชย์', 'หอพัก', 'สิ่งปลูกสร้าง'))) for t in active_types)
    )

    # 2. Calculate Median for Sq. Wah (Card 2 - Strictly ตร.ว. only, unified CONDO_PATTERN & rate logic)
    has_sel_u_stats = False
    median_u_sel = min_u_sel = max_u_sel = 0.0
    median_sqw_val = 0.0
    count_u_sel = 0
    c2_source_desc = ""

    def _is_condo_type(val):
        return bool(re.search(CONDO_PATTERN, str(val), re.IGNORECASE))

    target_is_condo = bool(target_type and _is_condo_type(target_type))
    target_is_pure_land = bool(target_type and _check_pure_land_mask_global(pd.Series([target_type])).iloc[0])

    if target_type and not target_is_condo and not target_is_pure_land:
        title_c2 = f"ราคากลางตร.ว. {target_type}"
        calc_type_df = filtered_nearby[filtered_nearby['ประเภททรัพย์'] == target_type] if not filtered_nearby.empty else pd.DataFrame()
    elif active_types:
        landed_active = [t for t in active_types if not _check_pure_land_mask_global(pd.Series([t])).iloc[0] and not _is_condo_type(t)]
        if landed_active:
            title_c2 = f"ราคากลางตร.ว. {', '.join(landed_active)}"
            calc_type_df = filtered_nearby[filtered_nearby['ประเภททรัพย์'].isin(landed_active)] if not filtered_nearby.empty else pd.DataFrame()
        elif user_filtered_pure_land:
            title_c2 = "ราคากลางตร.ว. ที่ดินเปล่า"
            calc_type_df = filtered_nearby[is_fn_pure_land] if not filtered_nearby.empty else pd.DataFrame()
        else:
            title_c2 = "ราคากลางตร.ว. บ้านและสิ่งปลูกสร้าง"
            calc_type_df = pd.DataFrame()
    elif target_is_pure_land:
        title_c2 = "ราคากลางตร.ว. ที่ดินเปล่า"
        calc_type_df = filtered_nearby[is_fn_pure_land] if not filtered_nearby.empty else pd.DataFrame()
    elif target_is_condo:
        title_c2 = "ราคากลางตร.ว. บ้านและสิ่งปลูกสร้าง"
        calc_type_df = pd.DataFrame()
    else:
        title_c2 = "ราคากลางตร.ว. บ้านและสิ่งปลูกสร้าง"
        calc_type_df = (
            filtered_nearby[~is_fn_pure_land & ~filtered_nearby['ประเภททรัพย์'].astype(str).str.contains(CONDO_PATTERN, case=False, na=False)]
            if (not filtered_nearby.empty and 'ประเภททรัพย์' in filtered_nearby.columns)
            else pd.DataFrame()
        )

    sqw_rates = _sqw_rate_from_df(calc_type_df).dropna()
    sqw_rates = sqw_rates[sqw_rates > 0]
    if not sqw_rates.empty:
        median_u_sel = float(sqw_rates.median())
        median_sqw_val = median_u_sel
        min_u_sel = float(sqw_rates.min())
        max_u_sel = float(sqw_rates.max())
        count_u_sel = len(sqw_rates)
        has_sel_u_stats = True

    # 3. Calculate Median for All Sq. Metre (Card 4 - unified _sqm_rate_from_df)
    has_sqm_median = False
    median_sqm_val = 0.0
    count_sqm_val = 0
    min_sqm_val = max_sqm_val = 0.0
    if not filtered_nearby.empty:
        sqm_rates = _sqm_rate_from_df(filtered_nearby).dropna()
        sqm_rates = sqm_rates[sqm_rates > 0]
        if not sqm_rates.empty:
            median_sqm_val = float(sqm_rates.median())
            min_sqm_val = float(sqm_rates.min())
            max_sqm_val = float(sqm_rates.max())
            count_sqm_val = len(sqm_rates)
            has_sqm_median = True

    # Render 4 Metric Cards
    card_c1, card_c2, card_c3, card_c4 = st.columns(4)
    total_nearby_cnt = len(filtered_nearby)
    safe_scope_header = html.escape(str(scope_header))

    price_ref_price = price_ref_sqw_num = price_ref_sqw_rate = price_ref_sqm_rate = 0.0
    ref_is_condo = False
    ref_prop_code = ""
    ref_prop_company = ""
    if active_price_ref_prop is not None:
        ref_prop_code = str(active_price_ref_prop.get('รหัสทรัพย์', '-')).strip()
        ref_prop_company = str(active_price_ref_prop.get('บริษัท', '-')).strip()
        ref_proj = str(active_price_ref_prop.get('ชื่อโครงการ', '')).strip()
        ref_type = str(active_price_ref_prop.get('ประเภททรัพย์', '-')).strip()
        price_ref_price, price_ref_sqw_num, price_ref_sqw_rate, price_ref_sqm_rate, ref_is_condo = _extract_asset_unit_rates(active_price_ref_prop)

        ref_title_sub = f"[{html.escape(ref_prop_company)}] {html.escape(ref_proj if ref_proj and ref_proj not in _INVALID_LOC_TOKENS else ref_type)}"
        card1_price_str = f"฿{price_ref_price:,.0f} บาท" if price_ref_price > 0 else "-"
        card1_html = (
            f"<div class='metric-card metric-card-pink' id='median-card-1' style='position: relative; overflow: hidden; background: rgba(246, 186, 192, 0.12) !important; border: 1.5px solid rgba(246, 186, 192, 0.6) !important; border-top: 3.5px solid #F6BAC0 !important; border-top-color: #F6BAC0 !important; border-radius: 12px; padding: 12px 14px; box-shadow: 0 4px 12px rgba(246, 186, 192, 0.15) !important; min-height: 140px; display: flex; flex-direction: column; justify-content: space-between;'>"
            f"<div class='metric-card-bg-icon' style='position: absolute; left: -24px; bottom: -20px; font-size: 7rem; line-height: 1; pointer-events: none; z-index: 0; color: #F6BAC0; opacity: 0.25;'><i class='fa-solid fa-scale-balanced'></i></div>"
            f"<div style='position: relative; z-index: 1;'>"
            f"<div style='font-size: 0.78rem; font-weight: 700; color: #be185d; text-transform: uppercase; letter-spacing: 0.4px;'><i class='fa-solid fa-hashtag' style='color: #e11d48; margin-right:4px;'></i> รหัสทรัพย์ศูนย์กลางราคา</div>"
            f"<div id='median-card1-val' style='font-size: 1.45rem; font-weight: 800; color: #be185d; margin: 3px 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;' title='{html.escape(ref_prop_code)}'>{html.escape(ref_prop_code)}</div>"
            f"</div>"
            f"<div style='position: relative; z-index: 1;'>"
            f"<div id='median-card1-loc' style='color: #e11d48; font-size: 0.76rem; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;'><i class='fa-solid fa-tag' style='color:#e11d48; font-size:0.72rem; margin-right:3px;'></i>{card1_price_str}</div>"
            f"<div id='median-card1-sub' style='color: #64748b; font-size: 0.74rem; margin-top: 2px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;'>{ref_title_sub}</div>"
            f"</div>"
            f"</div>"
        )

        if price_ref_sqw_rate > 0:
            c4_main, c4_unit, c4_sub = f"฿{price_ref_sqw_rate:,.0f}", "/ตร.ว.", f"เนื้อที่: {price_ref_sqw_num:,.1f} ตร.ว."
        elif ref_is_condo:
            c4_main, c4_unit, c4_sub = "-", "", "คอนโดมิเนียม (ไม่มีเนื้อที่ดิน)"
        else:
            c4_main, c4_unit, c4_sub = "-", "", "ไม่มีข้อมูลเนื้อที่ดิน"

        card4_html = (
            f"<div class='metric-card metric-card-pink' id='median-card-3' style='position: relative; overflow: hidden; background: rgba(246, 186, 192, 0.12) !important; border: 1.5px solid rgba(246, 186, 192, 0.6) !important; border-top: 3.5px solid #F6BAC0 !important; border-top-color: #F6BAC0 !important; border-radius: 12px; padding: 12px 14px; box-shadow: 0 4px 12px rgba(246, 186, 192, 0.15) !important; min-height: 140px; display: flex; flex-direction: column; justify-content: space-between;'>"
            f"<div class='metric-card-bg-icon' style='position: absolute; left: -24px; bottom: -20px; font-size: 7rem; line-height: 1; pointer-events: none; z-index: 0; color: #F6BAC0; opacity: 0.25;'><i class='fa-solid fa-house-chimney'></i></div>"
            f"<div style='position: relative; z-index: 1;'>"
            f"<div id='median-card3-title' style='font-size: 0.78rem; font-weight: 700; color: #be185d; text-transform: uppercase; letter-spacing: 0.4px;'><i class='fa-solid fa-house' style='color: #e11d48; margin-right:4px;'></i> ราคา / ตร.ว. (ทรัพย์ที่เลือก)</div>"
            f"<div id='median-card3-val' style='font-size: 1.55rem; font-weight: 800; color: #be185d; margin: 3px 0;'>{c4_main} <span style='font-size:0.85rem; font-weight:600; color:#64748b;'>{c4_unit}</span></div>"
            f"</div>"
            f"<div style='position: relative; z-index: 1;'>"
            f"<div id='median-card3-sub' style='color: #64748b; font-size: 0.76rem;'>{c4_sub}</div>"
            f"</div>"
            f"</div>"
        )

        if price_ref_sqm_rate > 0:
            raw_sqm = _safe_float(active_price_ref_prop.get('พื้นที่ใช้สอย (ตร.ม.)'), 0.0)
            c3_main, c3_unit = f"฿{price_ref_sqm_rate:,.0f}", "/ตร.ม."
            c3_sub = f"พื้นที่ใช้สอย: {raw_sqm:,.1f} ตร.ม." if raw_sqm > 0 else "พื้นที่ใช้สอย (มีข้อมูล)"
        else:
            c3_main, c3_unit, c3_sub = "-", "", "ไม่มีข้อมูลพื้นที่ใช้สอย"

        card3_html = (
            f"<div class='metric-card metric-card-pink' id='median-card-2' style='position: relative; overflow: hidden; background: rgba(246, 186, 192, 0.12) !important; border: 1.5px solid rgba(246, 186, 192, 0.6) !important; border-top: 3.5px solid #F6BAC0 !important; border-top-color: #F6BAC0 !important; border-radius: 12px; padding: 12px 14px; box-shadow: 0 4px 12px rgba(246, 186, 192, 0.15) !important; min-height: 140px; display: flex; flex-direction: column; justify-content: space-between;'>"
            f"<div class='metric-card-bg-icon' style='position: absolute; left: -24px; bottom: -20px; font-size: 7rem; line-height: 1; pointer-events: none; z-index: 0; color: #F6BAC0; opacity: 0.25;'><i class='fa-solid fa-building'></i></div>"
            f"<div style='position: relative; z-index: 1;'>"
            f"<div id='median-card2-title' style='font-size: 0.78rem; font-weight: 700; color: #be185d; text-transform: uppercase; letter-spacing: 0.4px;'><i class='fa-solid fa-building' style='color: #e11d48; margin-right:4px;'></i> ราคา / ตร.ม. (ทรัพย์ที่เลือก)</div>"
            f"<div id='median-card2-val' style='font-size: 1.55rem; font-weight: 800; color: #be185d; margin: 3px 0;'>{c3_main} <span style='font-size:0.85rem; font-weight:600; color:#64748b;'>{c3_unit}</span></div>"
            f"</div>"
            f"<div style='position: relative; z-index: 1;'>"
            f"<div id='median-card2-sub' style='color: #64748b; font-size: 0.76rem;'>{c3_sub}</div>"
            f"</div>"
            f"</div>"
        )
    else:
        if active_ref_prop is not None:
            p_co = html.escape(str(active_ref_prop.get('บริษัท', '-')))
            p_code = html.escape(str(active_ref_prop.get('รหัสทรัพย์', '-')))
            p_type_str = html.escape(str(active_ref_prop.get('ประเภททรัพย์', '-')))
            sub_ref_info = f"<div id='median-card1-sub' style='color: #94a3b8; font-size: 0.74rem; margin-top: 2px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;'>[{p_co}] {p_code} &bull; {p_type_str}</div>"
        elif has_ref_point:
            sub_ref_info = "<div id='median-card1-sub' style='color: #94a3b8; font-size: 0.74rem; margin-top: 2px;'>กำหนดจากพิกัดแผนที่</div>"
        else:
            sub_ref_info = f"<div id='median-card1-sub' style='color: #94a3b8; font-size: 0.74rem; margin-top: 2px;'>{safe_scope_header}</div>"

        card1_loc_detail = f"{active_ref_lat:.5f}, {active_ref_lon:.5f} (รัศมี {active_ref_radius:.1f} กม.)" if has_ref_point else safe_scope_header
        card1_html = (
            f"<div class='metric-card' id='median-card-1' style='position: relative; overflow: hidden; background: rgba(16, 185, 129, 0.04); border: 1px solid rgba(16, 185, 129, 0.25); border-radius: 12px; padding: 12px 14px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); min-height: 140px; display: flex; flex-direction: column; justify-content: space-between;'>"
            f"<div class='metric-card-bg-icon' style='position: absolute; left: -24px; bottom: -20px; font-size: 7rem; line-height: 1; pointer-events: none; z-index: 0;'><i class='fa-solid fa-layer-group'></i></div>"
            f"<div style='position: relative; z-index: 1;'>"
            f"<div style='font-size: 0.78rem; font-weight: 700; color: #64748b; text-transform: uppercase; letter-spacing: 0.4px;'><i class='fa-solid fa-layer-group' style='color: #10b981; margin-right:4px;'></i> จำนวนทรัพย์ทั้งหมด</div>"
            f"<div id='median-card1-val' style='font-size: 1.55rem; font-weight: 800; color: #059669; margin: 3px 0;'>{total_nearby_cnt:,} <span style='font-size:0.85rem; font-weight:600; color:#64748b;'>รายการ</span></div>"
            f"</div>"
            f"<div style='position: relative; z-index: 1;'>"
            f"<div id='median-card1-loc' style='color: #64748b; font-size: 0.76rem;'><i class='fa-solid fa-location-dot' style='color:#10b981; font-size:0.72rem; margin-right:3px;'></i>{card1_loc_detail}</div>"
            f"{sub_ref_info}"
            f"</div>"
            f"</div>"
        )

        if has_sqm_median:
            c3_main, c3_unit = f"฿{median_sqm_val:,.0f}", "/ตร.ม."
            c3_sub = f"ต่ำสุด ฿{min_sqm_val:,.0f} &bull; สูงสุด ฿{max_sqm_val:,.0f}"
            c3_badge = f"<span style='font-size:0.74rem; font-weight:600; color:#10b981;'>({count_sqm_val:,} แปลง)</span>"
        else:
            c3_main, c3_unit, c3_sub, c3_badge = "-", "", "ไม่มีข้อมูลพื้นที่ใช้สอย", ""

        card3_html = (
            f"<div class='metric-card' id='median-card-2' style='position: relative; overflow: hidden; background: rgba(16, 185, 129, 0.04); border: 1px solid rgba(16, 185, 129, 0.25); border-radius: 12px; padding: 12px 14px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); min-height: 140px; display: flex; flex-direction: column; justify-content: space-between;'>"
            f"<div class='metric-card-bg-icon' style='position: absolute; left: -24px; bottom: -20px; font-size: 7rem; line-height: 1; pointer-events: none; z-index: 0;'><i class='fa-solid fa-building'></i></div>"
            f"<div style='position: relative; z-index: 1;'>"
            f"<div id='median-card2-title' style='font-size: 0.78rem; font-weight: 700; color: #64748b; text-transform: uppercase; letter-spacing: 0.4px;'><i class='fa-solid fa-building' style='color: #10b981; margin-right:4px;'></i> ราคากลาง / ตร.ม. <span id='median-card2-badge'>{c3_badge}</span></div>"
            f"<div id='median-card2-val' style='font-size: 1.55rem; font-weight: 800; color: #059669; margin: 3px 0;'>{c3_main} <span style='font-size:0.85rem; font-weight:600; color:#64748b;'>{c3_unit}</span></div>"
            f"</div>"
            f"<div style='position: relative; z-index: 1;'>"
            f"<div id='median-card2-sub' style='color: #64748b; font-size: 0.76rem;'>{c3_sub}</div>"
            f"</div>"
            f"</div>"
        )

        if has_sel_u_stats:
            c4_main, c4_unit = f"฿{median_u_sel:,.0f}", "/ตร.ว."
            c4_sub = f"ต่ำสุด ฿{min_u_sel:,.0f} &bull; สูงสุด ฿{max_u_sel:,.0f}"
            if c2_source_desc:
                c4_sub = f"<div style='color: #059669; font-size: 0.74rem; font-weight: 600;'><i class='fa-solid fa-location-dot' style='font-size:0.72rem; margin-right:3px;'></i>{html.escape(str(c2_source_desc))}</div>" + c4_sub
            c4_badge = f"<span style='font-size:0.74rem; font-weight:600; color:#10b981;'>({count_u_sel:,} แปลง)</span>"
        else:
            c4_main, c4_unit, c4_sub, c4_badge = "-", "", "-", ""

        card4_html = (
            f"<div class='metric-card' id='median-card-3' style='position: relative; overflow: hidden; background: rgba(16, 185, 129, 0.04); border: 1px solid rgba(16, 185, 129, 0.25); border-radius: 12px; padding: 12px 14px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); min-height: 140px; display: flex; flex-direction: column; justify-content: space-between;'>"
            f"<div class='metric-card-bg-icon' style='position: absolute; left: -24px; bottom: -20px; font-size: 7rem; line-height: 1; pointer-events: none; z-index: 0;'><i class='fa-solid fa-house-chimney'></i></div>"
            f"<div style='position: relative; z-index: 1;'>"
            f"<div id='median-card3-title' style='font-size: 0.78rem; font-weight: 700; color: #64748b; text-transform: uppercase; letter-spacing: 0.4px;'><i class='fa-solid fa-house' style='color: #10b981; margin-right:4px;'></i> {html.escape(str(title_c2))} <span id='median-card3-badge'>{c4_badge}</span></div>"
            f"<div id='median-card3-val' style='font-size: 1.55rem; font-weight: 800; color: #059669; margin: 3px 0;'>{c4_main} <span style='font-size:0.85rem; font-weight:600; color:#64748b;'>{c4_unit}</span></div>"
            f"</div>"
            f"<div style='position: relative; z-index: 1;'>"
            f"<div id='median-card3-sub' style='color: #64748b; font-size: 0.76rem;'>{c4_sub}</div>"
            f"</div>"
            f"</div>"
        )

    if has_raw_land:
        c5_main, c5_unit = f"฿{median_raw_land:,.0f}", "/ตร.ว."
        c5_sub = f"ต่ำสุด ฿{min_raw_land:,.0f} &bull; สูงสุด ฿{max_raw_land:,.0f}"
        c5_badge = f"<span style='font-size:0.74rem; font-weight:600; color:#92400e;'>({count_raw_land:,} แปลง)</span>"
        safe_land_desc = html.escape(str(land_source_desc))
        c5_source_html = f"<div id='median-card4-source' style='color: #92400e; font-size: 0.76rem; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;' title='{safe_land_desc}'><i class='fa-solid {source_icon}' style='font-size:0.72rem; margin-right:3px; color: #b45309;'></i>{safe_land_desc}</div>"
    else:
        c5_main, c5_unit, c5_sub, c5_badge, c5_source_html = "-", "", "-", "", ""

    card5_html = (
        f"<div class='metric-card metric-card-brown' id='median-card-4' style='position: relative; overflow: hidden; background: rgba(180, 83, 9, 0.04) !important; border: 1px solid rgba(180, 83, 9, 0.35) !important; border-top: 3.5px solid #92400e !important; border-radius: 12px; padding: 12px 14px; box-shadow: 0 4px 12px rgba(120, 53, 15, 0.06); min-height: 140px; display: flex; flex-direction: column; justify-content: space-between;'>"
        f"<div class='metric-card-bg-icon metric-card-bg-icon-brown' style='position: absolute; left: -24px; bottom: -20px; font-size: 7rem; line-height: 1; pointer-events: none; z-index: 0; color: #92400e;'><i class='fa-solid fa-mountain-sun'></i></div>"
        f"<div style='position: relative; z-index: 1;'>"
        f"<div id='median-card4-title' style='font-size: 0.78rem; font-weight: 700; color: #78716c; text-transform: uppercase; letter-spacing: 0.4px;'><i class='fa-solid fa-mountain-sun' style='color: #b45309; margin-right:4px;'></i> ราคากลางที่ดินเปล่า <span id='median-card4-badge'>{c5_badge}</span></div>"
        f"<div id='median-card4-val' style='font-size: 1.55rem; font-weight: 800; color: #92400e; margin: 3px 0;'>{c5_main} <span style='font-size:0.85rem; font-weight:600; color:#78716c;'>{c5_unit}</span></div>"
        f"</div>"
        f"<div style='position: relative; z-index: 1;'>"
        f"{c5_source_html}"
        f"<div id='median-card4-sub' style='color: #78716c; font-size: 0.74rem; margin-top: 1px;'>{c5_sub}</div>"
        f"</div>"
        f"</div>"
    )

    with card_c1:
        st.html(card1_html)
    with card_c2:
        st.html(card4_html)
    with card_c3:
        st.html(card5_html)
    with card_c4:
        st.html(card3_html)

    # Nearby Assets Table & Export
    render_tab2_nearby_table_and_export(
        filtered_nearby=filtered_nearby,
        is_fn_pure_land=is_fn_pure_land,
        is_dark_mode=is_dark_mode,
        active_cos=active_cos,
        active_proj=active_proj,
        active_price_ref_prop=active_price_ref_prop,
        ref_prop_code=ref_prop_code,
        ref_prop_company=ref_prop_company,
        has_ref_point=has_ref_point,
        active_ref_lat=active_ref_lat,
        active_ref_lon=active_ref_lon,
        active_ref_radius=active_ref_radius,
        safe_scope_header=safe_scope_header,
        scope_header=scope_header,
        is_comparison_active=is_comparison_active,
        median_raw_land=median_raw_land,
        median_sqw_val=median_sqw_val,
        median_u_sel=median_u_sel,
        median_sqm_val=median_sqm_val,
        price_ref_sqw_rate=price_ref_sqw_rate,
        price_ref_sqm_rate=price_ref_sqm_rate,
        _cur_mtime_t2=_cur_mtime_t2,
        _has_custom_t2=_has_custom_t2,
        _custom_fp_t2=_custom_fp_t2,
    )
