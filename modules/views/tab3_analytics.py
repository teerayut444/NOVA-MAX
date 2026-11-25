import html
import json
import re
import numpy as np
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from modules.config.constants import (
    COMPANY_COLORS,
    COMP_BRAND_COLORS,
    get_gradient_palette,
    PRICE_TIER_ORDER,
)
from modules.config.theme import style_plotly_fig
from modules.services.data_loader import get_data_mtime

fragment_decorator = getattr(st, "fragment", lambda f: f)

PREFERRED_COMPANY_ORDER = [
    "LED", "LED Legal", "SAM", "BAM", "Chayo555", "Chayo", "Chayo NPA",
    "GHB", "KBANK", "KTB", "SCB", "GSB",
    "DDproperty", "Livinginsider", "NaYoo", "ZmyHome", "Baania",
]

PROPERTY_TYPE_COLORS = {
    'บ้านเดี่ยว': '#059669',
    'ห้องชุดพักอาศัย': '#2563eb',
    'คอนโด': '#2563eb',
    'ทาวน์เฮ้าส์': '#f59e0b',
    'ทาวน์โฮม': '#f59e0b',
    'ที่ดินเปล่า': '#06b6d4',
    'ที่ดินพร้อมสิ่งปลูกสร้าง': '#f97316',
    'อาคารพาณิชย์': '#8b5cf6',
    'โรงงาน/โกดัง': '#ec4899',
    'บ้านแฝด': '#14b8a6',
    'วิลล่า': '#e11d48',
    'อพาร์ทเมนท์': '#a855f7',
    'อาคารสำนักงาน': '#64748b',
    'โรงแรม/รีสอร์ท': '#eab308',
    'โฮมออฟฟิศ': '#4f46e5',
    'อื่นๆ': '#94a3b8',
}

_INLINE_BUILDING_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 384 512" '
    'style="width:14px;height:14px;fill:currentColor;vertical-align:-2px;margin-right:6px;">'
    '<path d="M48 0C21.5 0 0 21.5 0 48V464c0 26.5 21.5 48 48 48h96V432c0-26.5 21.5-48 48-48s48 '
    '21.5 48 48v80h96c26.5 0 48-21.5 48-48V48c0-26.5-21.5-48-48-48H48zM64 240c0-8.8 7.2-16 '
    '16-16h32c8.8 0 16 7.2 16 16v32c0 8.8-7.2 16-16 16H80c-8.8 0-16-7.2-16-16V240zm112-16h32c8.8 '
    '0 16 7.2 16 16v32c0 8.8-7.2 16-16 16H176c-8.8 0-16-7.2-16-16V240c0-8.8 7.2-16 16-16zm80 '
    '16c0-8.8 7.2-16 16-16h32c8.8 0 16 7.2 16 16v32c0 8.8-7.2 16-16 16H272c-8.8 0-16-7.2-16-16V240z'
    'M80 96h32c8.8 0 16 7.2 16 16v32c0 8.8-7.2 16-16 16H80c-8.8 0-16-7.2-16-16V112c0-8.8 7.2-16 '
    '16-16zm80 16c0-8.8 7.2-16 16-16h32c8.8 0 16 7.2 16 16v32c0 8.8-7.2 16-16 16H176c-8.8 0-16-7.2-16-16V112z'
    'm112-16h32c8.8 0 16 7.2 16 16v32c0 8.8-7.2 16-16 16H272c-8.8 0-16-7.2-16-16V112c0-8.8 7.2-16 16-16z"/>'
    '</svg>'
)


