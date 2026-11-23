import os
import re
import ast
import math
import datetime
import threading
import urllib.parse
from pathlib import Path
import numpy as np
import pandas as pd
try:
    import streamlit as st
except ImportError:
    class _NoOpStreamlit:
        @staticmethod
        def cache_resource(*args, **kwargs):
            def _decorator(fn):
                return fn
            return _decorator

        @staticmethod
        def cache_data(*args, **kwargs):
            def _decorator(fn):
                return fn
            return _decorator

    st = _NoOpStreamlit()

from modules.config.constants import (
    PROPERTY_TYPE_MAPPING,
    SALE_TYPE_MAPPING,
    PROVINCE_TO_REGION,
)
from modules.services.text_clean_helpers import (
    clean_plaintiff_name,
    clean_project_name_standalone,
    get_known_centroids_set,
    translate_amphoe_en_to_th,
)

_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_PROJ_CACHE_LOCK = threading.Lock()
_TH_TZ = datetime.timezone(datetime.timedelta(hours=7))
_LED_LEGAL_COMPANIES = frozenset({"LED LEGAL", "LED_LEGAL", "LED_SOLD", "LED SOLD"})
_SAFE_LINK_PREFIXES = ("https://", "http://", "/app/static/")


def clean_project_name(name, **kwargs):
    """Self-contained project name cleaner (independent of gitignored Py Scraper/)."""
    return clean_project_name_standalone(name, **kwargs)


@st.cache_resource(show_spinner=False)
def _load_readonly_project_clean_cache():
    """Load precomputed project_name_clean_cache.parquet once as a read-only dict."""
    cache_path = os.path.join(_ROOT_DIR, "data", "project_name_clean_cache.parquet")
    if not os.path.exists(cache_path):
        return {}
    try:
        c_df = pd.read_parquet(cache_path)
        if "raw_project" in c_df.columns and "clean_project" in c_df.columns:
            return dict(zip(c_df["raw_project"].astype(str), c_df["clean_project"]))
    except Exception:
        pass
    return {}

_BRAND_TAG_PATTERNS = [
    (re.compile(r'eastgate|อีสท์เกต', re.I), 'Eastgate / อีสท์เกต'),
    (re.compile(r'ไอดีโอ|ไอดิโอ|ไอเดีย|ideo|idio|ไอดิโอ้|ไอดีโอ้', re.I), 'IDEO / ไอดิโอ'),
    (re.compile(r'ลุมพ[ิีึื]น[ิีึื]|lumpini|lpn', re.I), 'LPN / Lumpini'),
    (re.compile(r'พฤกษา|พฤษภา|พฤษา|พึกษา|พฤกสา|pruksa|ps\b', re.I), 'Pruksa / PS'),
    (re.compile(r'[ศส]ุ[ภพ]าลัย|supalai|spali', re.I), 'Supalai / ศุภาลัย'),
    (re.compile(r'แสนสิริ|sansiri|siri\b', re.I), 'Sansiri / แสนสิริ'),
    (re.compile(r'แอสปา[ยร์]+|aspire', re.I), 'Aspire / แอสปาย'),
    (re.compile(r'ดีคอนโด|dcondo|d\s*condo', re.I), 'Dcondo'),
    (re.compile(r'เดอะ\s*เบส|the\s*base', re.I), 'The Base'),
    (re.compile(r'ไลฟ์|life\b', re.I), 'Life'),
    (re.compile(r'ริ[ทธ]ึ่?[มม์]|rhythm', re.I), 'Rhythm'),
    (re.compile(r'ไนท์บริด[จช์]+|knightsbridge', re.I), 'Knightsbridge'),
    (re.compile(r'พลัม|plum', re.I), 'Plum'),
    (re.compile(r'คาซ่า|casa', re.I), 'Casa'),
    (re.compile(r'เซ็?นทริ[คก]|centric', re.I), 'Centric'),
    (re.compile(r'คอนโดเล็?ต|condolette', re.I), 'Condolette'),
    (re.compile(r'ยู\s*ดีไลท์|udelight', re.I), 'U Delight'),
    (re.compile(r'แชปเตอร์\s*วัน|chapter\s*one', re.I), 'Chapter One'),
    (re.compile(r'รีเจ้?นท์?|regent', re.I), 'Regent'),
    (re.compile(r'โนเบิ?ล|noble', re.I), 'Noble'),
    (re.compile(r'พาร์?คแลน[ด์]*|parkland', re.I), 'Parkland'),
    (re.compile(r'แอชตัน|ashton', re.I), 'Ashton'),
    (re.compile(r'เอล?ลิโอ|elio', re.I), 'Elio'),
    (re.compile(r'ยูนิโอ|unio', re.I), 'Unio'),
    (re.compile(r'โมดิ[ซส]|modiz', re.I), 'Modiz'),
    (re.compile(r'แอทโม[ซส]|atmoz', re.I), 'Atmoz'),
    (re.compile(r'เคฟ|kave', re.I), 'Kave'),
    (re.compile(r'แชมเบอร์?ส?|chambers', re.I), 'Chambers / แชมเบอร์ส'),
    (re.compile(r'เดอะ\s*คิวบ์?|the\s*cube', re.I), 'The Cube / เดอะคิวบ์'),
    (re.compile(r'พลีโน่?|pleno', re.I), 'Pleno / พลีโน่'),
    (re.compile(r'บริทาเนีย|britania', re.I), 'Britania'),
    (re.compile(r'ออริจิ้?น|origin', re.I), 'Origin / ออริจิ้น'),
    (re.compile(r'ริช\s*พาร์?ค|rich\s*park', re.I), 'Rich Park / ริชพาร์ค'),
    (re.compile(r'เดอะ\s*ทรี|the\s*tree', re.I), 'The Tree / เดอะทรี'),
    (re.compile(r'เมโทร\s*ลักซ์?|metro\s*luxe', re.I), 'Metro Luxe / เมโทรลักซ์'),
    (re.compile(r'เดอะ\s*ทรัสต์?|the\s*trust', re.I), 'The Trust / เดอะทรัสต์'),
    (re.compile(r'ชวนชื่?น|chuanchuen', re.I), 'Chuanchuen / ชวนชื่น'),
    (re.compile(r'เพอร์เฟ[็คกต์]+|perfect', re.I), 'Perfect / เพอร์เฟค'),
    (re.compile(r'[ภพ]ัสสร|passorn', re.I), 'Passorn / ภัสสร'),
    (re.compile(r'มั?ณฑนา|mantana', re.I), 'Mantana / มัณฑนา'),
    (re.compile(r'ชัยพฤก[ษ์ษา]+|chaiyapruek', re.I), 'Chaiyapruek / ชัยพฤกษ์'),
    (re.compile(r'วิลลาจจิ?โอ|villaggio', re.I), 'Villaggio'),
    (re.compile(r'อินดี้?|indy\b', re.I), 'Indy / อินดี้'),
    (re.compile(r'เซ็?นโทร|centro', re.I), 'Centro / เซนโทร'),
    (re.compile(r'บ้านกลางเมือง|baan\s*klang\s*muang', re.I), 'Baan Klang Muang'),
    (re.compile(r'บ้านกลางกรุง|baan\s*klang\s*krung', re.I), 'Baan Klang Krung'),
    (re.compile(r'เดอะ\s*คอนเนค|the\s*connect', re.I), 'The Connect'),
    (re.compile(r'พฤกษาวิลล์|pruksa\s*ville', re.I), 'Pruksa Ville'),
    (re.compile(r'บ้านพฤกษา|baan\s*pruksa', re.I), 'Baan Pruksa'),
    (re.compile(r'เดอะ\s*ซิตี้|the\s*city', re.I), 'The City'),
    (re.compile(r'เดอะ\s*ไลน์|the\s*line', re.I), 'The Line'),
]

def get_brand_search_tag(raw_name):
    """Returns alias search tag (e.g. IDEO / ไอดิโอ, LPN / Lumpini) to ensure instant search in Streamlit dropdown."""
    name_str = str(raw_name).strip()
    for pat, tag in _BRAND_TAG_PATTERNS:
        if pat.search(name_str):
            return tag
    return ""

_INVALID_PROJECT_SET = {
    '', '-', '--', '---', '.', '..', '...', 'nan', 'null', 'none', 'undefined',
    'ไม่ระบุ', 'ไม่มีชื่อ', 'ไม่มีข้อมูล', 'โครงการไม่มีชื่อ', 'ไม่มี',
    'โครงการ', 'หมู่บ้าน', 'คอนโด', 'บ้านเดี่ยว', 'ที่ดิน', 'ทาวน์โฮม', 'อาคารพาณิชย์', 'ห้องชุด',
    'บ้าน', 'ตึก', 'ทาวน์เฮ้าส์', 'อพาร์ทเม้นท์', 'อาคารชุด',
    # Scraper-polluted generic / truncated / non-project words
    'ราคา', 'มิเนียม', 'จัดสรร', 'บ้านจัดสรร', 'ที่ดินจัดสรร', 'รายย่อย', 'เปล่า',
    'ใหม่', 'ติด', 'ติดทะเล', 'ติดถนน', 'หรู', 'เทล', 'เอส', 'โฮม',
    'ห้องสวย', 'ห้องใหญ่', 'ห้องมุม', 'หลังมุม', 'แปลงมุม', 'ถมแล้ว', 'วิวทะเล',
    'ออมสิน', 'call', 'modern', 'tropical', 'boho style', 'low rise', 'high rise',
    'ขนาดใหญ่', 'เลต', 'สอบถามโทร', 'บ้าน สตูดิโอ', 'สำหรับ ขาย คอนโด', 'สำหรับขายคอนโด',
    'พร้อมสิ่งปลูกสร้าง', 'การเคหะ', 'การเคหะแห่งชาติ', 'in1',
}
_ROOM_SCRAPE_PAT = re.compile(r'^\d+\s*ห้อง(นอน)?(\s*\d+\s*ห้องน้ำ)?', re.I)
_STUDIO_PAT = re.compile(r'^(สตูดิโอ|ห้องนอน|ห้องน้ำ|studio)$', re.I)
_AD_PITCH_PAT = re.compile(r'^(?:ขายด่วน|ขายถูก|ขายบ้าน|ขายคอนโด|ให้เช่า|ต้องการขาย|ลดราคา|ขาย|เช่า|เซ้ง|ด่วน)(?:\s|$|[ก-๙0-9])', re.I)
_COORD_PAT = re.compile(r'^-?\d{1,2}\.\d+[\s,]+-?\d{2,3}\.\d+$')
_DIGIT_ONLY_PAT = re.compile(r'^[\d.,/\s-]+$')
_GENERIC_TYPE_NUM_PAT = re.compile(r'^(บ้านเดี่ยว|บ้านแฝด|บ้าน|ทาวน์โฮม|ทาวน์เฮ้าส์|ทาวน์เฮาท์|คอนโด|ห้องชุด|ที่ดิน|อาคารพาณิชย์|ตึกแถว|เดี่ยว|เฮ้าส์|เฮาส์|เฮาท์|พาณิชย์|แฝด|แถว)\s*\d+(?:\s*-?\s*(?:ห้องนอน|ห้องน้ำ|ชั้น))?$', re.I)
_FLOOR_DESC_PAT = re.compile(r'^(?:บ้านเดี่ยว|บ้านแฝด|บ้านตึก|บ้านไม้|บ้านครึ่งตึกครึ่งไม้|บ้าน|ทาวน์เฮ้าส์|ทาวน์โฮม|ทาวเฮ้าส์|ทาวน์ฮ้าส์|ทาวน์เฮาท์|ตึกแถว|อาคารพาณิชย์|อาคารโกดัง|วิลล่า|คอนโด)?\s*\d+(?:\.\d+)?\s*ชั้น(?:$|\s|ครึ่ง|[0-9])', re.I)
_AD_NEAR_PAT = re.compile(r'^(?:ใกล้|ติด)\s*(?:bts|mrt|แอร์พอร์ต|ทางด่วน|ถนน|สถานี|ห้าง|รถไฟฟ้า|ทะเล|หาด)', re.I)
_PRICE_IN_NAME_PAT = re.compile(r'(?:ราคา|ขายเพียง|ลดเหลือ|ผ่อนเพียง|ตรว\.ละ|วาละ|ขาย|เช่า)\s*\d+(?:\.\d+)?\s*(?:ลบ|ล้าน|แสน|บาท|บ(?:\.|\s|$))')
_ROOM_CNT_PAT = re.compile(r'(?:\d+\s*-?\s*(?:ห้องนอน|ห้องน้ำ)|\d+\s*นอน\s*\d+\s*น้ำ|ห้อง(?:นอน|น้ำ)?\s*\d+\s*ห้อง)')
_AREA_SCRAPE_PAT = re.compile(r'^\d+[\d.,/-]*\s*(?:ตร\.?ว\.?|ตร\.?ม\.?|ตารางวา|ตารางเมตร|ไร่|วา)(?:$|\s|\d)', re.I)
_AREA_MID_PAT = re.compile(r'\d+[\d.,]*\s*(?:ตร\.?ว\.?|ตร\.?ม\.?|ตารางวา|ตารางเมตร)(?:$|\s|\d)', re.I)
_POSTAL_PREFIX_PAT = re.compile(r'^\d{5}\s*(?:บ้าน|ทาวน์|อาคาร|ที่ดิน|คอนโด|เดอะ|มบ\.|หมู่บ้าน|ทาวเฮ้าส์)', re.I)
_AD_BUZZWORDS_PAT = re.compile(r'(?:ขายด่วน|ด่วนมาก|ลดกระหน่ำ|ขายถูกที่สุด|ราคาถูกที่สุด|รีโนเวทใหม่|รีโนเวทแล้ว|ตกแต่งใหม่ทั้งหลัง|พร้อมอยู่ทันที|กู้เต็ม|กู้ได้เต็ม|ฟรีโอน|ขายขาดทุน|เจ้าของขายเอง|ผ่อนตรง|รับผ่อนตรง|agent welcomed|ขายยกแปลง)', re.I)
_CONTACT_PAT = re.compile(r'(?:โทร|tel|contact|line\s*id)\s*[:\.]?\s*\d', re.I)
_SCRAPED_DIST_PRICE_PAT = re.compile(r'ใน(?:อำเภอ|อ\.)\s*[ก-๙]+')
_AD_ADJECTIVE_PAT = re.compile(r'(?:พร้อมอยู่|ตกแต่งครบ|เฟอร์นิเจอร์|ฟรีโอน|วิวสวย|วิวทะเล|วิวสระ|ทำเลทอง)')
_SOCIAL_HANDLE_PAT = re.compile(r'^@[a-zA-Z0-9_.\-]+')
_CORRUPT_INST_BANK_PAT = re.compile(r'(?:สถาบัน|ถาบัน|าบัน|บัน)?(?:โดย|ดย)\s*(?:ghb|gsb|bam|sam|ktb|scb|kbank)\b', re.I)
_AD_DESC_START_PAT = re.compile(r'^(?:สำหรับ\s*ขาย|สอบถาม|ติดต่อ|วิวทะเล|วิวเขา|พร้อมที่ดิน|พร้อมสิ่งปลูกสร้าง|บ้าน\s*สตูดิโอ|\+\s*บ้าน|private\s+house\b|pool\s+villa\b|house\s+for\s+sale\b|condo\s+for\s+sale\b)', re.I)

