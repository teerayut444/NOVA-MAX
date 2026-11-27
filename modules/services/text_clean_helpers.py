"""
Self-contained Text, Location & PDPA Cleaning Helpers
=====================================================
Vendored into `modules/services/` so NOVA Dashboard runs identically on a clean
`git clone` deployment without depending on gitignored `Py Scraper/` or `tools/`.
"""

from __future__ import annotations

import json
import os
import re
import sys
import threading
import pandas as pd

_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_HELPER_LOCK = threading.RLock()


def _resolve_bundled_data_path(rel_path: str) -> str:
    """Resolve a workspace/data asset across normal checkout AND frozen PyInstaller .exe (_MEIPASS or external data/)."""
    fname = os.path.basename(rel_path)
    candidates = [os.path.join(_ROOT_DIR, rel_path)]
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        candidates.append(os.path.join(exe_dir, rel_path))
        candidates.append(os.path.join(exe_dir, fname))
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(os.path.join(meipass, rel_path))
        candidates.append(os.path.join(meipass, fname))
    candidates.append(os.path.join(_ROOT_DIR, fname))
    candidates.append(os.path.join(_ROOT_DIR, "Py Scraper", fname))
    for p in candidates:
        if p and os.path.exists(p):
            return p
    return candidates[0]

_AMP_EN_TO_TH_CACHE: dict[str, str] | None = None
_CENTROIDS_SET_CACHE: set[str] | None = None
_CANONICAL_PROJ_MAP_CACHE: dict[str, str] | None = None
_GEOJSON_DATA_CACHE: dict[str, dict] = {}
_THAI_DISTRICT_NAMES_CACHE: frozenset[str] | None = None


def _get_cached_geojson(rel_path: str) -> dict:
    """Load and parse a workspace GeoJSON file once per process (thread-safe)."""
    if rel_path in _GEOJSON_DATA_CACHE:
        return _GEOJSON_DATA_CACHE[rel_path]
    with _HELPER_LOCK:
        if rel_path in _GEOJSON_DATA_CACHE:
            return _GEOJSON_DATA_CACHE[rel_path]
        p = _resolve_bundled_data_path(rel_path)
        data: dict = {}
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    data = loaded
            except Exception:
                data = {}
        _GEOJSON_DATA_CACHE[rel_path] = data
        return data


def get_thai_district_names_set() -> frozenset[str]:
    """Lazily extract Thai district names from cached districts.geojson (excluding brand collisions)."""
    global _THAI_DISTRICT_NAMES_CACHE
    if _THAI_DISTRICT_NAMES_CACHE is not None:
        return _THAI_DISTRICT_NAMES_CACHE
    with _HELPER_LOCK:
        if _THAI_DISTRICT_NAMES_CACHE is not None:
            return _THAI_DISTRICT_NAMES_CACHE
        names: set[str] = set()
        gj = _get_cached_geojson("data/districts.geojson")
        for feat in gj.get("features", []):
            pr = feat.get("properties", {})
            a_th = str(pr.get("amp_th") or "").strip()
            if a_th:
                names.add(a_th)
                if a_th.startswith("เมือง") and len(a_th) > 5:
                    names.add(a_th[5:])
        names.add("ราชพฤกษ์")
        names.difference_update({"ชัยพฤกษ์", "บัวทอง", "ลุมพินี"})
        _THAI_DISTRICT_NAMES_CACHE = frozenset(names)
        return _THAI_DISTRICT_NAMES_CACHE

