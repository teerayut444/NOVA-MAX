from datetime import datetime, timezone, timedelta
import numpy as np
import pandas as pd
import streamlit as st
from modules.services.data_loader import get_data_mtime
from modules.services.data_cleaner import is_invalid_project_name

_TH_TZ = timezone(timedelta(hours=7))
_TH_MONTHS_MAP = {
    1: 'ม.ค.', 2: 'ก.พ.', 3: 'มี.ค.', 4: 'เม.ย.',
    5: 'พ.ค.', 6: 'มิ.ย.', 7: 'ก.ค.', 8: 'ส.ค.',
    9: 'ก.ย.', 10: 'ต.ค.', 11: 'พ.ย.', 12: 'ธ.ค.',
}


def _as_clean_str(series, default=''):
    s = series.astype(object).fillna(default).astype(str).str.strip()
    return s.replace({'': default, 'nan': default, 'None': default, '<NA>': default, 'NaN': default})


def _parse_livinginsider_dates(raw_series):
    """Vectorized parser supporting Thai DD/MM/YYYY (BE/CE) and ISO YYYY-MM-DD date strings."""
    s = raw_series.astype(object).fillna('').astype(str).str.strip()
    result = pd.Series(pd.NaT, index=raw_series.index, dtype='datetime64[ns]')

    # 1. Slash format: D/M/YYYY (with optional trailing timestamp)
    m_slash = s.str.extract(r'^(\d{1,2})/(\d{1,2})/(\d{4})\b')
    has_slash = m_slash[0].notna()
    if has_slash.any():
        d = pd.to_numeric(m_slash.loc[has_slash, 0], errors='coerce')
        m = pd.to_numeric(m_slash.loc[has_slash, 1], errors='coerce')
        y = pd.to_numeric(m_slash.loc[has_slash, 2], errors='coerce')
        y = y.where(y <= 2400, y - 543)
        valid_rng = (y >= 1990) & (y <= 2100) & (m >= 1) & (m <= 12) & (d >= 1) & (d <= 31)
        if valid_rng.any():
            idx_ok = valid_rng[valid_rng].index
            date_str = (
                y.loc[idx_ok].astype(int).astype(str)
                + '-' + m.loc[idx_ok].astype(int).astype(str).str.zfill(2)
                + '-' + d.loc[idx_ok].astype(int).astype(str).str.zfill(2)
            )
            result.loc[idx_ok] = pd.to_datetime(date_str, format='%Y-%m-%d', errors='coerce')

    # 2. ISO/dash format: YYYY-MM-DD (for rows still NaT)
    rem_mask = result.isna() & (s != '')
    if rem_mask.any():
        m_iso = s.loc[rem_mask].str.extract(r'^(\d{4})-(\d{1,2})-(\d{1,2})\b')
        has_iso = m_iso[0].notna()
        if has_iso.any():
            idx_iso = has_iso[has_iso].index
            y = pd.to_numeric(m_iso.loc[idx_iso, 0], errors='coerce')
            m = pd.to_numeric(m_iso.loc[idx_iso, 1], errors='coerce')
            d = pd.to_numeric(m_iso.loc[idx_iso, 2], errors='coerce')
            y = y.where(y <= 2400, y - 543)
            valid_rng = (y >= 1990) & (y <= 2100) & (m >= 1) & (m <= 12) & (d >= 1) & (d <= 31)
            if valid_rng.any():
                idx_ok = valid_rng[valid_rng].index
                date_str = (
                    y.loc[idx_ok].astype(int).astype(str)
                    + '-' + m.loc[idx_ok].astype(int).astype(str).str.zfill(2)
                    + '-' + d.loc[idx_ok].astype(int).astype(str).str.zfill(2)
                )
                result.loc[idx_ok] = pd.to_datetime(date_str, format='%Y-%m-%d', errors='coerce')

    return result


def _format_thai_dates_vec(dt_series):
    """Vectorized formatting of datetime Series to Thai short date e.g. '15 ก.พ. 2569'."""
    out = pd.Series('-', index=dt_series.index, dtype=object)
    valid = dt_series.notna()
    if valid.any():
        v = dt_series.loc[valid]
        days_s = v.dt.day.astype(int).astype(str)
        months_s = v.dt.month.map(_TH_MONTHS_MAP).fillna('')
        years_s = (v.dt.year.astype(int) + 543).astype(str)
        out.loc[valid] = days_s + ' ' + months_s + ' ' + years_s
    return out


