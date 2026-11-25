"""Batch reference property radius matching, group statistics, and grouped CSV/Excel export service."""

import hashlib
import io
import math
import re
import numpy as np
import pandas as pd

from modules.config.constants import is_true_centroid
from modules.services.data_cleaner import (
    ensure_derived_cols,
    format_coord_vectorized,
    format_to_rai_ngan_wah,
    to_float_sqm,
    to_float_sqwah,
)
from modules.services.export_service import (
    EXCEL_MAX_DATA_ROWS,
    _prepare_export_df,
    _read_uploaded_dataframe,
    convert_df_to_csv,
    convert_df_to_excel,
)
from modules.services.geo_service import haversine_distance_vectorized

try:
    from scipy.spatial import cKDTree as _cKDTree
except Exception:
    _cKDTree = None

_EARTH_RADIUS_KM = 6371.0
CONDO_PATTERN = r"คอนโด|ห้องชุด|อาคารชุด"
_CONDO_RE = re.compile(CONDO_PATTERN, re.IGNORECASE)


def _safe_float(val, default=0.0):
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


def _is_centroid_series(df_obj):
    if df_obj is None or df_obj.empty:
        return pd.Series(dtype=bool)
    if "is_centroid" not in df_obj.columns:
        return pd.Series(False, index=df_obj.index, dtype=bool)
    col = df_obj["is_centroid"]
    if pd.api.types.is_bool_dtype(col):
        return col.fillna(False).astype(bool)
    if pd.api.types.is_numeric_dtype(col):
        return (pd.to_numeric(col, errors="coerce").fillna(0.0) != 0.0).astype(bool)
    raw = col.astype(object)
    u_map = {v: bool(is_true_centroid(v)) for v in raw.dropna().unique()}
    return raw.map(u_map).fillna(False).astype(bool)


def _clean_str_series(s, default="-"):
    if isinstance(s.dtype, pd.CategoricalDtype):
        cats = [str(c).strip() for c in s.cat.categories]
        cat_map = {
            orig: (default if cln in ("", "-", "nan", "None", "null", "<NA>") else cln)
            for orig, cln in zip(s.cat.categories, cats)
        }
        return s.astype(object).map(cat_map).fillna(default)
    uniq = s.dropna().unique()
    if len(uniq) < len(s) * 0.4:
        u_map = {
            v: (default if str(v).strip() in ("", "-", "nan", "None", "null", "<NA>") else str(v).strip())
            for v in uniq
        }
        return s.map(u_map).fillna(default)
    return (
        s.astype(object)
        .fillna(default)
        .astype(str)
        .str.strip()
        .replace({"": default, "nan": default, "None": default, "null": default, "<NA>": default})
    )


def _sqw_from_df(df_obj):
    if df_obj is None or df_obj.empty:
        return pd.Series(dtype=float)
    if "พื้นที่_ตารางวา" in df_obj.columns:
        sqw_num = pd.to_numeric(df_obj["พื้นที่_ตารางวา"], errors="coerce")
        if "เนื้อที่ (ตร.ว.)" in df_obj.columns and sqw_num.isna().any():
            raw_obj = df_obj["เนื้อที่ (ตร.ว.)"].astype(object)
            na_mask = sqw_num.isna()
            u_raw = raw_obj.loc[na_mask].dropna().unique()
            if len(u_raw) > 0:
                u_map = {v: to_float_sqwah(v) for v in u_raw}
                sqw_num = sqw_num.fillna(pd.to_numeric(raw_obj.map(u_map), errors="coerce"))
        return sqw_num
    if "เนื้อที่ (ตร.ว.)" in df_obj.columns:
        raw_obj = df_obj["เนื้อที่ (ตร.ว.)"].astype(object)
        u_map = {v: to_float_sqwah(v) for v in raw_obj.dropna().unique()}
        return pd.to_numeric(raw_obj.map(u_map), errors="coerce")
    return pd.Series(np.nan, index=df_obj.index, dtype=float)


def _sqm_from_df(df_obj):
    if df_obj is None or df_obj.empty or "พื้นที่ใช้สอย (ตร.ม.)" not in df_obj.columns:
        return pd.Series(np.nan, index=df_obj.index if df_obj is not None else [], dtype=float)
    raw_col = df_obj["พื้นที่ใช้สอย (ตร.ม.)"]
    sqm_num = pd.to_numeric(raw_col, errors="coerce")
    if not pd.api.types.is_numeric_dtype(raw_col) and sqm_num.isna().any():
        raw_obj = raw_col.astype(object)
        na_mask = sqm_num.isna()
        u_raw = raw_obj.loc[na_mask].dropna().unique()
        if len(u_raw) > 0:
            u_map = {v: to_float_sqm(v) for v in u_raw}
            sqm_num = sqm_num.fillna(pd.to_numeric(raw_obj.map(u_map), errors="coerce"))
    return sqm_num.where(sqm_num > 0, np.nan)


def _sqw_rate_from_df(df_obj, sqw_vals=None, price_vals=None):
    if df_obj is None or df_obj.empty:
        return pd.Series(dtype=float)
    p_num = price_vals if price_vals is not None else (
        pd.to_numeric(df_obj["ราคา"], errors="coerce") if "ราคา" in df_obj.columns else pd.Series(np.nan, index=df_obj.index, dtype=float)
    )
    s_num = sqw_vals if sqw_vals is not None else _sqw_from_df(df_obj)
    puw_vals = (
        pd.to_numeric(df_obj["ราคาต่อตารางวา"], errors="coerce")
        if "ราคาต่อตารางวา" in df_obj.columns
        else pd.Series(np.nan, index=df_obj.index, dtype=float)
    )
    if "ราคาต่อหน่วย" in df_obj.columns:
        puw_vals = puw_vals.combine_first(pd.to_numeric(df_obj["ราคาต่อหน่วย"], errors="coerce"))
    fallback = np.where((p_num > 0) & (s_num > 0), p_num / s_num, np.nan)
    rates = np.where(puw_vals.notna() & (puw_vals > 0), puw_vals, fallback)
    return pd.Series(rates, index=df_obj.index, dtype=float)