_PERSON_TITLE_CORE = (
    r"(?<!ท)(?<!เจ้า)(?<!นคร)นาย(?!หน้า|ายอาม|กเทศ|กองค์|กสมาคม|ก\s*อบต)|"
    r"ทนาย(?!ความ)|"
    r"นางสาว|น\.?ส\.|"
    r"นาง(?!รอง|เลิ้ง|แล|บวช|แก้ว|ตะเคียน|ฟ้า|พญา|ไม้)|"
    r"เด็กชาย|เด็กหญิง|ด\.ช\.|ด\.ญ\.|"
    r"ว่าที่\s*ร้อย|ว่าที่\s*ร\.ต\.|ว่าที่\s*ร\.ท\.|ว่าที่\s*ร\.อ\.|"
    r"(?:ร้อย|พัน|พล)\s*(?:ตรี|โท|เอก)|"
    r"(?:ร้อย|พัน|พล)\s*ตำรวจ\s*(?:ตรี|โท|เอก)|"
    r"(?:ร|พ|พล)\.ต\.[อตท]\.|(?:ร|พ|พล|น)\.[อตท]\.|"
    r"ดาบตำรวจ|ด\.ต\.|จ่าสิบ|จ\.ส\.[อตท]\.|สิบตำรวจ|ส\.ต\.[อตท]\.|"
    r"นายแพทย์|แพทย์หญิง|นพ\.|พญ\.|"
    r"ศ\.ดร\.|ผศ\.ดร\.|รศ\.ดร\.|ดร\.|ผศ\.|รศ\.|(?<![พคจม]\.)(?<![พคม])ศ\.|"
    r"คุณหญิง|ท่านผู้หญิง|ม\.ร\.ว\.|ม\.ล\.|หม่อมราชวงศ์|หม่อมหลวง|"
    r"มิสเตอร์(?!โดนัท)|มิสซิส|มิส(?!ทีน|เตอร์โดนัท)|\b(?:mr|mrs|miss|ms)(?:\.\s+|\.(?=$)|\s+)"
)

_PERSON_TITLES_PATTERN = re.compile(_PERSON_TITLE_CORE, re.IGNORECASE)

_PERSON_START_PATTERN = re.compile(
    r"^(?:(?:โดย|แทน|ในนาม|ผู้รับมอบอำนาจ)\s*)?(?:" + _PERSON_TITLE_CORE + r")",
    re.IGNORECASE,
)

_PERSON_SUFFIX_STRIP_PATTERN = re.compile(
    r"[\s,]+(?:(?:โดย|แทน|ในนาม|ผู้รับมอบอำนาจ)\s*)?(?:" + _PERSON_TITLE_CORE + r").*$",
    re.IGNORECASE,
)


def clean_plaintiff_name(name) -> str:
    """
    PDPA Privacy Compliance redactor for LED plaintiff names:
    - Personal names (นาย, นาง, นางสาว, military/police/medical titles, Mr/Mrs/Ms) -> ""
    - Legal entities with trailing representative person name -> keep legal entity only
    - Preserves public office titles like นายกเทศมนตรี, นายกองค์การ, นายกสมาคม (stripping trailing representative)
    """
    if name is None or pd.isna(name):
        return ""
    s = str(name).strip()
    if s.lower() in ("none", "null", "nan", "<na>", "-", ""):
        return ""
    if s.startswith(("นายกเทศมนตรี", "นายกองค์การ", "นายกสมาคม")):
        return _PERSON_SUFFIX_STRIP_PATTERN.sub("", s).strip()
    if _PERSON_START_PATTERN.search(s):
        return ""
    s_cleaned = _PERSON_SUFFIX_STRIP_PATTERN.sub("", s).strip()
    s_check = (
        s_cleaned.replace("ทนายความ", "")
        .replace("ทนาย", "")
        .replace("นครนายก", "")
        .replace("มิสทีน", "")
        .replace("มิสเตอร์โดนัท", "")
        .replace("นางแล", "")
        .replace("นายหน้า", "")
        .replace("นายายอาม", "")
    )
    if _PERSON_TITLES_PATTERN.search(s_check):
        return ""
    return s_cleaned


_COMMON_AMP_EN_ALIASES: dict[str, str] = {
    "sathorn": "สาทร",
    "sathon": "สาทร",
    "ladprao": "ลาดพร้าว",
    "latphrao": "ลาดพร้าว",
    "jatujak": "จตุจักร",
    "chatuchak": "จตุจักร",
    "sriracha": "ศรีราชา",
    "siracha": "ศรีราชา",
    "klongluang": "คลองหลวง",
    "khlongluang": "คลองหลวง",
    "huaykwang": "ห้วยขวาง",
    "huaikhwang": "ห้วยขวาง",
    "bangna": "บางนา",
    "watthana": "วัฒนา",
    "wattana": "วัฒนา",
    "phrakhanong": "พระโขนง",
    "prakanong": "พระโขนง",
    "pathumwan": "ปทุมวัน",
    "ratchathewi": "ราชเทวี",
    "phayathai": "พญาไท",
    "bangrak": "บางรัก",
    "khlongtoei": "คลองเตย",
    "klongtoey": "คลองเตย",
    "bangkapi": "บางกะปิ",
    "bangkhen": "บางเขน",
    "bangsue": "บางซื่อ",
    "suanluang": "สวนหลวง",
    "prawet": "ประเวศ",
    "bangphli": "บางพลี",
    "bangplee": "บางพลี",
    "pakkret": "ปากเกร็ด",
    "thanyaburi": "ธัญบุรี",
    "lamlukka": "ลำลูกกา",
    "banglamung": "บางละมุง",
    "pattaya": "บางละมุง",
    "huahin": "หัวหิน",
    "chaam": "ชะอำ",
}


