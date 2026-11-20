from datetime import datetime, timezone, timedelta
import base64
import gc
import gzip
import hashlib
import hmac
import html
import json
import os
from pathlib import Path
import re
import secrets
import threading
import numpy as np
import pandas as pd
import streamlit as st

_ROOT_DIR = Path(__file__).resolve().parents[2]
_TH_TZ = timezone(timedelta(hours=7))
_STATIC_DIR = _ROOT_DIR / "static"
_LEGACY_STATIC_MAP_PAYLOAD_PATH = str(_STATIC_DIR / "map_payload_cache.js")
_STATIC_PAYLOAD_LOCK = threading.Lock()
_SERVER_PAYLOAD_SECRET = b"NOVA_NPA_STATIC_MAP_BUNDLE_V3_2026"

from modules.config.constants import COMPANY_COLORS
from modules.services.data_cleaner import (
    ensure_derived_cols,
    parse_listing_age_days,
    parse_sold_date_value,
)
from modules.services.geo_service import (
    get_map_icon_atlas_and_mapping,
    get_leaflet_logo_dict,
)


def _resolve_root_file(rel_path):
    p_root = _ROOT_DIR / rel_path
    if p_root.exists():
        return p_root
    return Path(rel_path)


def _today_th_str():
    return datetime.now(_TH_TZ).strftime("%Y-%m-%d")


def _parse_sold_date_value(val):
    """Backwards-compatible alias delegating to data_cleaner.parse_sold_date_value."""
    return parse_sold_date_value(val)


def _safe_json_inline(obj):
    """Safely serialize Python data for inline JS inside <script>, neutralizing script breakout & line separators."""
    s = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    return (
        s.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("'", "\\u0027")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _replace_placeholders_single_pass(template_str, replacements):
    """Replaces all placeholder keys in a single regex pass so injected values cannot trigger other placeholders."""
    if not template_str or not replacements:
        return template_str
    pattern = re.compile("|".join(re.escape(k) for k in replacements.keys()))
    return pattern.sub(lambda m: replacements[m.group(0)], template_str)


def _hex_to_rgb_list(h):
    try:
        h = str(h).lstrip('#')
        if len(h) == 6:
            return [int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)]
    except Exception:
        pass
    return [99, 102, 241]


def _default_company_map_rgb():
    out = {k: _hex_to_rgb_list(v) for k, v in COMPANY_COLORS.items()}
    out.setdefault("LED Legal", [71, 85, 105])
    out.setdefault("LED_SOLD", [71, 85, 105])
    return out


_INVALID_STR_TOKENS = {'', 'nan', 'None', '<NA>', 'NaN', 'null', 'undefined'}


def _safe_str_series(series, default=''):
    """Categorical-safe conversion to stripped string Series on Pandas 3.0."""
    if isinstance(series.dtype, pd.CategoricalDtype):
        cats = [str(c).strip() for c in series.cat.categories]
        cats = [default if c in _INVALID_STR_TOKENS else c for c in cats]
        # Build deduplicated category list and remap codes without unpacking 461k object strings
        seen = {}
        new_cats = []
        remap = np.empty(len(cats) + 1, dtype='int32')
        for idx, c in enumerate(cats):
            pos = seen.get(c)
            if pos is None:
                pos = len(new_cats)
                seen[c] = pos
                new_cats.append(c)
            remap[idx] = pos
        def_pos = seen.get(default)
        if def_pos is None:
            def_pos = len(new_cats)
            seen[default] = def_pos
            new_cats.append(default)
        remap[len(cats)] = def_pos
        codes = series.cat.codes.to_numpy(dtype='int32', copy=False)
        safe_codes = np.where(codes >= 0, codes, len(cats))
        mapped_codes = remap[safe_codes]
        return pd.Series(pd.Categorical.from_codes(mapped_codes, categories=new_cats), index=series.index)
    s = series.astype(object).fillna(default).astype(str).str.strip()
    return s.replace({'': default, 'nan': default, 'None': default, '<NA>': default, 'NaN': default, 'null': default, 'undefined': default})


def _safe_bool_mask(series):
    if pd.api.types.is_bool_dtype(series.dtype):
        return series.fillna(False).astype(bool)
    return series.astype(object).fillna('').astype(str).str.strip().str.lower().isin({'true', '1', '1.0', 'yes', 't'})


def get_latest_parquet_path():
    """Returns the primary dashboard dataset path strictly: all_assets.parquet or all_asset.parquet."""
    for name in ("all_assets.parquet", "all_asset.parquet"):
        p_root = _ROOT_DIR / name
        if p_root.exists():
            return p_root
        p_cwd = Path(name)
        if p_cwd.exists():
            return p_cwd
    return _ROOT_DIR / "all_assets.parquet"


def get_data_mtime():
    """Get modification timestamp of the primary dataset."""
    p = get_latest_parquet_path()
    if p.exists():
        return p.stat().st_mtime
    return 0


def get_data_size_token():
    """Deterministic dataset byte-size fingerprint identical across local machine and Streamlit Cloud git clone."""
    p = get_latest_parquet_path()
    if p.exists():
        try:
            return str(p.stat().st_size)
        except Exception:
            pass
    return "0"


def get_data_mtime_token(data_mtime=None):
    """Canonical string representation of data_mtime shared between Python cache writers and JS readers."""
    m = get_data_mtime() if data_mtime is None else data_mtime
    try:
        return f"{float(m):.6f}"
    except Exception:
        return str(m or "0")


def get_cache_builder_version():
    """Cache-busting version string derived from max mtime of map_cache_builder.js and static/map/* assets."""
    candidates = [str(_resolve_root_file("static/map_cache_builder.js"))]
    map_dir = str(_resolve_root_file("static/map"))
    if os.path.isdir(map_dir):
        try:
            for fn in os.listdir(map_dir):
                if fn.endswith((".js", ".css")):
                    candidates.append(os.path.join(map_dir, fn))
        except OSError:
            pass
    max_mt = 0.0
    for p in candidates:
        try:
            if os.path.exists(p):
                mt = os.path.getmtime(p)
                if mt > max_mt:
                    max_mt = mt
        except OSError:
            pass
    return f"{max_mt:.0f}" if max_mt > 0 else "1"


