import hashlib
import html
import io
import re
import zipfile
import pandas as pd
import streamlit as st

from modules.config.constants import COMPANY_COLORS
from modules.services.data_cleaner import (
    combine_split_land_area_columns,
    detect_split_land_area_columns,
    format_coord_vectorized,
)

_SAFE_HEX_COLOR_RE = re.compile(r'^#[0-9a-fA-F]{6}$')
_CSV_RNW_EXACT_RE = re.compile(r'^[ \t]*="\d+-\d+-\d+(?:\.\d+)?"$')
_SAFE_DASH_RE = re.compile(r'^ *-$')
_DANGEROUS_LEAD_RE = re.compile(r'^(?:[\t\r\n]|[ \t\r\n]*[=+\-@])')
_FILENAME_UNSAFE_RE = re.compile(r'[\\/:*?"<>|\s]+')

MAX_UPLOAD_BYTES = 200 * 1024 * 1024  # 200 MB
MAX_UPLOAD_ROWS = 300_000
MAX_XLSX_UNCOMPRESSED_BYTES = 1024 * 1024 * 1024  # 1 GB
MAX_XLSX_COMPRESSION_RATIO = 100.0
MAX_XLSX_ENTRIES = 2000
MAX_NEW_COMPANIES_PER_UPLOAD = 50
EXCEL_MAX_DATA_ROWS = 1_048_575


def _safe_hex_color(val, default="#6366f1"):
    s = str(val or "").strip()
    return s if _SAFE_HEX_COLOR_RE.match(s) else default


def _sanitize_filename_prefix(prefix, default="npa_data"):
    cleaned = _FILENAME_UNSAFE_RE.sub("_", str(prefix or "")).strip("._")
    return cleaned[:100] if cleaned else default


def _sanitize_spreadsheet_text(val, allow_csv_rnw=False):
    if not isinstance(val, str) or not val:
        return val
    # Guard leading control characters BEFORE lstrip()
    if val[0] in ('\t', '\r', '\n'):
        return "'" + val
    if _SAFE_DASH_RE.match(val):
        return val
    stripped = val.lstrip()
    if not stripped:
        return val
    # Preserve intentional Excel text formatting for Thai Rai-Ngan-Wah notation e.g. ="1-2-30" in CSV
    if allow_csv_rnw and _CSV_RNW_EXACT_RE.match(val):
        return val
    if stripped[0] in ('=', '+', '-', '@'):
        return "'" + val
    return val


def _sanitize_csv_text(val):
    return _sanitize_spreadsheet_text(val, allow_csv_rnw=True)


def _invalidate_imported_view_caches():
    for k in (
        "_merged_df_cache_key",
        "_merged_df_cache",
        "cached_map_html_base",
        "_tab2_custom_map_cache",
        "_custom_import_fp",
    ):
        st.session_state.pop(k, None)
    st.session_state["_custom_import_ver"] = int(st.session_state.get("_custom_import_ver", 0)) + 1


def _sync_legacy_custom_keys():
    """Keep legacy single-company session keys aligned after add/delete."""
    all_saved_cos = st.session_state.get("imported_custom_companies")
    if isinstance(all_saved_cos, dict) and all_saved_cos:
        first_co_name = next(iter(all_saved_cos))
        first_co_conf = all_saved_cos[first_co_name] or {}
        st.session_state["imported_custom_company"] = first_co_name
        st.session_state["imported_custom_company_label"] = first_co_name
        st.session_state["imported_custom_symbol"] = first_co_conf.get("symbol", "CST")
        st.session_state["imported_custom_color"] = first_co_conf.get("color", "#6366f1")
    else:
        for k in (
            "imported_custom_companies",
            "imported_custom_company",
            "imported_custom_company_label",
            "imported_custom_symbol",
            "imported_custom_color",
        ):
            st.session_state.pop(k, None)


DEFAULT_NEW_CO_PALETTE = [
    "#6366f1", "#ec4899", "#14b8a6", "#f59e0b", "#8b5cf6",
    "#06b6d4", "#10b981", "#f43f5e", "#84cc16", "#3b82f6",
    "#e11d48", "#d97706", "#a855f7", "#0284c7", "#f97316"
]

KNOWN_SYSTEM_SYMBOLS = {
    "LED", "SAM", "BAM", "CHY", "GHB", "KBK", "KTB", "SCB", "GSB",
    "DDP", "LVI", "NYO", "ZMY", "BAA"
}


def generate_default_symbol(company_name):
    """Generates default 3-character uppercase symbol for a company name."""
    clean = re.sub(r'^(บจก\.|บมจ\.|บริษัท|หจก\.)\s*', '', str(company_name).strip(), flags=re.I)
    clean = re.sub(r'\s*(จำกัด|มหาชน)$', '', clean, flags=re.I)
    clean = re.sub(r'[^a-zA-Z0-9\u0E00-\u0E7F]', '', clean).strip()
    if not clean:
        return "CST"
    sym = clean[:3].upper()
    if sym in KNOWN_SYSTEM_SYMBOLS:
        sym = (clean[:2] + "X")[:3].upper()
    return sym or "CST"


_CSV_AREA_TEXT_COLS = ('เนื้อที่ (ตร.ว.)', 'เนื้อที่ (ไร่-งาน-ตร.ว.)', 'เนื้อที่')


def _prepare_export_df(df, for_csv=False):
    """Formats coordinates, strips internal '_' columns, and neutralizes spreadsheet formulas for both CSV and Excel."""
    if df is None or df.empty:
        return df
    export_cols = [c for c in df.columns if not str(c).startswith('_')]
    out = df[export_cols].copy()
    for coord_col in ('ละติจูด', 'ลองจิจูด'):
        if coord_col in out.columns and not pd.api.types.is_string_dtype(out[coord_col]):
            out[coord_col] = format_coord_vectorized(df, coord_col)
    if for_csv:
        for area_col in _CSV_AREA_TEXT_COLS:
            if area_col in out.columns:
                out[area_col] = (
                    out[area_col]
                    .astype(object)
                    .fillna('')
                    .astype(str)
                    .str.strip()
                    .replace({'nan': '', 'None': '', '<NA>': ''})
                    .str.replace(r'^(\d+-\d+-\d+(?:\.\d+)?)$', r'="\1"', regex=True)
                )

    # Vectorized formula neutralization across ALL text/object/categorical columns (both CSV & Excel)
    for col in out.columns:
        dt = out[col].dtype
        if isinstance(dt, pd.CategoricalDtype):
            old_cats = list(out[col].cat.categories)
            new_cats = [_sanitize_spreadsheet_text(c, allow_csv_rnw=for_csv) for c in old_cats]
            if new_cats != old_cats:
                if len(set(new_cats)) == len(new_cats):
                    out[col] = out[col].cat.rename_categories(new_cats)
                else:
                    out[col] = out[col].astype(object).map(
                        lambda v: _sanitize_spreadsheet_text(v, allow_csv_rnw=for_csv)
                    )
        elif pd.api.types.is_string_dtype(dt):
            s_col = out[col]
            danger_mask = s_col.str.match(_DANGEROUS_LEAD_RE, na=False)
            if danger_mask.any():
                exempt_mask = s_col.str.match(_SAFE_DASH_RE, na=False)
                if for_csv:
                    exempt_mask = exempt_mask | s_col.str.match(_CSV_RNW_EXACT_RE, na=False)
                fix_mask = danger_mask & (~exempt_mask)
                if fix_mask.any():
                    out.loc[fix_mask, col] = "'" + s_col.loc[fix_mask]
        elif pd.api.types.is_object_dtype(dt):
            s_col = out[col]
            s_str = s_col.astype(str)
            danger_mask = s_col.notna() & s_str.str.match(_DANGEROUS_LEAD_RE, na=False)
            if danger_mask.any():
                exempt_mask = s_str.str.match(_SAFE_DASH_RE, na=False)
                if for_csv:
                    exempt_mask = exempt_mask | s_str.str.match(_CSV_RNW_EXACT_RE, na=False)
                fix_mask = danger_mask & (~exempt_mask)
                if fix_mask.any():
                    out.loc[fix_mask, col] = s_col.loc[fix_mask].map(
                        lambda v: ("'" + v) if isinstance(v, str) else v
                    )
    return out


