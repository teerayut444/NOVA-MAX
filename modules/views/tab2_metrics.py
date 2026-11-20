"""Tab 2 metric, unit-conversion, pure-land, and project-matching helpers."""

import math
import re
import numpy as np
import pandas as pd
import streamlit as st

from modules.services.data_cleaner import (
    to_float_sqwah,
    to_float_sqm,
    normalize_project_name,
)
from modules.config.constants import is_true_centroid

CONDO_PATTERN = r'คอนโด|ห้องชุด|อาคารชุด'
_INVALID_LOC_TOKENS = {'', '-', 'ไม่มีข้อมูล', 'ไม่ระบุ', 'nan', 'None', '<NA>', 'null'}
_FILENAME_CLEAN_RE = re.compile(r'[\\/:*?"<>|\s]+')


def _sqw_from_df(df_obj):
    """Return numeric Sq.Wah series, parsing Rai-Ngan-Wah strings via unique-mapped to_float_sqwah when needed."""
    if df_obj is None or df_obj.empty:
        return pd.Series(dtype=float)
    if 'พื้นที่_ตารางวา' in df_obj.columns:
        sqw_num = pd.to_numeric(df_obj['พื้นที่_ตารางวา'], errors='coerce')
        if 'เนื้อที่ (ตร.ว.)' in df_obj.columns and sqw_num.isna().any():
            raw_obj = df_obj['เนื้อที่ (ตร.ว.)'].astype(object)
            na_mask = sqw_num.isna()
            u_raw = raw_obj.loc[na_mask].dropna().unique()
            if len(u_raw) > 0:
                u_map = {v: to_float_sqwah(v) for v in u_raw}
                sqw_num = sqw_num.fillna(pd.to_numeric(raw_obj.map(u_map), errors='coerce'))
        return sqw_num
    if 'เนื้อที่ (ตร.ว.)' in df_obj.columns:
        raw_obj = df_obj['เนื้อที่ (ตร.ว.)'].astype(object)
        u_raw = raw_obj.dropna().unique()
        u_map = {v: to_float_sqwah(v) for v in u_raw}
        return pd.to_numeric(raw_obj.map(u_map), errors='coerce')
    return pd.Series(np.nan, index=df_obj.index, dtype=float)


def _sqm_from_df(df_obj):
    """Return numeric usable Sq.Metre series, parsing unit-suffixed strings via unique-mapped to_float_sqm when needed."""
    if df_obj is None or df_obj.empty or 'พื้นที่ใช้สอย (ตร.ม.)' not in df_obj.columns:
        return pd.Series(np.nan, index=df_obj.index if df_obj is not None else [], dtype=float)
    raw_col = df_obj['พื้นที่ใช้สอย (ตร.ม.)']
    if pd.api.types.is_numeric_dtype(raw_col):
        sqm_num = pd.to_numeric(raw_col, errors='coerce')
        return sqm_num.where(sqm_num > 0, np.nan)
    sqm_num = pd.to_numeric(raw_col, errors='coerce')
    if sqm_num.isna().any():
        raw_obj = raw_col.astype(object)
        na_mask = sqm_num.isna()
        u_raw = raw_obj.loc[na_mask].dropna().unique()
        if len(u_raw) > 0:
            u_map = {v: to_float_sqm(v) for v in u_raw}
            sqm_num = sqm_num.fillna(pd.to_numeric(raw_obj.map(u_map), errors='coerce'))
    return sqm_num.where(sqm_num > 0, np.nan)


def _sqw_rate_from_df(df_obj, sqw_vals=None, price_vals=None):
    """Unified price-per-sq.wah series preferring explicit ราคาต่อตารางวา > 0 before ราคา / พื้นที่_ตารางวา."""
    if df_obj is None or df_obj.empty:
        return pd.Series(dtype=float)
    p_num = price_vals if price_vals is not None else (
        pd.to_numeric(df_obj['ราคา'], errors='coerce') if 'ราคา' in df_obj.columns else pd.Series(np.nan, index=df_obj.index, dtype=float)
    )
    s_num = sqw_vals if sqw_vals is not None else _sqw_from_df(df_obj)
    puw_vals = (
        pd.to_numeric(df_obj['ราคาต่อตารางวา'], errors='coerce')
        if 'ราคาต่อตารางวา' in df_obj.columns
        else pd.Series(np.nan, index=df_obj.index, dtype=float)
    )
    if 'ราคาต่อหน่วย' in df_obj.columns:
        puw_vals = puw_vals.combine_first(pd.to_numeric(df_obj['ราคาต่อหน่วย'], errors='coerce'))
    fallback = np.where((p_num > 0) & (s_num > 0), p_num / s_num, np.nan)
    rates = np.where(puw_vals.notna() & (puw_vals > 0), puw_vals, fallback)
    return pd.Series(rates, index=df_obj.index, dtype=float)