# Pure Thai location / zone / road / province tokens (prevents zone labels like 'พัทยา บางแสน ชลบุรี สัตหีบ' from masquerading as projects)
_THAI_ZONE_LOCATION_TOKENS = frozenset({
    # Provinces & nicknames
    'กรุงเทพ', 'กรุงเทพฯ', 'กรุงเทพมหานคร', 'กทม', 'กทม.', 'โคราช', 'อยุธยา', 'มหาชัย', 'แปดริ้ว', 'ปากน้ำ',
    'กระบี่', 'กาญจนบุรี', 'กาฬสินธุ์', 'กำแพงเพชร', 'ขอนแก่น', 'จันทบุรี', 'ฉะเชิงเทรา', 'ชลบุรี',
    'ชัยนาท', 'ชัยภูมิ', 'ชุมพร', 'เชียงราย', 'เชียงใหม่', 'ตรัง', 'ตราด', 'ตาก', 'นครนายก',
    'นครปฐม', 'นครพนม', 'นครราชสีมา', 'นครศรีธรรมราช', 'นครสวรรค์', 'นนทบุรี', 'นราธิวาส', 'น่าน',
    'บึงกาฬ', 'บุรีรัมย์', 'ปทุมธานี', 'ประจวบคีรีขันธ์', 'ปราจีนบุรี', 'ปัตตานี', 'พระนครศรีอยุธยา',
    'พะเยา', 'พังงา', 'พัทลุง', 'พิจิตร', 'พิษณุโลก', 'เพชรบุรี', 'เพชรบูรณ์', 'แพร่', 'ภูเก็ต',
    'มหาสารคาม', 'มุกดาหาร', 'แม่ฮ่องสอน', 'ยโสธร', 'ยะลา', 'ร้อยเอ็ด', 'ระนอง', 'ระยอง', 'ราชบุรี',
    'ลพบุรี', 'ลำปาง', 'ลำพูน', 'เลย', 'ศรีสะเกษ', 'สกลนคร', 'สงขลา', 'สตูล', 'สมุทรปราการ',
    'สมุทรสงคราม', 'สมุทรสาคร', 'สระแก้ว', 'สระบุรี', 'สิงห์บุรี', 'สุโขทัย', 'สุพรรณบุรี',
    'สุราษฎร์ธานี', 'สุรินทร์', 'หนองคาย', 'หนองบัวลำภู', 'อ่างทอง', 'อำนาจเจริญ', 'อุดรธานี',
    'อุตรดิตถ์', 'อุทัยธานี', 'อุบลราชธานี',
    # Major tourist / regional zones
    'พัทยา', 'บางแสน', 'สัตหีบ', 'ศรีราชา', 'แหลมฉบัง', 'บ้านบึง', 'บ่อวิน', 'ปลวกแดง', 'มาบตาพุด',
    'จอมเทียน', 'นาเกลือ', 'หัวหิน', 'ชะอำ', 'ปราณบุรี', 'เขาใหญ่', 'ปากช่อง', 'สมุย', 'เกาะสมุย',
    'ป่าตอง', 'กะทู้', 'ถลาง', 'กะรน', 'กมลา', 'ราไวย์', 'ฉลอง', 'หาดใหญ่', 'นิมมาน', 'แม่ริม',
    'หางดง', 'สันทราย', 'สันกำแพง', 'สารภี', 'ดอยสะเก็ด',
    'huahin', 'pattaya', 'bangsaen', 'samui', 'phuket', 'chiangmai', 'korat', 'rangsit', 'salaya',
    'khonkaen', 'rayong', 'chonburi', 'prachuap', 'khiri', 'khan', 'naklua', 'jomtien', 'patong', 'hatyai',
    # Bangkok & Vicinity roads, zones, transit hubs, landmarks
    'สุขุมวิท', 'อโศก', 'ทองหล่อ', 'เอกมัย', 'พร้อมพงษ์', 'นานา', 'เพลินจิต', 'ชิดลม', 'วิทยุ', 'ราชดำริ', 'หลังสวน',
    'พระโขนง', 'อ่อนนุช', 'บางจาก', 'ปุณณวิถี', 'อุดมสุข', 'บางนา', 'แบริ่ง', 'ลาซาล', 'สำโรง', 'เทพารักษ์',
    'ศรีนครินทร์', 'พัฒนาการ', 'กิ่งแก้ว', 'บางพลี', 'บางปู', 'สุวรรณภูมิ', 'ลาดกระบัง', 'ร่มเกล้า', 'มีนบุรี',
    'หนองจอก', 'คลองสามวา', 'ประเวศ', 'สวนหลวง',
    'สีลม', 'สาทร', 'สาธร', 'ศาลาแดง', 'บางรัก', 'สี่พระยา', 'เจริญกรุง', 'เจริญนคร', 'คลองสาน',
    'วงเวียนใหญ่', 'กรุงธนบุรี', 'ธนบุรี', 'ตลาดพลู', 'ท่าพระ', 'วุฒากาศ', 'บางหว้า', 'ตากสิน', 'พระราม',
    'สาธุประดิษฐ์', 'ยานนาวา', 'บางคอแหลม', 'คลองเตย', 'กล้วยน้ำไท', 'ราษฎร์บูรณะ', 'สุขสวัสดิ์',
    'ประชาอุทิศ', 'ทุ่งครุ', 'บางขุนเทียน', 'ท่าข้าม', 'เอกชัย', 'บางบอน', 'จอมทอง', 'กัลปพฤกษ์', 'กาญจนาภิเษก',
    'สยาม', 'จุฬา', 'สามย่าน', 'ปทุมวัน', 'ราชเทวี', 'พญาไท', 'อนุสาวรีย์', 'อารีย์', 'สนามเป้า', 'สะพานควาย',
    'จตุจักร', 'หมอชิต', 'ประดิพัทธ์', 'สุทธิสาร', 'อินทามระ', 'ดินแดง', 'ห้วยขวาง', 'รัชดา', 'รัชดาภิเษก',
    'เพชรบุรี', 'เพชรบุรีตัดใหม่', 'rca', 'มักกะสัน', 'ประตูน้ำ', 'เยาวราช', 'บางลำพู', 'ปิ่นเกล้า',
    'จรัญสนิทวงศ์', 'จรัญฯ', 'บางพลัด', 'บางอ้อ', 'บางโพ', 'บางซื่อ', 'เตาปูน', 'วงศ์สว่าง', 'ประชาชื่น',
    'วิภาวดี', 'พหลโยธิน', 'รัชโยธิน', 'เกษตร', 'เกษตรศาสตร์', 'เสนานิคม', 'ลาดปลาเค้า', 'วังหิน',
    'โชคชัย', 'ลาดพร้าว', 'แฮปปี้แลนด์', 'บางกะปิ', 'หัวหมาก', 'รามคำแหง', 'ลำสาลี', 'เสรีไทย', 'นิด้า',
    'นวมินทร์', 'รามอินทรา', 'เลียบทางด่วน', 'เลียบทางด่วนรามอินทรา', 'เลียบด่วน', 'เลียบด่วนรามอินทรา',
    'ประดิษฐ์มนูธรรม', 'วัชรพล', 'สายไหม', 'สุขาภิบาล', 'หทัยราษฎร์', 'คู้บอน', 'ปัญญาอินทรา',
    'บางเขน', 'สะพานใหม่', 'ดอนเมือง', 'สรงประภา', 'หลักสี่', 'แจ้งวัฒนะ', 'เมืองทอง', 'ปากเกร็ด',
    'ติวานนท์', 'งามวงศ์วาน', 'พงษ์เพชร', 'แคราย', 'รัตนาธิเบศร์', 'สนามบินน้ำ', 'พระนั่งเกล้า',
    'บางใหญ่', 'บางบัวทอง', 'บางกรวย', 'ไทรน้อย', 'นครอินทร์', 'ตลิ่งชัน', 'ทวีวัฒนา', 'พุทธมณฑล',
    'ศาลายา', 'บางแค', 'เพชรเกษม', 'หนองแขม', 'บางแวก', 'ภาษีเจริญ', 'พรานนก', 'ศิริราช', 'บรมราชชนนี',
    'รังสิต', 'ธรรมศาสตร์', 'คลองหลวง', 'ธัญบุรี', 'ลำลูกกา', 'นวนคร', 'ตลาดไท', 'ฟิวเจอร์พาร์ค',
    'เซ็นทรัลลาดพร้าว', 'เซ็นทรัลเวสต์เกต', 'เซ็นทรัลบางนา', 'เซ็นทรัลพระราม', 'เมกะบางนา',
    'เดอะมอลล์บางกะปิ', 'เดอะมอลล์งามวงศ์วาน',
    'ทางด่วน', 'ถนน', 'ซอย', 'แยก', 'คลอง', 'สาย', 'โซน', 'ย่าน', 'ฝั่งธน', 'ฝั่งธนบุรี',
    'ใจกลางเมือง', 'ในเมือง', 'นอกเมือง',
    # English equivalents
    'sukhumvit', 'asoke', 'asok', 'thonglor', 'ekkamai', 'ekamai', 'silom', 'sathorn', 'sathon',
    'rama', 'ladprao', 'latphrao', 'ratchada', 'bangna', 'onnut', 'udomsuk', 'bearing', 'lasalle',
    'ramintra', 'nawamin', 'ramkhamhaeng', 'pinklao', 'charan', 'ratchaphruek', 'chaengwattana',
    'tiwanon', 'ngamwongwan', 'rattanathibet', 'phaholyothin', 'srinakarin', 'pattanakarn',
    'phetkasem', 'bangkae', 'bangyai', 'bangbuathong', 'donmueang', 'lamlukka', 'saimai',
    'minburi', 'latkrabang', 'prawet',
})

# Single-word location tokens that double as real housing-estate names (protected when standalone; still caught by spatial coherence if scattered)
_AMBIGUOUS_SINGLE_LOCATION_NAMES = frozenset({
    'เมืองทอง', 'บางแสน', 'สุขสวัสดิ์', 'เกษตร', 'นานา', 'บางพระ', 'ศรีสุนทร',
})
# Housing-estate brand prefixes that look like roads/districts (e.g. 'ชัยพฤกษ์ ศรีนครินทร์', 'ราชพฤกษ์ สุวรรณภูมิ')
_PROTECTED_ESTATE_BRAND_PREFIXES = frozenset({
    'ชัยพฤกษ์', 'ราชพฤกษ์', 'บัวทอง', 'ลุมพินี', 'เมืองทอง',
})
_NUMBERED_ADDRESS_CONDO_PAT = re.compile(r'^\d{2,4}\s+[ก-๙a-zA-Z]')
_ROAD_WITH_NUM_PAT = re.compile(
    r'^(?:พระราม\s*[1-9]|โชคชัย\s*4|ลาดพร้าว\s*\d+|สุขุมวิท\s*\d+|พหลโยธิน\s*\d+|รามคำแหง\s*\d+|เพชรเกษม\s*\d+|'
    r'รัชดา(?:ภิเษก)?\s*\d+|จรัญ(?:สนิทวงศ์)?\s*\d+|อ่อนนุช\s*\d+|บางนา[\s\-]*ตราด(?:\s*กม\.?\s*\d+)?|'
    r'huahin\s*\d+|หัวหิน\s*\d+|สุขาภิบาล\s*\d+|พุทธมณฑล\s*สาย\s*\d+|สาย\s*\d+)$',
    re.I,
)
_LOCATION_SPLIT_PAT = re.compile(r'[\s\-–—/,|&]+')
_ADMIN_PREFIX_STRIP_PAT = re.compile(r'^(?:จ\.|จังหวัด|อ\.|อำเภอ|เขต|ต\.|ตำบล|แขวง|ถ\.|ถนน|ซ\.|ซอย|แยก|ย่าน|โซน)')
_PURE_TOKEN_NUM_PAT = re.compile(r'^\d+[a-z]?$', re.I)

_DISTRICTS_NAME_SET_CACHE = None


def _get_thai_district_names_set():
    """Lazily loads Thai district/amphoe names from data/districts.geojson (excluding estate-brand collisions)."""
    global _DISTRICTS_NAME_SET_CACHE
    if _DISTRICTS_NAME_SET_CACHE is not None:
        return _DISTRICTS_NAME_SET_CACHE
    names = set()
    try:
        import json
        p = os.path.join(_ROOT_DIR, "data", "districts.geojson")
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                gj = json.load(f)
            for feat in gj.get("features", []):
                pr = feat.get("properties", {})
                a_th = str(pr.get("amp_th") or "").strip()
                if a_th:
                    names.add(a_th)
                    if a_th.startswith("เมือง") and len(a_th) > 5:
                        names.add(a_th[5:])
    except Exception:
        pass
    names.add('ราชพฤกษ์')
    names.difference_update({'ชัยพฤกษ์', 'บัวทอง', 'ลุมพินี'})
    _DISTRICTS_NAME_SET_CACHE = frozenset(names)
    return _DISTRICTS_NAME_SET_CACHE


