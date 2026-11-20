from collections import OrderedDict
from functools import lru_cache
import base64
import io
import json
import math
import os
from pathlib import Path
import threading
import numpy as np
import pandas as pd
import streamlit as st
from PIL import Image, ImageDraw, ImageFont

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.abspath(os.path.join(_SCRIPT_DIR, "..", ".."))

_ICON_CACHE_LOCK = threading.Lock()
_ATLAS_CACHE_BY_KEY = OrderedDict()
_LEAFLET_LOGO_CACHE_BY_KEY = OrderedDict()
_MAX_ICON_CACHE_ENTRIES = 32
_MAX_CUSTOM_ATLAS_COMPANIES = 64
_ATLAS_GRID_COLS = 10
_TRANSPARENT_1PX_PNG_URI = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)


def haversine_distance(lat1, lon1, lat2, lon2):
    """Haversine distance calculation between two points in km."""
    R = 6371.0  # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2.0) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2.0) ** 2
    )
    a = min(1.0, max(0.0, a))
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c


def haversine_distance_vectorized(lat1, lon1, lats, lons):
    """Vectorized Haversine distance computation using NumPy."""
    R = 6371.0  # Earth radius in km
    lat1_rad = np.radians(lat1)
    lon1_rad = np.radians(lon1)
    lats_rad = np.radians(lats)
    lons_rad = np.radians(lons)

    dlat = lats_rad - lat1_rad
    dlon = lons_rad - lon1_rad

    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1_rad) * np.cos(lats_rad) * np.sin(dlon / 2.0) ** 2
    c = 2.0 * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))
    return R * c


def find_nearby_properties(input_lat, input_lon, df_all, radius_km, match_type=None, company=None):
    """Find properties within radius_km of the given coordinates (Bounding Box + Haversine)."""
    if df_all is None or df_all.empty:
        empty_df = pd.DataFrame()
        empty_df['ระยะทาง (กม.)'] = pd.Series(dtype='float64')
        return empty_df

    empty_res = df_all.head(0).copy()
    if 'ระยะทาง (กม.)' not in empty_res.columns:
        empty_res['ระยะทาง (กม.)'] = pd.Series(dtype='float64')

    try:
        in_lat = float(input_lat)
        in_lon = float(input_lon)
        rad = float(radius_km)
    except (TypeError, ValueError):
        return empty_res

    if not (math.isfinite(in_lat) and math.isfinite(in_lon) and math.isfinite(rad)) or rad <= 0:
        return empty_res
    if 'ละติจูด' not in df_all.columns or 'ลองจิจูด' not in df_all.columns:
        return empty_res

    cos_lat = max(0.1, abs(math.cos(math.radians(in_lat))))
    lat_margin = (rad / 110.574) + 0.015
    lon_margin = (rad / (111.32 * cos_lat)) + 0.015

    mask = (
        df_all['ละติจูด'].notna() &
        df_all['ลองจิจูด'].notna() &
        df_all['ละติจูด'].between(in_lat - lat_margin, in_lat + lat_margin) &
        df_all['ลองจิจูด'].between(in_lon - lon_margin, in_lon + lon_margin)
    )

    if company and 'บริษัท' in df_all.columns:
        mask &= (df_all['บริษัท'] == company)

    if match_type and 'ประเภททรัพย์' in df_all.columns:
        if isinstance(match_type, (list, tuple, set)):
            clean_types = [str(t).strip() for t in match_type if str(t).strip() not in ['', 'nan', 'None']]
            if clean_types:
                mask &= (df_all['ประเภททรัพย์'].isin(clean_types))
        elif str(match_type).strip() not in ['', 'nan', 'None']:
            mask &= (df_all['ประเภททรัพย์'] == str(match_type).strip())

    df_sub = df_all[mask]
    if df_sub.empty:
        return empty_res

    lats = df_sub['ละติจูด'].to_numpy(dtype=float)
    lons = df_sub['ลองจิจูด'].to_numpy(dtype=float)

    distances = haversine_distance_vectorized(in_lat, in_lon, lats, lons)
    nearby_mask = distances <= rad

    if not np.any(nearby_mask):
        return empty_res

    df_result = df_sub[nearby_mask].copy()
    df_result['ระยะทาง (กม.)'] = np.round(distances[nearby_mask], 2)
    return df_result


@lru_cache(maxsize=32)
def _get_badge_text_font(font_size):
    for fp in (
        'C:/Windows/Fonts/segoeuib.ttf',
        'C:/Windows/Fonts/tahomabd.ttf',
        'C:/Windows/Fonts/arialbd.ttf',
        'C:/Windows/Fonts/segoeui.ttf',
        'C:/Windows/Fonts/tahoma.ttf',
        'C:/Windows/Fonts/arial.ttf',
    ):
        if os.path.exists(fp):
            try:
                return ImageFont.truetype(fp, font_size)
            except Exception:
                pass
    return ImageFont.load_default()


@lru_cache(maxsize=16)
def _get_fa_solid_font(font_size):
    for font_candidate in (
        os.path.join(_ROOT_DIR, "static", "fa-solid-900.ttf"),
        os.path.join(_SCRIPT_DIR, "static", "fa-solid-900.ttf"),
        os.path.join(_SCRIPT_DIR, "..", "..", "static", "fa-solid-900.ttf"),
        "static/fa-solid-900.ttf",
    ):
        if os.path.exists(font_candidate):
            try:
                return ImageFont.truetype(font_candidate, font_size)
            except Exception:
                pass
    return None