def _sqm_rate_from_df(df_obj, sqm_vals=None, price_vals=None):
    """Unified price-per-sq.metre series preferring explicit ราคาต่อตารางเมตร > 0 before ราคา / พื้นที่ใช้สอย."""
    if df_obj is None or df_obj.empty:
        return pd.Series(dtype=float)
    p_num = price_vals if price_vals is not None else (
        pd.to_numeric(df_obj['ราคา'], errors='coerce') if 'ราคา' in df_obj.columns else pd.Series(np.nan, index=df_obj.index, dtype=float)
    )
    m_num = sqm_vals if sqm_vals is not None else _sqm_from_df(df_obj)
    pum_vals = (
        pd.to_numeric(df_obj['ราคาต่อตารางเมตร'], errors='coerce')
        if 'ราคาต่อตารางเมตร' in df_obj.columns
        else pd.Series(np.nan, index=df_obj.index, dtype=float)
    )
    fallback = np.where((p_num > 0) & (m_num > 0), p_num / m_num, np.nan)
    rates = np.where(pum_vals.notna() & (pum_vals > 0), pum_vals, fallback)
    return pd.Series(rates, index=df_obj.index, dtype=float)


def _safe_float(val, default=0.0):
    """Safely parse any value to finite float without throwing exceptions on None/corrupt/inf data."""
    try:
        if val is None:
            return default
        f = float(val)
        return default if not math.isfinite(f) else f
    except (ValueError, TypeError):
        return default


def _is_valid_thai_coord(lat_val, lon_val):
    try:
        la = float(lat_val)
        lo = float(lon_val)
        return math.isfinite(la) and math.isfinite(lo) and (5.0 <= la <= 21.0) and (97.0 <= lo <= 106.0)
    except (ValueError, TypeError):
        return False


def _fmt_coord_val(row, coord_col):
    val = row.get(coord_col)
    try:
        if val is None or pd.isna(val):
            return '-'
        f = float(val)
        if not math.isfinite(f) or f == 0:
            return '-'
        is_cen = is_true_centroid(row.get('is_centroid'), row.get('บริษัท'))
        return f"⚠️ {f:.6f}" if is_cen else f"{f:.6f}"
    except (ValueError, TypeError):
        return '-'


def _check_pure_land_mask_global(s_types):
    p = s_types.astype(str)
    return p.str.contains('ที่ดินเปล่า|ที่ดิน', regex=True, na=False) & \
        ~p.str.contains('บ้าน|อาคาร|ทาวน์|คอนโด|ตึก|โรงงาน|พาณิชย์|หอพัก|สิ่งปลูกสร้าง|พร้อมสิ่งปลูกสร้าง', regex=True, na=False)


def _extract_pure_land_pool_global(df_cand):
    if df_cand is None or df_cand.empty or 'ประเภททรัพย์' not in df_cand.columns or 'ราคา' not in df_cand.columns:
        return pd.DataFrame(), pd.Series(dtype=float)
    is_pure = _check_pure_land_mask_global(df_cand['ประเภททรัพย์'])
    p_num = pd.to_numeric(df_cand['ราคา'], errors='coerce')
    pure_df = df_cand[is_pure & (p_num > 0)].copy()
    if pure_df.empty:
        return pure_df, pd.Series(dtype=float)

    rates = _sqw_rate_from_df(pure_df)
    pure_df['rate_per_sqw'] = rates
    pure_df['ราคาต่อหน่วย'] = rates
    valid_mask = pure_df['rate_per_sqw'].notna() & (pure_df['rate_per_sqw'] > 0)
    valid_rates = pure_df.loc[valid_mask, 'rate_per_sqw']
    return pure_df.loc[valid_mask], valid_rates


@st.cache_data(show_spinner=False, max_entries=4)
def _get_cached_nationwide_pure_land(_df_raw, cache_key=None):
    return _extract_pure_land_pool_global(_df_raw)