def convert_df_to_csv(df):
    """Direct CSV generator returning UTF-8 with BOM bytes."""
    if df is None or df.empty:
        return b""
    df_out = _prepare_export_df(df, for_csv=True)
    return df_out.to_csv(index=False).encode('utf-8-sig')


def _write_excel_openpyxl_write_only(df_out, excel_buffer):
    """Memory-safe openpyxl write_only fallback that never interprets strings as formulas."""
    import openpyxl

    wb = openpyxl.Workbook(write_only=True)
    ws = wb.create_sheet(title='Assets')
    ws.append([str(c) for c in df_out.columns])
    for row in df_out.itertuples(index=False, name=None):
        clean_row = []
        for val in row:
            if val is None or (not isinstance(val, str) and pd.isna(val)):
                clean_row.append(None)
            elif hasattr(val, 'item') and not isinstance(val, (bytes, str)):
                clean_row.append(val.item())
            else:
                clean_row.append(val)
        ws.append(clean_row)
    wb.save(excel_buffer)


def convert_df_to_excel(df):
    """High-performance Excel generator using xlsxwriter with formula/URL auto-execution disabled."""
    if df is None or df.empty:
        return b""
    df_out = _prepare_export_df(df, for_csv=False)
    if len(df_out) > EXCEL_MAX_DATA_ROWS:
        df_out = df_out.iloc[:EXCEL_MAX_DATA_ROWS]
    excel_buffer = io.BytesIO()
    try:
        with pd.ExcelWriter(
            excel_buffer,
            engine='xlsxwriter',
            engine_kwargs={
                'options': {
                    'constant_memory': True,
                    'strings_to_formulas': False,
                    'strings_to_urls': False,
                }
            },
        ) as writer:
            df_out.to_excel(writer, index=False, sheet_name='Assets')
    except Exception:
        # Reset buffer so partial/corrupted bytes from a failed xlsxwriter run are discarded
        excel_buffer = io.BytesIO()
        _write_excel_openpyxl_write_only(df_out, excel_buffer)
    return excel_buffer.getvalue()


def _get_uploaded_file_size(uploaded_file):
    size = getattr(uploaded_file, "size", None)
    if isinstance(size, (int, float)) and size >= 0:
        return int(size)
    try:
        pos = uploaded_file.tell()
        uploaded_file.seek(0, io.SEEK_END)
        size = uploaded_file.tell()
        uploaded_file.seek(pos)
        return int(size)
    except Exception:
        return 0


def _validate_xlsx_zip_safety(uploaded_file):
    """Guards against ZIP bombs and XML entity expansion (XXE/Billion Laughs) before openpyxl reads the file."""
    uploaded_file.seek(0)
    try:
        if not zipfile.is_zipfile(uploaded_file):
            uploaded_file.seek(0)
            return
        uploaded_file.seek(0)
        with zipfile.ZipFile(uploaded_file, 'r') as zf:
            infos = zf.infolist()
            if len(infos) > MAX_XLSX_ENTRIES:
                raise ValueError(f"ไฟล์ Excel มีโครงสร้างย่อยเกินกำหนด ({len(infos):,} รายการ)")
            total_uncompressed = 0
            total_compressed = 0
            for info in infos:
                total_uncompressed += max(0, int(info.file_size))
                total_compressed += max(0, int(info.compress_size))
                if total_uncompressed > MAX_XLSX_UNCOMPRESSED_BYTES:
                    raise ValueError(
                        f"ขนาดข้อมูลหลังแตกไฟล์ Excel เกินขีดจำกัด ({MAX_XLSX_UNCOMPRESSED_BYTES // (1024 * 1024):,} MB)"
                    )
                if info.filename.lower().endswith(('.xml', '.rels')):
                    with zf.open(info, 'r') as member:
                        head = member.read(8192)
                    if b'<!ENTITY' in head or b'<!DOCTYPE' in head:
                        raise ValueError("ตรวจพบโครงสร้าง XML ที่ไม่ปลอดภัย (DOCTYPE/ENTITY) ในไฟล์ Excel")
            if total_compressed > 0 and (total_uncompressed / total_compressed) > MAX_XLSX_COMPRESSION_RATIO:
                raise ValueError("อัตราการบีบอัดไฟล์ Excel ผิดปกติ (อาจเป็นไฟล์ ZIP Bomb)")
    finally:
        uploaded_file.seek(0)


def _read_uploaded_dataframe(uploaded_file):
    """Reads CSV or Excel with strict size, ZIP-bomb, and row-count limits."""
    file_size = _get_uploaded_file_size(uploaded_file)
    if file_size > MAX_UPLOAD_BYTES:
        raise ValueError(
            f"ขนาดไฟล์เกินกำหนด ({file_size / (1024 * 1024):.1f} MB > {MAX_UPLOAD_BYTES // (1024 * 1024)} MB)"
        )

    file_name_lower = str(getattr(uploaded_file, "name", "") or "").lower()
    if file_name_lower.endswith('.csv'):
        u_df = None
        for enc in ['utf-8-sig', 'utf-8', 'cp874', 'tis-620']:
            try:
                uploaded_file.seek(0)
                u_df = pd.read_csv(uploaded_file, encoding=enc, nrows=MAX_UPLOAD_ROWS + 1)
                break
            except Exception:
                continue
        if u_df is None:
            uploaded_file.seek(0)
            u_df = pd.read_csv(
                uploaded_file,
                encoding='utf-8',
                encoding_errors='replace',
                nrows=MAX_UPLOAD_ROWS + 1,
            )
    else:
        if file_name_lower.endswith('.xlsx') or file_name_lower.endswith('.xlsm'):
            _validate_xlsx_zip_safety(uploaded_file)
        uploaded_file.seek(0)
        u_df = pd.read_excel(uploaded_file, nrows=MAX_UPLOAD_ROWS + 1)

    if u_df is not None and len(u_df) > MAX_UPLOAD_ROWS:
        raise ValueError(f"จำนวนแถวในไฟล์เกินขีดจำกัด ({MAX_UPLOAD_ROWS:,} แถวต่อครั้ง)")
    if u_df is not None:
        u_df.columns = [str(c).strip() for c in u_df.columns]
    return u_df


