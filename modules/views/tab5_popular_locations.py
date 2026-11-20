import gzip
import hashlib
import hmac
import html
import json
import os
import re
import statistics
import threading
import streamlit as st
import streamlit.components.v1 as stc

from modules.config.constants import REGION_PROVINCES, PROVINCE_TO_REGION
from modules.services.data_cleaner import get_dataset_month_year
from modules.services.data_loader import (
    _SERVER_PAYLOAD_SECRET,
    _safe_json_inline,
    _today_th_str,
    get_data_mtime,
    get_data_mtime_token,
)
from modules.services.livinginsider_service import get_livinginsider_project_metrics

fragment_decorator = getattr(st, "fragment", lambda f: f)

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_STATIC_DIR = os.path.join(_BASE_DIR, "static")
_TAB5_TEMPLATE_PATH = os.path.join(_STATIC_DIR, "tab5_popular_locations.html")
_TAB5_PAYLOAD_LOCK = threading.Lock()
_TAB5_OFFLOAD_MIN_PROJECTS = 200
_SLIM_PROJECT_KEYS = (
    "name", "units", "prov", "dist", "subdist", "prop_type",
    "lat", "lon", "price", "p_sqm", "p_sqw",
    "vd", "cd", "sum_vd", "sum_cd", "days", "start_dt", "end_dt", "link",
)


@st.cache_resource(show_spinner=False, max_entries=2)
def _load_tab5_html_template(template_mtime: float) -> str:
    """Reads and caches static/tab5_popular_locations.html, inlining Leaflet & FontAwesome for Cloud (/~/+/) compatibility."""
    _ = template_mtime
    from modules.config.theme import get_fa_solid_data_uri

    with open(_TAB5_TEMPLATE_PATH, "r", encoding="utf-8") as f:
        html_str = f.read()

    html_str = html_str.replace("/app/static/fa-solid-900.ttf", get_fa_solid_data_uri())

    def _read_static(rel_p):
        p = os.path.join(_STATIC_DIR, rel_p)
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as fp:
                return fp.read()
        return ""

    leaflet_css = _read_static(os.path.join("vendor", "leaflet", "leaflet.css"))
    if leaflet_css:
        html_str = html_str.replace(
            '<link rel="stylesheet" href="/app/static/vendor/leaflet/leaflet.css" />',
            f"<style>\n{leaflet_css}\n</style>",
        )

    leaflet_js = _read_static(os.path.join("vendor", "leaflet", "leaflet.js"))
    if leaflet_js:
        html_str = html_str.replace(
            '<script src="/app/static/vendor/leaflet/leaflet.js"></script>',
            f"<script>\n{leaflet_js}\n</script>",
        )

    heat_js = _read_static("leaflet-heat.js")
    if heat_js:
        html_str = html_str.replace(
            '<script src="/app/static/leaflet-heat.js"></script>',
            f"<script>\n{heat_js}\n</script>",
        )

    return html_str


def _render_tab5_template(replacements: dict[str, str]) -> str:
    """Single-pass placeholder renderer immune to chained token expansion."""
    tmpl_mtime = os.path.getmtime(_TAB5_TEMPLATE_PATH) if os.path.exists(_TAB5_TEMPLATE_PATH) else 0.0
    tmpl = _load_tab5_html_template(tmpl_mtime)
    pattern = re.compile("|".join(re.escape(k) for k in replacements))
    return pattern.sub(lambda m: replacements[m.group(0)], tmpl)


def _strip_unused_project_fields(projects):
    """Drops unused min_p/max_p keys before JSON serialization to cut payload size."""
    return [{k: p[k] for k in _SLIM_PROJECT_KEYS if k in p} for p in projects]


