import os
import io
import math
import base64
import datetime
import functools
import html
import pandas as pd
from PIL import Image

_ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
_TH_TZ = datetime.timezone(datetime.timedelta(hours=7))

def format_price_thai(val):
    if pd.isna(val) or val == 0:
        return "฿0 บาท"
    if val >= 1_000_000_000:
        return f"฿{val / 1_000_000_000:,.2f} พันล้าน"
    elif val >= 1_000_000:
        return f"฿{val / 1_000_000:,.1f} ล้าน"
    elif val >= 1_000:
        return f"฿{val / 1_000:,.0f} พัน"
    return f"฿{val:,.0f} บาท"

@functools.lru_cache(maxsize=64)
def get_company_logo_data_uri(comp_id):
    """Loads compact (max 128x128 PNG) base64 Data URI of official company logo case-insensitively."""
    target = str(comp_id or "").strip().lower()
    alias_targets = [target]
    if target in ("led_legal", "led_sold", "led legal"):
        alias_targets.extend(["led_legal", "led legal", "led_sold", "led"])
    elif target == "nayoo":
        alias_targets.extend(["nayoo", "nayoo logo"])
    elif target == "bam":
        alias_targets.extend(["bam", "bam logo"])

    ext_priority = ['.png', '.svg', '.webp', '.jpg', '.jpeg']
    logo_dirs = [
        os.path.join(_ROOT_DIR, 'logo', 'logos'),
        os.path.join(_ROOT_DIR, 'assets', 'logos'),
        os.path.join('logo', 'logos'),
        os.path.join('assets', 'logos'),
    ]

    for logo_dir in logo_dirs:
        if not os.path.isdir(logo_dir):
            continue
        try:
            entries = os.listdir(logo_dir)
        except OSError:
            continue
        by_stem_ext = {}
        for fn in entries:
            stem, ext = os.path.splitext(fn)
            ext_l = ext.lower()
            if ext_l in ext_priority:
                by_stem_ext[(stem.strip().lower(), ext_l)] = os.path.join(logo_dir, fn)

        for cand_t in alias_targets:
            for ext in ext_priority:
                p = by_stem_ext.get((cand_t, ext))
                if p and os.path.exists(p):
                    try:
                        if ext == '.svg':
                            with open(p, 'rb') as f:
                                b64 = base64.b64encode(f.read()).decode('utf-8')
                            return f'data:image/svg+xml;base64,{b64}'
                        # Downscale large raster logos to max 128x128 PNG (shrinks Tab 1 HTML from ~5.5 MB to <120 KB)
                        with Image.open(p) as _src_im:
                            im = _src_im.convert("RGBA")
                        bbox = im.getbbox()
                        if bbox:
                            im = im.crop(bbox)
                        im.thumbnail((128, 128), Image.Resampling.LANCZOS)
                        buf = io.BytesIO()
                        im.save(buf, format="PNG", optimize=True)
                        b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
                        return f'data:image/png;base64,{b64}'
                    except Exception:
                        try:
                            mime_map = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp'}
                            mime = mime_map.get(ext, 'image/png')
                            with open(p, 'rb') as f:
                                b64 = base64.b64encode(f.read()).decode('utf-8')
                            return f'data:{mime};base64,{b64}'
                        except Exception:
                            pass

    fallback = "data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjQiIGhlaWdodD0iMjQiIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48Y2lyY2xlIGN4PSIxMiIgY3k9IjEyIiIgcj0iMTAiIGZpbGw9IiM2NDc0OGIiLz48L3N2Zz4="
    return fallback