def get_amp_en_to_th() -> dict[str, str]:
    """Load English->Thai district mapping once from local data/districts.geojson + common aliases."""
    global _AMP_EN_TO_TH_CACHE
    if _AMP_EN_TO_TH_CACHE is not None:
        return _AMP_EN_TO_TH_CACHE
    with _HELPER_LOCK:
        if _AMP_EN_TO_TH_CACHE is not None:
            return _AMP_EN_TO_TH_CACHE
        mapping: dict[str, str] = dict(_COMMON_AMP_EN_ALIASES)
        for rel in ("data/districts.geojson", "data/subdistricts.geojson"):
            try:
                data = _get_cached_geojson(rel)
                for feat in data.get("features", []):
                    props = feat.get("properties", {})
                    th = str(props.get("amp_th") or "").strip()
                    en = str(props.get("amp_en") or "").strip()
                    if th and en:
                        k = re.sub(r"[^a-zA-Z0-9]", "", en).lower()
                        mapping[k] = th
                        if en.lower().startswith("mueang "):
                            base_en = re.sub(r"[^a-zA-Z0-9]", "", en[7:]).lower()
                            if base_en not in mapping:
                                mapping[base_en] = th
                if mapping:
                    break
            except Exception:
                pass
        _AMP_EN_TO_TH_CACHE = mapping
        return _AMP_EN_TO_TH_CACHE


def translate_amphoe_en_to_th(val) -> str:
    """Translate English amphoe names to Thai or strip bilingual English noise."""
    if not val or pd.isna(val):
        return ""
    s = str(val).strip()
    if not re.search(r"[a-zA-Z]", s):
        return s

    amp_map = get_amp_en_to_th()
    s_clean = re.sub(r"^(?:amphoe|amphur|khet|district)\s+", "", s, flags=re.I).strip()
    s_norm = re.sub(r"^muang\s+", "mueang", s_clean, flags=re.I)
    k = re.sub(r"[^a-zA-Z0-9]", "", s_norm).lower()
    if k in amp_map:
        return amp_map[k]

    m_en = re.search(r"([a-zA-Z]+(?:[\s\-]+[a-zA-Z]+)*)", s)
    if m_en:
        sub_k = re.sub(r"^(?:amphoe|amphur|khet|district)\s+", "", m_en.group(1), flags=re.I).strip()
        sub_norm = re.sub(r"^muang\s+", "mueang", sub_k, flags=re.I)
        sub_key = re.sub(r"[^a-zA-Z0-9]", "", sub_norm).lower()
        if sub_key in amp_map:
            return amp_map[sub_key]

    if re.search(r"[ก-๙]", s):
        # Strip ASCII-only parentheticals first so Thai names inside parentheses e.g. 'Amphoe X (เมืองเก่า)' are kept
        s_th = re.sub(r"[\(\[\{][a-zA-Z0-9\s,.\-_/]*[\)\]\}]", "", s)
        s_th = re.sub(r"[a-zA-Z]+", "", s_th)
        s_th = re.sub(r"[\(\[\{\)\]\}\/\\_:,.]+", " ", s_th)
        s_th = re.sub(r"^[\s\-]+|[\s\-]+$", "", s_th)
        s_th = re.sub(r"\s+", " ", s_th).strip()
        if re.search(r"[ก-๙]", s_th):
            return s_th

    return ""