def is_pure_location_project_name(name):
    """Returns True if `name` consists solely of Thai location/zone/road/province/district tokens rather than a real project name."""
    if not name or pd.isna(name):
        return False
    s = str(name).strip()
    s = re.sub(r'^[\'"“‘\s]+|[\'"”’\s]+$', '', s)
    if not s:
        return False
    # Protect real numbered-address luxury condos e.g. '185 ราชดำริ', '28 ชิดลม', '168 สุขุมวิท 36'
    if _NUMBERED_ADDRESS_CONDO_PAT.match(s):
        return False
    if _ROAD_WITH_NUM_PAT.match(s):
        return True

    raw_tokens = [t.strip().lower() for t in _LOCATION_SPLIT_PAT.split(s) if t.strip()]
    if not raw_tokens:
        return False

    non_num = []
    has_num = False
    for tok in raw_tokens:
        if _PURE_TOKEN_NUM_PAT.match(tok):
            has_num = True
            continue
        t_clean = _ADMIN_PREFIX_STRIP_PAT.sub('', tok).strip()
        if t_clean:
            non_num.append(t_clean)

    if not non_num:
        return False

    # Single location token without trailing number (e.g. 'มหาชัย', 'โคราช', 'สมุย', 'เอกชัย', 'สะพานควาย', 'รัชดา')
    if len(non_num) == 1 and not has_num:
        t0 = non_num[0]
        return t0 in _THAI_ZONE_LOCATION_TOKENS and t0 not in _AMBIGUOUS_SINGLE_LOCATION_NAMES

    # Multi-token zone combinations (e.g. 'พัทยา บางแสน ชลบุรี สัตหีบ', 'นวมินทร์ รามอินทรา', 'พระราม 5 ราชพฤกษ์')
    if len(non_num) >= 2:
        if non_num[0] in _PROTECTED_ESTATE_BRAND_PREFIXES:
            return False
        amp_tokens = _get_thai_district_names_set()
        return all((t in _THAI_ZONE_LOCATION_TOKENS or t in amp_tokens) for t in non_num)

    return False


def is_invalid_project_name(name):
    """Detects invalid, corrupt, pure-location, or scraper-polluted project names."""
    if not name or pd.isna(name):
        return True
    p = str(name).strip()
    p = re.sub(r'^[\'"“‘\s]+|[\'"”’\s]+$', '', p)
    if not p or p.lower() in _INVALID_PROJECT_SET or len(p) <= 2:
        return True
    if _SOCIAL_HANDLE_PAT.match(p) or _CORRUPT_INST_BANK_PAT.search(p) or _AD_DESC_START_PAT.search(p):
        return True
    if _COORD_PAT.match(p) or _DIGIT_ONLY_PAT.match(p):
        return True
    if _GENERIC_TYPE_NUM_PAT.match(p) or _FLOOR_DESC_PAT.search(p) or _AD_NEAR_PAT.search(p):
        return True
    if _POSTAL_PREFIX_PAT.search(p) or _AREA_SCRAPE_PAT.search(p):
        return True
    if _ROOM_SCRAPE_PAT.match(p) or _STUDIO_PAT.match(p) or _AD_PITCH_PAT.search(p):
        return True
    if re.search(r'ขาย(?:คอนโด|บ้าน|ทาวน์|ที่ดิน)', p, re.I):
        return True
    if _PRICE_IN_NAME_PAT.search(p) or _ROOM_CNT_PAT.search(p) or _AD_BUZZWORDS_PAT.search(p) or _CONTACT_PAT.search(p):
        return True
    if _AREA_MID_PAT.search(p) and len(p) > 15:
        return True
    if _SCRAPED_DIST_PRICE_PAT.search(p) and 'ราคา' in p:
        return True
    if _AD_ADJECTIVE_PAT.search(p) and len(p) > 20:
        return True
    if is_pure_location_project_name(p):
        return True
    return False


def find_spatially_scattered_project_keys(
    df,
    group_col='norm_project_name',
    lat_col='ละติจูด',
    lon_col='ลองจิจูด',
    centroid_col='is_centroid',
    max_median_km=5.0,
    max_pair_km=10.0,
    max_p75_km=None,
    min_p75_count=3,
):
    """Returns set of project group keys whose valid property coordinates are scattered too far apart to be one project.

    Uses spatial median distance (robust against 1-2 mis-geocoded outliers) and prefers non-centroid coordinates
    whenever a group has >= 2 non-centroid points.
    - For 2-point groups: flags if pairwise distance > `max_pair_km` (median distance to midpoint > max_pair_km / 2).
    - For >=3-point groups: flags if median distance from spatial median > `max_median_km`,
      or (when `max_p75_km` is set and count >= `min_p75_count`) if 75th-percentile distance > `max_p75_km`.
    """
    if df is None or df.empty or lat_col not in df.columns or lon_col not in df.columns:
        return set()

    if isinstance(group_col, (list, tuple)):
        cols_req = list(group_col)
    else:
        cols_req = [group_col]
    if any(c not in df.columns for c in cols_req):
        return set()

    lat_s = pd.to_numeric(df[lat_col], errors='coerce')
    lon_s = pd.to_numeric(df[lon_col], errors='coerce')
    valid_geo = (
        lat_s.notna()
        & lon_s.notna()
        & np.isfinite(lat_s)
        & np.isfinite(lon_s)
        & lat_s.between(5.0, 21.0)
        & lon_s.between(97.0, 106.0)
    )
    if not valid_geo.any():
        return set()

    work = pd.DataFrame({'_lat': lat_s.loc[valid_geo].to_numpy(dtype='float64'), '_lon': lon_s.loc[valid_geo].to_numpy(dtype='float64')})
    for c in cols_req:
        s_c = df.loc[valid_geo, c]
        if isinstance(s_c.dtype, pd.CategoricalDtype):
            work[c] = s_c.astype(object).fillna('').astype(str).str.strip().to_numpy()
        else:
            work[c] = s_c.fillna('').astype(str).str.strip().to_numpy()
    non_empty = np.ones(len(work), dtype=bool)
    for c in cols_req:
        non_empty &= (work[c].to_numpy() != '')
    if not non_empty.any():
        return set()
    work = work.loc[non_empty].copy()

    if centroid_col and centroid_col in df.columns:
        c_raw = df.loc[valid_geo, centroid_col]
        if pd.api.types.is_bool_dtype(c_raw.dtype):
            is_cen = c_raw.fillna(False).to_numpy(dtype=bool)[non_empty]
        else:
            is_cen = c_raw.astype(object).fillna('').astype(str).str.strip().str.lower().isin({'true', '1', '1.0', 'yes', 't'}).to_numpy(dtype=bool)[non_empty]
        work['_cen'] = is_cen
        nc_counts = work.loc[~work['_cen']].groupby(cols_req, sort=False).size()
        if len(nc_counts) > 0:
            nc_multi_keys = set(nc_counts[nc_counts >= 2].index)
            if nc_multi_keys:
                if len(cols_req) == 1:
                    in_nc_multi = work[cols_req[0]].isin(nc_multi_keys).to_numpy()
                else:
                    in_nc_multi = pd.MultiIndex.from_frame(work[cols_req]).isin(nc_multi_keys)
                work = work.loc[(~work['_cen'].to_numpy()) | (~in_nc_multi)]

    if work.empty:
        return set()

    grp_sizes = work.groupby(cols_req, sort=False)['_lat'].transform('size')
    work = work.loc[grp_sizes >= 2]
    if work.empty:
        return set()

    g = work.groupby(cols_req, sort=False)
    med_lat = g['_lat'].transform('median').to_numpy(dtype='float64')
    med_lon = g['_lon'].transform('median').to_numpy(dtype='float64')
    dlat_km = (work['_lat'].to_numpy(dtype='float64') - med_lat) * 111.0
    dlon_km = (work['_lon'].to_numpy(dtype='float64') - med_lon) * 111.0 * np.cos(np.radians(med_lat))
    work = work.assign(_dist_km=np.hypot(dlat_km, dlon_km))

    g2 = work.groupby(cols_req, sort=False)
    cnts = g2['_dist_km'].count()
    med_d = g2['_dist_km'].median()

    pair_half_km = float(max_pair_km) / 2.0
    scattered_mask = ((cnts == 2) & (med_d > pair_half_km)) | ((cnts >= 3) & (med_d > float(max_median_km)))
    if max_p75_km is not None:
        p75_d = g2['_dist_km'].quantile(0.75)
        scattered_mask |= ((cnts >= int(min_p75_count)) & (p75_d > float(max_p75_km)))

    return set(scattered_mask[scattered_mask].index.tolist())

def clean_display_project_name(name):
    """Normalizes formatting of project names for beautiful, clean presentation without typos/punctuation noise."""
    if not name:
        return ""
    txt = str(name).strip()
    txt = re.sub(r'^[\'"“‘\s]+|[\'"”’\s]+$', '', txt)
    if ' : ' in txt:
        parts = txt.split(' : ')
        txt = parts[1] if len(parts) > 1 else parts[0]
    
    # Standardize common brand typos and spacing in display
    txt = re.sub(r'ลุมพินี\s*ทาวน์ชิป\s*รังสิต', 'ลุมพินี ทาวน์ชิป รังสิต', txt)
    txt = re.sub(r'ทางน์ชิป|ทาวชิป|ทาวน์ซิป|ทาวนชิป', 'ทาวน์ชิป', txt)
    txt = re.sub(r'township\b', 'ทาวน์ชิป', txt, flags=re.I)
    txt = re.sub(r'\bc[\s,\.]*d[\s,\.]*e\b', 'ซีดีอี', txt, flags=re.I)
    txt = re.sub(r'\ba[\s,\.]*b\b', 'เอบี', txt, flags=re.I)
    txt = re.sub(r'\bc[\s,\.]*d\b', 'ซีดี', txt, flags=re.I)
    txt = re.sub(r'\be[\s,\.]*f\b', 'อีเอฟ', txt, flags=re.I)
    txt = re.sub(r'\bf[\s,\.]*g\b', 'เอฟจี', txt, flags=re.I)

    # Standardize popular developer names in display
    txt = re.sub(r'เดอะ\s*คิว(?:บ์|บ)', 'เดอะคิวบ์', txt)
    txt = re.sub(r'เดอะ\s*คอนเน[คกต์]+', 'เดอะ คอนเนค', txt)
    txt = re.sub(r'เดอะ\s*เบส', 'เดอะเบส', txt)
    txt = re.sub(r'เดอะ\s*ทรี', 'เดอะทรี', txt)
    txt = re.sub(r'เดอะ\s*ทรัสต์?', 'เดอะทรัสต์', txt)
    txt = re.sub(r'รีเจ้?น[ท์]*', 'รีเจ้นท์', txt)
    txt = re.sub(r'ไอดีโอ้?|ไอดิโอ้?|ไอเดีย', 'ไอดีโอ', txt)
    txt = re.sub(r'พฤกษ์?ลดา', 'พฤกษ์ลดา', txt)
    txt = re.sub(r'มั?ณฑนา', 'มัณฑนา', txt)
    txt = re.sub(r'ชัยพฤก[ษ์ษา]+', 'ชัยพฤกษ์', txt)
    txt = re.sub(r'เพอร์?เฟ[็คกต์]+', 'เพอร์เฟค', txt)
    txt = re.sub(r'วิลลาจจิ?โอ', 'วิลลาจจิโอ', txt)
    txt = re.sub(r'อินดี้?', 'อินดี้', txt)

    # Standardize comma-separated single Thai/English letters e.g. A,B,C -> ABC (avoid merging words like Q.House / St.Louis)
    txt = re.sub(r'(?<![ก-๙a-zA-Z])([ก-๙a-zA-Z])\s*,\s*([ก-๙a-zA-Z])\s*,\s*([ก-๙a-zA-Z])(?![ก-๙a-zA-Z])', r'\1\2\3', txt)
    txt = re.sub(r'(?<![ก-๙a-zA-Z])([ก-๙a-zA-Z])\s*,\s*([ก-๙a-zA-Z])(?![ก-๙a-zA-Z])', r'\1\2', txt)
    # Standardize dots between single letters e.g. A.B.C -> ABC (preserving Q.House, St.Louis)
    txt = re.sub(r'(?<![ก-๙a-zA-Z])([ก-๙a-zA-Z])\s*\.\s*([ก-๙a-zA-Z])\s*\.\s*([ก-๙a-zA-Z])(?![ก-๙a-zA-Z])', r'\1\2\3', txt)
    txt = re.sub(r'(?<![ก-๙a-zA-Z])([ก-๙a-zA-Z])\s*\.\s*([ก-๙a-zA-Z])(?![ก-๙a-zA-Z])', r'\1\2', txt)
    # Standardize spaces around hyphens and numbers
    txt = re.sub(r'\s*-\s*', '-', txt)
    txt = re.sub(r'คลอง\s*(\d+)', r'คลอง \1', txt)
    txt = re.sub(r'\s+', ' ', txt).strip()
    return txt