def _safe_json_for_script(obj):
    """Serialize JSON safely for inline <script> blocks, neutralizing </script> (any case) and line separators."""
    s = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    return (
        s.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("'", "\\u0027")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _safe_hover_label(val):
    """Escapes HTML special chars and Plotly '%' placeholders for safe hovertemplate embedding."""
    return html.escape(str(val or ""), quote=True).replace("%", "&#37;")


@st.cache_resource(show_spinner=False)
def _highcharts_inline_script_tags():
    """Reads and caches local Highcharts & Highcharts-3D scripts for inline Cloud (/~/+/) serving."""
    import os
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    tags = []
    for rel in ("static/vendor/highcharts/highcharts.js", "static/vendor/highcharts/highcharts-3d.js"):
        p = os.path.join(root_dir, rel)
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    tags.append(f"<script>\n{f.read()}\n</script>")
            except Exception:
                pass
    return "\n".join(tags)


def _highcharts_script_tags():
    """Local-First Highcharts script tags: subpath-aware URLs under NOVA_BASE_URL_PATH, inlined under root/Cloud (/~/+/)."""
    from modules.config.constants import get_base_url_prefix, get_static_url

    if not get_base_url_prefix():
        inlined = _highcharts_inline_script_tags()
        if inlined:
            return inlined
    hc_url = get_static_url("vendor/highcharts/highcharts.js")
    hc3d_url = get_static_url("vendor/highcharts/highcharts-3d.js")
    return (
        f'<script src="{hc_url}"></script>\n'
        f'        <script src="{hc3d_url}"></script>'
    )


def _vectorized_price_tier(price_series):
    p = pd.to_numeric(price_series, errors='coerce')
    conds = [
        p.isna() | (p <= 0),
        p < 1_000_000,
        p < 3_000_000,
        p < 5_000_000,
        p < 10_000_000,
        p <= 20_000_000,
    ]
    choices = [
        "ไม่ระบุราคา",
        "< 1 ล้านบาท",
        "1 - 3 ล้านบาท",
        "3 - 5 ล้านบาท",
        "5 - 10 ล้านบาท",
        "10 - 20 ล้านบาท",
    ]
    return np.select(conds, choices, default="> 20 ล้านบาท")


def _map_simplified_type_scalar(t):
    """Categorizes property types into 6 clean groups, separating ที่ดินพร้อมสิ่งปลูกสร้าง from ที่ดินเปล่า and retaining อื่นๆ."""
    t_str = str(t or '').strip()
    if not t_str or t_str in ('-', 'nan', 'None', '<NA>', 'null'):
        return 'อื่นๆ'
    if 'พร้อมสิ่งปลูกสร้าง' in t_str or ('ที่ดิน' in t_str and any(k in t_str for k in ('บ้าน', 'อาคาร', 'สิ่งปลูกสร้าง', 'โรงงาน', 'โกดัง', 'พาณิชย์'))):
        return 'ที่ดินพร้อมสิ่งปลูกสร้าง'
    if 'ที่ดิน' in t_str:
        return 'ที่ดินเปล่า'
    if any(k in t_str for k in ('คอนโด', 'ห้องชุด', 'อาคารชุด')):
        return 'ห้องชุดพักอาศัย'
    if any(k in t_str for k in ('ทาวน์โฮม', 'ทาวน์เฮ้าส์', 'ทาวน์เฮาส์')):
        return 'ทาวน์เฮ้าส์'
    if any(k in t_str for k in ('บ้านเดี่ยว', 'บ้านแฝด', 'พูลวิลล่า', 'วิลล่า', 'บ้าน')):
        return 'บ้านเดี่ยว'
    return 'อื่นๆ'


def _compute_box_stats(values_arr):
    """Computes Tukey box-plot quantiles in NumPy so Plotly receives 6 numbers instead of 100k raw rows."""
    arr = np.asarray(values_arr, dtype=float)
    arr = arr[np.isfinite(arr) & (arr > 0)]
    if arr.size == 0:
        return None
    q1, med, q3 = np.percentile(arr, [25, 50, 75])
    iqr = q3 - q1
    min_v = float(np.min(arr))
    max_v = float(np.max(arr))
    lf = max(min_v, float(q1 - 1.5 * iqr))
    uf = min(max_v, float(q3 + 1.5 * iqr))
    mean_v = float(np.mean(arr))
    return {
        "q1": round(float(q1), 4),
        "median": round(float(med), 4),
        "q3": round(float(q3), 4),
        "lowerfence": round(float(lf), 4),
        "upperfence": round(float(uf), 4),
        "mean": round(mean_v, 4),
    }


def _build_precomputed_box_trace(df_sub, categories, trace_name, color_val):
    """Builds a lightweight go.Box trace using precomputed quantiles (kilobytes instead of megabytes)."""
    xs, q1s, meds, q3s, lfs, ufs, means = [], [], [], [], [], [], []
    if df_sub is not None and not df_sub.empty:
        grouped = df_sub.groupby('ประเภททรัพย์', observed=True)['val_million']
        for cat in categories:
            if cat not in grouped.groups:
                continue
            stats = _compute_box_stats(grouped.get_group(cat).to_numpy())
            if stats is None:
                continue
            xs.append(cat)
            q1s.append(stats["q1"])
            meds.append(stats["median"])
            q3s.append(stats["q3"])
            lfs.append(stats["lowerfence"])
            ufs.append(stats["upperfence"])
            means.append(stats["mean"])
    return go.Box(
        x=xs,
        q1=q1s,
        median=meds,
        q3=q3s,
        lowerfence=lfs,
        upperfence=ufs,
        mean=means,
        name=trace_name,
        marker=dict(color=color_val, opacity=0.85),
        line=dict(color=color_val, width=1.6),
        boxpoints=False,
        boxmean=True,
    )


def _build_tab3_subtab1_uncached(df_filtered, is_dark_mode):
    plotly_template = "plotly_dark" if is_dark_mode else "plotly_white"

    def get_comp_hex_color(c_name):
        if not c_name or pd.isna(c_name):
            return '#3b82f6'
        return COMP_BRAND_COLORS.get(str(c_name).strip(), '#3b82f6')

    comp_counts = df_filtered['บริษัท'].value_counts().reset_index()
    comp_counts.columns = ['บริษัท', 'จำนวนทรัพย์สิน']
    comp_counts = comp_counts[comp_counts['จำนวนทรัพย์สิน'] > 0]
    tot_units_all = int(comp_counts['จำนวนทรัพย์สิน'].sum()) if not comp_counts.empty else 1
    comp_counts['pct_share'] = (comp_counts['จำนวนทรัพย์สิน'] / tot_units_all) * 100.0

    fig_comp = go.Figure(go.Bar(
        x=comp_counts['บริษัท'].astype(str),
        y=comp_counts['จำนวนทรัพย์สิน'],
        marker=dict(
            color=[get_comp_hex_color(c) for c in comp_counts['บริษัท']],
            cornerradius=10,
            line=dict(width=1.2, color='rgba(255, 255, 255, 0.4)')
        ),
        text=[f"<b>{int(c):,}</b><br><span style='font-size:9.5px;color:#94a3b8;'>({p:.1f}%)</span>" for c, p in zip(comp_counts['จำนวนทรัพย์สิน'], comp_counts['pct_share'])],
        textposition='outside',
        textfont=dict(size=10.5, family="Noto Sans Thai, Inter, sans-serif"),
        hovertemplate="<b>%{x}</b><br>จำนวนทรัพย์: <b>%{y:,}</b> รายการ<extra></extra>"
    ))
    fig_comp.update_layout(
        title=dict(text='จำนวนรายการทรัพย์สินเปรียบเทียบแต่ละบริษัท (Market Share)', font=dict(size=14, family="Noto Sans Thai, Inter, sans-serif")),
        yaxis=dict(title='จำนวนทรัพย์ (รายการ)', showgrid=True, gridcolor='rgba(255,255,255,0.06)' if is_dark_mode else 'rgba(0,0,0,0.05)', zeroline=False),
        xaxis=dict(showgrid=False),
        height=450,
        margin=dict(t=50, b=20, l=10, r=10),
        template=plotly_template,
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)'
    )
    fig_comp = style_plotly_fig(fig_comp, is_dark_mode=is_dark_mode)

    # 3D Pie: Keep Top 8 property types and roll ALL remaining (rank 9+) into 'อื่นๆ' so shares sum to 100% of tot_units_all
    all_type_counts = df_filtered['ประเภททรัพย์'].astype(object).fillna('อื่นๆ').astype(str).str.strip().replace({'': 'อื่นๆ', '-': 'อื่นๆ', 'nan': 'อื่นๆ', 'None': 'อื่นๆ'}).value_counts()
    all_type_counts = all_type_counts[all_type_counts > 0]
    top8 = all_type_counts.head(8)
    rest_sum = int(all_type_counts.iloc[8:].sum()) if len(all_type_counts) > 8 else 0

    pie_rows = [(str(k), int(v)) for k, v in top8.items()]
    if rest_sum > 0:
        existing_other_idx = next((i for i, (k, _) in enumerate(pie_rows) if k == 'อื่นๆ'), None)
        if existing_other_idx is not None:
            k_o, v_o = pie_rows[existing_other_idx]
            pie_rows[existing_other_idx] = (k_o, v_o + rest_sum)
        else:
            pie_rows.append(('อื่นๆ', rest_sum))

    vibrant_donut_colors = ['#10b981', '#3b82f6', '#f59e0b', '#06b6d4', '#8b5cf6', '#ec4899', '#14b8a6', '#f97316', '#64748b']
    c2_series_data = [
        {"name": html.escape(str(name), quote=True), "y": cnt, "color": '#94a3b8' if name == 'อื่นๆ' else vibrant_donut_colors[i % len(vibrant_donut_colors)]}
        for i, (name, cnt) in enumerate(pie_rows)
    ]

    text_color = "#f8fafc" if is_dark_mode else "#0f172a"
    label_color = "#cbd5e1" if is_dark_mode else "#334155"
    hc_scripts = _highcharts_script_tags()

    html_c2 = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=Noto+Sans+Thai:wght@300;400;500;600;700;800&display=swap" referrerpolicy="no-referrer">
        {hc_scripts}
        <style>
            * {{
                box-sizing: border-box;
                font-family: 'Noto Sans Thai', 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif !important;
            }}
            body {{
                background: transparent;
                margin: 0;
                padding: 4px;
                font-family: 'Noto Sans Thai', 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                color: {text_color};
                overflow: hidden;
            }}
            #chart_type_3d {{
                height: 430px;
                width: 100%;
            }}
        </style>
    </head>
    <body>
        <div id="chart_type_3d"></div>
        <script>
            if (typeof Highcharts === 'undefined') {{
                document.getElementById('chart_type_3d').innerHTML = '<div style="padding:32px;text-align:center;color:#94a3b8;font-size:13px;">ไม่สามารถโหลดไลบรารีกราฟ Highcharts ได้ กรุณาตรวจสอบไฟล์ local static</div>';
            }} else {{
                Highcharts.setOptions({{
                    chart: {{
                        style: {{
                            fontFamily: "'Noto Sans Thai', 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
                        }}
                    }}
                }});
                Highcharts.chart('chart_type_3d', {{
                    chart: {{
                        type: 'pie',
                        options3d: {{
                            enabled: true,
                            alpha: 50,
                            depth: 38
                        }},
                        backgroundColor: 'transparent',
                        margin: [45, 10, 10, 10]
                    }},
                    title: {{
                        text: 'สัดส่วนประเภททรัพย์หลัก (3D Asset Share)',
                        align: 'left',
                        style: {{ color: '{text_color}', fontSize: '14px', fontFamily: "'Noto Sans Thai', 'Inter', sans-serif", fontWeight: '700' }}
                    }},
                    subtitle: {{
                        text: 'รวมทั้งหมด: <b style="color:#047857;">{tot_units_all:,} รายการ</b>',
                        align: 'left',
                        style: {{ color: '#64748b', fontSize: '12px', fontFamily: "'Noto Sans Thai', 'Inter', sans-serif" }}
                    }},
                    tooltip: {{
                        headerFormat: '',
                        pointFormat: '<b>{{point.name}}</b>: <b>{{point.y:,.0f}} รายการ</b> ({{point.percentage:.1f}}%)',
                        style: {{ fontSize: '13px', fontFamily: "'Noto Sans Thai', 'Inter', sans-serif" }}
                    }},
                    plotOptions: {{
                        pie: {{
                            innerSize: 0,
                            depth: 38,
                            size: '72%',
                            center: ['50%', '52%'],
                            dataLabels: {{
                                enabled: true,
                                format: '{{point.name}}<br><b>{{point.percentage:.1f}}%</b>',
                                distance: 14,
                                style: {{
                                    color: '{label_color}',
                                    textOutline: 'none',
                                    fontSize: '12px',
                                    fontFamily: "'Noto Sans Thai', 'Inter', sans-serif",
                                    fontWeight: '600'
                                }}
                            }}
                        }}
                    }},
                    series: [{{
                        name: 'สัดส่วน',
                        data: {_safe_json_for_script(c2_series_data)}
                    }}],
                    credits: {{ enabled: false }}
                }});
            }}
        </script>
    </body>
    </html>
    """

    top_prov = df_filtered['จังหวัด'].value_counts().head(10).reset_index()
    top_prov.columns = ['จังหวัด', 'จำนวนทรัพย์']
    top_prov = top_prov[top_prov['จำนวนทรัพย์'] > 0]
    prov_tot = max(1, int(df_filtered['จังหวัด'].count())) if not df_filtered.empty else 1
    top_prov['pct'] = (top_prov['จำนวนทรัพย์'] / prov_tot) * 100.0

    fig_prov = go.Figure(go.Bar(
        x=top_prov['จำนวนทรัพย์'],
        y=top_prov['จังหวัด'].astype(str),
        orientation='h',
        marker=dict(
            color=top_prov['จำนวนทรัพย์'],
            colorscale=[[0, '#06b6d4'], [0.45, '#3b82f6'], [1, '#4f46e5']],
            cornerradius=10,
            line=dict(width=1.5, color='rgba(255, 255, 255, 0.5)')
        ),
        text=[f"{int(c):,} ({p:.1f}%)" for c, p in zip(top_prov['จำนวนทรัพย์'], top_prov['pct'])],
        textposition='outside',
        textfont=dict(size=10.5, family="Noto Sans Thai, Inter, sans-serif", weight="bold"),
        hovertemplate="จังหวัด: <b>%{y}</b><br>จำนวนทรัพย์: <b>%{x:,}</b> รายการ<extra></extra>"
    ))
    fig_prov.update_layout(
        yaxis=dict(autorange="reversed"),
        xaxis=dict(showgrid=True, gridcolor='rgba(255,255,255,0.06)' if is_dark_mode else 'rgba(0,0,0,0.05)', zeroline=False),
        title=dict(text='10 อันดับจังหวัดที่มีทรัพย์สินหนาแน่นที่สุด (Top 10 Locations)', font=dict(size=14, family="Noto Sans Thai, Inter, sans-serif")),
        height=500,
        margin=dict(t=50, b=20, l=10, r=10),
        template=plotly_template,
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)'
    )
    fig_prov = style_plotly_fig(fig_prov, is_dark_mode=is_dark_mode)

    # 100% Exact Full-Dataset Price Distribution Histogram (no 10k sampling!) + Precomputed Marginal Box
    prices_s = pd.to_numeric(df_filtered['ราคา'], errors='coerce')
    cap_mask = prices_s.notna() & np.isfinite(prices_s) & (prices_s > 0) & (prices_s <= 16_000_000)
    df_price_capped = pd.DataFrame({
        'ราคา': prices_s.loc[cap_mask],
        'ประเภททรัพย์': df_filtered.loc[cap_mask, 'ประเภททรัพย์'].astype(object),
    })
    uniq_types = df_price_capped['ประเภททรัพย์'].dropna().unique()
    type_map = {u: _map_simplified_type_scalar(u) for u in uniq_types}
    df_price_capped['ประเภททรัพย์_กลุ่ม'] = df_price_capped['ประเภททรัพย์'].map(type_map).fillna('อื่นๆ')

    group_order = [
        ("บ้านเดี่ยว", "#10b981"),
        ("ห้องชุดพักอาศัย", "#3b82f6"),
        ("ที่ดินพร้อมสิ่งปลูกสร้าง", "#f97316"),
        ("ที่ดินเปล่า", "#06b6d4"),
        ("ทาวน์เฮ้าส์", "#f59e0b"),
        ("อื่นๆ", "#94a3b8"),
    ]
    bin_edges = np.linspace(0.0, 16_000_000.0, 41)  # 40 bins of 400k Baht
    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2.0
    bin_width = float(bin_edges[1] - bin_edges[0])
    bin_labels = [f"฿{lo/1e6:.1f}M - ฿{hi/1e6:.1f}M" for lo, hi in zip(bin_edges[:-1], bin_edges[1:])]

    fig_price_dist = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.20, 0.80],
    )

    for grp_name, grp_col in group_order:
        grp_vals = df_price_capped.loc[df_price_capped['ประเภททรัพย์_กลุ่ม'] == grp_name, 'ราคา'].to_numpy(dtype=float)
        if grp_vals.size == 0:
            continue
        counts, _ = np.histogram(grp_vals, bins=bin_edges)
        safe_grp = _safe_hover_label(grp_name)
        fig_price_dist.add_trace(
            go.Bar(
                x=bin_centers,
                y=counts,
                width=bin_width * 0.94,
                name=grp_name,
                legendgroup=grp_name,
                marker=dict(color=grp_col, opacity=0.88, line=dict(width=0.6, color='rgba(255,255,255,0.4)')),
                customdata=bin_labels,
                hovertemplate=f"<b>{safe_grp}</b><br>ช่วงราคา: %{{customdata}}<br>จำนวน: <b>%{{y:,}}</b> รายการ<extra></extra>",
            ),
            row=2,
            col=1,
        )
        b_stats = _compute_box_stats(grp_vals)
        if b_stats is not None:
            fig_price_dist.add_trace(
                go.Box(
                    y=[grp_name],
                    q1=[b_stats["q1"]],
                    median=[b_stats["median"]],
                    q3=[b_stats["q3"]],
                    lowerfence=[b_stats["lowerfence"]],
                    upperfence=[b_stats["upperfence"]],
                    mean=[b_stats["mean"]],
                    orientation='h',
                    name=grp_name,
                    legendgroup=grp_name,
                    showlegend=False,
                    marker=dict(color=grp_col),
                    line=dict(color=grp_col, width=1.4),
                    boxpoints=False,
                ),
                row=1,
                col=1,
            )

    fig_price_dist.update_layout(
        title=dict(
            text=f'การกระจายตัวของราคาทรัพย์สิน ≤ 16 ล้านบาท ({len(df_price_capped):,} รายการจากที่มีราคา > 0)',
            font=dict(size=14, family="Noto Sans Thai, Inter, sans-serif"),
        ),
        barmode='stack',
        bargap=0.04,
        height=500,
        margin=dict(l=60, r=20, t=55, b=70),
        legend=dict(orientation="h", yanchor="top", y=-0.16, xanchor="center", x=0.5, font=dict(size=10.5, family="Noto Sans Thai, Inter, sans-serif")),
        template=plotly_template,
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
    )
    fig_price_dist.update_yaxes(showticklabels=False, showgrid=False, row=1, col=1)
    fig_price_dist.update_yaxes(title_text="จำนวนรายการ", showgrid=True, gridcolor='rgba(255,255,255,0.06)' if is_dark_mode else 'rgba(0,0,0,0.05)', row=2, col=1)
    fig_price_dist.update_xaxes(title_text="ราคาเริ่มต้น (บาท)", range=[0, 16_000_000], row=2, col=1)
    fig_price_dist = style_plotly_fig(fig_price_dist, is_dark_mode=is_dark_mode)

    return fig_comp, html_c2, fig_prov, fig_price_dist


@st.cache_data(show_spinner=False, max_entries=16)
def _build_tab3_subtab1_bundle(_df_filtered, is_dark_mode, cache_key=None):
    return _build_tab3_subtab1_uncached(_df_filtered, is_dark_mode)


def _build_tab3_subtab2_uncached(df_filtered, is_val_metric, is_dark_mode):
    if is_val_metric:
        value_col = 'มูลค่าทรัพย์สินรวม'
        p_pos = pd.to_numeric(df_filtered['ราคา'], errors='coerce')
        tmp = pd.DataFrame({
            'บริษัท': df_filtered['บริษัท'],
            'ประเภททรัพย์': df_filtered['ประเภททรัพย์'],
            '_val': p_pos.where(p_pos > 0, 0.0),
        })
        comp_type_df = tmp.groupby(['บริษัท', 'ประเภททรัพย์'], observed=False)['_val'].sum().reset_index(name=value_col)
        comp_type_df = comp_type_df[comp_type_df[value_col] > 0]
    else:
        value_col = 'จำนวนทรัพย์สิน'
        comp_type_df = df_filtered.groupby(['บริษัท', 'ประเภททรัพย์'], observed=False).size().reset_index(name=value_col)
        comp_type_df = comp_type_df[comp_type_df[value_col] > 0]

    other_color = '#94a3b8'
    all_comps = [str(c) for c in comp_type_df['บริษัท'].dropna().unique()]
    companies = sorted(
        all_comps,
        key=lambda c: (PREFERRED_COMPANY_ORDER.index(c) if c in PREFERRED_COMPANY_ORDER else 999, c)
    )

    if len(companies) == 0:
        return None, 0

    companies_3d_data = []
    for comp in companies:
        comp_color = COMPANY_COLORS.get(comp, '#3b82f6')
        if is_dark_mode and str(comp_color).lower() == '#475569':
            comp_color = '#94a3b8'
        cdf = comp_type_df[comp_type_df['บริษัท'].astype(str) == comp].sort_values(value_col, ascending=False)
        total = float(cdf[value_col].sum())
        if total <= 0:
            continue

        cdf = cdf.copy()
        cdf['pct'] = (cdf[value_col] / total) * 100.0
        major = cdf[cdf['pct'] >= 3.0]
        minor = cdf[cdf['pct'] < 3.0]

        series_data = []
        existing_other_idx = None
        for _, r in major.iterrows():
            t_name = str(r['ประเภททรัพย์']).strip() or 'อื่นๆ'
            t_raw = float(r[value_col])
            t_pct = round(float(r['pct']), 1)
            t_c = PROPERTY_TYPE_COLORS.get(t_name, '#6366f1')
            raw_lbl = (f"฿{t_raw:,.0f}" if t_raw < 1e6 else f"฿{t_raw/1e6:,.2f}M") if is_val_metric else f"{int(round(t_raw)):,} รายการ"
            if t_name == 'อื่นๆ':
                existing_other_idx = len(series_data)
            series_data.append({"name": html.escape(t_name, quote=True), "y": t_pct, "color": t_c, "raw_label": raw_lbl})

        if not minor.empty:
            other_pct = round(float(minor['pct'].sum()), 1)
            other_raw = float(minor[value_col].sum())
            other_lbl = (f"฿{other_raw:,.0f}" if other_raw < 1e6 else f"฿{other_raw/1e6:,.2f}M") if is_val_metric else f"{int(round(other_raw)):,} รายการ"
            if other_pct > 0:
                if existing_other_idx is not None:
                    series_data[existing_other_idx]["y"] = round(series_data[existing_other_idx]["y"] + other_pct, 1)
                else:
                    series_data.append({"name": "อื่นๆ", "y": other_pct, "color": other_color, "raw_label": other_lbl})

        total_display = f"฿{total/1e6:,.0f}M" if is_val_metric and total >= 1e6 else (f"{int(total):,} รายการ" if not is_val_metric else f"฿{total:,.0f}")

        pills = []
        for _, r in cdf.head(3).iterrows():
            t_name = str(r['ประเภททรัพย์']).strip() or 'อื่นๆ'
            t_pct = float(r['pct'])
            t_c = PROPERTY_TYPE_COLORS.get(t_name, '#6366f1')
            pills.append({"name": t_name, "pct": t_pct, "color": t_c})

        companies_3d_data.append({
            "company": comp,
            "color": comp_color,
            "total_str": total_display,
            "pills": pills,
            "series_data": series_data,
        })

    card_bg = "rgba(15, 23, 42, 0.82)" if is_dark_mode else "linear-gradient(135deg, #ffffff 0%, #f8fafc 100%)"
    card_border = "rgba(255, 255, 255, 0.12)" if is_dark_mode else "rgba(226, 232, 240, 0.9)"
    text_color = "#f8fafc" if is_dark_mode else "#0f172a"
    label_color = "#e2e8f0" if is_dark_mode else "#1e293b"

    cards_html = ""
    js_init = ""
    for idx, item in enumerate(companies_3d_data):
        comp = html.escape(str(item['company']))
        comp_color = item['color']
        total_str = html.escape(str(item['total_str']))
        top_pills_html = "".join([
            f"<span style='display:inline-block;background:{p['color']}18;color:{p['color']};border:1px solid {p['color']}40;border-radius:6px;padding:3px 8px;font-size:12px;font-weight:700;margin:2px 3px;'>{html.escape(str(p['name']))} {p['pct']:.0f}%</span>"
            for p in item['pills']
        ])

        cards_html += f"""
        <div class="donut-card" style="border-top: 4px solid {comp_color};">
            <div class="card-header">
                <span style="color: {comp_color}; font-weight: 800; font-size: 18px;">{_INLINE_BUILDING_SVG}{comp}</span>
                <span style="color: {'#cbd5e1' if is_dark_mode else '#64748b'}; font-weight: 700; font-size: 14.5px;">รวม: <b style="color:{text_color};">{total_str}</b></span>
            </div>
            <div style="text-align:center; margin-top:4px; margin-bottom: 6px;">{top_pills_html}</div>
            <div id="chart3d_{idx}" class="chart-box"></div>
        </div>
        """

        series_json = _safe_json_for_script(item['series_data'])
        js_init += f"""
        Highcharts.chart('chart3d_{idx}', {{
            chart: {{
                type: 'pie',
                options3d: {{
                    enabled: true,
                    alpha: 48,
                    beta: 0,
                    depth: 36
                }},
                backgroundColor: 'transparent',
                margin: [10, 24, 10, 24]
            }},
            title: {{ text: null }},
            tooltip: {{
                headerFormat: '',
                pointFormat: '<b>{{point.name}}</b>: <b>{{point.y:.1f}}%</b> ({{point.raw_label}})',
                style: {{ fontSize: '13px', fontFamily: 'Noto Sans Thai' }}
            }},
            plotOptions: {{
                pie: {{
                    innerSize: 0,
                    depth: 36,
                    size: '64%',
                    center: ['50%', '50%'],
                    dataLabels: {{
                        enabled: true,
                        crop: false,
                        overflow: 'allow',
                        distance: 10,
                        connectorPadding: 2,
                        connectorWidth: 1.2,
                        formatter: function() {{
                            var n = this.point.name;
                            if (n === 'ที่ดินพร้อมสิ่งปลูกสร้าง') n = 'ที่ดิน+สิ่งปลูกสร้าง';
                            return n + '<br><b>' + this.point.y.toFixed(1) + '%</b>';
                        }},
                        style: {{
                            color: '{label_color}',
                            textOutline: 'none',
                            fontSize: '11.5px',
                            fontWeight: '700',
                            fontFamily: 'Noto Sans Thai, Inter, sans-serif'
                        }}
                    }}
                }}
            }},
            series: [{{
                name: 'สัดส่วน',
                data: {series_json}
            }}],
            credits: {{ enabled: false }}
        }});
        """

    n_items = len(companies_3d_data)
    est_cols = 3 if n_items >= 6 else (2 if n_items >= 2 else 1)
    est_rows = (n_items + est_cols - 1) // est_cols
    card_est_h = 420
    total_height = max(440, est_rows * card_est_h + 30)
    hc_scripts = _highcharts_script_tags()

    full_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=Noto+Sans+Thai:wght@300;400;500;600;700;800&display=swap" referrerpolicy="no-referrer">
        {hc_scripts}
        <style>
            * {{
                box-sizing: border-box;
                font-family: 'Noto Sans Thai', 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif !important;
            }}
            body {{
                background: transparent;
                margin: 0;
                padding: 4px;
                font-family: 'Noto Sans Thai', 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                color: {text_color};
            }}
            .grid-container {{
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(420px, 1fr));
                gap: 16px;
                width: 100%;
            }}
            .donut-card {{
                background: {card_bg};
                border: 1px solid {card_border};
                border-radius: 14px;
                padding: 14px 10px 10px 10px;
                box-shadow: 0 6px 20px rgba(0,0,0,0.08);
                display: flex;
                flex-direction: column;
                justify-content: space-between;
                min-width: 0;
                transition: transform 0.2s ease, box-shadow 0.2s ease;
            }}
            .donut-card:hover {{
                transform: translateY(-3px);
                box-shadow: 0 10px 26px rgba(0,0,0,0.14);
            }}
            .card-header {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 6px;
            }}
            .chart-box {{
                height: 330px;
                width: 100%;
            }}
        </style>
    </head>
    <body>
        <div class="grid-container">
            {cards_html}
        </div>
        <script>
            if (typeof Highcharts === 'undefined') {{
                document.querySelectorAll('.chart-box').forEach(function(el) {{
                    el.innerHTML = '<div style="padding:32px;text-align:center;color:#94a3b8;font-size:13px;">ไม่สามารถโหลดไลบรารีกราฟ Highcharts ได้</div>';
                }});
            }} else {{
                Highcharts.setOptions({{
                    chart: {{
                        style: {{
                            fontFamily: "'Noto Sans Thai', 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
                        }}
                    }}
                }});
                {js_init}
            }}

            function notifyResize() {{
                try {{
                    const grid = document.querySelector('.grid-container');
                    if (!grid) return;
                    const rectH = Math.ceil(grid.getBoundingClientRect().height);
                    if (rectH <= 50) return;
                    const targetH = rectH + 16;

                    if (window.frameElement) {{
                        window.frameElement.style.height = targetH + 'px';
                    }}
                    const targetOrigin = (window.location && window.location.origin && window.location.origin !== 'null')
                        ? window.location.origin
                        : ((typeof window.origin === 'string' && window.origin && window.origin !== 'null')
                            ? window.origin
                            : ((window.parent && window.parent.location && window.parent.location.origin && window.parent.location.origin !== 'null')
                                ? window.parent.location.origin
                                : ''));
                    if (targetOrigin) {{
                        window.parent.postMessage({{
                            type: 'streamlit:setFrameHeight',
                            height: targetH
                        }}, targetOrigin);
                    }}
                }} catch(e) {{}}
            }}

            window.addEventListener('DOMContentLoaded', notifyResize);
            window.addEventListener('load', function() {{
                notifyResize();
                setTimeout(notifyResize, 150);
                setTimeout(notifyResize, 400);
                setTimeout(notifyResize, 800);
            }});
            window.addEventListener('resize', function() {{
                if (window.Highcharts && Highcharts.charts) {{
                    Highcharts.charts.forEach(function(c) {{
                        if (c) c.reflow();
                    }});
                }}
                notifyResize();
            }});
            if (window.ResizeObserver) {{
                const grid = document.querySelector('.grid-container');
                if (grid) {{
                    new ResizeObserver(function() {{
                        notifyResize();
                    }}).observe(grid);
                }}
            }}
        </script>
    </body>
    </html>
    """
    return full_html, total_height