def _sqm_rate_from_df(df_obj, sqm_vals=None, price_vals=None):
    if df_obj is None or df_obj.empty:
        return pd.Series(dtype=float)
    p_num = price_vals if price_vals is not None else (
        pd.to_numeric(df_obj["ราคา"], errors="coerce") if "ราคา" in df_obj.columns else pd.Series(np.nan, index=df_obj.index, dtype=float)
    )
    m_num = sqm_vals if sqm_vals is not None else _sqm_from_df(df_obj)
    pum_vals = (
        pd.to_numeric(df_obj["ราคาต่อตารางเมตร"], errors="coerce")
        if "ราคาต่อตารางเมตร" in df_obj.columns
        else pd.Series(np.nan, index=df_obj.index, dtype=float)
    )
    fallback = np.where((p_num > 0) & (m_num > 0), p_num / m_num, np.nan)
    rates = np.where(pum_vals.notna() & (pum_vals > 0), pum_vals, fallback)
    return pd.Series(rates, index=df_obj.index, dtype=float)

STAT_COL_PRICE_MEAN = "ราคาเฉลี่ย (บาท)"
STAT_COL_PRICE_MEDIAN = "ราคากลาง Median (บาท)"
STAT_COL_SQW_MEAN = "ราคาต่อตร.ว. เฉลี่ย (บาท)"
STAT_COL_SQW_MEDIAN = "ราคาต่อตร.ว. Median (บาท)"
STAT_COL_SQM_MEAN = "ราคาต่อตร.ม. เฉลี่ย (บาท)"
STAT_COL_SQM_MEDIAN = "ราคาต่อตร.ม. Median (บาท)"

STAT_SUMMARY_COLUMNS = (
    STAT_COL_PRICE_MEAN,
    STAT_COL_PRICE_MEDIAN,
    STAT_COL_SQW_MEAN,
    STAT_COL_SQW_MEDIAN,
    STAT_COL_SQM_MEAN,
    STAT_COL_SQM_MEDIAN,
)

# Columns mapped into the standard NOVA export layout (not treated as extra uploaded columns)
_STANDARD_INPUT_COLS = frozenset({
    "บริษัท",
    "รหัสทรัพย์",
    "ชื่อโครงการ",
    "ชื่อประกาศ",
    "ประเภททรัพย์",
    "ประเภทการขาย",
    "ราคา",
    "ราคา (บาท)",
    "ราคาขาย (บาท)",
    "ราคาขายได้",
    "เนื้อที่ (ตร.ว.)",
    "เนื้อที่ (ไร่-งาน-ตร.ว.)",
    "เนื้อที่(ไร่-งาน-ตร.ว.)",
    "เนื้อที่ (ไร่-งาน-วา)",
    "พื้นที่ (ไร่-งาน-วา)",
    "พื้นที่ (ไร่-งาน-ตร.ว.)",
    "พื้นที่_ตารางวา",
    "เนื้อที่_ตารางวา",
    "เนื้อที่",
    "พื้นที่ดิน",
    "ไร่",
    "งาน",
    "ตร.ว.",
    "ตารางวา",
    "วา",
    "พื้นที่ใช้สอย (ตร.ม.)",
    "ราคาต่อตารางวา",
    "ราคาต่อตร.ว. (บาท)",
    "ราคาต่อหน่วย",
    "ราคาต่อตารางเมตร",
    "ราคาต่อตร.ม. (บาท)",
    "ระยะทาง (กม.)",
    "ชั้น",
    "ห้องนอน",
    "ห้องน้ำ",
    "ที่จอดรถ",
    "ตำบล",
    "อำเภอ",
    "จังหวัด",
    "ภาค",
    "ละติจูด",
    "ลองจิจูด",
    "เลขโฉนด",
    "ลิงก์",
    "เปิดลิงก์",
    "โจทก์",
    "ศาล",
    "วันประกาศ",
    "วันที่ขาย",
    "วันที่ดึงข้อมูล",
    "ยอดเข้าชม",
    "ยอดคลิก",
    "is_centroid",
    "norm_project_name",
    "_is_derived_clean",
})

_GROUPED_EXCEL_STYLE_MAX_ROWS = EXCEL_MAX_DATA_ROWS


def _empty_stat_dict():
    return {col: np.nan for col in STAT_SUMMARY_COLUMNS}


def _mean_median_pos(values):
    """Returns (mean, median) over finite values > 0 rounded to 2 decimals, or (nan, nan)."""
    if values is None:
        return np.nan, np.nan
    arr = np.asarray(values, dtype=np.float64)
    if arr.size == 0:
        return np.nan, np.nan
    valid = arr[np.isfinite(arr) & (arr > 0.0)]
    if valid.size == 0:
        return np.nan, np.nan
    return round(float(np.mean(valid)), 2), round(float(np.median(valid)), 2)