_PREFIX_PAT = re.compile(
    r'^(คอนโด\s*โครงการ|โครงการ\s*คอนโด|โครงการ\s*หมู่บ้าน|อาคารชุด|คอนโดมิเนียม|มีเนียม|โครงการ|หมู่บ้าน|คอนโด|บ้านเดี่ยว|บ้านแฝด|บ้าน(?!กลางเมือง|กลางกรุง|พฤกษา)|ทาวน์โฮม|ทาวน์เฮ้าส์|ขายคอนโด)\s*',
    re.I
)
_SUFFIX_PAT = re.compile(
    r'(\[.*?\]|\(.*?\)|\[[^\]]*$|\([^)]*$|,\s*(กรุงเทพมหานคร|กรุงเทพฯ|กรุงเทพ|นนทบุรี|ปทุมธานี|สมุทรปราการ|ชลบุรี|เชียงใหม่|ระยอง|ภูเก็ต).*$|[\s\-_/]+(?:อาคาร|ตึก)\s+[a-zA-Z0-9ก-๙]\s+ชั้น\s*\d+.*$|[\s\-_/]+ชั้น\s*\d+.*$|ชั้น\s*\d+.*$|(?:^|\s)(?:ติด|ใกล้)\s*(?:bts|mrt).*$)',
    re.I
)
_SPACE_CLEAN = re.compile(r'[\s\-_/.,:;()\[\]{}]+')

_NORM_PATTERNS = [
    (re.compile(r'ทางน์ชิป|ทาวชิป|ทาวน์ซิป|ทาวนชิป|\btownship\b', re.I), 'ทาวน์ชิป'),
    (re.compile(r'ซี[,\.\s]*ดี[,\.\s]*อี[,\.\s]*เอฟ|\bc[\s,\.]*d[\s,\.]*e[\s,\.]*f\b', re.I), 'ซีดีอีเอฟ'),
    (re.compile(r'ซี[,\.\s]*ดี[,\.\s]*อี|\bc[\s,\.]*d[\s,\.]*e\b', re.I), 'ซีดีอี'),
    (re.compile(r'เอ[,\.\s]*บี|\ba[\s,\.]*b\b', re.I), 'เอบี'),
    (re.compile(r'ซี[,\.\s]*ดี|\bc[\s,\.]*d\b', re.I), 'ซีดี'),
    (re.compile(r'อี[,\.\s]*เอฟ|\be[\s,\.]*f\b', re.I), 'อีเอฟ'),
    (re.compile(r'เอฟ[,\.\s]*จี|\bf[\s,\.]*g\b', re.I), 'เอฟจี'),
    (re.compile(r'บี[.\s]*เค[.\s]*|\bb[\s\.]*k\b', re.I), 'บีเค'),
    (re.compile(r'เอส[.\s]*ซี[.\s]*|\bs[\s\.]*c\b', re.I), 'เอสซี'),
    (re.compile(r'\bklong\b', re.I), 'คลอง'),
    (re.compile(r'\brangsit\b', re.I), 'รังสิต'),
    (re.compile(r'\bsukhumvit\b', re.I), 'สุขุมวิท'),
    (re.compile(r'\brama\b', re.I), 'พระราม'),
    (re.compile(r'\b(?:sathorn|sathon)\b', re.I), 'สาทร'),
    (re.compile(r'\b(?:asoke|asok)\b', re.I), 'อโศก'),
    (re.compile(r'\b(?:ladprao|latphrao)\b', re.I), 'ลาดพร้าว'),
    (re.compile(r'\btiwanon\b', re.I), 'ติวานนท์'),
    (re.compile(r'\b(?:bangna|bang\s*na)\b', re.I), 'บางนา'),
    (re.compile(r'\bratchada\b', re.I), 'รัชดา'),
    (re.compile(r'\b(?:thonglor|thong\s*lo)\b', re.I), 'ทองหล่อ'),
    (re.compile(r'\b(?:ekkamai|ekamai)\b', re.I), 'เอกมัย'),
    (re.compile(r'\bsilom\b', re.I), 'สีลม'),
    (re.compile(r'\bmobi\b', re.I), 'โมบิ'),
    (re.compile(r'\bville\b', re.I), 'วิลล์'),
    (re.compile(r'\bpark\b|ปาร์ค', re.I), 'พาร์ค'),
    (re.compile(r'\bplace\b', re.I), 'เพลส'),
    (re.compile(r'\bprime\b', re.I), 'ไพร์ม'),
    (re.compile(r'\bveranda\b', re.I), 'เวอเรนด้า'),
    (re.compile(r'\bcampus\b', re.I), 'แคมปัส'),
    (re.compile(r'\bresort\b', re.I), 'รีสอร์ท'),
    (re.compile(r'\bstation\b', re.I), 'สเตชั่น'),
    (re.compile(r'\bcondo\b', re.I), 'คอนโด'),
    (re.compile(r'ไอดีโอ้?|ไอดิโอ้?|ไอเดีย|\b(?:ideo|idio)\b', re.I), 'ไอดีโอ'),
    (re.compile(r'ลุมพ[ิีึื]น[ิีึื]|\b(?:lumpini|lpn)\b', re.I), 'ลุมพินี'),
    (re.compile(r'พฤกษาวิลล์?|\bpruksa\s*ville\b', re.I), 'พฤกษาวิลล์'),
    (re.compile(r'บ้านพฤกษา|\bbaan\s*pruksa\b', re.I), 'บ้านพฤกษา'),
    (re.compile(r'พฤกษา|พฤษภา|พฤษา|พึกษา|พฤกสา|พฤษษา|พฤกษภ|\b(?:pruksa|ps)\b', re.I), 'พฤกษา'),
    (re.compile(r'[ศส]ุ[ภพ]าลัย|\b(?:supalai|spali)\b', re.I), 'ศุภาลัย'),
    (re.compile(r'แสนสิริ|\b(?:sansiri|siri)\b', re.I), 'แสนสิริ'),
    (re.compile(r'แอสปา[ยร์]+|\baspire\b', re.I), 'แอสปาย'),
    (re.compile(r'ดีคอนโด|\b(?:dcondo|d\s*condo)\b', re.I), 'ดีคอนโด'),
    (re.compile(r'เดอะ\s*เบส|\bthe\s*base\b', re.I), 'เดอะเบส'),
    (re.compile(r'ไลฟ์|\blife\b', re.I), 'ไลฟ์'),
    (re.compile(r'ริ[ทธ]ึ่?[มม์]|\brhythm\b', re.I), 'ริทึ่ม'),
    (re.compile(r'ไนท์บริด[จช์]*|\bknightsbridge\b', re.I), 'ไนท์บริดจ์'),
    (re.compile(r'พลัม|\bplum\b', re.I), 'พลัม'),
    (re.compile(r'คาซ่า?|\bcasa\b', re.I), 'คาซ่า'),
    (re.compile(r'เซ็?นทริ[คก]|\bcentric\b', re.I), 'เซ็นทริค'),
    (re.compile(r'คอนโดเล็?ต|\bcondolette\b', re.I), 'คอนโดเลต'),
    (re.compile(r'ยู\s*ดีไลท์|\bu\s*delight\b', re.I), 'ยูดีไลท์'),
    (re.compile(r'แชปเตอร์\s*วัน|\bchapter\s*one\b', re.I), 'แชปเตอร์วัน'),
    (re.compile(r'รีเจ้?น[ท์]*|\bregent\b', re.I), 'รีเจ้นท์'),
    (re.compile(r'โนเบิ?ล|\bnoble\b', re.I), 'โนเบิล'),
    (re.compile(r'พาร์?คแลน[ด์]*|\bparkland\b', re.I), 'พาร์คแลนด์'),
    (re.compile(r'แอชตัน|\bashton\b', re.I), 'แอชตัน'),
    (re.compile(r'เอล?ลิโอ|\belio\b', re.I), 'เอลิโอ'),
    (re.compile(r'ยูนิโอ|\bunio\b', re.I), 'ยูนิโอ'),
    (re.compile(r'โมดิ[ซสช]|\bmodiz\b', re.I), 'โมดิซ'),
    (re.compile(r'แอทโม[ซส]|\batmoz\b', re.I), 'แอทโมซ'),
    (re.compile(r'เคฟ|\bkave\b', re.I), 'เคฟ'),
    (re.compile(r'แชมเบอร์?ส?|\bchambers\b', re.I), 'แชมเบอร์ส'),
    (re.compile(r'เดอะ\s*คิว(?:บ์|บ)?|\bthe\s*cube\b', re.I), 'เดอะคิวบ์'),
    (re.compile(r'พลีโน่?|\bpleno\b', re.I), 'พลีโน่'),
    (re.compile(r'บริทาเนีย|\bbritani?a\b', re.I), 'บริทาเนีย'),
    (re.compile(r'ออริจิ้?น|\borigin\b', re.I), 'ออริจิ้น'),
    (re.compile(r'ริช\s*พาร์?ค|\brich\s*park\b', re.I), 'ริชพาร์ค'),
    (re.compile(r'เดอะ\s*ทรี|\bthe\s*tree\b', re.I), 'เดอะทรี'),
    (re.compile(r'เมโทร\s*ลักซ์?|\bmetro\s*luxe\b', re.I), 'เมโทรลักซ์'),
    (re.compile(r'เดอะ\s*ทรัสต์?|\bthe\s*trust\b', re.I), 'เดอะทรัสต์'),
    (re.compile(r'ชวนชื่?น|\b(?:chuanchuen|chuan\s*chuen)\b', re.I), 'ชวนชื่น'),
    (re.compile(r'เพอร์?เฟ[็คกต์]+|\bperfect\b', re.I), 'เพอร์เฟค'),
    (re.compile(r'[ภพ]ัสสร|\bpassorn\b', re.I), 'ภัสสร'),
    (re.compile(r'มั?ณฑนา|\bmantana\b', re.I), 'มัณฑนา'),
    (re.compile(r'ชัยพฤก[ษ์ษา]+|\bchaiyapruek\b', re.I), 'ชัยพฤกษ์'),
    (re.compile(r'วิลลาจจิ?โอ|\bvillaggio\b', re.I), 'วิลลาจจิโอ'),
    (re.compile(r'อินดี้?|\bindy\b', re.I), 'อินดี้'),
    (re.compile(r'ฮาบิเทีย|\bhabitia\b', re.I), 'ฮาบิเทีย'),
    (re.compile(r'ส[ะา]ราญสิริ|\bsaransiri\b', re.I), 'สราญสิริ'),
    (re.compile(r'บุราสิริ|\bburasiri\b', re.I), 'บุราสิริ'),
    (re.compile(r'(?:เ[ศส]|ส)รษฐสิริ|\bsetthasiri\b', re.I), 'เศรษฐสิริ'),
    (re.compile(r'นาราสิริ|\bnarasiri\b', re.I), 'นาราสิริ'),
    (re.compile(r'คณาสิริ|\bkanasiri\b', re.I), 'คณาสิริ'),
    (re.compile(r'อณาสิริ|\banasiri\b', re.I), 'อณาสิริ'),
    (re.compile(r'เซ็?นโทร|\bcentro\b', re.I), 'เซนโทร'),
    (re.compile(r'บ้านกลางเมือง|\bbaan\s*klang\s*muang\b', re.I), 'บ้านกลางเมือง'),
    (re.compile(r'บ้านกลางกรุง|\bbaan\s*klang\s*krung\b', re.I), 'บ้านกลางกรุง'),
    (re.compile(r'ซิตี้เซนส์?|\bcity\s*sense\b', re.I), 'ซิตี้เซนส์'),
    (re.compile(r'เดอะ\s*คอนเน[คกต์]+|\bthe\s*connect\b', re.I), 'เดอะ คอนเนค'),
    (re.compile(r'เดอะ\s*ซิตี้|\bthe\s*city\b', re.I), 'เดอะ ซิตี้'),
    (re.compile(r'เดอะ\s*ไลน์|\bthe\s*line\b', re.I), 'เดอะ ไลน์'),
    (re.compile(r'สินมั่?นคง', re.I), 'สินมั่นคง'),
    (re.compile(r'ทิพมา[ศส]', re.I), 'ทิพมาศ'),
    (re.compile(r'คาร์พ[ิี]เดี้ย?ม', re.I), 'คาร์พิเดียม'),
    (re.compile(r'เดอะ\s*คันทรี?่?|\bthe\s*country\b', re.I), 'เดอะคันทรี'),
    (re.compile(r'โมเดิร?์?น|\bmodern\b', re.I), 'โมเดิร์น'),
    (re.compile(r'โฮม|\bhome\b', re.I), 'โฮม'),
    (re.compile(r'เบญจทรัพย์', re.I), 'เบญจทรัพย์'),
    (re.compile(r'แพรมาพร', re.I), 'แพรมาพร'),
    (re.compile(r'ทรัพย์รุ่งเรือง', re.I), 'ทรัพย์รุ่งเรือง'),
    (re.compile(r'แบงค์?\s*คอก\s*ฮอไรซอน|\bbangkok\s*horizon\b', re.I), 'แบงค์คอก ฮอไรซอน'),
    (re.compile(r'พฤกษ์?ลดา|\bprueklada\b', re.I), 'พฤกษ์ลดา'),
    (re.compile(r'กัสโต้|\bgusto\b', re.I), 'กัสโต้'),
    (re.compile(r'ควอลิตี้\s*เฮ้าส์|\b(?:quality\s*house|q\.?\s*house)\b', re.I), 'ควอลิตี้ เฮ้าส์'),
    (re.compile(r'แลนด์\s*แอนด์?\s*เฮ้าส์?|\bland\s*(?:&|and)\s*house\b', re.I), 'แลนด์ แอนด์ เฮ้าส์'),
    (re.compile(r'อีสท์เกต|\beastgate\b', re.I), 'อีสท์เกต'),
]

