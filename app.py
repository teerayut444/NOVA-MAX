import hashlib
import os
import sys
from PIL import Image
import pandas as pd
import streamlit as st

# Ensure project root is in sys.path
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if _BASE_DIR not in sys.path:
    sys.path.insert(0, _BASE_DIR)

# Core configuration & theme
from modules.config.theme import inject_global_theme_css

# Services
from modules.services.data_cleaner import ensure_derived_cols
from modules.services.data_loader import load_properties_data, get_data_mtime, get_latest_parquet_path

# UI Components
from modules.ui.welcome_screen import render_welcome_screen
from modules.ui.sidebar import render_sidebar
from modules.ui.kpi_header import render_floating_kpi_cards

# Views
from modules.views.tab1_bubble import render_tab1_bubble_view
from modules.views.tab2_map import render_tab2_map_view
from modules.views.tab3_analytics import render_tab3_analytics_view
from modules.views.tab4_inventory import render_tab4_inventory_view
from modules.views.tab5_popular_locations import render_tab5_popular_locations_view


@st.cache_resource(show_spinner=False)
def _load_app_page_icon():
    """Loads and detaches the favicon once per process so file descriptors never leak across reruns."""
    for rel in (os.path.join("logo", "app_icon.ico"), os.path.join("assets", "app_icon.ico")):
        cand = os.path.join(_BASE_DIR, rel)
        if os.path.exists(cand):
            try:
                with Image.open(cand) as im:
                    return im.copy()
            except Exception:
                pass
    return ":material/analytics:"