def _compute_livinginsider_project_metrics(_df_raw):
    """Core Livinginsider project-level velocity & price aggregation."""
    if _df_raw is None or _df_raw.empty:
        return []

    if 'บริษัท' in _df_raw.columns:
        li = _df_raw[_df_raw['บริษัท'].astype(str) == 'Livinginsider'].copy()
    else:
        li = _df_raw.copy()

    if li.empty:
        return []

    for col in ('วันประกาศ', 'ยอดเข้าชม', 'ยอดคลิก', 'ละติจูด', 'ลองจิจูด', 'ชื่อโครงการ', 'ราคา', 'ประเภททรัพย์', 'ตำบล', 'อำเภอ', 'จังหวัด', 'ลิงก์'):
        if col not in li.columns:
            li[col] = None

    # Parse dates (DD/MM/YYYY BE/CE and ISO YYYY-MM-DD)
    post_dates = _parse_livinginsider_dates(li['วันประกาศ'])
    today = pd.Timestamp(datetime.now(_TH_TZ).date())

    lat_num = pd.to_numeric(li['ละติจูด'], errors='coerce')
    lon_num = pd.to_numeric(li['ลองจิจูด'], errors='coerce')
    views_num = pd.to_numeric(li['ยอดเข้าชม'], errors='coerce').fillna(0.0)
    clicks_num = pd.to_numeric(li['ยอดคลิก'], errors='coerce').fillna(0.0)

    # Filter bbox, valid past/present dates (no future dates), and non-negative finite metrics BEFORE groupby
    valid_mask = (
        post_dates.notna()
        & (post_dates <= today)
        & np.isfinite(lat_num)
        & np.isfinite(lon_num)
        & (lat_num >= 5.0)
        & (lat_num <= 21.0)
        & (lon_num >= 97.0)
        & (lon_num <= 106.0)
        & np.isfinite(views_num)
        & np.isfinite(clicks_num)
        & (views_num >= 0)
        & (clicks_num >= 0)
        & (views_num < 1_000_000)
        & (clicks_num < 500_000)
    )
    if not valid_mask.any():
        return []

    li = li.loc[valid_mask].copy()
    post_dates = post_dates.loc[valid_mask]
    views = views_num.loc[valid_mask]
    clicks = clicks_num.loc[valid_mask]

    li['post_date'] = post_dates
    li['days_active'] = (today - post_dates).dt.days.clip(lower=1)
    li['vd'] = (views / li['days_active']).round(2)
    li['cd'] = (clicks / li['days_active']).round(2)
    li['lat'] = lat_num.loc[valid_mask]
    li['lon'] = lon_num.loc[valid_mask]

    price_raw = pd.to_numeric(li['ราคา'], errors='coerce')
    li['price'] = price_raw.where(np.isfinite(price_raw) & (price_raw > 0), np.nan)

    # Price per sq.m. and sq.wah
    if 'พื้นที่ใช้สอย (ตร.ม.)' in li.columns:
        if pd.api.types.is_numeric_dtype(li['พื้นที่ใช้สอย (ตร.ม.)']):
            sqm = pd.to_numeric(li['พื้นที่ใช้สอย (ตร.ม.)'], errors='coerce')
        else:
            sqm = pd.to_numeric(
                li['พื้นที่ใช้สอย (ตร.ม.)'].astype(object).fillna('').astype(str).str.replace(',', '', regex=False).str.strip(),
                errors='coerce',
            )
    else:
        sqm = pd.Series(np.nan, index=li.index, dtype='float64')

    if 'พื้นที่_ตารางวา' in li.columns:
        sqw = pd.to_numeric(li['พื้นที่_ตารางวา'], errors='coerce')
    else:
        sqw = pd.Series(np.nan, index=li.index, dtype='float64')

    sqm = sqm.where(np.isfinite(sqm) & (sqm >= 10) & (sqm <= 50_000), np.nan)
    sqw = sqw.where(np.isfinite(sqw) & (sqw >= 1) & (sqw <= 500_000), np.nan)

    li['p_sqm'] = (li['price'] / sqm).where(li['price'].notna() & sqm.notna(), np.nan)
    li['p_sqw'] = (li['price'] / sqw).where(li['price'].notna() & sqw.notna(), np.nan)

    # Clean string fields safely (Categorical-safe on Pandas 3.0)
    pt_clean = _as_clean_str(li['ประเภททรัพย์'], 'อื่นๆ')
    dist_clean = _as_clean_str(li['อำเภอ'], '-')
    subdist_clean = _as_clean_str(li['ตำบล'], '-')
    prov_clean = _as_clean_str(li['จังหวัด'], '-')
    proj_raw = _as_clean_str(li['ชื่อโครงการ'], '')

    # Detect missing or invalid project names via unique-value mapping (fast)
    unique_projs = proj_raw.unique()
    invalid_proj_set = {p for p in unique_projs if not p or p == '-' or is_invalid_project_name(p)}
    no_proj = proj_raw.isin(invalid_proj_set)

    sub_lbl = subdist_clean.replace({'-': ''})
    dist_lbl = dist_clean.replace({'-': ''})
    fallback_loc = (sub_lbl + ' ' + dist_lbl).str.strip()
    fallback_name = pt_clean + np.where(fallback_loc != '', ' (' + fallback_loc + ')', '')

    li['proj_clean'] = proj_raw.where(~no_proj, fallback_name)
    li['prov_clean'] = prov_clean
    li['_pt_clean'] = pt_clean
    li['_dist_clean'] = dist_clean
    li['_subdist_clean'] = subdist_clean

    # URL scheme allowlist (http:// or https:// only)
    links_raw = _as_clean_str(li['ลิงก์'], '')
    li['_link_clean'] = links_raw.where(links_raw.str.match(r'^https?://', case=False, na=False), '')

    # Vectorized dominant property type (mode) per (proj_clean, prov_clean)
    pt_counts = (
        li.groupby(['proj_clean', 'prov_clean', '_pt_clean'], sort=False, observed=True)
        .size()
        .reset_index(name='_pt_cnt')
        .sort_values(['_pt_cnt', '_pt_clean'], ascending=[False, True])
        .drop_duplicates(subset=['proj_clean', 'prov_clean'], keep='first')
    )
    dominant_pt = pt_counts.set_index(['proj_clean', 'prov_clean'])['_pt_clean']

    # Aggregate by (project clean name, province) using Median (robust to outliers)
    grp = li.groupby(['proj_clean', 'prov_clean'], sort=False, dropna=False).agg(
        units=('lat', 'count'),
        prov=('prov_clean', 'first'),
        dist=('_dist_clean', 'first'),
        subdist=('_subdist_clean', 'first'),
        lat=('lat', 'median'),
        lon=('lon', 'median'),
        price=('price', 'median'),
        min_p=('price', 'min'),
        max_p=('price', 'max'),
        p_sqm=('p_sqm', 'median'),
        p_sqw=('p_sqw', 'median'),
        vd=('vd', 'median'),
        cd=('cd', 'median'),
        sum_vd=('vd', 'sum'),
        sum_cd=('cd', 'sum'),
        days=('days_active', 'median'),
        start_date=('post_date', 'min'),
        end_date=('post_date', 'max'),
        link=('_link_clean', lambda s: next((x for x in s if x), '')),
    )
    grp['prop_type'] = dominant_pt.reindex(grp.index).fillna('อื่นๆ')
    grp = grp.reset_index()

    # Vectorized Thai Buddhist Era date formatting
    grp['start_dt'] = _format_thai_dates_vec(grp['start_date'])
    grp['end_dt'] = _format_thai_dates_vec(grp['end_date'])
    grp = grp.drop(columns=['start_date', 'end_date'])

    # Clean & format numeric/string columns (guarantee zero NaN/inf in JSON output)
    grp['lat'] = grp['lat'].round(6)
    grp['lon'] = grp['lon'].round(6)
    grp['vd'] = grp['vd'].fillna(0.0).round(2)
    grp['cd'] = grp['cd'].fillna(0.0).round(2)
    grp['sum_vd'] = grp['sum_vd'].fillna(0.0).round(1)
    grp['sum_cd'] = grp['sum_cd'].fillna(0.0).round(1)
    grp['price'] = grp['price'].fillna(0.0).round(0)
    grp['min_p'] = grp['min_p'].fillna(0.0).round(0)
    grp['max_p'] = grp['max_p'].fillna(0.0).round(0)
    grp['p_sqm'] = grp['p_sqm'].fillna(0.0).round(0)
    grp['p_sqw'] = grp['p_sqw'].fillna(0.0).round(0)
    grp['days'] = grp['days'].fillna(1.0).round(0)
    grp['prov'] = _as_clean_str(grp['prov'], '-')
    grp['dist'] = _as_clean_str(grp['dist'], '-')
    grp['subdist'] = _as_clean_str(grp['subdist'], '-')
    grp['prop_type'] = _as_clean_str(grp['prop_type'], 'อื่นๆ')
    grp['link'] = _as_clean_str(grp['link'], '')

    if 'prov_clean' in grp.columns:
        grp = grp.drop(columns=['prov_clean'])
    grp = grp.rename(columns={'proj_clean': 'name'})

    return grp.to_dict(orient='records')