def _hex_to_rgba(h, alpha=255):
    try:
        h = str(h).lstrip('#')
        if len(h) == 6:
            return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), alpha)
    except Exception:
        pass
    return (99, 102, 241, alpha)


def _resolve_custom_company_inputs(
    include_session_custom=True,
    custom_companies=None,
    custom_company=None,
    custom_color_hex="#6366f1",
    custom_symbol="IMP",
):
    c_company = custom_company
    c_color = custom_color_hex
    c_sym = custom_symbol
    c_dict = custom_companies if isinstance(custom_companies, dict) else {}

    if include_session_custom and custom_companies is None and custom_company is None:
        try:
            if hasattr(st, "session_state"):
                c_company = st.session_state.get("imported_custom_company")
                c_color = st.session_state.get("imported_custom_color", "#6366f1")
                c_sym = st.session_state.get("imported_custom_symbol", "IMP")
                sess_dict = st.session_state.get("imported_custom_companies", {})
                if isinstance(sess_dict, dict):
                    c_dict = sess_dict
        except Exception:
            pass

    sanitized_dict = {}
    for k, v in c_dict.items():
        if k and isinstance(v, dict):
            sanitized_dict[str(k)] = {
                "symbol": str(v.get("symbol", "") or ""),
                "color": str(v.get("color", "#6366f1") or "#6366f1"),
            }
            if len(sanitized_dict) >= _MAX_CUSTOM_ATLAS_COMPANIES:
                break

    custom_fp_tuple = tuple(
        (k, v["symbol"], v["color"]) for k, v in sorted(sanitized_dict.items())
    )
    return c_company, str(c_color or "#6366f1"), str(c_sym or "IMP"), sanitized_dict, custom_fp_tuple