def get_static_map_payload_meta(data_mtime=None, th_date=None):
    """Returns deterministic 128-bit static payload metadata keyed by dataset byte size so pre-built .gz works on Cloud."""
    mtime_token = get_data_mtime_token(data_mtime)
    day_str = str(th_date or _today_th_str())
    size_token = get_data_size_token()
    token_hex = hmac.new(
        _SERVER_PAYLOAD_SECRET,
        f"map|sz={size_token}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:32]
    filename = f"map_payload_{token_hex}.gz"
    sidecar_filename = f"map_meta_{token_hex}.json.gz"
    full_path = str(_STATIC_DIR / filename)
    sidecar_path = str(_STATIC_DIR / sidecar_filename)
    return {
        "filename": filename,
        "path": full_path,
        "sidecar_filename": sidecar_filename,
        "sidecar_path": sidecar_path,
        "url": f"/app/static/{filename}",
        "token": token_hex,
        "mtime": mtime_token,
        "th_date": day_str,
        "size_token": size_token,
    }


def _cleanup_stale_map_payload_files(keep_filename=None, keep_sidecar=None):
    """Deletes legacy predictable map_payload_cache.js and any outdated tokenized map_payload_*.gz / map_meta_*.gz files."""
    try:
        if os.path.exists(_LEGACY_STATIC_MAP_PAYLOAD_PATH):
            os.remove(_LEGACY_STATIC_MAP_PAYLOAD_PATH)
    except Exception:
        pass
    try:
        if _STATIC_DIR.exists():
            for p in _STATIC_DIR.iterdir():
                name = p.name
                if name in (keep_filename, keep_sidecar):
                    continue
                if (name.startswith(("map_payload_", "map_meta_")) and (name.endswith(".gz") or name.endswith(".js") or ".tmp." in name)):
                    try:
                        p.unlink()
                    except Exception:
                        pass
    except Exception:
        pass


def ensure_static_map_payload_gz(data_mtime, lookup_obj, csv_utf8_bytes, th_date=None, legend_content="", map_data_full_len=0, sam_project_options=None):
    """Writes a single-pass GZIP JSON bundle and lightweight metadata sidecar under /app/static/."""
    if not csv_utf8_bytes:
        return None
    meta = get_static_map_payload_meta(data_mtime=data_mtime, th_date=th_date)
    target = meta["path"]
    sidecar_target = meta["sidecar_path"]

    with _STATIC_PAYLOAD_LOCK:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        if not (os.path.exists(target) and os.path.getsize(target) > 0):
            tmp_path = f"{target}.tmp.{os.getpid()}.{threading.get_ident()}"
            try:
                csv_str = csv_utf8_bytes.decode("utf-8") if isinstance(csv_utf8_bytes, (bytes, bytearray)) else str(csv_utf8_bytes)
                payload_bytes = json.dumps(
                    {
                        "mtime": meta["mtime"],
                        "th_date": meta["th_date"],
                        "lut": lookup_obj or {},
                        "csv": csv_str,
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
                with gzip.open(tmp_path, "wb", compresslevel=6) as gz_out:
                    gz_out.write(payload_bytes)
                os.replace(tmp_path, target)
            except Exception:
                try:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
                except Exception:
                    pass
                return None

        if legend_content or map_data_full_len > 0 or sam_project_options is not None:
            tmp_sc = f"{sidecar_target}.tmp.{os.getpid()}.{threading.get_ident()}"
            try:
                sc_bytes = json.dumps(
                    {
                        "size_token": meta["size_token"],
                        "legend_content": legend_content,
                        "map_data_full_len": int(map_data_full_len),
                        "sam_project_options": list(sam_project_options) if sam_project_options is not None else None,
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
                with gzip.open(tmp_sc, "wb", compresslevel=6) as gz_sc:
                    gz_sc.write(sc_bytes)
                os.replace(tmp_sc, sidecar_target)
            except Exception:
                try:
                    if os.path.exists(tmp_sc):
                        os.remove(tmp_sc)
                except Exception:
                    pass

        _cleanup_stale_map_payload_files(keep_filename=meta["filename"], keep_sidecar=meta["sidecar_filename"])
        return meta


def ensure_static_map_payload_file(data_mtime, lookup_b64, csv_base64, th_date=None):
    """Backwards-compatible wrapper that writes tokenized static .gz payload from gzip+b64 inputs."""
    if not csv_base64:
        return False
    try:
        csv_bytes = gzip.decompress(base64.b64decode(csv_base64))
        lut_obj = json.loads(gzip.decompress(base64.b64decode(lookup_b64)).decode("utf-8")) if lookup_b64 else {}
        return ensure_static_map_payload_gz(data_mtime, lut_obj, csv_bytes, th_date=th_date) is not None
    except Exception:
        return False


@st.cache_resource(max_entries=1, show_spinner="กำลังโหลดฐานข้อมูลทรัพย์สิน (all_assets.parquet)...")
def _load_properties_data_cached(data_version=0):
    """Load property dataset strictly from all_assets.parquet / all_asset.parquet.

    Raises on failure so Streamlit never memoizes `None` across a transient disk error.
    """
    parquet_file = get_latest_parquet_path()
    if not parquet_file.exists():
        raise FileNotFoundError(f"ไม่พบไฟล์ข้อมูล '{parquet_file.name}' กรุณาตรวจสอบไฟล์ในโฟลเดอร์หลัก")

    df = pd.read_parquet(parquet_file)
    df = ensure_derived_cols(df, persist_cache=False)
    df.attrs['source'] = parquet_file.name
    return df


def load_properties_data(data_version=0):
    """Load property dataset strictly from all_assets.parquet / all_asset.parquet.

    Returns df.copy(deep=False) so each session gets an independent DataFrame wrapper
    without duplicating ~460k rows in RAM.
    """
    try:
        df = _load_properties_data_cached(data_version=data_version)
    except FileNotFoundError as fnf:
        st.error(str(fnf))
        return None
    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดในการโหลดไฟล์ Parquet: {e}")
        return None

    if df is not None:
        df_copy = df.copy(deep=False)
        df_copy.attrs = getattr(df, 'attrs', {}).copy()
        return df_copy
    return None


load_properties_data.clear = _load_properties_data_cached.clear


@st.cache_resource(show_spinner=False, max_entries=4)
def _get_sam_project_options_cached(_df, cache_key=None):
    """Single cached computation returning full 5-tuple project inventory so Welcome Screen and Tab 2 share 1 entry."""
    if _df is None or _df.empty or 'ชื่อโครงการ' not in _df.columns or 'บริษัท' not in _df.columns:
        return [], {}, [], [], {}

    # Fast-path: load precomputed project options from sidecar if base dataset (no custom upload)
    is_base_dataset = (not isinstance(cache_key, tuple)) or (len(cache_key) < 3) or (cache_key[2] is None)
    if is_base_dataset:
        try:
            meta = get_static_map_payload_meta()
            if os.path.exists(meta["sidecar_path"]):
                with gzip.open(meta["sidecar_path"], "rb") as gz_sc:
                    sc_data = json.loads(gz_sc.read().decode("utf-8"))
                spo = sc_data.get("sam_project_options")
                if isinstance(spo, list) and len(spo) == 5 and spo[0]:
                    return spo[0], spo[1], spo[2], spo[3], spo[4]
        except Exception:
            pass

    from modules.services.data_cleaner import (
        is_invalid_project_name,
        normalize_project_name,
        get_brand_search_tag,
        clean_display_project_name,
    )

    has_norm_col = 'norm_project_name' in _df.columns
    if has_norm_col:
        pair_vc = _df.groupby(['ชื่อโครงการ', 'norm_project_name', 'บริษัท'], observed=True).size()
        pair_vc = pair_vc[pair_vc > 0]
    else:
        pair_vc = _df.groupby(['ชื่อโครงการ', 'บริษัท'], observed=True).size()
        pair_vc = pair_vc[pair_vc > 0]

    if pair_vc.empty:
        return [], {}, [], [], {}

    sam_counts = {}
    comp_counts = {}
    comp_companies_sets = {}
    norm_groups = {}
    raw_counts = {}
    sam_raw_counts = {}
    invalid_cache = {}
    norm_cache = {}

    if has_norm_col:
        for (raw_p, raw_nk, raw_co), cnt in pair_vc.items():
            p = str(raw_p).strip()
            if not p or p in _INVALID_STR_TOKENS:
                continue
            nk = str(raw_nk).strip()
            if len(nk) <= 2 or nk in _INVALID_STR_TOKENS:
                continue
            inv = invalid_cache.get(p)
            if inv is None:
                inv = is_invalid_project_name(p)
                invalid_cache[p] = inv
            if inv:
                continue
            cnt_i = int(cnt)
            raw_counts[p] = raw_counts.get(p, 0) + cnt_i
            ng = norm_groups.get(nk)
            if ng is None:
                norm_groups[nk] = [p]
            elif p not in ng:
                ng.append(p)
            co_s = str(raw_co).strip()
            if co_s.upper() == 'SAM':
                sam_counts[nk] = sam_counts.get(nk, 0) + cnt_i
                sam_raw_counts[p] = sam_raw_counts.get(p, 0) + cnt_i
            else:
                comp_counts[nk] = comp_counts.get(nk, 0) + cnt_i
                cs = comp_companies_sets.get(nk)
                if cs is None:
                    comp_companies_sets[nk] = {co_s}
                else:
                    cs.add(co_s)
    else:
        for (raw_p, raw_co), cnt in pair_vc.items():
            p = str(raw_p).strip()
            if not p or p in _INVALID_STR_TOKENS:
                continue
            inv = invalid_cache.get(p)
            if inv is None:
                inv = is_invalid_project_name(p)
                invalid_cache[p] = inv
            if inv:
                continue
            nk = norm_cache.get(p)
            if nk is None:
                nk = normalize_project_name(p)
                norm_cache[p] = nk
            if len(nk) <= 2:
                continue
            cnt_i = int(cnt)
            raw_counts[p] = raw_counts.get(p, 0) + cnt_i
            ng = norm_groups.get(nk)
            if ng is None:
                norm_groups[nk] = [p]
            elif p not in ng:
                ng.append(p)
            co_s = str(raw_co).strip()
            if co_s.upper() == 'SAM':
                sam_counts[nk] = sam_counts.get(nk, 0) + cnt_i
                sam_raw_counts[p] = sam_raw_counts.get(p, 0) + cnt_i
            else:
                comp_counts[nk] = comp_counts.get(nk, 0) + cnt_i
                cs = comp_companies_sets.get(nk)
                if cs is None:
                    comp_companies_sets[nk] = {co_s}
                else:
                    cs.add(co_s)

    if not norm_groups:
        return [], {}, [], [], {}

    # Merge canonical display collisions instead of dropping later groups
    canonical_agg = {}  # can_p -> {"sam": int, "comp": int, "comp_cos": set}
    for k, raws in norm_groups.items():
        if not k or len(k) <= 2:
            continue
        sam_candidates = [r for r in raws if r in sam_raw_counts]
        if sam_candidates:
            sam_candidates.sort(key=lambda r: sam_raw_counts[r], reverse=True)
            best_raw = sam_candidates[0]
        else:
            candidates = sorted(raws, key=lambda r: raw_counts.get(r, 0), reverse=True)
            best_raw = candidates[0]

        can_p = clean_display_project_name(best_raw)
        if not can_p:
            continue

        s_cnt = int(sam_counts.get(k, 0))
        o_cnt = int(comp_counts.get(k, 0))
        c_set = comp_companies_sets.get(k, set())

        if can_p in canonical_agg:
            canonical_agg[can_p]["sam"] += s_cnt
            canonical_agg[can_p]["comp"] += o_cnt
            canonical_agg[can_p]["comp_cos"].update(c_set)
        else:
            canonical_agg[can_p] = {
                "sam": s_cnt,
                "comp": o_cnt,
                "comp_cos": set(c_set),
            }

    sam_projs = [p for p, agg in canonical_agg.items() if agg["sam"] > 0]
    other_projs = [p for p, agg in canonical_agg.items() if agg["sam"] == 0]

    sam_projs.sort(
        key=lambda p: (
            1 if canonical_agg[p]["comp"] > 0 else 0,
            canonical_agg[p]["comp"],
            canonical_agg[p]["sam"],
        ),
        reverse=True,
    )
    other_projs.sort(key=lambda p: canonical_agg[p]["comp"], reverse=True)

    sorted_projs = sam_projs + other_projs
    labels = {}
    proj_stats = {}
    for p in sorted_projs:
        agg = canonical_agg[p]
        s = agg["sam"]
        o = agg["comp"]
        cj = len(agg["comp_cos"])
        tag = get_brand_search_tag(p)
        tag_suffix = f"  [{tag}]" if tag else ""
        if s > 0:
            if o > 0:
                labels[p] = f"{p}  ➔  SAM: {s}  |  คู่แข่ง: {cj} เจ้า ({o} ทรัพย์){tag_suffix}"
            else:
                labels[p] = f"{p}  ➔  SAM: {s}  |  ไม่มีคู่แข่ง{tag_suffix}"
        else:
            labels[p] = f"{p}  ➔  {o} ทรัพย์ ({cj} เจ้า){tag_suffix}"
        proj_stats[p] = [s, o]

    return sorted_projs, labels, sam_projs, other_projs, proj_stats


def get_sam_project_options(_df, cache_key=None, return_meta=False):
    """Returns project options and labels, reusing a single shared cache entry regardless of return_meta."""
    sorted_projs, labels, sam_projs, other_projs, proj_stats = _get_sam_project_options_cached(
        _df, cache_key=cache_key
    )
    if return_meta:
        return sorted_projs, labels, sam_projs, other_projs, proj_stats
    return sorted_projs, labels


@st.cache_resource(show_spinner=False, max_entries=2)
def get_base_map_html(mtime=None):
    """Load and cache the base HTML template for Deck.gl interactive map, inlining CSS/JS for Cloud (/~/+/) compatibility."""
    try:
        from modules.config.theme import get_inlined_fa_local_css

        tmpl_path = _resolve_root_file("static/map_template.html")
        with open(tmpl_path, "r", encoding="utf-8") as f:
            html_str = f.read()

        def _read_static_text(rel_p):
            p = _resolve_root_file(rel_p)
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8") as fp:
                    return fp.read()
            return ""

        fa_css = get_inlined_fa_local_css()
        if fa_css:
            html_str = html_str.replace(
                '<link rel="stylesheet" href="/app/static/fa-local.css">',
                f"<style>\n{fa_css}\n</style>",
            )

        map_css = _read_static_text("static/map/map_styles.css")
        if map_css:
            html_str = html_str.replace(
                '<link rel="stylesheet" href="/app/static/map/map_styles.css?v=CACHE_BUILDER_VER_PLACEHOLDER">',
                f"<style>\n{map_css}\n</style>",
            )

        script_replacements = [
            ('<script src="/app/static/d3.js"></script>', "static/d3.js"),
            ('<script src="/app/static/map_cache_builder.js?v=CACHE_BUILDER_VER_PLACEHOLDER"></script>', "static/map_cache_builder.js"),
            ('<script src="/app/static/deck.gl.js"></script>', "static/deck.gl.js"),
            ('<script src="/app/static/map/map_popups_and_basemap.js?v=CACHE_BUILDER_VER_PLACEHOLDER"></script>', "static/map/map_popups_and_basemap.js"),
            ('<script src="/app/static/map/map_search_and_saved.js?v=CACHE_BUILDER_VER_PLACEHOLDER"></script>', "static/map/map_search_and_saved.js"),
            ('<script src="/app/static/map/map_layers_and_filters.js?v=CACHE_BUILDER_VER_PLACEHOLDER"></script>', "static/map/map_layers_and_filters.js"),
            ('<script src="/app/static/map/map_sync_and_init.js?v=CACHE_BUILDER_VER_PLACEHOLDER"></script>', "static/map/map_sync_and_init.js"),
        ]
        for tag_str, rel_js in script_replacements:
            js_code = _read_static_text(rel_js)
            if js_code:
                html_str = html_str.replace(tag_str, f"<script>\n{js_code}\n</script>")

        return html_str
    except Exception:
        return ""


def _sanitize_map_links(map_data):
    """Extracts and allowlists safe navigation links (http/https or local LED bridge paths)."""
    n = len(map_data)
    if 'ลิงก์' not in map_data.columns:
        return [''] * n

    _lnk = _safe_str_series(map_data['ลิงก์'], '')
    # Normalize relative app/static/led_ -> /app/static/led_
    rel_m = _lnk.str.startswith('app/static/led_')
    if rel_m.any():
        _lnk = _lnk.where(~rel_m, '/' + _lnk)

    if 'บริษัท' in map_data.columns:
        is_legal = _safe_str_series(map_data['บริษัท'], '').str.upper().isin(['LED LEGAL', 'LED_LEGAL', 'LED_SOLD'])
        if is_legal.any():
            _lnk = _lnk.where(~is_legal, _lnk.str.replace('led_bridge.html', 'led_legal_bridge.html', regex=False))

    safe_mask = _lnk.str.match(r'^(?:https?://|/app/static/led(?:_legal)?_bridge\.html\?)', case=False, na=False)
    return _lnk.where(safe_mask, '').tolist()


def _build_map_payload_raw_from_df(
    df,
    df_project_source=None,
    data_mtime=0,
    progress_bar=None,
    custom_companies=None,
    custom_company=None,
    custom_color=None,
):
    """Builds raw UTF-8 CSV bytes, lookup dict, and legend HTML safely across Pandas 3 Categoricals and missing cols."""
    if df is None or df.empty:
        return b"", {}, "", 0
    if 'ละติจูด' not in df.columns or 'ลองจิจูด' not in df.columns:
        return b"", {}, "", 0

    lat_num = pd.to_numeric(df['ละติจูด'], errors='coerce')
    lon_num = pd.to_numeric(df['ลองจิจูด'], errors='coerce')
    valid_coord_mask = (
        lat_num.notna()
        & lon_num.notna()
        & np.isfinite(lat_num)
        & np.isfinite(lon_num)
        & lat_num.between(5.0, 21.0)
        & lon_num.between(97.0, 106.0)
    )
    if not valid_coord_mask.any():
        return b"", {}, "", 0

    map_data = df.loc[valid_coord_mask]
    lat_vals = lat_num.loc[valid_coord_mask].to_numpy(dtype='float64')
    lon_vals = lon_num.loc[valid_coord_mask].to_numpy(dtype='float64')

    if progress_bar is not None:
        progress_bar.progress(40, text="กำลังจัดเตรียมและคำนวณราคาต่อหน่วย (40%)...")

    map_data_full_len = len(map_data)
    _prices_num = (
        pd.to_numeric(map_data['ราคา'], errors='coerce')
        if 'ราคา' in map_data.columns
        else pd.Series(np.nan, index=map_data.index, dtype='float64')
    )

    _p_wah = pd.to_numeric(map_data['ราคาต่อตารางวา'], errors='coerce') if 'ราคาต่อตารางวา' in map_data.columns else pd.Series(np.nan, index=map_data.index)
    _p_sqm = pd.to_numeric(map_data['ราคาต่อตารางเมตร'], errors='coerce') if 'ราคาต่อตารางเมตร' in map_data.columns else pd.Series(np.nan, index=map_data.index)
    _sqw_calc = pd.to_numeric(map_data['พื้นที่_ตารางวา'], errors='coerce') if 'พื้นที่_ตารางวา' in map_data.columns else pd.Series(np.nan, index=map_data.index)
    _sqm_calc = pd.to_numeric(map_data['พื้นที่ใช้สอย (ตร.ม.)'], errors='coerce') if 'พื้นที่ใช้สอย (ตร.ม.)' in map_data.columns else pd.Series(np.nan, index=map_data.index)
    _p_wah_calc = np.where((_p_wah > 0), _p_wah, np.where((_sqw_calc > 0) & (_prices_num > 0), _prices_num / _sqw_calc, np.nan))
    _p_sqm_calc = np.where((_p_sqm > 0), _p_sqm, np.where((_sqm_calc > 0) & (_prices_num > 0), _prices_num / _sqm_calc, np.nan))
    _ptype_str = _safe_str_series(map_data['ประเภททรัพย์'], '-') if 'ประเภททรัพย์' in map_data.columns else pd.Series('-', index=map_data.index)
    _is_condo = _ptype_str.str.contains('ห้องชุด|คอนโด|อาคารชุด', na=False)
    _unit_prices = np.where(
        _is_condo,
        np.where(pd.notna(_p_sqm_calc) & (_p_sqm_calc > 0), _p_sqm_calc, np.where(pd.notna(_p_wah_calc) & (_p_wah_calc > 0), _p_wah_calc, 0.0)),
        np.where(pd.notna(_p_wah_calc) & (_p_wah_calc > 0), _p_wah_calc, np.where(pd.notna(_p_sqm_calc) & (_p_sqm_calc > 0), _p_sqm_calc, 0.0))
    )

    title_col = 'ชื่อประกาศ' if 'ชื่อประกาศ' in map_data.columns else ('ชื่อโครงการ' if 'ชื่อโครงการ' in map_data.columns else ('รหัสทรัพย์' if 'รหัสทรัพย์' in map_data.columns else None))
    titles = _safe_str_series(map_data[title_col], 'ไม่มีชื่อ').str[:80].tolist() if title_col else ['ไม่มีชื่อ'] * map_data_full_len
    ids = _safe_str_series(map_data['รหัสทรัพย์'], '-').tolist() if 'รหัสทรัพย์' in map_data.columns else ['-'] * map_data_full_len

    if 'is_centroid' in map_data.columns:
        centroid_mask = _safe_bool_mask(map_data['is_centroid'])
    else:
        centroid_mask = pd.Series(False, index=map_data.index, dtype=bool)
    centroid_flags = centroid_mask.astype('uint8').tolist()

    co_clean_s = _safe_str_series(map_data['บริษัท'], '-') if 'บริษัท' in map_data.columns else pd.Series('-', index=map_data.index)
    centroid_per_company = co_clean_s.loc[centroid_mask].value_counts().to_dict()

    COMPANY_MAP_RGB = _default_company_map_rgb()
    imported_cos = custom_companies
    custom_co_val = custom_company
    custom_color_val = custom_color
    if imported_cos is None:
        try:
            if hasattr(st, "session_state"):
                imported_cos = st.session_state.get("imported_custom_companies", {})
                if custom_co_val is None:
                    custom_co_val = st.session_state.get("imported_custom_company")
                if custom_color_val is None:
                    custom_color_val = st.session_state.get("imported_custom_color", "#6366f1")
        except Exception:
            imported_cos = {}

    if isinstance(imported_cos, dict):
        for co_n, co_inf in imported_cos.items():
            if isinstance(co_inf, dict) and "color" in co_inf:
                COMPANY_MAP_RGB[co_n] = _hex_to_rgb_list(co_inf["color"])

    custom_rgb = _hex_to_rgb_list(custom_color_val or "#6366f1")
    COMPANY_MAP_RGB["ไฟล์นำเข้า"] = custom_rgb
    if (
        custom_co_val
        and custom_co_val != "ไฟล์นำเข้า"
        and custom_co_val != "(ตามข้อมูลในไฟล์)"
        and (not isinstance(imported_cos, dict) or custom_co_val not in imported_cos)
    ):
        COMPANY_MAP_RGB[custom_co_val] = custom_rgb
    DEFAULT_COLOR = [148, 163, 184]

    co_counts = co_clean_s.value_counts()
    legend_items_html = ['<div style="font-weight: 600; font-size: 11px; text-transform: uppercase; color: #64748b; margin-bottom: 4px; letter-spacing: 0.5px;">บริษัททรัพย์สิน</div>']
    for co_name, co_rgb in COMPANY_MAP_RGB.items():
        c_cnt = int(co_counts.get(co_name, 0))
        if c_cnt > 0:
            hex_c = f"rgb({int(co_rgb[0])},{int(co_rgb[1])},{int(co_rgb[2])})"
            c_centroid = int(centroid_per_company.get(co_name, 0))
            centroid_tag = f' <span class="legend-centroid-badge" style="background:#fef3c7; color:#92400e; font-size:9.5px; font-weight:800; padding:0px 4px; border-radius:4px; border:1px solid #fde68a;">&#9651; {c_centroid:,}</span>' if c_centroid > 0 else ''
            legend_items_html.append(f'<div class="legend-item"><span class="legend-color" style="background:{hex_c};"></span>{html.escape(str(co_name), quote=True)} ({c_cnt:,}){centroid_tag}</div>')
    other_co_cnt = sum(int(cnt) for co, cnt in co_counts.items() if co not in COMPANY_MAP_RGB)
    if other_co_cnt > 0:
        other_co_names = [co for co in co_counts.index if co not in COMPANY_MAP_RGB]
        other_co_centroid = sum(int(centroid_per_company.get(co, 0)) for co in other_co_names)
        other_centroid_tag = f' <span class="legend-centroid-badge" style="background:#fef3c7; color:#92400e; font-size:9.5px; font-weight:800; padding:0px 4px; border-radius:4px; border:1px solid #fde68a;">&#9651; {other_co_centroid:,}</span>' if other_co_centroid > 0 else ''
        legend_items_html.append(f'<div class="legend-item"><span class="legend-color" style="background:#94a3b8;"></span>อื่นๆ ({other_co_cnt:,}){other_centroid_tag}</div>')
    total_centroid_count = sum(int(v) for v in centroid_per_company.values())
    if total_centroid_count > 0:
        legend_items_html.append(f'<div class="legend-centroid-summary" style="border-top:1px dashed #e2e8f0; margin-top:5px; padding-top:5px; font-size:10.5px; color:#92400e; font-weight:700;">&#9651; พิกัดกึ่งกลาง {total_centroid_count:,} จาก {map_data_full_len:,} จุด</div>')
    legend_content = "\n".join(legend_items_html)

    links = _sanitize_map_links(map_data)

    if progress_bar is not None:
        progress_bar.progress(80, text="กำลังบีบอัด GZIP ข้อมูลพิกัด (80%)...")

    _co_cat = pd.Categorical(co_clean_s)
    _ty_series = _ptype_str.replace({'': '-'})
    _ty_counts = _ty_series.value_counts()
    _ordered_types = [t for t in _ty_counts.index if t and t != '-'] + ['-']
    _ty_cat = pd.Categorical(_ty_series, categories=_ordered_types)
    _pv_cat = pd.Categorical(_safe_str_series(map_data['จังหวัด'], '-') if 'จังหวัด' in map_data.columns else pd.Series('-', index=map_data.index))
    _st_cat = pd.Categorical(_safe_str_series(map_data['ประเภทการขาย'], 'ไม่ระบุ') if 'ประเภทการขาย' in map_data.columns else pd.Series('ไม่ระบุ', index=map_data.index))
    _rg_cat = pd.Categorical(_safe_str_series(map_data['ภาค'], 'ไม่ระบุ') if 'ภาค' in map_data.columns else pd.Series('ไม่ระบุ', index=map_data.index))
    _dt_cat = pd.Categorical(_safe_str_series(map_data['อำเภอ'], 'ไม่ระบุ') if 'อำเภอ' in map_data.columns else pd.Series('ไม่ระบุ', index=map_data.index))
    _subdt_cat = pd.Categorical(_safe_str_series(map_data['ตำบล'], 'ไม่ระบุ') if 'ตำบล' in map_data.columns else pd.Series('ไม่ระบุ', index=map_data.index))
    if 'โครงการ' in map_data.columns:
        _prj_col = _safe_str_series(map_data['โครงการ'], '-')
    elif 'ชื่อโครงการ' in map_data.columns:
        _prj_col = _safe_str_series(map_data['ชื่อโครงการ'], '-')
    else:
        _prj_col = pd.Series('-', index=map_data.index)
    _prj_cat = pd.Categorical(_prj_col)

    _plain_col = _safe_str_series(map_data['โจทก์'], '').replace({'-': ''}) if 'โจทก์' in map_data.columns else pd.Series('', index=map_data.index)
    _plain_cat = pd.Categorical(_plain_col)

    proj_src = df_project_source if df_project_source is not None else df
    if proj_src is not None and not proj_src.empty:
        # Include custom_companies fingerprint so custom uploads never hit base project cache
        custom_proj_sig = tuple(sorted(imported_cos.keys())) if isinstance(imported_cos, dict) and imported_cos else None
        sam_projs_list, _, sam_only, other_only, proj_stats = get_sam_project_options(
            proj_src, cache_key=(data_mtime, len(proj_src), custom_proj_sig), return_meta=True
        )
    else:
        sam_projs_list, sam_only, other_only, proj_stats = [], [], [], {}

    lookup_obj = {
        'co': _co_cat.categories.tolist(),
        'co_rgb': [COMPANY_MAP_RGB.get(c, DEFAULT_COLOR) for c in _co_cat.categories.tolist()],
        'ty': _ty_cat.categories.tolist(),
        'pv': _pv_cat.categories.tolist(),
        'st': _st_cat.categories.tolist(),
        'rg': _rg_cat.categories.tolist(),
        'dt': _dt_cat.categories.tolist(),
        'subdt': _subdt_cat.categories.tolist(),
        'prj': _prj_cat.categories.tolist(),
        'plaintiff': _plain_cat.categories.tolist(),
        'sam_prj': sam_only,
        'other_prj': other_only,
        'all_prj': sam_projs_list,
        'prj_stats': proj_stats,
    }

    deeds = _safe_str_series(map_data['เลขโฉนด'], '').to_numpy() if 'เลขโฉนด' in map_data.columns else [''] * map_data_full_len

    # Floor numeric extraction
    if 'ชั้น' in map_data.columns:
        fl_raw = map_data['ชั้น']
        fl_num = pd.to_numeric(fl_raw, errors='coerce')
        fl_str = fl_raw.astype(object).fillna('').astype(str)
        needs_extract = fl_num.isna() & fl_str.str.contains(r'\d', na=False)
        extracted = pd.to_numeric(fl_str[needs_extract].str.extract(r'(\d+(?:\.\d+)?)', expand=False), errors='coerce')
        fl_final = np.where(fl_num.notna() & np.isfinite(fl_num) & (fl_num >= 0) & (fl_num <= 200), fl_num, -1.0).astype('float32')
        if needs_extract.any():
            fl_final[needs_extract.to_numpy()] = np.where(
                extracted.notna() & np.isfinite(extracted) & (extracted >= 0) & (extracted <= 200),
                extracted,
                -1.0,
            )
        fl_final = np.nan_to_num(fl_final, nan=-1.0, posinf=-1.0, neginf=-1.0).round(1).astype('float32')
    else:
        fl_final = np.full(map_data_full_len, -1.0, dtype='float32')

    # Bedrooms
    if 'ห้องนอน' in map_data.columns:
        bed_raw = map_data['ห้องนอน']
        bed_num = pd.to_numeric(bed_raw, errors='coerce')
        is_studio = bed_raw.astype(object).fillna('').astype(str).str.contains('สตูดิโอ|studio', case=False, na=False)
        bed_arr = np.where(is_studio, 0.0, np.where(bed_num.notna() & np.isfinite(bed_num) & (bed_num >= 0), bed_num, -1.0))
        bed_final = np.clip(np.nan_to_num(bed_arr, nan=-1.0, posinf=-1.0, neginf=-1.0).round(0), -1, 1000).astype('int32')
    else:
        bed_final = np.full(map_data_full_len, -1, dtype='int32')

    # Bathrooms
    if 'ห้องน้ำ' in map_data.columns:
        bath_num = pd.to_numeric(map_data['ห้องน้ำ'], errors='coerce')
        bath_arr = np.where(bath_num.notna() & np.isfinite(bath_num) & (bath_num >= 0), bath_num, -1.0)
        bath_final = np.clip(np.nan_to_num(bath_arr, nan=-1.0, posinf=-1.0, neginf=-1.0).round(0), -1, 1000).astype('int32')
    else:
        bath_final = np.full(map_data_full_len, -1, dtype='int32')

    # Parking
    if 'ที่จอดรถ' in map_data.columns:
        pkg_num = pd.to_numeric(map_data['ที่จอดรถ'], errors='coerce')
        pkg_arr = np.where(pkg_num.notna() & np.isfinite(pkg_num) & (pkg_num >= 0), pkg_num, -1.0)
        pkg_final = np.clip(np.nan_to_num(pkg_arr, nan=-1.0, posinf=-1.0, neginf=-1.0).round(0), -1, 1000).astype('int32')
    else:
        pkg_final = np.full(map_data_full_len, -1, dtype='int32')

    # Listing age in days
    if 'วันประกาศ' in map_data.columns:
        u_ann = map_data['วันประกาศ'].dropna().unique()
        age_map = {u: parse_listing_age_days(u) for u in u_ann}
        age_s = map_data['วันประกาศ'].map(age_map).fillna(-1.0).copy()

        if 'วันที่ขาย' in map_data.columns and 'บริษัท' in map_data.columns:
            legal_mask = (
                co_clean_s.str.upper().isin(['LED LEGAL', 'LED_LEGAL', 'LED_SOLD'])
                & map_data['วันประกาศ'].notna()
                & map_data['วันที่ขาย'].notna()
            )
            if legal_mask.any():
                sub_legal = map_data.loc[legal_mask, ['วันประกาศ', 'วันที่ขาย']].drop_duplicates()
                legal_age_map = {}
                for ann_v, sold_v in sub_legal.itertuples(index=False, name=None):
                    try:
                        s_dt = parse_sold_date_value(sold_v)
                        if pd.notna(s_dt):
                            diff = parse_listing_age_days(ann_v, ref_date=s_dt.date())
                            if diff >= 0:
                                legal_age_map[(ann_v, sold_v)] = float(diff)
                    except Exception:
                        pass
                if legal_age_map:
                    legal_vals = [
                        legal_age_map.get((a, b))
                        for a, b in zip(map_data.loc[legal_mask, 'วันประกาศ'], map_data.loc[legal_mask, 'วันที่ขาย'])
                    ]
                    valid_legal = [v is not None for v in legal_vals]
                    if any(valid_legal):
                        target_l_idx = map_data.loc[legal_mask].index[valid_legal]
                        age_s.loc[target_l_idx] = [v for v in legal_vals if v is not None]

        age_final = np.clip(
            np.nan_to_num(age_s.to_numpy(dtype='float64'), nan=-1.0, posinf=-1.0, neginf=-1.0).round(0),
            -1,
            100_000,
        ).astype('int32')
    else:
        age_final = np.full(map_data_full_len, -1, dtype='int32')

    # Sold price & Sold date (for LED Legal)
    if 'ราคาขายได้' in map_data.columns:
        sold_p_raw = pd.to_numeric(map_data['ราคาขายได้'], errors='coerce').fillna(0.0).to_numpy(dtype='float64')
        sold_p_num = np.clip(np.nan_to_num(sold_p_raw, nan=0.0, posinf=0.0, neginf=0.0).round(0), 0, 10**15).astype('int64')
    else:
        sold_p_num = np.zeros(map_data_full_len, dtype='int64')

    sold_date_list = _safe_str_series(map_data['วันที่ขาย'], '').tolist() if 'วันที่ขาย' in map_data.columns else [''] * map_data_full_len

    _p_int64 = np.clip(np.nan_to_num(_prices_num.fillna(0.0).to_numpy(dtype='float64'), nan=0.0, posinf=0.0, neginf=0.0).round(0), 0, 10**15).astype('int64')
    _up_int64 = np.clip(np.nan_to_num(_unit_prices, nan=0.0, posinf=0.0, neginf=0.0).round(0), 0, 10**15).astype('int64')
    _puw_int64 = np.clip(np.nan_to_num(_p_wah_calc, nan=0.0, posinf=0.0, neginf=0.0).round(0), 0, 10**15).astype('int64')
    _pum_int64 = np.clip(np.nan_to_num(_p_sqm_calc, nan=0.0, posinf=0.0, neginf=0.0).round(0), 0, 10**15).astype('int64')
    _sqw_f32 = np.clip(np.nan_to_num(_sqw_calc.to_numpy(dtype='float64'), nan=0.0, posinf=0.0, neginf=0.0), 0.0, 1e9).round(1).astype('float32')
    _sqm_f32 = np.clip(np.nan_to_num(_sqm_calc.to_numpy(dtype='float64'), nan=0.0, posinf=0.0, neginf=0.0), 0.0, 1e9).round(1).astype('float32')

    csv_df = pd.DataFrame({
        'lon': np.round(lon_vals, 6),
        'lat': np.round(lat_vals, 6),
        '_title': titles,
        '_id': ids,
        '_ci': _co_cat.codes.astype('int16'),
        '_ti': _ty_cat.codes.astype('int16'),
        '_pi': _pv_cat.codes.astype('int16'),
        '_sti': _st_cat.codes.astype('int16'),
        '_rgi': _rg_cat.codes.astype('int16'),
        '_dti': _dt_cat.codes.astype('int16'),
        '_subdti': _subdt_cat.codes.astype('int16'),
        '_prji': _prj_cat.codes.astype('int32'),
        '_p': _p_int64,
        '_up': _up_int64,
        '_sqw': _sqw_f32,
        '_sqm': _sqm_f32,
        '_puw': _puw_int64,
        '_pum': _pum_int64,
        '_fl': fl_final,
        '_bed': bed_final,
        '_bath': bath_final,
        '_pkg': pkg_final,
        '_age': age_final,
        '_link': links,
        '_centroid': centroid_flags,
        '_deed': deeds,
        '_pti': _plain_cat.codes.astype('int32' if (len(_plain_cat.codes) > 0 and _plain_cat.codes.max() > 32767) else 'int16'),
        '_sold_p': sold_p_num,
        '_sold_date': sold_date_list,
    })

    csv_utf8_bytes = csv_df.to_csv(index=False).encode('utf-8')
    del csv_df
    gc.collect()
    return csv_utf8_bytes, lookup_obj, legend_content, map_data_full_len


def build_map_payload_from_df(
    df,
    df_project_source=None,
    data_mtime=0,
    progress_bar=None,
    custom_companies=None,
    custom_company=None,
    custom_color=None,
):
    """Builds GZIP+Base64 CSV payload, categorical lookup_b64, and legend HTML from a properties DataFrame."""
    csv_utf8_bytes, lookup_obj, legend_content, map_data_full_len = _build_map_payload_raw_from_df(
        df,
        df_project_source=df_project_source,
        data_mtime=data_mtime,
        progress_bar=progress_bar,
        custom_companies=custom_companies,
        custom_company=custom_company,
        custom_color=custom_color,
    )
    if map_data_full_len == 0:
        return "", "", "", 0

    lookup_b64 = base64.b64encode(
        gzip.compress(json.dumps(lookup_obj, ensure_ascii=False, separators=(",", ":")).encode('utf-8'), compresslevel=1)
    ).decode('utf-8')
    csv_base64 = base64.b64encode(gzip.compress(csv_utf8_bytes, compresslevel=1)).decode('utf-8')
    del csv_utf8_bytes, lookup_obj
    gc.collect()
    return csv_base64, lookup_b64, legend_content, map_data_full_len


@st.cache_resource(show_spinner=False, max_entries=1)
def _ensure_static_map_bundle_cached(data_mtime, th_date):
    """Loads pre-built static .gz map bundle & sidecar metadata from disk in <20ms (0 GB RAM spike), or builds once if missing."""
    meta = get_static_map_payload_meta(data_mtime=data_mtime, th_date=th_date)
    if (
        os.path.exists(meta["path"])
        and os.path.getsize(meta["path"]) > 0
        and os.path.exists(meta["sidecar_path"])
        and os.path.getsize(meta["sidecar_path"]) > 0
    ):
        try:
            with gzip.open(meta["sidecar_path"], "rb") as gz_sc:
                sc_data = json.loads(gz_sc.read().decode("utf-8"))
            leg = str(sc_data.get("legend_content") or "")
            cnt = int(sc_data.get("map_data_full_len") or 0)
            if leg and cnt > 0:
                return leg, cnt, meta, "", ""
        except Exception:
            pass

    df = load_properties_data(data_mtime)
    csv_utf8_bytes, lookup_obj, legend_content, map_data_full_len = _build_map_payload_raw_from_df(
        df,
        df_project_source=df,
        data_mtime=data_mtime,
        custom_companies={},
        custom_company="",
        custom_color="#6366f1",
    )
    if map_data_full_len == 0:
        return "", 0, None, "", ""

    spo = get_sam_project_options(df, cache_key=(data_mtime, len(df), None), return_meta=True)
    static_meta = ensure_static_map_payload_gz(
        data_mtime,
        lookup_obj,
        csv_utf8_bytes,
        th_date=th_date,
        legend_content=legend_content,
        map_data_full_len=map_data_full_len,
        sam_project_options=spo,
    )
    if static_meta is not None:
        csv_inject = ""
        lut_inject = ""
    else:
        csv_inject = base64.b64encode(gzip.compress(csv_utf8_bytes, compresslevel=1)).decode('utf-8')
        lut_inject = base64.b64encode(
            gzip.compress(json.dumps(lookup_obj, ensure_ascii=False, separators=(",", ":")).encode('utf-8'), compresslevel=1)
        ).decode('utf-8')

    del csv_utf8_bytes, lookup_obj
    gc.collect()
    return legend_content, map_data_full_len, static_meta, csv_inject, lut_inject


def get_precomputed_map_payload(data_mtime):
    """Returns GZIP+Base64 map payload on demand without keeping 80 MB raw bytes in @st.cache_data."""
    day_str = _today_th_str()
    legend_content, map_data_full_len, static_meta, csv_inject, lut_inject = _ensure_static_map_bundle_cached(data_mtime, day_str)
    if map_data_full_len == 0:
        return "", "", "", 0
    if csv_inject and lut_inject:
        return csv_inject, lut_inject, legend_content, map_data_full_len
    if static_meta and os.path.exists(static_meta["path"]):
        try:
            with gzip.open(static_meta["path"], "rb") as gz_in:
                bundle = json.loads(gz_in.read().decode("utf-8"))
            csv_b64 = base64.b64encode(gzip.compress(bundle.get("csv", "").encode("utf-8"), compresslevel=1)).decode("utf-8")
            lut_b64 = base64.b64encode(
                gzip.compress(json.dumps(bundle.get("lut", {}), ensure_ascii=False, separators=(",", ":")).encode("utf-8"), compresslevel=1)
            ).decode("utf-8")
            del bundle
            gc.collect()
            return csv_b64, lut_b64, legend_content, map_data_full_len
        except Exception:
            pass
    df = load_properties_data(data_mtime)
    return build_map_payload_from_df(df, df_project_source=df, data_mtime=data_mtime)


@st.cache_resource(show_spinner=False, max_entries=1)
def _build_full_map_html_v2(data_mtime, tmpl_mtime, cache_builder_ver="1", th_date=None):
    """Builds the slimmed nationwide map HTML once per (data, template, builder, day).

    Offloads the heavy nationwide payload to a 128-bit tokenized binary GZIP file under /app/static/
    (`map_payload_<token>.gz`) whose URL is only emitted into authenticated HTML, avoiding predictable
    unauthenticated data dumps while slashing LAN and Cloud RAM footprint.
    """
    day_str = str(th_date or _today_th_str())
    legend_content, map_data_full_len, static_meta, csv_inject, lut_inject = _ensure_static_map_bundle_cached(data_mtime, day_str)
    if map_data_full_len == 0:
        return None, 0, None

    payload_url_inject = static_meta["url"] if static_meta is not None else ""

    base_tmpl = get_base_map_html(tmpl_mtime)
    if not base_tmpl:
        return None, 0, static_meta

    # Never read per-user session_state custom companies into the shared nationwide base HTML
    atlas_uri, icon_mapping = get_map_icon_atlas_and_mapping(128, include_session_custom=False)
    icon_mapping_json = _safe_json_inline(icon_mapping)

    company_logos_dict = get_leaflet_logo_dict(72, include_session_custom=False)
    company_logos_json = _safe_json_inline(company_logos_dict)

    df = load_properties_data(data_mtime)
    all_provinces_list = sorted(list({
        str(p).strip().strip(" ,;.-'\"")
        for p in df['จังหวัด'].dropna().unique()
        if str(p).strip().strip(" ,;.-'\"")
        and str(p).strip().strip(" ,;.-'\"") not in ('-', 'ไม่มีข้อมูล', 'nan', 'None')
        and not re.search(r'\d', str(p))
        and re.search(r'^[ก-๙]', str(p).strip())
    })) if df is not None and not df.empty and 'จังหวัด' in df.columns else []
    all_provinces_json = _safe_json_inline(all_provinces_list)

    html_out = _replace_placeholders_single_pass(
        base_tmpl,
        {
            "CSV_BASE64_PLACEHOLDER": csv_inject,
            "LOOKUP_BASE64_PLACEHOLDER": lut_inject,
            "MAP_PAYLOAD_URL_PLACEHOLDER": payload_url_inject,
            "DATA_MTIME_PLACEHOLDER": f"{get_data_mtime_token(data_mtime)}|{day_str}",
            "CACHE_BUILDER_VER_PLACEHOLDER": str(cache_builder_ver),
            "LEGEND_ITEMS_PLACEHOLDER": legend_content,
            "ATLAS_BASE64_PLACEHOLDER": atlas_uri,
            "ICON_MAPPING_PLACEHOLDER": icon_mapping_json,
            "COMPANY_LOGOS_PLACEHOLDER": company_logos_json,
            "ALL_PROVINCES_PLACEHOLDER": all_provinces_json,
            "CUSTOM_COMPANY_COLORS_PLACEHOLDER": '"ไฟล์นำเข้า": "#6366f1"',
        },
    )
    return html_out, map_data_full_len, static_meta


def precompute_full_map_html(data_mtime):
    """Pre-assembles the map HTML with all heavy data offloaded to a tokenized static .gz file."""
    _tmpl_path = str(_resolve_root_file("static/map_template.html"))
    _tmpl_mtime = os.path.getmtime(_tmpl_path) if os.path.exists(_tmpl_path) else None
    _builder_ver = get_cache_builder_version()
    _day_str = _today_th_str()
    _payload_meta = get_static_map_payload_meta(data_mtime=data_mtime, th_date=_day_str)

    # Self-heal if tokenized static payload or sidecar file is missing even though resource/session cache exists
    if not os.path.exists(_payload_meta["path"]) or not os.path.exists(_payload_meta["sidecar_path"]):
        _ensure_static_map_bundle_cached.clear()
        _build_full_map_html_v2.clear()

    if (
        "cached_map_html_base" in st.session_state
        and st.session_state.get("cached_map_tmpl_mtime") == _tmpl_mtime
        and st.session_state.get("cached_map_data_mtime") == data_mtime
        and st.session_state.get("cached_map_builder_ver") == _builder_ver
        and st.session_state.get("cached_map_th_date") == _day_str
        and st.session_state.get("cached_map_payload_url") == _payload_meta["url"]
    ):
        return _payload_meta

    html_out, map_data_full_len, static_meta = _build_full_map_html_v2(
        data_mtime, _tmpl_mtime, _builder_ver, _day_str
    )
    if not html_out:
        return static_meta

    # Session only stores a reference to the shared string (no extra memory per user)
    st.session_state["cached_map_html_base"] = html_out
    st.session_state["cached_map_data_len"] = map_data_full_len
    st.session_state["cached_map_tmpl_mtime"] = _tmpl_mtime
    st.session_state["cached_map_data_mtime"] = data_mtime
    st.session_state["cached_map_builder_ver"] = _builder_ver
    st.session_state["cached_map_th_date"] = _day_str
    st.session_state["cached_map_payload_url"] = (static_meta or {}).get("url", "")
    return static_meta