def _compute_custom_import_fingerprint(imp_df):
    """Deterministic content fingerprint for session-scoped uploaded data to prevent cross-user cache collisions."""
    if imp_df is None or imp_df.empty:
        return None
    h = hashlib.blake2b(digest_size=12)
    h.update(f"n={len(imp_df)}|cols={len(imp_df.columns)}|".encode("utf-8"))
    for c in imp_df.columns:
        h.update(str(c).encode("utf-8", errors="ignore"))
        h.update(b",")
    n = len(imp_df)
    sample_idx = sorted({0, min(1, n - 1), n // 2, max(0, n - 2), n - 1})
    key_cols = [c for c in ("บริษัท", "รหัสทรัพย์", "ชื่อโครงการ", "ราคา", "จังหวัด") if c in imp_df.columns] or list(imp_df.columns[:5])
    for row in imp_df.iloc[sample_idx][key_cols].itertuples(index=False, name=None):
        h.update(repr(row).encode("utf-8", errors="ignore"))
    if "ราคา" in imp_df.columns:
        try:
            p_sum = float(pd.to_numeric(imp_df["ราคา"], errors="coerce").sum(skipna=True))
            h.update(f"|psum={p_sum:.2f}".encode("utf-8"))
        except Exception:
            pass
    # Include custom company color/symbol metadata
    cos_meta = st.session_state.get("imported_custom_companies")
    if isinstance(cos_meta, dict) and cos_meta:
        for k, v in sorted(cos_meta.items()):
            if isinstance(v, dict):
                h.update(f"|{k}:{v.get('symbol','')}:{v.get('color','')}".encode("utf-8", errors="ignore"))
    return h.hexdigest()


# ----------------- PAGE CONFIGURATION -----------------
st.set_page_config(
    page_title="NOVA NPA Dashboard",
    page_icon=_load_app_page_icon(),
    layout="wide",
    initial_sidebar_state="expanded"
)

# ----------------- PORTAL GATEWAY ENTRY CHECK -----------------
if "portal_entered" not in st.session_state:
    if st.query_params.get("portal") == "skip" and st.session_state.get("authenticated", False):
        st.session_state["portal_entered"] = True

if not st.session_state.get("authenticated", False) or not st.session_state.get("portal_entered", False):
    render_welcome_screen()
    st.stop()

# ----------------- DATA LOADING & CACHING -----------------
data_mtime = get_data_mtime()
df_raw = load_properties_data(data_mtime)
if df_raw is not None:
    df_raw = df_raw.copy(deep=False)

# Merge user uploaded data if available (protect shared cache & compute collision-free fingerprint)
if "imported_custom_df" in st.session_state and st.session_state["imported_custom_df"] is not None and not st.session_state["imported_custom_df"].empty:
    imp_df = st.session_state["imported_custom_df"]
    if 'บริษัท' not in imp_df.columns or '_is_derived_clean' not in imp_df.columns:
        imp_df = imp_df.copy()
        if 'บริษัท' not in imp_df.columns:
            custom_co = st.session_state.get("imported_custom_company", "ไฟล์นำเข้า")
            imp_df['บริษัท'] = custom_co
        imp_df = ensure_derived_cols(imp_df, persist_cache=False)
        st.session_state["imported_custom_df"] = imp_df

    import_ver = int(st.session_state.get("_custom_import_ver", 0))
    merge_cache_key = (id(imp_df), len(imp_df), data_mtime, import_ver)
    if st.session_state.get("_merged_df_cache_key") != merge_cache_key or not st.session_state.get("_custom_import_fp"):
        st.session_state["_custom_import_fp"] = _compute_custom_import_fingerprint(imp_df)

    if df_raw is not None and not df_raw.empty:
        if st.session_state.get("_merged_df_cache_key") == merge_cache_key and "_merged_df_cache" in st.session_state:
            df_raw = st.session_state["_merged_df_cache"]
        else:
            orig_attrs = getattr(df_raw, 'attrs', {}).copy()
            df_raw = df_raw.copy()
            imp_df_copy = imp_df.copy()
            all_cat_cols = set(
                [c for c in df_raw.columns if isinstance(df_raw[c].dtype, pd.CategoricalDtype)]
                + [c for c in imp_df_copy.columns if isinstance(imp_df_copy[c].dtype, pd.CategoricalDtype)]
            )
            for c in all_cat_cols:
                if c in df_raw.columns and isinstance(df_raw[c].dtype, pd.CategoricalDtype):
                    df_raw[c] = df_raw[c].astype(object)
                if c in imp_df_copy.columns and isinstance(imp_df_copy[c].dtype, pd.CategoricalDtype):
                    imp_df_copy[c] = imp_df_copy[c].astype(object)
            df_raw = pd.concat([df_raw, imp_df_copy], ignore_index=True)
            for c in ('บริษัท', 'ประเภททรัพย์', 'จังหวัด', 'อำเภอ', 'ตำบล', 'ภาค', 'ประเภทการขาย'):
                if c in df_raw.columns:
                    df_raw[c] = df_raw[c].astype('category')
            df_raw.attrs.update(orig_attrs)
            st.session_state["_merged_df_cache_key"] = merge_cache_key
            st.session_state["_merged_df_cache"] = df_raw
    else:
        df_raw = imp_df.copy()
else:
    st.session_state.pop("_custom_import_fp", None)

if df_raw is None or df_raw.empty:
    _expected_parquet = get_latest_parquet_path().name
    st.markdown(f"""
    <div style="background-color: rgba(239, 68, 68, 0.08); border: 1px solid rgba(239, 68, 68, 0.2); border-radius: 12px; padding: 40px; text-align: center; margin-top: 50px; max-width: 800px; margin-left: auto; margin-right: auto; box-shadow: 0 10px 30px rgba(0,0,0,0.04);">
        <i class="fa-solid fa-triangle-exclamation" style="font-size: 4rem; color: #ef4444; margin-bottom: 20px;"></i>
        <h2 style="color: #ef4444; margin-bottom: 15px; font-weight: 700;">ไม่พบไฟล์ข้อมูล '{_expected_parquet}'</h2>
        <p style="color: #475569; font-size: 1rem;">กรุณารันคำสั่ง <code>python convert_csv_to_parquet.py</code> เพื่อแปลงไฟล์และเริ่มต้นใช้งานแดชบอร์ด</p>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

# ----------------- SIDEBAR & THEME SETUP -----------------
is_dark_mode = render_sidebar(df_raw)
inject_global_theme_css(is_dark_mode)

# ----------------- GLOBAL FLOATING KPI CARDS -----------------
render_floating_kpi_cards(df_raw, df_raw, is_dark_mode)

# ----------------- MAIN NAVIGATION TABS (Keep All Tabs Mounted Client-Side — Eager) -----------------
_tab_labels = [
    "ภาพรวม (Bubble Chart)",
    "แผนที่ (Interactive Map)",
    "สถิติ & วิเคราะห์",
    "รายการทรัพย์สิน",
    "ทำเลยอดนิยม",
]
_reset_nonce = int(st.session_state.get("_nova_reset_nonce", 0))
_default_tab = (
    _tab_labels[1]
    if (st.query_params.get("map_ref_id") or st.query_params.get("map_price_ref_id"))
    else _tab_labels[0]
)
with st.container(key="main_tabs_container"):
    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        _tab_labels,
        default=_default_tab,
        key=f"main_tabs_{_reset_nonce}",
    )

has_custom_imports = bool(
    "imported_custom_df" in st.session_state
    and st.session_state["imported_custom_df"] is not None
    and not st.session_state["imported_custom_df"].empty
)

# Tab 1: 3D Bubble Chart
with tab1:
    render_tab1_bubble_view(df_raw, is_dark_mode=is_dark_mode, has_active_filters=has_custom_imports)

# Tab 2: Interactive Deck.gl Map + Median Reference Analytics Fragment
with tab2:
    render_tab2_map_view(df_raw, df_raw, is_dark_mode=is_dark_mode)

# Tab 3: Competitor & Market Analytics
with tab3:
    render_tab3_analytics_view(df_raw, df_raw, is_dark_mode=is_dark_mode)

# Tab 4: Property Listing / Inventory Table
with tab4:
    render_tab4_inventory_view(df_raw, is_dark_mode=is_dark_mode)

# Tab 5: Popular Locations Map & Leaderboard (Livinginsider)
with tab5:
    render_tab5_popular_locations_view(df_raw, is_dark_mode=is_dark_mode)