_IMPORT_ESSENTIAL_COLS = (
    ("รหัสทรัพย์", "จำเป็นสำหรับระบุอ้างอิงทรัพย์บนแผนที่และตารางเปรียบเทียบ"),
    ("ประเภททรัพย์", "หากไม่มีจะจัดเป็น 'อื่นๆ'"),
    ("ราคา", "หากไม่มีจะไม่คำนวณราคากลางและราคาต่อหน่วย"),
    ("ละติจูด", "จำเป็นสำหรับปักหมุดบนแผนที่ Tab 2"),
    ("ลองจิจูด", "จำเป็นสำหรับปักหมุดบนแผนที่ Tab 2"),
    ("จังหวัด", "จำเป็นสำหรับกรองตามจังหวัดและจัดกลุ่มภาค"),
)

_IMPORT_LAND_ANY_COLS = frozenset({
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
})
_CONDO_ONLY_TYPE_RE = re.compile(r'คอนโด|ห้องชุด|อาคารชุด|condo|penthouse|duplex', re.I)


def _is_condo_only_dataframe(df):
    """Returns True when every non-empty 'ประเภททรัพย์' row in `df` is a condo/unit type."""
    if df is None or df.empty or "ประเภททรัพย์" not in df.columns:
        return False
    u_types = [
        str(v).strip()
        for v in df["ประเภททรัพย์"].dropna().unique()
        if str(v).strip() not in ("", "-", "nan", "None", "null", "<NA>", "NaN")
    ]
    return bool(u_types) and all(_CONDO_ONLY_TYPE_RE.search(t) for t in u_types)


def _inspect_uploaded_columns(df):
    """Inspects uploaded DataFrame columns against dashboard expectations and detects split Rai/Ngan/Wah columns."""
    cols = [str(c).strip() for c in df.columns]
    col_set = set(cols)
    split_info = detect_split_land_area_columns(cols, df=df)

    missing_essential = [(col, desc) for col, desc in _IMPORT_ESSENTIAL_COLS if col not in col_set]
    present_essential = [col for col, _ in _IMPORT_ESSENTIAL_COLS if col in col_set]

    matched_land_cols = [c for c in cols if c in _IMPORT_LAND_ANY_COLS]
    has_land_area = bool(split_info["source_cols"]) or bool(matched_land_cols)
    is_condo_only_with_sqm = ("พื้นที่ใช้สอย (ตร.ม.)" in col_set) and _is_condo_only_dataframe(df)

    if has_land_area:
        if split_info["combined"]:
            present_essential.append(str(split_info["combined"]))
        elif split_info["source_cols"]:
            present_essential.append(" + ".join(str(c) for c in split_info["source_cols"]))
        else:
            present_essential.append(matched_land_cols[0])
    elif is_condo_only_with_sqm:
        present_essential.append("พื้นที่ใช้สอย (ตร.ม.)")
    else:
        missing_essential.append((
            "เนื้อที่ (ตร.ว.) หรือ เนื้อที่ (ไร่-งาน-ตร.ว.)",
            "จำเป็นสำหรับแสดงขนาดที่ดินและคำนวณราคาต่อ ตร.ว. (รองรับคอลัมน์แยก ไร่ / งาน / ตร.ว. ด้วย)",
        ))

    has_company = "บริษัท" in col_set
    return {
        "has_company": has_company,
        "present_essential": present_essential,
        "missing_essential": missing_essential,
        "has_land_area": has_land_area,
        "is_condo_only_with_sqm": is_condo_only_with_sqm,
        "split_info": split_info,
    }


def _build_map_pin_preview_html(symbol, color_hex, company_name, count):
    """Builds inline HTML preview matching the real circular Deck.gl / Leaflet map pin and compact legend item."""
    safe_col = _safe_hex_color(color_hex)
    sym_clean = str(symbol or "").strip().upper()
    sym_disp = html.escape(sym_clean if sym_clean else "?", quote=True)
    co_raw = str(company_name or "").strip()
    co_short = (co_raw[:20] + "…") if len(co_raw) > 21 else co_raw
    co_esc = html.escape(co_short, quote=True)
    co_title = html.escape(co_raw, quote=True)

    s_len = len(sym_clean)
    if s_len <= 1:
        f_px = 18
    elif s_len == 2:
        f_px = 14
    elif s_len == 3:
        f_px = 11.5
    else:
        f_px = 9.5

    return (
        f'<div style="font-size:14px; font-weight:400; line-height:1.4; margin-bottom:4px; color:inherit;">'
        f'ตัวอย่างหมุดบนแผนที่'
        f'</div>'
        f'<div style="display:flex; align-items:center; gap:10px; min-height:42px;">'
        f'  <div title="หมุดบนแผนที่: {sym_disp}" style="width:40px; height:40px; min-width:40px; border-radius:50%; '
        f'      background:#ffffff; border:3px solid {safe_col}; color:{safe_col}; '
        f'      display:flex; align-items:center; justify-content:center; '
        f'      font-family:Segoe UI, Tahoma, sans-serif; font-weight:800; font-size:{f_px}px; '
        f'      letter-spacing:-0.2px; line-height:1; box-shadow:0 2px 6px rgba(15,23,42,0.20);">'
        f'      {sym_disp}'
        f'  </div>'
        f'  <div title="{co_title}" style="display:inline-flex; align-items:center; gap:6px; '
        f'      background:rgba(148,163,184,0.10); border:1px solid rgba(148,163,184,0.28); '
        f'      border-radius:6px; padding:4px 8px; max-width:100%; overflow:hidden;">'
        f'      <span style="width:9px; height:9px; min-width:9px; border-radius:50%; background:{safe_col}; display:inline-block;"></span>'
        f'      <span style="font-size:12px; font-weight:600; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">{co_esc}</span>'
        f'      <span style="font-size:11px; opacity:0.72; white-space:nowrap;">({int(count):,})</span>'
        f'  </div>'
        f'</div>'
    )


