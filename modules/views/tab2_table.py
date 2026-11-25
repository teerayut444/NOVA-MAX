"""Tab 2 comparative table builder, Styler renderer, and export integration."""

import hashlib
import html
import math
import re
import numpy as np
import pandas as pd
import streamlit as st

from modules.services.batch_reference_service import append_summary_stat_columns
from modules.services.export_service import render_import_export_section
from modules.services.data_cleaner import (
    format_to_rai_ngan_wah,
    format_announcement_age,
    format_coord_vectorized,
    parse_listing_age_days,
    parse_sold_date_value,
)
from modules.services.data_loader import _today_th_str
from modules.views.tab2_metrics import (
    CONDO_PATTERN,
    _FILENAME_CLEAN_RE,
    _check_pure_land_mask_global,
    _clean_str_series,
    _get_cached_nationwide_pure_land,
    _is_valid_thai_coord,
    _sqm_from_df,
    _sqm_rate_from_df,
    _sqw_from_df,
    _sqw_rate_from_df,
)


def _compute_df_content_fp(df_obj):
    """Fast deterministic content fingerprint (immune to reset_index RangeIndex collisions)."""
    if df_obj is None or df_obj.empty:
        return "empty"
    n = len(df_obj)
    h = hashlib.blake2b(digest_size=10)
    h.update(f"n={n}|".encode("utf-8"))
    sample_pos = sorted({0, min(1, n - 1), n // 2, max(0, n - 2), n - 1})
    cols = [c for c in ('บริษัท', 'รหัสทรัพย์', 'ราคา', 'ระยะทาง (กม.)') if c in df_obj.columns]
    if cols:
        for row in df_obj.iloc[sample_pos][cols].itertuples(index=False, name=None):
            h.update(repr(row).encode("utf-8", errors="ignore"))
    if 'ราคา' in df_obj.columns:
        p_sum = float(pd.to_numeric(df_obj['ราคา'], errors='coerce').sum(skipna=True))
        h.update(f"|p={p_sum:.2f}".encode("utf-8"))
    if 'ระยะทาง (กม.)' in df_obj.columns:
        d_sum = float(pd.to_numeric(df_obj['ระยะทาง (กม.)'], errors='coerce').sum(skipna=True))
        h.update(f"|d={d_sum:.3f}".encode("utf-8"))
    return h.hexdigest()


def _materialize_export_df(show_df, export_proj_full=None, price_ref_id=""):
    """Builds export DataFrame via shallow column sharing to avoid duplicating 100k+ rows in RAM."""
    df_to_export = show_df.copy(deep=False)
    if export_proj_full is not None:
        df_to_export['ชื่อโครงการ'] = export_proj_full
    if price_ref_id and not df_to_export.empty and 'รหัสทรัพย์' in df_to_export.columns:
        first_val = str(df_to_export['รหัสทรัพย์'].iat[0])
        if first_val.startswith('[อ้างอิง] '):
            id_col = df_to_export['รหัสทรัพย์'].copy()
            id_col.iat[0] = first_val[len('[อ้างอิง] '):]
            df_to_export['รหัสทรัพย์'] = id_col
    return append_summary_stat_columns(df_to_export)


def _build_tab2_show_df_compact(
    filtered_nearby,
    is_fn_pure_land,
    median_raw_land,
    median_sqw_val,
    median_u_sel,
    median_sqm_val,
    price_ref_sqw=0.0,
    price_ref_sqm=0.0,
    price_ref_id="",
    price_ref_company="",
):
    """Core vectorized builder returning (show_df, export_proj_full_or_none, has_valid_proj) without duplicating show_df."""
    show_df = pd.DataFrame(index=filtered_nearby.index)
    has_trunc_proj = False

    # 1. บริษัท, รหัสทรัพย์, ชื่อโครงการ, ประเภททรัพย์
    for col in ('บริษัท', 'รหัสทรัพย์', 'ชื่อโครงการ', 'ประเภททรัพย์'):
        if col in filtered_nearby.columns:
            if col == 'ชื่อโครงการ':
                proj_clean = _clean_str_series(filtered_nearby[col], '-')
                long_mask = proj_clean.str.len() > 35
                has_trunc_proj = bool(long_mask.any())
                if has_trunc_proj:
                    show_df[col] = np.where(long_mask, proj_clean.str.slice(0, 35) + '...', proj_clean)
                    show_df['_export_proj_full'] = proj_clean
                else:
                    show_df[col] = proj_clean
            else:
                show_df[col] = _clean_str_series(filtered_nearby[col], '-')
        elif col == 'ชื่อโครงการ':
            show_df[col] = '-'

    # 2. ราคา (บาท)
    price_num = pd.to_numeric(filtered_nearby['ราคา'], errors='coerce') if 'ราคา' in filtered_nearby.columns else pd.Series(np.nan, index=filtered_nearby.index)
    show_df['ราคา (บาท)'] = price_num

    # 3. เนื้อที่ (ไร่-งาน-ตร.ว.)
    sqw_vals = _sqw_from_df(filtered_nearby)
    if 'เนื้อที่ (ตร.ว.)' in filtered_nearby.columns:
        raw_sqw_obj = filtered_nearby['เนื้อที่ (ตร.ว.)'].astype(object)
        u_str_sqw = raw_sqw_obj.dropna().unique()
        u_fmt_str_map = {v: format_to_rai_ngan_wah(v) for v in u_str_sqw}
        formatted_sqw = raw_sqw_obj.map(u_fmt_str_map).astype(object).fillna("-")
        need_num_fmt = (formatted_sqw == "-") & sqw_vals.notna()
        if need_num_fmt.any():
            u_num_sqw = sqw_vals.loc[need_num_fmt].dropna().unique()
            u_fmt_num_map = {v: format_to_rai_ngan_wah(v) for v in u_num_sqw}
            formatted_sqw.loc[need_num_fmt] = sqw_vals.loc[need_num_fmt].astype(object).map(u_fmt_num_map).astype(object).fillna("-")
    else:
        u_num_sqw = sqw_vals.dropna().unique()
        u_fmt_num_map = {v: format_to_rai_ngan_wah(v) for v in u_num_sqw}
        formatted_sqw = sqw_vals.astype(object).map(u_fmt_num_map).astype(object).fillna("-")

    # 4. ราคาต่อตร.ว. (บาท)
    calc_p_sqw_s = _sqw_rate_from_df(filtered_nearby, sqw_vals=sqw_vals, price_vals=price_num)
    is_condo_row = (
        filtered_nearby['ประเภททรัพย์'].astype(str).str.contains(CONDO_PATTERN, case=False, na=False)
        if 'ประเภททรัพย์' in filtered_nearby.columns
        else pd.Series(False, index=filtered_nearby.index)
    )
    calc_p_sqw_s = calc_p_sqw_s.mask(is_condo_row, np.nan)
    formatted_sqw = formatted_sqw.astype(object).mask(is_condo_row, "-")

    def _fmt_diff_pct(val, med):
        if pd.isna(val) or val <= 0 or pd.isna(med) or med <= 0:
            return "-"
        diff = ((val - med) / med) * 100.0
        if diff > 0:
            return f"↑ +{diff:.1f}%"
        elif diff < 0:
            return f"↓ {diff:.1f}%"
        return "0.0%"

    def _fmt_diff_sub(val, med):
        if pd.isna(val) or val <= 0 or pd.isna(med) or med <= 0:
            return "-"
        diff = val - med
        if diff > 0:
            return f"↑ +{diff:,.0f} ฿"
        elif diff < 0:
            return f"↓ -{abs(diff):,.0f} ฿"
        return "0 ฿"

    # 5. พื้นที่ใช้สอย (ตร.ม.) & ราคาต่อตร.ม.
    sqm_vals = _sqm_from_df(filtered_nearby)
    calc_p_sqm_s = _sqm_rate_from_df(filtered_nearby, sqm_vals=sqm_vals, price_vals=price_num)

    type_sqw_medians = {}
    type_sqm_medians = {}
    p_types_series = show_df['ประเภททรัพย์'] if 'ประเภททรัพย์' in show_df.columns else pd.Series([], dtype=str)
    if not filtered_nearby.empty and not p_types_series.empty:
        grouped_idx = filtered_nearby.groupby(p_types_series, observed=False).groups
        for pt, sub_idx in grouped_idx.items():
            sub_rates = calc_p_sqw_s.loc[sub_idx].dropna()
            sub_rates = sub_rates[sub_rates > 0]
            if not sub_rates.empty:
                type_sqw_medians[pt] = float(sub_rates.median())

            sub_sqm = calc_p_sqm_s.loc[sub_idx].dropna()
            sub_sqm = sub_sqm[sub_sqm > 0]
            if not sub_sqm.empty:
                type_sqm_medians[pt] = float(sub_sqm.median())

    uniq_pts = p_types_series.unique() if not p_types_series.empty else []
    fallback_med_sqw = median_sqw_val if median_sqw_val > 0 else (median_u_sel if median_u_sel > 0 else (median_raw_land if median_raw_land > 0 else np.nan))
    pt_med_sqw_map = {}
    pt_med_sqm_map = {}
    for pt in uniq_pts:
        pt_clean = str(pt).strip()
        if re.search(CONDO_PATTERN, pt_clean, re.IGNORECASE):
            pt_med_sqw_map[pt] = np.nan
        elif pt_clean in type_sqw_medians:
            pt_med_sqw_map[pt] = type_sqw_medians[pt_clean]
        else:
            pt_med_sqw_map[pt] = fallback_med_sqw
        pt_med_sqm_map[pt] = type_sqm_medians.get(pt_clean, median_sqm_val if median_sqm_val > 0 else np.nan)

    if price_ref_id:
        if price_ref_sqw > 0:
            target_med_sqw_s = pd.Series(price_ref_sqw, index=filtered_nearby.index).mask(is_condo_row, np.nan)
        else:
            target_med_sqw_s = pd.Series(np.nan, index=filtered_nearby.index)
        target_med_sqm_s = (
            pd.Series(price_ref_sqm, index=filtered_nearby.index)
            if price_ref_sqm > 0
            else pd.Series(np.nan, index=filtered_nearby.index)
        )
    else:
        target_med_sqw_s = p_types_series.map(pt_med_sqw_map)
        if median_raw_land > 0 and isinstance(is_fn_pure_land, pd.Series) and len(is_fn_pure_land) == len(target_med_sqw_s):
            need_land_fb = target_med_sqw_s.isna() & is_fn_pure_land & (~is_condo_row)
            if need_land_fb.any():
                target_med_sqw_s = target_med_sqw_s.mask(need_land_fb, median_raw_land)
        target_med_sqm_s = p_types_series.map(pt_med_sqm_map)

    valid_sqw_diff = calc_p_sqw_s.notna() & (calc_p_sqw_s > 0) & target_med_sqw_s.notna() & (target_med_sqw_s > 0)
    diff_sqw_col = pd.Series("-", index=filtered_nearby.index, dtype=object)
    if valid_sqw_diff.any():
        diff_sqw_col.loc[valid_sqw_diff] = [
            _fmt_diff_pct(v, m)
            for v, m in zip(calc_p_sqw_s.loc[valid_sqw_diff], target_med_sqw_s.loc[valid_sqw_diff])
        ]

    sub_land_col = pd.Series("-", index=filtered_nearby.index, dtype=object)
    if median_raw_land > 0:
        valid_sub_land = calc_p_sqw_s.notna() & (calc_p_sqw_s > 0) & (~is_condo_row)
        if valid_sub_land.any():
            sub_land_col.loc[valid_sub_land] = [
                _fmt_diff_sub(v, median_raw_land)
                for v in calc_p_sqw_s.loc[valid_sub_land]
            ]

    valid_sqm_diff = calc_p_sqm_s.notna() & (calc_p_sqm_s > 0) & target_med_sqm_s.notna() & (target_med_sqm_s > 0)
    diff_sqm_col = pd.Series("-", index=filtered_nearby.index, dtype=object)
    if valid_sqm_diff.any():
        diff_sqm_col.loc[valid_sqm_diff] = [
            _fmt_diff_pct(v, m)
            for v, m in zip(calc_p_sqm_s.loc[valid_sqm_diff], target_med_sqm_s.loc[valid_sqm_diff])
        ]

    # Land Sq.Wah columns
    show_df['เนื้อที่ (ไร่-งาน-ตร.ว.)'] = formatted_sqw
    show_df['ราคาต่อตร.ว. (บาท)'] = calc_p_sqw_s.to_numpy()
    if price_ref_id:
        show_df['เทียบราคา ตร.ว. (ทรัพย์อ้างอิง)'] = diff_sqw_col
    else:
        show_df['เทียบราคากลางต่อ ตร.ว.'] = diff_sqw_col
    show_df['หักลบราคากลาง ตร.ว. ที่ดินเปล่า'] = sub_land_col

    # Usable Area Sq.Metre columns
    show_df['พื้นที่ใช้สอย (ตร.ม.)'] = sqm_vals
    show_df['ราคาต่อตร.ม. (บาท)'] = calc_p_sqm_s.to_numpy()
    if price_ref_id:
        show_df['เทียบราคา ตร.ม. (ทรัพย์อ้างอิง)'] = diff_sqm_col
    else:
        show_df['เทียบราคากลางต่อ ตร.ม.'] = diff_sqm_col

    if 'ระยะทาง (กม.)' in filtered_nearby.columns:
        show_df['ระยะทาง (กม.)'] = pd.to_numeric(filtered_nearby['ระยะทาง (กม.)'], errors='coerce')

    show_df['ชั้น'] = _clean_str_series(filtered_nearby['ชั้น'], '-') if 'ชั้น' in filtered_nearby.columns else '-'

    # Links: preserve None/NaN safely without converting to literal "nan", and allowlist http(s)/led_bridge
    if 'ลิงก์' in filtered_nearby.columns:
        raw_links = filtered_nearby['ลิงก์'].astype(object)
        valid_l_mask = raw_links.notna()
        links_clean = pd.Series(None, index=filtered_nearby.index, dtype=object)
        if valid_l_mask.any():
            from modules.config.constants import get_base_url_prefix
            base_prefix = get_base_url_prefix()
            l_str = raw_links.loc[valid_l_mask].astype(str).str.strip()
            rel_m = l_str.str.startswith('app/static/led_')
            if rel_m.any():
                l_str = l_str.where(~rel_m, f'{base_prefix}/' + l_str)
            if base_prefix:
                root_m = l_str.str.startswith('/app/static/led_')
                if root_m.any():
                    l_str = l_str.where(~root_m, base_prefix + l_str)
            if 'บริษัท' in filtered_nearby.columns:
                is_legal_l = filtered_nearby.loc[valid_l_mask, 'บริษัท'].astype(str).str.strip().str.upper().isin(['LED LEGAL', 'LED_LEGAL', 'LED_SOLD'])
                if is_legal_l.any():
                    l_str = l_str.where(~is_legal_l, l_str.str.replace('led_bridge.html', 'led_legal_bridge.html', regex=False))
            safe_l = l_str.str.match(r'^(?:https?://|(?:/[A-Za-z0-9_/-]+)?/app/static/led(?:_legal)?_bridge\.html\?)', case=False, na=False)
            links_clean.loc[valid_l_mask] = l_str.where(safe_l, None)
        show_df['เปิดลิงก์'] = links_clean

    # Listing age (uses BE-safe parse_sold_date_value for LED Legal)
    if 'วันประกาศ' in filtered_nearby.columns:
        ann_res = pd.Series("-", index=filtered_nearby.index, dtype=object)
        ann_col_obj = filtered_nearby['วันประกาศ'].astype(object)
        ann_mask = ann_col_obj.notna()
        if ann_mask.any():
            is_legal = (
                filtered_nearby['บริษัท'].astype(str).str.strip().str.upper().isin(['LED LEGAL', 'LED_LEGAL', 'LED_SOLD'])
                if 'บริษัท' in filtered_nearby.columns else pd.Series(False, index=filtered_nearby.index)
            )
            has_sold = (
                filtered_nearby['วันที่ขาย'].notna()
                & (~filtered_nearby['วันที่ขาย'].astype(str).str.strip().isin(['', '-', 'nan', 'None', '<NA>']))
                if 'วันที่ขาย' in filtered_nearby.columns else pd.Series(False, index=filtered_nearby.index)
            )
            legal_sold_mask = is_legal & has_sold & ann_mask
            reg_mask = ann_mask & ~legal_sold_mask
            if reg_mask.any():
                u_ann_dates = ann_col_obj.loc[reg_mask].dropna().unique()
                u_ann_map = {d: format_announcement_age(d) for d in u_ann_dates}
                ann_res.loc[reg_mask] = ann_col_obj.loc[reg_mask].map(u_ann_map).astype(object).fillna("-")

            if legal_sold_mask.any():
                sub_pairs = filtered_nearby.loc[legal_sold_mask, ['วันประกาศ', 'วันที่ขาย']].astype(object).drop_duplicates()
                pair_map = {}
                for ann_v, sold_v in sub_pairs.itertuples(index=False, name=None):
                    val_str = None
                    try:
                        s_dt = parse_sold_date_value(sold_v)
                        if pd.notna(s_dt):
                            diff = parse_listing_age_days(ann_v, ref_date=s_dt.date())
                            if diff >= 0:
                                val_str = f"ขายได้ใน {diff:,} วัน"
                    except Exception:
                        pass
                    if not val_str:
                        val_str = format_announcement_age(ann_v)
                    pair_map[(ann_v, sold_v)] = val_str
                ann_res.loc[legal_sold_mask] = [
                    pair_map.get((a, s), "-")
                    for a, s in zip(ann_col_obj.loc[legal_sold_mask], filtered_nearby.loc[legal_sold_mask, 'วันที่ขาย'].astype(object))
                ]
        show_df['อายุวันประกาศ'] = ann_res
    else:
        show_df['อายุวันประกาศ'] = '-'

    show_df['เลขโฉนด'] = _clean_str_series(filtered_nearby['เลขโฉนด'], '-') if 'เลขโฉนด' in filtered_nearby.columns else '-'

    def _fmt_spec_count(val):
        if pd.isna(val) or val is None:
            return "-"
        s = str(val).strip()
        if s in ("", "-", "nan", "None", "<NA>", "null"):
            return "-"
        try:
            f = float(s)
            if not math.isfinite(f) or f <= 0:
                return "-"
            return str(int(round(f)))
        except (ValueError, TypeError):
            return "-"

    for room_col in ('ห้องนอน', 'ห้องน้ำ', 'ที่จอดรถ'):
        if room_col in filtered_nearby.columns:
            rm_obj = filtered_nearby[room_col].astype(object)
            u_rm = rm_obj.dropna().unique()
            u_rm_map = {v: _fmt_spec_count(v) for v in u_rm}
            show_df[room_col] = rm_obj.map(u_rm_map).astype(object).fillna("-")
        else:
            show_df[room_col] = '-'

    for loc_col in ('ตำบล', 'อำเภอ', 'จังหวัด'):
        show_df[loc_col] = _clean_str_series(filtered_nearby[loc_col], '-') if loc_col in filtered_nearby.columns else '-'

    show_df['ละติจูด'] = format_coord_vectorized(filtered_nearby, 'ละติจูด') if 'ละติจูด' in filtered_nearby.columns else '-'
    show_df['ลองจิจูด'] = format_coord_vectorized(filtered_nearby, 'ลองจิจูด') if 'ลองจิจูด' in filtered_nearby.columns else '-'
    show_df['โจทก์'] = _clean_str_series(filtered_nearby['โจทก์'], '-') if 'โจทก์' in filtered_nearby.columns else '-'

    if 'ระยะทาง (กม.)' in show_df.columns:
        show_df = show_df.sort_values(by='ระยะทาง (กม.)', ascending=True, na_position='last').reset_index(drop=True)

    # Pin Price Center row to top, matching (รหัสทรัพย์, บริษัท) when company is known, and preserving TRUE distance!
    if price_ref_id and not show_df.empty and 'รหัสทรัพย์' in show_df.columns:
        clean_p_ref = str(price_ref_id).strip().lower()
        is_ref_row = show_df['รหัสทรัพย์'].astype(str).str.strip().str.lower() == clean_p_ref
        clean_co_ref = str(price_ref_company or '').strip().lower()
        if clean_co_ref and 'บริษัท' in show_df.columns:
            both_match = is_ref_row & (show_df['บริษัท'].astype(str).str.strip().str.lower() == clean_co_ref)
            if both_match.any():
                is_ref_row = both_match
        if is_ref_row.any():
            # Move first matching reference row to index 0 while preserving its real distance
            first_match_pos = int(np.flatnonzero(is_ref_row.to_numpy())[0])
            order_idx = [first_match_pos] + [i for i in range(len(show_df)) if i != first_match_pos]
            show_df = show_df.iloc[order_idx].reset_index(drop=True)
            show_df.loc[0, 'รหัสทรัพย์'] = f"[อ้างอิง] {show_df.loc[0, 'รหัสทรัพย์']}"

    has_valid_proj = False
    if 'ชื่อโครงการ' in show_df.columns:
        has_valid_proj = bool(
            (show_df['ชื่อโครงการ'].astype(str).str.strip().replace({'': '-', 'nan': '-', 'None': '-', 'null': '-', '<NA>': '-'}) != '-').any()
        )

    export_proj_full = show_df.pop('_export_proj_full') if (has_trunc_proj and '_export_proj_full' in show_df.columns) else None
    if '_export_proj_full' in show_df.columns:
        show_df = show_df.drop(columns=['_export_proj_full'])
    return show_df, export_proj_full, has_valid_proj


def _build_tab2_show_df_uncached(
    filtered_nearby,
    is_fn_pure_land,
    median_raw_land,
    median_sqw_val,
    median_u_sel,
    median_sqm_val,
    price_ref_sqw=0.0,
    price_ref_sqm=0.0,
    price_ref_id="",
    price_ref_company="",
):
    """Core vectorized builder for Tab 2 comparison table (show_df, df_to_export, has_valid_proj)."""
    show_df, export_proj_full, has_valid_proj = _build_tab2_show_df_compact(
        filtered_nearby,
        is_fn_pure_land,
        median_raw_land,
        median_sqw_val,
        median_u_sel,
        median_sqm_val,
        price_ref_sqw=price_ref_sqw,
        price_ref_sqm=price_ref_sqm,
        price_ref_id=price_ref_id,
        price_ref_company=price_ref_company,
    )
    df_to_export = _materialize_export_df(show_df, export_proj_full, price_ref_id=price_ref_id)
    return show_df, df_to_export, has_valid_proj


@st.cache_data(show_spinner=False, max_entries=2)
def _build_tab2_show_df_compact_cached(
    _filtered_nearby,
    _is_fn_pure_land,
    median_raw_land,
    median_sqw_val,
    median_u_sel,
    median_sqm_val,
    price_ref_sqw=0.0,
    price_ref_sqm=0.0,
    price_ref_id="",
    cache_key=None,
    price_ref_company="",
):
    """Memory-lean cached wrapper storing a single DataFrame + optional full-project Series."""
    return _build_tab2_show_df_compact(
        _filtered_nearby,
        _is_fn_pure_land,
        median_raw_land,
        median_sqw_val,
        median_u_sel,
        median_sqm_val,
        price_ref_sqw=price_ref_sqw,
        price_ref_sqm=price_ref_sqm,
        price_ref_id=price_ref_id,
        price_ref_company=price_ref_company,
    )


@st.cache_data(show_spinner=False, max_entries=2)
def _build_tab2_show_df_cached(
    _filtered_nearby,
    _is_fn_pure_land,
    median_raw_land,
    median_sqw_val,
    median_u_sel,
    median_sqm_val,
    price_ref_sqw=0.0,
    price_ref_sqm=0.0,
    price_ref_id="",
    cache_key=None,
    price_ref_company="",
):
    """Cached wrapper for Tab 2 comparison table keyed by full content fingerprint & Thailand date."""
    return _build_tab2_show_df_uncached(
        _filtered_nearby,
        _is_fn_pure_land,
        median_raw_land,
        median_sqw_val,
        median_u_sel,
        median_sqm_val,
        price_ref_sqw=price_ref_sqw,
        price_ref_sqm=price_ref_sqm,
        price_ref_id=price_ref_id,
        price_ref_company=price_ref_company,
    )


def precompute_tab2_default_analytics(df_raw, data_mtime=0):
    """Pre-warms only the nationwide pure-land benchmark cache hit by Tab 2 filters (without copying 461k rows)."""
    if df_raw is None or df_raw.empty:
        return
    needed_cols = [c for c in ('บริษัท', 'ประเภททรัพย์', 'ราคา', 'พื้นที่_ตารางวา', 'เนื้อที่ (ตร.ว.)', 'ราคาต่อตารางวา', 'ราคาต่อหน่วย', 'ละติจูด', 'ลองจิจูด') if c in df_raw.columns]
    df_sub = df_raw[needed_cols]
    if 'ละติจูด' in df_sub.columns and 'ลองจิจูด' in df_sub.columns:
        valid_coords_mask = (
            df_sub['ละติจูด'].notna() & df_sub['ลองจิจูด'].notna() &
            df_sub['ละติจูด'].between(5, 21) & df_sub['ลองจิจูด'].between(97, 106)
        )
        if not bool(valid_coords_mask.all()):
            df_sub = df_sub.loc[valid_coords_mask]
    if df_sub.empty:
        return

    base_key = (data_mtime, len(df_sub), None)
    _get_cached_nationwide_pure_land(df_sub, cache_key=base_key)


def render_tab2_nearby_table_and_export(
    *,
    filtered_nearby,
    is_fn_pure_land,
    is_dark_mode,
    active_cos,
    active_proj,
    active_price_ref_prop,
    ref_prop_code,
    ref_prop_company,
    has_ref_point,
    active_ref_lat,
    active_ref_lon,
    active_ref_radius,
    safe_scope_header,
    scope_header,
    is_comparison_active,
    median_raw_land,
    median_sqw_val,
    median_u_sel,
    median_sqm_val,
    price_ref_sqw_rate,
    price_ref_sqm_rate,
    _cur_mtime_t2,
    _has_custom_t2,
    _custom_fp_t2,
):
    """Renders the comparative nearby assets table and CSV/Excel export controls for Tab 2."""
    # Nearby Assets Table
    filter_summary_str = f" [กรอง: {', '.join(active_cos)}]" if (active_cos and not active_proj) else ""
    if not filtered_nearby.empty:
        # Prioritize Price Center property (matching code+company) or SAM assets
        if active_price_ref_prop is not None and 'รหัสทรัพย์' in filtered_nearby.columns:
            ref_c_lower = ref_prop_code.lower()
            ref_co_lower = ref_prop_company.lower()
            is_ref_near = filtered_nearby['รหัสทรัพย์'].astype(str).str.strip().str.lower() == ref_c_lower
            if ref_co_lower and 'บริษัท' in filtered_nearby.columns:
                both_m = is_ref_near & (filtered_nearby['บริษัท'].astype(str).str.strip().str.lower() == ref_co_lower)
                if both_m.any():
                    is_ref_near = both_m
            if is_ref_near.any():
                filtered_nearby = pd.concat([filtered_nearby[is_ref_near], filtered_nearby[~is_ref_near]], ignore_index=True)
            else:
                ref_row_df = pd.DataFrame([active_price_ref_prop])
                # Compute real distance to reference pin if radius scope has distance column
                if 'ระยะทาง (กม.)' in filtered_nearby.columns and has_ref_point:
                    from modules.services.geo_service import haversine_distance
                    if _is_valid_thai_coord(active_price_ref_prop.get('ละติจูด'), active_price_ref_prop.get('ลองจิจูด')):
                        ref_row_df['ระยะทาง (กม.)'] = round(
                            haversine_distance(
                                active_ref_lat,
                                active_ref_lon,
                                float(active_price_ref_prop['ละติจูด']),
                                float(active_price_ref_prop['ลองจิจูด']),
                            ),
                            2,
                        )
                filtered_nearby = pd.concat([ref_row_df, filtered_nearby], ignore_index=True)
            is_fn_pure_land = _check_pure_land_mask_global(filtered_nearby['ประเภททรัพย์']) if 'ประเภททรัพย์' in filtered_nearby.columns else pd.Series(False, index=filtered_nearby.index)
        elif active_proj and 'บริษัท' in filtered_nearby.columns:
            is_sam = (filtered_nearby['บริษัท'].astype(str) == 'SAM')
            filtered_nearby = pd.concat([filtered_nearby[is_sam], filtered_nearby[~is_sam]], ignore_index=True)
            is_fn_pure_land = _check_pure_land_mask_global(filtered_nearby['ประเภททรัพย์']) if 'ประเภททรัพย์' in filtered_nearby.columns else pd.Series(False, index=filtered_nearby.index)
        else:
            filtered_nearby = filtered_nearby.reset_index(drop=True)
            is_fn_pure_land = is_fn_pure_land.reset_index(drop=True)

        legend_txt_color = "#94a3b8" if is_dark_mode else "#475569"
        legend_bg = "rgba(148, 163, 184, 0.12)" if is_dark_mode else "rgba(100, 116, 139, 0.08)"
        legend_border = "rgba(148, 163, 184, 0.22)" if is_dark_mode else "rgba(148, 163, 184, 0.3)"
        legend_green = "#34d399" if is_dark_mode else "#059669"
        legend_red = "#f87171" if is_dark_mode else "#dc2626"

        if active_price_ref_prop is not None:
            safe_ref_c_id = html.escape(ref_prop_code)
            table_title_text = f"เปรียบเทียบราคาโดยตรงกับทรัพย์ {safe_ref_c_id} ({len(filtered_nearby):,} รายการ {safe_scope_header})"
            tbl_title_icon = "<i class='fa-solid fa-scale-balanced' style='color:#e11d48; margin-right:8px;'></i>"
            tbl_badge_html = (
                f"<span style='font-size: 0.8rem; font-weight: 600; color: #be185d; background: rgba(246, 186, 192, 0.2); padding: 4px 12px; border-radius: 20px; border: 1.2px solid rgba(246, 186, 192, 0.6);'>"
                f"<i class='fa-solid fa-scale-balanced' style='margin-right:5px;'></i>ศูนย์กลางราคา: {safe_ref_c_id}</span>"
            )
        elif is_comparison_active:
            table_title_text = f"รายการทรัพย์สินที่เลือกเปรียบเทียบ ({len(filtered_nearby):,} รายการ)"
            tbl_title_icon = "<i class='fa-solid fa-table-list' style='color:#059669; margin-right:8px;'></i>"
            tbl_badge_html = (
                "<span style='font-size: 0.8rem; font-weight: 600; color: #059669; background: rgba(16, 185, 129, 0.1); padding: 4px 12px; border-radius: 20px; border: 1.2px solid rgba(16, 185, 129, 0.3);'>"
                "<i class='fa-solid fa-layer-group' style='margin-right:5px;'></i>ตารางเปรียบเทียบข้อมูลทรัพย์</span>"
            )
        else:
            table_title_text = f"รายการทรัพย์สิน ({len(filtered_nearby):,} รายการ {safe_scope_header}{html.escape(str(filter_summary_str))})"
            tbl_title_icon = "<i class='fa-solid fa-table-list' style='color:#059669; margin-right:8px;'></i>"
            tbl_badge_html = (
                "<span style='font-size: 0.8rem; font-weight: 600; color: #059669; background: rgba(16, 185, 129, 0.1); padding: 4px 12px; border-radius: 20px; border: 1.2px solid rgba(16, 185, 129, 0.3);'>"
                "<i class='fa-solid fa-layer-group' style='margin-right:5px;'></i>ตารางเปรียบเทียบข้อมูลทรัพย์</span>"
            )

        st.markdown(
            f"<div style='margin-top: 22px; margin-bottom: 12px; font-weight: 700; font-size: 1.06rem; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px;'>"
            f"<span>{tbl_title_icon}"
            f"<span id='median-table-title'>{table_title_text}</span></span>"
            f"<div style='display: flex; align-items: center; gap: 10px;'>"
            f"<span style='font-size: 0.8rem; font-weight: 500; color: {legend_txt_color}; background: {legend_bg}; padding: 4px 10px; border-radius: 8px; border: 1px solid {legend_border}; display: inline-flex; align-items: center; gap: 4px;'>"
            f"คำอธิบาย: <span style=\"color: {legend_green}; font-weight: 600;\">↓ สีเขียว (ถูกกว่า)</span> / <span style=\"color: {legend_red}; font-weight: 600;\">↑ สีแดง (แพงกว่า)</span>"
            f"</span>"
            f"{tbl_badge_html}"
            f"</div>"
            f"</div>",
            unsafe_allow_html=True
        )

        # Build detailed analysis dataframe with collision-free content fingerprint + Thailand date + custom_import_fp
        _has_dist_k = bool('ระยะทาง (กม.)' in filtered_nearby.columns)
        _content_fp = _compute_df_content_fp(filtered_nearby)
        _th_day_t2 = _today_th_str()
        if _has_custom_t2 and not _custom_fp_t2:
            show_df, df_to_export, has_valid_proj = _build_tab2_show_df_uncached(
                filtered_nearby,
                is_fn_pure_land,
                median_raw_land,
                median_sqw_val,
                median_u_sel,
                median_sqm_val,
                price_ref_sqw=price_ref_sqw_rate if active_price_ref_prop else 0.0,
                price_ref_sqm=price_ref_sqm_rate if active_price_ref_prop else 0.0,
                price_ref_id=ref_prop_code if active_price_ref_prop else "",
                price_ref_company=ref_prop_company if active_price_ref_prop else "",
            )
        else:
            _tbl_cache_key = (
                _cur_mtime_t2,
                _th_day_t2,
                _custom_fp_t2,
                len(filtered_nearby),
                _content_fp,
                round(float(active_ref_lat or 0.0), 5),
                round(float(active_ref_lon or 0.0), 5),
                round(float(active_ref_radius or 0.0), 2),
                round(float(median_raw_land), 2),
                round(float(median_sqw_val), 2),
                round(float(median_u_sel), 2),
                round(float(median_sqm_val), 2),
                round(float(price_ref_sqw_rate), 2) if active_price_ref_prop else 0.0,
                round(float(price_ref_sqm_rate), 2) if active_price_ref_prop else 0.0,
                ref_prop_code if active_price_ref_prop else "",
                ref_prop_company if active_price_ref_prop else "",
                _has_dist_k,
                bool(is_comparison_active),
            )
            show_df, export_proj_full, has_valid_proj = _build_tab2_show_df_compact_cached(
                filtered_nearby,
                is_fn_pure_land,
                median_raw_land,
                median_sqw_val,
                median_u_sel,
                median_sqm_val,
                price_ref_sqw=price_ref_sqw_rate if active_price_ref_prop else 0.0,
                price_ref_sqm=price_ref_sqm_rate if active_price_ref_prop else 0.0,
                price_ref_id=ref_prop_code if active_price_ref_prop else "",
                cache_key=_tbl_cache_key,
                price_ref_company=ref_prop_company if active_price_ref_prop else "",
            )
            df_to_export = _materialize_export_df(
                show_df,
                export_proj_full,
                price_ref_id=ref_prop_code if active_price_ref_prop else "",
            )

        proj_col_width = "medium" if has_valid_proj else "small"
        is_ref_mode = active_price_ref_prop is not None
        col_sqw_title = "เทียบราคา ตร.ว. (ทรัพย์อ้างอิง)" if is_ref_mode else "เทียบราคากลางต่อ ตร.ว."
        col_sqm_title = "เทียบราคา ตร.ม. (ทรัพย์อ้างอิง)" if is_ref_mode else "เทียบราคากลางต่อ ตร.ม."
        col_sqw_help = "เทียบกับราคาต่อ ตร.ว. ของทรัพย์อ้างอิงที่เลือก (↓ สีเขียว = ถูกกว่าทรัพย์อ้างอิง, ↑ สีแดง = แพงกว่าทรัพย์อ้างอิง)" if is_ref_mode else "เทียบกับราคากลางต่อ ตร.ว. ตามประเภททรัพย์นั้นๆ ในพื้นที่ (↓ สีเขียว = ถูกกว่าราคากลางประเภทนั้น, ↑ สีแดง = แพงกว่าราคากลางประเภทนั้น)"
        col_sqm_help = "เทียบกับราคาต่อ ตร.ม. ของทรัพย์อ้างอิงที่เลือก (↓ สีเขียว = ถูกกว่าทรัพย์อ้างอิง, ↑ สีแดง = แพงกว่าทรัพย์อ้างอิง)" if is_ref_mode else "เทียบกับราคากลางต่อ ตร.ม. ตามประเภททรัพย์นั้นๆ ในพื้นที่ (↓ สีเขียว = ถูกกว่าราคากลางประเภทนั้น, ↑ สีแดง = แพงกว่าราคากลางประเภทนั้น)"

        table_col_config = {
            "บริษัท": st.column_config.TextColumn("บริษัท", help="บริษัทบริหารสินทรัพย์", pinned=True),
            "ชื่อโครงการ": st.column_config.TextColumn("ชื่อโครงการ", help="ชื่อโครงการ / หมู่บ้าน / อาคารชุด", width=proj_col_width),
            "ชั้น": st.column_config.TextColumn("ชั้น", help="ชั้นที่ตั้งของทรัพย์สิน หรือจำนวนชั้นของอาคาร"),
            "ราคา (บาท)": st.column_config.NumberColumn("ราคา (บาท)", format="฿%,d"),
            "เนื้อที่ (ไร่-งาน-ตร.ว.)": st.column_config.TextColumn("เนื้อที่ (ไร่-งาน-ตร.ว.)", help="ขนาดเนื้อที่ดินในรูปแบบ ไร่-งาน-ตารางวา (0-0-0)"),
            "เนื้อที่ (ตร.ว.)": st.column_config.TextColumn("เนื้อที่ (ไร่-งาน-ตร.ว.)", help="ขนาดเนื้อที่ดินในรูปแบบ ไร่-งาน-ตารางวา (0-0-0)"),
            "ราคาต่อตร.ว. (บาท)": st.column_config.NumberColumn("ราคาต่อตร.ว. (บาท)", format="฿%,d"),
            col_sqw_title: st.column_config.TextColumn(col_sqw_title, help=col_sqw_help),
            "หักลบราคากลาง ตร.ว. ที่ดินเปล่า": st.column_config.TextColumn(
                "หักลบราคากลาง ตร.ว. ที่ดินเปล่า",
                help=f"หักลบกับราคากลาง ตร.ว. ของที่ดินเปล่าแท้ๆ ในพื้นที่ (ราคาต่อ ตร.ว. - ฿{median_raw_land:,.0f}/ตร.ว.) | ↓ สีเขียว = ถูกกว่า, ↑ สีแดง = แพงกว่า" if median_raw_land > 0 else "หักลบราคากลาง ตร.ว. ที่ดินเปล่า"
            ),
            "พื้นที่ใช้สอย (ตร.ม.)": st.column_config.NumberColumn("พื้นที่ใช้สอย (ตร.ม.)", format="%,.1f"),
            "ราคาต่อตร.ม. (บาท)": st.column_config.NumberColumn("ราคาต่อตร.ม. (บาท)", format="฿%,d"),
            col_sqm_title: st.column_config.TextColumn(col_sqm_title, help=col_sqm_help),
            "ระยะทาง (กม.)": st.column_config.NumberColumn("ระยะทาง (กม.)", format="%.2f กม."),
            "เปิดลิงก์": st.column_config.LinkColumn("เปิดลิงก์", display_text="เปิดดูทรัพย์"),
            "อายุวันประกาศ": st.column_config.TextColumn("อายุวันประกาศ", help="ระยะเวลาตั้งแต่เริ่มลงประกาศจนถึงปัจจุบัน (คำนวณจากวันประกาศ)"),
            "เลขโฉนด": st.column_config.TextColumn("เลขโฉนด", help="เลขที่โฉนดที่ดิน หรือ เอกสารสิทธิ์"),
            "ห้องนอน": st.column_config.TextColumn("ห้องนอน", help="จำนวนห้องนอน"),
            "ห้องน้ำ": st.column_config.TextColumn("ห้องน้ำ", help="จำนวนห้องน้ำ"),
            "ที่จอดรถ": st.column_config.TextColumn("ที่จอดรถ", help="จำนวนช่องจอดรถ"),
            "ตำบล": st.column_config.TextColumn("ตำบล", help="ตำบล/แขวง"),
            "อำเภอ": st.column_config.TextColumn("อำเภอ", help="อำเภอ/เขต"),
            "จังหวัด": st.column_config.TextColumn("จังหวัด", help="จังหวัด"),
            "ละติจูด": st.column_config.TextColumn("ละติจูด", help="พิกัดละติจูด (⚠️ = พิกัดกึ่งกลางตำบล/อำเภอโดยประมาณ ไม่ใช่ตำแหน่งจริง)"),
            "ลองจิจูด": st.column_config.TextColumn("ลองจิจูด", help="พิกัดลองจิจูด (⚠️ = พิกัดกึ่งกลางตำบล/อำเภอโดยประมาณ ไม่ใช่ตำแหน่งจริง)"),
            "โจทก์": st.column_config.TextColumn("โจทก์", help="โจทก์ผู้ฟ้องคดี (เฉพาะทรัพย์กรมบังคับคดี LED / LED Legal)"),
        }

        def highlight_diff_cells(val):
            s = str(val).strip()
            if s in ("-", "", "nan", "None", "0.0%", "0 ฿", "0") or "(0.0%)" in s:
                return ""
            if s.startswith("↓") or s.startswith("▼"):
                return (
                    "color: #34d399; font-weight: 700; background-color: rgba(16, 185, 129, 0.15); border: 1.5px solid rgba(16, 185, 129, 0.45); border-radius: 6px;"
                    if is_dark_mode else
                    "color: #047857; font-weight: 700; background-color: rgba(16, 185, 129, 0.12); border: 1.5px solid rgba(16, 185, 129, 0.4); border-radius: 6px;"
                )
            elif s.startswith("↑") or s.startswith("▲"):
                return (
                    "color: #f87171; font-weight: 700; background-color: rgba(239, 68, 68, 0.15); border: 1.5px solid rgba(239, 68, 68, 0.45); border-radius: 6px;"
                    if is_dark_mode else
                    "color: #b91c1c; font-weight: 700; background-color: rgba(239, 68, 68, 0.12); border: 1.5px solid rgba(239, 68, 68, 0.4); border-radius: 6px;"
                )
            return ""

        diff_target_cols = [
            c for c in (
                'เทียบราคากลางต่อ ตร.ว.',
                'หักลบราคากลาง ตร.ว. ที่ดินเปล่า',
                'เทียบราคากลางต่อ ตร.ม.',
                'เทียบราคา ตร.ว. (ทรัพย์อ้างอิง)',
                'เทียบราคา ตร.ม. (ทรัพย์อ้างอิง)',
            )
            if c in show_df.columns
        ]

        # Cap Styler at 50,000 cells to keep browser Glide grid snappy and prevent OOM
        df_to_render = show_df
        if diff_target_cols and show_df.size <= 50_000:
            try:
                df_to_render = show_df.style.map(highlight_diff_cells, subset=diff_target_cols)
            except Exception:
                df_to_render = show_df

        first_asset_id = str(show_df['รหัสทรัพย์'].iloc[0]) if not show_df.empty and 'รหัสทรัพย์' in show_df.columns else ""
        first_co = str(show_df['บริษัท'].iloc[0]) if not show_df.empty and 'บริษัท' in show_df.columns else ""
        co_part = ','.join(sorted(active_cos)) if active_cos else 'ALL'
        grid_sig = f"{co_part}_{active_proj or ''}_{len(show_df)}_{first_asset_id}_{first_co}_{_content_fp}"
        grid_key = f"tab2_table_grid_{hashlib.md5(grid_sig.encode('utf-8')).hexdigest()[:12]}"

        try:
            st.dataframe(df_to_render, width="stretch", height=420, column_config=table_col_config, hide_index=True, key=grid_key)
        except Exception:
            st.dataframe(show_df, width="stretch", height=420, column_config=table_col_config, hide_index=True, key=f"{grid_key}_fb")

        safe_scope_fname = _FILENAME_CLEAN_RE.sub("_", str(scope_header or "map")).strip("_")[:60] or "map"
        render_import_export_section(df_to_export, filename_prefix=f"comparison_{safe_scope_fname}", key_suffix="tab2_compare")
    else:
        safe_scope_md = re.sub(r'([\\`*_{}\[\]()#+\-!|>$])', r'\\\1', str(scope_header or ''))
        st.info(f"ไม่พบรายการทรัพย์สินที่ตรงตามเงื่อนไขตัวกรอง {safe_scope_md}")