@st.cache_data(show_spinner=False, max_entries=8, ttl=86400)
def _get_livinginsider_project_metrics_cached(_df_raw, cache_key=None):
    return _compute_livinginsider_project_metrics(_df_raw)


def get_livinginsider_project_metrics(df_raw, cache_key=None):
    """Public wrapper caching Livinginsider metrics by (data_mtime, len(df_raw), th_date) with custom-import isolation."""
    if df_raw is None or df_raw.empty:
        return []
    th_date = datetime.now(_TH_TZ).strftime("%Y-%m-%d")

    has_custom_imports = False
    custom_fp = None
    try:
        if hasattr(st, "session_state"):
            imp_df = st.session_state.get("imported_custom_df")
            if imp_df is not None and not imp_df.empty:
                has_custom_imports = True
                custom_fp = st.session_state.get("_custom_import_fp") or st.session_state.get("_custom_import_ver")
    except Exception:
        pass

    if has_custom_imports and cache_key is None:
        # Avoid cross-user cache collision when session has custom imports without an explicit content fingerprint
        if custom_fp is None:
            return _compute_livinginsider_project_metrics(df_raw)
        cache_key = (get_data_mtime(), len(df_raw), custom_fp, th_date)
    elif cache_key is None:
        cache_key = (get_data_mtime(), len(df_raw), th_date)
    else:
        cache_key = (cache_key, th_date)
    return _get_livinginsider_project_metrics_cached(df_raw, cache_key=cache_key)