def _render_import_column_guide():
    """Renders collapsible essential column specification guide for file import."""
    with st.expander("คู่มือคอลัมน์ที่รองรับในการนำเข้าไฟล์ (คลิกเพื่อดูรายละเอียด)", icon=":material/table_chart:", expanded=False):
        st.markdown(
            """
**คอลัมน์สำคัญ (แนะนำให้มีครบเพื่อให้แผนที่และการวิเคราะห์ทำงานได้เต็มประสิทธิภาพ)**
| ชื่อคอลัมน์ | รายละเอียด / ตัวอย่างรูปแบบ |
|---|---|
| `บริษัท` | ชื่อบริษัท/เจ้าของทรัพย์ (หากไม่ระบุ ระบบตั้งค่าเป็น `"ไฟล์นำเข้า"` และกำหนดตัวย่อ+สีหมุดได้) |
| `รหัสทรัพย์` | รหัสอ้างอิงทรัพย์สิน (ใช้เลือกทรัพย์อ้างอิงบนแผนที่และตารางเปรียบเทียบ) |
| `ประเภททรัพย์` | เช่น `บ้านเดี่ยว`, `ทาวน์เฮ้าส์`, `ห้องชุดพักอาศัย`, `ที่ดินเปล่า`, `อาคารพาณิชย์` ฯลฯ |
| `ราคา` | ราคาขาย (บาท) รองรับตัวเลขหรือข้อความมีคอมม่า เช่น `3,500,000` |
| `เนื้อที่ (ตร.ว.)` หรือ `เนื้อที่ (ไร่-งาน-ตร.ว.)`<br>หรือแยก `ไร่`, `งาน`, `ตร.ว.` | **รองรับทั้ง 2 แบบ:**<br>1) **แบบรวมช่องเดียว** เช่น `1-2-30` หรือตัวเลขตารางวา เช่น `630`<br>2) **แบบแยกคอลัมน์** `ไร่` / `งาน` / `ตร.ว.` (ระบบคำนวณรวมและทดหน่วยให้อัตโนมัติ) |
| `พื้นที่ใช้สอย (ตร.ม.)` | พื้นที่ใช้สอยเป็นตารางเมตร เช่น `145.5` *(สำคัญสำหรับคอนโด/ห้องชุด)* |
| `ละติจูด` | พิกัดละติจูด (เช่น `13.756312`) — จำเป็นสำหรับปักหมุดบนแผนที่ |
| `ลองจิจูด` | พิกัดลองจิจูด (เช่น `100.501812`) — จำเป็นสำหรับปักหมุดบนแผนที่ |
| `จังหวัด` | ชื่อจังหวัด เช่น `กรุงเทพมหานคร`, `ชลบุรี` |

> **หมายเหตุ:** ระบบจะคำนวณคอลัมน์ `ราคาต่อตารางวา` และ `ราคาต่อตารางเมตร` ให้อัตโนมัติ ไม่จำเป็นต้องใส่ในไฟล์ต้นทาง
""",
            unsafe_allow_html=True,
        )


def _compute_export_fingerprint(df_to_export):
    """Fast content-aware fingerprint so two equal-length filtered DataFrames never reuse a stale file."""
    n_rows = len(df_to_export)
    cols_tuple = tuple(str(c) for c in df_to_export.columns)
    custom_ver = int(st.session_state.get("_custom_import_ver", 0))
    h = hashlib.blake2b(digest_size=12)
    h.update(f"{n_rows}|{custom_ver}|{len(cols_tuple)}".encode("utf-8"))
    for c in cols_tuple:
        h.update(c.encode("utf-8", errors="ignore"))
        h.update(b"|")

    # Sample first, middle, and last rows on key identifying columns
    if n_rows > 0:
        sample_positions = sorted({
            0,
            min(1, n_rows - 1),
            min(2, n_rows - 1),
            n_rows // 2,
            max(0, n_rows - 2),
            n_rows - 1,
        })
        key_cols = [
            c for c in ('รหัสทรัพย์', 'บริษัท', 'ชื่อโครงการ', 'จังหวัด', 'อำเภอ', 'ราคา', 'ประเภททรัพย์')
            if c in df_to_export.columns
        ] or list(df_to_export.columns[:5])
        sample_df = df_to_export.iloc[sample_positions][key_cols]
        for row in sample_df.itertuples(index=False, name=None):
            h.update(repr(row).encode("utf-8", errors="ignore"))
        if 'ราคา' in df_to_export.columns and pd.api.types.is_numeric_dtype(df_to_export['ราคา']):
            try:
                p_sum = float(df_to_export['ราคา'].sum(skipna=True))
                h.update(f"|p:{p_sum:.2f}".encode("utf-8"))
            except Exception:
                pass
    return (n_rows, custom_ver, h.hexdigest())