def normalize_project_name(s):
    """Normalizes project names to link variations (e.g. ไอดิโอ <-> ไอดีโอ <-> IDEO)."""
    if not s or pd.isna(s):
        return ''
    txt = str(s).strip()
    txt = re.sub(r'^[\'"“‘\s]+|[\'"”’\s]+$', '', txt)
    if ' : ' in txt:
        parts = txt.split(' : ')
        txt = parts[1] if len(parts) > 1 else parts[0]
    while True:
        nt = _PREFIX_PAT.sub('', txt).strip()
        if nt == txt:
            break
        txt = nt
    txt = _SUFFIX_PAT.sub('', txt).strip()

    # Normalize numbers with common Thai real-estate prefixes
    txt = re.sub(r'คลอง\s*(\d+)', r'คลอง\1', txt)
    txt = re.sub(r'เฟส\s*(\d+)', r'เฟส\1', txt)
    txt = re.sub(r'ซอย\s*(\d+)', r'ซอย\1', txt)
    txt = re.sub(r'สาย\s*(\d+)', r'สาย\1', txt)
    txt = re.sub(r'phase\s*(\d+)', r'เฟส\1', txt, flags=re.I)

    for pat, rep in _NORM_PATTERNS:
        txt = pat.sub(rep, txt)

    res = _SPACE_CLEAN.sub('', txt)
    res = res.lower()
    res = re.sub(r'[่้๊๋์็]', '', res)
    res = res.replace('ศ', 'ส').replace('ษ', 'ส').replace('ภ', 'พ').replace('ธ', 'ท')
    res = res.replace('ณ', 'น').replace('ญ', 'ย').replace('ฌ', 'ช').replace('ฬ', 'ล')
    res = res.replace('ี', 'ิ').replace('ื', 'ิ').replace('ึ', 'ิ')
    if res in {'บาน', 'คอนโด', 'ทิดิน', 'ทาวนโฮม', 'อาคารพานิชย', ''}:
        return ''
    return res

def _strip_excel_text_formula(s):
    """Strips Excel CSV text formula wrapper like =\"1-1-1\" or leading apostrophe '1-1-1."""
    s = str(s).strip()
    if s.startswith('="') and s.endswith('"') and len(s) >= 3:
        return s[2:-1].strip()
    if s.startswith("'"):
        return s[1:].strip()
    return s

def parse_area_to_sqwah(area_str):
    """Helper function to parse 'พื้นที่ (ไร่-งาน-วา)' to positive float square wah."""
    if pd.isna(area_str):
        return np.nan
    if isinstance(area_str, (int, float, np.number)):
        f = float(area_str)
        return f if (math.isfinite(f) and f > 0) else np.nan
    if not isinstance(area_str, str) or area_str.strip() == "":
        return np.nan
    area_str = _strip_excel_text_formula(area_str)
    
    parts = area_str.split('-')
    if len(parts) == 3:
        try:
            rai = float(parts[0].replace(',', '').strip()) if parts[0].strip() else 0.0
            ngan = float(parts[1].replace(',', '').strip()) if parts[1].strip() else 0.0
            wah = float(parts[2].replace(',', '').strip()) if parts[2].strip() else 0.0
            total = (rai * 400.0) + (ngan * 100.0) + wah
            return total if (math.isfinite(total) and total > 0) else np.nan
        except ValueError:
            pass
    elif len(parts) == 1:
        try:
            f = float(parts[0].replace(',', '').strip())
            return f if (math.isfinite(f) and f > 0) else np.nan
        except ValueError:
            pass
            
    try:
        rai_match = re.search(r'([\d,]+(?:\.\d+)?)\s*ไร่', area_str)
        rai = float(rai_match.group(1).replace(',', '')) if rai_match else 0.0
        
        ngan_match = re.search(r'([\d,]+(?:\.\d+)?)\s*งาน', area_str)
        ngan = float(ngan_match.group(1).replace(',', '')) if ngan_match else 0.0
        
        wah_match = re.search(r'([\d,]+(?:\.\d+)?)\s*(?:ตารางวา|ตร\.?\s*ว\.?|วา)', area_str)
        wah = float(wah_match.group(1).replace(',', '')) if wah_match else 0.0
        
        if rai > 0 or ngan > 0 or wah > 0:
            total = (rai * 400.0) + (ngan * 100.0) + wah
            return total if math.isfinite(total) else np.nan
    except Exception:
        pass
        
    return np.nan

def to_float_sqwah(val):
    """Converts any value (numeric or string like '2-0-57', '1 ไร่ 2 งาน', '50.5') to float square wah."""
    if pd.isna(val):
        return np.nan
    if isinstance(val, (int, float, np.number)):
        f = float(val)
        return f if (math.isfinite(f) and f > 0) else np.nan
    val_str = _strip_excel_text_formula(val).replace(',', '')
    if not val_str or val_str in ['nan', 'None', '-', '']:
        return np.nan
    try:
        f = float(val_str)
        return f if (math.isfinite(f) and f > 0) else np.nan
    except (ValueError, TypeError):
        return parse_area_to_sqwah(_strip_excel_text_formula(val))

def to_float_sqm(val):
    """Converts any usable area value to positive finite float square meters."""
    if pd.isna(val):
        return np.nan
    if isinstance(val, (int, float, np.number)):
        f = float(val)
        return f if (math.isfinite(f) and f > 0) else np.nan
    val_str = str(val).strip()
    if not val_str or val_str in ['nan', 'None', '-', ''] or val_str.startswith('-'):
        return np.nan
    try:
        m = re.search(r'(?<!-)\b([\d,]+(?:\.\d+)?)', val_str)
        if not m:
            return np.nan
        f = float(m.group(1).replace(',', ''))
        return f if (math.isfinite(f) and f > 0) else np.nan
    except (ValueError, TypeError):
        return np.nan