def compute_group_price_stats(df_group, *, is_condo=False):
    """Computes the 6 summary statistics (Mean & Median for Price, Price/Sq.Wah, Price/Sq.M.)."""
    if df_group is None or df_group.empty:
        return _empty_stat_dict()

    if "ราคา (บาท)" in df_group.columns:
        price_s = pd.to_numeric(df_group["ราคา (บาท)"], errors="coerce")
    elif "ราคา" in df_group.columns:
        price_s = pd.to_numeric(df_group["ราคา"], errors="coerce")
    else:
        price_s = pd.Series(np.nan, index=df_group.index, dtype=float)

    if is_condo:
        sqw_rates = np.array([], dtype=np.float64)
    elif "ราคาต่อตร.ว. (บาท)" in df_group.columns:
        sqw_rates = pd.to_numeric(df_group["ราคาต่อตร.ว. (บาท)"], errors="coerce").to_numpy(dtype=np.float64)
    else:
        sqw_s = _sqw_rate_from_df(df_group, price_vals=price_s)
        if "ประเภททรัพย์" in df_group.columns:
            condo_m = df_group["ประเภททรัพย์"].astype(str).str.contains(CONDO_PATTERN, case=False, na=False)
            sqw_s = sqw_s.mask(condo_m, np.nan)
        sqw_rates = sqw_s.to_numpy(dtype=np.float64)

    if "ราคาต่อตร.ม. (บาท)" in df_group.columns:
        sqm_rates = pd.to_numeric(df_group["ราคาต่อตร.ม. (บาท)"], errors="coerce").to_numpy(dtype=np.float64)
    else:
        sqm_rates = _sqm_rate_from_df(df_group, price_vals=price_s).to_numpy(dtype=np.float64)

    p_mean, p_med = _mean_median_pos(price_s.to_numpy(dtype=np.float64))
    sqw_mean, sqw_med = _mean_median_pos(sqw_rates)
    sqm_mean, sqm_med = _mean_median_pos(sqm_rates)

    return {
        STAT_COL_PRICE_MEAN: p_mean,
        STAT_COL_PRICE_MEDIAN: p_med,
        STAT_COL_SQW_MEAN: sqw_mean,
        STAT_COL_SQW_MEDIAN: sqw_med,
        STAT_COL_SQM_MEAN: sqm_mean,
        STAT_COL_SQM_MEDIAN: sqm_med,
    }


def append_summary_stat_columns(df_export):
    """Appends the 6 Mean/Median summary columns to a Tab 2 comparison export DataFrame."""
    if df_export is None or df_export.empty:
        return df_export
    stats = compute_group_price_stats(df_export, is_condo=False)
    out = df_export.copy(deep=False)
    for col_name in STAT_SUMMARY_COLUMNS:
        out[col_name] = stats[col_name]
    return out


def _latlon_to_unit_xyz(lats_deg, lons_deg):
    lat_rad = np.radians(lats_deg)
    lon_rad = np.radians(lons_deg)
    cos_lat = np.cos(lat_rad)
    return np.column_stack((cos_lat * np.cos(lon_rad), cos_lat * np.sin(lon_rad), np.sin(lat_rad)))


def _km_to_chord(radius_km):
    half_angle = min(math.pi / 2.0, max(0.0, float(radius_km) / (2.0 * _EARTH_RADIUS_KM)))
    return 2.0 * math.sin(half_angle)


def _normalize_uploaded_ref_df(raw_df):
    """Normalizes an uploaded reference DataFrame without touching global dashboard caches."""
    if raw_df is None or raw_df.empty:
        return pd.DataFrame(), [], {
            "total_rows": 0,
            "valid_coord_rows": 0,
            "invalid_coord_rows": 0,
            "prop_types": [],
            "missing_required": ["ละติจูด", "ลองจิจูด", "ประเภททรัพย์"],
            "extra_cols": [],
        }

    df = raw_df.copy()
    df.columns = [str(c).strip() for c in df.columns]

    # Support common Thai/English aliases for coordinates & essential fields if canonical column absent
    alias_map = {
        "ละติจูด": ("lat", "latitude", "Lat", "Latitude", "LAT", "LATITUDE", "พิกัดละติจูด"),
        "ลองจิจูด": ("lon", "lng", "long", "longitude", "Lon", "Lng", "Long", "Longitude", "LON", "LNG", "LONGITUDE", "พิกัดลองจิจูด"),
        "ราคา": ("ราคา (บาท)", "ราคาขาย (บาท)", "ราคาขาย", "price", "Price", "PRICE"),
        "รหัสทรัพย์": ("รหัส", "รหัสทรัพย์สิน", "asset_id", "property_id", "code", "Code", "ID"),
        "ประเภททรัพย์": ("ประเภท", "ประเภททรัพย์สิน", "property_type", "type", "Type"),
        "ชื่อโครงการ": ("โครงการ", "project", "Project"),
    }
    for canonical, aliases in alias_map.items():
        if canonical not in df.columns:
            for al in aliases:
                if al in df.columns:
                    df[canonical] = df[al]
                    break

    raw_cols_ordered = list(df.columns)
    missing_required = [c for c in ("ละติจูด", "ลองจิจูด", "ประเภททรัพย์") if c not in df.columns]

    # Identify extra user-provided columns before ensure_derived_cols adds derived fields
    extra_cols = [
        c for c in raw_cols_ordered
        if c not in _STANDARD_INPUT_COLS
        and c not in STAT_SUMMARY_COLUMNS
        and not str(c).startswith("_")
    ]
    # Keep a clean copy of extra columns so ensure_derived_cols never mutates/drops them
    extra_df = df[extra_cols].copy() if extra_cols else pd.DataFrame(index=df.index)

    if "บริษัท" not in df.columns:
        df["บริษัท"] = "ทรัพย์อ้างอิง"
    else:
        blank_co = df["บริษัท"].isna() | df["บริษัท"].astype(str).str.strip().isin(("", "-", "nan", "None", "null", "<NA>"))
        if blank_co.any():
            df.loc[blank_co, "บริษัท"] = "ทรัพย์อ้างอิง"

    if "รหัสทรัพย์" not in df.columns:
        df["รหัสทรัพย์"] = [f"REF-{i + 1:03d}" for i in range(len(df))]
    else:
        code_s = df["รหัสทรัพย์"].astype(object)
        blank_code = code_s.isna() | code_s.astype(str).str.strip().isin(("", "-", "nan", "None", "null", "<NA>"))
        if blank_code.any():
            fallback_codes = pd.Series([f"REF-{i + 1:03d}" for i in range(len(df))], index=df.index)
            df.loc[blank_code, "รหัสทรัพย์"] = fallback_codes.loc[blank_code]
        df["รหัสทรัพย์"] = df["รหัสทรัพย์"].astype(str).str.strip()

    if "ประเภททรัพย์" not in df.columns:
        df["ประเภททรัพย์"] = "อื่นๆ"

    # Run NOVA standard cleaner (normalizes ประเภททรัพย์, ราคา, Rai/Ngan/Wah, sqm, unit rates, coords)
    cleaned = ensure_derived_cols(df, persist_cache=False)

    # Restore extra columns cleanly aligned by index
    for ec in extra_cols:
        if ec in extra_df.columns:
            cleaned[ec] = extra_df.loc[cleaned.index, ec]

    # Preserve original row order as 1-based reference sequence
    cleaned = cleaned.reset_index(drop=True)
    lat_num = pd.to_numeric(cleaned["ละติจูด"], errors="coerce") if "ละติจูด" in cleaned.columns else pd.Series(np.nan, index=cleaned.index)
    lon_num = pd.to_numeric(cleaned["ลองจิจูด"], errors="coerce") if "ลองจิจูด" in cleaned.columns else pd.Series(np.nan, index=cleaned.index)
    valid_mask = (
        lat_num.notna()
        & lon_num.notna()
        & np.isfinite(lat_num)
        & np.isfinite(lon_num)
        & lat_num.between(5.0, 21.0)
        & lon_num.between(97.0, 106.0)
    )
    cleaned["_batch_valid_coord"] = valid_mask.astype(bool)

    prop_types = sorted({
        str(t).strip()
        for t in cleaned["ประเภททรัพย์"].dropna().unique()
        if str(t).strip() not in ("", "-", "nan", "None", "<NA>")
    })

    audit = {
        "total_rows": len(cleaned),
        "valid_coord_rows": int(valid_mask.sum()),
        "invalid_coord_rows": int((~valid_mask).sum()),
        "prop_types": prop_types,
        "missing_required": missing_required,
        "extra_cols": extra_cols,
    }
    return cleaned, extra_cols, audit