def render_import_export_section(df_to_export, filename_prefix="npa_data", key_suffix=""):
    """Renders side-by-side Import (Excel/CSV with multi-company support) and Export (Excel/CSV) UI."""
    safe_prefix = _sanitize_filename_prefix(filename_prefix)
    st.markdown("<br/>", unsafe_allow_html=True)
    st.markdown("##### <i class='fa-solid fa-arrow-right-arrow-left' style='color:#059669; margin-right:6px;'></i>นำเข้าและส่งออกข้อมูล (Import & Export Data)", unsafe_allow_html=True)
    col_imp, col_exp = st.columns(2)

    # Left: Import File
    with col_imp:
        st.markdown("###### <i class='fa-solid fa-file-import' style='color:#64748b; margin-right:6px;'></i>นำเข้าข้อมูลเพิ่มเติม (Import File)", unsafe_allow_html=True)
        _render_import_column_guide()
        uploader_gen_key = f"_uploader_gen_{key_suffix}"
        uploader_gen = int(st.session_state.get(uploader_gen_key, 0))
        uploaded_file = st.file_uploader(
            "เลือกไฟล์ Excel หรือ CSV เพื่อเพิ่มข้อมูล",
            type=["xlsx", "xls", "csv"],
            key=f"custom_file_uploader_{key_suffix}_{uploader_gen}",
            help=(
                f"รองรับไฟล์ไม่เกิน {MAX_UPLOAD_BYTES // (1024 * 1024)} MB / {MAX_UPLOAD_ROWS:,} แถว "
                f"(คอลัมน์สำคัญ: บริษัท, รหัสทรัพย์, ประเภททรัพย์, ราคา, เนื้อที่ (ตร.ว.) หรือ เนื้อที่ (ไร่-งาน-ตร.ว.) "
                f"หรือแยก ไร่ / งาน / ตร.ว., ละติจูด, ลองจิจูด, จังหวัด)"
            ),
        )
        if uploaded_file is not None:
            try:
                file_size = _get_uploaded_file_size(uploaded_file)
                upload_uid = (
                    getattr(uploaded_file, "file_id", None)
                    or f"{str(getattr(uploaded_file, 'name', '')).lower()}:{file_size}"
                )
                parse_cache_key = f"_parsed_upload_cache_{key_suffix}"
                cached_upload = st.session_state.get(parse_cache_key)
                if isinstance(cached_upload, dict) and cached_upload.get("uid") == upload_uid:
                    u_df = cached_upload.get("df")
                else:
                    # Free any stale parsed-upload cache from other widgets before parsing
                    for _pk in [k for k in st.session_state.keys() if str(k).startswith("_parsed_upload_cache_")]:
                        st.session_state.pop(_pk, None)
                    u_df = _read_uploaded_dataframe(uploaded_file)
                    st.session_state[parse_cache_key] = {"uid": upload_uid, "df": u_df}

                if u_df is not None and not u_df.empty:
                    # Inspect columns & split Rai/Ngan/Wah before mutating u_work_df
                    col_audit = _inspect_uploaded_columns(u_df)

                    # Clean and inspect companies
                    has_company_col = col_audit["has_company"]
                    u_work_df = u_df.copy()

                    if not has_company_col:
                        u_work_df['บริษัท'] = "ไฟล์นำเข้า"
                    else:
                        blank_mask = (
                            u_work_df['บริษัท'].isna() |
                            u_work_df['บริษัท'].astype(str).str.strip().isin(['', 'nan', 'None', 'null', '<NA>', 'NaN', '-'])
                        )
                        if blank_mask.any():
                            u_work_df.loc[blank_mask, 'บริษัท'] = "ไฟล์นำเข้า"
                        u_work_df['บริษัท'] = u_work_df['บริษัท'].astype(str).str.strip()

                    co_counts = u_work_df['บริษัท'].value_counts()
                    co_counts = co_counts[co_counts > 0]
                    total_detected_cos = len(co_counts)

                    st.success(f"อ่านไฟล์สำเร็จ ({len(u_work_df):,} รายการ จาก {total_detected_cos:,} บริษัท)")

                    # 0a. Inform when separate Rai / Ngan / Wah columns are detected
                    split_info = col_audit["split_info"]
                    if split_info["source_cols"]:
                        src_cols_md = " + ".join(f"`{c}`" for c in split_info["source_cols"])
                        if split_info["combined"]:
                            split_msg = (
                                f"**ตรวจพบคอลัมน์แยกเนื้อที่ดิน:** {src_cols_md}\n\n"
                                f"_พบคอลัมน์รวม `{split_info['combined']}` อยู่แล้วด้วย — ระบบจะยึดค่าจากคอลัมน์รวมเป็นหลัก "
                                f"และนำค่าจากคอลัมน์แยกมาคำนวณรวม (ทดหน่วยมาตรฐาน) เติมให้เฉพาะแถวที่ว่าง "
                                f"พร้อมลบคอลัมน์แยกออกหลังรวมเสร็จ_"
                            )
                        else:
                            split_msg = (
                                f"**ตรวจพบคอลัมน์แยกเนื้อที่ดิน:** {src_cols_md}\n\n"
                                f"_ระบบจะรวมและทดหน่วยมาตรฐานเป็นช่องเดียว (`เนื้อที่ (ตร.ว.)` รูปแบบ ไร่-งาน-ตร.ว. "
                                f"และ `พื้นที่_ตารางวา`) พร้อมลบคอลัมน์แยกออกให้อัตโนมัติ_"
                            )
                        st.info(split_msg, icon=":material/straighten:")

                    # 0b. Non-blocking warning if any essential columns are missing
                    missing_ess = col_audit["missing_essential"]
                    if missing_ess:
                        present_ess = col_audit["present_essential"]
                        present_txt = ", ".join(f"`{c}`" for c in present_ess) if present_ess else "ไม่มี"
                        missing_lines = "\n".join(f"- `{c}` — {desc}" for c, desc in missing_ess)
                        st.warning(
                            f"**ไม่พบคอลัมน์สำคัญบางรายการในไฟล์นี้** *(ตรวจพบแล้ว: {present_txt})*\n\n"
                            f"{missing_lines}\n\n"
                            f"_คุณยังสามารถกดปุ่ม \"รวมเข้ากับฐานข้อมูลหลัก\" ได้ตามปกติ หากข้อมูลบางส่วนไม่จำเป็นต้องใช้_",
                            icon=":material/warning:",
                        )

                    # Separate known vs new companies
                    known_keys_upper = {k.upper(): k for k in COMPANY_COLORS.keys()}
                    known_cos = []
                    new_cos = []

                    for co_name, cnt in co_counts.items():
                        co_upper = str(co_name).strip().upper()
                        if co_upper in known_keys_upper:
                            known_cos.append((known_keys_upper[co_upper], cnt))
                        else:
                            new_cos.append((str(co_name), cnt))

                    # 1. Inform if known system companies are found (pure Markdown, no raw HTML inside st.info)
                    if known_cos:
                        known_desc = ", ".join([f"**{c}** ({cnt:,})" for c, cnt in known_cos])
                        st.info(
                            f"**ตรวจพบ {len(known_cos)} บริษัทมาตรฐานในระบบ:** {known_desc}\n\n"
                            f"_ระบบจะใช้สีองค์กรและโลโก้มาตรฐานเดิมอัตโนมัติ ไม่ต้องตั้งค่าซ้ำ_",
                            icon=":material/verified:"
                        )

                    # Guard against excessive unique new companies (prevents UI/atlas blowup)
                    too_many_companies = len(new_cos) > MAX_NEW_COMPANIES_PER_UPLOAD
                    if too_many_companies:
                        st.error(
                            f"ตรวจพบบริษัทใหม่ {len(new_cos):,} รายชื่อ เกินขีดจำกัด {MAX_NEW_COMPANIES_PER_UPLOAD} บริษัทต่อไฟล์ "
                            f"กรุณาตรวจสอบคอลัมน์ 'บริษัท' ในไฟล์ต้นทางก่อนนำเข้า"
                        )

                    # 2. Accordions for new companies
                    configured_new_cos = {}
                    entered_symbols = {}

                    if new_cos and not too_many_companies:
                        st.markdown(
                            "<div style='margin-top:10px; margin-bottom:6px;'>"
                            "<span style='font-size:13px; font-weight:700; color:#1e293b;'>"
                            "<i class='fa-solid fa-sliders' style='color:#6366f1; margin-right:6px;'></i>"
                            f"ตั้งค่าตัวย่อและสีหมุดสำหรับบริษัทใหม่ ({len(new_cos)} บริษัท):"
                            "</span>"
                            "</div>",
                            unsafe_allow_html=True
                        )

                        existing_cos_state = st.session_state.get("imported_custom_companies", {})

                        for idx, (co_name, cnt) in enumerate(new_cos):
                            default_sym = generate_default_symbol(co_name)
                            default_col = DEFAULT_NEW_CO_PALETTE[idx % len(DEFAULT_NEW_CO_PALETTE)]

                            saved_conf = existing_cos_state.get(co_name, {}) if isinstance(existing_cos_state, dict) else {}
                            init_sym = saved_conf.get("symbol", default_sym)
                            init_col = _safe_hex_color(saved_conf.get("color", default_col), default=default_col)

                            with st.expander(f"{co_name} ({cnt:,} รายการ)", expanded=(len(new_cos) <= 3 or idx == 0), icon=":material/business:"):
                                c_sym_col, c_color_col, c_prev_col = st.columns([1.05, 0.55, 1.4])
                                with c_sym_col:
                                    sym_val = st.text_input(
                                        "ตัวย่อบนหมุด",
                                        value=init_sym,
                                        max_chars=4,
                                        key=f"custom_sym_input_{key_suffix}_{uploader_gen}_{idx}_{co_name}",
                                        help=f"ตัวอักษร 1-4 ตัวบนหมุดแผนที่ (เริ่มต้นจาก 3 ตัวแรกของ '{co_name}')"
                                    ).strip().upper()
                                with c_color_col:
                                    color_val = st.color_picker(
                                        "เลือกสีหมุด",
                                        value=init_col,
                                        key=f"custom_color_picker_{key_suffix}_{uploader_gen}_{idx}_{co_name}",
                                        help="สีนี้จะใช้แสดงเป็นขอบหมุดและจุดสีใน Legend"
                                    )
                                with c_prev_col:
                                    st.markdown(
                                        _build_map_pin_preview_html(sym_val, color_val, co_name, cnt),
                                        unsafe_allow_html=True,
                                    )
                                configured_new_cos[co_name] = {"symbol": sym_val, "color": _safe_hex_color(color_val)}
                                entered_symbols[co_name] = sym_val

                    # 3. Validation
                    is_valid = not too_many_companies
                    validation_errors = []

                    # Check empty symbols
                    empty_sym_cos = [html.escape(str(co), quote=True) for co, sym in entered_symbols.items() if not sym]
                    if empty_sym_cos:
                        is_valid = False
                        validation_errors.append(f"กรุณาระบุตัวย่อบนหมุดให้ครบถ้วน (ว่าง: {', '.join(empty_sym_cos)})")

                    # Check duplicates among entered symbols
                    sym_groups = {}
                    for co, sym in entered_symbols.items():
                        if sym:
                            sym_groups.setdefault(sym, []).append(co)

                    for sym, cos in sym_groups.items():
                        if len(cos) > 1:
                            is_valid = False
                            safe_sym = html.escape(str(sym), quote=True)
                            safe_cos = ", ".join(html.escape(str(c), quote=True) for c in cos)
                            validation_errors.append(f"ตัวย่อ <b>'{safe_sym}'</b> ซ้ำกันระหว่างบริษัท: {safe_cos}")

                    # Check duplicates against standard system symbols or company names
                    known_upper_names = {k.upper() for k in COMPANY_COLORS.keys()}
                    for co, sym in entered_symbols.items():
                        if sym in KNOWN_SYSTEM_SYMBOLS or sym in known_upper_names:
                            is_valid = False
                            safe_sym = html.escape(str(sym), quote=True)
                            safe_co = html.escape(str(co), quote=True)
                            validation_errors.append(f"ตัวย่อ <b>'{safe_sym}'</b> ของ <i>'{safe_co}'</i> ซ้ำกับบริษัทมาตรฐานในระบบ ({safe_sym})")

                    # Check duplicates against previously imported custom companies
                    existing_saved_cos = st.session_state.get("imported_custom_companies", {})
                    if isinstance(existing_saved_cos, dict):
                        for co, sym in entered_symbols.items():
                            for ex_co, ex_conf in existing_saved_cos.items():
                                if ex_co != co and isinstance(ex_conf, dict) and ex_conf.get("symbol") == sym:
                                    is_valid = False
                                    safe_sym = html.escape(str(sym), quote=True)
                                    safe_co = html.escape(str(co), quote=True)
                                    safe_ex_co = html.escape(str(ex_co), quote=True)
                                    validation_errors.append(
                                        f"ตัวย่อ <b>'{safe_sym}'</b> ของ <i>'{safe_co}'</i> ซ้ำกับบริษัทที่เคยนำเข้าไว้: <i>'{safe_ex_co}'</i>"
                                    )

                    # Show errors or success message
                    if not is_valid and validation_errors:
                        err_html = "<br/>".join([f"• {e}" for e in validation_errors])
                        st.markdown(
                            f'''<div style="background:rgba(239,68,68,0.08); border:1px solid rgba(239,68,68,0.3); border-radius:8px; padding:10px 14px; margin:10px 0;">
                                <div style="color:#b91c1c; font-size:12.5px; font-weight:700; margin-bottom:4px;">
                                    <i class="fa-solid fa-triangle-exclamation" style="margin-right:6px;"></i>ตรวจพบข้อผิดพลาด กรุณาแก้ไขตัวย่อไม่ให้ซ้ำกัน:
                                </div>
                                <div style="color:#dc2626; font-size:12px; line-height:1.5;">{err_html}</div>
                            </div>''',
                            unsafe_allow_html=True
                        )
                    elif new_cos and is_valid:
                        st.markdown(
                            '''<div style="background:rgba(16,185,129,0.08); border:1px solid rgba(16,185,129,0.3); border-radius:8px; padding:8px 12px; margin:10px 0;">
                                <div style="color:#047857; font-size:12px; font-weight:600;">
                                    <i class="fa-solid fa-circle-check" style="margin-right:6px;"></i>ตัวย่อและสีหมุดถูกต้องครบถ้วน ไม่พบการซ้ำซ้อน พร้อมรวมข้อมูล
                                </div>
                            </div>''',
                            unsafe_allow_html=True
                        )

                    # 4. Merge Button
                    if st.button("รวมเข้ากับฐานข้อมูลหลัก", icon=":material/merge:", key=f"btn_apply_import_{key_suffix}", disabled=not is_valid, use_container_width=True):
                        from modules.services.data_cleaner import ensure_derived_cols

                        # Prepare data
                        u_clean = u_work_df.copy()

                        # Standardize known company names in u_clean if casing differs
                        if known_keys_upper:
                            u_clean['บริษัท'] = u_clean['บริษัท'].apply(
                                lambda c: known_keys_upper.get(str(c).strip().upper(), str(c).strip())
                            )

                        # Update session state metadata
                        if "imported_custom_companies" not in st.session_state or not isinstance(st.session_state["imported_custom_companies"], dict):
                            st.session_state["imported_custom_companies"] = {}

                        for co_name, conf in configured_new_cos.items():
                            st.session_state["imported_custom_companies"][co_name] = conf

                        _sync_legacy_custom_keys()

                        # Combine separate Rai / Ngan / Wah columns (if present) before deriving full schema
                        u_clean, _ = combine_split_land_area_columns(u_clean, drop_source_cols=True)

                        # Enrich derived cols (read-only cache mode prevents polluting shared disk cache)
                        u_clean_derived = ensure_derived_cols(u_clean, persist_cache=False)

                        # Append mode (un-categorize ALL categorical cols including อำเภอ/ตำบล before concat)
                        if "imported_custom_df" in st.session_state and st.session_state["imported_custom_df"] is not None and not st.session_state["imported_custom_df"].empty:
                            prev_df = st.session_state["imported_custom_df"].copy()
                            all_cat_cols = set(
                                [c for c in prev_df.columns if isinstance(prev_df[c].dtype, pd.CategoricalDtype)]
                                + [c for c in u_clean_derived.columns if isinstance(u_clean_derived[c].dtype, pd.CategoricalDtype)]
                            )
                            for col in all_cat_cols:
                                if col in prev_df.columns and isinstance(prev_df[col].dtype, pd.CategoricalDtype):
                                    prev_df[col] = prev_df[col].astype(object)
                                if col in u_clean_derived.columns and isinstance(u_clean_derived[col].dtype, pd.CategoricalDtype):
                                    u_clean_derived[col] = u_clean_derived[col].astype(object)
                            combined_imp = pd.concat([prev_df, u_clean_derived], ignore_index=True)
                            st.session_state["imported_custom_df"] = combined_imp
                        else:
                            st.session_state["imported_custom_df"] = u_clean_derived

                        # Rotate uploader key & clear parsed upload cache to prevent duplicate-merge clicks and free RAM
                        st.session_state[uploader_gen_key] = uploader_gen + 1
                        st.session_state.pop(parse_cache_key, None)

                        # Clear view caches
                        _invalidate_imported_view_caches()
                        st.success("นำเข้าข้อมูลสำเร็จแล้ว!")
                        st.rerun()
            except Exception as ex:
                st.error(f"อ่านไฟล์ไม่สำเร็จ: {ex}")

        # Status Card and Management (Clear All & Selective Delete)
        if "imported_custom_df" in st.session_state and st.session_state["imported_custom_df"] is not None and not st.session_state["imported_custom_df"].empty:
            imp_df_current = st.session_state["imported_custom_df"]
            imp_companies_dict = st.session_state.get("imported_custom_companies", {})
            total_imp_count = len(imp_df_current)
            co_counts = imp_df_current['บริษัท'].value_counts()
            co_counts = co_counts[co_counts > 0]

            badges_html = []
            for co_name, cnt in co_counts.items():
                co_str = str(co_name)
                if isinstance(imp_companies_dict, dict) and co_str in imp_companies_dict:
                    sym_show = imp_companies_dict[co_str].get("symbol", "CST")
                    col_show = imp_companies_dict[co_str].get("color", "#6366f1")
                elif co_str in COMPANY_COLORS:
                    sym_show = co_str[:3].upper()
                    col_show = COMPANY_COLORS[co_str]
                else:
                    sym_show = st.session_state.get("imported_custom_symbol", "CST")
                    col_show = st.session_state.get("imported_custom_color", "#6366f1")

                co_esc = html.escape(co_str, quote=True)
                sym_esc = html.escape(str(sym_show), quote=True)
                col_safe = _safe_hex_color(col_show)
                badge_item = (
                    f'<div style="display:inline-flex; align-items:center; background:#ffffff; border:1px solid #cbd5e1; '
                    f'border-radius:6px; padding:2px 8px; margin:3px 5px 3px 0; box-shadow:0 1px 2px rgba(0,0,0,0.04);">'
                    f'<span style="display:inline-block; border:1.5px solid {col_safe}; color:{col_safe}; background:#ffffff; '
                    f'font-size:10.5px; font-weight:800; border-radius:4px; padding:0px 5px; margin-right:6px;">{sym_esc}</span>'
                    f'<span style="color:#1e293b; font-size:12.5px; font-weight:600; margin-right:5px;">{co_esc}</span>'
                    f'<span style="color:#64748b; font-size:11.5px; font-weight:500;">({cnt:,})</span>'
                    f'</div>'
                )
                badges_html.append(badge_item)

            badges_container_html = "".join(badges_html)
            st.markdown(
                f'''<div style="background:rgba(99,102,241,0.06); border:1px solid rgba(99,102,241,0.22); border-radius:10px; padding:12px 14px; margin:12px 0 10px 0;">
                    <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:8px;">
                        <span style="color:#1e293b; font-weight:700; font-size:13.5px;">
                            <i class="fa-solid fa-layer-group" style="color:#6366f1; margin-right:6px;"></i>ข้อมูลนำเข้าสะสมทั้งหมด: <b style="color:#4f46e5;">{total_imp_count:,}</b> รายการ ({len(co_counts):,} บริษัท)
                        </span>
                    </div>
                    <div style="display:flex; flex-wrap:wrap; align-items:center;">
                        {badges_container_html}
                    </div>
                </div>''',
                unsafe_allow_html=True
            )

            col_del_all, col_del_sel = st.columns([1, 1])
            with col_del_all:
                if st.button("ล้างข้อมูลนำเข้าทั้งหมด", icon=":material/delete_forever:", key=f"btn_clear_all_{key_suffix}", use_container_width=True):
                    st.session_state.pop("imported_custom_df", None)
                    st.session_state.pop("imported_custom_companies", None)
                    _sync_legacy_custom_keys()
                    _invalidate_imported_view_caches()
                    st.rerun()

            with col_del_sel:
                with st.popover("ลบเฉพาะบางบริษัท", icon=":material/delete_sweep:", use_container_width=True):
                    st.markdown("<p style='font-size:12.5px; font-weight:600; color:#334155; margin-bottom:4px;'>เลือกบริษัทที่ต้องการลบออกจากระบบ:</p>", unsafe_allow_html=True)
                    avail_cos = sorted([str(c) for c in co_counts.keys()])
                    cos_to_remove = st.multiselect("บริษัท:", options=avail_cos, key=f"sel_cos_to_remove_{key_suffix}", label_visibility="collapsed")
                    if st.button("ยืนยันลบบริษัทที่เลือก", type="primary", key=f"btn_confirm_del_sel_{key_suffix}", use_container_width=True):
                        if cos_to_remove:
                            remaining_df = imp_df_current[~imp_df_current['บริษัท'].astype(str).isin(cos_to_remove)].copy()
                            if remaining_df.empty:
                                st.session_state.pop("imported_custom_df", None)
                                st.session_state.pop("imported_custom_companies", None)
                            else:
                                if 'บริษัท' in remaining_df.columns and isinstance(remaining_df['บริษัท'].dtype, pd.CategoricalDtype):
                                    remaining_df['บริษัท'] = remaining_df['บริษัท'].cat.remove_unused_categories()
                                st.session_state["imported_custom_df"] = remaining_df
                                if "imported_custom_companies" in st.session_state and isinstance(st.session_state["imported_custom_companies"], dict):
                                    for rm_co in cos_to_remove:
                                        st.session_state["imported_custom_companies"].pop(rm_co, None)
                            _sync_legacy_custom_keys()
                            _invalidate_imported_view_caches()
                            st.rerun()

    # Right: Export File
    with col_exp:
        st.markdown("###### <i class='fa-solid fa-file-export' style='color:#64748b; margin-right:6px;'></i>ส่งออกข้อมูลในตาราง (Export Data)", unsafe_allow_html=True)
        if df_to_export is not None and not df_to_export.empty:
            n_rows = len(df_to_export)
            data_fp = _compute_export_fingerprint(df_to_export)
            st.caption(f"ข้อมูลพร้อมส่งออกทั้งหมด **{n_rows:,}** รายการ")

            c_exp1, c_exp2 = st.columns(2)
            with c_exp1:
                csv_key = f"csv_data_{key_suffix}"
                csv_rows_key = f"csv_rows_{key_suffix}"

                if csv_key in st.session_state and st.session_state.get(csv_rows_key) != data_fp:
                    st.session_state.pop(csv_key, None)
                    st.session_state.pop(csv_rows_key, None)

                has_cached_csv = (
                    st.session_state.get(csv_rows_key) == data_fp and
                    csv_key in st.session_state and
                    isinstance(st.session_state[csv_key], bytes) and
                    len(st.session_state[csv_key]) > 0
                )

                if n_rows <= 10000:
                    st.download_button(
                        label="ส่งออก CSV (.csv)",
                        data=lambda: convert_df_to_csv(df_to_export),
                        file_name=f"{safe_prefix}.csv",
                        mime="text/csv",
                        icon=":material/download:",
                        use_container_width=True,
                        key=f"btn_export_csv_{key_suffix}",
                        help="ดาวน์โหลดทันที รองรับภาษาไทย UTF-8"
                    )
                else:
                    if has_cached_csv:
                        csv_data = st.session_state[csv_key]
                        size_mb = len(csv_data) / (1024 * 1024)
                        st.success(f"✅ ไฟล์ CSV พร้อมแล้ว ({size_mb:.1f} MB)")
                        st.download_button(
                            label=f"ดาวน์โหลด CSV ({n_rows:,} รายการ)",
                            data=csv_data,
                            file_name=f"{safe_prefix}.csv",
                            mime="text/csv",
                            icon=":material/download:",
                            use_container_width=True,
                            key=f"btn_export_csv_{key_suffix}",
                            help="คลิกเพื่อบันทึกไฟล์ CSV ลงในโฟลเดอร์ Downloads บนคอมพิวเตอร์ของคุณ"
                        )
                        if st.button("แปลงไฟล์ใหม่อีกครั้ง", key=f"btn_reset_csv_{key_suffix}", icon=":material/refresh:", help="คลิกเพื่อล้างและสร้างไฟล์ใหม่"):
                            st.session_state.pop(csv_key, None)
                            st.session_state.pop(csv_rows_key, None)
                            st.rerun()
                    else:
                        st.caption(f"ชุดข้อมูลใหญ่ ({n_rows:,} แถว) กดเพื่อเตรียมไฟล์")
                        if st.button("สร้างไฟล์ CSV (.csv)", icon=":material/description:", key=f"btn_prep_csv_{key_suffix}", use_container_width=True, help="คลิกเพื่อเริ่มแปลงข้อมูลเป็นไฟล์ CSV"):
                            with st.spinner(f"กำลังแปลงข้อมูล {n_rows:,} รายการเป็นไฟล์ CSV..."):
                                for _old_k in [
                                    k for k in st.session_state.keys()
                                    if str(k).startswith(("csv_data_", "csv_rows_", "excel_data_", "excel_rows_"))
                                ]:
                                    st.session_state.pop(_old_k, None)
                                csv_bytes = convert_df_to_csv(df_to_export)
                                st.session_state[csv_key] = csv_bytes
                                st.session_state[csv_rows_key] = data_fp
                                st.rerun()

            with c_exp2:
                excel_key = f"excel_data_{key_suffix}"
                excel_rows_key = f"excel_rows_{key_suffix}"

                if excel_key in st.session_state and st.session_state.get(excel_rows_key) != data_fp:
                    st.session_state.pop(excel_key, None)
                    st.session_state.pop(excel_rows_key, None)

                has_cached_excel = (
                    st.session_state.get(excel_rows_key) == data_fp and
                    excel_key in st.session_state and
                    isinstance(st.session_state[excel_key], bytes) and
                    len(st.session_state[excel_key]) > 0
                )

                if n_rows <= 10000:
                    st.download_button(
                        label="ดาวน์โหลด Excel (.xlsx)",
                        data=lambda: convert_df_to_excel(df_to_export),
                        file_name=f"{safe_prefix}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        icon=":material/download:",
                        use_container_width=True,
                        key=f"btn_export_excel_{key_suffix}"
                    )
                else:
                    if has_cached_excel:
                        excel_data = st.session_state[excel_key]
                        size_mb = len(excel_data) / (1024 * 1024)
                        st.success(f"✅ ไฟล์ Excel พร้อมแล้ว ({size_mb:.1f} MB)")
                        st.download_button(
                            label=f"ดาวน์โหลด Excel (.xlsx) ({n_rows:,} รายการ)",
                            data=excel_data,
                            file_name=f"{safe_prefix}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            icon=":material/download:",
                            use_container_width=True,
                            key=f"btn_export_excel_{key_suffix}",
                            help="คลิกเพื่อบันทึกไฟล์ Excel ลงในโฟลเดอร์ Downloads บนคอมพิวเตอร์ของคุณ"
                        )
                        if st.button("แปลงไฟล์ Excel ใหม่อีกครั้ง", key=f"btn_reset_excel_{key_suffix}", icon=":material/refresh:", help="คลิกเพื่อล้างและสร้างไฟล์ใหม่"):
                            st.session_state.pop(excel_key, None)
                            st.session_state.pop(excel_rows_key, None)
                            st.rerun()
                    else:
                        st.caption(f"แนะนำ **CSV** สำหรับ {n_rows:,} แถว (เร็วและเบาที่สุด)")
                        if st.button(f"เตรียมไฟล์ Excel ({n_rows:,} รายการ)", icon=":material/table_view:", key=f"btn_prep_excel_{key_suffix}", use_container_width=True, help="คลิกเพื่อเริ่มแปลงข้อมูลเป็นไฟล์ Excel (.xlsx)"):
                            with st.spinner(f"กำลังแปลงข้อมูล {n_rows:,} รายการเป็น Excel ด้วย xlsxwriter (โปรดรอสักครู่)..."):
                                for _old_k in [
                                    k for k in st.session_state.keys()
                                    if str(k).startswith(("csv_data_", "csv_rows_", "excel_data_", "excel_rows_"))
                                ]:
                                    st.session_state.pop(_old_k, None)
                                excel_bytes = convert_df_to_excel(df_to_export)
                                st.session_state[excel_key] = excel_bytes
                                st.session_state[excel_rows_key] = data_fp
                                st.rerun()
        else:
            st.info("ไม่มีข้อมูลสำหรับส่งออก")
