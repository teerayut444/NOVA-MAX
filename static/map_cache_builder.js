(function (global) {
  'use strict';

  const GRID_CELL_SIZE = 0.2; // ~22 km grid buckets for instantaneous spatial lookup
  const DEFAULT_CO_RGB = [148, 163, 184];

  const BRAND_TAG_RULES = [
    [/eastgate|อีสท์เกต/i, 'Eastgate / อีสท์เกต'],
    [/ไอดีโอ|ไอดิโอ|ไอเดีย|ideo|ไอดิโอ้|ไอดีโอ้/i, 'IDEO / ไอดิโอ'],
    [/ลุมพ[ิีึื]น[ิีึื]|lumpini|lpn/i, 'LPN / Lumpini'],
    [/พฤกษา|พฤษภา|พฤษา|พึกษา|พฤกสา|pruksa|ps\b/i, 'Pruksa / PS'],
    [/[ศส]ุ[ภพ]าลัย|supalai|spali/i, 'Supalai / ศุภาลัย'],
    [/แสนสิริ|sansiri|siri\b/i, 'Sansiri / แสนสิริ'],
    [/แอสปา[ยร์]+|aspire/i, 'Aspire / แอสปาย'],
    [/ดีคอนโด|dcondo/i, 'Dcondo'],
    [/เดอะ\s*เบส|the\s*base/i, 'The Base'],
    [/ไลฟ์|life\b/i, 'Life'],
    [/ริ[ทธ]ึ่?[มม์]|rhythm/i, 'Rhythm'],
    [/ไนท์บริด[จช์]+|knightsbridge/i, 'Knightsbridge'],
    [/พลัม|plum/i, 'Plum'],
    [/คาซ่า|casa/i, 'Casa'],
    [/เซ็?นทริค|centric/i, 'Centric'],
    [/คอนโดเล็?ต|condolette/i, 'Condolette'],
    [/ยู\s*ดีไลท์|udelight/i, 'U Delight'],
    [/แชปเตอร์\s*วัน|chapter\s*one/i, 'Chapter One'],
    [/รีเจ้?นท์?|regent/i, 'Regent'],
    [/โนเบิล|noble/i, 'Noble'],
    [/พาร์?คแลน[ด์]*|parkland/i, 'Parkland'],
    [/แอชตัน|ashton/i, 'Ashton'],
    [/เอล?ลิโอ|elio/i, 'Elio'],
    [/ยูนิโอ|unio/i, 'Unio'],
    [/โมดิซ|modiz/i, 'Modiz'],
    [/แอทโม[ซส]|atmoz/i, 'Atmoz'],
    [/เคฟ|kave/i, 'Kave'],
    [/แชมเบอร์?ส?|chambers/i, 'Chambers / แชมเบอร์ส'],
    [/เดอะ\s*คิวบ์?|the\s*cube/i, 'The Cube / เดอะคิวบ์'],
    [/พลีโน่?|pleno/i, 'Pleno / พลีโน่'],
    [/บริทาเนีย|britania/i, 'Britania'],
    [/ออริจิ้?น|origin/i, 'Origin / ออริจิ้น'],
    [/ริช\s*พาร์?ค|rich\s*park/i, 'Rich Park / ริชพาร์ค'],
    [/เดอะ\s*ทรี|the\s*tree/i, 'The Tree / เดอะทรี'],
    [/เมโทร\s*ลักซ์?|metro\s*luxe/i, 'Metro Luxe / เมโทรลักซ์'],
    [/เดอะ\s*ทรัสต์?|the\s*trust/i, 'The Trust / เดอะทรัสต์'],
    [/ชวนชื่?น|chuanchuen/i, 'Chuan Chuen / ชวนชื่น'],
    [/เพอร์เฟ[็คกต์]+|perfect/i, 'Perfect / เพอร์เฟค'],
    [/[ภพ]ัสสร|passorn/i, 'Passorn / ภัสสร'],
    [/มั?ณฑนา|mantana/i, 'Mantana / มัณฑนา'],
    [/ชัยพฤก[ษ์ษา]+|chaiyapruek/i, 'Chaiyapruek / ชัยพฤกษ์'],
    [/วิลลาจจิ?โอ|villaggio/i, 'Villaggio / วิลลาจจิโอ'],
    [/อินดี้?|indy\b/i, 'Indy / อินดี้']
  ];

  function getBrandSearchTag(name) {
    if (!name) return '';
    const str = name.toString();
    for (let i = 0; i < BRAND_TAG_RULES.length; i++) {
      if (BRAND_TAG_RULES[i][0].test(str)) {
        return BRAND_TAG_RULES[i][1];
      }
    }
    return '';
  }

  const EXTRA_INVALID_PROJECT_TOKENS = new Set([
    'ราคา', 'มิเนียม', 'จัดสรร', 'บ้านจัดสรร', 'ที่ดินจัดสรร', 'รายย่อย', 'เปล่า',
    'ใหม่', 'ติด', 'ติดทะเล', 'ติดถนน', 'หรู', 'เทล', 'เอส', 'โฮม',
    'ห้องสวย', 'ห้องใหญ่', 'ห้องมุม', 'หลังมุม', 'แปลงมุม', 'ถมแล้ว', 'วิวทะเล',
    'ออมสิน', 'call', 'modern', 'tropical', 'boho style', 'low rise', 'high rise',
    'ขนาดใหญ่', 'เลต', 'สอบถามโทร', 'บ้าน สตูดิโอ', 'สำหรับ ขาย คอนโด', 'สำหรับขายคอนโด',
    'พร้อมสิ่งปลูกสร้าง', 'การเคหะ', 'การเคหะแห่งชาติ', 'in1'
  ]);

  const THAI_ZONE_LOCATION_TOKENS = new Set([
    // Provinces & nicknames
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
    // Major tourist / regional zones
    'พัทยา', 'บางแสน', 'สัตหีบ', 'ศรีราชา', 'แหลมฉบัง', 'บ้านบึง', 'บ่อวิน', 'ปลวกแดง', 'มาบตาพุด',
    'จอมเทียน', 'นาเกลือ', 'หัวหิน', 'ชะอำ', 'ปราณบุรี', 'เขาใหญ่', 'ปากช่อง', 'สมุย', 'เกาะสมุย',
    'ป่าตอง', 'กะทู้', 'ถลาง', 'กะรน', 'กมลา', 'ราไวย์', 'ฉลอง', 'หาดใหญ่', 'นิมมาน', 'แม่ริม',
    'หางดง', 'สันทราย', 'สันกำแพง', 'สารภี', 'ดอยสะเก็ด',
    'huahin', 'pattaya', 'bangsaen', 'samui', 'phuket', 'chiangmai', 'korat', 'rangsit', 'salaya',
    'khonkaen', 'rayong', 'chonburi', 'prachuap', 'khiri', 'khan', 'naklua', 'jomtien', 'patong', 'hatyai',
    // Bangkok & Vicinity roads, zones, transit hubs, landmarks
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
    'sukhumvit', 'asoke', 'asok', 'thonglor', 'ekkamai', 'ekamai', 'silom', 'sathorn', 'sathon',
    'rama', 'ladprao', 'latphrao', 'ratchada', 'bangna', 'onnut', 'udomsuk', 'bearing', 'lasalle',
    'ramintra', 'nawamin', 'ramkhamhaeng', 'pinklao', 'charan', 'ratchaphruek', 'chaengwattana',
    'tiwanon', 'ngamwongwan', 'rattanathibet', 'phaholyothin', 'srinakarin', 'pattanakarn',
    'phetkasem', 'bangkae', 'bangyai', 'bangbuathong', 'donmueang', 'lamlukka', 'saimai',
    'minburi', 'latkrabang', 'prawet'
  ]);
  const AMBIGUOUS_SINGLE_LOCATION_NAMES = new Set(['เมืองทอง', 'บางแสน', 'สุขสวัสดิ์', 'เกษตร', 'นานา', 'บางพระ', 'ศรีสุนทร']);
  const PROTECTED_ESTATE_BRAND_PREFIXES = new Set(['ชัยพฤกษ์', 'ราชพฤกษ์', 'บัวทอง', 'ลุมพินี', 'เมืองทอง']);
  const ROAD_WITH_NUM_RE = /^(?:พระราม\s*[1-9]|โชคชัย\s*4|ลาดพร้าว\s*\d+|สุขุมวิท\s*\d+|พหลโยธิน\s*\d+|รามคำแหง\s*\d+|เพชรเกษม\s*\d+|รัชดา(?:ภิเษก)?\s*\d+|จรัญ(?:สนิทวงศ์)?\s*\d+|อ่อนนุช\s*\d+|บางนา[\s\-]*ตราด(?:\s*กม\.?\s*\d+)?|huahin\s*\d+|หัวหิน\s*\d+|สุขาภิบาล\s*\d+|พุทธมณฑล\s*สาย\s*\d+|สาย\s*\d+)$/i;

  function isPureLocationProjectName(name) {
    if (!name) return false;
    let s = name.toString().trim().replace(/^['"“‘\s]+|['"”’\s]+$/g, '');
    if (!s) return false;
    // Protect real numbered-address condos e.g. '185 ราชดำริ', '28 ชิดลม', '168 สุขุมวิท 36'
    if (/^\d{2,4}\s+[ก-๙a-zA-Z]/.test(s)) return false;
    if (ROAD_WITH_NUM_RE.test(s)) return true;

    const rawTokens = s.split(/[\s\-–—/,|&]+/).map(t => t.trim().toLowerCase()).filter(Boolean);
    if (rawTokens.length === 0) return false;

    const nonNum = [];
    let hasNum = false;
    for (let i = 0; i < rawTokens.length; i++) {
      const tok = rawTokens[i];
      if (/^\d+[a-z]?$/i.test(tok)) {
        hasNum = true;
        continue;
      }
      const tc = tok.replace(/^(?:จ\.|จังหวัด|อ\.|อำเภอ|เขต|ต\.|ตำบล|แขวง|ถ\.|ถนน|ซ\.|ซอย|แยก|ย่าน|โซน)/, '').trim();
      if (tc) nonNum.push(tc);
    }
    if (nonNum.length === 0) return false;

    if (nonNum.length === 1 && !hasNum) {
      return THAI_ZONE_LOCATION_TOKENS.has(nonNum[0]) && !AMBIGUOUS_SINGLE_LOCATION_NAMES.has(nonNum[0]);
    }
    if (nonNum.length >= 2) {
      if (PROTECTED_ESTATE_BRAND_PREFIXES.has(nonNum[0])) return false;
      for (let i = 0; i < nonNum.length; i++) {
        const tk = nonNum[i];
        if (tk !== 'ราชพฤกษ์' && !THAI_ZONE_LOCATION_TOKENS.has(tk)) return false;
      }
      return true;
    }
    return false;
  }

  function isInvalidProjectName(p) {
    if (!p) return true;
    let s = p.toString().trim();
    s = s.replace(/^['"“‘\s]+|['"”’\s]+$/g, '');
    const sLower = s.toLowerCase();
    if (
      !s ||
      sLower === '-' ||
      sLower === '--' ||
      sLower === '---' ||
      sLower === '.' ||
      sLower === '..' ||
      sLower === '...' ||
      sLower === 'nan' ||
      sLower === 'none' ||
      sLower === 'null' ||
      sLower === 'undefined' ||
      sLower === 'ไม่มีข้อมูล' ||
      sLower === 'ไม่มีชื่อ' ||
      sLower === 'ไม่ระบุ' ||
      sLower === 'โครงการไม่มีชื่อ' ||
      sLower === 'ไม่มี' ||
      sLower === 'โครงการ' ||
      sLower === 'หมู่บ้าน' ||
      sLower === 'คอนโด' ||
      sLower === 'บ้านเดี่ยว' ||
      sLower === 'ที่ดิน' ||
      sLower === 'ทาวน์โฮม' ||
      sLower === 'อาคารพาณิชย์' ||
      sLower === 'ห้องชุด' ||
      sLower === 'บ้าน' ||
      sLower === 'ตึก' ||
      sLower === 'ทาวน์เฮ้าส์' ||
      sLower === 'อพาร์ทเม้นท์' ||
      sLower === 'อาคารชุด' ||
      EXTRA_INVALID_PROJECT_TOKENS.has(sLower)
    ) {
      return true;
    }
    if (s.length <= 2) return true;
    if (/^@[a-zA-Z0-9_.\-]+/.test(s)) return true;
    if (/(?:สถาบัน|ถาบัน|าบัน|บัน)?(?:โดย|ดย)\s*(?:ghb|gsb|bam|sam|ktb|scb|kbank)\b/i.test(s)) return true;
    if (/^(?:สำหรับ\s*ขาย|สอบถาม|ติดต่อ|วิวทะเล|วิวเขา|พร้อมที่ดิน|พร้อมสิ่งปลูกสร้าง|บ้าน\s*สตูดิโอ|\+\s*บ้าน|private\s+house\b|pool\s+villa\b|house\s+for\s+sale\b|condo\s+for\s+sale\b)/i.test(s)) return true;
    if (/^-?\d{1,2}\.\d+[\s,]+-?\d{2,3}\.\d+$/.test(s)) return true;
    if (/^[\d.,/\s-]+$/.test(s)) return true;
    if (/^(บ้านเดี่ยว|บ้านแฝด|บ้าน|ทาวน์โฮม|ทาวน์เฮ้าส์|ทาวน์เฮาท์|คอนโด|ห้องชุด|ที่ดิน|อาคารพาณิชย์|ตึกแถว|เดี่ยว|เฮ้าส์|เฮาส์|เฮาท์|พาณิชย์|แฝด|แถว)\s*\d+(?:\s*-?\s*(?:ห้องนอน|ห้องน้ำ|ชั้น))?$/i.test(s)) return true;
    if (/^(?:บ้านเดี่ยว|บ้านแฝด|บ้านตึก|บ้านไม้|บ้านครึ่งตึกครึ่งไม้|บ้าน|ทาวน์เฮ้าส์|ทาวน์โฮม|ทาวเฮ้าส์|ทาวน์ฮ้าส์|ทาวน์เฮาท์|ตึกแถว|อาคารพาณิชย์|อาคารโกดัง|วิลล่า|คอนโด)?\s*\d+(?:\.\d+)?\s*ชั้น(?:$|\s|ครึ่ง|[0-9])/i.test(s)) return true;
    if (/^\d{5}\s*(?:บ้าน|ทาวน์|อาคาร|ที่ดิน|คอนโด|เดอะ|มบ\.|หมู่บ้าน|ทาวเฮ้าส์)/i.test(s)) return true;
    if (/^\d+[\d.,/-]*\s*(?:ตร\.?ว\.?|ตร\.?ม\.?|ตารางวา|ตารางเมตร|ไร่|วา)(?:$|\s|\d)/i.test(s)) return true;
    if (/^(?:ใกล้|ติด)\s*(?:bts|mrt|แอร์พอร์ต|ทางด่วน|ถนน|สถานี|ห้าง|รถไฟฟ้า|ทะเล|หาด)/i.test(s)) return true;
    if (/^\d+\s*ห้อง(นอน)?(\s*\d+\s*ห้องน้ำ)?\s*$/i.test(s) || /^(สตูดิโอ|ห้องนอน|ห้องน้ำ|studio)\s*$/i.test(s) || /^\d+\s*bed(room)?s?\s*$/i.test(s)) return true;
    if (/(?:\d+\s*-?\s*(?:ห้องนอน|ห้องน้ำ)|\d+\s*นอน\s*\d+\s*น้ำ|ห้อง(?:นอน|น้ำ)?\s*\d+\s*ห้อง)/i.test(s)) return true;
    if (/^(?:ขายด่วน|ขายถูก|ขายบ้าน|ขายคอนโด|ให้เช่า|ต้องการขาย|ลดราคา|ขาย|เช่า|เซ้ง|ด่วน)(?:\s|$|[ก-๙0-9])/i.test(s)) return true;
    if (/ขาย(?:คอนโด|บ้าน|ทาวน์|ที่ดิน)/i.test(s)) return true;
    if (/(?:ราคา|ขายเพียง|ลดเหลือ|ผ่อนเพียง|ตรว\.ละ|วาละ|ขาย|เช่า)\s*\d+(?:\.\d+)?\s*(?:ลบ|ล้าน|แสน|บาท|บ(?:\.|\s|$))/i.test(s)) return true;
    if (/(?:ขายด่วน|ด่วนมาก|ลดกระหน่ำ|ขายถูกที่สุด|ราคาถูกที่สุด|รีโนเวทใหม่|รีโนเวทแล้ว|ตกแต่งใหม่ทั้งหลัง|พร้อมอยู่ทันที|กู้เต็ม|กู้ได้เต็ม|ฟรีโอน|ขายขาดทุน|เจ้าของขายเอง|ผ่อนตรง|รับผ่อนตรง|agent welcomed|ขายยกแปลง)/i.test(s)) return true;
    if (/(?:โทร|tel|contact|line\s*id)\s*[:\.]?\s*\d/i.test(s)) return true;
    if (/\d+[\d.,]*\s*(?:ตร\.?ว\.?|ตร\.?ม\.?|ตารางวา|ตารางเมตร)(?:$|\s|\d)/i.test(s) && s.length > 15) return true;
    if (/ใน(?:อำเภอ|อ\.)\s*[ก-๙]+/i.test(s) && /ราคา/i.test(s)) return true;
    if (/(?:พร้อมอยู่|ตกแต่งครบ|เฟอร์นิเจอร์|ฟรีโอน|วิวสวย|วิวทะเล|วิวสระ|ทำเลทอง)/i.test(s) && s.length > 20) return true;
    if (isPureLocationProjectName(s)) return true;
    return false;
  }

  function _medianNum(arr) {
    const n = arr.length;
    if (n === 0) return 0;
    const sorted = arr.slice().sort((a, b) => a - b);
    const mid = Math.floor(n / 2);
    return n % 2 === 1 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
  }

  function isSpatiallyScatteredGroup(items, maxMedianKm = 5.0, maxPairKm = 10.0) {
    if (!items || items.length < 2) return false;
    const allPts = [];
    const ncPts = [];
    for (let i = 0; i < items.length; i++) {
      const d = items[i];
      const lat = +d.lat;
      const lon = +d.lon;
      if (!Number.isFinite(lat) || !Number.isFinite(lon) || lat < 5.0 || lat > 21.0 || lon < 97.0 || lon > 106.0) continue;
      const pt = [lat, lon];
      allPts.push(pt);
      if (String(d._centroid || '') !== '1') ncPts.push(pt);
    }
    const pts = ncPts.length >= 2 ? ncPts : allPts;
    if (pts.length < 2) return false;

    const lats = pts.map(pt => pt[0]);
    const lons = pts.map(pt => pt[1]);
    const medLat = _medianNum(lats);
    const medLon = _medianNum(lons);
    const cosLat = Math.cos((medLat * Math.PI) / 180.0);
    const dists = pts.map(pt => Math.hypot((pt[0] - medLat) * 111.0, (pt[1] - medLon) * 111.0 * cosLat));
    const medDist = _medianNum(dists);
    if (pts.length === 2) {
      return medDist > maxPairKm / 2.0;
    }
    return medDist > maxMedianKm;
  }

  function cleanDisplayProjectName(name) {
    if (!name) return '';
    let txt = name.toString().trim();
    txt = txt.replace(/^['"“‘\s]+|['"”’\s]+$/g, '');
    if (txt.includes(' : ')) {
      const parts = txt.split(' : ');
      txt = parts.length > 1 ? parts[1] : parts[0];
    }
    txt = txt
      .replace(/ลุมพินี\s*ทาวน์ชิป\s*รังสิต/gi, 'ลุมพินี ทาวน์ชิป รังสิต')
      .replace(/ทางน์ชิป|ทาวชิป|ทาวน์ซิป|ทาวนชิป/gi, 'ทาวน์ชิป')
      .replace(/\btownship\b/gi, 'ทาวน์ชิป')
      .replace(/\bc[\s,\.]*d[\s,\.]*e[\s,\.]*f\b/gi, 'ซีดีอีเอฟ')
      .replace(/\bc[\s,\.]*d[\s,\.]*e\b/gi, 'ซีดีอี')
      .replace(/\ba[\s,\.]*b\b/gi, 'เอบี')
      .replace(/\bc[\s,\.]*d\b/gi, 'ซีดี')
      .replace(/\be[\s,\.]*f\b/gi, 'อีเอฟ')
      .replace(/\bf[\s,\.]*g\b/gi, 'เอฟจี');

    txt = txt
      .replace(/เดอะ\s*คิว(?:บ์|บ)/gi, 'เดอะคิวบ์')
      .replace(/เดอะ\s*คอนเน[คกต์]+/gi, 'เดอะ คอนเนค')
      .replace(/เดอะ\s*เบส/gi, 'เดอะเบส')
      .replace(/เดอะ\s*ทรี/gi, 'เดอะทรี')
      .replace(/เดอะ\s*ทรัสต์?/gi, 'เดอะทรัสต์')
      .replace(/รีเจ้?น[ท์]*/gi, 'รีเจ้นท์')
      .replace(/ไอดีโอ้?|ไอดิโอ้?|ไอเดีย/gi, 'ไอดีโอ')
      .replace(/พฤกษ์?ลดา/gi, 'พฤกษ์ลดา')
      .replace(/มั?ณฑนา/gi, 'มัณฑนา')
      .replace(/ชัยพฤก[ษ์ษา]+/gi, 'ชัยพฤกษ์')
      .replace(/เพอร์?เฟ[็คกต์]+/gi, 'เพอร์เฟค')
      .replace(/วิลลาจจิ?โอ/gi, 'วิลลาจจิโอ')
      .replace(/อินดี้?/gi, 'อินดี้');

    txt = txt
      .replace(/(^|[^ก-๙a-zA-Z])([ก-๙a-zA-Z])\s*,\s*([ก-๙a-zA-Z])\s*,\s*([ก-๙a-zA-Z])(?![ก-๙a-zA-Z])/g, '$1$2$3$4')
      .replace(/(^|[^ก-๙a-zA-Z])([ก-๙a-zA-Z])\s*,\s*([ก-๙a-zA-Z])(?![ก-๙a-zA-Z])/g, '$1$2$3')
      .replace(/(^|[^ก-๙a-zA-Z])([ก-๙a-zA-Z])\s*\.\s*([ก-๙a-zA-Z])\s*\.\s*([ก-๙a-zA-Z])(?![ก-๙a-zA-Z])/g, '$1$2$3$4')
      .replace(/(^|[^ก-๙a-zA-Z])([ก-๙a-zA-Z])\s*\.\s*([ก-๙a-zA-Z])(?![ก-๙a-zA-Z])/g, '$1$2$3')
      .replace(/\s*-\s*/g, '-')
      .replace(/คลอง\s*(\d+)/g, 'คลอง $1')
      .replace(/\s+/g, ' ')
      .trim();
    return txt;
  }

  function normalizeProjectKeyword(str) {
    if (!str) return '';
    let txt = str.toString().trim().toLowerCase();
    txt = txt.replace(/^['"“‘\s]+|['"”’\s]+$/g, '');
    if (txt.includes(' : ')) {
      const parts = txt.split(' : ');
      txt = parts.length > 1 ? parts[1] : parts[0];
    }
    const prefixRe = /^(คอนโด\s*โครงการ|โครงการ\s*คอนโด|โครงการ\s*หมู่บ้าน|อาคารชุด|คอนโดมิเนียม|มีเนียม|โครงการ|หมู่บ้าน|คอนโด|บ้านเดี่ยว|บ้านแฝด|บ้าน(?!กลางเมือง|กลางกรุง|พฤกษา)|ทาวน์โฮม|ทาวน์เฮ้าส์|ขายคอนโด)\s*/i;
    while (true) {
      const nt = txt.replace(prefixRe, '').trim();
      if (nt === txt) break;
      txt = nt;
    }
    txt = txt.replace(
      /(\[.*?\]|\(\s*(?:มือสอง|เจ้าของขายเอง|ราคาพิเศษ|พร้อมอยู่|ขายด่วน|ด่วน|ลดราคา|รีโนเวท|renovate|ห้องมุม|corner|วิว[^)]*|ใกล้\s*(?:bts|mrt|arl)[^)]*|ติด\s*(?:bts|mrt|arl)[^)]*|ไม่ระบุ|ไม่มี|null|none)\s*\)|\[[^\]]*$|\([^)]*$|,\s*(กรุงเทพมหานคร|กรุงเทพฯ|กรุงเทพ|นนทบุรี|ปทุมธานี|สมุทรปราการ|ชลบุรี|เชียงใหม่|ระยอง|ภูเก็ต).*$|[\s\-_/]+(?:อาคาร|ตึก)\s+[a-zA-Z0-9ก-๙]\s+ชั้น\s*\d+.*$|[\s\-_/]+ชั้น\s*\d+.*$|ชั้น\s*\d+.*$|(?:^|\s)(?:ติด|ใกล้)\s*(?:bts|mrt).*$)/gi,
      ''
    );

    txt = txt
      .replace(/คลอง\s*(\d+)/g, 'คลอง$1')
      .replace(/เฟส\s*(\d+)/g, 'เฟส$1')
      .replace(/ซอย\s*(\d+)/g, 'ซอย$1')
      .replace(/สาย\s*(\d+)/g, 'สาย$1')
      .replace(/phase\s*(\d+)/gi, 'เฟส$1');

    txt = txt
      .replace(/\bsukhumvit\b|สุขุมวิท/gi, 'สุขุมวิท')
      .replace(/\brama\b|พระราม/gi, 'พระราม')
      .replace(/\b(?:sathorn|sathon)\b|สาทร/gi, 'สาทร')
      .replace(/\b(?:asoke|asok)\b|อโศก/gi, 'อโศก')
      .replace(/\b(?:ladprao|latphrao)\b|ลาดพร้าว/gi, 'ลาดพร้าว')
      .replace(/\btiwanon\b|ติวานนท์/gi, 'ติวานนท์')
      .replace(/\b(?:bangna|bang\s*na)\b|บางนา/gi, 'บางนา')
      .replace(/\bratchada\b|รัชดา/gi, 'รัชดา')
      .replace(/\b(?:thonglor|thong\s*lo)\b|ทองหล่อ/gi, 'ทองหล่อ')
      .replace(/\b(?:ekkamai|ekamai)\b|เอกมัย/gi, 'เอกมัย')
      .replace(/\bsilom\b|สีลม/gi, 'สีลม')
      .replace(/\brangsit\b|รังสิต/gi, 'รังสิต')
      .replace(/\bklong\b/gi, 'คลอง')
      .replace(/\bmobi\b|โมบิ/gi, 'โมบิ')
      .replace(/\bville\b|วิลล์/gi, 'วิลล์')
      .replace(/\bpark\b|พาร์ค|ปาร์ค/gi, 'พาร์ค')
      .replace(/\bplace\b|เพลส/gi, 'เพลส')
      .replace(/\bprime\b|ไพร์ม/gi, 'ไพร์ม')
      .replace(/\bveranda\b|เวอเรนด้า/gi, 'เวอเรนด้า')
      .replace(/\bcampus\b|แคมปัส/gi, 'แคมปัส')
      .replace(/\bresort\b|รีสอร์ท/gi, 'รีสอร์ท')
      .replace(/\bstation\b|สเตชั่น/gi, 'สเตชั่น')
      .replace(/\bcondo\b/gi, 'คอนโด')
      .replace(/ทางน์ชิป|ทาวชิป|ทาวน์ซิป|ทาวนชิป|\btownship\b/gi, 'ทาวน์ชิป')
      .replace(/ซี[,\.\s]*ดี[,\.\s]*อี[,\.\s]*เอฟ|\bc[\s,\.]*d[\s,\.]*e[\s,\.]*f\b/gi, 'ซีดีอีเอฟ')
      .replace(/ซี[,\.\s]*ดี[,\.\s]*อี|\bc[\s,\.]*d[\s,\.]*e\b/gi, 'ซีดีอี')
      .replace(/เอ[,\.\s]*บี|\ba[\s,\.]*b\b/gi, 'เอบี')
      .replace(/ซี[,\.\s]*ดี|\bc[\s,\.]*d\b/gi, 'ซีดี')
      .replace(/อี[,\.\s]*เอฟ|\be[\s,\.]*f\b/gi, 'อีเอฟ')
      .replace(/เอฟ[,\.\s]*จี|\bf[\s,\.]*g\b/gi, 'เอฟจี')
      .replace(/บี[.\s]*เค[.\s]*|\bb[\s\.]*k\b/gi, 'บีเค')
      .replace(/เอส[.\s]*ซี[.\s]*|\bs[\s\.]*c\b/gi, 'เอสซี')
      .replace(/สินมั่?นคง/gi, 'สินมั่นคง')
      .replace(/\beastgate\b/gi, 'อีสท์เกต')
      .replace(/ไอดีโอ้?|ไอดิโอ้?|ไอเดีย|\b(?:ideo|idio)\b/gi, 'ไอดีโอ')
      .replace(/ลุมพ[ิีึื]น[ิีึื]|\b(?:lumpini|lpn)\b/gi, 'ลุมพินี')
      .replace(/พฤกษาวิลล์?|\bpruksa\s*ville\b/gi, 'พฤกษาวิลล์')
      .replace(/บ้านพฤกษา|\bbaan\s*pruksa\b/gi, 'บ้านพฤกษา')
      .replace(/พฤกษา|พฤษภา|พฤษา|พึกษา|พฤกสา|พฤษษา|พฤกษภ|\b(?:pruksa|ps)\b/gi, 'พฤกษา')
      .replace(/[ศส]ุ[ภพ]าลัย|\b(?:supalai|spali)\b/gi, 'ศุภาลัย')
      .replace(/แสนสิริ|\b(?:sansiri|siri)\b/gi, 'แสนสิริ')
      .replace(/แอสปา[ยร์]+|\baspire\b/gi, 'แอสปาย')
      .replace(/ดีคอนโด|\b(?:dcondo|d\s*condo)\b/gi, 'ดีคอนโด')
      .replace(/เดอะ\s*เบส|\bthe\s*base\b/gi, 'เดอะเบส')
      .replace(/ไลฟ์|\blife\b/gi, 'ไลฟ์')
      .replace(/ริ[ทธ]ึ่?[มม์]|\brhythm\b/gi, 'ริทึ่ม')
      .replace(/ไนท์บริด[จช์]*|\bknightsbridge\b/gi, 'ไนท์บริดจ์')
      .replace(/พลัม|\bplum\b/gi, 'พลัม')
      .replace(/คาซ่า?|\bcasa\b/gi, 'คาซ่า')
      .replace(/เซ็?นทริ[คก]|\bcentric\b/gi, 'เซ็นทริค')
      .replace(/คอนโดเล็?ต|\bcondolette\b/gi, 'คอนโดเลต')
      .replace(/ยู\s*ดีไลท์|\bu\s*delight\b/gi, 'ยูดีไลท์')
      .replace(/แชปเตอร์\s*วัน|\bchapter\s*one\b/gi, 'แชปเตอร์วัน')
      .replace(/รีเจ้?น[ท์]*|\bregent\b/gi, 'รีเจ้นท์')
      .replace(/โนเบิ?ล|\bnoble\b/gi, 'โนเบิล')
      .replace(/พาร์?คแลน[ด์]*|\bparkland\b/gi, 'พาร์คแลนด์')
      .replace(/แอชตัน|\bashton\b/gi, 'แอชตัน')
      .replace(/เอล?ลิโอ|\belio\b/gi, 'เอลิโอ')
      .replace(/ยูนิโอ|\bunio\b/gi, 'ยูนิโอ')
      .replace(/โมดิ[ซสช]|\bmodiz\b/gi, 'โมดิซ')
      .replace(/แอทโม[ซส]|\batmoz\b/gi, 'แอทโมซ')
      .replace(/เคฟ|\bkave\b/gi, 'เคฟ')
      .replace(/แชมเบอร์?ส?|\bchambers\b/gi, 'แชมเบอร์ส')
      .replace(/เดอะ\s*คิว(?:บ์|บ)?|\bthe\s*cube\b/gi, 'เดอะคิวบ์')
      .replace(/พลีโน่?|\bpleno\b/gi, 'พลีโน่')
      .replace(/บริทาเนีย|\bbritani?a\b/gi, 'บริทาเนีย')
      .replace(/ออริจิ้?น|\borigin\b/gi, 'ออริจิ้น')
      .replace(/ริช\s*พาร์?ค|\brich\s*park\b/gi, 'ริชพาร์ค')
      .replace(/เดอะ\s*ทรี|\bthe\s*tree\b/gi, 'เดอะทรี')
      .replace(/เมโทร\s*ลักซ์?|\bmetro\s*luxe\b/gi, 'เมโทรลักซ์')
      .replace(/เดอะ\s*ทรัสต์?|\bthe\s*trust\b/gi, 'เดอะทรัสต์')
      .replace(/ชวนชื่?น|\b(?:chuanchuen|chuan\s*chuen)\b/gi, 'ชวนชื่น')
      .replace(/เพอร์?เฟ[็คกต์]+|\bperfect\b/gi, 'เพอร์เฟค')
      .replace(/[ภพ]ัสสร|\bpassorn\b/gi, 'ภัสสร')
      .replace(/มั?ณฑนา|\bmantana\b/gi, 'มัณฑนา')
      .replace(/ชัยพฤก[ษ์ษา]+|\bchaiyapruek\b/gi, 'ชัยพฤกษ์')
      .replace(/วิลลาจจิ?โอ|\bvillaggio\b/gi, 'วิลลาจจิโอ')
      .replace(/อินดี้?|\bindy\b/gi, 'อินดี้')
      .replace(/ฮาบิเทีย|\bhabitia\b/gi, 'ฮาบิเทีย')
      .replace(/ส[ะา]ราญสิริ|\bsaransiri\b/gi, 'สราญสิริ')
      .replace(/บุราสิริ|\bburasiri\b/gi, 'บุราสิริ')
      .replace(/(?:เ[ศส]|ส)รษฐสิริ|\bsetthasiri\b/gi, 'เศรษฐสิริ')
      .replace(/นาราสิริ|\bnarasiri\b/gi, 'นาราสิริ')
      .replace(/คณาสิริ|\bkanasiri\b/gi, 'คณาสิริ')
      .replace(/อณาสิริ|\banasiri\b/gi, 'อณาสิริ')
      .replace(/เซ็?นโทร|\bcentro\b/gi, 'เซนโทร')
      .replace(/บ้านกลางเมือง|\bbaan\s*klang\s*muang\b/gi, 'บ้านกลางเมือง')
      .replace(/บ้านกลางกรุง|\bbaan\s*klang\s*krung\b/gi, 'บ้านกลางกรุง')
      .replace(/ซิตี้เซนส์?|\bcity\s*sense\b/gi, 'ซิตี้เซนส์')
      .replace(/เดอะ\s*คอนเน[คกต์]+|\bthe\s*connect\b/gi, 'เดอะ คอนเนค')
      .replace(/เดอะ\s*ซิตี้|\bthe\s*city\b/gi, 'เดอะ ซิตี้')
      .replace(/เดอะ\s*ไลน์|\bthe\s*line\b/gi, 'เดอะ ไลน์')
      .replace(/ทิพมา[ศส]/gi, 'ทิพมาศ')
      .replace(/คาร์พ[ิี]เดี้ย?ม/gi, 'คาร์พิเดียม')
      .replace(/เดอะ\s*คันทรี?่?|\bthe\s*country\b/gi, 'เดอะคันทรี')
      .replace(/โมเดิร?์?น|\bmodern\b/gi, 'โมเดิร์น')
      .replace(/โฮม|\bhome\b/gi, 'โฮม')
      .replace(/เบญจทรัพย์/gi, 'เบญจทรัพย์')
      .replace(/แพรมาพร/gi, 'แพรมาพร')
      .replace(/ทรัพย์รุ่งเรือง/gi, 'ทรัพย์รุ่งเรือง')
      .replace(/แบงค์?\s*คอก\s*ฮอไรซอน|\bbangkok\s*horizon\b/gi, 'แบงค์คอก ฮอไรซอน')
      .replace(/พฤกษ์?ลดา|\bprueklada\b/gi, 'พฤกษ์ลดา')
      .replace(/กัสโต้|\bgusto\b/gi, 'กัสโต้')
      .replace(/ควอลิตี้\s*เฮ้าส์|\b(?:quality\s*house|q\.?\s*house)\b/gi, 'ควอลิตี้ เฮ้าส์')
      .replace(/แลนด์\s*แอนด์?\s*เฮ้าส์?|\bland\s*(?:&|and)\s*house\b/gi, 'แลนด์ แอนด์ เฮ้าส์')
      .replace(/อีสท์เกต|\beastgate\b/gi, 'อีสท์เกต');

    txt = txt.replace(/[\s\-_/.,:;()\[\]{}]+/g, '');
    txt = txt.replace(/[่้๊๋์็]/g, '');
    txt = txt.replace(/[ศษ]/g, 'ส').replace(/ภ/g, 'พ').replace(/ธ/g, 'ท');
    txt = txt.replace(/ณ/g, 'น').replace(/ญ/g, 'ย').replace(/ฌ/g, 'ช').replace(/ฬ/g, 'ล');
    txt = txt.replace(/[ีืึ]/g, 'ิ');

    if (['บาน', 'คอนโด', 'ทิดิน', 'ทาวนโฮม', 'อาคารพานิชย', ''].includes(txt)) return '';
    return txt;
  }

  /**
   * Native GZIP base64 decompression using fetch('data:...') for C++ base64 decoding,
   * with backpressure-safe Blob.stream().pipeThrough fallback.
   */
  async function decompressGzip(b64str) {
    if (!b64str) return '';
    if (typeof DecompressionStream !== 'function') {
      throw new Error('DecompressionStream is not supported in this browser');
    }
    try {
      const resp = await fetch('data:application/octet-stream;base64,' + b64str);
      if (resp && resp.body) {
        const ds = new DecompressionStream('gzip');
        return await new Response(resp.body.pipeThrough(ds)).text();
      }
    } catch (_e) {
      // Fallback below
    }
    const raw = atob(b64str);
    const bytes = new Uint8Array(raw.length);
    for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
    const ds = new DecompressionStream('gzip');
    return await new Response(new Blob([bytes]).stream().pipeThrough(ds)).text();
  }

  function formatThbPriceStr(priceVal) {
    if (!(priceVal > 0)) return 'ไม่ระบุ';
    const s = String(Math.round(priceVal));
    let out = '';
    for (let i = s.length; i > 0; i -= 3) {
      out = s.slice(Math.max(0, i - 3), i) + (out ? ',' + out : '');
    }
    return '฿' + out + ' บาท';
  }

  function isIOSOrIPadOS() {
    try {
      const nav = global.navigator;
      if (!nav) return false;
      const ua = String(nav.userAgent || '');
      if (/iPad|iPhone|iPod/i.test(ua)) return true;
      // iPadOS 13+ reports Macintosh in UA with multi-touch support
      if (/Macintosh/i.test(ua) && Number(nav.maxTouchPoints || 0) > 1) return true;
    } catch (_e) {}
    return false;
  }

  function hydrateMapRows(data, lut) {
    if (!data || !data.length) return data;
    const _lut = lut || {};
    const coRgbLut = _lut.co_rgb;
    const coLut = _lut.co;
    const tyLut = _lut.ty;
    const pvLut = _lut.pv;
    const stLut = _lut.st;
    const rgLut = _lut.rg;
    const dtLut = _lut.dt;
    const subdtLut = _lut.subdt;
    const prjLut = _lut.prj;
    const plaintiffLut = _lut.plaintiff;
    const _parseOptNum = (v, fallback) => {
      if (v === undefined || v === null || v === '') return fallback;
      const n = +v;
      return Number.isFinite(n) ? n : fallback;
    };

    // Build a single fixed-shape compact object per row, dropping the 11 dead raw CSV index keys
    // (_ci/_ti/_pi/_sti/_rgi/_dti/_subdti/_prji/_p/_up/_pti) to cut JS heap RAM by ~100-140 MB on iPad Safari.
    for (let i = 0; i < data.length; i++) {
      const d = data[i];
      const ci = +d._ci;
      let rVal, gVal, bVal;
      if (d.r !== undefined && d.g !== undefined && d.b !== undefined && d.r !== '') {
        rVal = +d.r;
        gVal = +d.g;
        bVal = +d.b;
      } else {
        const rgb = (coRgbLut && coRgbLut[ci]) || DEFAULT_CO_RGB;
        rVal = rgb[0];
        gVal = rgb[1];
        bVal = rgb[2];
      }
      const priceVal = +d._p || 0;
      data[i] = {
        _uid: i,
        lon: +d.lon,
        lat: +d.lat,
        r: rVal,
        g: gVal,
        b: bVal,
        _title: d._title || '',
        _id: d._id || '',
        _link: d._link || '',
        _centroid: d._centroid || 0,
        _deed: d._deed || '',
        _company: (coLut && coLut[ci]) || '-',
        _type: (tyLut && tyLut[+d._ti]) || '-',
        _prov: (pvLut && pvLut[+d._pi]) || '-',
        _sale: (stLut && stLut[+d._sti]) || '-',
        _region: (rgLut && rgLut[+d._rgi]) || '-',
        _district: (dtLut && dtLut[+d._dti]) || '-',
        _subdistrict: (subdtLut && d._subdti !== undefined && subdtLut[+d._subdti]) || '-',
        _project: (prjLut && d._prji !== undefined && prjLut[+d._prji]) || '-',
        _price: priceVal,
        _price_str: d._price_str || formatThbPriceStr(priceVal),
        _unit_price: +d._up || 0,
        _sqw: +d._sqw || 0,
        _sqm: +d._sqm || 0,
        _puw: +d._puw || 0,
        _pum: +d._pum || 0,
        _fl: _parseOptNum(d._fl, -1),
        _bed: _parseOptNum(d._bed, -1),
        _bath: _parseOptNum(d._bath, -1),
        _pkg: _parseOptNum(d._pkg, -1),
        _age: _parseOptNum(d._age, -1),
        _sold_p: _parseOptNum(d._sold_p, 0),
        _sold_date: d._sold_date || '',
        _plaintiff: (plaintiffLut && d._pti !== undefined && plaintiffLut[+d._pti]) || '',
        _normKey: '',
        _detailLoaded: true
      };
    }
    return data;
  }

  function buildSpatialGrid(data) {
    const grid = new Map();
    if (!data || !data.length) return grid;
    for (let i = 0; i < data.length; i++) {
      const d = data[i];
      if (isNaN(d.lon) || isNaN(d.lat)) continue;
      const gx = Math.floor(d.lon / GRID_CELL_SIZE);
      const gy = Math.floor(d.lat / GRID_CELL_SIZE);
      const key = gx + '_' + gy;
      let cell = grid.get(key);
      if (!cell) {
        cell = [];
        grid.set(key, cell);
      }
      cell.push(d);
    }
    return grid;
  }

  function _indexProjectItemCo(nk, p, d, globalNormToItemsMap, globalProjToItemsMap, globalNormToCompaniesMap, globalProjToCompaniesMap, projCompanyCountsMap) {
    let nArr = globalNormToItemsMap.get(nk);
    if (!nArr) {
      nArr = [];
      globalNormToItemsMap.set(nk, nArr);
    }
    nArr.push(d);

    let pArr = globalProjToItemsMap.get(p);
    if (!pArr) {
      pArr = [];
      globalProjToItemsMap.set(p, pArr);
    }
    pArr.push(d);

    const co = (d._company || '').trim();
    if (co && co !== '-') {
      let coSet = globalNormToCompaniesMap.get(nk);
      if (!coSet) {
        coSet = new Set();
        globalNormToCompaniesMap.set(nk, coSet);
      }
      coSet.add(co);

      let pCoSet = globalProjToCompaniesMap.get(p);
      if (!pCoSet) {
        pCoSet = new Set();
        globalProjToCompaniesMap.set(p, pCoSet);
      }
      pCoSet.add(co);

      let counts = projCompanyCountsMap.get(nk);
      if (!counts) {
        counts = {};
        projCompanyCountsMap.set(nk, counts);
      }
      counts[co] = (counts[co] || 0) + 1;
    }
  }

  function buildProjectIndex(data, lut) {
    const samProjectStatsMap = new Map();
    const globalProjToNormMap = new Map();
    const globalNormToItemsMap = new Map();
    const globalProjToItemsMap = new Map();
    const globalNormToCompaniesMap = new Map();
    const globalProjToCompaniesMap = new Map();
    const projCompanyCountsMap = new Map();
    const normKeyToCanonicalMap = new Map();
    let allSamProjectsList = [];
    let allOtherProjectsList = [];
    let allProjectsList = [];

    const lutObj = lut && typeof lut === 'object' && !Array.isArray(lut) ? lut : null;
    const rawSamPrj = (lutObj && lutObj.sam_prj) || (Array.isArray(lut) ? lut : null);
    const rawOtherPrj = (lutObj && lutObj.other_prj) || null;
    const rawAllPrj = (lutObj && lutObj.all_prj) || null;
    const prjStatsDict = (lutObj && lutObj.prj_stats) || {};
    const samStatsArr = (lutObj && Array.isArray(lutObj.sam_stats)) ? lutObj.sam_stats : null;
    const otherStatsArr = (lutObj && Array.isArray(lutObj.other_stats)) ? lutObj.other_stats : null;
    const samNormArr = (lutObj && Array.isArray(lutObj.sam_norm)) ? lutObj.sam_norm : null;
    const otherNormArr = (lutObj && Array.isArray(lutObj.other_norm)) ? lutObj.other_norm : null;
    if (lutObj && Array.isArray(lutObj.prj) && Array.isArray(lutObj.prj_norm) && lutObj.prj.length === lutObj.prj_norm.length) {
      for (let i = 0; i < lutObj.prj.length; i++) {
        const rp = (lutObj.prj[i] || '').trim();
        const rn = (lutObj.prj_norm[i] || '').trim();
        if (rp && rn) globalProjToNormMap.set(rp, rn);
      }
    }
    const _isValidPrjEntry = (p) => !!(p && p !== '-' && p !== 'ไม่มีข้อมูล' && p !== 'ไม่ระบุ' && p.length > 1 && !isInvalidProjectName(p));

    // Fast path: pre-computed structured project inventory from backend lookup
    if (rawSamPrj && Array.isArray(rawSamPrj) && rawSamPrj.length > 0) {
      allSamProjectsList = [];
      for (let i = 0; i < rawSamPrj.length; i++) {
        const p = rawSamPrj[i];
        if (!_isValidPrjEntry(p)) continue;
        allSamProjectsList.push(p);
        const pair = (samStatsArr && samStatsArr[i]) || prjStatsDict[p] || [1, 0];
        const sc = Math.max(1, pair[0] || 1);
        const oc = pair[1] || 0;
        const nk = (samNormArr && samNormArr[i]) || globalProjToNormMap.get(p) || normalizeProjectKeyword(p);
        const tag = getBrandSearchTag(p);
        samProjectStatsMap.set(p, { sam: sc, other: oc, normKey: nk, tag: tag });
        if (nk) {
          normKeyToCanonicalMap.set(nk, p);
          globalProjToNormMap.set(p, nk);
        }
      }

      allOtherProjectsList = [];
      if (rawOtherPrj && Array.isArray(rawOtherPrj)) {
        for (let i = 0; i < rawOtherPrj.length; i++) {
          const p = rawOtherPrj[i];
          if (!_isValidPrjEntry(p)) continue;
          allOtherProjectsList.push(p);
          const pair = otherStatsArr ? [0, otherStatsArr[i] || 1] : (prjStatsDict[p] || [0, 1]);
          const oc = Math.max(1, pair[1] || 1);
          const nk = (otherNormArr && otherNormArr[i]) || globalProjToNormMap.get(p) || normalizeProjectKeyword(p);
          const tag = getBrandSearchTag(p);
          if (!samProjectStatsMap.has(p)) {
            samProjectStatsMap.set(p, { sam: 0, other: oc, normKey: nk, tag: tag });
          }
          if (nk) {
            if (!normKeyToCanonicalMap.has(nk)) normKeyToCanonicalMap.set(nk, p);
            if (!globalProjToNormMap.has(p)) globalProjToNormMap.set(p, nk);
          }
        }
      }

      allProjectsList =
        rawAllPrj && Array.isArray(rawAllPrj) && rawAllPrj.length > 0
          ? rawAllPrj.filter(_isValidPrjEntry)
          : allSamProjectsList.concat(allOtherProjectsList);

      if (data && data.length > 0) {
        for (let i = 0; i < data.length; i++) {
          const d = data[i];
          const p = (d._project || '').trim();
          if (!p || p === '-' || p === 'ไม่มีข้อมูล' || p.length <= 1 || isInvalidProjectName(p)) {
            d._normKey = '';
            continue;
          }
          let nk = globalProjToNormMap.get(p);
          if (nk === undefined) {
            nk = normalizeProjectKeyword(p);
            globalProjToNormMap.set(p, nk);
          }
          if (!nk || !normKeyToCanonicalMap.has(nk)) {
            d._normKey = '';
            continue;
          }
          d._normKey = nk;
          _indexProjectItemCo(
            nk,
            p,
            d,
            globalNormToItemsMap,
            globalProjToItemsMap,
            globalNormToCompaniesMap,
            globalProjToCompaniesMap,
            projCompanyCountsMap
          );
        }
      }

      return {
        allSamProjectsList,
        allOtherProjectsList,
        allProjectsList,
        samProjectStatsMap,
        globalProjToNormMap,
        globalNormToItemsMap,
        globalProjToItemsMap,
        globalNormToCompaniesMap,
        globalProjToCompaniesMap,
        projCompanyCountsMap,
        normKeyToCanonicalMap
      };
    }

    // Fallback when structured project metadata isn't present
    if (data && data.length > 0) {
      const samCountsByNorm = new Map();
      const otherCountsByNorm = new Map();
      const normKeyGroups = new Map();

      for (let i = 0; i < data.length; i++) {
        const d = data[i];
        const p = (d._project || '').trim();
        const isSam = (d._company || '').toString().trim().toUpperCase() === 'SAM';
        if (isInvalidProjectName(p)) {
          d._normKey = '';
          continue;
        }
        let nk = globalProjToNormMap.get(p);
        if (nk === undefined) {
          nk = normalizeProjectKeyword(p);
          globalProjToNormMap.set(p, nk);
        }
        d._normKey = nk;
        if (!nk || nk.length <= 1) continue;

        if (isSam) {
          samCountsByNorm.set(nk, (samCountsByNorm.get(nk) || 0) + 1);
        } else {
          otherCountsByNorm.set(nk, (otherCountsByNorm.get(nk) || 0) + 1);
        }

        _indexProjectItemCo(
          nk,
          p,
          d,
          globalNormToItemsMap,
          globalProjToItemsMap,
          globalNormToCompaniesMap,
          globalProjToCompaniesMap,
          projCompanyCountsMap
        );

        let grp = normKeyGroups.get(nk);
        if (!grp) {
          grp = { samRaws: new Map(), otherRaws: new Map() };
          normKeyGroups.set(nk, grp);
        }
        const targetMap = isSam ? grp.samRaws : grp.otherRaws;
        targetMap.set(p, (targetMap.get(p) || 0) + 1);
      }

      const samProjectsList = [];
      const otherProjectsList = [];
      const seenCanonicalNames = new Set();

      normKeyGroups.forEach((grp, nk) => {
        const nkItems = globalNormToItemsMap.get(nk);
        if (nkItems && isSpatiallyScatteredGroup(nkItems, 5.0, 10.0)) {
          for (let j = 0; j < nkItems.length; j++) nkItems[j]._normKey = '';
          globalNormToItemsMap.delete(nk);
          globalNormToCompaniesMap.delete(nk);
          projCompanyCountsMap.delete(nk);
          return;
        }
        let bestRaw = '';
        let bestCount = -1;
        if (grp.samRaws.size > 0) {
          grp.samRaws.forEach((cnt, raw) => {
            if (cnt > bestCount) {
              bestCount = cnt;
              bestRaw = raw;
            }
          });
        } else {
          grp.otherRaws.forEach((cnt, raw) => {
            if (cnt > bestCount) {
              bestCount = cnt;
              bestRaw = raw;
            }
          });
        }

        const canonicalName = cleanDisplayProjectName(bestRaw);
        if (!canonicalName || seenCanonicalNames.has(canonicalName)) return;
        seenCanonicalNames.add(canonicalName);

        const sc = samCountsByNorm.get(nk) || 0;
        const oc = otherCountsByNorm.get(nk) || 0;
        const tag = getBrandSearchTag(canonicalName);

        samProjectStatsMap.set(canonicalName, { sam: sc, other: oc, normKey: nk, tag: tag });
        normKeyToCanonicalMap.set(nk, canonicalName);

        if (sc > 0) {
          samProjectsList.push(canonicalName);
        } else {
          otherProjectsList.push(canonicalName);
        }
      });

      samProjectsList.sort((a, b) => {
        const statsA = samProjectStatsMap.get(a) || { sam: 0, other: 0 };
        const statsB = samProjectStatsMap.get(b) || { sam: 0, other: 0 };
        const hasCompA = statsA.other > 0 ? 1 : 0;
        const hasCompB = statsB.other > 0 ? 1 : 0;
        if (hasCompA !== hasCompB) return hasCompB - hasCompA;
        if (statsA.other !== statsB.other) return statsB.other - statsA.other;
        if (statsA.sam !== statsB.sam) return statsB.sam - statsA.sam;
        return a.localeCompare(b, 'th');
      });

      otherProjectsList.sort((a, b) => {
        const statsA = samProjectStatsMap.get(a) || { sam: 0, other: 0 };
        const statsB = samProjectStatsMap.get(b) || { sam: 0, other: 0 };
        if (statsA.other !== statsB.other) return statsB.other - statsA.other;
        return a.localeCompare(b, 'th');
      });

      allSamProjectsList = samProjectsList.slice();
      allOtherProjectsList = otherProjectsList.slice();
      allProjectsList = samProjectsList.concat(otherProjectsList);
    }

    return {
      allSamProjectsList,
      allOtherProjectsList,
      allProjectsList,
      samProjectStatsMap,
      globalProjToNormMap,
      globalNormToItemsMap,
      globalProjToItemsMap,
      globalNormToCompaniesMap,
      globalProjToCompaniesMap,
      projCompanyCountsMap,
      normKeyToCanonicalMap
    };
  }

  function computeTypeCounts(data) {
    const typeCounts = {};
    if (data && data.length > 0) {
      for (let i = 0; i < data.length; i++) {
        const t = (data[i]._type || '').trim();
        if (t && t !== '-') {
          typeCounts[t] = (typeCounts[t] || 0) + 1;
        }
      }
    }
    return typeCounts;
  }

  const PROP_COMPOSITE_SEP = '||';

  function makePropCompositeKey(itemOrCo, maybeId) {
    let co = '';
    let id = '';
    if (itemOrCo && typeof itemOrCo === 'object') {
      co = String(itemOrCo._company || itemOrCo.company || '').trim();
      id = String(itemOrCo._id || itemOrCo.id || '').trim();
    } else {
      co = String(itemOrCo || '').trim();
      id = String(maybeId || '').trim();
    }
    if (!id || id === '-') return '';
    if (co && co !== '-') return co + PROP_COMPOSITE_SEP + id;
    return id;
  }

  function parsePropCompositeKey(rawKey) {
    const s = String(rawKey || '').trim();
    if (!s) return { company: '', id: '' };
    const sepIdx = s.indexOf(PROP_COMPOSITE_SEP);
    if (sepIdx >= 0) {
      return {
        company: s.slice(0, sepIdx).trim(),
        id: s.slice(sepIdx + PROP_COMPOSITE_SEP.length).trim()
      };
    }
    return { company: '', id: s };
  }

  function buildIdLookupIndex(data) {
    const idExactLookupMap = new Map();
    const idStrippedLookupMap = new Map();
    const idCompanyLookupMap = new Map();
    if (!data || !data.length) {
      return { idExactLookupMap, idStrippedLookupMap, idCompanyLookupMap };
    }
    for (let i = 0; i < data.length; i++) {
      const d = data[i];
      const raw = (d._id || '').trim().toLowerCase();
      if (!raw) continue;
      if (!idExactLookupMap.has(raw)) idExactLookupMap.set(raw, d);
      const co = (d._company || '').trim().toLowerCase();
      if (co && co !== '-') {
        const cKey = co + PROP_COMPOSITE_SEP + raw;
        if (!idCompanyLookupMap.has(cKey)) idCompanyLookupMap.set(cKey, d);
      }
      const stripped = raw.replace(/[^a-z0-9\u0E00-\u0E7F]/g, '');
      if (stripped && !idStrippedLookupMap.has(stripped)) idStrippedLookupMap.set(stripped, d);
    }
    return { idExactLookupMap, idStrippedLookupMap, idCompanyLookupMap };
  }

  function resolvePropertyByKey(rawKey, indexes, fallbackCompany) {
    if (!rawKey || !indexes) return null;
    const parsed = parsePropCompositeKey(rawKey);
    const idLow = (parsed.id || '').toLowerCase();
    const coLow = (parsed.company || String(fallbackCompany || '').trim()).toLowerCase();
    if (!idLow) return null;
    if (coLow && indexes.idCompanyLookupMap) {
      const hitCo = indexes.idCompanyLookupMap.get(coLow + PROP_COMPOSITE_SEP + idLow);
      if (hitCo) return hitCo;
    }
    if (indexes.idExactLookupMap) {
      const hitExact = indexes.idExactLookupMap.get(idLow);
      if (hitExact) return hitExact;
    }
    if (indexes.idStrippedLookupMap) {
      const stripped = idLow.replace(/[^a-z0-9\u0E00-\u0E7F]/g, '');
      if (stripped) return indexes.idStrippedLookupMap.get(stripped) || null;
    }
    return null;
  }

  function getEffectiveSelfOrigin() {
    try {
      const locOrigin = global.location && global.location.origin;
      if (locOrigin && locOrigin !== 'null') return locOrigin;
      if (typeof global.origin === 'string' && global.origin && global.origin !== 'null') {
        return global.origin;
      }
      const href = (global.location && global.location.href) || '';
      if (href === 'about:srcdoc' || href === 'about:blank') {
        if (global.parent && global.parent !== global && global.parent.document && global.parent.location) {
          const pOrigin = global.parent.location.origin;
          if (pOrigin && pOrigin !== 'null') return pOrigin;
        }
      }
    } catch (_e) {
      // Ignore cross-origin frame access error
    }
    return '';
  }

  function getParentHost() {
    try {
      if (global.parent && global.parent !== global) {
        const parentOrigin = global.parent.location && global.parent.location.origin;
        const selfOrigin = getEffectiveSelfOrigin();
        // Verify same-origin explicitly (supports both normal iframes and about:srcdoc frames with allow-same-origin)
        if (
          parentOrigin &&
          parentOrigin !== 'null' &&
          selfOrigin === parentOrigin &&
          global.parent.document
        ) {
          return global.parent;
        }
      }
    } catch (_e) {
      // Ignore cross-origin frame access error
    }
    return null;
  }

  function extractPayloadToken(url) {
    if (!url) return '';
    const m = String(url).match(/map_payload_([a-f0-9]{16,64})\.gz/i);
    return m ? m[1].toLowerCase() : String(url).split('?')[0].trim();
  }

  function clearParentMapCache() {
    const host = getParentHost();
    if (!host) return;
    try {
      host.__NOVA_MAP_CACHE__ = null;
      host.__NOVA_MAP_CACHE_PROMISE__ = null;
      host.__NOVA_MAP_CACHE_PROMISE_KEY__ = '';
    } catch (_e) {}
  }

  function getValidParentCache(expectedMtime, expectedPayloadUrl) {
    const host = getParentHost();
    if (!host || !host.__NOVA_MAP_CACHE__) return null;
    const c = host.__NOVA_MAP_CACHE__;
    if (!c.data || !c.data.length || !c.spatialGrid || !c.projIndex) return null;
    if (expectedMtime && String(c.mtime || '') !== String(expectedMtime)) return null;
    if (expectedPayloadUrl) {
      const wantTok = extractPayloadToken(expectedPayloadUrl);
      const haveTok = c.payloadToken || extractPayloadToken(c.payloadUrl || (c.detailConfig && c.detailConfig.dir ? ('map_payload_' + String(c.detailConfig.dir).replace(/^map_details_/, '') + '.gz') : ''));
      if (wantTok && haveTok && wantTok !== haveTok) return null;
    }
    return c;
  }

  function getParentBoundaryCache() {
    const host = getParentHost();
    return host && host.__NOVA_BOUNDARY_CACHE__ ? host.__NOVA_BOUNDARY_CACHE__ : null;
  }

  function storeParentBoundaryCache(kind, dictObj) {
    if (!dictObj || typeof dictObj !== 'object' || Object.keys(dictObj).length === 0) return;
    const host = getParentHost();
    if (!host) return;
    if (!host.__NOVA_BOUNDARY_CACHE__) host.__NOVA_BOUNDARY_CACHE__ = {};
    host.__NOVA_BOUNDARY_CACHE__[kind] = dictObj;
  }

  async function yieldIfVisible() {
    if (typeof document !== 'undefined' && document.hidden) return;
    await new Promise(resolve => setTimeout(resolve, 0));
  }

  async function _buildCacheObjFromDecoded(mtimeStr, lutObj, csvText, onProgress) {
    if (!csvText) {
      throw new Error('Missing map CSV payload');
    }
    const _lut =
      lutObj && typeof lutObj === 'object'
        ? lutObj
        : { co: [], ty: [], pv: [], st: [], rg: [], dt: [], subdt: [], prj: [], plaintiff: [], co_rgb: [] };

    if (typeof onProgress === 'function') {
      onProgress(95, 'กำลังวิเคราะห์ตารางพิกัด (Parsing CSV)...');
      await yieldIfVisible();
    }

    if (!global.d3 || typeof global.d3.csvParse !== 'function') {
      throw new Error('d3.csvParse unavailable');
    }
    const data = global.d3.csvParse(csvText);
    // Allow GC to reclaim the ~140 MB raw CSV string before building indexes
    csvText = '';

    hydrateMapRows(data, _lut);

    if (typeof onProgress === 'function') {
      onProgress(98, 'กำลังสร้างดัชนีพิกัดและโครงการ (' + data.length.toLocaleString() + ' จุด)...');
      await yieldIfVisible();
    }

    const spatialGrid = buildSpatialGrid(data);
    const projIndex = buildProjectIndex(data, _lut);
    const typeCounts = computeTypeCounts(data);
    // On iPadOS/iOS, defer the two 460k-entry ID Maps until first ID search to stay safely under WebKit Jetsam RAM limits
    const idLookup = isIOSOrIPadOS() ? { idExactLookupMap: null, idStrippedLookupMap: null } : buildIdLookupIndex(data);

    const cacheObj = {
      mtime: mtimeStr || '',
      lut: _lut,
      data: data,
      spatialGrid: spatialGrid,
      projIndex: projIndex,
      typeCounts: typeCounts,
      idExactLookupMap: idLookup.idExactLookupMap,
      idStrippedLookupMap: idLookup.idStrippedLookupMap,
      builtAt: Date.now()
    };

    const host = getParentHost();
    if (host) {
      host.__NOVA_MAP_CACHE__ = cacheObj;
    }
    return cacheObj;
  }

  async function buildAndStoreParentCache(mtimeToken, rawPayload, onProgress) {
    const mtimeStr = mtimeToken ? String(mtimeToken) : '';
    const existing = getValidParentCache(mtimeStr);
    if (existing) {
      if (typeof onProgress === 'function') onProgress(100, '✓ พร้อมใช้งานแล้ว');
      return existing;
    }

    if (!rawPayload || !rawPayload.csv) {
      throw new Error('Missing map CSV payload');
    }

    // Support both pre-decoded JSON payloads ({ lut: object, csv: rawCsv }) and legacy GZIP+Base64 strings
    let _lut = null;
    let initialCsvText = '';
    if (typeof rawPayload.lut === 'object' && rawPayload.lut !== null) {
      _lut = rawPayload.lut;
      initialCsvText = String(rawPayload.csv || '');
    } else {
      if (typeof onProgress === 'function') {
        onProgress(92, 'กำลังถอดรหัส GZIP ข้อมูลแผนที่บนเบราว์เซอร์...');
        await yieldIfVisible();
      }
      const lutB64 = rawPayload.lut ? String(rawPayload.lut) : '';
      const csvB64 = String(rawPayload.csv || '');
      const [lutJsonStr, csvStr] = await Promise.all([
        lutB64 ? decompressGzip(lutB64).catch(() => null) : Promise.resolve(null),
        decompressGzip(csvB64)
      ]);
      initialCsvText = csvStr;
      if (lutJsonStr) {
        try {
          _lut = JSON.parse(lutJsonStr);
        } catch (e) {
          console.warn('Lookup JSON parse failed', e);
        }
      }
    }

    // Release raw payload references for immediate GC
    rawPayload.lut = '';
    rawPayload.csv = '';
    if (global.__NOVA_RAW_MAP_PAYLOAD__ === rawPayload) {
      global.__NOVA_RAW_MAP_PAYLOAD__ = null;
    }

    return await _buildCacheObjFromDecoded(
      mtimeStr || String(rawPayload.mtime || ''),
      _lut,
      initialCsvText,
      onProgress
    );
  }

  function resolveStaticUrlCandidates(rawUrl) {
    if (!rawUrl) return [];
    const raw = String(rawUrl).trim();
    const staticIdx = raw.indexOf('app/static/');
    const clean = (staticIdx >= 0)
      ? raw.slice(staticIdx)
      : raw.replace(/^(\.\/|\/)+/, '').replace(/^~\/\+\//, '');
    const out = [];
    if (raw.startsWith('/') && staticIdx > 1) {
      out.push(raw);
    }
    const addOriginBase = (origin, pathname) => {
      if (!origin || origin === 'null') return;
      let basePath = pathname || '/';
      basePath = basePath.replace(/\/component\/.*$/, '/').replace(/\/index\.html$/, '/');
      if (!basePath.endsWith('/')) basePath += '/';
      out.push(origin + basePath + clean);
      out.push(origin + '/~/+/' + clean);
      out.push(origin + '/' + clean);
    };
    try {
      const pLoc = (global.parent && global.parent.location && global.parent.location.origin && global.parent.location.origin !== 'null')
        ? global.parent.location
        : global.location;
      if (pLoc && pLoc.origin && pLoc.origin !== 'null') {
        addOriginBase(pLoc.origin, pLoc.pathname);
      }
      if (pLoc && pLoc.pathname && pLoc.pathname !== 'srcdoc' && pLoc.pathname !== 'blank') {
        let basePath = pLoc.pathname.replace(/\/component\/.*$/, '/').replace(/\/index\.html$/, '/');
        if (!basePath.endsWith('/')) basePath += '/';
        out.push(basePath + clean);
      }
    } catch (_e) {}
    // Fallback to document.referrer when embedded under cross-origin wrappers (e.g. Cloud iframe)
    try {
      if (typeof document !== 'undefined' && document.referrer) {
        const refUrl = new URL(document.referrer);
        addOriginBase(refUrl.origin, refUrl.pathname);
      }
    } catch (_e) {}
    out.push('/~/+/' + clean);
    out.push('/' + clean);
    out.push(clean);
    return Array.from(new Set(out));
  }

  function _parseCsvLineFields(line) {
    if (line.indexOf('"') === -1) {
      return line.split(',');
    }
    const out = [];
    let cur = '';
    let inQuotes = false;
    const len = line.length;
    for (let i = 0; i < len; i++) {
      const ch = line.charCodeAt(i);
      if (inQuotes) {
        if (ch === 34) {
          if (i + 1 < len && line.charCodeAt(i + 1) === 34) {
            cur += '"';
            i++;
          } else {
            inQuotes = false;
          }
        } else {
          cur += line[i];
        }
      } else {
        if (ch === 44) {
          out.push(cur);
          cur = '';
        } else if (ch === 34 && cur.length === 0) {
          inQuotes = true;
        } else {
          cur += line[i];
        }
      }
    }
    out.push(cur);
    return out;
  }

  function _peekAndWrapGzipStream(readableStream) {
    const reader = readableStream.getReader();
    return (async () => {
      const buffered = [];
      let totalLen = 0;
      let streamDone = false;
      while (totalLen < 2) {
        const { value, done } = await reader.read();
        if (done) {
          streamDone = true;
          break;
        }
        if (value && value.byteLength > 0) {
          buffered.push(value);
          totalLen += value.byteLength;
        }
      }
      let b0 = -1;
      let b1 = -1;
      if (totalLen >= 2) {
        let pos = 0;
        for (let i = 0; i < buffered.length && pos < 2; i++) {
          const chunk = buffered[i];
          for (let j = 0; j < chunk.byteLength && pos < 2; j++) {
            if (pos === 0) b0 = chunk[j];
            else b1 = chunk[j];
            pos++;
          }
        }
      }
      const isGzip = (b0 === 0x1f && b1 === 0x8b);
      const replayStream = new ReadableStream({
        start(controller) {
          for (let i = 0; i < buffered.length; i++) {
            controller.enqueue(buffered[i]);
          }
          buffered.length = 0;
          if (streamDone) {
            try { reader.releaseLock(); } catch (_e) {}
            controller.close();
          }
        },
        async pull(controller) {
          try {
            const { value, done } = await reader.read();
            if (done) {
              try { reader.releaseLock(); } catch (_e) {}
              controller.close();
            } else if (value && value.byteLength > 0) {
              controller.enqueue(value);
            }
          } catch (err) {
            try { reader.releaseLock(); } catch (_e) {}
            controller.error(err);
          }
        },
        cancel(reason) {
          return reader.cancel(reason).catch(() => {});
        }
      });
      return { stream: replayStream, isGzip: isGzip };
    })();
  }

  async function _unwrapAutoGzipStream(readableStream) {
    // Magic-byte auto-detection on actual stream bytes (never trusts Content-Type / Content-Encoding headers,
    // which Streamlit AppStaticFileHandler or reverse proxies frequently set to text/plain or double-gzip).
    let cur = readableStream;
    for (let pass = 0; pass < 2; pass++) {
      const peeked = await _peekAndWrapGzipStream(cur);
      if (!peeked.isGzip) {
        return peeked.stream;
      }
      if (typeof peeked.stream.pipeThrough !== 'function' || typeof DecompressionStream !== 'function') {
        throw new Error('เบราว์เซอร์รุ่นนี้ไม่รองรับ DecompressionStream กรุณาอัปเดต Chrome/Edge/Safari');
      }
      cur = peeked.stream.pipeThrough(new DecompressionStream('gzip'));
    }
    return cur;
  }

  async function _readStreamToUint8Array(readableStream) {
    const reader = readableStream.getReader();
    const chunks = [];
    let total = 0;
    try {
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        if (value && value.byteLength > 0) {
          chunks.push(value);
          total += value.byteLength;
        }
      }
    } finally {
      try { reader.releaseLock(); } catch (_e) {}
    }
    const out = new Uint8Array(total);
    let offset = 0;
    for (let i = 0; i < chunks.length; i++) {
      out.set(chunks[i], offset);
      offset += chunks[i].byteLength;
    }
    return out;
  }

  async function _readStreamToUtf8Text(readableStream, onProgress, progressPrefix) {
    const reader = readableStream.getReader();
    const decoder = new TextDecoder('utf-8');
    const parts = [];
    let decodedBytes = 0;
    let lastEmitAt = 0;
    try {
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        if (value && value.byteLength > 0) {
          decodedBytes += value.byteLength;
          parts.push(decoder.decode(value, { stream: true }));
          if (typeof onProgress === 'function') {
            const now = Date.now();
            if (now - lastEmitAt >= 200) {
              lastEmitAt = now;
              const mb = (decodedBytes / 1048576).toFixed(1);
              onProgress(92, (progressPrefix || 'กำลังดาวน์โหลดและถอดรหัสแคชแผนที่') + ' (' + mb + ' MB)...');
            }
          }
        }
      }
      const tail = decoder.decode();
      if (tail) parts.push(tail);
    } finally {
      try { reader.releaseLock(); } catch (_e) {}
    }
    if (typeof onProgress === 'function') {
      const mb = (decodedBytes / 1048576).toFixed(1);
      onProgress(94, (progressPrefix || 'กำลังดาวน์โหลดและถอดรหัสแคชแผนที่') + ' (' + mb + ' MB)...');
    }
    return parts.join('');
  }

  async function _openAutoGzipTextStream(resp, forceBufferedMagicCheck) {
    // WebKit/Safari-safe native streaming path: NEVER wrap a JS ReadableStream into new Response(...).text()
    // (doing so triggers WebKit's "TypeError: Load failed" on iPadOS Safari).
    if (!forceBufferedMagicCheck && resp.body && typeof resp.body.getReader === 'function' && typeof ReadableStream === 'function') {
      return await _unwrapAutoGzipStream(resp.body);
    }
    const buf = await resp.arrayBuffer();
    let bytes = new Uint8Array(buf);
    for (let pass = 0; pass < 2; pass++) {
      if (bytes.length >= 2 && bytes[0] === 0x1f && bytes[1] === 0x8b) {
        if (typeof DecompressionStream !== 'function') {
          throw new Error('เบราว์เซอร์รุ่นนี้ไม่รองรับ DecompressionStream กรุณาอัปเดต Chrome/Edge/Safari');
        }
        const ds = new DecompressionStream('gzip');
        const blobStream = new Blob([bytes]).stream().pipeThrough(ds);
        if (pass === 0) {
          bytes = await _readStreamToUint8Array(blobStream);
          continue;
        }
        return blobStream;
      }
      break;
    }
    return new Blob([bytes]).stream();
  }

  async function _readResponseTextAutoGzip(resp, onProgress, forceBufferedMagicCheck) {
    if (!forceBufferedMagicCheck && resp.body && typeof resp.body.getReader === 'function' && typeof ReadableStream === 'function') {
      const textStream = await _unwrapAutoGzipStream(resp.body);
      return await _readStreamToUtf8Text(textStream, onProgress, 'กำลังดาวน์โหลดและแตกไฟล์แคชแผนที่');
    }

    // Buffered fallback & magic-byte auto-detection (handles unannounced proxy auto-decompression or double-gzip)
    if (typeof onProgress === 'function') {
      onProgress(91, 'กำลังดาวน์โหลดแคชแผนที่...');
    }
    const buf = await resp.arrayBuffer();
    let bytes = new Uint8Array(buf);
    if (bytes.length === 0) return '';
    for (let pass = 0; pass < 2; pass++) {
      const isGzip = bytes.length >= 2 && bytes[0] === 0x1f && bytes[1] === 0x8b;
      if (!isGzip) break;
      if (typeof DecompressionStream !== 'function') {
        throw new Error('เบราว์เซอร์รุ่นนี้ไม่รองรับ DecompressionStream กรุณาอัปเดต Chrome/Edge/Safari');
      }
      const ds = new DecompressionStream('gzip');
      const blobStream = new Blob([bytes]).stream().pipeThrough(ds);
      bytes = await _readStreamToUint8Array(blobStream);
    }
    return new TextDecoder('utf-8').decode(bytes);
  }

  function _resolveDetailBaseUrl(winningPayloadUrl, detailDir) {
    if (!detailDir) return '';
    if (winningPayloadUrl) {
      const slashPos = winningPayloadUrl.lastIndexOf('/');
      if (slashPos >= 0) {
        return winningPayloadUrl.slice(0, slashPos + 1) + detailDir;
      }
    }
    return '/app/static/' + detailDir;
  }

  async function _finalizeCacheObj(mtimeStr, lutObj, data, detailConfig, onProgress, payloadUrl) {
    if (!data || !data.length) {
      throw new Error('Missing map coordinate rows');
    }
    const _lut =
      lutObj && typeof lutObj === 'object'
        ? lutObj
        : { co: [], ty: [], pv: [], st: [], rg: [], dt: [], subdt: [], prj: [], plaintiff: [], co_rgb: [] };

    if (typeof onProgress === 'function') {
      onProgress(98, 'กำลังสร้างดัชนีพิกัดและโครงการ (' + data.length.toLocaleString() + ' จุด)...');
      await yieldIfVisible();
    }

    const spatialGrid = buildSpatialGrid(data);
    const projIndex = buildProjectIndex(data, _lut);
    const typeCounts = computeTypeCounts(data);
    // On iPadOS/iOS, defer the two 460k-entry ID Maps until first ID search to stay safely under WebKit Jetsam RAM limits
    const idLookup = isIOSOrIPadOS() ? { idExactLookupMap: null, idStrippedLookupMap: null } : buildIdLookupIndex(data);

    const resolvedUrl = payloadUrl ? String(payloadUrl) : '';
    const cacheObj = {
      mtime: mtimeStr || '',
      payloadUrl: resolvedUrl,
      payloadToken: extractPayloadToken(resolvedUrl),
      lut: _lut,
      data: data,
      spatialGrid: spatialGrid,
      projIndex: projIndex,
      typeCounts: typeCounts,
      idExactLookupMap: idLookup.idExactLookupMap,
      idStrippedLookupMap: idLookup.idStrippedLookupMap,
      detailConfig: detailConfig || null,
      loadedDetailChunks: new Set(),
      inflightDetailChunks: new Map(),
      builtAt: Date.now()
    };

    const host = getParentHost();
    if (host) {
      host.__NOVA_MAP_CACHE__ = cacheObj;
    }
    return cacheObj;
  }

  async function _streamParseBundleToCacheObj(textStream, expectedMtime, winningPayloadUrl, onProgress) {
    const reader = textStream.getReader();
    const decoder = new TextDecoder('utf-8');
    let leftover = '';
    let lineNo = 0;
    let headerObj = null;
    let legacyJsonParts = null;
    let colIdx = null;
    let data = [];
    let expectedRows = 0;
    let hasDeferredDetails = false;
    let coRgbLut, coLut, tyLut, pvLut, stLut, rgLut, dtLut, subdtLut, prjLut, plaintiffLut;
    let lastEmitAt = 0;

    const _optNum = (v, fallback) => {
      if (v === undefined || v === null || v === '') return fallback;
      const n = +v;
      return Number.isFinite(n) ? n : fallback;
    };

    const processLine = (rawLine) => {
      const line = rawLine.endsWith('\r') ? rawLine.slice(0, -1) : rawLine;
      if (lineNo === 0) {
        lineNo = 1;
        if (!line) return;
        const trimmed = line.charCodeAt(0) === 0xfeff ? line.slice(1) : line;
        headerObj = JSON.parse(trimmed);
        if (headerObj && headerObj.v >= 4 && headerObj.lut && typeof headerObj.csv !== 'string') {
          const _lut = headerObj.lut || {};
          coRgbLut = _lut.co_rgb;
          coLut = _lut.co;
          tyLut = _lut.ty;
          pvLut = _lut.pv;
          stLut = _lut.st;
          rgLut = _lut.rg;
          dtLut = _lut.dt;
          subdtLut = _lut.subdt;
          prjLut = _lut.prj;
          plaintiffLut = _lut.plaintiff;
          expectedRows = Number(headerObj.rows) || 0;
          hasDeferredDetails = !!(headerObj.detail && headerObj.detail.dir);
          data = [];
        } else {
          // Legacy single-line JSON bundle ({ mtime, lut, csv })
          legacyJsonParts = headerObj;
        }
        return;
      }

      if (legacyJsonParts) return;

      if (lineNo === 1) {
        lineNo = 2;
        if (!line) return;
        const hdrCols = _parseCsvLineFields(line);
        colIdx = {};
        for (let i = 0; i < hdrCols.length; i++) {
          colIdx[hdrCols[i].trim()] = i;
        }
        return;
      }

      if (!line) return;
      const cols = _parseCsvLineFields(line);
      const ci = +cols[colIdx._ci];
      const rgb = (coRgbLut && coRgbLut[ci]) || DEFAULT_CO_RGB;
      const pRaw = cols[colIdx._p];
      const priceVal = pRaw ? (+pRaw || 0) : 0;
      const ptiIdx = colIdx._pti;
      const ptiStr = (ptiIdx !== undefined) ? cols[ptiIdx] : '';
      const ptiCode = ptiStr ? +ptiStr : 0;
      const titleIdx = colIdx._title;
      const linkIdx = colIdx._link;
      const deedIdx = colIdx._deed;
      const soldDateIdx = colIdx._sold_date;
      const centIdx = colIdx._centroid;

      data.push({
        _uid: data.length,
        lon: +cols[colIdx.lon],
        lat: +cols[colIdx.lat],
        r: rgb[0],
        g: rgb[1],
        b: rgb[2],
        _title: (titleIdx !== undefined && cols[titleIdx]) || '',
        _id: (colIdx._id !== undefined && cols[colIdx._id]) || '',
        _link: (linkIdx !== undefined && cols[linkIdx]) || '',
        _centroid: (centIdx !== undefined && cols[centIdx]) ? +cols[centIdx] : 0,
        _deed: (deedIdx !== undefined && cols[deedIdx]) || '',
        _company: (coLut && coLut[ci]) || '-',
        _type: (tyLut && tyLut[+cols[colIdx._ti]]) || '-',
        _prov: (pvLut && pvLut[+cols[colIdx._pi]]) || '-',
        _sale: (stLut && stLut[+cols[colIdx._sti]]) || '-',
        _region: (rgLut && rgLut[+cols[colIdx._rgi]]) || '-',
        _district: (dtLut && dtLut[+cols[colIdx._dti]]) || '-',
        _subdistrict: (subdtLut && colIdx._subdti !== undefined && subdtLut[+cols[colIdx._subdti]]) || '-',
        _project: (prjLut && colIdx._prji !== undefined && prjLut[+cols[colIdx._prji]]) || '-',
        _price: priceVal,
        _price_str: formatThbPriceStr(priceVal),
        _unit_price: (colIdx._up !== undefined && cols[colIdx._up]) ? (+cols[colIdx._up] || 0) : 0,
        _sqw: (colIdx._sqw !== undefined && cols[colIdx._sqw]) ? (+cols[colIdx._sqw] || 0) : 0,
        _sqm: (colIdx._sqm !== undefined && cols[colIdx._sqm]) ? (+cols[colIdx._sqm] || 0) : 0,
        _puw: (colIdx._puw !== undefined && cols[colIdx._puw]) ? (+cols[colIdx._puw] || 0) : 0,
        _pum: (colIdx._pum !== undefined && cols[colIdx._pum]) ? (+cols[colIdx._pum] || 0) : 0,
        _fl: (colIdx._fl !== undefined) ? _optNum(cols[colIdx._fl], -1) : -1,
        _bed: (colIdx._bed !== undefined) ? _optNum(cols[colIdx._bed], -1) : -1,
        _bath: (colIdx._bath !== undefined) ? _optNum(cols[colIdx._bath], -1) : -1,
        _pkg: (colIdx._pkg !== undefined) ? _optNum(cols[colIdx._pkg], -1) : -1,
        _age: (colIdx._age !== undefined) ? _optNum(cols[colIdx._age], -1) : -1,
        _sold_p: (colIdx._sold_p !== undefined && cols[colIdx._sold_p]) ? (+cols[colIdx._sold_p] || 0) : 0,
        _sold_date: (soldDateIdx !== undefined && cols[soldDateIdx]) || '',
        _plaintiff: (plaintiffLut && plaintiffLut[ptiCode]) || '',
        _normKey: '',
        _detailLoaded: !hasDeferredDetails
      });
    };

    try {
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        if (!value || value.byteLength === 0) continue;
        const textChunk = decoder.decode(value, { stream: true });
        if (!textChunk) continue;
        let combined = leftover + textChunk;
        let nlIdx = combined.indexOf('\n');
        let startPos = 0;
        while (nlIdx !== -1) {
          processLine(combined.slice(startPos, nlIdx));
          startPos = nlIdx + 1;
          nlIdx = combined.indexOf('\n', startPos);
        }
        leftover = combined.slice(startPos);
        if (typeof onProgress === 'function' && lineNo >= 2) {
          const now = Date.now();
          if (now - lastEmitAt >= 180) {
            lastEmitAt = now;
            if (expectedRows > 0) {
              const pctRows = Math.min(99, Math.round((data.length / expectedRows) * 100));
              const uiPct = 90 + Math.round(pctRows * 0.07);
              onProgress(uiPct, 'กำลังโหลดพิกัดแผนที่ ' + pctRows + '% (' + data.length.toLocaleString() + ' จุด)...');
            } else {
              onProgress(94, 'กำลังโหลดพิกัดแผนที่ (' + data.length.toLocaleString() + ' จุด)...');
            }
          }
        }
      }
      const tail = decoder.decode();
      if (tail) leftover += tail;
      if (leftover && leftover.length > 0) {
        processLine(leftover);
      }
      leftover = '';
    } finally {
      try { reader.releaseLock(); } catch (_e) {}
    }

    if (legacyJsonParts) {
      const lutObj = legacyJsonParts && typeof legacyJsonParts.lut === 'object' ? legacyJsonParts.lut : null;
      const resolvedMtime = expectedMtime || String((legacyJsonParts && legacyJsonParts.mtime) || '');
      let csvText = legacyJsonParts && legacyJsonParts.csv ? String(legacyJsonParts.csv) : '';
      legacyJsonParts.csv = '';
      legacyJsonParts = null;
      const res = await _buildCacheObjFromDecoded(resolvedMtime, lutObj, csvText, onProgress);
      csvText = '';
      return res;
    }

    if (!headerObj || !data.length) {
      throw new Error('ไม่สามารถอ่านข้อมูลแคชแผนที่ได้');
    }

    const detailMeta = headerObj.detail;
    const detailConfig = (detailMeta && detailMeta.dir)
      ? {
          dir: detailMeta.dir,
          baseUrl: _resolveDetailBaseUrl(winningPayloadUrl, detailMeta.dir),
          chunkSize: Number(detailMeta.chunk_size) || 7000,
          chunks: Number(detailMeta.chunks) || 0
        }
      : null;

    const resolvedMtime = expectedMtime || String(headerObj.mtime || '');
    return await _finalizeCacheObj(resolvedMtime, headerObj.lut, data, detailConfig, onProgress, winningPayloadUrl);
  }

  function _expandChunkLink(encLink, lp) {
    if (!encLink) return '';
    const bar = encLink.indexOf('|');
    if (bar < 0) return encLink;
    const prefIdxStr = encLink.slice(0, bar);
    const rest = encLink.slice(bar + 1);
    if (!prefIdxStr) return rest;
    const pref = (lp && lp[+prefIdxStr]) || '';
    return pref + rest;
  }

  async function loadDetailChunk(cacheObj, chunkIdx) {
    const c = cacheObj || getValidParentCache();
    if (!c || !c.detailConfig || !c.detailConfig.baseUrl) return true;
    const idx = Number(chunkIdx);
    if (!Number.isInteger(idx) || idx < 0) return false;
    if (c.detailConfig.chunks > 0 && idx >= c.detailConfig.chunks) return false;

    if (!c.loadedDetailChunks) c.loadedDetailChunks = new Set();
    if (!c.inflightDetailChunks) c.inflightDetailChunks = new Map();
    if (c.loadedDetailChunks.has(idx)) return true;

    const pending = c.inflightDetailChunks.get(idx);
    if (pending) return await pending;

    const chunkFile = 'c' + String(idx).padStart(2, '0') + '.gz';
    const chunkUrl = c.detailConfig.baseUrl + '/' + chunkFile;
    const candidates = resolveStaticUrlCandidates(chunkUrl);

    const p = (async () => {
      let jsonText = '';
      let lastErr = null;
      for (let attempt = 0; attempt < 2; attempt++) {
        try {
          const { resp } = await _fetchStaticPayloadResponse(candidates);
          jsonText = await _readResponseTextAutoGzip(resp, null, attempt === 1);
          if (jsonText && jsonText.charCodeAt(0) === 123) {
            lastErr = null;
            break;
          }
          lastErr = new Error('Invalid detail chunk JSON');
        } catch (err) {
          lastErr = err;
          if (attempt === 0) await new Promise((r) => setTimeout(r, 200));
        }
      }
      if (lastErr || !jsonText) {
        if (lastErr && (lastErr.status === 404 || lastErr.status === 410 || lastErr.isTokenExpired)) {
          try {
            const host = getParentHost();
            if (host) {
              host.__NOVA_TAB2_TOKEN_EXPIRED__ = {
                reason: 'detail_chunk_404',
                status: lastErr.status || 404,
                url: chunkUrl,
                ts: Date.now()
              };
            }
          } catch (_e) {}
        }
        throw lastErr || new Error('Failed to load detail chunk ' + chunkFile);
      }
      const parsed = JSON.parse(jsonText);
      const startUid = Number(parsed && parsed.s) || 0;
      const lp = (parsed && Array.isArray(parsed.lp)) ? parsed.lp : [];
      const rows = (parsed && Array.isArray(parsed.r)) ? parsed.r : [];
      const dataArr = c.data || [];
      for (let i = 0; i < rows.length; i++) {
        const target = dataArr[startUid + i];
        if (!target) continue;
        const rec = rows[i];
        if (Array.isArray(rec)) {
          target._title = rec[0] || '';
          target._link = rec[1] ? _expandChunkLink(rec[1], lp) : '';
          target._deed = rec[2] || '';
          target._sold_date = rec[3] || '';
        }
        target._detailLoaded = true;
      }
      c.loadedDetailChunks.add(idx);
      return true;
    })();

    c.inflightDetailChunks.set(idx, p);
    try {
      return await p;
    } finally {
      if (c.inflightDetailChunks.get(idx) === p) {
        c.inflightDetailChunks.delete(idx);
      }
    }
  }

  async function ensureDetailsForItems(items, cacheObj) {
    const c = cacheObj || getValidParentCache();
    if (!c || !c.detailConfig || !c.detailConfig.baseUrl) return true;
    const list = Array.isArray(items) ? items : (items ? [items] : []);
    if (!list.length) return true;
    const chunkSize = c.detailConfig.chunkSize || 7000;
    const needed = new Set();
    for (let i = 0; i < list.length; i++) {
      const it = list[i];
      if (!it || it._detailLoaded) continue;
      const uid = Number(it._uid);
      if (!Number.isInteger(uid) || uid < 0) continue;
      const ci = Math.floor(uid / chunkSize);
      if (!c.loadedDetailChunks || !c.loadedDetailChunks.has(ci)) {
        needed.add(ci);
      }
    }
    if (needed.size === 0) return true;
    const tasks = [];
    needed.forEach((ci) => {
      tasks.push(loadDetailChunk(c, ci).catch(() => false));
    });
    await Promise.all(tasks);
    return true;
  }

  function prefetchDetailForItem(item, cacheObj) {
    if (!item || item._detailLoaded) return;
    ensureDetailsForItems([item], cacheObj).catch(() => {});
  }

  async function _fetchStaticPayloadResponse(candidates) {
    let lastStatus = 0;
    let lastErr = null;
    for (let i = 0; i < candidates.length; i++) {
      try {
        const r = await fetch(candidates[i], { credentials: 'same-origin' });
        lastStatus = r.status;
        const ct = (r.headers && r.headers.get('content-type') || '').toLowerCase();
        if (r.ok && !ct.includes('text/html')) {
          return { resp: r, url: candidates[i] };
        }
        if (r.body && typeof r.body.cancel === 'function') {
          r.body.cancel().catch(() => {});
        }
      } catch (err) {
        lastErr = err;
      }
    }
    if (lastStatus > 0) {
      const httpErr = new Error('ไม่สามารถโหลดไฟล์แคชข้อมูลแผนที่ได้ (HTTP ' + lastStatus + ')');
      httpErr.status = lastStatus;
      httpErr.isTokenExpired = (lastStatus === 404 || lastStatus === 410);
      throw httpErr;
    }
    throw lastErr || new Error('ไม่สามารถโหลดไฟล์แคชข้อมูลแผนที่ได้ (HTTP 0)');
  }

  async function fetchAndBuildParentCache(mtimeToken, payloadUrl, onProgress) {
    const mtimeStr = mtimeToken ? String(mtimeToken) : '';
    const existing = getValidParentCache(mtimeStr, payloadUrl);
    if (existing) {
      if (typeof onProgress === 'function') onProgress(100, '✓ พร้อมใช้งานแล้ว');
      return existing;
    }
    if (!payloadUrl) {
      throw new Error('Missing tokenized map payload URL');
    }

    const host = getParentHost();
    const inflightKey = mtimeStr + '|' + String(payloadUrl);
    if (host && host.__NOVA_MAP_CACHE_PROMISE__ && host.__NOVA_MAP_CACHE_PROMISE_KEY__ === inflightKey) {
      try {
        const shared = await host.__NOVA_MAP_CACHE_PROMISE__;
        if (shared && shared.data && shared.data.length > 0) {
          return shared;
        }
      } catch (_sharedErr) {
        // If an earlier iframe (e.g. Welcome prewarmer) was unmounted mid-download, Safari aborts its
        // fetch with "Load failed". Clear the dead promise and perform a fresh fetch in this active iframe.
        if (host.__NOVA_MAP_CACHE_PROMISE_KEY__ === inflightKey) {
          host.__NOVA_MAP_CACHE_PROMISE__ = null;
          host.__NOVA_MAP_CACHE_PROMISE_KEY__ = '';
        }
      }
    }

    const workPromise = (async () => {
      if (typeof onProgress === 'function') {
        onProgress(90, 'กำลังดาวน์โหลดและถอดรหัสแคชข้อมูลแผนที่...');
        await yieldIfVisible();
      }
      const candidates = resolveStaticUrlCandidates(payloadUrl);
      let lastReadErr = null;
      for (let attempt = 0; attempt < 2; attempt++) {
        try {
          const { resp, url: winningUrl } = await _fetchStaticPayloadResponse(candidates);
          // Attempt 0: true magic-byte streaming pipeThrough; Attempt 1: buffered arrayBuffer + magic-byte check
          const textStream = await _openAutoGzipTextStream(resp, attempt === 1);
          return await _streamParseBundleToCacheObj(textStream, mtimeStr, winningUrl, onProgress);
        } catch (err) {
          lastReadErr = err;
          if (attempt === 0) {
            if (typeof onProgress === 'function') {
              onProgress(90, 'กำลังเชื่อมต่อดาวน์โหลดแคชแผนที่ใหม่...');
            }
            await new Promise((r) => setTimeout(r, 350));
          }
        }
      }
      throw lastReadErr || new Error('ไม่สามารถอ่านข้อมูลแคชแผนที่ได้');
    })();

    if (host) {
      host.__NOVA_MAP_CACHE_PROMISE__ = workPromise;
      host.__NOVA_MAP_CACHE_PROMISE_KEY__ = inflightKey;
    }
    try {
      return await workPromise;
    } finally {
      if (host && host.__NOVA_MAP_CACHE_PROMISE__ === workPromise) {
        host.__NOVA_MAP_CACHE_PROMISE__ = null;
        host.__NOVA_MAP_CACHE_PROMISE_KEY__ = '';
      }
    }
  }

  // =========================================================================
  // PARENT-SHARED BASEMAP TILE BLOB CACHE (Zero-Latency Initial Map Display)
  // Stores immutable Blobs on window.parent so Tab 2 decodes ImageBitmaps in
  // its own realm (avoiding deck.gl cross-realm instanceof failures & leaks).
  // =========================================================================
  const MAX_CACHED_TILES = isIOSOrIPadOS() ? 48 : 240;
  const _localTileStore = { blobs: new Map(), inflight: new Map() };
  const BASEMAP_TILE_TEMPLATES = {
    google_hybrid: [
      'https://mt0.google.com/vt?lyrs=y&hl=th&x={x}&y={y}&z={z}',
      'https://mt1.google.com/vt?lyrs=y&hl=th&x={x}&y={y}&z={z}',
      'https://mt2.google.com/vt?lyrs=y&hl=th&x={x}&y={y}&z={z}',
      'https://mt3.google.com/vt?lyrs=y&hl=th&x={x}&y={y}&z={z}'
    ],
    google_roadmap: [
      'https://mt0.google.com/vt?lyrs=m&hl=th&x={x}&y={y}&z={z}',
      'https://mt1.google.com/vt?lyrs=m&hl=th&x={x}&y={y}&z={z}',
      'https://mt2.google.com/vt?lyrs=m&hl=th&x={x}&y={y}&z={z}',
      'https://mt3.google.com/vt?lyrs=m&hl=th&x={x}&y={y}&z={z}'
    ],
    satellite: [
      'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'
    ],
    osm: [
      'https://tile.openstreetmap.org/{z}/{x}/{y}.png'
    ],
    voyager: [
      'https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}'
    ]
  };

  function getParentTileCache() {
    const host = getParentHost();
    if (!host) return _localTileStore;
    if (!host.__NOVA_TILE_CACHE__ || !(host.__NOVA_TILE_CACHE__.blobs && host.__NOVA_TILE_CACHE__.inflight)) {
      host.__NOVA_TILE_CACHE__ = { blobs: new Map(), inflight: new Map() };
    }
    return host.__NOVA_TILE_CACHE__;
  }

  function getTileCacheKey(styleName, z, x, y) {
    return String(styleName || 'google_hybrid') + '/' + z + '/' + x + '/' + y;
  }

  function _putTileBlobLRU(blobsMap, key, blob) {
    if (!blobsMap || !blob) return;
    if (blobsMap.has(key)) blobsMap.delete(key);
    blobsMap.set(key, blob);
    while (blobsMap.size > MAX_CACHED_TILES) {
      const oldestKey = blobsMap.keys().next().value;
      if (oldestKey === undefined) break;
      blobsMap.delete(oldestKey);
    }
  }

  function _resolveTileUrl(styleName, z, x, y, explicitUrl) {
    if (explicitUrl) return explicitUrl;
    const list = BASEMAP_TILE_TEMPLATES[styleName] || BASEMAP_TILE_TEMPLATES.google_hybrid;
    const idx = Math.abs((x * 31 + y * 17 + z) | 0) % list.length;
    return list[idx].replace('{x}', String(x)).replace('{y}', String(y)).replace('{z}', String(z));
  }

  async function fetchAndCacheTileBlob(styleName, z, x, y, explicitUrl, signal) {
    const store = getParentTileCache();
    const key = getTileCacheKey(styleName, z, x, y);

    const cached = store.blobs.get(key);
    if (cached) {
      // Touch LRU position
      store.blobs.delete(key);
      store.blobs.set(key, cached);
      return cached;
    }

    const pending = store.inflight.get(key);
    if (pending) {
      return await pending;
    }

    const url = _resolveTileUrl(styleName, z, x, y, explicitUrl);
    const reqPromise = (async () => {
      const fetchOpts = { mode: 'cors', credentials: 'omit' };
      if (signal) fetchOpts.signal = signal;
      const resp = await fetch(url, fetchOpts);
      if (!resp.ok) {
        throw new Error('Tile HTTP ' + resp.status);
      }
      const blob = await resp.blob();
      if (!blob || blob.size === 0) {
        throw new Error('Empty tile blob');
      }
      _putTileBlobLRU(store.blobs, key, blob);
      return blob;
    })();

    store.inflight.set(key, reqPromise);
    try {
      return await reqPromise;
    } finally {
      if (store.inflight.get(key) === reqPromise) {
        store.inflight.delete(key);
      }
    }
  }

  function _lonLatToTileXY(lon, lat, z) {
    const n = Math.pow(2, z);
    const x = ((lon + 180) / 360) * n;
    const latRad = (lat * Math.PI) / 180;
    const y = ((1 - Math.log(Math.tan(latRad) + 1 / Math.cos(latRad)) / Math.PI) / 2) * n;
    return { x, y };
  }

  function _computeInitialThailandTileSpecs(opts) {
    const o = opts || {};
    const lon = Number.isFinite(o.lon) ? o.lon : 100.5;
    const lat = Number.isFinite(o.lat) ? o.lat : 13.5;
    const viewZoom = Number.isFinite(o.zoom) ? o.zoom : 5.2;
    const host = getParentHost();
    const rawW = (host && host.innerWidth) || (global.innerWidth) || 1600;
    const vpW = Math.max(1024, Math.min(2560, rawW));
    const vpH = Number.isFinite(o.height) ? o.height : 870;

    // Deck.gl Tileset2D uses tileZoom = Math.round(viewZoom + Math.log2(512 / tileSize))
    // For tileSize = 256 and viewZoom = 5.2, primary zoom is z = 6; also warm coarse z = 5 fallback.
    const primaryZ = Math.max(4, Math.min(18, Math.round(viewZoom + 1)));
    const specs = [];
    const seen = new Set();

    const addZoomRing = (z, halfW, halfH, priorityWeight) => {
      const n = Math.pow(2, z);
      const c = _lonLatToTileXY(lon, lat, z);
      const minX = Math.max(0, Math.floor(c.x - halfW));
      const maxX = Math.min(n - 1, Math.floor(c.x + halfW));
      const minY = Math.max(0, Math.floor(c.y - halfH));
      const maxY = Math.min(n - 1, Math.floor(c.y + halfH));
      for (let x = minX; x <= maxX; x++) {
        for (let y = minY; y <= maxY; y++) {
          const k = z + '/' + x + '/' + y;
          if (seen.has(k)) continue;
          seen.add(k);
          const dx = (x + 0.5) - c.x;
          const dy = (y + 0.5) - c.y;
          specs.push({ z, x, y, dist: priorityWeight + (dx * dx + dy * dy) });
        }
      }
    };

    const pxPerPrimaryTile = 256 * Math.pow(2, viewZoom + 1 - primaryZ);
    const halfWPrimary = (vpW / 2) / pxPerPrimaryTile + 0.25;
    const halfHPrimary = (vpH / 2) / pxPerPrimaryTile + 0.25;
    // Primary zoom (z=6) gets priority 0 so visible initial tiles finish first; z=5 fallback gets priority 100 (Desktop only)
    addZoomRing(primaryZ, halfWPrimary, halfHPrimary, 0);
    if (primaryZ > 4 && !isIOSOrIPadOS()) {
      addZoomRing(primaryZ - 1, Math.max(1.6, halfWPrimary / 2), Math.max(0.9, halfHPrimary / 2), 100);
    }

    specs.sort((a, b) => a.dist - b.dist);
    return specs;
  }

  async function preloadBasemapTiles(styleName, opts) {
    const style = styleName || 'google_hybrid';
    const specs = _computeInitialThailandTileSpecs(opts);
    if (!specs.length) return { total: 0, loaded: 0 };

    const defaultConc = isIOSOrIPadOS() ? 8 : 16;
    const concurrency = Math.max(4, Math.min(20, (opts && opts.concurrency) || defaultConc));
    let cursor = 0;
    let loaded = 0;

    async function worker() {
      while (cursor < specs.length) {
        const item = specs[cursor++];
        try {
          await fetchAndCacheTileBlob(style, item.z, item.x, item.y, null, null);
          loaded += 1;
        } catch (_err) {
          // Non-fatal: firewall / transient tile error must never block Welcome screen
        }
      }
    }

    const workers = [];
    const count = Math.min(concurrency, specs.length);
    for (let i = 0; i < count; i++) {
      workers.push(worker());
    }
    await Promise.all(workers);
    return { total: specs.length, loaded: loaded };
  }

  // Expose legacy global symbol names so map_template.html has zero duplicate definitions
  global.BRAND_TAG_RULES = BRAND_TAG_RULES;
  global.getBrandSearchTag = getBrandSearchTag;
  global.isPureLocationProjectName = isPureLocationProjectName;
  global.isInvalidProjectName = isInvalidProjectName;
  global.isSpatiallyScatteredGroup = isSpatiallyScatteredGroup;
  global.cleanDisplayProjectName = cleanDisplayProjectName;
  global.normalizeProjectKeyword = normalizeProjectKeyword;
  global.decompressGzip = decompressGzip;
  global.buildSpatialGrid = buildSpatialGrid;
  global.resolveStaticUrlCandidates = resolveStaticUrlCandidates;
  global.makePropCompositeKey = makePropCompositeKey;
  global.parsePropCompositeKey = parsePropCompositeKey;
  global.resolvePropertyByKey = resolvePropertyByKey;

  global.NovaMapCache = {
    GRID_CELL_SIZE: GRID_CELL_SIZE,
    DEFAULT_CO_RGB: DEFAULT_CO_RGB,
    decompressGzip: decompressGzip,
    formatThbPriceStr: formatThbPriceStr,
    hydrateMapRows: hydrateMapRows,
    buildSpatialGrid: buildSpatialGrid,
    buildProjectIndex: buildProjectIndex,
    buildIdLookupIndex: buildIdLookupIndex,
    makePropCompositeKey: makePropCompositeKey,
    parsePropCompositeKey: parsePropCompositeKey,
    resolvePropertyByKey: resolvePropertyByKey,
    computeTypeCounts: computeTypeCounts,
    getEffectiveSelfOrigin: getEffectiveSelfOrigin,
    getParentHost: getParentHost,
    extractPayloadToken: extractPayloadToken,
    clearParentMapCache: clearParentMapCache,
    getValidParentCache: getValidParentCache,
    buildAndStoreParentCache: buildAndStoreParentCache,
    fetchAndBuildParentCache: fetchAndBuildParentCache,
    loadDetailChunk: loadDetailChunk,
    ensureDetailsForItems: ensureDetailsForItems,
    prefetchDetailForItem: prefetchDetailForItem,
    getParentBoundaryCache: getParentBoundaryCache,
    storeParentBoundaryCache: storeParentBoundaryCache,
    getParentTileCache: getParentTileCache,
    getTileCacheKey: getTileCacheKey,
    fetchAndCacheTileBlob: fetchAndCacheTileBlob,
    preloadBasemapTiles: preloadBasemapTiles,
    isIOSOrIPadOS: isIOSOrIPadOS,
    resolveStaticUrlCandidates: resolveStaticUrlCandidates
  };
})(typeof window !== 'undefined' ? window : globalThis);
