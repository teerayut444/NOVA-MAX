import streamlit as st
import streamlit.components.v1 as stc
from bubble_chart import generate_3d_glossy_bubble_chart_html
from modules.services.data_loader import get_data_mtime


@st.cache_data(show_spinner=False, max_entries=6)
def get_cached_bubble_chart_html(_df, cache_key=None, is_dark_mode=False):
    """Shared process-wide cache for base 3D bubble chart HTML (eliminates per-session duplication)."""
    return generate_3d_glossy_bubble_chart_html(_df, is_dark_mode=bool(is_dark_mode))


def render_tab1_bubble_view(df_filtered, is_dark_mode=False, has_active_filters=False):
    """Renders Tab 1: 3D Glossy Bubble Chart View."""
    with st.container(key="tab_bubble"):
        st.markdown("""
        <style>
        .st-key-tab_bubble {
            margin-top: -14px !important;
        }
        .st-key-tab_bubble div[data-testid="stHorizontalBlock"] {
            margin-bottom: -18px !important;
        }
        .st-key-tab_bubble iframe {
            margin-top: -8px !important;
        }
        </style>
        """, unsafe_allow_html=True)

        row_cnt = len(df_filtered) if df_filtered is not None else 0
        if not has_active_filters:
            cache_key = (get_data_mtime(), row_cnt, bool(is_dark_mode))
            bubble_html = get_cached_bubble_chart_html(
                df_filtered,
                cache_key=cache_key,
                is_dark_mode=is_dark_mode,
            )
        else:
            # Never pollute process-wide cache with per-user filtered or custom-imported charts
            bubble_html = generate_3d_glossy_bubble_chart_html(
                df_filtered,
                is_dark_mode=is_dark_mode,
            )

        try:
            stc.html(bubble_html, height=860)
        except Exception:
            st.error("ไม่สามารถแสดงกราฟ 3D Bubble Chart ได้ กรุณาลองรีเฟรชหน้าเว็บ")