def generate_3d_glossy_bubble_chart_html(df_filtered, bubble_metric="สัดส่วนตามจำนวนทรัพย์สิน (Asset Count)", is_dark_mode=False):
    """
    Generates an interactive, responsive 3D Glossy Bubble Chart HTML component
    strictly divided into 4 distinct sectors across a 1680px canvas:
    1. บริษัทบริหารสินทรัพย์ (Asset Management Companies / AMC)
    2. สถาบันการเงิน / ธนาคาร (Financial Institutions / Banks)
    3. เว็บไซต์ / แพลตฟอร์มอสังหาริมทรัพย์ (Portals & Marketplaces)
    4. หน่วยงานภาครัฐ / ขายทอดตลาด (Government & Public Auction / LED)
    """
    companies_meta = [
        # ================= SECTOR 1: GOVERNMENT (หน่วยงานภาครัฐ / ทอดตลาด) =================
        {
            "id": "led",
            "name": "LED",
            "label": "LED กรมบังคับคดี",
            "sector": "gov",
            "base_cx": 143, "base_cy": 235,
            "scraped_grad": "led-scraped",
            "float_dur": "7.0s",
            "color_hex": "#0891b2"
        },
        {
            "id": "led_legal",
            "name": "LED Legal",
            "label": "LED Legal",
            "sector": "gov",
            "base_cx": 143, "base_cy": 545,
            "scraped_grad": "led-legal-scraped",
            "float_dur": "7.8s",
            "color_hex": "#475569"
        },

        # ================= SECTOR 2: AMC (บริษัทบริหารสินทรัพย์) =================
        {
            "id": "sam",
            "name": "SAM",
            "label": "SAM NPA",
            "sector": "amc",
            "base_cx": 390, "base_cy": 235,
            "scraped_grad": "sam-scraped",
            "float_dur": "8.2s",
            "color_hex": "#10b981"
        },
        {
            "id": "bam",
            "name": "BAM",
            "label": "BAM NPA",
            "sector": "amc",
            "base_cx": 390, "base_cy": 545,
            "scraped_grad": "bam-scraped",
            "float_dur": "6.0s",
            "color_hex": "#3b82f6"
        },
        {
            "id": "chayo555",
            "name": "Chayo555",
            "label": "Chayo555 NPA",
            "sector": "amc",
            "base_cx": 545, "base_cy": 385,
            "scraped_grad": "chayo555-scraped",
            "float_dur": "7.5s",
            "color_hex": "#f97316"
        },

        # ================= SECTOR 3: BANKS (สถาบันการเงิน / ธนาคาร) =================
        {
            "id": "kbank",
            "name": "KBANK",
            "label": "KBANK NPA",
            "sector": "bank",
            "base_cx": 775, "base_cy": 220,
            "scraped_grad": "kbank-scraped",
            "float_dur": "7.2s",
            "color_hex": "#059669"
        },
        {
            "id": "gsb",
            "name": "GSB",
            "label": "GSB NPA",
            "sector": "bank",
            "base_cx": 1025, "base_cy": 220,
            "scraped_grad": "gsb-scraped",
            "float_dur": "7.4s",
            "color_hex": "#eb1985"
        },
        {
            "id": "ghb",
            "name": "GHB",
            "label": "GHB NPA",
            "sector": "bank",
            "base_cx": 900, "base_cy": 385,
            "scraped_grad": "ghb-scraped",
            "float_dur": "6.8s",
            "color_hex": "#ca8a04"
        },
        {
            "id": "scb",
            "name": "SCB",
            "label": "SCB NPA",
            "sector": "bank",
            "base_cx": 775, "base_cy": 545,
            "scraped_grad": "scb-scraped",
            "float_dur": "7.0s",
            "color_hex": "#7e22ce"
        },
        {
            "id": "ktb",
            "name": "KTB",
            "label": "KTB NPA",
            "sector": "bank",
            "base_cx": 1025, "base_cy": 545,
            "scraped_grad": "ktb-scraped",
            "float_dur": "6.2s",
            "color_hex": "#0284c7"
        },

        # ================= SECTOR 4: PORTALS (เว็บไซต์ / แพลตฟอร์ม) =================
        {
            "id": "zmyhome",
            "name": "ZmyHome",
            "label": "ZmyHome NPA",
            "sector": "portal",
            "base_cx": 1275, "base_cy": 215,
            "scraped_grad": "zmyhome-scraped",
            "float_dur": "8.0s",
            "color_hex": "#ec4899"
        },
        {
            "id": "baania",
            "name": "Baania",
            "label": "Baania NPA",
            "sector": "portal",
            "base_cx": 1275, "base_cy": 550,
            "scraped_grad": "baania-scraped",
            "float_dur": "7.5s",
            "color_hex": "#f59e0b"
        },
        {
            "id": "nayoo",
            "name": "NaYoo",
            "label": "NaYoo NPA",
            "sector": "portal",
            "base_cx": 1550, "base_cy": 215,
            "scraped_grad": "nayoo-scraped",
            "float_dur": "6.5s",
            "color_hex": "#8b5cf6"
        },
        {
            "id": "ddproperty",
            "name": "DDproperty",
            "label": "DDproperty",
            "sector": "portal",
            "base_cx": 1550, "base_cy": 555,
            "scraped_grad": "ddproperty-scraped",
            "float_dur": "7.2s",
            "color_hex": "#a855f7"
        },
        {
            "id": "livinginsider",
            "name": "Livinginsider",
            "label": "Livinginsider",
            "sector": "portal",
            "base_cx": 1412, "base_cy": 380,
            "scraped_grad": "livinginsider-scraped",
            "float_dur": "6.8s",
            "color_hex": "#14b8a6"
        }
    ]

    total_market_count = len(df_filtered) if df_filtered is not None else 0
    if df_filtered is not None and not df_filtered.empty and 'ราคา' in df_filtered.columns:
        _all_p = pd.to_numeric(df_filtered['ราคา'], errors='coerce')
        valid_prices = _all_p[_all_p > 0]
        total_market_val = float(valid_prices.sum()) if not valid_prices.empty else 0.0
    else:
        total_market_val = 0.0

    is_count_metric = ("จำนวน" in str(bubble_metric))

    # Calculate 4 sector-level aggregates with Government on the leftmost position
    # Unified SAM Green Theme for all sector pods (no multi-colored borders)
    theme_accent = "#10b981" if is_dark_mode else "#047857"
    theme_border = "rgba(16, 185, 129, 0.25)" if is_dark_mode else "rgba(4, 120, 87, 0.22)"
    theme_tint = "rgba(17, 40, 32, 0.45)" if is_dark_mode else "rgba(244, 248, 246, 0.55)"
    theme_glow = "rgba(16, 185, 129, 0.15)" if is_dark_mode else "rgba(4, 120, 87, 0.12)"

    sector_meta = {
        "gov": {
            "title": "หน่วยงานภาครัฐ",
            "subtitle": "Government & Public Auction",
            "icon": "",
            "color": theme_accent,
            "glow": theme_glow,
            "bg_border": theme_border,
            "bg_tint": theme_tint,
            "x": 8, "y": 36, "w": 270, "h": 710,
            "count": 0, "val": 0.0
        },
        "amc": {
            "title": "บริษัทบริหารสินทรัพย์",
            "subtitle": "Asset Management (AMC)",
            "icon": "",
            "color": theme_accent,
            "glow": theme_glow,
            "bg_border": theme_border,
            "bg_tint": theme_tint,
            "x": 286, "y": 36, "w": 360, "h": 710,
            "count": 0, "val": 0.0
        },
        "bank": {
            "title": "สถาบันการเงิน",
            "subtitle": "Banks & Financial Institutions",
            "icon": "",
            "color": theme_accent,
            "glow": theme_glow,
            "bg_border": theme_border,
            "bg_tint": theme_tint,
            "x": 654, "y": 36, "w": 490, "h": 710,
            "count": 0, "val": 0.0
        },
        "portal": {
            "title": "เว็บไซต์สื่อกลาง",
            "subtitle": "Portals & Marketplaces",
            "icon": "",
            "color": theme_accent,
            "glow": theme_glow,
            "bg_border": theme_border,
            "bg_tint": theme_tint,
            "x": 1152, "y": 36, "w": 520, "h": 710,
            "count": 0, "val": 0.0
        }
    }

    # Aggregate company stats in one fast categorical pass (avoids unpacking 461k object strings in RAM)
    def _norm_co_key(k):
        s = str(k).strip()
        return 'LED Legal' if s in ('LED_SOLD', 'LED_Legal', 'LED Legal') else s

    comp_stats = {}
    if df_filtered is not None and not df_filtered.empty and 'บริษัท' in df_filtered.columns:
        co_col = df_filtered['บริษัท']
        prices_num = pd.to_numeric(df_filtered['ราคา'], errors='coerce') if 'ราคา' in df_filtered.columns else pd.Series(float('nan'), index=df_filtered.index)
        pos_prices = prices_num.where(prices_num > 0)
        if 'ราคาขายได้' in df_filtered.columns:
            legal_m = co_col.isin(['LED Legal', 'LED_Legal', 'LED_SOLD'])
            if legal_m.any():
                sold_num = pd.to_numeric(df_filtered.loc[legal_m, 'ราคาขายได้'], errors='coerce')
                pos_prices = pos_prices.copy()
                pos_prices.loc[legal_m] = sold_num.where(sold_num > 0).fillna(pos_prices.loc[legal_m])

        co_counts_map = {}
        for k, v in co_col.value_counts().items():
            nk = _norm_co_key(k)
            co_counts_map[nk] = co_counts_map.get(nk, 0) + int(v)

        co_sums_map = {}
        for k, v in pos_prices.groupby(co_col, observed=True).sum().items():
            nk = _norm_co_key(k)
            co_sums_map[nk] = co_sums_map.get(nk, 0.0) + (float(v) if pd.notna(v) else 0.0)

        if co_sums_map:
            total_market_val = float(sum(float(v) for v in co_sums_map.values() if pd.notna(v) and v > 0))
        # Centroid counts per company (safe for both bool and string 'False' columns)
        if 'is_centroid' in df_filtered.columns:
            c_col = df_filtered['is_centroid']
            if pd.api.types.is_bool_dtype(c_col.dtype):
                centroid_mask = c_col.fillna(False).astype(bool)
            else:
                centroid_mask = c_col.astype(object).fillna('').astype(str).str.strip().str.lower().isin({'true', '1', '1.0', 'yes', 't'})
            co_centroid_map = {}
            for k, v in co_col[centroid_mask].value_counts().items():
                nk = _norm_co_key(k)
                co_centroid_map[nk] = co_centroid_map.get(nk, 0) + int(v)
        else:
            co_centroid_map = {}
    else:
        co_counts_map, co_sums_map, co_centroid_map = {}, {}, {}

    # Extract company scraping/extraction dates (dedup unique date strings per company; KEEP min() business convention!)
    thai_short_m = ['ม.ค.', 'ก.พ.', 'มี.ค.', 'เม.ย.', 'พ.ค.', 'มิ.ย.', 'ก.ค.', 'ส.ค.', 'ก.ย.', 'ต.ค.', 'พ.ย.', 'ธ.ค.']
    co_dates_map = {}
    if df_filtered is not None and not df_filtered.empty and 'วันที่ดึงข้อมูล' in df_filtered.columns and 'บริษัท' in df_filtered.columns:
        try:
            from modules.services.data_cleaner import _parse_announcement_date
            _dt_vc = df_filtered.groupby(['บริษัท', 'วันที่ดึงข้อมูล'], observed=True).size()
            _dt_vc = _dt_vc[_dt_vc > 0]
            _parsed_lut = {}
            _co_dt_buckets = {}
            for (raw_co, raw_dt), _ in _dt_vc.items():
                _sv = str(raw_dt).strip()
                if not _sv or _sv in ('', 'nan', 'None', '-', '<NA>', 'NaT'):
                    continue
                if raw_dt not in _parsed_lut:
                    _d_obj, _ = _parse_announcement_date(_sv)
                    _parsed_lut[raw_dt] = _d_obj
                _d_obj = _parsed_lut[raw_dt]
                if _d_obj is not None:
                    nk = _norm_co_key(raw_co)
                    _co_dt_buckets.setdefault(nk, []).append(_d_obj)
            for c_key, parsed_list in _co_dt_buckets.items():
                if parsed_list:
                    min_d = min(parsed_list)
                    m_str = thai_short_m[min_d.month - 1]
                    y_short = (min_d.year + 543) % 100 if min_d.year < 2500 else min_d.year % 100
                    co_dates_map[str(c_key)] = f"{min_d.day} {m_str} {y_short}"
        except Exception:
            pass

    # Dynamic extraction of sale month for LED Legal (deduped & BE-safe)
    led_sold_month_num = "9-10"
    if df_filtered is not None and not df_filtered.empty and 'วันที่ขาย' in df_filtered.columns and 'บริษัท' in df_filtered.columns:
        try:
            from modules.services.data_cleaner import parse_sold_date_value
            ls_mask = df_filtered['บริษัท'].isin(['LED Legal', 'LED_Legal', 'LED_SOLD'])
            u_sales = df_filtered.loc[ls_mask, 'วันที่ขาย'].dropna().unique()
            months_set = set()
            for raw_s in u_sales:
                ts = parse_sold_date_value(raw_s)
                if pd.notna(ts):
                    months_set.add(int(ts.month))
            if months_set:
                m_unique = sorted(months_set)
                led_sold_month_num = f"{m_unique[0]}-{m_unique[-1]}" if len(m_unique) > 1 else f"{m_unique[0]}"
        except Exception:
            pass

    now_dt = datetime.datetime.now(_TH_TZ)
    default_short_date = f"{now_dt.day} {thai_short_m[now_dt.month - 1]} {(now_dt.year + 543) % 100}"
    FALLBACK_COMPANY_DATES = {comp["name"]: default_short_date for comp in companies_meta}

    for comp in companies_meta:
        comp_name = comp["name"]
        c_count = co_counts_map.get(comp_name, 0)
        c_val = co_sums_map.get(comp_name, 0.0)
        c_centroid = co_centroid_map.get(comp_name, 0)
        
        comp_stats[comp["id"]] = {
            "count": c_count,
            "val": c_val,
            "centroid": c_centroid
        }
        
        sec = comp["sector"]
        if sec in sector_meta:
            sector_meta[sec]["count"] += c_count
            sector_meta[sec]["val"] += c_val

    bubbles_html_list = []
    bubble_clip_defs = []
    keyframes_list = []
    hover_classes_list = []

    for comp in companies_meta:
        comp_name = comp["name"]
        st_data = comp_stats.get(comp["id"], {"count": 0, "val": 0.0, "centroid": 0})
        c_count = st_data["count"]
        if c_count == 0:
            continue

        c_val = st_data["val"]
        c_centroid = st_data.get("centroid", 0)
        
        pct_count = (c_count / total_market_count * 100) if total_market_count > 0 else 0.0
        pct_val = (c_val / total_market_val * 100) if total_market_val > 0 else 0.0
        
        active_pct = pct_count if is_count_metric else pct_val
        active_fraction = active_pct / 100.0
        
        if active_fraction > 0:
            radius = int(60 + 68 * math.sqrt(active_fraction))
            radius = max(60, min(118, radius))
        else:
            radius = 60

        cx, cy = comp["base_cx"], comp["base_cy"]
        bubble_id = f"bubble-{comp['id']}"

        # Outer bubble slice & shadow
        slices = f'<g filter="url(#shadow)"><circle cx="{cx}" cy="{cy}" r="{radius}" fill="url(#{comp["scraped_grad"]})" stroke="rgba(255, 255, 255, 0.7)" stroke-width="2.5" /></g>'
        sheen = f'<circle cx="{cx}" cy="{cy}" r="{radius}" fill="none" stroke="rgba(255, 255, 255, 0.45)" stroke-width="2.5" />'
        
        hcx = cx - radius * 0.35
        hcy = cy - radius * 0.35
        hrx = radius * 0.4
        hry = radius * 0.25
        highlight = f'<ellipse cx="{hcx}" cy="{hcy}" rx="{hrx}" ry="{hry}" fill="url(#highlight-grad)" transform="rotate(-30, {hcx}, {hcy})" />'

        # Pure Native SVG interior (100% immune to iPadOS WebKit <foreignObject> scaling & compositing bugs)
        logo_badge_r = max(18.0, min(26.0, radius * 0.21))
        logo_img_sz = (logo_badge_r - 3.0) * 1.75
        logo_data_uri = get_company_logo_data_uri(comp["id"])
        clip_id = f"clip-logo-{comp['id']}"
        bubble_clip_defs.append(
            f'<clipPath id="{clip_id}"><circle cx="{cx}" cy="{{LOGO_CY}}" r="{logo_badge_r - 2.0:.1f}" /></clipPath>'
        )

        title_size = max(12.0, min(18.5, radius * 0.158))
        stat_label_size = max(8.5, min(11.5, radius * 0.098))
        stat_val_size = max(9.2, min(12.6, radius * 0.108))
        pill_h = max(14.5, min(20.0, radius * 0.172))
        pill_gap = max(2.2, min(3.8, radius * 0.032))
        gap_logo_title = max(3.5, radius * 0.045)
        gap_title_pills = max(3.5, radius * 0.045)

        card_bg_color = "rgba(15, 23, 42, 0.78)" if is_dark_mode else "rgba(255, 255, 255, 0.88)"
        card_stroke_color = "rgba(255, 255, 255, 0.35)" if is_dark_mode else "rgba(255, 255, 255, 0.75)"
        text_title_color = "#f8fafc" if is_dark_mode else "#0f172a"
        text_sub_color = "#cbd5e1" if is_dark_mode else "#475569"
        text_val_color = "#ffffff" if is_dark_mode else "#0f172a"
        pct_accent_color = "#34d399" if is_dark_mode else "#047857"

        comp_date_str = co_dates_map.get(comp_name) or FALLBACK_COMPANY_DATES.get(comp_name, "-")

        if comp["id"] in ("led_legal", "led_sold"):
            date_badge_label = "เดือน"
            date_badge_val = led_sold_month_num
        else:
            date_badge_label = "ดึงข้อมูล"
            date_badge_val = comp_date_str

        val_str = format_price_thai(c_val)
        pills_spec = [
            (
                "ทรัพย์สิน",
                f"{c_count:,}",
                f" ({pct_count:.1f}%)",
                card_bg_color,
                card_stroke_color,
                text_sub_color,
                text_val_color,
                pct_accent_color,
            ),
            (
                "มูลค่า",
                val_str,
                "",
                card_bg_color,
                card_stroke_color,
                text_sub_color,
                text_val_color,
                "",
            ),
            (
                date_badge_label,
                str(date_badge_val),
                "",
                card_bg_color,
                card_stroke_color,
                text_sub_color,
                text_val_color,
                "",
            ),
        ]
        if c_centroid > 0:
            pills_spec.append(
                (
                    "△ กึ่งกลาง",
                    f"{c_centroid:,}",
                    "",
                    "rgba(254, 243, 199, 0.96)",
                    "#fde68a",
                    "#b45309",
                    "#92400e",
                    "",
                )
            )

        n_pills = len(pills_spec)
        total_stack_h = (
            (logo_badge_r * 2.0)
            + gap_logo_title
            + title_size
            + gap_title_pills
            + (n_pills * pill_h)
            + (max(0, n_pills - 1) * pill_gap)
        )
        # Keep stack comfortably inside circle if 4 pills on smaller bubble
        max_inner_h = radius * 1.82
        if total_stack_h > max_inner_h:
            scale_y = max_inner_h / total_stack_h
            logo_badge_r *= scale_y
            logo_img_sz = (logo_badge_r - 2.5) * 1.75
            title_size *= scale_y
            stat_label_size *= scale_y
            stat_val_size *= scale_y
            pill_h *= scale_y
            pill_gap *= scale_y
            gap_logo_title *= scale_y
            gap_title_pills *= scale_y
            total_stack_h = max_inner_h

        top_y = cy - (total_stack_h / 2.0)
        logo_cy = top_y + logo_badge_r
        title_y = logo_cy + logo_badge_r + gap_logo_title + (title_size * 0.5)
        first_pill_cy = title_y + (title_size * 0.5) + gap_title_pills + (pill_h * 0.5)

        # Patch clipPath cy now that final logo_cy is known
        bubble_clip_defs[-1] = (
            f'<clipPath id="{clip_id}"><circle cx="{cx}" cy="{logo_cy:.1f}" r="{max(8.0, logo_badge_r - 2.0):.1f}" /></clipPath>'
        )

        pills_svg_parts = []
        for p_idx, (lbl, val, pct_s, bg_c, st_c, lbl_c, val_c, pct_c) in enumerate(pills_spec):
            py = first_pill_cy + p_idx * (pill_h + pill_gap)
            dy = abs(py - cy)
            max_chord = max(radius * 0.7, 2.0 * math.sqrt(max(0.0, radius * radius - dy * dy)) - 10.0)
            plain_len = len(lbl) + 1 + len(val) + len(pct_s)
            est_w = plain_len * (stat_val_size * 0.56) + 16.0
            pill_w = min(max_chord, max(radius * 0.85, est_w))
            safe_lbl = html.escape(lbl, quote=True)
            safe_val = html.escape(val, quote=True)
            safe_pct = html.escape(pct_s, quote=True)
            pct_tspan = (
                f'<tspan fill="{pct_c}" font-weight="700" font-size="{stat_val_size:.1f}">{safe_pct}</tspan>'
                if safe_pct
                else ""
            )
            pills_svg_parts.append(
                f'<rect x="{cx - pill_w / 2.0:.1f}" y="{py - pill_h / 2.0:.1f}" '
                f'width="{pill_w:.1f}" height="{pill_h:.1f}" rx="{pill_h / 2.0:.1f}" '
                f'fill="{bg_c}" stroke="{st_c}" stroke-width="1" />'
                f'<text x="{cx}" y="{py:.1f}" text-anchor="middle" dominant-baseline="central" '
                f'font-family="Outfit, Sarabun, Noto Sans Thai, sans-serif">'
                f'<tspan fill="{lbl_c}" font-weight="600" font-size="{stat_label_size:.1f}">{safe_lbl} </tspan>'
                f'<tspan fill="{val_c}" font-weight="800" font-size="{stat_val_size:.1f}">{safe_val}</tspan>'
                f'{pct_tspan}</text>'
            )

        safe_comp_title = html.escape(comp["name"].upper(), quote=True)
        bubble_body = f"""
            <g class="bubble-group sector-bubble sector-{comp['sector']}" id="{bubble_id}">
                {slices}
                {sheen}
                {highlight}
                <g pointer-events="none">
                    <circle cx="{cx}" cy="{logo_cy:.1f}" r="{logo_badge_r:.1f}" fill="rgba(255, 255, 255, 0.96)" stroke="#ffffff" stroke-width="2" filter="url(#badge-shadow)" />
                    <image href="{logo_data_uri}" x="{cx - logo_img_sz / 2.0:.1f}" y="{logo_cy - logo_img_sz / 2.0:.1f}" width="{logo_img_sz:.1f}" height="{logo_img_sz:.1f}" preserveAspectRatio="xMidYMid meet" clip-path="url(#{clip_id})" />
                    <text x="{cx}" y="{title_y:.1f}" text-anchor="middle" dominant-baseline="central" font-family="Outfit, Sarabun, Noto Sans Thai, sans-serif" font-weight="800" font-size="{title_size:.1f}" fill="{text_title_color}" letter-spacing="-0.3">{safe_comp_title}</text>
                    {''.join(pills_svg_parts)}
                </g>
            </g>
        """

        bubbles_html_list.append(f"""
        <g class="float-wrapper float-{bubble_id}">
            {bubble_body}
        </g>
        """)

        hover_classes_list.append(f"#{bubble_id} {{ transform-origin: {cx}px {cy}px; }}")
        
        anim_name = f"float-{comp['id']}-anim"
        dx = 3 if comp["base_cx"] > 800 else -3
        dy = -5 if comp["base_cy"] > 350 else 5
        keyframes_list.append(f"""
        @keyframes {anim_name} {{
            0% {{ transform: translate(0px, 0px); }}
            50% {{ transform: translate({dx}px, {dy}px); }}
            100% {{ transform: translate(0px, 0px); }}
        }}
        .float-{bubble_id} {{
            animation: {anim_name} {comp['float_dur']} ease-in-out infinite;
        }}
        """)

    # Build 4 Sector Backdrop Panels (Pods) using Pure Native SVG headers (zero <foreignObject>)
    sector_pods_svg = []
    for s_key, s_data in sector_meta.items():
        s_cnt = s_data["count"]
        s_val = s_data["val"]
        s_pct_cnt = (s_cnt / total_market_count * 100) if total_market_count > 0 else 0.0
        s_pct_val = (s_val / total_market_val * 100) if total_market_val > 0 else 0.0
        
        stat_display = f"{s_cnt:,} รายการ ({s_pct_cnt:.1f}%)" if is_count_metric else f"{format_price_thai(s_val)} ({s_pct_val:.1f}%)"
        
        bg_card = "rgba(17, 40, 32, 0.92)" if is_dark_mode else "rgba(255, 255, 255, 0.96)"
        title_c = "#f8fafc" if is_dark_mode else "#0f172a"
        border_c = s_data["bg_border"]
        hdr_cx = s_data["x"] + (s_data["w"] / 2.0)
        hdr_cy = s_data["y"] + 8.0
        est_hdr_w = max(len(s_data["title"]) * 8.2, len(stat_display) * 6.4) + 34.0
        hdr_w = min(s_data["w"] - 20.0, max(168.0, est_hdr_w))
        hdr_h = 40.0
        safe_s_title = html.escape(s_data["title"], quote=True)
        safe_s_stat = html.escape(stat_display, quote=True)

        pod_svg = f"""
        <g class="sector-pod-group sector-pod-{s_key}" id="pod-{s_key}">
            <!-- Glassmorphic Pod Container Box -->
            <rect x="{s_data['x']}" y="{s_data['y']}" width="{s_data['w']}" height="{s_data['h']}" rx="24" ry="24" 
                  fill="{s_data['bg_tint']}" stroke="{border_c}" stroke-width="1.5" stroke-dasharray="none" />
                  
            <!-- Top Sector Header Pill (Pure SVG) -->
            <g filter="url(#badge-shadow)">
                <rect x="{hdr_cx - hdr_w / 2.0:.1f}" y="{hdr_cy - hdr_h / 2.0:.1f}" width="{hdr_w:.1f}" height="{hdr_h:.1f}" rx="20" ry="20"
                      fill="{bg_card}" stroke="{s_data['color']}" stroke-width="1.5" />
            </g>
            <text x="{hdr_cx:.1f}" y="{hdr_cy - 6.5:.1f}" text-anchor="middle" dominant-baseline="central"
                  font-family="Outfit, Sarabun, Noto Sans Thai, sans-serif" font-weight="800" font-size="13" fill="{title_c}" letter-spacing="-0.2">{safe_s_title}</text>
            <text x="{hdr_cx:.1f}" y="{hdr_cy + 9.0:.1f}" text-anchor="middle" dominant-baseline="central"
                  font-family="Outfit, Sarabun, Noto Sans Thai, sans-serif" font-weight="700" font-size="10.5" fill="{s_data['color']}">{safe_s_stat}</text>
        </g>
        """
        sector_pods_svg.append(pod_svg)

    svg_content = f"""
    <svg viewBox="0 0 1680 770" width="100%" preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg" style="background-color: transparent; width: 100%; height: auto; max-height: 820px; display: block;">
      <defs>
        <filter id="shadow" x="-30%" y="-30%" width="160%" height="160%">
          <feDropShadow dx="0" dy="8" stdDeviation="12" flood-color="#0f172a" flood-opacity="{'0.35' if is_dark_mode else '0.15'}"/>
        </filter>
        <filter id="badge-shadow" x="-25%" y="-25%" width="150%" height="150%">
          <feDropShadow dx="0" dy="3" stdDeviation="4" flood-color="#0f172a" flood-opacity="{'0.35' if is_dark_mode else '0.14'}"/>
        </filter>
        {''.join(bubble_clip_defs)}
        
        <linearGradient id="highlight-grad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="rgba(255, 255, 255, 0.75)"/>
          <stop offset="100%" stop-color="rgba(255, 255, 255, 0)"/>
        </linearGradient>
        
        <!-- LED Radial Gradient (Cyan/Teal) -->
        <radialGradient id="led-scraped" cx="50%" cy="50%" r="50%" fx="35%" fy="30%">
          <stop offset="0%" stop-color="#ecfeff"/>
          <stop offset="45%" stop-color="#22d3ee"/>
          <stop offset="100%" stop-color="#0891b2"/>
        </radialGradient>

        <!-- LED Legal & SOLD Radial Gradient (Slate / Charcoal) -->
        <radialGradient id="led-legal-scraped" cx="50%" cy="50%" r="50%" fx="35%" fy="30%">
          <stop offset="0%" stop-color="#f8fafc"/>
          <stop offset="45%" stop-color="#64748b"/>
          <stop offset="100%" stop-color="#334155"/>
        </radialGradient>
        <radialGradient id="led-sold-scraped" cx="50%" cy="50%" r="50%" fx="35%" fy="30%">
          <stop offset="0%" stop-color="#f8fafc"/>
          <stop offset="45%" stop-color="#64748b"/>
          <stop offset="100%" stop-color="#334155"/>
        </radialGradient>

        <!-- NaYoo Radial Gradients (Purple/Violet) -->
        <radialGradient id="nayoo-scraped" cx="50%" cy="50%" r="50%" fx="35%" fy="30%">
          <stop offset="0%" stop-color="#faf5ff"/>
          <stop offset="45%" stop-color="#c084fc"/>
          <stop offset="100%" stop-color="#7e22ce"/>
        </radialGradient>
        
        <!-- ZmyHome Radial Gradients (Pink/Rose) -->
        <radialGradient id="zmyhome-scraped" cx="50%" cy="50%" r="50%" fx="38%" fy="35%">
          <stop offset="0%" stop-color="#fff1f5"/>
          <stop offset="45%" stop-color="#f472b6"/>
          <stop offset="100%" stop-color="#be185d"/>
        </radialGradient>
        
        <!-- BAM Radial Gradients (Blue/Gold) -->
        <radialGradient id="bam-scraped" cx="50%" cy="50%" r="50%" fx="35%" fy="30%">
          <stop offset="0%" stop-color="#eff6ff"/>
          <stop offset="45%" stop-color="#60a5fa"/>
          <stop offset="100%" stop-color="#1d4ed8"/>
        </radialGradient>
        
        <!-- Baania Radial Gradients (Amber/Gold) -->
        <radialGradient id="baania-scraped" cx="50%" cy="50%" r="50%" fx="35%" fy="30%">
          <stop offset="0%" stop-color="#fffdf5"/>
          <stop offset="45%" stop-color="#fbbf24"/>
          <stop offset="100%" stop-color="#d97706"/>
        </radialGradient>
        
        <!-- SAM Radial Gradients (Emerald/Teal) -->
        <radialGradient id="sam-scraped" cx="50%" cy="50%" r="50%" fx="35%" fy="30%">
          <stop offset="0%" stop-color="#f0fdf4"/>
          <stop offset="45%" stop-color="#34d399"/>
          <stop offset="100%" stop-color="#047857"/>
        </radialGradient>

        <!-- Chayo555 Radial Gradients (Orange/Coral) -->
        <radialGradient id="chayo555-scraped" cx="50%" cy="50%" r="50%" fx="35%" fy="30%">
          <stop offset="0%" stop-color="#fff7ed"/>
          <stop offset="45%" stop-color="#fb923c"/>
          <stop offset="100%" stop-color="#ea580c"/>
        </radialGradient>

        <!-- KBANK Standalone Gradient (Green) -->
        <radialGradient id="kbank-scraped" cx="50%" cy="50%" r="50%" fx="35%" fy="30%">
          <stop offset="0%" stop-color="#ecfdf5"/>
          <stop offset="45%" stop-color="#34d399"/>
          <stop offset="100%" stop-color="#059669"/>
        </radialGradient>

        <!-- GHB Standalone Gradient (Gold/Yellow) -->
        <radialGradient id="ghb-scraped" cx="50%" cy="50%" r="50%" fx="35%" fy="30%">
          <stop offset="0%" stop-color="#fefce8"/>
          <stop offset="45%" stop-color="#fde047"/>
          <stop offset="100%" stop-color="#ca8a04"/>
        </radialGradient>

        <!-- SCB Standalone Gradient (Royal Purple) -->
        <radialGradient id="scb-scraped" cx="50%" cy="50%" r="50%" fx="35%" fy="30%">
          <stop offset="0%" stop-color="#faf5ff"/>
          <stop offset="45%" stop-color="#a855f7"/>
          <stop offset="100%" stop-color="#6b21a8"/>
        </radialGradient>

        <!-- KTB Standalone Gradient (Sky Blue) -->
        <radialGradient id="ktb-scraped" cx="50%" cy="50%" r="50%" fx="35%" fy="30%">
          <stop offset="0%" stop-color="#f0f9ff"/>
          <stop offset="45%" stop-color="#38bdf8"/>
          <stop offset="100%" stop-color="#0284c7"/>
        </radialGradient>

        <!-- GSB Standalone Gradient (Vivid Pink) -->
        <radialGradient id="gsb-scraped" cx="50%" cy="50%" r="50%" fx="35%" fy="30%">
          <stop offset="0%" stop-color="#fdf2f8"/>
          <stop offset="45%" stop-color="#f472b6"/>
          <stop offset="100%" stop-color="#db2777"/>
        </radialGradient>

        <!-- DDproperty Standalone Gradient (Purple/Violet) -->
        <radialGradient id="ddproperty-scraped" cx="50%" cy="50%" r="50%" fx="35%" fy="30%">
          <stop offset="0%" stop-color="#faf5ff"/>
          <stop offset="45%" stop-color="#c084fc"/>
          <stop offset="100%" stop-color="#9333ea"/>
        </radialGradient>

        <!-- Livinginsider Standalone Gradient (Teal) -->
        <radialGradient id="livinginsider-scraped" cx="50%" cy="50%" r="50%" fx="35%" fy="30%">
          <stop offset="0%" stop-color="#f0fdfa"/>
          <stop offset="45%" stop-color="#2dd4bf"/>
          <stop offset="100%" stop-color="#0d9488"/>
        </radialGradient>
      </defs>
      
      <!-- 4 Sector Glass Pods in Background -->
      {''.join(sector_pods_svg)}

      <!-- 3D Bubbles on Top of Pods -->
      {''.join(bubbles_html_list)}
    </svg>
    """

    hover_css = "\n".join(hover_classes_list)
    keyframes_css = "\n".join(keyframes_list)

    displayed_sector_cnt = sum(s["count"] for s in sector_meta.values())
    displayed_sector_val = sum(s["val"] for s in sector_meta.values())
    extra_cnt = max(0, int(total_market_count) - int(displayed_sector_cnt))
    extra_val = max(0.0, float(total_market_val) - float(displayed_sector_val))
    extra_note_html = ""
    if extra_cnt > 0:
        known_names = {c["name"] for c in companies_meta}
        extra_cos = sorted(str(k) for k, v in co_counts_map.items() if v > 0 and k not in known_names)
        extra_co_list = ", ".join(html.escape(c, quote=True) for c in extra_cos[:5]) + (" ..." if len(extra_cos) > 5 else "")
        note_bg = "rgba(30, 41, 59, 0.72)" if is_dark_mode else "rgba(241, 245, 249, 0.9)"
        note_fg = "#cbd5e1" if is_dark_mode else "#334155"
        note_bd = "rgba(148, 163, 184, 0.25)" if is_dark_mode else "rgba(148, 163, 184, 0.35)"
        extra_note_html = (
            f'<div style="margin-top:6px; padding:6px 14px; border-radius:9999px; background:{note_bg}; '
            f'border:1px solid {note_bd}; color:{note_fg}; font-family:\'Outfit\',\'Sarabun\',sans-serif; '
            f'font-size:12px; font-weight:600;">'
            f'+ ข้อมูลเพิ่มเติม/นำเข้านอกกลุ่ม 15 บริษัทหลัก ({extra_co_list}): '
            f'<b>{extra_cnt:,}</b> รายการ ({format_price_thai(extra_val)})</div>'
        )

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;600;700;800;900&family=Sarabun:wght@400;600;700;800&display=swap" rel="stylesheet">
    <style>
        * {{
            box-sizing: border-box;
            font-family: 'Outfit', 'Sarabun', 'Noto Sans Thai', 'Segoe UI', Tahoma, sans-serif;
        }}
        html, body {{
            margin: 0;
            padding: 0px 4px 16px 4px;
            background: transparent;
            overflow: hidden;
            width: 100%;
            height: auto;
            user-select: none;
            display: flex;
            flex-direction: column;
            align-items: center;
        }}
        .chart-container {{
            width: 100%;
            display: flex;
            justify-content: center;
            align-items: center;
            margin: 0 auto;
        }}
        svg {{
            width: 100%;
            height: auto;
            max-height: 820px;
            display: block;
            overflow: visible;
        }}
        .bubble-group {{
            cursor: pointer;
            transition: transform 0.4s cubic-bezier(0.34, 1.56, 0.64, 1), filter 0.3s ease, opacity 0.3s ease;
        }}
        .bubble-group:hover {{
            transform: scale(1.08);
            filter: brightness(1.08) drop-shadow(0 15px 25px rgba(0,0,0,0.25));
        }}
        .sector-pod-group {{
            transition: opacity 0.35s ease, transform 0.35s ease;
        }}
        {hover_css}
        {keyframes_css}
    </style>
    </head>
    <body>
        <div class="chart-container">
            {svg_content}
        </div>
        {extra_note_html}
    </body>
    </html>
    """
    return html_content