def parse_batch_reference_upload(uploaded_file):
    """Reads and normalizes an uploaded CSV/Excel file for Tab 2 Batch Reference mode."""
    raw_df = _read_uploaded_dataframe(uploaded_file)
    return _normalize_uploaded_ref_df(raw_df)


def compute_batch_ref_fingerprint(ref_df, radius_km, companies, exclude_centroids, match_same_type, exclude_self, data_mtime):
    """Deterministic fingerprint for caching batch grouped export results."""
    h = hashlib.blake2b(digest_size=12)
    n = len(ref_df) if ref_df is not None else 0
    co_str = ",".join(sorted(str(c) for c in (companies or [])))
    h.update(
        f"n={n}|r={float(radius_km):.3f}|co={co_str}|ec={int(bool(exclude_centroids))}|"
        f"mt={int(bool(match_same_type))}|es={int(bool(exclude_self))}|dm={data_mtime}".encode("utf-8")
    )
    if ref_df is not None and not ref_df.empty:
        sample_idx = sorted({0, min(1, n - 1), n // 2, max(0, n - 2), n - 1})
        key_cols = [c for c in ("รหัสทรัพย์", "ประเภททรัพย์", "ละติจูด", "ลองจิจูด", "ราคา") if c in ref_df.columns]
        for row in ref_df.iloc[sample_idx][key_cols].itertuples(index=False, name=None):
            h.update(repr(row).encode("utf-8", errors="ignore"))
    return h.hexdigest()


def _format_standard_rows(df_part, *, distances=None):
    """Formats a DataFrame slice (reference rows or DB nearby rows) into NOVA standard export columns."""
    out = pd.DataFrame(index=df_part.index)
    for col in ("บริษัท", "รหัสทรัพย์", "ชื่อโครงการ", "ประเภททรัพย์"):
        if col in df_part.columns:
            out[col] = _clean_str_series(df_part[col], "-")
        else:
            out[col] = "-"

    price_num = pd.to_numeric(df_part["ราคา"], errors="coerce") if "ราคา" in df_part.columns else pd.Series(np.nan, index=df_part.index, dtype=float)
    out["ราคา (บาท)"] = price_num.to_numpy(dtype=np.float64)

    sqw_vals = _sqw_from_df(df_part)
    if "เนื้อที่ (ตร.ว.)" in df_part.columns:
        raw_sqw_obj = df_part["เนื้อที่ (ตร.ว.)"].astype(object)
        u_str = raw_sqw_obj.dropna().unique()
        formatted_sqw = raw_sqw_obj.map({v: format_to_rai_ngan_wah(v) for v in u_str}).astype(object).fillna("-")
        need_num = (formatted_sqw == "-") & sqw_vals.notna()
        if need_num.any():
            u_num = sqw_vals.loc[need_num].dropna().unique()
            formatted_sqw.loc[need_num] = (
                sqw_vals.loc[need_num].astype(object).map({v: format_to_rai_ngan_wah(v) for v in u_num}).astype(object).fillna("-")
            )
    else:
        u_num = sqw_vals.dropna().unique()
        formatted_sqw = sqw_vals.astype(object).map({v: format_to_rai_ngan_wah(v) for v in u_num}).astype(object).fillna("-")

    is_condo_row = (
        df_part["ประเภททรัพย์"].astype(str).str.contains(CONDO_PATTERN, case=False, na=False)
        if "ประเภททรัพย์" in df_part.columns
        else pd.Series(False, index=df_part.index)
    )
    sqw_rate_s = _sqw_rate_from_df(df_part, sqw_vals=sqw_vals, price_vals=price_num).mask(is_condo_row, np.nan)
    formatted_sqw = formatted_sqw.astype(object).mask(is_condo_row, "-")
    sqm_vals = _sqm_from_df(df_part)
    sqm_rate_s = _sqm_rate_from_df(df_part, sqm_vals=sqm_vals, price_vals=price_num)

    out["เนื้อที่ (ไร่-งาน-ตร.ว.)"] = formatted_sqw.to_numpy(dtype=object)
    out["ราคาต่อตร.ว. (บาท)"] = np.round(sqw_rate_s.to_numpy(dtype=np.float64), 2)
    out["พื้นที่ใช้สอย (ตร.ม.)"] = np.round(sqm_vals.to_numpy(dtype=np.float64), 2)
    out["ราคาต่อตร.ม. (บาท)"] = np.round(sqm_rate_s.to_numpy(dtype=np.float64), 2)

    if distances is not None:
        out["ระยะทาง (กม.)"] = np.round(np.asarray(distances, dtype=np.float64), 2)
    else:
        out["ระยะทาง (กม.)"] = 0.0

    for col in ("ชั้น", "ห้องนอน", "ห้องน้ำ", "ที่จอดรถ", "ตำบล", "อำเภอ", "จังหวัด"):
        out[col] = _clean_str_series(df_part[col], "-") if col in df_part.columns else "-"

    out["ละติจูด"] = format_coord_vectorized(df_part, "ละติจูด") if "ละติจูด" in df_part.columns else "-"
    out["ลองจิจูด"] = format_coord_vectorized(df_part, "ลองจิจูด") if "ลองจิจูด" in df_part.columns else "-"
    out["เลขโฉนด"] = _clean_str_series(df_part["เลขโฉนด"], "-") if "เลขโฉนด" in df_part.columns else "-"
    out["ลิงก์"] = _clean_str_series(df_part["ลิงก์"], "-") if "ลิงก์" in df_part.columns else "-"
    return out


class _SpatialPoolIndex:
    """Fast radius query index (3D unit-sphere cKDTree with vectorized bbox fallback)."""

    def __init__(self, df_slice):
        self.df = df_slice.reset_index(drop=True)
        self.lats = pd.to_numeric(self.df["ละติจูด"], errors="coerce").to_numpy(dtype=np.float64)
        self.lons = pd.to_numeric(self.df["ลองจิจูด"], errors="coerce").to_numpy(dtype=np.float64)
        self.codes_lower = (
            self.df["รหัสทรัพย์"].astype(object).fillna("").astype(str).str.strip().str.lower().to_numpy()
            if "รหัสทรัพย์" in self.df.columns
            else np.full(len(self.df), "", dtype=object)
        )
        self.companies_lower = (
            self.df["บริษัท"].astype(object).fillna("").astype(str).str.strip().str.lower().to_numpy()
            if "บริษัท" in self.df.columns
            else np.full(len(self.df), "", dtype=object)
        )
        self.prices = (
            pd.to_numeric(self.df["ราคา"], errors="coerce").to_numpy(dtype=np.float64)
            if "ราคา" in self.df.columns
            else np.full(len(self.df), np.nan, dtype=np.float64)
        )
        self.sqw_rates = _sqw_rate_from_df(self.df).to_numpy(dtype=np.float64)
        if "ประเภททรัพย์" in self.df.columns:
            condo_m = self.df["ประเภททรัพย์"].astype(str).str.contains(CONDO_PATTERN, case=False, na=False).to_numpy()
            self.sqw_rates = np.where(condo_m, np.nan, self.sqw_rates)
        self.sqm_rates = _sqm_rate_from_df(self.df).to_numpy(dtype=np.float64)

        self.tree = None
        if _cKDTree is not None and len(self.df) > 0:
            try:
                self.tree = _cKDTree(_latlon_to_unit_xyz(self.lats, self.lons))
            except Exception:
                self.tree = None

    def query(self, lat, lon, radius_km):
        if len(self.df) == 0:
            return np.empty(0, dtype=np.int64), np.empty(0, dtype=np.float64)

        if self.tree is not None:
            q_xyz = _latlon_to_unit_xyz(np.array([lat]), np.array([lon]))[0]
            # Slight chord margin to avoid float boundary misses before exact Haversine check
            chord = _km_to_chord(radius_km * 1.005 + 0.01)
            cand_idx = np.asarray(self.tree.query_ball_point(q_xyz, r=chord), dtype=np.int64)
        else:
            cos_lat = max(0.1, abs(math.cos(math.radians(lat))))
            lat_m = (radius_km / 110.574) + 0.015
            lon_m = (radius_km / (111.32 * cos_lat)) + 0.015
            mask = (
                (self.lats >= lat - lat_m)
                & (self.lats <= lat + lat_m)
                & (self.lons >= lon - lon_m)
                & (self.lons <= lon + lon_m)
            )
            cand_idx = np.flatnonzero(mask)

        if cand_idx.size == 0:
            return np.empty(0, dtype=np.int64), np.empty(0, dtype=np.float64)

        dists = haversine_distance_vectorized(lat, lon, self.lats[cand_idx], self.lons[cand_idx])
        within = np.isfinite(dists) & (dists <= radius_km)
        if not np.any(within):
            return np.empty(0, dtype=np.int64), np.empty(0, dtype=np.float64)

        matched_idx = cand_idx[within]
        matched_dists = dists[within]
        order = np.argsort(matched_dists, kind="mergesort")
        return matched_idx[order], matched_dists[order]


def build_batch_grouped_export_df(
    ref_df,
    db_df,
    radius_km=5.0,
    *,
    extra_cols=None,
    companies=None,
    exclude_centroids=True,
    match_same_type=True,
    exclude_self=True,
):
    """Builds the Grouped Details DataFrame for all imported reference properties.

    Each reference property forms a group:
      - First row: บทบาท = 'ทรัพย์อ้างอิง' (distance 0.00, carries extra_cols)
      - Following rows: บทบาท = 'ทรัพย์ใกล้เคียง' (sorted by distance ascending)
    All rows in the group carry the 6 group summary statistics (Mean & Median for
    Price, Price/Sq.Wah, Price/Sq.M.) computed strictly from matched nearby comparables.
    """
    extra_cols = [c for c in (extra_cols or []) if c in ref_df.columns] if ref_df is not None else []
    rad = max(0.05, min(50.0, _safe_float(radius_km, 5.0)))

    if ref_df is None or ref_df.empty:
        return pd.DataFrame(), {
            "total_refs": 0,
            "matched_refs": 0,
            "zero_match_refs": 0,
            "invalid_coord_refs": 0,
            "total_nearby_rows": 0,
            "total_output_rows": 0,
            "radius_km": rad,
        }

    # Prepare filtered DB pool once
    pool = pd.DataFrame()
    if db_df is not None and not db_df.empty and "ละติจูด" in db_df.columns and "ลองจิจูด" in db_df.columns:
        lat_n = pd.to_numeric(db_df["ละติจูด"], errors="coerce")
        lon_n = pd.to_numeric(db_df["ลองจิจูด"], errors="coerce")
        pool_mask = (
            lat_n.notna()
            & lon_n.notna()
            & lat_n.between(5.0, 21.0)
            & lon_n.between(97.0, 106.0)
        )
        if companies and "บริษัท" in db_df.columns:
            co_set = {str(c).strip() for c in companies if str(c).strip()}
            if co_set:
                pool_mask &= db_df["บริษัท"].astype(str).str.strip().isin(co_set)
        if exclude_centroids and "is_centroid" in db_df.columns:
            pool_mask &= ~_is_centroid_series(db_df)
        pool = db_df.loc[pool_mask]

    # Build spatial indexes lazily per property type (only for types present in ref_df!)
    type_indexes = {}
    all_pool_index = None
    if not pool.empty:
        if match_same_type and "ประเภททรัพย์" in pool.columns:
            needed_types = {
                str(t).strip()
                for t in ref_df["ประเภททรัพย์"].dropna().unique()
                if str(t).strip() not in ("", "-", "nan", "None", "<NA>")
            }
            pool_types_s = pool["ประเภททรัพย์"].astype(str).str.strip()
            for pt in needed_types:
                sub = pool.loc[pool_types_s == pt]
                if not sub.empty:
                    type_indexes[pt] = _SpatialPoolIndex(sub)
        else:
            all_pool_index = _SpatialPoolIndex(pool)

    # Pre-format all reference rows vectorized once
    ref_std_df = _format_standard_rows(ref_df, distances=np.zeros(len(ref_df), dtype=np.float64))
    ref_lats = pd.to_numeric(ref_df["ละติจูด"], errors="coerce").to_numpy(dtype=np.float64) if "ละติจูด" in ref_df.columns else np.full(len(ref_df), np.nan)
    ref_lons = pd.to_numeric(ref_df["ลองจิจูด"], errors="coerce").to_numpy(dtype=np.float64) if "ลองจิจูด" in ref_df.columns else np.full(len(ref_df), np.nan)
    ref_prices = pd.to_numeric(ref_df["ราคา"], errors="coerce").to_numpy(dtype=np.float64) if "ราคา" in ref_df.columns else np.full(len(ref_df), np.nan)

    group_frames = []
    matched_refs = 0
    zero_match_refs = 0
    invalid_coord_refs = 0
    total_nearby_rows = 0

    for i in range(len(ref_df)):
        group_no = i + 1
        ref_code = str(ref_std_df["รหัสทรัพย์"].iat[i]).strip()
        ref_code_l = ref_code.lower()
        ref_co_l = str(ref_std_df["บริษัท"].iat[i]).strip().lower()
        ref_type = str(ref_std_df["ประเภททรัพย์"].iat[i]).strip()
        ref_is_condo = bool(_CONDO_RE.search(ref_type))
        ref_lat = ref_lats[i]
        ref_lon = ref_lons[i]
        ref_price = ref_prices[i]

        has_valid_coord = _is_valid_thai_coord(ref_lat, ref_lon)
        matched_idx = np.empty(0, dtype=np.int64)
        matched_dists = np.empty(0, dtype=np.float64)
        idx_obj = None

        if not has_valid_coord:
            invalid_coord_refs += 1
            status_note = "พิกัดไม่ถูกต้อง/ว่าง"
        else:
            idx_obj = type_indexes.get(ref_type) if match_same_type else all_pool_index
            if idx_obj is not None:
                matched_idx, matched_dists = idx_obj.query(ref_lat, ref_lon, rad)
                if exclude_self and matched_idx.size > 0:
                    keep = np.ones(matched_idx.size, dtype=bool)
                    c_codes = idx_obj.codes_lower[matched_idx]
                    c_cos = idx_obj.companies_lower[matched_idx]
                    c_prices = idx_obj.prices[matched_idx]

                    # Exclude exact code match (when user supplied a real non-generated code)
                    is_generated_code = bool(re.match(r"^ref-\d{3,}$", ref_code_l))
                    if ref_code_l and ref_code_l != "-" and not is_generated_code:
                        code_same = (c_codes == ref_code_l)
                        if ref_co_l and ref_co_l not in ("-", "ทรัพย์อ้างอิง", "ไฟล์นำเข้า"):
                            keep &= ~(code_same & ((c_cos == ref_co_l) | (matched_dists <= 0.05)))
                        else:
                            keep &= ~(code_same & (matched_dists <= 0.05))

                    # Also exclude exact same spot (< 5m) with identical price (catches self without matching code)
                    if np.isfinite(ref_price) and ref_price > 0:
                        same_spot_price = (matched_dists < 0.005) & np.isfinite(c_prices) & (np.abs(c_prices - ref_price) < 1.0)
                        keep &= ~same_spot_price

                    matched_idx = matched_idx[keep]
                    matched_dists = matched_dists[keep]

            if matched_idx.size > 0:
                matched_refs += 1
                total_nearby_rows += int(matched_idx.size)
                status_note = "พบข้อมูล"
            else:
                zero_match_refs += 1
                status_note = "ไม่พบทรัพย์ใกล้เคียงในรัศมี"

        # Compute 6 group stats strictly from matched nearby comparables
        if matched_idx.size > 0 and idx_obj is not None:
            p_mean, p_med = _mean_median_pos(idx_obj.prices[matched_idx])
            sqw_mean, sqw_med = (np.nan, np.nan) if ref_is_condo else _mean_median_pos(idx_obj.sqw_rates[matched_idx])
            sqm_mean, sqm_med = _mean_median_pos(idx_obj.sqm_rates[matched_idx])
            g_stats = {
                STAT_COL_PRICE_MEAN: p_mean,
                STAT_COL_PRICE_MEDIAN: p_med,
                STAT_COL_SQW_MEAN: sqw_mean,
                STAT_COL_SQW_MEDIAN: sqw_med,
                STAT_COL_SQM_MEAN: sqm_mean,
                STAT_COL_SQM_MEDIAN: sqm_med,
            }
        else:
            g_stats = _empty_stat_dict()

        nearby_cnt = int(matched_idx.size)

        # Build group frame: Reference row on top + Nearby rows below
        ref_row_frame = ref_std_df.iloc[[i]].copy()
        if matched_idx.size > 0 and idx_obj is not None:
            nearby_std_frame = _format_standard_rows(idx_obj.df.iloc[matched_idx], distances=matched_dists)
            grp_df = pd.concat([ref_row_frame, nearby_std_frame], ignore_index=True)
            is_ref_flags = [True] + [False] * nearby_cnt
        else:
            grp_df = ref_row_frame.reset_index(drop=True)
            is_ref_flags = [True]

        # Append the 6 group summary stat columns ONLY on the Reference row (blank/NaN on nearby rows)
        for stat_col in STAT_SUMMARY_COLUMNS:
            stat_vals = np.full(len(grp_df), np.nan, dtype=np.float64)
            stat_vals[0] = g_stats[stat_col]
            grp_df[stat_col] = stat_vals

        # Append extra columns from uploaded file (populated on the Reference row of each group)
        for ec in extra_cols:
            col_vals = [None] * len(grp_df)
            raw_val = ref_df[ec].iat[i]
            col_vals[0] = None if (raw_val is None or (not isinstance(raw_val, str) and pd.isna(raw_val))) else raw_val
            grp_df[ec] = col_vals

        # Internal metadata columns (prefixed with '_' so _prepare_export_df strips them from output files)
        grp_df["_batch_group_no"] = group_no
        grp_df["_batch_is_ref"] = is_ref_flags
        grp_df["_batch_nearby_count"] = nearby_cnt
        grp_df["_batch_status"] = status_note

        group_frames.append(grp_df)

    grouped_df = pd.concat(group_frames, ignore_index=True) if group_frames else pd.DataFrame()
    summary_meta = {
        "total_refs": len(ref_df),
        "matched_refs": matched_refs,
        "zero_match_refs": zero_match_refs,
        "invalid_coord_refs": invalid_coord_refs,
        "total_nearby_rows": total_nearby_rows,
        "total_output_rows": len(grouped_df),
        "radius_km": rad,
    }
    return grouped_df, summary_meta


def convert_grouped_df_to_csv(grouped_df):
    """Exports grouped batch reference DataFrame as UTF-8 BOM CSV with formula sanitization."""
    return convert_df_to_csv(grouped_df)


def convert_grouped_df_to_excel(grouped_df):
    """Exports grouped batch reference DataFrame as styled Excel (.xlsx) with collapsed [+] row grouping."""
    if grouped_df is None or grouped_df.empty:
        return b""

    src_df = grouped_df.iloc[:EXCEL_MAX_DATA_ROWS] if len(grouped_df) > EXCEL_MAX_DATA_ROWS else grouped_df
    if "_batch_is_ref" in src_df.columns:
        is_ref_arr = src_df["_batch_is_ref"].fillna(False).astype(bool).to_numpy()
    elif "บทบาท" in src_df.columns:
        is_ref_arr = (src_df["บทบาท"].astype(str) == "ทรัพย์อ้างอิง").to_numpy()
    else:
        return convert_df_to_excel(src_df)

    if "_batch_nearby_count" in src_df.columns:
        nearby_cnt_arr = pd.to_numeric(src_df["_batch_nearby_count"], errors="coerce").fillna(0).astype(int).to_numpy()
    else:
        nearby_cnt_arr = np.zeros(len(src_df), dtype=int)
        for idx_r in range(len(src_df) - 1):
            if is_ref_arr[idx_r] and not is_ref_arr[idx_r + 1]:
                nearby_cnt_arr[idx_r] = 1

    df_out = _prepare_export_df(src_df, for_csv=False)
    excel_buffer = io.BytesIO()
    try:
        import xlsxwriter

        wb = xlsxwriter.Workbook(
            excel_buffer,
            {
                "in_memory": True,
                "constant_memory": True,
                "strings_to_formulas": False,
                "strings_to_urls": False,
                "nan_inf_to_errors": True,
            },
        )
        ws = wb.add_worksheet("Grouped_Reference")
        # Summary row is ABOVE detail rows so clicking [+] on each reference row expands its nearby comparables below
        ws.outline_settings(visible=True, symbols_below=False, symbols_right=True, auto_style=False)

        header_fmt = wb.add_format({
            "bold": True,
            "font_name": "Tahoma",
            "font_size": 10,
            "font_color": "#FFFFFF",
            "bg_color": "#047857",
            "border": 1,
            "border_color": "#065F46",
            "align": "center",
            "valign": "vcenter",
            "text_wrap": True,
        })
        stat_header_fmt = wb.add_format({
            "bold": True,
            "font_name": "Tahoma",
            "font_size": 10,
            "font_color": "#FFFFFF",
            "bg_color": "#0F766E",
            "border": 1,
            "border_color": "#115E59",
            "align": "center",
            "valign": "vcenter",
            "text_wrap": True,
        })
        ref_text_fmt = wb.add_format({
            "bold": True,
            "font_name": "Tahoma",
            "font_size": 10,
            "font_color": "#064E3B",
            "bg_color": "#D1FAE5",
            "border": 1,
            "border_color": "#A7F3D0",
            "valign": "vcenter",
        })
        ref_num_fmt = wb.add_format({
            "bold": True,
            "font_name": "Tahoma",
            "font_size": 10,
            "font_color": "#064E3B",
            "bg_color": "#D1FAE5",
            "border": 1,
            "border_color": "#A7F3D0",
            "num_format": "#,##0.00",
            "valign": "vcenter",
        })
        body_text_fmt = wb.add_format({
            "font_name": "Tahoma",
            "font_size": 10,
            "border": 1,
            "border_color": "#E2E8F0",
            "valign": "vcenter",
        })
        body_num_fmt = wb.add_format({
            "font_name": "Tahoma",
            "font_size": 10,
            "border": 1,
            "border_color": "#E2E8F0",
            "num_format": "#,##0.00",
            "valign": "vcenter",
        })

        cols = list(df_out.columns)
        stat_col_set = set(STAT_SUMMARY_COLUMNS)
        money_float_cols = {
            "ราคา (บาท)",
            "ราคาต่อตร.ว. (บาท)",
            "พื้นที่ใช้สอย (ตร.ม.)",
            "ราคาต่อตร.ม. (บาท)",
            "ระยะทาง (กม.)",
            *stat_col_set,
        }

        ws.set_row(0, 26)
        for c_idx, col_name in enumerate(cols):
            h_fmt = stat_header_fmt if col_name in stat_col_set else header_fmt
            ws.write_string(0, c_idx, str(col_name), h_fmt)
            if col_name in stat_col_set:
                ws.set_column(c_idx, c_idx, 20)
            elif col_name in ("ชื่อโครงการ", "ลิงก์"):
                ws.set_column(c_idx, c_idx, 24)
            elif col_name in ("ชั้น", "ห้องนอน", "ห้องน้ำ", "ที่จอดรถ"):
                ws.set_column(c_idx, c_idx, 10)
            else:
                ws.set_column(c_idx, c_idx, 16)

        for row_pos, row_vals in enumerate(df_out.itertuples(index=False, name=None)):
            r_idx = row_pos + 1
            is_ref_row = bool(is_ref_arr[row_pos])
            if is_ref_row:
                if int(nearby_cnt_arr[row_pos]) > 0:
                    ws.set_row(r_idx, 21, None, {"collapsed": True})
                else:
                    ws.set_row(r_idx, 21)
            else:
                ws.set_row(r_idx, 19, None, {"level": 1, "hidden": True})

            t_fmt = ref_text_fmt if is_ref_row else body_text_fmt
            n_fmt = ref_num_fmt if is_ref_row else body_num_fmt

            for c_idx, val in enumerate(row_vals):
                col_name = cols[c_idx]
                is_empty = val is None or (not isinstance(val, str) and pd.isna(val))
                if is_empty:
                    ws.write_blank(r_idx, c_idx, None, t_fmt)
                elif isinstance(val, (int, np.integer)) and not isinstance(val, bool):
                    ws.write_number(r_idx, c_idx, int(val), n_fmt)
                elif isinstance(val, (float, np.floating)):
                    f_val = float(val)
                    if math.isfinite(f_val):
                        ws.write_number(r_idx, c_idx, f_val, n_fmt)
                    else:
                        ws.write_blank(r_idx, c_idx, None, t_fmt)
                else:
                    s_val = str(val)
                    if col_name in money_float_cols:
                        try:
                            f_val = float(s_val)
                            if math.isfinite(f_val):
                                ws.write_number(r_idx, c_idx, f_val, n_fmt)
                                continue
                        except (ValueError, TypeError):
                            pass
                    ws.write_string(r_idx, c_idx, s_val, t_fmt)

        ws.freeze_panes(1, 2)
        ws.autofilter(0, 0, len(df_out), max(0, len(cols) - 1))
        wb.close()
        return excel_buffer.getvalue()
    except Exception:
        return convert_df_to_excel(df_out)


def build_map_batch_refs_payload(ref_df):
    """Builds a compact JSON-serializable list of imported reference rows for the Tab 2 map popup."""
    if ref_df is None or ref_df.empty:
        return []

    sqw_s = _sqw_from_df(ref_df)
    sqm_s = _sqm_from_df(ref_df)
    items = []
    for i in range(len(ref_df)):
        row = ref_df.iloc[i]
        lat = _safe_float(row.get("ละติจูด"), 0.0)
        lon = _safe_float(row.get("ลองจิจูด"), 0.0)
        valid = _is_valid_thai_coord(lat, lon)
        code = str(row.get("รหัสทรัพย์", f"REF-{i + 1:03d}") or f"REF-{i + 1:03d}").strip()
        company = str(row.get("บริษัท", "ทรัพย์อ้างอิง") or "ทรัพย์อ้างอิง").strip()
        prop_type = str(row.get("ประเภททรัพย์", "อื่นๆ") or "อื่นๆ").strip()
        project = str(row.get("ชื่อโครงการ", "") or "").strip()
        if project in ("-", "nan", "None", "<NA>"):
            project = ""
        price = _safe_float(row.get("ราคา"), 0.0)
        sqw = _safe_float(sqw_s.iat[i], 0.0) if i < len(sqw_s) else 0.0
        sqm = _safe_float(sqm_s.iat[i], 0.0) if i < len(sqm_s) else 0.0
        prov = str(row.get("จังหวัด", "") or "").strip()
        dist = str(row.get("อำเภอ", "") or "").strip()
        if prov in ("-", "nan", "None", "<NA>"):
            prov = ""
        if dist in ("-", "nan", "None", "<NA>"):
            dist = ""

        items.append({
            "idx": i + 1,
            "code": code[:80],
            "company": company[:60],
            "prop_type": prop_type[:60],
            "project": project[:80],
            "price": round(price, 2) if price > 0 else 0.0,
            "sqw": round(sqw, 2) if sqw > 0 else 0.0,
            "sqm": round(sqm, 2) if sqm > 0 else 0.0,
            "lat": round(lat, 6) if valid else None,
            "lon": round(lon, 6) if valid else None,
            "valid": bool(valid),
            "prov": prov[:50],
            "dist": dist[:50],
        })
    return items
