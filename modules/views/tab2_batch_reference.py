"""Tab 2 Batch Reference Import panel (isolated from global Tab 1-5 data) and Grouped CSV/Excel Export UI."""

import datetime
import html
import json
import pandas as pd
import streamlit as st

from modules.services.batch_reference_service import (
    build_batch_grouped_export_df,
    build_map_batch_refs_payload,
    compute_batch_ref_fingerprint,
    convert_grouped_df_to_excel,
    parse_batch_reference_upload,
)
from modules.services.data_loader import _safe_json_inline, get_data_mtime
from modules.services.export_service import (
    MAX_UPLOAD_BYTES,
    MAX_UPLOAD_ROWS,
    _get_uploaded_file_size,
    _sanitize_filename_prefix,
)

_fragment_decorator = getattr(st, "fragment", lambda f: f)
_TH_TZ = datetime.timezone(datetime.timedelta(hours=7))


def _push_batch_refs_to_map_iframe(items, radius_km=None):
    """Pushes the current batch reference list into the live Tab 2 map iframe without reloading the map."""
    payload_obj = {
        "items": items or [],
        "radius_km": float(radius_km) if radius_km is not None else None,
        "ts": int(datetime.datetime.now(_TH_TZ).timestamp() * 1000),
    }
    payload_json = _safe_json_inline(payload_obj)
    st.html(
        f"""
        <script>
        (function() {{
            try {{
                var data = {payload_json};
                var pWin = window.parent || window;
                pWin.__NOVA_BATCH_REFS__ = data;
                var targetOrigin = (pWin.location && pWin.location.origin && pWin.location.origin !== 'null')
                    ? pWin.location.origin
                    : (window.location ? window.location.origin : '*');
                var pdoc = pWin.document;
                if (!pdoc) return;
                var iframes = pdoc.querySelectorAll('.st-key-tab2_map_stage iframe, .st-key-tab_map iframe');
                for (var i = 0; i < iframes.length; i++) {{
                    try {{
                        var cw = iframes[i].contentWindow;
                        if (!cw) continue;
                        if (typeof cw.setBatchReferenceItems === 'function') {{
                            cw.setBatchReferenceItems(data.items, data.radius_km);
                        }} else {{
                            cw.postMessage({{ action: 'set_batch_refs', items: data.items, radius_km: data.radius_km }}, targetOrigin);
                        }}
                    }} catch (_e) {{}}
                }}
            }} catch (_e) {{}}
        }})();
        </script>
        """,
        unsafe_allow_javascript=True,
    )


def _clear_batch_reference_state():
    """Clears all Tab 2 Batch Reference session state cleanly."""
    for k in (
        "_tab2_batch_ref_uid",
        "_tab2_batch_ref_name",
        "_tab2_batch_ref_df",
        "_tab2_batch_ref_extra_cols",
        "_tab2_batch_ref_audit",
        "_tab2_batch_ref_map_items",
        "_tab2_batch_export_cache",
        "_tab2_batch_file_bytes_cache",
        "tab2_batch_active_ref",
    ):
        st.session_state.pop(k, None)
    st.session_state["_tab2_batch_uploader_gen"] = int(st.session_state.get("_tab2_batch_uploader_gen", 0)) + 1
    st.session_state["_tab2_batch_pending_clear_push"] = True


def _render_batch_column_guide():
    with st.expander("คู่มือคอลัมน์สำหรับไฟล์ชุดทรัพย์อ้างอิง (คลิกดูรายละเอียด)", icon=":material/table_chart:", expanded=False):
        st.markdown(
            """
| คอลัมน์ | สถานะ | รายละเอียด |
|---|---|---|
| `ละติจูด`, `ลองจิจูด` | **จำเป็น** | พิกัด WGS84 ในประเทศไทย (รองรับชื่อ `lat`/`lon`/`lng` ด้วย) |
| `ประเภททรัพย์` | **จำเป็น** | ใช้จับคู่กับทรัพย์ประเภทเดียวกันในฐานข้อมูล (Normalize ชื่ออัตโนมัติ เช่น `คอนโด` → `ห้องชุดพักอาศัย`, `ทาวน์โฮม` → `ทาวน์เฮ้าส์`) |
| `รหัสทรัพย์` | แนะนำ | ใช้อ้างอิงชื่อกลุ่มและแสดงใน Popup บนแผนที่ (หากไม่มี ระบบสร้าง `REF-001`, `REF-002` ให้อัตโนมัติ) |
| `ราคา`, `เนื้อที่ (ตร.ว.)` / `ไร่-งาน-ตร.ว.`, `พื้นที่ใช้สอย (ตร.ม.)` | แนะนำ | ใช้แสดงในแถวทรัพย์อ้างอิงและคำนวณราคาต่อหน่วย |
"""
        )