@st.cache_data(show_spinner=False, max_entries=16)
def _build_tab3_subtab2_bundle(_df_filtered, is_val_metric, is_dark_mode, cache_key=None):
    return _build_tab3_subtab2_uncached(_df_filtered, is_val_metric, is_dark_mode)


def _fmt_mb_label(val_million):
    """Format million-Baht scalar without misleading '฿0M' rounding on sub-1M non-zero totals."""
    if val_million is None or not np.isfinite(val_million) or val_million <= 0:
        return ""
    if val_million < 1.0:
        return f"฿{val_million * 1000:,.0f}K" if val_million >= 0.001 else f"฿{val_million * 1e6:,.0f}"
    return f"฿{val_million:,.0f}M"


def _build_tab3_subtab3_uncached(df_filtered, df_raw, selected_company, compare_company, is_dark_mode):
    plotly_template = "plotly_dark" if is_dark_mode else "plotly_white"
    comp_bar_color = COMP_BRAND_COLORS.get(selected_company, "#10b981")
    comp2_bar_color = COMP_BRAND_COLORS.get(compare_company, "#3b82f6")

    comp_df_tab2 = (
        df_filtered[df_filtered['บริษัท'] == str(selected_company)].copy()
        if (df_filtered is not None and not df_filtered.empty and 'บริษัท' in df_filtered.columns)
        else pd.DataFrame()
    )

    is_comparing = (compare_company != "(ไม่เปรียบเทียบ - ดูบริษัทเดียว)")
    comp_df_2 = pd.DataFrame()
    if is_comparing:
        comp_df_2 = (
            df_filtered[df_filtered['บริษัท'] == str(compare_company)].copy()
            if (df_filtered is not None and not df_filtered.empty and 'บริษัท' in df_filtered.columns)
            else pd.DataFrame()
        )

    if comp_df_tab2.empty or (is_comparing and comp_df_2.empty):
        return {"mode": "empty", "selected_empty": comp_df_tab2.empty, "compare_empty": bool(is_comparing and comp_df_2.empty)}

    safe_c1_hover = _safe_hover_label(selected_company)
    safe_c2_hover = _safe_hover_label(compare_company)

    if is_comparing and not comp_df_tab2.empty and not comp_df_2.empty:
        comp_df_tab2['Price_Tier'] = _vectorized_price_tier(comp_df_tab2['ราคา'])
        comp_df_2['Price_Tier'] = _vectorized_price_tier(comp_df_2['ราคา'])

        c1_cnt, c2_cnt = len(comp_df_tab2), len(comp_df_2)
        p1_pos = pd.to_numeric(comp_df_tab2['ราคา'], errors='coerce')
        p1_pos = p1_pos[p1_pos > 0]
        p2_pos = pd.to_numeric(comp_df_2['ราคา'], errors='coerce')
        p2_pos = p2_pos[p2_pos > 0]

        c1_val = float(p1_pos.sum() / 1e6) if not p1_pos.empty else 0.0
        c2_val = float(p2_pos.sum() / 1e6) if not p2_pos.empty else 0.0
        c1_avg = float(p1_pos.mean() / 1e6) if not p1_pos.empty else 0.0
        c2_avg = float(p2_pos.mean() / 1e6) if not p2_pos.empty else 0.0
        c1_med = float(p1_pos.median() / 1e6) if not p1_pos.empty else 0.0
        c2_med = float(p2_pos.median() / 1e6) if not p2_pos.empty else 0.0

        card_bg = 'rgba(15, 23, 42, 0.75)' if is_dark_mode else 'linear-gradient(135deg, #ffffff 0%, #f8fafc 100%)'
        card_border = 'rgba(255, 255, 255, 0.1)' if is_dark_mode else 'rgba(226, 232, 240, 0.8)'

        safe_c1 = html.escape(str(selected_company))
        safe_c2 = html.escape(str(compare_company))

        cards_html = f"""
        <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-top: 6px; margin-bottom: 20px;">
            <div style="background: {card_bg}; border: 1px solid {card_border}; border-left: 4px solid {comp_bar_color}; border-radius: 12px; padding: 14px 16px; box-shadow: 0 4px 16px rgba(0,0,0,0.06);">
                <div style="font-size: 0.78rem; font-weight: 700; color: #64748b; margin-bottom: 6px;"><i class="fa fa-boxes"></i> จำนวนทรัพย์รวม (Units)</div>
                <div style="display: flex; justify-content: space-between; align-items: baseline; margin-top: 4px;">
                    <span style="font-size: 1.05rem; font-weight: 800; color: {comp_bar_color};">{safe_c1}: <b>{c1_cnt:,}</b></span>
                    <span style="font-size: 1.05rem; font-weight: 800; color: {comp2_bar_color};">{safe_c2}: <b>{c2_cnt:,}</b></span>
                </div>
            </div>
            <div style="background: {card_bg}; border: 1px solid {card_border}; border-left: 4px solid #f59e0b; border-radius: 12px; padding: 14px 16px; box-shadow: 0 4px 16px rgba(0,0,0,0.06);">
                <div style="font-size: 0.78rem; font-weight: 700; color: #64748b; margin-bottom: 6px;"><i class="fa fa-coins"></i> มูลค่าพอร์ตโฟลิโอรวม (MB)</div>
                <div style="display: flex; justify-content: space-between; align-items: baseline; margin-top: 4px;">
                    <span style="font-size: 1.05rem; font-weight: 800; color: {comp_bar_color};">{safe_c1}: <b>฿{c1_val:,.0f}M</b></span>
                    <span style="font-size: 1.05rem; font-weight: 800; color: {comp2_bar_color};">{safe_c2}: <b>฿{c2_val:,.0f}M</b></span>
                </div>
            </div>
            <div style="background: {card_bg}; border: 1px solid {card_border}; border-left: 4px solid #8b5cf6; border-radius: 12px; padding: 14px 16px; box-shadow: 0 4px 16px rgba(0,0,0,0.06);">
                <div style="font-size: 0.78rem; font-weight: 700; color: #64748b; margin-bottom: 6px;"><i class="fa fa-tag"></i> ราคาเฉลี่ยต่อยูนิต (Avg Price)</div>
                <div style="display: flex; justify-content: space-between; align-items: baseline; margin-top: 4px;">
                    <span style="font-size: 1.05rem; font-weight: 800; color: {comp_bar_color};">{safe_c1}: <b>฿{c1_avg:,.2f}M</b></span>
                    <span style="font-size: 1.05rem; font-weight: 800; color: {comp2_bar_color};">{safe_c2}: <b>฿{c2_avg:,.2f}M</b></span>
                </div>
            </div>
            <div style="background: {card_bg}; border: 1px solid {card_border}; border-left: 4px solid #06b6d4; border-radius: 12px; padding: 14px 16px; box-shadow: 0 4px 16px rgba(0,0,0,0.06);">
                <div style="font-size: 0.78rem; font-weight: 700; color: #64748b; margin-bottom: 6px;"><i class="fa fa-balance-scale"></i> ราคามัธยฐาน (Median Price)</div>
                <div style="display: flex; justify-content: space-between; align-items: baseline; margin-top: 4px;">
                    <span style="font-size: 1.05rem; font-weight: 800; color: {comp_bar_color};">{safe_c1}: <b>฿{c1_med:,.2f}M</b></span>
                    <span style="font-size: 1.05rem; font-weight: 800; color: {comp2_bar_color};">{safe_c2}: <b>฿{c2_med:,.2f}M</b></span>
                </div>
            </div>
        </div>
        """

        has_unpriced = bool((comp_df_tab2['Price_Tier'] == 'ไม่ระบุราคา').any() or (comp_df_2['Price_Tier'] == 'ไม่ระบุราคา').any())
        comp_tier_order = PRICE_TIER_ORDER + (['ไม่ระบุราคา'] if has_unpriced else [])
        tier1 = comp_df_tab2.groupby('Price_Tier', observed=False).agg(count=('Price_Tier', 'size'), val=('ราคา', 'sum')).reindex(comp_tier_order).reset_index().fillna(0)
        tier2 = comp_df_2.groupby('Price_Tier', observed=False).agg(count=('Price_Tier', 'size'), val=('ราคา', 'sum')).reindex(comp_tier_order).reset_index().fillna(0)
        tier1['val_million'] = tier1['val'] / 1e6
        tier2['val_million'] = tier2['val'] / 1e6

        grad1 = get_gradient_palette(selected_company, len(comp_tier_order))
        grad2 = get_gradient_palette(compare_company, len(comp_tier_order))

        fig_tier_comp = go.Figure()
        fig_tier_comp.add_trace(go.Bar(
            x=tier1['Price_Tier'],
            y=tier1['count'],
            name=f'{safe_c1} (จำนวนทรัพย์)',
            yaxis='y',
            marker=dict(color=grad1, cornerradius=8, line=dict(width=1.2, color='rgba(255, 255, 255, 0.4)')),
            text=[f"{int(c):,}" for c in tier1['count']],
            textposition='outside',
            textfont=dict(size=11, family="Noto Sans Thai", weight="bold"),
            hovertemplate=f"<b>{safe_c1_hover}</b><br>ช่วงราคา: %{{x}}<br>จำนวนทรัพย์: <b>%{{y:,}}</b> รายการ<extra></extra>"
        ))
        fig_tier_comp.add_trace(go.Bar(
            x=tier2['Price_Tier'],
            y=tier2['count'],
            name=f'{safe_c2} (จำนวนทรัพย์)',
            yaxis='y',
            marker=dict(color=grad2, cornerradius=8, line=dict(width=1.2, color='rgba(255, 255, 255, 0.4)')),
            text=[f"{int(c):,}" for c in tier2['count']],
            textposition='outside',
            textfont=dict(size=11, family="Noto Sans Thai", weight="bold"),
            hovertemplate=f"<b>{safe_c2_hover}</b><br>ช่วงราคา: %{{x}}<br>จำนวนทรัพย์: <b>%{{y:,}}</b> รายการ<extra></extra>"
        ))
        fig_tier_comp.add_trace(go.Scatter(
            x=tier1['Price_Tier'],
            y=tier1['val_million'],
            name=f'{safe_c1} (มูลค่ารวม MB)',
            yaxis='y2',
            mode='lines+markers+text',
            line=dict(width=3, color=comp_bar_color, shape='spline'),
            marker=dict(size=8, color=comp_bar_color, line=dict(width=2, color='#ffffff')),
            text=[_fmt_mb_label(v) for v in tier1['val_million']],
            textposition='top center',
            textfont=dict(size=10, family="Noto Sans Thai", color=comp_bar_color, weight="bold"),
            hovertemplate=f"มูลค่ารวม {safe_c1_hover}: <b>฿%{{y:,.1f}}M</b><extra></extra>"
        ))
        fig_tier_comp.add_trace(go.Scatter(
            x=tier2['Price_Tier'],
            y=tier2['val_million'],
            name=f'{safe_c2} (มูลค่ารวม MB)',
            yaxis='y2',
            mode='lines+markers+text',
            line=dict(width=3, color=comp2_bar_color, shape='spline', dash='dot'),
            marker=dict(size=8, color=comp2_bar_color, line=dict(width=2, color='#ffffff')),
            text=[_fmt_mb_label(v) for v in tier2['val_million']],
            textposition='top center',
            textfont=dict(size=10, family="Noto Sans Thai", color=comp2_bar_color, weight="bold"),
            hovertemplate=f"มูลค่ารวม {safe_c2_hover}: <b>฿%{{y:,.1f}}M</b><extra></extra>"
        ))

        fig_tier_comp.update_layout(
            title=dict(text=f'เปรียบเทียบจำนวนทรัพย์และมูลค่าตามช่วงราคา ({safe_c1} vs {safe_c2})', font=dict(size=14, family="Noto Sans Thai")),
            barmode='group',
            bargroupgap=0.1,
            bargap=0.25,
            yaxis=dict(title='จำนวนทรัพย์ (รายการ)', showgrid=True, gridcolor='rgba(255,255,255,0.06)' if is_dark_mode else 'rgba(0,0,0,0.05)', zeroline=False),
            yaxis2=dict(title='มูลค่ารวม (ล้านบาท)', overlaying='y', side='right', showgrid=False, zeroline=False),
            xaxis=dict(showgrid=False),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(family="Noto Sans Thai", size=11)),
            height=480,
            margin=dict(t=60, b=20, l=10, r=10),
            template=plotly_template,
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)'
        )
        fig_tier_comp = style_plotly_fig(fig_tier_comp, is_dark_mode=is_dark_mode)

        # Precomputed go.Box quantiles (shrinks 14.1 MB raw-array Plotly JSON down to ~3 KB!)
        top_types1 = comp_df_tab2['ประเภททรัพย์'].astype(str).value_counts()
        top_types1 = top_types1[top_types1 > 0].head(6).index.tolist()
        top_types2 = comp_df_2['ประเภททรัพย์'].astype(str).value_counts()
        top_types2 = top_types2[top_types2 > 0].head(6).index.tolist()
        combined_top = list(dict.fromkeys([str(t) for t in top_types1 + top_types2]))[:6]

        box1_df = comp_df_tab2[['ประเภททรัพย์', 'ราคา']].copy()
        box1_df['ประเภททรัพย์'] = box1_df['ประเภททรัพย์'].astype(str)
        box1_df['val_million'] = pd.to_numeric(box1_df['ราคา'], errors='coerce') / 1e6
        box1_df = box1_df[box1_df['ประเภททรัพย์'].isin(combined_top) & (box1_df['val_million'] > 0)]

        box2_df = comp_df_2[['ประเภททรัพย์', 'ราคา']].copy()
        box2_df['ประเภททรัพย์'] = box2_df['ประเภททรัพย์'].astype(str)
        box2_df['val_million'] = pd.to_numeric(box2_df['ราคา'], errors='coerce') / 1e6
        box2_df = box2_df[box2_df['ประเภททรัพย์'].isin(combined_top) & (box2_df['val_million'] > 0)]

        fig_box = go.Figure()
        fig_box.add_trace(_build_precomputed_box_trace(box1_df, combined_top, safe_c1, comp_bar_color))
        fig_box.add_trace(_build_precomputed_box_trace(box2_df, combined_top, safe_c2, comp2_bar_color))
        fig_box.update_layout(
            title=dict(text=f'เปรียบเทียบการกระจายราคาของ 6 ประเภททรัพย์หลัก ({safe_c1} vs {safe_c2})', font=dict(size=14, family="Noto Sans Thai")),
            boxmode='group',
            height=460,
            yaxis_type="log",
            yaxis_title="ราคา (ล้านบาท - สเกล Log)",
            yaxis=dict(
                showgrid=True,
                gridcolor='rgba(255,255,255,0.06)' if is_dark_mode else 'rgba(0,0,0,0.05)',
                tickmode='array',
                tickvals=[0.5, 1, 2, 5, 10, 20, 50, 100],
                ticktext=['฿0.5M', '฿1M', '฿2M', '฿5M', '฿10M', '฿20M', '฿50M', '฿100M'],
            ),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(family="Noto Sans Thai", size=12)),
            margin=dict(t=50, b=20, l=10, r=10),
            template=plotly_template,
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
        )
        fig_box = style_plotly_fig(fig_box, is_dark_mode=is_dark_mode)

        # Compute FULL share map first so #7+ types never falsely display 0.0%!
        t_share1_all = (comp_df_tab2['ประเภททรัพย์'].astype(str).value_counts(normalize=True) * 100.0)
        t_share2_all = (comp_df_2['ประเภททรัพย์'].astype(str).value_counts(normalize=True) * 100.0)
        top_s1 = t_share1_all[t_share1_all > 0].head(6).index.tolist()
        top_s2 = t_share2_all[t_share2_all > 0].head(6).index.tolist()
        common_types = list(dict.fromkeys(top_s1 + top_s2))[:6]
        t_share1_vals = [float(t_share1_all.get(t, 0.0)) for t in common_types]
        t_share2_vals = [float(t_share2_all.get(t, 0.0)) for t in common_types]

        grad_share1 = get_gradient_palette(selected_company, max(1, len(common_types)))
        grad_share2 = get_gradient_palette(compare_company, max(1, len(common_types)))

        fig_share = go.Figure()
        fig_share.add_trace(go.Bar(
            y=common_types,
            x=t_share1_vals,
            name=safe_c1,
            orientation='h',
            marker=dict(color=grad_share1, cornerradius=8, line=dict(width=1.2, color='rgba(255, 255, 255, 0.4)')),
            text=[f"{p:.1f}%" if p > 0 else "" for p in t_share1_vals],
            textposition='outside',
            textfont=dict(size=11, family="Noto Sans Thai", weight="bold"),
            hovertemplate=f"<b>{safe_c1_hover}</b><br>ประเภท: %{{y}}<br>สัดส่วน: <b>%{{x:.1f}}%</b><extra></extra>"
        ))
        fig_share.add_trace(go.Bar(
            y=common_types,
            x=t_share2_vals,
            name=safe_c2,
            orientation='h',
            marker=dict(color=grad_share2, cornerradius=8, line=dict(width=1.2, color='rgba(255, 255, 255, 0.4)')),
            text=[f"{p:.1f}%" if p > 0 else "" for p in t_share2_vals],
            textposition='outside',
            textfont=dict(size=11, family="Noto Sans Thai", weight="bold"),
            hovertemplate=f"<b>{safe_c2_hover}</b><br>ประเภท: %{{y}}<br>สัดส่วน: <b>%{{x:.1f}}%</b><extra></extra>"
        ))
        fig_share.update_layout(
            title=dict(text='สัดส่วนประเภททรัพย์ในพอร์ตโฟลิโอ (% Share)', font=dict(size=14, family="Noto Sans Thai")),
            barmode='group',
            bargroupgap=0.1,
            bargap=0.25,
            xaxis_title="สัดส่วนในพอร์ตโฟลิโอ (%)",
            xaxis=dict(showgrid=True, gridcolor='rgba(255,255,255,0.06)' if is_dark_mode else 'rgba(0,0,0,0.05)', zeroline=False),
            yaxis_title="",
            yaxis=dict(autorange="reversed"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(family="Noto Sans Thai", size=12)),
            height=440,
            margin=dict(t=50, b=20, l=10, r=10),
            template=plotly_template,
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)'
        )
        fig_share = style_plotly_fig(fig_share, is_dark_mode=is_dark_mode)

        fig_region = None
        if 'ภาค' in comp_df_tab2.columns and 'ภาค' in comp_df_2.columns:
            std_regions = ["ภาคกลาง", "ภาคเหนือ", "ภาคตะวันออกเฉียงเหนือ", "ภาคตะวันออก", "ภาคใต้", "ภาคตะวันตก"]
            std_set = set(std_regions)
            r1_s = comp_df_tab2['ภาค'].astype(object).fillna('').astype(str).str.strip()
            r2_s = comp_df_2['ภาค'].astype(object).fillna('').astype(str).str.strip()
            r1_norm = r1_s.where(r1_s.isin(std_set), 'อื่นๆ / ไม่ระบุ')
            r2_norm = r2_s.where(r2_s.isin(std_set), 'อื่นๆ / ไม่ระบุ')
            has_other_reg = bool((r1_norm == 'อื่นๆ / ไม่ระบุ').any() or (r2_norm == 'อื่นๆ / ไม่ระบุ').any())
            regions_all = std_regions + (['อื่นๆ / ไม่ระบุ'] if has_other_reg else [])

            r1 = r1_norm.value_counts().reindex(regions_all).fillna(0).reset_index()
            r1.columns = ['ภาค', 'count']
            r2 = r2_norm.value_counts().reindex(regions_all).fillna(0).reset_index()
            r2.columns = ['ภาค', 'count']

            grad_reg1 = get_gradient_palette(selected_company, len(regions_all))
            grad_reg2 = get_gradient_palette(compare_company, len(regions_all))

            fig_region = go.Figure()
            fig_region.add_trace(go.Bar(
                x=regions_all,
                y=r1['count'],
                name=safe_c1,
                marker=dict(color=grad_reg1, cornerradius=8, line=dict(width=1.2, color='rgba(255, 255, 255, 0.4)')),
                text=[f"{int(c):,}" if c > 0 else "" for c in r1['count']],
                textposition='outside',
                textfont=dict(size=11, family="Noto Sans Thai", weight="bold"),
                hovertemplate=f"<b>{safe_c1_hover}</b><br>ภูมิภาค: %{{x}}<br>จำนวน: <b>%{{y:,}}</b> รายการ<extra></extra>"
            ))
            fig_region.add_trace(go.Bar(
                x=regions_all,
                y=r2['count'],
                name=safe_c2,
                marker=dict(color=grad_reg2, cornerradius=8, line=dict(width=1.2, color='rgba(255, 255, 255, 0.4)')),
                text=[f"{int(c):,}" if c > 0 else "" for c in r2['count']],
                textposition='outside',
                textfont=dict(size=11, family="Noto Sans Thai", weight="bold"),
                hovertemplate=f"<b>{safe_c2_hover}</b><br>ภูมิภาค: %{{x}}<br>จำนวน: <b>%{{y:,}}</b> รายการ<extra></extra>"
            ))
            fig_region.update_layout(
                title=dict(text=f'เปรียบเทียบการกระจายตัวตามภูมิภาค ({safe_c1} vs {safe_c2})', font=dict(size=14, family="Noto Sans Thai")),
                barmode='group',
                bargroupgap=0.1,
                bargap=0.25,
                xaxis_title="ภูมิภาค",
                xaxis=dict(showgrid=False),
                yaxis_title="จำนวนทรัพย์ (รายการ)",
                yaxis=dict(showgrid=True, gridcolor='rgba(255,255,255,0.06)' if is_dark_mode else 'rgba(0,0,0,0.05)', zeroline=False),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(family="Noto Sans Thai", size=12)),
                height=440,
                margin=dict(t=50, b=20, l=10, r=10),
                template=plotly_template,
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)'
            )
            fig_region = style_plotly_fig(fig_region, is_dark_mode=is_dark_mode)

        return {
            "mode": "compare",
            "cards_html": cards_html,
            "fig_tier_comp": fig_tier_comp,
            "fig_box": fig_box,
            "fig_share": fig_share,
            "fig_region": fig_region,
        }
    else:
        if comp_df_tab2.empty:
            return {"mode": "empty"}
        comp_df_tab2['Price_Tier'] = _vectorized_price_tier(comp_df_tab2['ราคา'])

        single_tier_order = PRICE_TIER_ORDER + (['ไม่ระบุราคา'] if bool((comp_df_tab2['Price_Tier'] == 'ไม่ระบุราคา').any()) else [])
        tier_df = comp_df_tab2.groupby('Price_Tier', observed=False).agg(
            count=('Price_Tier', 'size'),
            total_val=('ราคา', 'sum')
        ).reindex(single_tier_order).reset_index()
        tier_df['count'] = tier_df['count'].fillna(0)
        tier_df['val_million'] = tier_df['total_val'].fillna(0) / 1e6

        single_grad = get_gradient_palette(selected_company, len(single_tier_order))

        fig_tier = go.Figure()
        fig_tier.add_trace(go.Bar(
            x=tier_df['Price_Tier'],
            y=tier_df['count'],
            name='จำนวนทรัพย์ (รายการ)',
            marker=dict(color=single_grad, cornerradius=8, line=dict(width=1.2, color='rgba(255, 255, 255, 0.45)')),
            yaxis='y',
            text=tier_df['count'].astype(int),
            textposition='outside',
            textfont=dict(size=11, family="Noto Sans Thai", weight="bold"),
            hovertemplate=f"<b>{safe_c1_hover}</b><br>ช่วงราคา: %{{x}}<br>จำนวนทรัพย์: <b>%{{y:,}}</b> รายการ<extra></extra>"
        ))
        fig_tier.add_trace(go.Scatter(
            x=tier_df['Price_Tier'],
            y=tier_df['val_million'],
            name='มูลค่ารวม (ล้านบาท)',
            mode='lines+markers+text',
            text=[_fmt_mb_label(v) for v in tier_df['val_million']],
            textposition='top center',
            textfont=dict(size=11, family="Noto Sans Thai", color="#3b82f6", weight="bold"),
            yaxis='y2',
            line=dict(width=3.5, color='#3b82f6', shape='spline'),
            marker=dict(size=9, color='#3b82f6', line=dict(width=2, color='#ffffff')),
            fill='tozeroy',
            fillcolor='rgba(59, 130, 246, 0.08)',
            hovertemplate="มูลค่ารวม: <b>฿%{y:,.1f}M</b><extra></extra>"
        ))
        safe_c1_single = html.escape(str(selected_company))
        fig_tier.update_layout(
            title=dict(text=f'การกระจายตัวตามช่วงราคา {safe_c1_single} (Price Tier Pyramid)', font=dict(size=14, family="Noto Sans Thai")),
            yaxis=dict(title='จำนวนทรัพย์ (รายการ)', showgrid=True, gridcolor='rgba(255,255,255,0.06)' if is_dark_mode else 'rgba(0,0,0,0.05)', zeroline=False),
            yaxis2=dict(title='มูลค่ารวม (ล้านบาท)', overlaying='y', side='right', showgrid=False),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(family="Noto Sans Thai", size=12)),
            height=460,
            margin=dict(t=50, b=20, l=10, r=10),
            template=plotly_template,
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)'
        )
        fig_tier = style_plotly_fig(fig_tier, is_dark_mode=is_dark_mode)

        top_types = comp_df_tab2['ประเภททรัพย์'].astype(str).value_counts()
        top_types = [str(t) for t in top_types[top_types > 0].head(6).index.tolist()]
        box_data = comp_df_tab2[['ประเภททรัพย์', 'ราคา']].copy()
        box_data['ประเภททรัพย์'] = box_data['ประเภททรัพย์'].astype(str)
        box_data['val_million'] = pd.to_numeric(box_data['ราคา'], errors='coerce') / 1e6
        box_data = box_data[box_data['ประเภททรัพย์'].isin(top_types) & (box_data['val_million'] > 0)]

        palette = get_gradient_palette(selected_company, max(1, len(top_types)))
        fig_box = go.Figure()
        grouped_single = box_data.groupby('ประเภททรัพย์', observed=True)['val_million']
        for i, cat in enumerate(top_types):
            if cat not in grouped_single.groups:
                continue
            st_q = _compute_box_stats(grouped_single.get_group(cat).to_numpy())
            if st_q is None:
                continue
            col_c = palette[i % len(palette)]
            fig_box.add_trace(go.Box(
                x=[cat],
                q1=[st_q["q1"]],
                median=[st_q["median"]],
                q3=[st_q["q3"]],
                lowerfence=[st_q["lowerfence"]],
                upperfence=[st_q["upperfence"]],
                mean=[st_q["mean"]],
                name=html.escape(str(cat)),
                marker=dict(color=col_c, opacity=0.85),
                line=dict(color=col_c, width=1.6),
                boxpoints=False,
                boxmean=True,
            ))

        fig_box.update_layout(
            title=dict(text=f'การกระจายราคาของ 6 ประเภททรัพย์หลัก {safe_c1_single} (Box Plot - ล้านบาท)', font=dict(size=14, family="Noto Sans Thai")),
            height=460,
            showlegend=False,
            yaxis_type="log",
            yaxis_title="ราคา (ล้านบาท - สเกล Log)",
            yaxis=dict(
                showgrid=True,
                gridcolor='rgba(255,255,255,0.06)' if is_dark_mode else 'rgba(0,0,0,0.05)',
                tickmode='array',
                tickvals=[0.5, 1, 2, 5, 10, 20, 50, 100],
                ticktext=['฿0.5M', '฿1M', '฿2M', '฿5M', '฿10M', '฿20M', '฿50M', '฿100M'],
            ),
            margin=dict(t=50, b=20, l=10, r=10),
            template=plotly_template,
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
        )
        fig_box = style_plotly_fig(fig_box, is_dark_mode=is_dark_mode)

        return {
            "mode": "single",
            "fig_tier": fig_tier,
            "fig_box": fig_box,
        }