def format_to_rai_ngan_wah(val):
    """Formats any land area value (sqwah float or text like '0-0-67' or '1 ไร่ 2 งาน') to 'X-Y-Z' (ไร่-งาน-ตร.ว.)"""
    if pd.isna(val):
        return "-"
    val_str = _strip_excel_text_formula(val)
    if not val_str or val_str in ['nan', 'None', '-', '0', '0-0-0', '0-0-0.0']:
        return "-"
    if re.match(r'^\d+-\d+-\d+(?:\.\d+)?$', val_str):
        return "-" if val_str in ['0-0-0', '0-0-0.0'] else val_str
    sqwah = to_float_sqwah(val)
    if pd.isna(sqwah) or sqwah <= 0:
        return "-"
    sqwah = round(sqwah, 4)
    rai = int(sqwah // 400)
    rem = round(sqwah % 400, 4)
    ngan = int(rem // 100)
    wah = round(rem % 100, 2)
    if wah >= 100.0:
        ngan += int(wah // 100)
        wah = round(wah % 100, 2)
    if ngan >= 4:
        rai += ngan // 4
        ngan = ngan % 4
    wah_str = str(int(wah)) if wah == int(wah) else f"{wah:.1f}"
    return f"{rai}-{ngan}-{wah_str}"

def _parse_announcement_date(s):
    """Parse Thai/CE date strings (full date preferred over year-only); returns (datetime.date | None, year_only_diff | None)."""
    # 1. Full d/m/yyyy (with optional HH:MM[:SS]) - handles BE years >= 2400 and m/d/yyyy fallback
    m_dmy = re.match(r'^(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{4})(?:[T\s]+\d{1,2}:\d{2}(?::\d{2})?)?$', s)
    if m_dmy:
        d_i, m_i, y_i = int(m_dmy.group(1)), int(m_dmy.group(2)), int(m_dmy.group(3))
        if y_i >= 2400:
            y_i -= 543
        try:
            return datetime.date(y_i, m_i, d_i), None
        except ValueError:
            if m_i > 12 and 1 <= d_i <= 12:
                try:
                    return datetime.date(y_i, d_i, m_i), None
                except ValueError:
                    pass

    # 2. ISO yyyy-mm-dd / timestamp (supports T or space separator and BE years)
    m_iso = re.match(r'^(\d{4})[-/\.](\d{1,2})[-/\.](\d{1,2})(?:[T\s].*)?$', s)
    if m_iso:
        y_i, m_i, d_i = int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3))
        if y_i >= 2400:
            y_i -= 543
        try:
            return datetime.date(y_i, m_i, d_i), None
        except ValueError:
            pass

    # 3. General pandas fallback (convert tz-aware timestamps to Thailand TZ, never UTC)
    if not re.match(r'^(?:ปี\s*)?\d{4}(?:\.0+)?$', s):
        is_iso_like = bool(re.match(r'^\d{4}[-/]', s))
        dt = pd.to_datetime(s, errors='coerce', dayfirst=not is_iso_like)
        if not pd.isna(dt):
            if getattr(dt, "tzinfo", None) is not None:
                dt = dt.tz_convert(_TH_TZ)
            d = dt.date()
            if d.year >= 2400:
                try:
                    d = datetime.date(d.year - 543, d.month, d.day)
                except ValueError:
                    return None, None
            return d, None

    # 4. Anchored year-only formats: 'ปี 2556', '2569', '2024.0'
    m_be = re.match(r'^(?:ปี\s*)?(24\d{2}|25\d{2})(?:\.0+)?$', s)
    if m_be:
        return None, int(m_be.group(1)) - 543

    m_yr = re.match(r'^(19\d{2}|20\d{2})(?:\.0+)?$', s)
    if m_yr:
        return None, int(m_yr.group(1))

    return None, None


def parse_sold_date_value(val):
    """Parse Thai Buddhist Era or Gregorian date string into pandas Timestamp safely."""
    if val is None or pd.isna(val):
        return pd.NaT
    s = str(val).strip()
    if not s or s.lower() in ('nan', 'none', 'null', '-', '<na>'):
        return pd.NaT
    d, _ = _parse_announcement_date(s)
    if d is not None:
        try:
            return pd.Timestamp(year=d.year, month=d.month, day=d.day)
        except Exception:
            return pd.NaT
    return pd.NaT


def format_announcement_age(val, ref_date=None):
    """
    Calculates the elapsed duration from an announcement date until today in 'X ปี Y เดือน' format:
    - >= 1 year with months: '1 ปี 3 เดือน'
    - >= 1 year with 0 months: '2 ปี'
    - < 1 year: '5 เดือน'
    - < 1 month: '< 1 เดือน'
    - Year-only input (e.g. '2024.0', 'ปี 2556'): '2 ปี', '13 ปี'
    - Empty, missing, or invalid: '-'
    """
    if ref_date is None:
        ref_date = datetime.datetime.now(_TH_TZ).date()
    if pd.isna(val) or val is None:
        return "-"
    s = str(val).strip()
    if not s or s in ['-', 'nan', 'None', '<NA>', 'null', '0', '0.0', 'ไม่มีข้อมูล']:
        return "-"

    try:
        d, yr_only = _parse_announcement_date(s)
        if yr_only is not None:
            diff_yr = ref_date.year - yr_only
            if diff_yr > 0:
                return f"{diff_yr} ปี"
            elif diff_yr == 0:
                return "< 1 ปี"
            return "-"
        if d is None:
            return "-"
        if d > ref_date:
            return "< 1 เดือน"

        total_months = (ref_date.year - d.year) * 12 + (ref_date.month - d.month)
        if ref_date.day < d.day:
            total_months -= 1
        if total_months < 0:
            total_months = 0

        years = total_months // 12
        months = total_months % 12

        if years > 0 and months > 0:
            return f"{years} ปี {months} เดือน"
        elif years > 0 and months == 0:
            return f"{years} ปี"
        elif years == 0 and months > 0:
            return f"{months} เดือน"
        else:
            return "< 1 เดือน"
    except Exception:
        return "-"

def parse_listing_age_days(val, ref_date=None):
    """
    Parses announcement date and returns elapsed age in days (integer >= 0).
    Returns -1 if missing, empty, future, or unparseable.
    """
    if ref_date is None:
        ref_date = datetime.datetime.now(_TH_TZ).date()
    if pd.isna(val) or val is None:
        return -1
    s = str(val).strip()
    if not s or s in ['-', 'nan', 'None', '<NA>', 'null', '0', '0.0', 'ไม่มีข้อมูล']:
        return -1

    try:
        d, yr_only = _parse_announcement_date(s)
        if d is not None:
            delta = (ref_date - d).days
            return delta if delta >= 0 else -1
        if yr_only is not None:
            delta_yr = ref_date.year - yr_only
            return delta_yr * 365 if delta_yr >= 0 else -1
    except Exception:
        pass

    return -1

def parse_floor_numeric(val):
    """
    Extracts numeric floor number or building floor count from string/number.
    Returns float >= 0, or -1.0 if missing/unspecified/negative.
    """
    if pd.isna(val) or val is None:
        return -1.0
    s = str(val).strip()
    if s in ['', '-', 'nan', 'None', '<NA>', 'null', 'ไม่ระบุ', 'ไม่มีข้อมูล'] or s.startswith('-'):
        return -1.0
    m = re.search(r'(?<!-)(\d+(?:\.\d+)?)', s)
    if m:
        try:
            f = float(m.group(1))
            return f if (math.isfinite(f) and f >= 0) else -1.0
        except (ValueError, TypeError):
            return -1.0
    return -1.0

def parse_room_count(val):
    """
    Extracts room/parking count.
    Returns float >= 0 (0.0 for studio/none), or -1.0 if missing/unspecified/negative.
    """
    if pd.isna(val) or val is None:
        return -1.0
    s = str(val).strip().lower()
    if s in ['', '-', 'nan', 'none', '<na>', 'null', 'ไม่ระบุ', 'ไม่มีข้อมูล'] or s.startswith('-'):
        return -1.0
    if 'สตูดิโอ' in s or 'studio' in s:
        return 0.0
    try:
        f = float(s)
        return f if (math.isfinite(f) and f >= 0) else -1.0
    except (ValueError, TypeError):
        m = re.search(r'(?<!-)(\d+(?:\.\d+)?)', s)
        if m:
            try:
                f = float(m.group(1))
                return f if (math.isfinite(f) and f >= 0) else -1.0
            except (ValueError, TypeError):
                return -1.0
        return -1.0

def format_num_val(val):
    """Safely format numeric fields (e.g., bedrooms, area) to nice string."""
    if val is None or pd.isna(val):
        return ""
    s = str(val).strip()
    if s == "" or s.lower() in ("nan", "$undefined"):
        return ""
    try:
        f_val = float(val)
        if not math.isfinite(f_val):
            return ""
        if f_val.is_integer():
            return str(int(f_val))
        return str(f_val)
    except (ValueError, TypeError):
        return s

def get_clean_title(val):
    """Clean property title string."""
    if not val or pd.isna(val):
        return "ไม่มีชื่อประกาศ"
    val_str = str(val).strip()
    if val_str.startswith("{") and val_str.endswith("}"):
        try:
            d = ast.literal_eval(val_str)
            if isinstance(d, dict):
                return d.get('th') or d.get('en') or val_str
        except Exception:
            pass
    return val_str

def get_clean_link(val):
    """Clean property link string and enforce safe URL schemes."""
    if not val or pd.isna(val):
        return ""
    val_str = str(val).strip()
    if val_str.startswith("{") and val_str.endswith("}"):
        try:
            d = ast.literal_eval(val_str)
            if isinstance(d, dict):
                val_str = str(d.get('th') or d.get('en') or "").strip()
        except Exception:
            pass
    if not val_str:
        return ""
    low = val_str.lower()
    if any(low.startswith(p) for p in _SAFE_LINK_PREFIXES):
        return val_str
    return ""

def format_coord_vectorized(df, coord_col):
    """Vectorized coordinate formatting with centroid warning prefix ('⚠️ ') and '-' fallback."""
    if df is None or df.empty or coord_col not in df.columns:
        return pd.Series('-', index=df.index if df is not None else [])
    vals = pd.to_numeric(df[coord_col], errors='coerce')
    valid_mask = vals.notna() & (vals != 0)
    if not valid_mask.any():
        return pd.Series('-', index=df.index)
    if 'is_centroid' in df.columns:
        c_raw = df['is_centroid']
        if pd.api.types.is_bool_dtype(c_raw.dtype):
            is_cen = c_raw.fillna(False).astype(bool)
        else:
            is_cen = c_raw.fillna('').astype(str).str.strip().str.lower().isin({'true', '1', '1.0', 'yes', 't'})
    else:
        is_cen = pd.Series(False, index=df.index)
    formatted = pd.Series('-', index=df.index, dtype=object)
    valid_vals = vals[valid_mask]
    valid_cen = is_cen[valid_mask]
    formatted.loc[valid_mask] = [
        f"⚠️ {v:.6f}" if c else f"{v:.6f}"
        for v, c in zip(valid_vals, valid_cen)
    ]
    return formatted

@st.cache_data(show_spinner=False, max_entries=8)
def _get_dataset_month_year_cached(_df, cache_key, exclude_legal=True):
    """Formats dataset date into Thai Month & Year using the earliest (min) extraction date."""
    thai_full_months = [
        'มกราคม', 'กุมภาพันธ์', 'มีนาคม', 'เมษายน', 'พฤษภาคม', 'มิถุนายน',
        'กรกฎาคม', 'สิงหาคม', 'กันยายน', 'ตุลาคม', 'พฤศจิกายน', 'ธันวาคม'
    ]
    thai_short_months = ['ม.ค.', 'ก.พ.', 'มี.ค.', 'เม.ย.', 'พ.ค.', 'มิ.ย.', 'ก.ค.', 'ส.ค.', 'ก.ย.', 'ต.ค.', 'พ.ย.', 'ธ.ค.']
    
    if _df is not None and not _df.empty and 'วันที่ดึงข้อมูล' in _df.columns:
        target_df = _df
        # Sidebar ที่บอกดึงข้อมูล ไม่ต้องนับของ LED Legal / LED_SOLD
        if exclude_legal and 'บริษัท' in _df.columns:
            legal_mask = _df['บริษัท'].astype(str).str.strip().str.upper().isin(_LED_LEGAL_COMPANIES)
            non_legal = _df[~legal_mask]
            if not non_legal.empty:
                target_df = non_legal

        # Deduplicate unique date strings first (~26 unique values vs 461k rows)
        u_raw = target_df['วันที่ดึงข้อมูล'].dropna().unique()
        parsed_dates = []
        for raw_v in u_raw:
            sv = str(raw_v).strip()
            if not sv or sv in ('', 'nan', 'None', '-', '<NA>', 'NaT'):
                continue
            d_obj, _ = _parse_announcement_date(sv)
            if d_obj is not None:
                parsed_dates.append(d_obj)

        if parsed_dates:
            min_dt = min(parsed_dates)
            min_year = min_dt.year + 543 if min_dt.year < 2500 else min_dt.year
            month_name = thai_full_months[min_dt.month - 1]
            min_short_m = thai_short_months[min_dt.month - 1]
            return f"{month_name} {min_year}", f"{min_dt.day} {min_short_m} {min_year}"
    try:
        p_path = next((p for p in [
            Path(_ROOT_DIR) / "all_assets.parquet",
            Path(_ROOT_DIR) / "all_asset.parquet",
            Path("all_assets.parquet"),
            Path("all_asset.parquet"),
        ] if p.exists()), None)
        if p_path is not None:
            dt = datetime.datetime.fromtimestamp(p_path.stat().st_mtime, tz=_TH_TZ)
            thai_year = dt.year + 543 if dt.year < 2500 else dt.year
            month_name = thai_full_months[dt.month - 1]
            short_month = thai_short_months[dt.month - 1]
            return f"{month_name} {thai_year}", f"{dt.day} {short_month} {thai_year}"
    except Exception:
        pass
    now_dt = datetime.datetime.now(_TH_TZ)
    fallback_year = now_dt.year + 543 if now_dt.year < 2500 else now_dt.year
    return f"{thai_full_months[now_dt.month - 1]} {fallback_year}", f"{now_dt.day} {thai_short_months[now_dt.month - 1]} {fallback_year}"

def get_dataset_month_year(_df, data_mtime=None, exclude_legal=True):
    """Formats dataset date into Thai Month & Year with automatic cache invalidation when dataset updates."""
    if data_mtime is None:
        try:
            p_path = next((p for p in [
                Path(_ROOT_DIR) / "all_assets.parquet",
                Path(_ROOT_DIR) / "all_asset.parquet",
                Path("all_assets.parquet"),
                Path("all_asset.parquet"),
            ] if p.exists()), None)
            data_mtime = p_path.stat().st_mtime if p_path is not None else 0.0
        except Exception:
            data_mtime = 0.0
    row_cnt = len(_df) if _df is not None else 0
    return _get_dataset_month_year_cached(_df, cache_key=(data_mtime, row_cnt, exclude_legal, 'no_led_legal_v2'), exclude_legal=exclude_legal)

def _sanitize_unit_prices(df):
    """Clear unit prices when total price is missing/invalid or when unit rates exceed realistic bounds."""
    has_price = 'ราคา' in df.columns
    if has_price:
        invalid_price = df['ราคา'].isna() | (df['ราคา'] < 500)
        if invalid_price.any():
            df.loc[invalid_price, 'ราคา'] = np.nan
    else:
        invalid_price = None

    if 'ราคาต่อตารางวา' in df.columns:
        puw = pd.to_numeric(df['ราคาต่อตารางวา'], errors='coerce').astype('float64')
        bad_puw = (~np.isfinite(puw)) | (puw <= 0) | (puw > 50_000_000)
        if invalid_price is not None:
            bad_puw |= invalid_price
        puw = puw.mask(bad_puw, np.nan)
        df['ราคาต่อตารางวา'] = puw

    if 'ราคาต่อตารางเมตร' in df.columns:
        pum = pd.to_numeric(df['ราคาต่อตารางเมตร'], errors='coerce').astype('float64')
        bad_pum = (~np.isfinite(pum)) | (pum <= 0) | (pum > 20_000_000)
        if invalid_price is not None:
            bad_pum |= invalid_price
        pum = pum.mask(bad_pum, np.nan)
        df['ราคาต่อตารางเมตร'] = pum
    return df


def _apply_led_legal_sold_prices(df):
    """For LED Legal (LED_SOLD): uses 'ราคาขายได้' as the selling price 'ราคา'
    and recalculates per-sqw and per-sqm unit rates based on the actual sold price.
    """
    if 'บริษัท' in df.columns and 'ราคาขายได้' in df.columns and 'ราคา' in df.columns:
        legal_sold_mask = df['บริษัท'].astype(str).str.strip().str.upper().isin(_LED_LEGAL_COMPANIES)
        if legal_sold_mask.any():
            if df['ราคา'].dtype != 'float64':
                df['ราคา'] = pd.to_numeric(df['ราคา'], errors='coerce').astype('float64')
            sold_p = pd.to_numeric(df.loc[legal_sold_mask, 'ราคาขายได้'], errors='coerce')
            valid_sold = sold_p.notna() & (sold_p >= 500)
            if valid_sold.any():
                target_idx = sold_p[valid_sold].index
                df.loc[target_idx, 'ราคา'] = sold_p.loc[target_idx]

                sqw_col = 'พื้นที่_ตารางวา' if 'พื้นที่_ตารางวา' in df.columns else ('เนื้อที่ (ตร.ว.)' if 'เนื้อที่ (ตร.ว.)' in df.columns else None)
                if sqw_col and 'ราคาต่อตารางวา' in df.columns:
                    if df['ราคาต่อตารางวา'].dtype != 'float64':
                        df['ราคาต่อตารางวา'] = pd.to_numeric(df['ราคาต่อตารางวา'], errors='coerce').astype('float64')
                    if sqw_col == 'พื้นที่_ตารางวา':
                        sqw_vals = pd.to_numeric(df.loc[target_idx, sqw_col], errors='coerce')
                    else:
                        u_sqw = df.loc[target_idx, sqw_col].dropna().unique()
                        sqw_map = {v: to_float_sqwah(v) for v in u_sqw}
                        sqw_vals = df.loc[target_idx, sqw_col].map(sqw_map)
                    valid_sqw = sqw_vals.notna() & (sqw_vals > 0) & (sold_p.loc[target_idx] > 0)
                    if valid_sqw.any():
                        v_idx = target_idx[valid_sqw.values]
                        df.loc[v_idx, 'ราคาต่อตารางวา'] = (sold_p.loc[v_idx] / sqw_vals.loc[v_idx]).astype('float64')

                if 'พื้นที่ใช้สอย (ตร.ม.)' in df.columns and 'ราคาต่อตารางเมตร' in df.columns:
                    if df['ราคาต่อตารางเมตร'].dtype != 'float64':
                        df['ราคาต่อตารางเมตร'] = pd.to_numeric(df['ราคาต่อตารางเมตร'], errors='coerce').astype('float64')
                    sqm_vals = pd.to_numeric(df.loc[target_idx, 'พื้นที่ใช้สอย (ตร.ม.)'], errors='coerce')
                    valid_sqm = sqm_vals.notna() & (sqm_vals > 0) & (sold_p.loc[target_idx] > 0)
                    if valid_sqm.any():
                        v_idx = target_idx[valid_sqm.values]
                        df.loc[v_idx, 'ราคาต่อตารางเมตร'] = (sold_p.loc[v_idx] / sqm_vals.loc[v_idx]).astype('float64')
    df = _sanitize_unit_prices(df)
    return df


def _clean_plaintiff_series_fast(s):
    """Deduplicate non-empty plaintiff strings before applying PDPA redaction (avoids 461k row-wise apply)."""
    s_str = s.astype(object).fillna('').astype(str).replace({'nan': '', 'None': '', 'null': '', '<NA>': '', 'NaN': '', '-': ''}).str.strip()
    non_empty = s_str != ''
    if not non_empty.any():
        return s_str
    u_vals = s_str.loc[non_empty].unique()
    lut = {v: clean_plaintiff_name(v) for v in u_vals}
    out = s_str.copy()
    out.loc[non_empty] = s_str.loc[non_empty].map(lut).fillna('')
    return out


def _coerce_numeric_price_series(s):
    """Parse numeric or comma/currency formatted prices (e.g. '฿3,500,000 บาท') safely to float64."""
    if pd.api.types.is_numeric_dtype(s):
        return pd.to_numeric(s, errors='coerce')
    cleaned = (
        s.astype(object)
        .where(s.notna(), np.nan)
        .astype(str)
        .str.replace(r'(?:฿|บาท|THB|,|\s)', '', regex=True, case=False)
    )
    return pd.to_numeric(cleaned, errors='coerce')


def ensure_derived_cols(df, persist_cache=False):
    """Enriches and normalizes the properties dataset with standard columns, categories, and parsed values.

    `persist_cache` defaults to False so runtime user uploads NEVER mutate shared server-side
    `data/project_name_clean_cache.parquet`.
    """
    if df is None or df.empty:
        return df

    # Fast-path: if ALL rows are already pre-cleaned and derived, skip heavy regex pipeline!
    if '_is_derived_clean' in df.columns:
        is_all_clean = bool(df['_is_derived_clean'].fillna(False).astype(bool).all()) if len(df) > 0 else False
        if is_all_clean:
            if 'is_centroid' in df.columns:
                if pd.api.types.is_bool_dtype(df['is_centroid'].dtype):
                    df['is_centroid'] = df['is_centroid'].fillna(False).astype(bool)
                else:
                    df['is_centroid'] = df['is_centroid'].astype(object).fillna('').astype(str).str.strip().str.lower().isin({'true', '1', '1.0', 'yes', 't'})
            if 'โจทก์' in df.columns:
                df['โจทก์'] = _clean_plaintiff_series_fast(df['โจทก์'])
            for f64_col in ['ราคา', 'ราคาขายได้', 'ละติจูด', 'ลองจิจูด', 'พื้นที่_ตารางวา', 'พื้นที่ใช้สอย (ตร.ม.)', 'ราคาต่อตารางวา', 'ราคาต่อตารางเมตร']:
                if f64_col in df.columns and df[f64_col].dtype != 'float64':
                    df[f64_col] = pd.to_numeric(df[f64_col], errors='coerce').astype('float64')
            if 'norm_project_name' not in df.columns:
                if 'ชื่อโครงการ' in df.columns:
                    u_projs = df['ชื่อโครงการ'].dropna().unique()
                    norm_map = {p: normalize_project_name(p) for p in u_projs if p}
                    df['norm_project_name'] = df['ชื่อโครงการ'].map(norm_map).fillna('')
                else:
                    df['norm_project_name'] = ''
            if 'ลิงก์' in df.columns:
                from modules.config.constants import get_base_url_prefix
                base_prefix = get_base_url_prefix()
                link_s = df['ลิงก์'].astype(str)
                rel_bridge_mask = link_s.str.startswith('app/static/led_')
                if rel_bridge_mask.any():
                    df.loc[rel_bridge_mask, 'ลิงก์'] = f"{base_prefix}/" + link_s.loc[rel_bridge_mask]
                    link_s = df['ลิงก์'].astype(str)
                if base_prefix:
                    root_bridge_mask = link_s.str.startswith('/app/static/led_')
                    if root_bridge_mask.any():
                        df.loc[root_bridge_mask, 'ลิงก์'] = base_prefix + link_s.loc[root_bridge_mask]
            for col in ['บริษัท', 'ประเภททรัพย์', 'จังหวัด', 'ภาค', 'ประเภทการขาย', 'อำเภอ', 'ตำบล']:
                if col in df.columns and not isinstance(df[col].dtype, pd.CategoricalDtype):
                    df[col] = df[col].astype('category')
            df = _apply_led_legal_sold_prices(df)
            return df

    if 'ประเภททรัพย์' in df.columns:
        prop_type_map = PROPERTY_TYPE_MAPPING
        u_types = df['ประเภททรัพย์'].dropna().unique()
        lower_prop_map = {k.lower(): v for k, v in prop_type_map.items()}

        def _resolve_single_type(t):
            s = str(t).strip()
            if s in prop_type_map:
                return prop_type_map[s]
            sl = s.lower()
            if sl in lower_prop_map:
                return lower_prop_map[sl]
            if sl.startswith('semi-detached') or 'twin house' in sl:
                return 'บ้านแฝด'
            if 'ทาวน์' in sl or sl.startswith('town'):
                return 'ทาวน์เฮ้าส์'
            if 'condo' in sl or sl in ['penthouse', 'duplex']:
                return 'ห้องชุดพักอาศัย'
            if sl.startswith('villa'):
                return 'วิลล่า'
            if sl == 'land' or sl.startswith('land '):
                return 'ที่ดินพร้อมสิ่งปลูกสร้าง' if 'building' in sl else 'ที่ดินเปล่า'
            if 'detached house' in sl or sl == 'single house' or sl == 'house':
                return 'บ้านเดี่ยว'
            if 'shophouse' in sl or 'commercial' in sl or sl == 'retail':
                return 'อาคารพาณิชย์'
            if 'apartment' in sl:
                return 'อพาร์ทเมนท์'
            if 'warehouse' in sl or 'factory' in sl:
                return 'โรงงาน/โกดัง'
            if 'home office' in sl or 'homeoffice' in sl:
                return 'โฮมออฟฟิศ'
            if 'office' in sl:
                return 'อาคารสำนักงาน'
            if 'hotel' in sl or 'resort' in sl:
                return 'โรงแรม/รีสอร์ท'
            return s

        type_lut = {t: _resolve_single_type(t) for t in u_types}
        df['ประเภททรัพย์'] = df['ประเภททรัพย์'].map(type_lut).fillna('อื่นๆ')
        
        # Resolve mixed 'อาคารพาณิชย์/โฮมออฟฟิศ' (vectorized, no axis=1 apply)
        comm_ho_mask = df['ประเภททรัพย์'].astype(str).str.contains('อาคารพาณิชย์/โฮมออฟฟิศ|โฮมออฟฟิศ/อาคารพาณิชย์', na=False)
        if comm_ho_mask.any():
            t_col = df.loc[comm_ho_mask, 'ชื่อประกาศ'].fillna('').astype(str) if 'ชื่อประกาศ' in df.columns else pd.Series('', index=df.index[comm_ho_mask])
            p_col = df.loc[comm_ho_mask, 'ชื่อโครงการ'].fillna('').astype(str) if 'ชื่อโครงการ' in df.columns else pd.Series('', index=df.index[comm_ho_mask])
            combined_txt = (t_col + ' ' + p_col).str.lower()
            is_ho = combined_txt.str.contains(r'โฮมออฟฟิศ|โฮมออฟฟิต|home\s*office|homeoffice', regex=True, na=False)
            df.loc[comm_ho_mask, 'ประเภททรัพย์'] = np.where(is_ho, 'โฮมออฟฟิศ', 'อาคารพาณิชย์')

        mixed_mask = df['ประเภททรัพย์'].astype(str).str.contains('บ้านเดี่ยว/ทาวน์', na=False)
        if mixed_mask.any():
            t_col = df.loc[mixed_mask, 'ชื่อประกาศ'].fillna('').astype(str) if 'ชื่อประกาศ' in df.columns else pd.Series('', index=df.index[mixed_mask])
            p_col = df.loc[mixed_mask, 'ชื่อโครงการ'].fillna('').astype(str) if 'ชื่อโครงการ' in df.columns else pd.Series('', index=df.index[mixed_mask])
            combined_txt = (t_col + ' ' + p_col).str.lower()
            conds = [
                combined_txt.str.contains(r'ตึกแถว|อาคารพาณิชย์|shophouse|พาณิชย์', regex=True, na=False),
                combined_txt.str.contains(r'โฮมออฟฟิศ|โฮมออฟฟิต|home\s*office|homeoffice', regex=True, na=False),
                combined_txt.str.contains(r'สำนักงาน|office', regex=True, na=False),
                combined_txt.str.contains(r'โกดัง|โรงงาน|warehouse|factory', regex=True, na=False),
                combined_txt.str.contains(r'ทาวน์โฮม|ทาวน์เฮ้าส์|ทาวน์เฮาส์|townhome|townhouse|ทาวน์', regex=True, na=False),
                combined_txt.str.contains(r'ที่ดิน|land', regex=True, na=False),
                combined_txt.str.contains(r'คอนโด|ห้องชุด|condo', regex=True, na=False),
            ]
            choices = ['อาคารพาณิชย์', 'โฮมออฟฟิศ', 'อาคารสำนักงาน', 'โรงงาน/โกดัง', 'ทาวน์เฮ้าส์', 'ที่ดินเปล่า', 'ห้องชุดพักอาศัย']
            df.loc[mixed_mask, 'ประเภททรัพย์'] = np.select(conds, choices, default='บ้านเดี่ยว')

    if 'ประเภทการขาย' in df.columns:
        df = df[~df['ประเภทการขาย'].astype(str).str.strip().isin(['ให้เช่า', 'เช่า'])].copy()
        df = df[~df['ประเภทการขาย'].astype(str).str.contains('NPL', case=False, na=False)].copy()
        sale_map = SALE_TYPE_MAPPING
        u_sales = df['ประเภทการขาย'].dropna().unique()
        sale_lut = {s: sale_map.get(str(s).strip(), str(s).strip()) for s in u_sales}
        df['ประเภทการขาย'] = df['ประเภทการขาย'].map(sale_lut).fillna('ขาย')

    if 'is_centroid' in df.columns:
        if not pd.api.types.is_bool_dtype(df['is_centroid'].dtype):
            df['is_centroid'] = df['is_centroid'].astype(object).fillna('').astype(str).str.strip().str.lower().isin({'true', '1', '1.0', 'yes', 't'})
        else:
            df['is_centroid'] = df['is_centroid'].fillna(False).astype(bool)
    elif 'ละติจูด' in df.columns and 'ลองจิจูด' in df.columns:
        try:
            known_cset = get_known_centroids_set()
            if known_cset:
                lat_n = pd.to_numeric(df['ละติจูด'], errors='coerce')
                lon_n = pd.to_numeric(df['ลองจิจูด'], errors='coerce')
                c_keys = lat_n.round(5).astype(str) + ',' + lon_n.round(5).astype(str)
                df['is_centroid'] = c_keys.isin(known_cset).fillna(False).astype(bool)
            else:
                df['is_centroid'] = False
        except Exception:
            df['is_centroid'] = False
    else:
        df['is_centroid'] = False

    if 'ชื่อโครงการ' in df.columns:
        # Respect already-cleaned projects; never write untrusted runtime uploads to shared server disk cache
        already_proj_cleaned = bool(df.attrs.get('_project_already_cleaned', False))
        if not already_proj_cleaned:
            u_proj = df['ชื่อโครงการ'].dropna().unique()
            proj_cache = _load_readonly_project_clean_cache()
            p_lut = {}
            missing = []
            for p in u_proj:
                ps = str(p)
                if ps in proj_cache:
                    p_lut[p] = proj_cache[ps]
                else:
                    cleaned = clean_project_name(p)
                    p_lut[p] = cleaned
                    missing.append((ps, cleaned))

            if persist_cache and missing:
                cache_path = os.path.join(_ROOT_DIR, "data", "project_name_clean_cache.parquet")
                with _PROJ_CACHE_LOCK:
                    disk_cache = {}
                    loaded_ok = not os.path.exists(cache_path)
                    if os.path.exists(cache_path):
                        try:
                            c_df = pd.read_parquet(cache_path)
                            disk_cache = dict(zip(c_df['raw_project'].astype(str), c_df['clean_project']))
                            loaded_ok = True
                        except Exception:
                            loaded_ok = False
                    # Only write back if existing cache loaded cleanly (prevents wiping 7 MB cache on transient read error!)
                    if loaded_ok:
                        for ps, cleaned in missing:
                            disk_cache[ps] = cleaned
                        tmp_cache_path = f"{cache_path}.tmp.{os.getpid()}.{threading.get_ident()}"
                        try:
                            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
                            updated_cache = pd.DataFrame(list(disk_cache.items()), columns=['raw_project', 'clean_project'])
                            updated_cache.to_parquet(tmp_cache_path, compression='zstd', index=False)
                            os.replace(tmp_cache_path, cache_path)
                        except Exception:
                            try:
                                if os.path.exists(tmp_cache_path):
                                    os.remove(tmp_cache_path)
                            except Exception:
                                pass

            df['ชื่อโครงการ'] = df['ชื่อโครงการ'].map(p_lut)

    if 'ชื่อประกาศ' not in df.columns:
        if 'ชื่อโครงการ' in df.columns:
            df['ชื่อประกาศ'] = df['ชื่อโครงการ'].fillna('ไม่มีชื่อ').astype(str)
        elif 'รหัสทรัพย์' in df.columns:
            df['ชื่อประกาศ'] = df['รหัสทรัพย์'].fillna('ทรัพย์สิน NPA').astype(str)
        else:
            df['ชื่อประกาศ'] = 'ทรัพย์สิน NPA'
    else:
        df['ชื่อประกาศ'] = df['ชื่อประกาศ'].fillna('ไม่มีชื่อ').astype(str)

    if 'ลิงก์' not in df.columns:
        df['ลิงก์'] = ""
    else:
        df['ลิงก์'] = df['ลิงก์'].astype(object).fillna("").astype(str)

    # Ensure LED & LED Legal property codes are uniquely formatted as <lawsuit>_<จังหวัด>
    if 'บริษัท' in df.columns and 'รหัสทรัพย์' in df.columns and 'จังหวัด' in df.columns:
        led_code_mask = df['บริษัท'].astype(str).str.startswith('LED')
        if led_code_mask.any():
            def _format_led_prop_code(code_val, prov_val):
                c = str(code_val).strip() if pd.notna(code_val) else ""
                p = str(prov_val).strip() if pd.notna(prov_val) else ""
                base_c = re.sub(r'_[^_]+$', '', c).strip()
                if not base_c or base_c in ['nan', 'None', '-']:
                    return c
                if not p or p in ['nan', 'None', '-']:
                    return base_c
                return f"{base_c}_{p}"

            df.loc[led_code_mask, 'รหัสทรัพย์'] = [
                _format_led_prop_code(c, p)
                for c, p in zip(df.loc[led_code_mask, 'รหัสทรัพย์'], df.loc[led_code_mask, 'จังหวัด'])
            ]

    # Ensure LED links use the smart lawsuit Auto-POST bridge
    if 'บริษัท' in df.columns and 'รหัสทรัพย์' in df.columns:
        led_mask = (df['บริษัท'] == 'LED')
        if led_mask.any():
            codes_s = df.loc[led_mask, 'รหัสทรัพย์'].fillna('').astype(str)
            courts_s = df.loc[led_mask, 'ศาล'].fillna('').astype(str) if 'ศาล' in df.columns else pd.Series('', index=codes_s.index)
            plaintiffs_s = df.loc[led_mask, 'โจทก์'].fillna('').astype(str) if 'โจทก์' in df.columns else pd.Series('', index=codes_s.index)

            from modules.config.constants import get_static_url
            led_bridge_base = get_static_url("led_bridge.html")

            def _build_led_url(code, court, plaintiff):
                s = str(code).strip()
                if not s or s in ['nan', 'None', '-']:
                    return "https://asset.led.go.th/newbidreg/asset_search_law_suit.asp"
                s_pure = re.sub(r'_[^_]+$', '', s).strip()
                if '/' in s_pure:
                    parts = s_pure.split('/', 1)
                    s_no, s_yr = parts[0].strip(), parts[1].strip()
                    base_u = f"{led_bridge_base}?suit_no={urllib.parse.quote(s_no)}&suit_year={urllib.parse.quote(s_yr)}"
                else:
                    base_u = f"{led_bridge_base}?suit_no={urllib.parse.quote(s_pure)}"
                p_raw = str(plaintiff).strip()
                if p_raw and p_raw not in ['nan', 'None', 'null', '<NA>', 'NaN', '-']:
                    p_clean = clean_plaintiff_name(p_raw)
                    p_search = re.sub(r'\s*\(.*$', '', p_clean).strip()
                    if p_search:
                        base_u += f"&person1={urllib.parse.quote(p_search)}"
                c_raw = str(court).strip()
                if c_raw and c_raw not in ['nan', 'None', 'null', '<NA>', 'NaN', '-']:
                    base_u += f"&court={urllib.parse.quote(c_raw)}"
                return base_u

            df.loc[led_mask, 'ลิงก์'] = [
                _build_led_url(c, ct, p)
                for c, ct, p in zip(codes_s, courts_s, plaintiffs_s)
            ]

        # For LED Legal: use dedicated led_legal_bridge.html targeting reports.asp with only lawsuit and year
        legal_mask = df['บริษัท'].astype(str).str.strip().str.upper().isin(_LED_LEGAL_COMPANIES)
        if legal_mask.any():
            from modules.config.constants import get_static_url
            led_legal_bridge_base = get_static_url("led_legal_bridge.html")
            codes_legal = df.loc[legal_mask, 'รหัสทรัพย์'].fillna('').astype(str)

            def _build_led_legal_url(code):
                s = str(code).strip()
                if not s or s in ['nan', 'None', '-']:
                    return "https://asset.led.go.th/report/reports.asp"
                s_pure = re.sub(r'_[^_]+$', '', s).strip()
                if '/' in s_pure:
                    parts = s_pure.split('/', 1)
                    s_no, s_yr = parts[0].strip(), parts[1].strip()
                    return f"{led_legal_bridge_base}?suit_no={urllib.parse.quote(s_no)}&suit_year={urllib.parse.quote(s_yr)}"
                return f"{led_legal_bridge_base}?suit_no={urllib.parse.quote(s_pure)}"

            df.loc[legal_mask, 'ลิงก์'] = [
                _build_led_legal_url(c)
                for c in codes_legal
            ]

    if 'ราคา' in df.columns:
        df['ราคา'] = _coerce_numeric_price_series(df['ราคา'])
        df.loc[df['ราคา'] < 500, 'ราคา'] = np.nan
    else:
        df['ราคา'] = np.nan

    for _area_c in ('เนื้อที่ (ตร.ว.)', 'เนื้อที่ (ไร่-งาน-ตร.ว.)', 'พื้นที่ (ไร่-งาน-วา)'):
        if _area_c in df.columns:
            df[_area_c] = (
                df[_area_c]
                .astype(str)
                .str.strip()
                .str.replace(r'^="(.*)"$', r'\1', regex=True)
                .replace({'nan': None, 'None': None, '<NA>': None, '': None})
            )
    if 'เนื้อที่ (ตร.ว.)' not in df.columns and 'เนื้อที่ (ไร่-งาน-ตร.ว.)' in df.columns:
        df['เนื้อที่ (ตร.ว.)'] = df['เนื้อที่ (ไร่-งาน-ตร.ว.)']

    if 'พื้นที่_ตารางวา' not in df.columns:
        if 'เนื้อที่_ตารางวา' in df.columns:
            s_sqw = pd.to_numeric(df['เนื้อที่_ตารางวา'], errors='coerce')
            na_m = s_sqw.isna() & df['เนื้อที่_ตารางวา'].notna()
            if na_m.any():
                u_v = df.loc[na_m, 'เนื้อที่_ตารางวา'].unique()
                s_sqw.loc[na_m] = df.loc[na_m, 'เนื้อที่_ตารางวา'].map({v: to_float_sqwah(v) for v in u_v})
            df['พื้นที่_ตารางวา'] = s_sqw
        elif 'เนื้อที่ (ตร.ว.)' in df.columns:
            u_v = df['เนื้อที่ (ตร.ว.)'].dropna().unique()
            df['พื้นที่_ตารางวา'] = df['เนื้อที่ (ตร.ว.)'].map({v: parse_area_to_sqwah(v) for v in u_v})
        elif 'เนื้อที่ (ไร่-งาน-ตร.ว.)' in df.columns:
            u_v = df['เนื้อที่ (ไร่-งาน-ตร.ว.)'].dropna().unique()
            df['พื้นที่_ตารางวา'] = df['เนื้อที่ (ไร่-งาน-ตร.ว.)'].map({v: parse_area_to_sqwah(v) for v in u_v})
        elif 'พื้นที่ (ไร่-งาน-วา)' in df.columns:
            u_v = df['พื้นที่ (ไร่-งาน-วา)'].dropna().unique()
            df['พื้นที่_ตารางวา'] = df['พื้นที่ (ไร่-งาน-วา)'].map({v: parse_area_to_sqwah(v) for v in u_v})
        else:
            df['พื้นที่_ตารางวา'] = np.nan
    else:
        raw_sqw = df['พื้นที่_ตารางวา']
        s_sqw = pd.to_numeric(raw_sqw, errors='coerce')
        na_m = s_sqw.isna() & raw_sqw.notna()
        if na_m.any():
            u_v = raw_sqw.loc[na_m].unique()
            s_sqw.loc[na_m] = raw_sqw.loc[na_m].map({v: to_float_sqwah(v) for v in u_v})
        df['พื้นที่_ตารางวา'] = s_sqw

    if 'พื้นที่ใช้สอย (ตร.ม.)' not in df.columns:
        df['พื้นที่ใช้สอย (ตร.ม.)'] = np.nan
    else:
        raw_sqm = df['พื้นที่ใช้สอย (ตร.ม.)']
        s_sqm = pd.to_numeric(raw_sqm, errors='coerce')
        na_m = s_sqm.isna() & raw_sqm.notna()
        if na_m.any():
            u_v = raw_sqm.loc[na_m].unique()
            s_sqm.loc[na_m] = raw_sqm.loc[na_m].map({v: to_float_sqm(v) for v in u_v})
        df['พื้นที่ใช้สอย (ตร.ม.)'] = s_sqm
        bad_area_mask = (df['ราคา'] > 10000) & (df['พื้นที่ใช้สอย (ตร.ม.)'] == df['ราคา'])
        if 'ประเภททรัพย์' in df.columns:
            bad_area_mask |= (df['ประเภททรัพย์'].isin(['คอนโด', 'คอนโดมิเนียม', 'ห้องชุด', 'ห้องชุดพักอาศัย', 'ทาวน์เฮ้าส์', 'ทาวน์โฮม']) & (df['พื้นที่ใช้สอย (ตร.ม.)'] > 5000))
        df.loc[bad_area_mask, 'พื้นที่ใช้สอย (ตร.ม.)'] = np.nan

    if 'ราคาต่อตารางวา' not in df.columns:
        df['ราคาต่อตารางวา'] = np.where((df['พื้นที่_ตารางวา'] > 0) & (df['ราคา'] > 0), df['ราคา'] / df['พื้นที่_ตารางวา'], np.nan)
    else:
        df['ราคาต่อตารางวา'] = pd.to_numeric(df['ราคาต่อตารางวา'], errors='coerce')
        missing_puw = df['ราคาต่อตารางวา'].isna() & (df['พื้นที่_ตารางวา'] > 0) & (df['ราคา'] > 0)
        if missing_puw.any():
            df.loc[missing_puw, 'ราคาต่อตารางวา'] = df.loc[missing_puw, 'ราคา'] / df.loc[missing_puw, 'พื้นที่_ตารางวา']

    if 'ราคาต่อตารางเมตร' not in df.columns:
        df['ราคาต่อตารางเมตร'] = np.where((df['พื้นที่ใช้สอย (ตร.ม.)'] > 0) & (df['ราคา'] > 0), df['ราคา'] / df['พื้นที่ใช้สอย (ตร.ม.)'], np.nan)
    else:
        df['ราคาต่อตารางเมตร'] = pd.to_numeric(df['ราคาต่อตารางเมตร'], errors='coerce')
        missing_pum = df['ราคาต่อตารางเมตร'].isna() & (df['พื้นที่ใช้สอย (ตร.ม.)'] > 0) & (df['ราคา'] > 0)
        if missing_pum.any():
            df.loc[missing_pum, 'ราคาต่อตารางเมตร'] = df.loc[missing_pum, 'ราคา'] / df.loc[missing_pum, 'พื้นที่ใช้สอย (ตร.ม.)']

    if 'จังหวัด' in df.columns:
        def _clean_prov_val(v):
            if pd.isna(v):
                return np.nan
            s = str(v).strip().strip(" ,;.-'\"/\\")
            s = re.sub(r'^(จ\.|จังหวัด)\s*', '', s).strip()
            if s in ['กทม', 'กทม.', 'กรุงเทพ', 'กรุงเทพฯ']:
                s = 'กรุงเทพมหานคร'
            elif s in ['อยุธยา']:
                s = 'พระนครศรีอยุธยา'
            if s in ['', '-', 'nan', 'None', '<NA>', 'ไม่มีข้อมูล']:
                return np.nan
            if re.search(r'\d', s) or not re.search(r'^[ก-๙]', s):
                return np.nan
            return s

        u_provs = df['จังหวัด'].dropna().unique()
        df['จังหวัด'] = df['จังหวัด'].map({v: _clean_prov_val(v) for v in u_provs})
        df['ภาค'] = df['จังหวัด'].map(PROVINCE_TO_REGION).fillna('อื่นๆ / ไม่ระบุ')

    if 'ชั้น' not in df.columns:
        df['ชั้น'] = None
    else:
        df['ชั้น'] = df['ชั้น'].replace({'nan': None, 'None': None, 'null': None, '<NA>': None, 'NaN': None, '-': None, '': None})

    if 'เลขโฉนด' not in df.columns:
        df['เลขโฉนด'] = None
    else:
        df['เลขโฉนด'] = df['เลขโฉนด'].replace({'nan': None, 'None': None, 'null': None, '<NA>': None, 'NaN': None, '-': None, '': None})

    if 'โจทก์' not in df.columns:
        df['โจทก์'] = None
    else:
        df['โจทก์'] = _clean_plaintiff_series_fast(df['โจทก์']).replace({'': None})

    for _cnt_col in ('ยอดเข้าชม', 'ยอดคลิก'):
        if _cnt_col not in df.columns:
            df[_cnt_col] = pd.Series(pd.NA, index=df.index, dtype='Int64')
        else:
            num_s = pd.to_numeric(df[_cnt_col], errors='coerce')
            # Reject non-finite, negative, or scraper phone-number anomalies (> 2^31-1) cleanly without Int32 crash
            num_s = num_s.where(np.isfinite(num_s) & (num_s >= 0) & (num_s <= 2_147_483_647), np.nan)
            df[_cnt_col] = num_s.round(0).astype('Int64')

    if 'อำเภอ' in df.columns:
        s_amp = df['อำเภอ'].astype(object).where(df['อำเภอ'].notna(), '').astype(str).str.strip().str.strip(" ,;.-'\"/\\")
        s_amp = s_amp.replace({'nan': '', 'None': '', '<NA>': '', 'NaN': '', '-': '', 'ไม่มีข้อมูล': ''})
        en_amp_mask = (s_amp != '') & s_amp.str.contains(r'[a-zA-Z]', regex=True, na=False)
        if en_amp_mask.any():
            def _safe_clean_amp(val):
                res = translate_amphoe_en_to_th(val)
                return res if re.match(r'^[ก-๙]', str(res or '')) else ''
            u_amp = s_amp.loc[en_amp_mask].unique()
            s_amp.loc[en_amp_mask] = s_amp.loc[en_amp_mask].map({v: _safe_clean_amp(v) for v in u_amp})
        df['อำเภอ'] = s_amp.replace({'': np.nan})

    if 'ตำบล' in df.columns:
        s_tam = df['ตำบล'].astype(object).where(df['ตำบล'].notna(), '').astype(str).str.strip().str.strip(" ,;.-'\"/\\")
        s_tam = s_tam.replace({'nan': '', 'None': '', '<NA>': '', 'NaN': '', '-': '', 'ไม่มีข้อมูล': ''})
        en_tam_mask = (s_tam != '') & s_tam.str.contains(r'[a-zA-Z]', regex=True, na=False)
        if en_tam_mask.any():
            u_tam = s_tam.loc[en_tam_mask].unique()
            tam_lut = {
                v: (re.sub(r'[a-zA-Z\(\)\[\]]+', '', str(v)).strip() if re.search(r'[ก-๙]', str(v)) else '')
                for v in u_tam
            }
            s_tam.loc[en_tam_mask] = s_tam.loc[en_tam_mask].map(tam_lut)
        df['ตำบล'] = s_tam.replace({'': np.nan})

    # Pre-clean normalized project name for ultra-fast competitor matching
    if 'norm_project_name' not in df.columns or (len(df) > 0 and not bool(df['_is_derived_clean'].fillna(False).all() if '_is_derived_clean' in df.columns else False)):
        if 'ชื่อโครงการ' in df.columns:
            u_projs = df['ชื่อโครงการ'].dropna().unique()
            norm_map = {p: normalize_project_name(p) for p in u_projs if p}
            df['norm_project_name'] = df['ชื่อโครงการ'].map(norm_map).fillna('')
        else:
            df['norm_project_name'] = ''

    # Preserve float64 for high-value prices (>16.77M Baht), 5-6 decimal coordinates, areas, and unit rates
    for f64_col in ['ราคา', 'ราคาขายได้', 'ละติจูด', 'ลองจิจูด', 'พื้นที่_ตารางวา', 'พื้นที่ใช้สอย (ตร.ม.)', 'ราคาต่อตารางวา', 'ราคาต่อตารางเมตร']:
        if f64_col in df.columns:
            df[f64_col] = pd.to_numeric(df[f64_col], errors='coerce').astype('float64')

    # Convert repeated string columns to category for 5x faster filtering and 70% less RAM
    for col in ['บริษัท', 'ประเภททรัพย์', 'จังหวัด', 'ภาค', 'ประเภทการขาย', 'อำเภอ', 'ตำบล']:
        if col in df.columns:
            df[col] = df[col].astype('category')

    df = _apply_led_legal_sold_prices(df)
    df['_is_derived_clean'] = True
    return df
