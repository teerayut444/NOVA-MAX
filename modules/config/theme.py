import base64
import os
import streamlit as st

_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@st.cache_resource(show_spinner=False)
def get_fa_solid_data_uri() -> str:
    """Returns a base64 data URI for static/fa-solid-900.ttf so FontAwesome works under both Cloud (/~/+/) and subpaths."""
    ttf_path = os.path.join(_ROOT_DIR, "static", "fa-solid-900.ttf")
    if os.path.exists(ttf_path):
        try:
            with open(ttf_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("ascii")
            return f"data:font/ttf;base64,{b64}"
        except Exception:
            pass
    return "/app/static/fa-solid-900.ttf"


@st.cache_resource(show_spinner=False)
def get_inlined_fa_local_css() -> str:
    """Returns static/fa-local.css with fa-solid-900.ttf embedded as a data URI (zero external /app/static/ requests)."""
    fa_css_path = os.path.join(_ROOT_DIR, "static", "fa-local.css")
    if not os.path.exists(fa_css_path):
        return ""
    try:
        with open(fa_css_path, "r", encoding="utf-8") as f:
            css = f.read()
        data_uri = get_fa_solid_data_uri()
        css = css.replace(
            "url('./fa-solid-900.ttf') format('truetype'), url('/app/static/fa-solid-900.ttf') format('truetype')",
            f"url('{data_uri}') format('truetype')",
        )
        return css.replace("/app/static/fa-solid-900.ttf", data_uri)
    except Exception:
        return ""

def get_root_css_variables(is_dark_mode=False):
    """Construct root CSS custom properties based on theme toggle selection (Emerald Green Palette)."""
    if is_dark_mode:
        return """--app-color-scheme: dark;
--card-bg: #112820;
--card-border: #1e4537;
--card-text: #f0fdf4;
--card-subtext: #86efac;
--sidebar-bg: #03251c;
--sidebar-border: #064032;
--tag-bg: #14352a;
--tag-border: #1e4d3c;
--tag-text: #a7f3d0;
--pill-bg: #14352a;
--pill-border: #1e4d3c;
--pill-text: #a7f3d0;
--input-bg: #112820;
--input-border: #1e4d3c;
--input-text: #f0fdf4;
--hover-bg: #194032;
--tab-bg: #091a14;
--page-bg: #091a14;
--tab-inactive-text: #6ee7b7;
--tab-hover-text: #ffffff;
--tab-active-text: #34d399;
--tab-active-border: #10b981;
--tab-container-border: #1e4537;
--nav-item-hover-bg: rgba(16, 185, 129, 0.08);
--primary-accent: #10b981;
--primary-accent-hover: #059669;
--kpi-gradient: linear-gradient(135deg, #a7f3d0 0%, #34d399 100%);
--kpi-border: rgba(52, 211, 153, 0.25);
--kpi-hover-border: #10b981;
--kpi-hover-shadow: rgba(16, 185, 129, 0.25);
--kpi-accent-bar: #10b981;
--seg-track-bg: rgba(255, 255, 255, 0.06);
--seg-track-border: transparent;
--seg-active-bg: rgba(16, 185, 129, 0.22);
--seg-active-border: #10b981;
--seg-active-text: #34d399;
--seg-active-shadow: 0 0 16px rgba(16, 185, 129, 0.45), inset 0 0 8px rgba(16, 185, 129, 0.25);
--seg-inactive-text: #94a3b8;"""
    else:
        return """--app-color-scheme: light;
--card-bg: #ffffff;
--card-border: #e2e8f0;
--card-text: #0f172a;
--card-subtext: #475569;
--sidebar-bg: #064e3b;
--sidebar-border: #043828;
--tag-bg: #ecfdf5;
--tag-border: #a7f3d0;
--tag-text: #065f46;
--pill-bg: #ecfdf5;
--pill-border: #a7f3d0;
--pill-text: #065f46;
--input-bg: #ffffff;
--input-border: #cbd5e1;
--input-text: #0f172a;
--hover-bg: #e6f4ee;
--tab-bg: #ffffff;
--page-bg: #f8faf9;
--tab-inactive-text: #64748b;
--tab-hover-text: #047857;
--tab-active-text: #065f46;
--tab-active-border: #047857;
--tab-container-border: #e2ede7;
--nav-item-hover-bg: rgba(5, 150, 105, 0.04);
--primary-accent: #047857;
--primary-accent-hover: #065f46;
--kpi-gradient: linear-gradient(135deg, #064e3b 0%, #047857 55%, #059669 100%);
--kpi-border: rgba(4, 120, 87, 0.16);
--kpi-hover-border: #047857;
--kpi-hover-shadow: rgba(4, 120, 87, 0.14);
--kpi-accent-bar: #047857;
--seg-track-bg: #f1f5f9;
--seg-track-border: transparent;
--seg-active-bg: rgba(16, 185, 129, 0.14);
--seg-active-border: #059669;
--seg-active-text: #065f46;
--seg-active-shadow: 0 0 14px rgba(16, 185, 129, 0.38), inset 0 0 6px rgba(16, 185, 129, 0.16);
--seg-inactive-text: #64748b;"""

def style_plotly_fig(fig, is_dark_mode=False):
    """Style Plotly figure according to current theme."""
    bg = "rgba(0,0,0,0)"
    font_c = "#f8fafc" if is_dark_mode else "#0f172a"
    tmpl = "plotly_dark" if is_dark_mode else "plotly_white"
    map_st = "carto-darkmatter" if is_dark_mode else "carto-positron"
    fig.update_layout(
        template=tmpl,
        paper_bgcolor=bg,
        plot_bgcolor=bg,
        font=dict(color=font_c, family="Noto Sans Thai, Inter, sans-serif"),
        title_font=dict(color=font_c, family="Noto Sans Thai, Inter, sans-serif"),
        legend=dict(font=dict(color=font_c))
    )
    try:
        fig.update_map(style=map_st)
    except Exception:
        pass
    if hasattr(fig, 'update_annotations'):
        fig.update_annotations(font=dict(color=font_c, family="Noto Sans Thai, Inter, sans-serif"))
    return fig

@st.cache_resource(show_spinner=False)
def _read_cached_css_template(css_file: str, mtime: float) -> str:
    """Reads and caches static CSS template keyed by modification timestamp, embedding Base64 FontAwesome."""
    with open(css_file, "r", encoding="utf-8") as f:
        raw = f.read()
    return raw.replace("/app/static/fa-solid-900.ttf", get_fa_solid_data_uri())

def load_global_css_template():
    """Loads static CSS template from static/style.css with mtime-based cache invalidation."""
    css_file = os.path.join(_ROOT_DIR, "static", "style.css")
    if os.path.exists(css_file):
        try:
            return _read_cached_css_template(css_file, os.path.getmtime(css_file))
        except Exception:
            with open(css_file, "r", encoding="utf-8") as f:
                return f.read().replace("/app/static/fa-solid-900.ttf", get_fa_solid_data_uri())
    return ""

def inject_global_theme_css(is_dark_mode=False):
    """Injects Google Fonts (Inter, Noto Sans Thai, Material Symbols), inlined Base64 FontAwesome, root variables, and CSS."""
    from modules.config.constants import rewrite_static_paths

    root_vars = get_root_css_variables(is_dark_mode)
    css_template = load_global_css_template()
    fa_inlined_css = get_inlined_fa_local_css()
    head_links = (
        '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
        '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=Noto+Sans+Thai:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">\n'
        '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200" />'
    )
    font_imports = (
        "@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=Noto+Sans+Thai:wght@300;400;500;600;700;800&display=swap');\n"
        "@import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200');\n"
    )
    if css_template:
        if "<style>" in css_template:
            if "ROOT_VARS_PLACEHOLDER" in css_template:
                full_css = css_template.replace("ROOT_VARS_PLACEHOLDER", root_vars)
            else:
                full_css = css_template.replace("<style>", f"<style>\n{font_imports}{fa_inlined_css}\n:root {{ {root_vars} }}\n", 1)
            st.html(rewrite_static_paths(f"{head_links}\n{full_css}"))
        else:
            if "ROOT_VARS_PLACEHOLDER" in css_template:
                rendered_css = css_template.replace("ROOT_VARS_PLACEHOLDER", root_vars)
            else:
                rendered_css = f":root {{ {root_vars} }}\n{css_template}"
            st.html(rewrite_static_paths(f"{head_links}\n<style>\n{font_imports}{fa_inlined_css}\n{rendered_css}\n</style>"))
    else:
        st.html(rewrite_static_paths(f"{head_links}\n<style>\n{font_imports}{fa_inlined_css}\n:root {{ {root_vars} }}\n</style>"))