@st.cache_data(show_spinner=False, max_entries=64)
def _build_tab3_subtab3_bundle(_df_filtered, _df_raw, selected_company, compare_company, is_dark_mode, cache_key=None):
    return _build_tab3_subtab3_uncached(_df_filtered, _df_raw, selected_company, compare_company, is_dark_mode)


def precompute_tab3_analytics(df_raw, is_dark_mode=False, data_mtime=0):
    """Pre-warms Tab 3 Sub-tab 1, Sub-tab 2, and Sub-tab 3 default caches during the Welcome Screen."""
    if df_raw is None or df_raw.empty:
        return
    base_key = (
        data_mtime or get_data_mtime(),
        len(df_raw),
        None,
        bool(is_dark_mode),
    )
    _build_tab3_subtab1_bundle(df_raw, is_dark_mode, cache_key=base_key)
    _build_tab3_subtab2_bundle(df_raw, False, is_dark_mode, cache_key=(base_key, False))

    comp_list_avail = [str(c) for c in df_raw['บริษัท'].dropna().unique()] if 'บริษัท' in df_raw.columns else []
    comp_options = sorted(
        comp_list_avail,
        key=lambda c: (PREFERRED_COMPANY_ORDER.index(c) if c in PREFERRED_COMPANY_ORDER else 999, c)
    )
    if comp_options:
        sel_c1 = "SAM" if "SAM" in comp_options else comp_options[0]
        comp_2_options = ["(ไม่เปรียบเทียบ - ดูบริษัทเดียว)"] + [c for c in comp_options if c != sel_c1]
        if sel_c1 == "SAM" and "BAM" in comp_2_options:
            sel_c2 = "BAM"
        elif sel_c1 == "BAM" and "SAM" in comp_2_options:
            sel_c2 = "SAM"
        elif len(comp_2_options) > 1:
            sel_c2 = comp_2_options[1]
        else:
            sel_c2 = comp_2_options[0]
        _build_tab3_subtab3_bundle(df_raw, df_raw, sel_c1, sel_c2, is_dark_mode, cache_key=(base_key, sel_c1, sel_c2))