@_fragment_decorator
def render_tab2_batch_reference_panel(df_db, is_dark_mode=False):
    """Renders the compact Batch Reference Import & Grouped Export card at the bottom of Tab 2."""
    bg_card = "rgba(15, 23, 42, 0.55)" if is_dark_mode else "#f8fafc"
    border_card = "rgba(16, 185, 129, 0.35)" if is_dark_mode else "rgba(5, 150, 105, 0.28)"
    title_c = "#34d399" if is_dark_mode else "#047857"
    sub_c = "#cbd5e1" if is_dark_mode else "#475569"
    pill_bg = "rgba(16, 185, 129, 0.16)" if is_dark_mode else "rgba(16, 185, 129, 0.10)"

    st.markdown("<div id='tab2-batch-reference-section' style='margin-top: 22px;'></div>", unsafe_allow_html=True)

    has_loaded = (
        isinstance(st.session_state.get("_tab2_batch_ref_df"), pd.DataFrame)
        and not st.session_state["_tab2_batch_ref_df"].empty
    )
    loaded_cnt = len(st.session_state["_tab2_batch_ref_df"]) if has_loaded else 0
    loaded_name = str(st.session_state.get("_tab2_batch_ref_name") or "")

    badge_html = (
        f"<span style='background:{pill_bg}; color:{title_c}; font-size:0.78rem; font-weight:700; "
        f"padding:3px 10px; border-radius:999px; border:1px solid {border_card};'>"
        f"<i class='fa-solid fa-circle-check' style='margin-right:4px;'></i>"
        f"โหลดแล้ว {loaded_cnt:,} ทรัพย์อ้างอิง ({html.escape(loaded_name)})</span>"
        if has_loaded
        else f"<span style='background:{pill_bg}; color:{title_c}; font-size:0.76rem; font-weight:700; "
             f"padding:3px 10px; border-radius:999px; border:1px solid {border_card};'>"
             f"แยกอิสระจากข้อมูลหลัก Tab 1–5</span>"
    )

    st.markdown(
        f"""
        <div style="background:{bg_card}; border:1.5px solid {border_card}; border-top:3.5px solid #10b981;
                    border-radius:14px; padding:14px 18px 10px 18px; margin-bottom:10px;
                    box-shadow:0 4px 16px rgba(16,185,129,0.06);">
            <div style="display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:8px;">
                <div style="font-size:1.05rem; font-weight:800; color:{title_c}; display:flex; align-items:center; gap:8px;">
                    <i class="fa-solid fa-layer-group"></i>
                    <span>นำเข้าไฟล์ชุดทรัพย์อ้างอิง (Batch Reference & Grouped Export)</span>
                </div>
                {badge_html}
            </div>
            <div style="font-size:0.83rem; color:{sub_c}; margin-top:4px; line-height:1.45;">
                อัปโหลดไฟล์ Excel / CSV เพื่อใช้ทุกแถวเป็นทรัพย์อ้างอิง — กดเลือกดูทีละชิ้นผ่าน <b>Popup กลางล่างสุดของแผนที่</b>
                หรือส่งออกไฟล์ <b>Excel (.xlsx) แบบจัดกลุ่มพับเก็บ [+]</b> พร้อมคอลัมน์ค่าเฉลี่ย &amp; Median 6 คอลัมน์ในแถวทรัพย์อ้างอิงได้ทันที
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_up, col_guide = st.columns([0.62, 0.38])
    with col_up:
        up_gen = int(st.session_state.get("_tab2_batch_uploader_gen", 0))
        uploaded_file = st.file_uploader(
            "อัปโหลดไฟล์ชุดทรัพย์อ้างอิง (Excel / CSV)",
            type=["xlsx", "xls", "csv"],
            key=f"tab2_batch_ref_uploader_{up_gen}",
            label_visibility="collapsed",
            help=(
                f"รองรับไม่เกิน {MAX_UPLOAD_BYTES // (1024 * 1024)} MB / {MAX_UPLOAD_ROWS:,} แถว "
                f"(คอลัมน์หลัก: ละติจูด, ลองจิจูด, ประเภททรัพย์, รหัสทรัพย์, ราคา, เนื้อที่)"
            ),
        )
    with col_guide:
        _render_batch_column_guide()
        if has_loaded:
            if st.button(
                "ล้างไฟล์ชุดทรัพย์อ้างอิง",
                icon=":material/delete_sweep:",
                key="btn_clear_tab2_batch_ref",
                width="stretch",
            ):
                _clear_batch_reference_state()
                st.rerun(scope="fragment")

    # Handle newly uploaded file
    if uploaded_file is not None:
        f_size = _get_uploaded_file_size(uploaded_file)
        f_name = str(getattr(uploaded_file, "name", "") or "batch_refs")
        upload_uid = getattr(uploaded_file, "file_id", None) or f"{f_name.lower()}:{f_size}"
        if st.session_state.get("_tab2_batch_ref_uid") != upload_uid:
            try:
                with st.spinner("กำลังอ่านและเตรียมชุดทรัพย์อ้างอิง..."):
                    ref_df, extra_cols, audit = parse_batch_reference_upload(uploaded_file)
                if ref_df.empty:
                    st.warning("ไม่พบแถวข้อมูลในไฟล์ที่อัปโหลด")
                else:
                    st.session_state["_tab2_batch_ref_uid"] = upload_uid
                    st.session_state["_tab2_batch_ref_name"] = f_name
                    st.session_state["_tab2_batch_ref_df"] = ref_df
                    st.session_state["_tab2_batch_ref_extra_cols"] = extra_cols
                    st.session_state["_tab2_batch_ref_audit"] = audit
                    st.session_state["_tab2_batch_ref_map_items"] = build_map_batch_refs_payload(ref_df)
                    st.session_state.pop("_tab2_batch_export_cache", None)
                    st.session_state.pop("_tab2_batch_file_bytes_cache", None)
                    has_loaded = True
            except Exception as exc:
                st.error(f"ไม่สามารถอ่านไฟล์ได้: {exc}")

    # Sync cleared state to map iframe if user clicked Clear
    if st.session_state.pop("_tab2_batch_pending_clear_push", False):
        _push_batch_refs_to_map_iframe([], radius_km=None)

    if not has_loaded:
        return

    ref_df = st.session_state["_tab2_batch_ref_df"]
    extra_cols = st.session_state.get("_tab2_batch_ref_extra_cols", [])
    audit = st.session_state.get("_tab2_batch_ref_audit", {})
    map_items = st.session_state.get("_tab2_batch_ref_map_items", [])

    # Sync loaded items to the live bottom-center map popup
    default_map_rad = float(st.session_state.get("tab2_ref_radius", 5.0) or 5.0)
    default_map_rad = min(50.0, max(0.05, default_map_rad))
    _push_batch_refs_to_map_iframe(map_items, radius_km=default_map_rad)

    # Validation / audit summary
    missing_req = audit.get("missing_required", [])
    if missing_req:
        st.warning(
            f"ไม่พบคอลัมน์จำเป็นบางรายการในไฟล์: {', '.join(f'`{c}`' for c in missing_req)} "
            f"— แถวที่ไม่มีพิกัดจะยังถูกเก็บไว้ในไฟล์ Export พร้อมระบุสถานะ",
            icon=":material/warning:",
        )

    valid_cnt = int(audit.get("valid_coord_rows", 0))
    invalid_cnt = int(audit.get("invalid_coord_rows", 0))
    prop_types_found = audit.get("prop_types", [])
    extra_note = f" • คอลัมน์พิเศษที่เก็บรักษา: {len(extra_cols)} คอลัมน์" if extra_cols else ""
    st.info(
        f"**พร้อมใช้งานบนแผนที่แล้ว:** เปิดดูแต่ละทรัพย์ได้ทันทีที่ **Popup ตรงกลางล่างสุดของแผนที่ด้านบน** "
        f"(พิกัดพร้อมใช้ **{valid_cnt:,}** / {len(ref_df):,} รายการ"
        + (f", พิกัดว่าง/ผิดปกติ **{invalid_cnt:,}** รายการ" if invalid_cnt > 0 else "")
        + f" • พบ **{len(prop_types_found)}** ประเภททรัพย์{extra_note})",
        icon=":material/my_location:",
    )

    # Controls row for Batch Export
    avail_companies = (
        sorted({
            str(c).strip()
            for c in df_db["บริษัท"].dropna().unique()
            if str(c).strip() not in ("", "-", "nan", "None", "<NA>")
        })
        if (df_db is not None and not df_db.empty and "บริษัท" in df_db.columns)
        else []
    )

    c_rad, c_co, c_opts = st.columns([0.22, 0.38, 0.40])
    with c_rad:
        batch_radius = st.number_input(
            "รัศมีค้นหา (กม.)",
            min_value=0.05,
            max_value=50.0,
            value=default_map_rad,
            step=0.5,
            format="%.2f",
            key="tab2_batch_export_radius",
            help="ค่าเริ่มต้นดึงตามแถบรัศมีบนแผนที่ Tab 2 และสามารถปรับแยกสำหรับ Batch Export ได้",
        )
    with c_co:
        selected_cos = st.multiselect(
            "กรองบริษัท/แหล่งข้อมูล (ว่าง = ทุกบริษัท)",
            options=avail_companies,
            default=[],
            key="tab2_batch_export_companies",
            placeholder="ทุกบริษัทในฐานข้อมูลหลัก",
        )
    with c_opts:
        st.markdown("<div style='height:4px;'></div>", unsafe_allow_html=True)
        oc1, oc2 = st.columns(2)
        with oc1:
            match_same_type = st.checkbox(
                "เฉพาะประเภทเดียวกัน",
                value=True,
                key="tab2_batch_match_same_type",
                help="จับคู่เฉพาะทรัพย์ใกล้เคียงที่มีประเภททรัพย์ตรงกับแถวอ้างอิงแต่ละชิ้น",
            )
            exclude_centroids = st.checkbox(
                "ตัดพิกัดกึ่งกลาง (Centroid)",
                value=True,
                key="tab2_batch_exclude_centroids",
                help="ตัดทรัพย์ที่ใช้พิกัดกึ่งกลางตำบล/อำเภอโดยประมาณออกจากการเปรียบเทียบ (เหมือนค่าเริ่มต้น Tab 2)",
            )
        with oc2:
            exclude_self = st.checkbox(
                "ตัดตัวทรัพย์อ้างอิงเองออก",
                value=True,
                key="tab2_batch_exclude_self",
                help="ไม่นำตัวทรัพย์อ้างอิงเองมาคิดค่าเฉลี่ย/Median หากตรวจพบซ้ำในฐานข้อมูลหลัก",
            )

    # Compute (cached by fingerprint)
    data_mtime = get_data_mtime()
    batch_fp = compute_batch_ref_fingerprint(
        ref_df,
        batch_radius,
        selected_cos,
        exclude_centroids,
        match_same_type,
        exclude_self,
        data_mtime,
    )
    cached_res = st.session_state.get("_tab2_batch_export_cache")
    if isinstance(cached_res, dict) and cached_res.get("fp") == batch_fp:
        grouped_df = cached_res["df"]
        meta = cached_res["meta"]
    else:
        with st.spinner(f"กำลังดึงข้อมูลรัศมี {batch_radius:.2f} กม. และคำนวณค่าเฉลี่ย/Median ทั้ง {len(ref_df):,} ทรัพย์อ้างอิง..."):
            grouped_df, meta = build_batch_grouped_export_df(
                ref_df,
                df_db,
                radius_km=batch_radius,
                extra_cols=extra_cols,
                companies=selected_cos,
                exclude_centroids=exclude_centroids,
                match_same_type=match_same_type,
                exclude_self=exclude_self,
            )
        st.session_state["_tab2_batch_export_cache"] = {
            "fp": batch_fp,
            "df": grouped_df,
            "meta": meta,
        }
        st.session_state.pop("_tab2_batch_file_bytes_cache", None)

    # Compact KPI summary of batch result
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("กลุ่มทรัพย์อ้างอิง", f"{meta['total_refs']:,} กลุ่ม")
    m2.metric("กลุ่มที่พบทรัพย์ใกล้เคียง", f"{meta['matched_refs']:,} กลุ่ม")
    m3.metric("กลุ่มที่พบ 0 รายการ / ไม่มีพิกัด", f"{meta['zero_match_refs'] + meta['invalid_coord_refs']:,} กลุ่ม")
    m4.metric("จำนวนแถวทั้งหมดที่จะส่งออก", f"{meta['total_output_rows']:,} แถว")

    # Download CSV & Excel buttons (lazy cached bytes per fingerprint)
    base_name = _sanitize_filename_prefix(
        str(st.session_state.get("_tab2_batch_ref_name", "batch_ref")).rsplit(".", 1)[0],
        default="batch_reference",
    )
    date_tag = datetime.datetime.now(_TH_TZ).strftime("%Y%m%d")
    rad_tag = f"{batch_radius:.2f}".rstrip("0").rstrip(".").replace(".", "p")
    fname_stem = f"{base_name}_grouped_{rad_tag}km_{date_tag}"

    # Prepare cache dict on the main Streamlit thread so the download callable never touches st.session_state on asyncio_0
    bytes_cache = st.session_state.get("_tab2_batch_file_bytes_cache")
    if not isinstance(bytes_cache, dict) or bytes_cache.get("fp") != batch_fp:
        bytes_cache = {"fp": batch_fp}
        st.session_state["_tab2_batch_file_bytes_cache"] = bytes_cache

    def _get_cached_xlsx(_cache=bytes_cache, _df=grouped_df):
        if "xlsx" not in _cache:
            _cache["xlsx"] = convert_grouped_df_to_excel(_df)
        return _cache["xlsx"]

    st.download_button(
        "ดาวน์โหลด Excel แบบจัดกลุ่มพับเก็บ [+] (.xlsx)",
        icon=":material/table_view:",
        data=_get_cached_xlsx,
        file_name=f"{fname_stem}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
        width="stretch",
        key=f"btn_dl_batch_xlsx_{batch_fp}",
    )