def get_known_centroids_set() -> set[str]:
    """Return cached set of 'lat,lon' strings (5-decimal rounded) for Thai administrative centroids."""
    global _CENTROIDS_SET_CACHE
    if _CENTROIDS_SET_CACHE is not None:
        return _CENTROIDS_SET_CACHE
    with _HELPER_LOCK:
        if _CENTROIDS_SET_CACHE is not None:
            return _CENTROIDS_SET_CACHE
        coords_set: set[str] = set()
        try:
            from shapely.geometry import shape
            for rel in ("data/districts.geojson", "data/subdistricts.geojson"):
                data = _get_cached_geojson(rel)
                if not data:
                    continue
                for feat in data.get("features", []):
                    geom = feat.get("geometry")
                    if not geom:
                        continue
                    try:
                        poly = shape(geom)
                        if not poly.is_empty:
                            c = poly.centroid
                            coords_set.add(f"{round(float(c.y), 5)},{round(float(c.x), 5)}")
                            rp = poly.representative_point()
                            coords_set.add(f"{round(float(rp.y), 5)},{round(float(rp.x), 5)}")
                    except Exception:
                        pass
        except Exception:
            pass
        _CENTROIDS_SET_CACHE = coords_set
        return _CENTROIDS_SET_CACHE


def _get_canonical_proj_map() -> dict[str, str]:
    global _CANONICAL_PROJ_MAP_CACHE
    if _CANONICAL_PROJ_MAP_CACHE is not None:
        return _CANONICAL_PROJ_MAP_CACHE
    with _HELPER_LOCK:
        if _CANONICAL_PROJ_MAP_CACHE is not None:
            return _CANONICAL_PROJ_MAP_CACHE
        mapping: dict[str, str] = {}
        p = _resolve_bundled_data_path(os.path.join("data", "project_canonical_mapping.json"))
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                if isinstance(raw, dict):
                    mapping = {str(k).strip(): str(v).strip() for k, v in raw.items() if k and v}
            except Exception:
                pass
        _CANONICAL_PROJ_MAP_CACHE = mapping
        return _CANONICAL_PROJ_MAP_CACHE


_STANDALONE_AD_PREFIX_RE = re.compile(
    r"^(?:ขายด่วน!?|ขายถูก!?|ขายบ้าน|ขายคอนโด|ขายทาวน์โฮม|ขายทาวน์เฮ้าส์|ขาย)\s*[:\-]?\s*",
    re.IGNORECASE,
)
_STANDALONE_CANON_LOOKUP_PREFIX_RE = re.compile(
    r"^(?:โครงการ|หมู่บ้านจัดสรร|หมู่บ้าน|มบ\.|คอนโดมิเนียม|คอนโด|อาคารชุด)\s*[:\-]?\s*",
    re.IGNORECASE,
)
_STANDALONE_AD_NOISE_RE = re.compile(
    r"\s*(?:ราคาถูก(?:มาก)?|พร้อมอยู่|ฟรีโอน|ด่วน!?|เจ้าของขายเอง|ทำเลดี|หลุดจอง|ลดราคา).*$",
    re.IGNORECASE,
)


def clean_project_name_standalone(raw_name, **kwargs) -> str:
    """Clean project name standalone using canonical mapping and safe ad-noise cleanup."""
    if raw_name is None or pd.isna(raw_name):
        return ""
    s = str(raw_name).strip()
    if not s or s.lower() in ("nan", "none", "null", "<na>", "-"):
        return ""
    s = re.sub(r"[\u200b\ufeff]", "", s)
    s = re.sub(r"^[\'\"“‘\s]+|[\'\"”’\s]+$", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    canon = _get_canonical_proj_map()
    if s in canon:
        return canon[s]
    s_clean = _STANDALONE_AD_PREFIX_RE.sub("", s).strip(" :-")
    s_clean = _STANDALONE_AD_NOISE_RE.sub("", s_clean).strip(" :-")
    s_clean = re.sub(r"\s+", " ", s_clean).strip()
    if s_clean in canon:
        return canon[s_clean]
    s_lookup = _STANDALONE_CANON_LOOKUP_PREFIX_RE.sub("", s_clean).strip(" :-")
    if s_lookup and s_lookup in canon:
        return canon[s_lookup]
    return s_clean or s