@fragment_decorator
def _render_tab3_subtab2_fragment(df_filtered, is_dark_mode, bypass_cache, base_cache_key):
    st.markdown("#### <i class='fa-solid fa-home-user' style='color:#059669; margin-right:6px;'></i>สัดส่วนประเภททรัพย์สินคู่แข่งเชิงลึก (Asset Type Focus)", unsafe_allow_html=True)

    st.markdown(
        f"<div style='font-size: 0.9rem; font-weight: 700; color: {'#f8fafc' if is_dark_mode else '#0f172a'}; margin-bottom: 4px; display: flex; align-items: center; gap: 6px;'>"
        f"<i class='fa-solid fa-sliders' style='color: #059669;'></i> เลือกเกณฑ์การวิเคราะห์:"
        f"</div>",
        unsafe_allow_html=True
    )
    focus_metric = st.radio(
        "เลือกเกณฑ์การวิเคราะห์",
        ["จำนวนทรัพย์สิน (Asset Count)", "มูลค่าทรัพย์สินรวม (Total Value)"],
        horizontal=True,
        label_visibility="collapsed",
        key="focus_metric_type",
    )

    is_val_metric = (focus_metric == "มูลค่าทรัพย์สินรวม (Total Value)")
    if bypass_cache:
        full_html, total_height = _build_tab3_subtab2_uncached(df_filtered, is_val_metric, is_dark_mode)
    else:
        full_html, total_height = _build_tab3_subtab2_bundle(
            df_filtered, is_val_metric, is_dark_mode, cache_key=(base_cache_key, is_val_metric)
        )
    if full_html and total_height > 0:
        components.html(full_html, height=total_height, scrolling=True)