def get_map_icon_atlas_and_mapping(
    icon_size=128,
    include_session_custom=True,
    custom_companies=None,
    custom_company=None,
    custom_color_hex="#6366f1",
    custom_symbol="IMP",
):
    """Builds and caches a 2D-grid Retina sprite sheet atlas containing company badges and property type pins."""
    c_company, c_color, c_sym, custom_companies_dict, custom_fp_tuple = _resolve_custom_company_inputs(
        include_session_custom=include_session_custom,
        custom_companies=custom_companies,
        custom_company=custom_company,
        custom_color_hex=custom_color_hex,
        custom_symbol=custom_symbol,
    )

    cache_key = (int(icon_size), c_company, c_color, c_sym, custom_fp_tuple)
    with _ICON_CACHE_LOCK:
        cached_entry = _ATLAS_CACHE_BY_KEY.get(cache_key)
        if cached_entry is not None:
            _ATLAS_CACHE_BY_KEY.move_to_end(cache_key)
            return cached_entry[0], dict(cached_entry[1])

    custom_rgba = _hex_to_rgba(c_color)

    companies = [
        "LED", "LED Legal", "LED_SOLD", "SAM", "BAM", "Chayo555", "GHB", "KBANK", "KTB", "SCB", "GSB",
        "DDproperty", "Livinginsider", "NaYoo", "ZmyHome", "Baania", "จุดอ้างอิง", "ไฟล์นำเข้า"
    ]
    for c_name in custom_companies_dict:
        if c_name and c_name not in companies:
            companies.append(c_name)
    if c_company and c_company not in companies and c_company != "(ตามข้อมูลในไฟล์)":
        companies.append(c_company)

    company_colors_map = {
        "LED": (8, 145, 178, 255), "LED Legal": (71, 85, 105, 255), "LED_SOLD": (71, 85, 105, 255),
        "SAM": (16, 185, 129, 255), "BAM": (59, 130, 246, 255),
        "Chayo555": (249, 115, 22, 255), "Chayo": (249, 115, 22, 255), "GHB": (202, 138, 4, 255),
        "KBANK": (5, 150, 105, 255), "KTB": (2, 132, 199, 255), "SCB": (126, 34, 206, 255),
        "GSB": (235, 25, 133, 255), "DDproperty": (168, 85, 247, 255), "Livinginsider": (20, 184, 166, 255),
        "NaYoo": (139, 92, 246, 255), "ZmyHome": (236, 72, 153, 255), "Baania": (245, 158, 11, 255),
        "ไฟล์นำเข้า": custom_rgba,
    }
    for c_name, c_info in custom_companies_dict.items():
        if isinstance(c_info, dict) and "color" in c_info:
            company_colors_map[c_name] = _hex_to_rgba(c_info["color"])
    if c_company:
        company_colors_map[c_company] = custom_rgba

    prop_types = [
        ("ห้องชุดพักอาศัย", "\uf1ad", (139, 92, 246, 255)),
        ("คอนโด", "\uf1ad", (139, 92, 246, 255)),
        ("คอนโดมิเนียม", "\uf1ad", (139, 92, 246, 255)),
        ("อาคารชุดพักอาศัย", "\uf1ad", (139, 92, 246, 255)),
        ("บ้านเดี่ยว", "\uf015", (37, 99, 235, 255)),
        ("ที่ดินพร้อมสิ่งปลูกสร้าง", "\ue587", (249, 115, 22, 255)),
        ("ที่ดินเปล่า", "\uf1bb", (139, 69, 19, 255)),
        ("ที่ดิน", "\uf1bb", (139, 69, 19, 255)),
        ("ทาวน์เฮ้าส์", None, (245, 158, 11, 255)),
        ("ทาวน์โฮม", None, (245, 158, 11, 255)),
        ("อาคารพาณิชย์", "\uf54e", (244, 63, 94, 255)),
        ("วิลล่า", "\uf3a5", (236, 72, 153, 255)),
        ("บ้านแฝด", "\ue00d", (14, 165, 233, 255)),
        ("โรงงาน/โกดัง", "\uf275", (6, 182, 212, 255)),
        ("อพาร์ทเมนท์", "\uf594", (168, 85, 247, 255)),
        ("อาคารสำนักงาน", "\uf0b1", (100, 116, 139, 255)),
        ("โรงแรม/รีสอร์ท", "\uf5ca", (234, 179, 8, 255)),
        ("ห้องชุดพาณิชยกรรม/สำนักงาน", "\uf1ad", (14, 165, 233, 255)),
        ("โฮมออฟฟิศ", "\ue016", (79, 70, 229, 255)),
        ("ปั๊มน้ำมัน", "\uf52f", (217, 119, 6, 255)),
        ("โชว์รูม", "\uf1b9", (249, 115, 22, 255)),
        ("สังหาริมทรัพย์", "\uf466", (120, 113, 108, 255)),
        ("เพิงอเนกประสงค์", "\uf494", (161, 98, 7, 255)),
        ("สิ่งปลูกสร้าง", "\uf1ad", (100, 116, 139, 255)),
        ("ฟาร์ม", "\ue4f8", (34, 197, 94, 255)),
        ("โรงเรียน", "\uf549", (234, 88, 12, 255)),
        ("อื่นๆ", "\uf3c5", (100, 116, 139, 255)),
    ]

    total_slots = len(companies) + len(prop_types)
    grid_cols = min(_ATLAS_GRID_COLS, max(1, total_slots))
    grid_rows = int(math.ceil(total_slots / float(grid_cols)))
    atlas_width = grid_cols * icon_size
    atlas_height = grid_rows * icon_size

    try:
        atlas = Image.new("RGBA", (atlas_width, atlas_height), (0, 0, 0, 0))
        icon_mapping = {}
        margin = 4
        border_w = max(5, int(icon_size * 0.065))
        fa_font = _get_fa_solid_font(int(icon_size * 0.48))

        logo_roots = (
            os.path.join(_ROOT_DIR, "logo", "logos"),
            os.path.join(_ROOT_DIR, "assets", "logos"),
            os.path.join("logo", "logos"),
            os.path.join("assets", "logos"),
        )

        # 1. Render Company Badges
        for i, name in enumerate(companies):
            x_offset = (i % grid_cols) * icon_size
            y_offset = (i // grid_cols) * icon_size
            cell = Image.new("RGBA", (icon_size, icon_size), (0, 0, 0, 0))
            draw = ImageDraw.Draw(cell)

            if name == "จุดอ้างอิง":
                draw.ellipse([margin, margin, icon_size - margin, icon_size - margin], fill=(239, 68, 68, 255), outline=(255, 255, 255, 255), width=border_w)
                c_mid = icon_size // 2
                draw.ellipse([c_mid - 24, c_mid - 24, c_mid + 24, c_mid + 24], fill=(255, 255, 255, 255))
                draw.ellipse([c_mid - 12, c_mid - 12, c_mid + 12, c_mid + 12], fill=(239, 68, 68, 255))
            elif name in ("ไฟล์นำเข้า", c_company) or name in custom_companies_dict:
                c_conf = custom_companies_dict.get(name, {})
                c_col_hex = c_conf.get("color", c_color)
                b_col = _hex_to_rgba(c_col_hex)
                draw.ellipse([margin, margin, icon_size - margin, icon_size - margin], fill=(255, 255, 255, 255), outline=b_col, width=border_w)
                c_mid = icon_size // 2
                sym = str(c_conf.get("symbol") or c_sym or "IMP").strip() or "IMP"
                sym_len = len(sym)
                if sym_len <= 1:
                    f_sz = int(icon_size * 0.52)
                elif sym_len == 2:
                    f_sz = int(icon_size * 0.42)
                elif sym_len == 3:
                    f_sz = int(icon_size * 0.34)
                else:
                    f_sz = int(icon_size * 0.28)
                t_font = _get_badge_text_font(f_sz)
                draw.text((c_mid, c_mid), sym, font=t_font, fill=b_col, anchor="mm")
            else:
                b_col = company_colors_map.get(name, (59, 130, 246, 255))
                draw.ellipse([margin, margin, icon_size - margin, icon_size - margin], fill=(255, 255, 255, 255), outline=b_col, width=border_w)

                logo_path = None
                search_bases = [name, name.lower(), name.upper(), name.capitalize(), name.title()] + (
                    ["LED", "led"] if name in ("LED Legal", "LED_Legal", "LED_SOLD") else []
                )
                for base in search_bases:
                    for ext in ('.png', '.jpg', '.jpeg', '.webp'):
                        for lr in logo_roots:
                            cand_p = os.path.join(lr, f"{base}{ext}")
                            if os.path.exists(cand_p):
                                logo_path = cand_p
                                break
                        if logo_path:
                            break
                    if logo_path:
                        break

                if logo_path:
                    try:
                        with Image.open(logo_path) as _src_logo:
                            logo = _src_logo.convert("RGBA")
                        if name in ("LED Legal", "LED_Legal", "LED_SOLD") or "sold" in name.lower() or "legal" in name.lower():
                            _, _, _, a_c = logo.split()
                            gray_c = logo.convert("L")
                            logo = Image.merge("RGBA", (gray_c, gray_c, gray_c, a_c))
                        bbox = logo.getbbox()
                        if bbox:
                            logo = logo.crop(bbox)
                        inner_max = int((icon_size - margin * 2) * 0.72)
                        logo.thumbnail((inner_max, inner_max), Image.Resampling.LANCZOS)
                        off_x = (icon_size - logo.width) // 2
                        off_y = (icon_size - logo.height) // 2
                        cell.paste(logo, (off_x, off_y), logo)
                    except Exception:
                        draw.text((icon_size // 2, icon_size // 2), name[:4].upper(), fill=(15, 23, 42, 255), anchor="mm")
                else:
                    draw.text((icon_size // 2, icon_size // 2), name[:4].upper(), fill=(15, 23, 42, 255), anchor="mm")

            atlas.paste(cell, (x_offset, y_offset), cell)
            slot_meta = {
                "x": x_offset,
                "y": y_offset,
                "width": icon_size,
                "height": icon_size,
                "mask": False,
                "anchorX": icon_size // 2,
                "anchorY": icon_size // 2,
            }
            icon_mapping[name] = slot_meta
            icon_mapping[name.lower()] = slot_meta
            icon_mapping[name.upper()] = slot_meta

        # 2. Render Property Type Badges using FontAwesome icons
        start_idx = len(companies)
        for j, (p_type, p_char, p_col) in enumerate(prop_types):
            slot_i = start_idx + j
            x_offset = (slot_i % grid_cols) * icon_size
            y_offset = (slot_i // grid_cols) * icon_size
            cell = Image.new("RGBA", (icon_size, icon_size), (0, 0, 0, 0))
            draw = ImageDraw.Draw(cell)
            draw.ellipse([margin, margin, icon_size - margin, icon_size - margin], fill=p_col, outline=(255, 255, 255, 255), width=border_w)

            c = icon_size // 2
            if fa_font and p_char:
                draw.text((c, c), p_char, font=fa_font, fill=(255, 255, 255, 255), anchor="mm")
            else:
                if "บ้าน" in p_type or p_type == "วิลล่า":
                    draw.polygon([(c, c - 26), (c - 28, c - 2), (c + 28, c - 2)], fill=(255, 255, 255, 255))
                    draw.rectangle([c - 20, c - 2, c + 20, c + 24], fill=(255, 255, 255, 255))
                    draw.rectangle([c - 7, c + 6, c + 7, c + 24], fill=p_col)
                elif "คอนโด" in p_type or "ห้องชุด" in p_type:
                    draw.rectangle([c - 22, c - 28, c + 22, c + 28], fill=(255, 255, 255, 255))
                    for wy in (-18, -6, 6, 18):
                        for wx in (-14, 2):
                            draw.rectangle([c + wx, c + wy, c + wx + 9, c + wy + 8], fill=p_col)
                elif "ทาวน์" in p_type:
                    draw.polygon([(c - 16, c - 24), (c - 32, c - 6), (c, c - 6)], fill=(255, 255, 255, 255))
                    draw.rectangle([c - 28, c - 6, c - 4, c + 24], fill=(255, 255, 255, 255))
                    draw.polygon([(c + 16, c - 24), (c, c - 6), (c + 32, c - 6)], fill=(255, 255, 255, 255))
                    draw.rectangle([c + 4, c - 6, c + 28, c + 24], fill=(255, 255, 255, 255))
                elif "ที่ดิน" in p_type:
                    draw.polygon([(c, c - 26), (c - 24, c + 4), (c + 24, c + 4)], fill=(255, 255, 255, 255))
                    draw.polygon([(c, c - 14), (c - 20, c + 14), (c + 20, c + 14)], fill=(255, 255, 255, 255))
                    draw.rectangle([c - 5, c + 14, c + 5, c + 26], fill=(255, 255, 255, 255))
                elif "พาณิชย์" in p_type:
                    draw.rectangle([c - 25, c - 18, c + 25, c + 25], fill=(255, 255, 255, 255))
                    draw.polygon([(c, c - 28), (c - 28, c - 18), (c + 28, c - 18)], fill=(255, 255, 255, 255))
                    draw.rectangle([c - 16, c - 2, c - 3, c + 12], fill=p_col)
                    draw.rectangle([c + 3, c - 2, c + 16, c + 12], fill=p_col)
                    draw.rectangle([c - 8, c + 14, c + 8, c + 25], fill=p_col)
                elif "โรงงาน" in p_type:
                    draw.polygon([(c - 26, c - 6), (c - 10, c - 20), (c - 10, c - 6), (c + 8, c - 20), (c + 8, c - 6), (c + 24, c - 6), (c + 24, c + 24), (c - 26, c + 24)], fill=(255, 255, 255, 255))
                    draw.rectangle([c + 14, c - 26, c + 20, c - 6], fill=(255, 255, 255, 255))
                else:
                    draw.ellipse([c - 16, c - 16, c + 16, c + 16], fill=(255, 255, 255, 255))

            atlas.paste(cell, (x_offset, y_offset), cell)
            icon_mapping[p_type] = {
                "x": x_offset,
                "y": y_offset,
                "width": icon_size,
                "height": icon_size,
                "mask": False,
                "anchorX": icon_size // 2,
                "anchorY": icon_size // 2,
            }

        buf = io.BytesIO()
        atlas.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        data_uri = f"data:image/png;base64,{b64}"

        with _ICON_CACHE_LOCK:
            if len(_ATLAS_CACHE_BY_KEY) >= _MAX_ICON_CACHE_ENTRIES:
                _ATLAS_CACHE_BY_KEY.popitem(last=False)
            _ATLAS_CACHE_BY_KEY[cache_key] = (data_uri, dict(icon_mapping))
        return data_uri, icon_mapping
    except Exception:
        return _TRANSPARENT_1PX_PNG_URI, {}


def create_map_circle_coords(lat, lon, radius_km, num_points=64):
    """Generates lat/lon coordinates for a smooth circular polygon on Plotly map."""
    angles = np.linspace(0, 2 * np.pi, num_points)
    d_lat = (radius_km / 111.32) * np.sin(angles)
    cos_lat = max(0.1, abs(np.cos(np.radians(lat))))
    d_lon = (radius_km / (111.32 * cos_lat)) * np.cos(angles)
    return lat + d_lat, lon + d_lon


def get_leaflet_logo_dict(
    size=72,
    include_session_custom=True,
    custom_companies=None,
    custom_company=None,
    custom_color_hex="#6366f1",
    custom_symbol="IMP",
):
    """Generates optimized base64 dictionary of all company logos for Leaflet pins."""
    c_company, c_color, c_sym, custom_companies_dict, custom_fp_tuple = _resolve_custom_company_inputs(
        include_session_custom=include_session_custom,
        custom_companies=custom_companies,
        custom_company=custom_company,
        custom_color_hex=custom_color_hex,
        custom_symbol=custom_symbol,
    )

    cache_k = (int(size), c_company, c_color, c_sym, custom_fp_tuple)
    with _ICON_CACHE_LOCK:
        cached_logos = _LEAFLET_LOGO_CACHE_BY_KEY.get(cache_k)
        if cached_logos is not None:
            _LEAFLET_LOGO_CACHE_BY_KEY.move_to_end(cache_k)
            return dict(cached_logos)

    root_path = Path(_ROOT_DIR)
    cwd_path = Path(os.getcwd())
    logo_dir = next(
        (d for d in (
            root_path / "logo" / "logos",
            cwd_path / "logo" / "logos",
            root_path / "assets" / "logos",
            cwd_path / "assets" / "logos",
        ) if d.exists()),
        root_path / "logo" / "logos",
    )

    logo_dict = {}
    if logo_dir.exists():
        for fname in os.listdir(logo_dir):
            if fname.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                path = logo_dir / fname
                base_name = os.path.splitext(fname)[0].strip()
                try:
                    with Image.open(path) as _src_im:
                        im = _src_im.convert("RGBA")
                    bbox = im.getbbox()
                    if bbox:
                        im = im.crop(bbox)
                    max_side = max(1, im.width, im.height)
                    square = Image.new("RGBA", (max_side, max_side), (0, 0, 0, 0))
                    ox = (max_side - im.width) // 2
                    oy = (max_side - im.height) // 2
                    square.paste(im, (ox, oy), im)
                    square = square.resize((size, size), Image.Resampling.LANCZOS)
                    buf = io.BytesIO()
                    square.save(buf, format="PNG", optimize=True)
                    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
                    data_uri = f"data:image/png;base64,{b64}"

                    variants = {
                        base_name,
                        base_name.lower(),
                        base_name.upper(),
                        base_name.capitalize(),
                        base_name.title(),
                    }
                    clean_name = base_name.replace("logo", "").replace(" ", "").strip()
                    if clean_name:
                        variants.update({
                            clean_name,
                            clean_name.lower(),
                            clean_name.upper(),
                            clean_name.capitalize(),
                            clean_name.title(),
                        })

                    low = base_name.lower()
                    if "zmyhome" in low:
                        variants.update({"ZmyHome", "Zmyhome", "zmyhome", "ZMYHOME"})
                    elif "nayoo" in low:
                        variants.update({"NaYoo", "Nayoo", "nayoo", "NAYOO"})
                    elif "baania" in low:
                        variants.update({"Baania", "baania", "BAANIA"})
                    elif "living" in low:
                        variants.update({"Livinginsider", "LivingInsider", "livinginsider", "LIVINGINSIDER"})
                    elif "ddproperty" in low:
                        variants.update({"DDproperty", "DDProperty", "ddproperty", "DDPROPERTY"})
                    elif "chayo" in low:
                        variants.update({"Chayo555", "Chayo", "Chayo NPA", "chayo555", "chayo"})
                    elif "kbank" in low:
                        variants.update({"KBANK", "Kbank", "kbank"})
                    elif "scb" in low:
                        variants.update({"SCB", "scb"})
                    elif "gsb" in low:
                        variants.update({"GSB", "gsb"})
                    elif "ghb" in low:
                        variants.update({"GHB", "ghb"})
                    elif "ktb" in low:
                        variants.update({"KTB", "ktb"})
                    elif "sam" in low:
                        variants.update({"SAM", "sam"})
                    elif "bam" in low:
                        variants.update({"BAM", "bam"})
                    elif "led_sold" in low or "led sold" in low or "led_legal" in low or "led legal" in low:
                        try:
                            _, _, _, a_s = square.split()
                            gray_s = square.convert("L")
                            bw_square = Image.merge("RGBA", (gray_s, gray_s, gray_s, a_s))
                            buf_s = io.BytesIO()
                            bw_square.save(buf_s, format="PNG", optimize=True)
                            b64_s = base64.b64encode(buf_s.getvalue()).decode("utf-8")
                            data_uri = f"data:image/png;base64,{b64_s}"
                        except Exception:
                            pass
                        variants.update({"LED Legal", "LED_Legal", "led legal", "led_legal", "LED_SOLD", "led_sold", "Led_Sold", "LED_sold", "LED SOLD", "led sold"})
                    elif "led" in low:
                        variants.update({"LED", "led", "Led", "LED_NPA", "led_npa"})
                        try:
                            _, _, _, a_s = square.split()
                            gray_s = square.convert("L")
                            bw_square = Image.merge("RGBA", (gray_s, gray_s, gray_s, a_s))
                            buf_s = io.BytesIO()
                            bw_square.save(buf_s, format="PNG", optimize=True)
                            b64_s = base64.b64encode(buf_s.getvalue()).decode("utf-8")
                            bw_uri = f"data:image/png;base64,{b64_s}"
                            for sv in ("LED Legal", "LED_Legal", "led legal", "led_legal", "LED_SOLD", "led_sold", "Led_Sold", "LED_sold", "LED SOLD", "led sold"):
                                if sv not in logo_dict:
                                    logo_dict[sv] = bw_uri
                        except Exception:
                            pass

                    for v in variants:
                        logo_dict[v] = data_uri
                except Exception:
                    pass

    try:
        rgba = _hex_to_rgba(c_color)
        im_b = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d_b = ImageDraw.Draw(im_b)
        bw = max(2, int(size * 0.08))
        d_b.ellipse([2, 2, size - 2, size - 2], fill=(255, 255, 255, 255), outline=rgba, width=bw)

        mid = size // 2
        sym = str(c_sym or "IMP").strip() or "IMP"
        sym_len = len(sym)
        if sym_len <= 1:
            f_sz = int(size * 0.52)
        elif sym_len == 2:
            f_sz = int(size * 0.42)
        elif sym_len == 3:
            f_sz = int(size * 0.34)
        else:
            f_sz = int(size * 0.28)
        t_font_mini = _get_badge_text_font(f_sz)
        d_b.text((mid, mid), sym, font=t_font_mini, fill=rgba, anchor="mm")

        buf_b = io.BytesIO()
        im_b.save(buf_b, format="PNG")
        b64_b = base64.b64encode(buf_b.getvalue()).decode("utf-8")
        data_uri_b = f"data:image/png;base64,{b64_b}"
        logo_dict["ไฟล์นำเข้า"] = data_uri_b
        if c_company and c_company != "(ตามข้อมูลในไฟล์)":
            logo_dict[c_company] = data_uri_b
        for c_name, c_info in custom_companies_dict.items():
            if not c_name or not isinstance(c_info, dict):
                continue
            try:
                c_hex = c_info.get("color", "#6366f1")
                c_rgba = _hex_to_rgba(c_hex)
                c_sym_item = str(c_info.get("symbol") or "IMP").strip() or "IMP"

                im_c = Image.new("RGBA", (size, size), (0, 0, 0, 0))
                d_c = ImageDraw.Draw(im_c)
                d_c.ellipse([1, 1, size - 2, size - 2], fill=(255, 255, 255, 255), outline=c_rgba, width=3)

                s_len = len(c_sym_item)
                if s_len <= 1:
                    f_sz = int(size * 0.52)
                elif s_len == 2:
                    f_sz = int(size * 0.42)
                elif s_len == 3:
                    f_sz = int(size * 0.34)
                else:
                    f_sz = int(size * 0.28)
                t_f = _get_badge_text_font(f_sz)
                d_c.text((mid, mid), c_sym_item, font=t_f, fill=c_rgba, anchor="mm")

                buf_c = io.BytesIO()
                im_c.save(buf_c, format="PNG")
                b64_c = base64.b64encode(buf_c.getvalue()).decode("utf-8")
                logo_dict[c_name] = f"data:image/png;base64,{b64_c}"
            except Exception:
                pass
    except Exception:
        pass

    with _ICON_CACHE_LOCK:
        if len(_LEAFLET_LOGO_CACHE_BY_KEY) >= _MAX_ICON_CACHE_ENTRIES:
            _LEAFLET_LOGO_CACHE_BY_KEY.popitem(last=False)
        _LEAFLET_LOGO_CACHE_BY_KEY[cache_k] = dict(logo_dict)
    return logo_dict


@st.cache_resource(show_spinner=False)
def _load_districts_geojson_strict():
    candidates = (
        os.path.join(_ROOT_DIR, "data", "districts.geojson"),
        os.path.join("data", "districts.geojson"),
    )
    path = next((p for p in candidates if os.path.exists(p)), None)
    if not path:
        raise FileNotFoundError("districts.geojson not found")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_raw_districts_geojson():
    try:
        return _load_districts_geojson_strict()
    except Exception:
        return None


@st.cache_resource(show_spinner=False)
def _load_subdistricts_geojson_strict():
    candidates = (
        os.path.join(_ROOT_DIR, "data", "subdistricts.geojson"),
        os.path.join("data", "subdistricts.geojson"),
    )
    path = next((p for p in candidates if os.path.exists(p)), None)
    if not path:
        raise FileNotFoundError("subdistricts.geojson not found")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_raw_subdistricts_geojson():
    try:
        return _load_subdistricts_geojson_strict()
    except Exception:
        return None


def _calc_polygon_centroid(geometry):
    """
    Computes an optimal interior label coordinate for a polygon/multipolygon.
    Uses Shapely centroid if safely contained inside the polygon, or representative_point
    for concave/irregular polygons (such as Khlong Toei) to prevent labels overlapping adjacent areas.
    """
    if not geometry or 'coordinates' not in geometry:
        return None
    try:
        from shapely.geometry import shape
        poly = shape(geometry)
        if not poly.is_empty:
            c = poly.centroid
            rp = poly.representative_point()
            if not poly.contains(c):
                return (round(float(rp.x), 5), round(float(rp.y), 5))
            d_c = poly.boundary.distance(c)
            d_rp = poly.boundary.distance(rp)
            if d_rp > d_c * 1.2:
                return (round(float(rp.x), 5), round(float(rp.y), 5))
            return (round(float(c.x), 5), round(float(c.y), 5))
    except Exception:
        pass

    coords = geometry['coordinates']
    lons, lats = [], []

    def _extract(c):
        if isinstance(c, (list, tuple)):
            if len(c) >= 2 and isinstance(c[0], (int, float)) and isinstance(c[1], (int, float)):
                lons.append(float(c[0]))
                lats.append(float(c[1]))
            else:
                for item in c:
                    _extract(item)

    _extract(coords)
    if lons and lats:
        avg_lon = (min(lons) + max(lons)) / 2.0
        avg_lat = (min(lats) + max(lats)) / 2.0
        return (round(avg_lon, 5), round(avg_lat, 5))
    return None


@st.cache_resource(show_spinner=False)
def _get_indexed_districts_boundaries():
    """Pre-indexes district GeoJSON features on demand with lazy centroid memoization."""
    dist_by_prov = {}
    dist_by_amp = {}
    centroid_cache = {}
    centroid_lock = threading.Lock()

    dist_data = load_raw_districts_geojson()
    if dist_data and 'features' in dist_data:
        for idx, feat in enumerate(dist_data['features']):
            props = feat.get('properties', {})
            pro_th = str(props.get('pro_th', '')).strip()
            amp_th = str(props.get('amp_th', '')).strip()
            rec = (f"d:{idx}", feat, amp_th, pro_th)
            if pro_th:
                dist_by_prov.setdefault(pro_th, []).append(rec)
            if amp_th:
                dist_by_amp.setdefault(amp_th, []).append(rec)

    return {
        "dist_by_prov": dist_by_prov,
        "dist_by_amp": dist_by_amp,
        "centroid_cache": centroid_cache,
        "centroid_lock": centroid_lock,
    }


@st.cache_resource(show_spinner=False)
def _get_indexed_subdistricts_boundaries():
    """Pre-indexes subdistrict GeoJSON features ONLY when a district/subdistrict filter is active."""
    subdist_by_tam = {}
    subdist_by_amp_prov = {}
    subdist_by_amp = {}
    centroid_cache = {}
    centroid_lock = threading.Lock()

    sd_data = load_raw_subdistricts_geojson()
    if sd_data and 'features' in sd_data:
        for idx, feat in enumerate(sd_data['features']):
            props = feat.get('properties', {})
            tam_th = str(props.get('tam_th', '')).strip()
            amp_th = str(props.get('amp_th', '')).strip()
            pro_th = str(props.get('pro_th', '')).strip()
            rec = (f"s:{idx}", feat, tam_th, amp_th, pro_th)
            if tam_th:
                subdist_by_tam.setdefault(tam_th, []).append(rec)
            if amp_th and pro_th:
                subdist_by_amp_prov.setdefault((amp_th, pro_th), []).append(rec)
            if amp_th:
                subdist_by_amp.setdefault(amp_th, []).append(rec)

    return {
        "subdist_by_tam": subdist_by_tam,
        "subdist_by_amp_prov": subdist_by_amp_prov,
        "subdist_by_amp": subdist_by_amp,
        "centroid_cache": centroid_cache,
        "centroid_lock": centroid_lock,
    }


def _get_cached_centroid(gis_idx, key, geometry):
    c_cache = gis_idx["centroid_cache"]
    if key in c_cache:
        return c_cache[key]
    val = _calc_polygon_centroid(geometry)
    with gis_idx["centroid_lock"]:
        c_cache[key] = val
    return val


def _adjust_subdistrict_label_coords(tam_th, pro_th, centroid):
    lbl_lon, lbl_lat = centroid[0], centroid[1]
    if tam_th == 'คลองเตย' and pro_th == 'กรุงเทพมหานคร' and (lbl_lon > 100.565 or lbl_lat > 13.725):
        return 100.5598, 13.71995
    return lbl_lon, lbl_lat


def get_boundary_geojson_features(prov_list=None, dist_list=None, subdist_list=None):
    """Filters pre-indexed districts or subdistricts GeoJSON to get boundary frames, dashed lines, and labels."""
    if not prov_list and not dist_list and not subdist_list:
        return None

    bare_dists = set()
    dist_prov_pairs = set()
    if dist_list:
        for d in dist_list:
            d_str = str(d).strip()
            if not d_str:
                continue
            if " (" in d_str and d_str.endswith(")"):
                d_base, p_hint = d_str[:-1].split(" (", 1)
                d_base, p_hint = d_base.strip(), p_hint.strip()
                if d_base and p_hint:
                    dist_prov_pairs.add((d_base, p_hint))
                    continue
            bare_dists.add(d_str.split(" (")[0].strip())

    clean_provs = {str(p).strip() for p in (prov_list or []) if str(p).strip()}

    bare_subdists = set()
    subdist_pairs = set()
    if subdist_list:
        for s in subdist_list:
            s_raw = str(s).strip()
            if not s_raw:
                continue
            if " (" in s_raw and s_raw.endswith(")"):
                s_base, s_hint = s_raw[:-1].split(" (", 1)
                s_base, s_hint = s_base.strip(), s_hint.strip()
                if s_base and s_hint:
                    subdist_pairs.add((s_base, s_hint))
                    continue
            bare_subdists.add(s_raw)

    has_dist_filter = bool(bare_dists or dist_prov_pairs)
    has_subdist_filter = bool(bare_subdists or subdist_pairs)

    def _dist_matches(amp_th, pro_th):
        if clean_provs and pro_th not in clean_provs:
            return False
        if (amp_th, pro_th) in dist_prov_pairs:
            return True
        return amp_th in bare_dists

    def _subdist_matches(tam_th, amp_th, pro_th):
        if clean_provs and pro_th not in clean_provs:
            return False
        if has_dist_filter and not _dist_matches(amp_th, pro_th):
            return False
        if (tam_th, amp_th) in subdist_pairs or (tam_th, pro_th) in subdist_pairs:
            return True
        return tam_th in bare_subdists

    district_labels = []

    # Case 1: Subdistrict selected (loads subdistricts GeoJSON lazily)
    if has_subdist_filter:
        sd_idx = _get_indexed_subdistricts_boundaries()
        candidate_tams = bare_subdists | {t for t, _ in subdist_pairs}
        matched = []
        seen_keys = set()
        for tam_key in candidate_tams:
            for rec_key, feat, tam_th, amp_th, pro_th in sd_idx["subdist_by_tam"].get(tam_key, ()):
                if rec_key in seen_keys:
                    continue
                if _subdist_matches(tam_th, amp_th, pro_th):
                    seen_keys.add(rec_key)
                    matched.append(feat)
                    centroid = _get_cached_centroid(sd_idx, rec_key, feat.get('geometry'))
                    if centroid:
                        lbl_lon, lbl_lat = _adjust_subdistrict_label_coords(tam_th, pro_th, centroid)
                        district_labels.append({"name": tam_th, "lon": lbl_lon, "lat": lbl_lat})
        if matched:
            return {
                "type": "FeatureCollection",
                "level": "single_subdistrict",
                "features": matched,
                "district_labels": district_labels,
            }

    # Case 2: District selected (loads subdistricts GeoJSON lazily; falls back to districts if needed)
    if has_dist_filter:
        sd_idx = _get_indexed_subdistricts_boundaries()
        matched_sd = []
        seen_sd = set()
        cand_sd_recs = []
        for pair in dist_prov_pairs:
            cand_sd_recs.extend(sd_idx["subdist_by_amp_prov"].get(pair, ()))
        for amp_k in bare_dists:
            cand_sd_recs.extend(sd_idx["subdist_by_amp"].get(amp_k, ()))

        for rec_key, feat, tam_th, amp_th, pro_th in cand_sd_recs:
            if rec_key in seen_sd:
                continue
            if _dist_matches(amp_th, pro_th):
                seen_sd.add(rec_key)
                matched_sd.append(feat)
                centroid = _get_cached_centroid(sd_idx, rec_key, feat.get('geometry'))
                if centroid:
                    lbl_lon, lbl_lat = _adjust_subdistrict_label_coords(tam_th, pro_th, centroid)
                    district_labels.append({"name": tam_th, "lon": lbl_lon, "lat": lbl_lat})
        if matched_sd:
            return {
                "type": "FeatureCollection",
                "level": "subdistrict",
                "features": matched_sd,
                "district_labels": district_labels,
            }

        dist_idx = _get_indexed_districts_boundaries()
        matched_d = []
        seen_d = set()
        cand_amps = bare_dists | {a for a, _ in dist_prov_pairs}
        for amp_k in cand_amps:
            for rec_key, feat, amp_th, pro_th in dist_idx["dist_by_amp"].get(amp_k, ()):
                if rec_key in seen_d:
                    continue
                if _dist_matches(amp_th, pro_th):
                    seen_d.add(rec_key)
                    matched_d.append(feat)
                    centroid = _get_cached_centroid(dist_idx, rec_key, feat.get('geometry'))
                    if centroid:
                        district_labels.append({"name": amp_th, "lon": centroid[0], "lat": centroid[1]})
        if matched_d:
            return {
                "type": "FeatureCollection",
                "level": "district",
                "features": matched_d,
                "district_labels": district_labels,
            }

    # Case 3: Province selected (ONLY loads districts.geojson, never touches subdistricts.geojson!)
    if clean_provs:
        dist_idx = _get_indexed_districts_boundaries()
        matched = []
        seen_d = set()
        for prov_k in clean_provs:
            for rec_key, feat, amp_th, pro_th in dist_idx["dist_by_prov"].get(prov_k, ()):
                if rec_key in seen_d:
                    continue
                seen_d.add(rec_key)
                matched.append(feat)
                centroid = _get_cached_centroid(dist_idx, rec_key, feat.get('geometry'))
                if centroid:
                    district_labels.append({"name": amp_th, "lon": centroid[0], "lat": centroid[1]})
        if matched:
            return {
                "type": "FeatureCollection",
                "level": "district",
                "features": matched,
                "district_labels": district_labels,
            }

    return None


@st.cache_resource(show_spinner=False)
def _load_official_gis_reference_strict():
    gis_candidates = (
        os.path.join(_ROOT_DIR, "references", "thailand_provinces_districts_subdistricts.json"),
        os.path.join(os.getcwd(), "references", "thailand_provinces_districts_subdistricts.json"),
    )
    gis_path = next((p for p in gis_candidates if os.path.exists(p)), None)
    if not gis_path:
        raise FileNotFoundError("thailand_provinces_districts_subdistricts.json not found")
    with open(gis_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    pairs = {
        (item['อำเภอ/เขต (ไทย)'].strip(), item['จังหวัด (ไทย)'].strip())
        for item in data
        if 'อำเภอ/เขต (ไทย)' in item and 'จังหวัด (ไทย)' in item
    }
    provs = {item['จังหวัด (ไทย)'].strip() for item in data if 'จังหวัด (ไทย)' in item}
    dists = {item['อำเภอ/เขต (ไทย)'].strip() for item in data if 'อำเภอ/เขต (ไทย)' in item}
    return pairs, provs, dists


def get_official_gis_reference():
    try:
        return _load_official_gis_reference_strict()
    except Exception:
        return set(), set(), set()