def get_static_tab5_payload_meta(data_mtime=None, th_date=None):
    """Returns deterministic 128-bit tokenized static payload metadata for Tab 5 Livinginsider projects."""
    from modules.services.data_loader import get_data_size_token
    mtime_token = get_data_mtime_token(data_mtime)
    day_str = str(th_date or _today_th_str())
    size_token = get_data_size_token()
    token_hex = hmac.new(
        _SERVER_PAYLOAD_SECRET,
        f"tab5|sz={size_token}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:32]
    filename = f"tab5_payload_{token_hex}.gz"
    return {
        "filename": filename,
        "path": os.path.join(_STATIC_DIR, filename),
        "url": f"/app/static/{filename}",
        "token": token_hex,
        "mtime": mtime_token,
        "th_date": day_str,
    }


def _cleanup_stale_tab5_payloads(keep_filename=None):
    try:
        if os.path.isdir(_STATIC_DIR):
            for name in os.listdir(_STATIC_DIR):
                if name == keep_filename:
                    continue
                if name.startswith("tab5_payload_") and (name.endswith(".gz") or ".tmp." in name):
                    try:
                        os.remove(os.path.join(_STATIC_DIR, name))
                    except OSError:
                        pass
    except Exception:
        pass


def ensure_static_tab5_payload_gz(projects_slim, data_mtime=None, th_date=None):
    """Atomically writes gzipped JSON project array to a 128-bit tokenized static path under /app/static/."""
    if not projects_slim:
        return None
    meta = get_static_tab5_payload_meta(data_mtime=data_mtime, th_date=th_date)
    target = meta["path"]

    with _TAB5_PAYLOAD_LOCK:
        try:
            if os.path.exists(target) and os.path.getsize(target) > 0:
                _cleanup_stale_tab5_payloads(keep_filename=meta["filename"])
                return meta
        except OSError:
            pass

        os.makedirs(_STATIC_DIR, exist_ok=True)
        tmp_path = f"{target}.tmp.{os.getpid()}.{threading.get_ident()}"
        try:
            raw_bytes = json.dumps(projects_slim, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            with gzip.open(tmp_path, "wb", compresslevel=6) as gz_out:
                gz_out.write(raw_bytes)
            os.replace(tmp_path, target)
            _cleanup_stale_tab5_payloads(keep_filename=meta["filename"])
            return meta
        except Exception:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except OSError:
                pass
            return None


def _build_tab5_popular_locations_uncached(df_raw, is_dark_mode=False, has_custom_imports=False, data_mtime=None, th_date=None, metrics_cache_key=None):
    # 1. Fetch Aggregated Metrics
    projects = get_livinginsider_project_metrics(df_raw, cache_key=metrics_cache_key)
    if not projects:
        return None

    projects_slim = _strip_unused_project_fields(projects)

    # 2. SSR KPI Summary Cards (match default client-side filter `units >= 2`, falling back to all if none >= 2)
    ssr_projects = [p for p in projects_slim if (p.get("units") or 0) >= 2] or projects_slim
    total_projects = len(ssr_projects)
    total_units = sum(p.get("units", 1) for p in ssr_projects)
    vds = [p.get("vd", 0) for p in ssr_projects if p.get("vd") is not None]
    cds = [p.get("cd", 0) for p in ssr_projects if p.get("cd") is not None]
    med_vd = statistics.median(vds) if vds else 0
    med_cd = statistics.median(cds) if cds else 0

    # Dataset month info for attribution banner
    cur_mtime = get_data_mtime() if data_mtime is None else data_mtime
    day_str = str(th_date or _today_th_str())
    month_th, _ = get_dataset_month_year(df_raw, data_mtime=cur_mtime)
    th_abbr = {
        'มกราคม': 'ม.ค.', 'กุมภาพันธ์': 'ก.พ.', 'มีนาคม': 'มี.ค.', 'เมษายน': 'เม.ย.',
        'พฤษภาคม': 'พ.ค.', 'มิถุนายน': 'มิ.ย.', 'กรกฎาคม': 'ก.ค.', 'สิงหาคม': 'ส.ค.',
        'กันยายน': 'ก.ย.', 'ตุลาคม': 'ต.ค.', 'พฤศจิกายน': 'พ.ย.', 'ธันวาคม': 'ธ.ค.',
    }
    month_short = str(month_th) if month_th else "ล่าสุด"
    for full_m, abbr_m in th_abbr.items():
        if full_m in month_short:
            month_short = month_short.replace(full_m, abbr_m)
            break

    # 3. Extract unique provinces, regions, and property types for select options
    provinces = sorted(list(set(p["prov"] for p in projects_slim if p.get("prov") and p["prov"] not in ('-', 'nan', 'None'))))
    priority_provs = ["กรุงเทพมหานคร", "นนทบุรี", "สมุทรปราการ", "ปทุมธานี", "ชลบุรี", "เชียงใหม่", "ภูเก็ต", "ระยอง"]
    sorted_provs = [p for p in priority_provs if p in provinces] + [p for p in provinces if p not in priority_provs]

    region_names = list(REGION_PROVINCES.keys())
    if any(p not in PROVINCE_TO_REGION for p in sorted_provs):
        region_names.append("อื่นๆ / ไม่ระบุ")

    prop_types = sorted(list(set(p["prop_type"] for p in projects_slim if p.get("prop_type") and p["prop_type"] not in ('-', 'nan', 'None'))))

    # 4. Tokenized static offload for production dataset (cuts 11.6 MB inline HTML down to ~45 KB!)
    tab5_payload_url = ""
    if not has_custom_imports and len(projects_slim) >= _TAB5_OFFLOAD_MIN_PROJECTS:
        meta = ensure_static_tab5_payload_gz(projects_slim, data_mtime=cur_mtime, th_date=day_str)
        if meta is not None:
            tab5_payload_url = meta["url"]

    projects_inline_json = "[]" if tab5_payload_url else _safe_json_inline(projects_slim)
    provinces_json = _safe_json_inline(sorted_provs)
    regions_json = _safe_json_inline(region_names)
    prov_to_region_json = _safe_json_inline(PROVINCE_TO_REGION)
    prop_types_json = _safe_json_inline(prop_types)
    payload_url_json = _safe_json_inline(tab5_payload_url)
    geo_url_json = _safe_json_inline("/app/static/provinces_outer_geojson.json")
    theme_class = "" if is_dark_mode else "light-theme"

    html_app = _render_tab5_template({
        "THEME_CLASS_PLACEHOLDER": theme_class,
        "TOTAL_PROJECTS_PLACEHOLDER": f"{total_projects:,.0f}",
        "TOTAL_UNITS_PLACEHOLDER": f"{total_units:,.0f}",
        "MED_VD_PLACEHOLDER": f"{med_vd:,.1f}",
        "MED_CD_PLACEHOLDER": f"{med_cd:,.2f}",
        "PROJECTS_JSON_PLACEHOLDER": projects_inline_json,
        "PAYLOAD_URL_JSON_PLACEHOLDER": payload_url_json,
        "GEO_URL_JSON_PLACEHOLDER": geo_url_json,
        "PROVINCES_JSON_PLACEHOLDER": provinces_json,
        "REGIONS_JSON_PLACEHOLDER": regions_json,
        "PROV_TO_REGION_JSON_PLACEHOLDER": prov_to_region_json,
        "PROP_TYPES_JSON_PLACEHOLDER": prop_types_json,
        "IS_DARK_PLACEHOLDER": "true" if is_dark_mode else "false",
    })

    return {
        "total_projects": total_projects,
        "total_units": total_units,
        "med_vd": med_vd,
        "med_cd": med_cd,
        "month_short": month_short,
        "html_app": html_app,
        "payload_url": tab5_payload_url,
    }


@st.cache_data(show_spinner=False, max_entries=6)
def _build_tab5_popular_locations_bundle(_df_raw, is_dark_mode=False, cache_key=None):
    return _build_tab5_popular_locations_uncached(
        _df_raw,
        is_dark_mode=is_dark_mode,
        has_custom_imports=bool(isinstance(cache_key, tuple) and len(cache_key) >= 4 and cache_key[3] is not None),
        metrics_cache_key=cache_key,
    )


def precompute_tab5_popular_locations(df_raw, is_dark_mode=False, data_mtime=0):
    """Pre-warms Tab 5 Livinginsider metrics, tokenized .gz payload, and 70/30 map HTML bundle."""
    if df_raw is None or df_raw.empty:
        return
    cur_mtime = data_mtime or get_data_mtime()
    th_date = _today_th_str()
    cache_key = (cur_mtime, len(df_raw), bool(is_dark_mode), None, th_date)
    _build_tab5_popular_locations_bundle(df_raw, is_dark_mode=is_dark_mode, cache_key=cache_key)


@fragment_decorator
def render_tab5_popular_locations_view(df_raw, is_dark_mode=False):
    """Renders Tab 5: Popular Locations (ทำเลยอดนิยม) with tokenized payload offload and local-first Leaflet."""
    with st.container(key="tab_popular_locations"):
        st.markdown("""
        <style>
        .st-key-tab_popular_locations {
            margin-top: -12px !important;
        }
        .st-key-tab_popular_locations div[data-testid="stHorizontalBlock"] {
            margin-bottom: 8px !important;
        }
        .popular-source-banner {
            background: rgba(30, 41, 59, 0.45);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 9px;
            padding: 7px 14px;
            font-size: 0.8rem;
            color: #94a3b8;
            margin-bottom: 8px;
            display: flex;
            align-items: center;
            gap: 4px;
        }
        .popular-source-banner strong {
            color: #f1f5f9;
            font-weight: 600;
        }
        .popular-source-banner.light {
            background: #f8fafc;
            border: 1px solid rgba(0, 0, 0, 0.07);
            color: #64748b;
        }
        .popular-source-banner.light strong {
            color: #0f172a;
        }
        </style>
        """, unsafe_allow_html=True)

        has_custom = bool(
            st.session_state.get("imported_custom_df") is not None
            and not st.session_state["imported_custom_df"].empty
        )
        custom_fp = st.session_state.get("_custom_import_fp") if has_custom else None
        th_date = _today_th_str()
        cur_mtime = get_data_mtime()

        if has_custom and not custom_fp:
            bundle = _build_tab5_popular_locations_uncached(
                df_raw,
                is_dark_mode=is_dark_mode,
                has_custom_imports=True,
                data_mtime=cur_mtime,
                th_date=th_date,
            )
        else:
            # Self-heal if cached bundle references a tokenized .gz file that was deleted on disk
            cache_key = (
                cur_mtime,
                len(df_raw) if df_raw is not None else 0,
                bool(is_dark_mode),
                custom_fp,
                th_date,
            )
            bundle = _build_tab5_popular_locations_bundle(df_raw, is_dark_mode=is_dark_mode, cache_key=cache_key)
            if bundle and bundle.get("payload_url"):
                expected_meta = get_static_tab5_payload_meta(data_mtime=cur_mtime, th_date=th_date)
                if not os.path.exists(expected_meta["path"]):
                    _build_tab5_popular_locations_bundle.clear()
                    bundle = _build_tab5_popular_locations_bundle(df_raw, is_dark_mode=is_dark_mode, cache_key=cache_key)

        if not bundle:
            st.info("ไม่พบข้อมูลสถิติของ Livinginsider ในชุดข้อมูลปัจจุบัน")
            return

        month_short = html.escape(str(bundle["month_short"]), quote=True)
        html_app = bundle["html_app"]
        theme_cls = "light" if not is_dark_mode else ""

        st.markdown(f"""
        <div class="popular-source-banner {theme_cls}">
            <i class="fa-solid fa-satellite-dish" style="color: #38bdf8; margin-right: 6px;"></i>
            <span><strong>แหล่งข้อมูล:</strong> สถิติการเข้าชมและยอดคลิกอ้างอิงจาก <strong>Livinginsider</strong> (อัปเดตล่าสุด: {month_short})</span>
        </div>
        """, unsafe_allow_html=True)

        try:
            reset_nonce = int(st.session_state.get("_nova_reset_nonce", 0))
            rendered_html = f"{html_app}\n<!-- reset-nonce:{reset_nonce} -->" if reset_nonce > 0 else html_app
            stc.html(rendered_html, height=960, scrolling=False)
        except Exception:
            st.error("ไม่สามารถแสดงแผนที่ทำเลยอดนิยมได้ กรุณาลองรีเฟรชหน้าเว็บ")