@fragment_decorator
def _render_tab3_subtab3_fragment(df_filtered, df_raw, is_dark_mode, bypass_cache, base_cache_key):
    col_head1, col_head2, col_head3 = st.columns([1.8, 1.1, 1.1])
    with col_head1:
        st.markdown("#### <i class='fa-solid fa-scale-balanced' style='color:#059669; margin-right:6px;'></i>การกระจายตัวเชิงลึกของพอร์ตโฟลิโอรายบริษัท", unsafe_allow_html=True)
        st.caption("วิเคราะห์และเปรียบเทียบการกระจายตัวตามช่วงราคา และประเภททรัพย์สินหลักระหว่างบริษัท")

    comp_list_avail = []
    if not df_filtered.empty and 'บริษัท' in df_filtered.columns:
        comp_list_avail = [str(c) for c in df_filtered['บริษัท'].dropna().unique()]

    comp_options = sorted(
        comp_list_avail,
        key=lambda c: (PREFERRED_COMPANY_ORDER.index(c) if c in PREFERRED_COMPANY_ORDER else 999, c)
    )
    if not comp_options:
        st.warning("ไม่พบรายชื่อบริษัทสำหรับเปรียบเทียบ")
        return

    default_idx1 = comp_options.index("SAM") if "SAM" in comp_options else 0

    with col_head2:
        st.markdown(
            f"<div style='font-size: 0.9rem; font-weight: 700; color: {'#f8fafc' if is_dark_mode else '#0f172a'}; margin-bottom: 4px; display: flex; align-items: center; gap: 6px;'>"
            f"<i class='fa-solid fa-building' style='color: #059669;'></i> บริษัทหลัก (Company 1):"
            f"</div>",
            unsafe_allow_html=True
        )
        selected_company = st.selectbox(
            "บริษัทหลัก (Company 1):",
            options=comp_options,
            index=default_idx1,
            label_visibility="collapsed",
            key="tab2_subtab3_selected_company",
        )

    comp_2_options = ["(ไม่เปรียบเทียบ - ดูบริษัทเดียว)"] + [c for c in comp_options if c != selected_company]
    if selected_company == "SAM" and "BAM" in comp_2_options:
        def_idx2 = comp_2_options.index("BAM")
    elif selected_company == "BAM" and "SAM" in comp_2_options:
        def_idx2 = comp_2_options.index("SAM")
    elif len(comp_2_options) > 1:
        def_idx2 = 1
    else:
        def_idx2 = 0

    with col_head3:
        st.markdown(
            f"<div style='font-size: 0.9rem; font-weight: 700; color: {'#f8fafc' if is_dark_mode else '#0f172a'}; margin-bottom: 4px; display: flex; align-items: center; gap: 6px;'>"
            f"<i class='fa-solid fa-arrows-left-right' style='color: #059669;'></i> เปรียบเทียบกับ (Company 2):"
            f"</div>",
            unsafe_allow_html=True
        )
        compare_company = st.selectbox(
            "เปรียบเทียบกับ (Company 2):",
            options=comp_2_options,
            index=def_idx2,
            label_visibility="collapsed",
            key="tab2_subtab3_compare_company",
        )

    if bypass_cache:
        sub3_bundle = _build_tab3_subtab3_uncached(df_filtered, df_raw, selected_company, compare_company, is_dark_mode)
    else:
        sub3_bundle = _build_tab3_subtab3_bundle(
            df_filtered, df_raw, selected_company, compare_company, is_dark_mode,
            cache_key=(base_cache_key, selected_company, compare_company),
        )

    if sub3_bundle.get("mode") == "empty":
        safe_sel_md = re.sub(r'([\\\[\]()!*_`<>])', r'\\\1', str(selected_company))
        if sub3_bundle.get("compare_empty"):
            safe_cmp_md = re.sub(r'([\\\[\]()!*_`<>])', r'\\\1', str(compare_company))
            st.warning(f"ไม่พบข้อมูลทรัพย์สินของ {safe_cmp_md} (หรือ {safe_sel_md}) ในตัวกรองปัจจุบัน")
        else:
            st.warning(f"ไม่พบข้อมูลทรัพย์สินของ {safe_sel_md} ในตัวกรองปัจจุบัน")
    elif sub3_bundle.get("mode") == "compare":
        st.markdown(sub3_bundle["cards_html"], unsafe_allow_html=True)
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            st.plotly_chart(sub3_bundle["fig_tier_comp"], width="stretch", theme=None)
        with col_c2:
            st.plotly_chart(sub3_bundle["fig_box"], width="stretch", theme=None)

        col_c3, col_c4 = st.columns(2)
        with col_c3:
            st.plotly_chart(sub3_bundle["fig_share"], width="stretch", theme=None)
        with col_c4:
            if sub3_bundle.get("fig_region") is not None:
                st.plotly_chart(sub3_bundle["fig_region"], width="stretch", theme=None)
    elif sub3_bundle.get("mode") == "single":
        col_s1, col_s2 = st.columns(2)
        with col_s1:
            st.plotly_chart(sub3_bundle["fig_tier"], width="stretch", theme=None)
        with col_s2:
            st.plotly_chart(sub3_bundle["fig_box"], width="stretch", theme=None)