def _clean_str_series(s, default='-'):
    """Fast vectorized string cleaner that leverages Categorical/unique values when possible."""
    if isinstance(s.dtype, pd.CategoricalDtype):
        cats = [str(c).strip() for c in s.cat.categories]
        cat_map = {
            orig: (default if cln in ('', '-', 'nan', 'None', 'null', '<NA>') else cln)
            for orig, cln in zip(s.cat.categories, cats)
        }
        return s.astype(object).map(cat_map).fillna(default)
    uniq = s.dropna().unique()
    if len(uniq) < len(s) * 0.4:
        u_map = {}
        for v in uniq:
            cln = str(v).strip()
            u_map[v] = default if cln in ('', '-', 'nan', 'None', 'null', '<NA>') else cln
        return s.map(u_map).fillna(default)
    return (
        s.astype(object)
        .fillna(default)
        .astype(str)
        .str.strip()
        .replace({'': default, 'nan': default, 'None': default, 'null': default, '<NA>': default})
    )


def _match_project_mask(df, p_list):
    """Robust matching of project names across all companies in the dataset."""
    if df is None or df.empty or not p_list:
        return pd.Series(False, index=df.index if df is not None else [])

    clean_p_list = [p.strip() for p in p_list if p.strip()]
    if not clean_p_list:
        return pd.Series(False, index=df.index)

    selected_raw_names = set(clean_p_list)
    selected_norm_keys = {normalize_project_name(p) for p in clean_p_list if normalize_project_name(p)}

    mask = pd.Series(False, index=df.index)
    if 'ชื่อโครงการ' in df.columns:
        proj_col = df['ชื่อโครงการ'].astype(object).fillna('').astype(str).str.strip()
        mask = mask | proj_col.isin(selected_raw_names)

        if selected_norm_keys:
            if 'norm_project_name' in df.columns:
                mask = mask | df['norm_project_name'].isin(selected_norm_keys)
            else:
                norm_col = proj_col.apply(normalize_project_name)
                mask = mask | norm_col.isin(selected_norm_keys)

        for raw_p in clean_p_list:
            clean_core = re.sub(
                r'^(คอนโด\s*โครงการ|โครงการ\s*คอนโด|โครงการ\s*หมู่บ้าน|อาคารชุด|คอนโดมิเนียม|มีเนียม|โครงการ|หมู่บ้าน|คอนโด|บ้านเดี่ยว|บ้านแฝด|บ้าน|ทาวน์โฮม|ทาวน์เฮ้าส์|ขายคอนโด)\s*',
                '', raw_p, flags=re.IGNORECASE
            ).strip()
            clean_core = re.sub(r'(\[.*?\]|\(.*?\)).*$', '', clean_core).strip()
            if len(clean_core) >= 4:
                mask = mask | proj_col.str.contains(re.escape(clean_core), case=False, na=False)

    return mask


def _extract_asset_unit_rates(p_dict):
    """Extracts price, sqw_num, sqw_rate, sqm_rate, is_condo from a property dict."""
    if not p_dict or not isinstance(p_dict, dict):
        return 0.0, 0.0, 0.0, 0.0, False

    price = _safe_float(p_dict.get('ราคา'), 0.0)
    p_type = str(p_dict.get('ประเภททรัพย์', '')).lower()
    is_condo = bool(re.search(CONDO_PATTERN, p_type))

    sqw = _safe_float(p_dict.get('พื้นที่_ตารางวา'), 0.0)
    if sqw <= 0 and 'เนื้อที่ (ตร.ว.)' in p_dict:
        sqw = to_float_sqwah(p_dict.get('เนื้อที่ (ตร.ว.)')) or 0.0

    sqw_rate = 0.0
    if not is_condo:
        raw_puw = _safe_float(p_dict.get('ราคาต่อตารางวา'), 0.0)
        if raw_puw > 0:
            sqw_rate = raw_puw
        elif sqw > 0 and price > 0:
            sqw_rate = price / sqw

    sqm = _safe_float(p_dict.get('พื้นที่ใช้สอย (ตร.ม.)'), 0.0)
    sqm_rate = 0.0
    raw_pum = _safe_float(p_dict.get('ราคาต่อตารางเมตร'), 0.0)
    if raw_pum > 0:
        sqm_rate = raw_pum
    elif sqm > 0 and price > 0:
        sqm_rate = price / sqm

    return price, sqw, sqw_rate, sqm_rate, is_condo