@fragment_decorator
def render_tab3_analytics_view(df_filtered, df_raw, is_dark_mode):
    """
    Renders Tab 3: Competitor & Market Analytics:
    - Sub-tab 1: Market Overview (Market share, 3D Asset Share with 'อื่นๆ', Top 10 locations, 100% Exact Price histogram)
    - Sub-tab 2: Asset Type Focus (3D Donuts per company by count or total valuation)
    - Sub-tab 3: Portfolio Deep Dive (Single company mode or Head-to-Head 2-company comparison with compact Box Plots)
    """
    st.markdown("### <i class='fa-solid fa-chart-line' style='color:#059669; margin-right:8px;'></i>วิเคราะห์เชิงลึกและเปรียบเทียบสถิติของคู่แข่ง", unsafe_allow_html=True)

    if df_filtered is None or df_filtered.empty:
        st.warning("ไม่มีข้อมูลสำหรับจัดทำแผนภูมิวิเคราะห์สถิติ")
        return

    has_custom = bool(
        st.session_state.get("imported_custom_df") is not None
        and not st.session_state["imported_custom_df"].empty
    )
    custom_fp = st.session_state.get("_custom_import_fp") if has_custom else None
    bypass_cache = has_custom and not custom_fp
    _idx_hash = (
        int(pd.util.hash_pandas_object(df_filtered.index, index=False).sum() & 0xFFFFFFFFFFFF)
        if len(df_filtered) > 0
        else 0
    )
    _co_sig = tuple(sorted(str(c) for c in df_filtered['บริษัท'].dropna().unique())) if 'บริษัท' in df_filtered.columns else ()
    base_cache_key = (
        get_data_mtime(),
        len(df_filtered),
        _idx_hash,
        _co_sig,
        custom_fp,
        bool(is_dark_mode),
    )

    sub_tab1, sub_tab2, sub_tab3 = st.tabs([
        "ภาพรวมตลาด (Market Overview)",
        "สัดส่วนสินค้าคู่แข่ง (Asset Type Focus)",
        "การกระจายตัวพอร์ตโฟลิโอรายบริษัท (Portfolio Deep Dive)",
    ])

    # =========================================================================
    # SUB-TAB 1: MARKET OVERVIEW
    # =========================================================================
    with sub_tab1:
        if bypass_cache:
            fig_comp, html_c2, fig_prov, fig_price_dist = _build_tab3_subtab1_uncached(df_filtered, is_dark_mode)
        else:
            fig_comp, html_c2, fig_prov, fig_price_dist = _build_tab3_subtab1_bundle(
                df_filtered, is_dark_mode, cache_key=base_cache_key
            )
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            with st.container(border=True):
                st.plotly_chart(fig_comp, width="stretch", theme=None)
        with col_c2:
            with st.container(border=True):
                components.html(html_c2, height=450, scrolling=False)

        st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)
        col_c3, col_c4 = st.columns(2)
        with col_c3:
            with st.container(border=True):
                st.plotly_chart(fig_prov, width="stretch", theme=None)
        with col_c4:
            with st.container(border=True):
                st.plotly_chart(fig_price_dist, width="stretch", theme=None)

    # =========================================================================
    # SUB-TAB 2: ASSET TYPE FOCUS (3D DONUTS)
    # =========================================================================
    with sub_tab2:
        _render_tab3_subtab2_fragment(df_filtered, is_dark_mode, bypass_cache, base_cache_key)

    # =========================================================================
    # SUB-TAB 3: PORTFOLIO DEEP DIVE (SINGLE OR 2-COMPANY COMPARISON)
    # =========================================================================
    with sub_tab3:
        _render_tab3_subtab3_fragment(df_filtered, df_raw, is_dark_mode, bypass_cache, base_cache_key)
