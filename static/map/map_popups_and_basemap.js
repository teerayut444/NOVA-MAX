const loader = document.getElementById('loader');
const loaderText = document.getElementById('loader-text');

let deckglInstance = null;
let cachedData = [];
let currentStyle = 'google_hybrid';
let activePropertyData = null;

let currentCoordMap = new Map();
let activeCoordStack = [];
let activeCoordStackIndex = 0;

function getCoordKey(d) {
  return Math.round(d.lat * 100000) + '_' + Math.round(d.lon * 100000);
}

function compareItemsByPriceAsc(a, b) {
  const pA = (a._price && a._price > 0) ? a._price : Infinity;
  const pB = (b._price && b._price > 0) ? b._price : Infinity;
  if (pA !== pB) return pA - pB;

  const uA = (a._unit_price && a._unit_price > 0) ? a._unit_price : Infinity;
  const uB = (b._unit_price && b._unit_price > 0) ? b._unit_price : Infinity;
  return uA - uB;
}

function formatPriceShort(val) {
  const n = Number(val);
  if (!n || isNaN(n) || n <= 0) return 'ไม่ระบุ';
  if (n >= 1000000) {
    const m = n / 1000000;
    return (m % 1 === 0 ? m.toFixed(0) : m.toFixed(2)) + ' ล้าน';
  }
  if (n >= 100000) {
    const k = n / 1000;
    return Math.round(k).toLocaleString() + ' พัน';
  }
  return Math.round(n).toLocaleString();
}

function buildCoordMap(data) {
  const map = new Map();
  for (let i = 0; i < data.length; i++) {
    const d = data[i];
    const key = Math.round(d.lat * 100000) + '_' + Math.round(d.lon * 100000);
    let list = map.get(key);
    if (!list) {
      list = [];
      map.set(key, list);
    }
    list.push(d);
  }
  for (const list of map.values()) {
    if (list.length > 1) {
      list.sort(compareItemsByPriceAsc);
    }
  }
  return map;
}

function updateDuplicateStats(data, coordMap) {
  const totalItems = data.length;
  const uniqueCoords = coordMap.size;
  let dupCoords = 0;
  let dupItems = 0;
  let crossCoCoords = 0;

  for (const list of coordMap.values()) {
    if (list.length > 1) {
      dupCoords++;
      dupItems += list.length;
      const firstCo = list[0]._company;
      for (let j = 1; j < list.length; j++) {
        if (list[j]._company !== firstCo) {
          crossCoCoords++;
          break;
        }
      }
    }
  }

  const overlapText = document.getElementById('legend-overlap-text');
  if (overlapText) {
    overlapText.innerHTML = `พิกัดจริง <b>${uniqueCoords.toLocaleString()}</b> จุด | ซ้ำ (>1) <b>${dupCoords.toLocaleString()}</b> จุด (<b>${dupItems.toLocaleString()}</b> รายการ)`;
    if (crossCoCoords > 0) {
      overlapText.innerHTML += `<br><span style="color:#0284c7; font-weight:700;"><i class="fa-solid fa-building-circle-check" style="margin-right:3px;"></i>มีหลายเจ้าแข่งกัน: <b>${crossCoCoords.toLocaleString()}</b> จุด</span>`;
    }
  }

  const countEl = document.getElementById('points-count');
  if (countEl) {
    countEl.innerText = `แสดงจุดพิกัด ${totalItems.toLocaleString()} รายการ (${uniqueCoords.toLocaleString()} พิกัด)`;
  }

  const badgeText = document.getElementById('filter-count-text');
  if (badgeText) {
    badgeText.innerText = `${totalItems.toLocaleString()} จุด (${uniqueCoords.toLocaleString()} พิกัด)`;
  }
}

function navigateStack(delta) {
  if (!activeCoordStack || activeCoordStack.length <= 1) return;
  let newIdx = activeCoordStackIndex + delta;
  if (newIdx < 0) newIdx = activeCoordStack.length - 1;
  if (newIdx >= activeCoordStack.length) newIdx = 0;
  activeCoordStackIndex = newIdx;
  showPropertyCard(activeCoordStack[activeCoordStackIndex], false);
}

function jumpToStackIndex(val) {
  const idx = parseInt(val, 10);
  if (!isNaN(idx) && activeCoordStack && idx >= 0 && idx < activeCoordStack.length) {
    activeCoordStackIndex = idx;
    showPropertyCard(activeCoordStack[activeCoordStackIndex], false);
  }
}

let toastTimer = null;
function showToast(msg) {
  const toast = document.getElementById('toast');
  if (!toast) return;
  toast.innerHTML = msg;
  toast.classList.add('show');
  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    toast.classList.remove('show');
  }, 2200);
}

function fallbackCopyText(text) {
  const temp = document.createElement('textarea');
  temp.value = text;
  temp.style.position = 'fixed';
  temp.style.opacity = '0';
  document.body.appendChild(temp);
  temp.select();
  try {
    document.execCommand('copy');
    showToast(`<i class="fa-regular fa-copy" style="color:#34d399; margin-right:4px;"></i>คัดลอกรหัสทรัพย์: ${escapeHtml(text)} เรียบร้อยแล้ว`);
  } catch (e) {
    showToast(`<i class="fa-solid fa-circle-xmark" style="color:#f87171; margin-right:4px;"></i>ไม่สามารถคัดลอกได้`);
  }
  document.body.removeChild(temp);
}

let activeCardCoord = null;

function updatePropertyCardPosition() {
  const card = document.getElementById('property-card');
  if (!card || !card.classList.contains('show') || !activeCardCoord || !deckglInstance) return;
  const viewport = getDeckViewport();
  if (!viewport) return;
  const [px, py] = viewport.project(activeCardCoord);
  if (isNaN(px) || isNaN(py)) return;

  const mapEl = document.getElementById('map');
  const mapW = (mapEl && mapEl.clientWidth) || window.innerWidth || 800;
  const mapH = (mapEl && mapEl.clientHeight) || window.innerHeight || 600;

  // Card dimensions
  const cardW = card.offsetWidth || 340;
  const cardH = card.offsetHeight || 380;

  // Anchor popup to the RIGHT of the property pin
  let isRightSide = true;
  let left = px + 18; // 18px clearance to the right of the pin
  let top = py - (cardH / 2); // vertically centered with pin

  // Guard: If not enough room on the right edge of screen, flip to the left
  if (left + cardW > mapW - 12 && px - cardW - 18 >= 12) {
    left = px - cardW - 18;
    isRightSide = false;
  }

  // Horizontal boundary guard
  const minLeft = 12;
  const maxLeft = mapW - cardW - 12;
  if (left < minLeft) left = minLeft;
  if (left > maxLeft) left = maxLeft;

  // Vertical boundary guard
  const minTop = 16;
  const maxTop = Math.max(16, mapH - cardH - 16);
  if (top < minTop) top = minTop;
  if (top > maxTop) top = maxTop;

  const arrowPy = py - top;
  const arrowPct = Math.max(12, Math.min(88, (arrowPy / cardH) * 100));

  card.classList.toggle('popup-on-left', !isRightSide);
  card.classList.toggle('popup-on-right', isRightSide);

  card.style.left = `${left.toFixed(1)}px`;
  card.style.top = `${top.toFixed(1)}px`;
  card.style.setProperty('--arrow-top', `${arrowPct.toFixed(1)}%`);
  card.style.transform = 'none';
}

function closePropertyCard() {
  activeCardCoord = null;
  const card = document.getElementById('property-card');
  if (card && card.classList.contains('show')) {
    card.classList.remove('card-pop-in', 'card-pulse-bounce');
    card.classList.add('card-fade-out');
    setTimeout(() => {
      card.classList.remove('show', 'card-fade-out');
    }, 190);
  }
}

let _hoverDetailPrefetchTimer = null;
let _lastPrefetchedChunkIdx = -1;

function _getDisplayItemTitle(item) {
  if (!item) return 'ไม่มีชื่อประกาศ';
  const raw = (item._title || '').trim();
  if (raw) return raw;
  const prj = (item._project || '').trim();
  const typ = (item._type || '').trim();
  const hasPrj = prj && prj !== '-' && prj !== 'ไม่มีข้อมูล' && prj !== 'ไม่ระบุ';
  const hasTyp = typ && typ !== '-' && typ !== 'ไม่มีข้อมูล' && typ !== 'ไม่ระบุ';
  if (hasTyp && hasPrj) return `${typ} • ${prj}`;
  if (hasPrj) return prj;
  const loc = [item._district, item._prov].filter(x => x && x !== '-' && x !== 'ไม่มีข้อมูล' && x !== 'ไม่ระบุ').join(', ');
  if (hasTyp && loc) return `${typ} • ${loc}`;
  return hasTyp ? typ : (loc || 'ไม่มีชื่อประกาศ');
}

function scheduleHoverDetailPrefetch(item) {
  try {
    if (!item || item._detailLoaded) return;
    const cacheObj = window._activeMapCacheObj;
    if (!cacheObj || !cacheObj.detailConfig || !window.NovaMapCache || typeof window.NovaMapCache.prefetchDetailForItem !== 'function') return;
    const chunkSize = cacheObj.detailConfig.chunkSize || 7000;
    const uid = Number(item._uid);
    if (!Number.isInteger(uid) || uid < 0) return;
    const ci = Math.floor(uid / chunkSize);
    if (cacheObj.loadedDetailChunks && cacheObj.loadedDetailChunks.has(ci)) return;
    if (ci === _lastPrefetchedChunkIdx && _hoverDetailPrefetchTimer) return;
    if (_hoverDetailPrefetchTimer) clearTimeout(_hoverDetailPrefetchTimer);
    _lastPrefetchedChunkIdx = ci;
    _hoverDetailPrefetchTimer = setTimeout(() => {
      _hoverDetailPrefetchTimer = null;
      window.NovaMapCache.prefetchDetailForItem(item, cacheObj);
    }, 120);
  } catch (_e) {}
}

function _refreshCardDetailFields(d) {
  if (!d || activePropertyData !== d) return;
  const titleEl = document.getElementById('card-title');
  if (titleEl) {
    titleEl.innerText = _getDisplayItemTitle(d);
  }
  const selectEl = document.getElementById('card-stack-select');
  if (selectEl && activeCoordStack && activeCoordStack.length > 1) {
    selectEl.innerHTML = activeCoordStack.map((item, i) => {
      const co = item._company || '-';
      const p = item._price_str || '-';
      const uStr = (item._unit_price && item._unit_price > 0) ? ` • ฿${Math.round(item._unit_price).toLocaleString()}/หน่วย` : '';
      const t = _getDisplayItemTitle(item).substring(0, 20);
      return `<option value="${i}" ${i === activeCoordStackIndex ? 'selected' : ''}>${i + 1}. [${escapeHtml(co)}] ${escapeHtml(t)} (${escapeHtml(p)}${uStr})</option>`;
    }).join('');
  }
  const deedEl = document.getElementById('card-deed');
  const rawDeed = String(d._deed || '').trim();
  const hasValidDeed = rawDeed && rawDeed !== '-' && rawDeed !== 'ไม่มีข้อมูล' && rawDeed !== 'nan' && rawDeed !== 'null';
  if (deedEl) {
    if (hasValidDeed) {
      deedEl.innerHTML = `<span style="cursor:pointer; color:#0284c7; font-weight:700; text-decoration:underline dotted;" title="คลิกเพื่อคัดลอกเลขโฉนด" onclick="copyCardDeed()">${escapeHtml(rawDeed)}</span> <i class="fa-regular fa-copy" style="cursor:pointer; font-size:11px; color:#94a3b8; margin-left:2px;" title="คัดลอกเลขโฉนด" onclick="copyCardDeed()"></i>`;
    } else {
      deedEl.innerText = '-';
    }
  }
  const soldDateLabel = document.getElementById('card-sold-date-label');
  const soldDateVal = document.getElementById('card-sold-date-val');
  const soldDate = String(d._sold_date || '').trim();
  if (soldDateLabel && soldDateVal) {
    if (soldDate && soldDate !== '-' && soldDate !== 'nan') {
      soldDateLabel.style.display = 'block';
      soldDateVal.style.display = 'block';
      soldDateVal.innerText = soldDate;
    } else {
      soldDateLabel.style.display = 'none';
      soldDateVal.style.display = 'none';
    }
  }
  const btnLink = document.getElementById('btn-open-link');
  const link = (d._link || '').trim();
  if (btnLink) {
    if (link && link !== '-' && link !== 'nan' && link !== 'None') {
      btnLink.style.display = 'inline-flex';
      btnLink.innerHTML = '<i class="fa-solid fa-arrow-up-right-from-square"></i> เปิดดูทรัพย์สิน (เว็บไซต์)';
      btnLink.disabled = false;
      btnLink.style.opacity = '1';
      btnLink.style.cursor = 'pointer';
    } else {
      btnLink.style.display = 'inline-flex';
      btnLink.innerHTML = '<i class="fa-solid fa-link-slash"></i> ไม่มีลิงก์ประกาศ';
      btnLink.disabled = true;
      btnLink.style.opacity = '0.5';
      btnLink.style.cursor = 'not-allowed';
    }
  }
  const companyName = d._company || 'ไม่ระบุ';
  const isCentroid = (String(d._centroid) === '1' || d._centroid === true || d._centroid === 'true');
  const btnLedRow = document.getElementById('card-row-led');
  const btnGmapTop = document.getElementById('btn-gmap-top');
  const btnGmap = document.getElementById('btn-gmap');
  const isLedComp = (companyName === 'LED' || String(companyName).toUpperCase().indexOf('LED') !== -1 || String(companyName).indexOf('กรมบังคับคดี') !== -1);
  if (isLedComp || hasValidDeed) {
    if (btnLedRow) btnLedRow.style.display = 'flex';
    if (btnGmapTop) btnGmapTop.style.display = 'none';
    if (btnGmap) btnGmap.style.display = isCentroid ? 'none' : 'inline-flex';
  } else {
    if (btnLedRow) btnLedRow.style.display = 'none';
    if (btnGmapTop) btnGmapTop.style.display = isCentroid ? 'none' : 'inline-flex';
    if (btnGmap) btnGmap.style.display = 'none';
  }
}

function showPropertyCard(d, rebuildStack = true) {
  if (d && d.item) d = d.item;
  activePropertyData = d;
  const card = document.getElementById('property-card');
  if (!card) return;

  const wasOpen = card.classList.contains('show');

  // Manage Multi-Asset Stack
  if (rebuildStack) {
    const key = getCoordKey(d);
    activeCoordStack = (currentCoordMap && currentCoordMap.get(key)) || [d];
    if (activeCoordStack.length > 1) {
      activeCoordStack.sort(compareItemsByPriceAsc);
    }
    activeCoordStackIndex = 0;
    if (activeCoordStack.length > 0) {
      d = activeCoordStack[0];
      activePropertyData = d;
    }
  }

  const stackNav = document.getElementById('card-stack-navigator');
  if (stackNav) {
    if (activeCoordStack && activeCoordStack.length > 1) {
      stackNav.style.display = 'flex';

      const coMap = Object.create(null);
      activeCoordStack.forEach(item => {
        const c = item._company || 'ไม่ระบุ';
        coMap[c] = (coMap[c] || 0) + 1;
      });
      const numCos = Object.keys(coMap).length;

      const summaryEl = document.getElementById('card-stack-summary');
      if (summaryEl) {
        summaryEl.innerHTML = `<i class="fa-solid fa-layer-group" style="color:#0284c7;"></i><span>พิกัดนี้มี <b>${activeCoordStack.length}</b> รายการ (<b>${numCos}</b> เจ้า) • เรียงราคาต่ำสุดขึ้นก่อน</span>`;
      }

      const counterEl = document.getElementById('card-stack-counter');
      if (counterEl) {
        counterEl.innerText = `${activeCoordStackIndex + 1} / ${activeCoordStack.length}`;
      }

      const chipsEl = document.getElementById('card-stack-chips');
      if (chipsEl) {
        chipsEl.innerHTML = Object.entries(coMap).map(([co, count]) => {
          return `<span class="card-stack-chip"><b>${escapeHtml(co)}:</b> ${count}</span>`;
        }).join('');
      }

      const selectEl = document.getElementById('card-stack-select');
      if (selectEl) {
        selectEl.innerHTML = activeCoordStack.map((item, i) => {
          const co = item._company || '-';
          const p = item._price_str || '-';
          const uStr = (item._unit_price && item._unit_price > 0) ? ` • ฿${Math.round(item._unit_price).toLocaleString()}/หน่วย` : '';
          const t = _getDisplayItemTitle(item).substring(0, 20);
          return `<option value="${i}" ${i === activeCoordStackIndex ? 'selected' : ''}>${i + 1}. [${escapeHtml(co)}] ${escapeHtml(t)} (${escapeHtml(p)}${uStr})</option>`;
        }).join('');
      }
    } else {
      stackNav.style.display = 'none';
    }
  }

  const badge = document.getElementById('card-badge');
  const title = document.getElementById('card-title');
  const price = document.getElementById('card-price');
  const id = document.getElementById('card-id');
  const type = document.getElementById('card-type');
  const prov = document.getElementById('card-prov');
  const btnLink = document.getElementById('btn-open-link');

  const companyName = d._company || 'ไม่ระบุ';
  badge.innerText = companyName;

  // Dynamic badge color matching company theme
  if (d.r !== undefined && d.g !== undefined && d.b !== undefined) {
    badge.style.background = `rgb(${d.r}, ${d.g}, ${d.b})`;
  } else {
    badge.style.background = '#2563eb';
  }

  // Centroid (approximate coordinate) indicator
  const isCentroid = (String(d._centroid) === '1' || d._centroid === true || d._centroid === 'true');
  const centroidBadge = document.getElementById('card-centroid-badge');
  const centroidWarning = document.getElementById('card-centroid-warning');
  if (centroidBadge) centroidBadge.style.display = isCentroid ? 'inline-flex' : 'none';
  if (centroidWarning) centroidWarning.style.display = isCentroid ? 'flex' : 'none';

  title.innerText = _getDisplayItemTitle(d);
  const _isLegalCompany = (companyName === 'LED Legal' || companyName === 'LED_SOLD');
  if (_isLegalCompany) {
    if (d._sold_p !== undefined && d._sold_p !== null && +d._sold_p >= 500) {
      price.innerText = `฿${Math.round(+d._sold_p).toLocaleString('en-US')} บาท (ขายได้)`;
    } else if (d._price_str && d._price_str !== 'ไม่ระบุราคา') {
      price.innerText = `${d._price_str} (ขายได้)`;
    } else {
      price.innerText = 'ไม่ระบุราคาขายได้';
    }
  } else {
    price.innerText = d._price_str || 'ไม่ระบุราคา';
  }

  const idEl = document.getElementById('card-id');
  const rawId = String(d._id || '').trim();
  const hasValidId = rawId && rawId !== '-' && rawId !== 'ไม่มีข้อมูล' && rawId !== 'nan' && rawId !== 'null';
  if (idEl) {
    if (hasValidId) {
      idEl.innerHTML = `<span style="cursor:pointer; color:#0284c7; font-weight:700; text-decoration:underline dotted;" title="คลิกเพื่อคัดลอกรหัสทรัพย์" onclick="copyCardId()">${escapeHtml(rawId)}</span> <i class="fa-regular fa-copy" style="cursor:pointer; font-size:11px; color:#94a3b8; margin-left:2px;" title="คัดลอกรหัสทรัพย์" onclick="copyCardId()"></i>`;
    } else {
      idEl.innerText = '-';
    }
  }

  const deedEl = document.getElementById('card-deed');
  const rawDeed = String(d._deed || '').trim();
  const hasValidDeed = rawDeed && rawDeed !== '-' && rawDeed !== 'ไม่มีข้อมูล' && rawDeed !== 'nan' && rawDeed !== 'null';
  if (deedEl) {
    if (hasValidDeed) {
      deedEl.innerHTML = `<span style="cursor:pointer; color:#0284c7; font-weight:700; text-decoration:underline dotted;" title="คลิกเพื่อคัดลอกเลขโฉนด" onclick="copyCardDeed()">${escapeHtml(rawDeed)}</span> <i class="fa-regular fa-copy" style="cursor:pointer; font-size:11px; color:#94a3b8; margin-left:2px;" title="คัดลอกเลขโฉนด" onclick="copyCardDeed()"></i>`;
    } else {
      deedEl.innerText = '-';
    }
  }

  type.innerText = d._type || '-';
  prov.innerText = d._prov || '-';

  const prjEl = document.getElementById('card-project');
  const btnPrjCard = document.getElementById('btn-filter-project-card');
  const prjName = (d._project || '').trim();
  const hasValidPrj = prjName && prjName !== '-' && !isInvalidProjectName(prjName);
  if (prjEl) {
    prjEl.innerText = hasValidPrj ? prjName : '-';
    prjEl.style.color = hasValidPrj ? '#059669' : '';
    prjEl.style.fontWeight = hasValidPrj ? '700' : 'normal';
  }
  if (btnPrjCard) {
    if (hasValidPrj) {
      btnPrjCard.style.display = 'inline-flex';
      const shortPrj = prjName.length > 24 ? prjName.substring(0, 22) + '...' : prjName;
      btnPrjCard.innerHTML = `<i class="fa-solid fa-city"></i> ดึงทุกทรัพย์ในโครงการ <b>${escapeHtml(shortPrj)}</b>`;
    } else {
      btnPrjCard.style.display = 'none';
    }
  }

  const dist = document.getElementById('card-dist');
  if (dist) dist.innerText = d._district || '-';
  const subdist = document.getElementById('card-subdist');
  if (subdist) subdist.innerText = d._subdistrict || '-';

  // 1. Location formatted as: ต.[ตำบล] อ.[อำเภอ] จ.[จังหวัด]
  const locParts = [];
  const rawSub = String(d._subdistrict || '').trim();
  if (rawSub && rawSub !== '-' && rawSub !== 'ไม่มีข้อมูล' && rawSub !== 'nan' && rawSub !== 'null') {
    locParts.push((rawSub.startsWith('ต.') || rawSub.startsWith('แขวง')) ? rawSub : `ต.${rawSub}`);
  }
  const rawDist = String(d._district || '').trim();
  if (rawDist && rawDist !== '-' && rawDist !== 'ไม่มีข้อมูล' && rawDist !== 'nan' && rawDist !== 'null') {
    locParts.push((rawDist.startsWith('อ.') || rawDist.startsWith('เขต')) ? rawDist : `อ.${rawDist}`);
  }
  const rawProv = String(d._prov || '').trim();
  if (rawProv && rawProv !== '-' && rawProv !== 'ไม่มีข้อมูล' && rawProv !== 'nan' && rawProv !== 'null') {
    locParts.push(rawProv.startsWith('จ.') ? rawProv : `จ.${rawProv}`);
  }
  const locStr = locParts.length > 0 ? locParts.join(' ') : '-';
  const locEl = document.getElementById('card-loc');
  if (locEl) locEl.innerText = locStr;

  // 2. Horizontal Specs: Floor, Bedroom, Bathroom, Parking (show only available specs)
  const specsLabel = document.getElementById('card-specs-label');
  const specsVal = document.getElementById('card-specs-val');
  const specFl = document.getElementById('card-spec-fl');
  const specFlTxt = document.getElementById('card-spec-fl-txt');
  const specBed = document.getElementById('card-spec-bed');
  const specBedTxt = document.getElementById('card-spec-bed-txt');
  const specBath = document.getElementById('card-spec-bath');
  const specBathTxt = document.getElementById('card-spec-bath-txt');
  const specPkg = document.getElementById('card-spec-pkg');
  const specPkgTxt = document.getElementById('card-spec-pkg-txt');

  let hasAnySpec = false;

  // Floor
  if (d._fl !== undefined && d._fl !== null && +d._fl > 0) {
    if (specFl && specFlTxt) {
      const isCondoType = /ห้องชุด|คอนโด|condo|อาคารชุด/i.test(d._type || '');
      const flNumStr = (+d._fl % 1 === 0) ? Math.round(+d._fl) : d._fl;
      specFlTxt.innerText = isCondoType ? `ชั้นที่ ${flNumStr}` : `${flNumStr} ชั้น`;
      specFl.setAttribute('title', isCondoType ? 'ชั้นที่' : 'จำนวนชั้น');
      specFl.style.display = 'inline-flex';
      hasAnySpec = true;
    }
  } else if (specFl) {
    specFl.style.display = 'none';
  }

  // Bedroom (0 = สตูดิโอ)
  if (d._bed !== undefined && d._bed !== null && +d._bed >= 0) {
    if (specBed && specBedTxt) {
      specBedTxt.innerText = (+d._bed === 0) ? 'สตูดิโอ' : `${Math.round(+d._bed)}`;
      specBed.style.display = 'inline-flex';
      hasAnySpec = true;
    }
  } else if (specBed) {
    specBed.style.display = 'none';
  }

  // Bathroom
  if (d._bath !== undefined && d._bath !== null && +d._bath > 0) {
    if (specBath && specBathTxt) {
      specBathTxt.innerText = `${Math.round(+d._bath)}`;
      specBath.style.display = 'inline-flex';
      hasAnySpec = true;
    }
  } else if (specBath) {
    specBath.style.display = 'none';
  }

  // Parking
  if (d._pkg !== undefined && d._pkg !== null && +d._pkg > 0) {
    if (specPkg && specPkgTxt) {
      specPkgTxt.innerText = `${Math.round(+d._pkg)}`;
      specPkg.style.display = 'inline-flex';
      hasAnySpec = true;
    }
  } else if (specPkg) {
    specPkg.style.display = 'none';
  }

  if (specsLabel && specsVal) {
    specsLabel.style.display = hasAnySpec ? 'block' : 'none';
    specsVal.style.display = hasAnySpec ? 'flex' : 'none';
  }

  // Also keep legacy elements populated for backward compatibility
  const flEl = document.getElementById('card-fl');
  if (flEl) {
    const isCondoType = /ห้องชุด|คอนโด|condo|อาคารชุด/i.test(d._type || '');
    const flNumStr = (d._fl !== undefined && d._fl !== null && +d._fl >= 0)
      ? ((+d._fl % 1 === 0) ? Math.round(+d._fl) : d._fl)
      : null;
    flEl.innerText = flNumStr !== null
      ? (isCondoType ? `ชั้นที่ ${flNumStr}` : `${flNumStr} ชั้น`)
      : '-';
  }
  const bedEl = document.getElementById('card-bed');
  if (bedEl) bedEl.innerText = (d._bed !== undefined && d._bed !== null && +d._bed >= 0) ? (+d._bed === 0 ? 'สตูดิโอ' : `${Math.round(+d._bed)} ห้อง`) : '-';
  const bathEl = document.getElementById('card-bath');
  if (bathEl) bathEl.innerText = (d._bath !== undefined && d._bath !== null && +d._bath >= 0) ? `${Math.round(+d._bath)} ห้อง` : '-';
  const pkgEl = document.getElementById('card-pkg');
  if (pkgEl) pkgEl.innerText = (d._pkg !== undefined && d._pkg !== null && +d._pkg >= 0) ? `${Math.round(+d._pkg)} คัน` : '-';

  // 3. Listing Age Pill (placed in pills header)
  const pillAge = document.getElementById('card-pill-age');
  const pillAgeVal = document.getElementById('card-pill-age-val');
  const isLegalComp = (companyName === 'LED Legal' || companyName === 'LED_SOLD');
  if (pillAge && pillAgeVal) {
    if (d._age !== undefined && d._age !== null && +d._age >= 0) {
      const ageFormatted = Math.round(+d._age).toLocaleString();
      if (isLegalComp) {
        pillAgeVal.innerText = `ขายได้ใน ${ageFormatted} วัน`;
        pillAge.setAttribute('title', 'ระยะเวลาตั้งแต่เริ่มประกาศจนถึงวันขายได้ (วันที่ขาย - วันประกาศ)');
        pillAge.style.background = 'rgba(71, 85, 105, 0.15)';
        pillAge.style.color = '#334155';
        pillAge.style.borderColor = 'rgba(71, 85, 105, 0.3)';
      } else {
        pillAgeVal.innerText = `${ageFormatted} วัน`;
        pillAge.setAttribute('title', 'อายุวันประกาศ (นับถึงปัจจุบัน)');
        pillAge.style.background = 'rgba(139,92,246,0.12)';
        pillAge.style.color = '#8b5cf6';
        pillAge.style.borderColor = 'rgba(139,92,246,0.25)';
      }
      pillAge.style.display = 'inline-flex';
    } else {
      pillAge.style.display = 'none';
    }
  }
  const ageEl = document.getElementById('card-age');
  if (ageEl) {
    if (d._age !== undefined && d._age !== null && +d._age >= 0) {
      const ageFormatted = Math.round(+d._age).toLocaleString();
      ageEl.innerText = isLegalComp ? `ขายได้ใน ${ageFormatted} วัน` : `${ageFormatted} วัน`;
    } else {
      ageEl.innerText = '-';
    }
  }

  // Area and Unit Price details
  const sqwEl = document.getElementById('card-sqw');
  if (sqwEl) {
    sqwEl.innerText = (d._sqw && d._sqw > 0) ? `${d._sqw.toLocaleString(undefined, {minimumFractionDigits: 1, maximumFractionDigits: 1})} ตร.ว.` : '-';
  }
  const sqmEl = document.getElementById('card-sqm');
  if (sqmEl) {
    sqmEl.innerText = (d._sqm && d._sqm > 0) ? `${d._sqm.toLocaleString(undefined, {minimumFractionDigits: 1, maximumFractionDigits: 1})} ตร.ม.` : '-';
  }
  const puwEl = document.getElementById('card-puw');
  if (puwEl) {
    puwEl.innerText = (d._puw && d._puw > 0) ? `฿${Math.round(d._puw).toLocaleString()} / ตร.ว.` : '-';
  }
  const pumEl = document.getElementById('card-pum');
  if (pumEl) {
    pumEl.innerText = (d._pum && d._pum > 0) ? `฿${Math.round(d._pum).toLocaleString()} / ตร.ม.` : '-';
  }

  // Unit Price Pills under price
  const pillPuw = document.getElementById('card-pill-puw');
  const pillPuwVal = document.getElementById('card-pill-puw-val');
  if (pillPuw && pillPuwVal) {
    if (d._puw && d._puw > 0) {
      pillPuwVal.innerText = `฿${Math.round(d._puw).toLocaleString()} / ตร.ว.`;
      pillPuw.style.display = 'inline-flex';
    } else {
      pillPuw.style.display = 'none';
    }
  }
  const pillPum = document.getElementById('card-pill-pum');
  const pillPumVal = document.getElementById('card-pill-pum-val');
  if (pillPum && pillPumVal) {
    if (d._pum && d._pum > 0) {
      pillPumVal.innerText = `฿${Math.round(d._pum).toLocaleString()} / ตร.ม.`;
      pillPum.style.display = 'inline-flex';
    } else {
      pillPum.style.display = 'none';
    }
  }

  // Sold Date (for LED Legal or any sold property)
  const soldDateLabel = document.getElementById('card-sold-date-label');
  const soldDateVal = document.getElementById('card-sold-date-val');
  const soldDate = String(d._sold_date || '').trim();

  if (soldDateLabel && soldDateVal) {
    if (soldDate && soldDate !== '-' && soldDate !== 'nan') {
      soldDateLabel.style.display = 'block';
      soldDateVal.style.display = 'block';
      soldDateVal.innerText = soldDate;
    } else {
      soldDateLabel.style.display = 'none';
      soldDateVal.style.display = 'none';
    }
  }

  // Plaintiff (for LED & LED Legal)
  const plaintiffLabel = document.getElementById('card-plaintiff-label');
  const plaintiffVal = document.getElementById('card-plaintiff-val');

  const plaintiffStr = String(d._plaintiff || '').trim();
  const isLed = String(d._company || '').startsWith('LED');

  if (plaintiffLabel && plaintiffVal) {
    if (isLed && plaintiffStr && plaintiffStr !== '-' && plaintiffStr !== 'nan' && plaintiffStr !== 'None' && plaintiffStr !== 'null') {
      plaintiffLabel.style.display = 'block';
      plaintiffVal.style.display = 'block';
      plaintiffVal.innerText = plaintiffStr;
    } else {
      plaintiffLabel.style.display = 'none';
      plaintiffVal.style.display = 'none';
    }
  }

  // Distance from active reference point & Status of reference button
  const pillDist = document.getElementById('card-pill-distance');
  const pillDistVal = document.getElementById('card-pill-dist-val');
  const btnSetRef = document.getElementById('btn-set-ref-card');

  let isCurrentRef = false;
  if (referencePoint && referencePoint.length >= 2 && d.lat && d.lon) {
    const distKm = haversineDistanceKm(referencePoint[1], referencePoint[0], parseFloat(d.lat), parseFloat(d.lon));
    isCurrentRef = (
      (currentRefProp && (String(currentRefProp._id).trim() === String(d._id).trim() && String(d._id).trim() !== '-' && String(d._id).trim() !== '')) ||
      distKm < 0.002
    );

    if (pillDist && pillDistVal) {
      if (isCurrentRef || distKm < 0.002) {
        pillDistVal.innerText = 'จุดอ้างอิงปัจจุบัน';
        pillDist.style.display = 'inline-flex';
        pillDist.style.background = 'rgba(239, 68, 68, 0.12)';
        pillDist.style.color = '#ef4444';
        pillDist.style.borderColor = 'rgba(239, 68, 68, 0.25)';
      } else {
        const distText = distKm < 1 ? `${Math.round(distKm * 1000)} ม.` : `${distKm.toFixed(2)} กม.`;
        pillDistVal.innerText = `ห่างจากจุดอ้างอิง ${distText}`;
        pillDist.style.display = 'inline-flex';
        pillDist.style.background = 'rgba(245, 158, 11, 0.12)';
        pillDist.style.color = '#d97706';
        pillDist.style.borderColor = 'rgba(245, 158, 11, 0.25)';
      }
    }
  } else if (pillDist) {
    pillDist.style.display = 'none';
  }

  if (btnSetRef) {
    if (isCurrentRef) {
      btnSetRef.disabled = true;
      btnSetRef.style.opacity = '0.7';
      btnSetRef.style.cursor = 'default';
      btnSetRef.style.background = '#64748b';
      btnSetRef.innerHTML = '<i class="fa-solid fa-check"></i> จุดอ้างอิงปัจจุบัน';
    } else {
      btnSetRef.disabled = false;
      btnSetRef.style.opacity = '1';
      btnSetRef.style.cursor = 'pointer';
      btnSetRef.style.background = 'linear-gradient(135deg, #059669, #047857)';
      btnSetRef.innerHTML = '<i class="fa-solid fa-crosshairs"></i> ตั้งจุดอ้างอิง';
    }
  }

  const btnSetPriceCenter = document.getElementById('btn-set-price-center-card');
  if (btnSetPriceCenter) {
    const propId = String(d._id || '').trim().toLowerCase();
    const isPriceCenter = (currentPriceCenterId && propId && String(currentPriceCenterId).trim().toLowerCase() === propId);
    if (isPriceCenter) {
      btnSetPriceCenter.disabled = false;
      btnSetPriceCenter.style.opacity = '1';
      btnSetPriceCenter.style.cursor = 'pointer';
      btnSetPriceCenter.style.background = 'linear-gradient(135deg, #e11d48, #be185d)';
      btnSetPriceCenter.style.boxShadow = '0 0 0 2px #F6BAC0, 0 4px 12px rgba(225, 29, 72, 0.45)';
      btnSetPriceCenter.innerHTML = '<i class="fa-solid fa-check"></i> ศูนย์กลางราคาปัจจุบัน (คลิกเพื่อตั้งซ้ำ)';
    } else {
      btnSetPriceCenter.disabled = false;
      btnSetPriceCenter.style.opacity = '1';
      btnSetPriceCenter.style.cursor = 'pointer';
      btnSetPriceCenter.style.background = 'linear-gradient(135deg, #F6BAC0, #f43f5e)';
      btnSetPriceCenter.style.boxShadow = '0 4px 12px rgba(244, 63, 94, 0.35)';
      btnSetPriceCenter.innerHTML = '<i class="fa-solid fa-scale-balanced"></i> ตั้งศูนย์กลางราคา (เทียบตรง)';
    }
  }

  const btnToggleComp = document.getElementById('btn-toggle-compare-card');
  if (btnToggleComp) {
    const propId = String(d._id || '').trim();
    const isSelected = selectedComparisonProps && selectedComparisonProps.has(propId);
    if (isSelected) {
      btnToggleComp.classList.add('selected');
      btnToggleComp.innerHTML = '<i class="fa-solid fa-square-check"></i> เลือกอยู่ (ยกเลิก)';
    } else {
      btnToggleComp.classList.remove('selected');
      btnToggleComp.innerHTML = '<i class="fa-regular fa-square-check"></i> ติ๊กเลือกเปรียบเทียบ';
    }
  }

  const cacheObjForDetail = window._activeMapCacheObj;
  const needsDetailFetch = !!(
    cacheObjForDetail &&
    cacheObjForDetail.detailConfig &&
    window.NovaMapCache &&
    typeof window.NovaMapCache.ensureDetailsForItems === 'function' &&
    (!d._detailLoaded || (activeCoordStack && activeCoordStack.some(it => it && !it._detailLoaded)))
  );

  const link = (d._link || '').trim();
  if (link && link !== '-' && link !== 'nan' && link !== 'None') {
    btnLink.style.display = 'inline-flex';
    btnLink.innerHTML = '<i class="fa-solid fa-arrow-up-right-from-square"></i> เปิดดูทรัพย์สิน (เว็บไซต์)';
    btnLink.disabled = false;
    btnLink.style.opacity = '1';
    btnLink.style.cursor = 'pointer';
  } else if (needsDetailFetch) {
    btnLink.style.display = 'inline-flex';
    btnLink.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> กำลังโหลดรายละเอียด...';
    btnLink.disabled = true;
    btnLink.style.opacity = '0.75';
    btnLink.style.cursor = 'wait';
  } else {
    btnLink.style.display = 'inline-flex';
    btnLink.innerHTML = '<i class="fa-solid fa-link-slash"></i> ไม่มีลิงก์ประกาศ';
    btnLink.disabled = true;
    btnLink.style.opacity = '0.5';
    btnLink.style.cursor = 'not-allowed';
  }

  if (needsDetailFetch) {
    const itemsToHydrate = (activeCoordStack && activeCoordStack.length > 0) ? activeCoordStack : [d];
    window.NovaMapCache.ensureDetailsForItems(itemsToHydrate, cacheObjForDetail)
      .then(() => { _refreshCardDetailFields(d); })
      .catch(() => { _refreshCardDetailFields(d); });
  }

  const btnLedRow = document.getElementById('card-row-led');
  const btnGmapTop = document.getElementById('btn-gmap-top');
  const btnGmap = document.getElementById('btn-gmap');
  const isLedComp = (companyName === 'LED' || String(companyName).toUpperCase().indexOf('LED') !== -1 || String(companyName).indexOf('กรมบังคับคดี') !== -1);
  const hasDeed = !!hasValidDeed;
  const hasLandsMap = (isLedComp || hasDeed);

  if (hasLandsMap) {
    if (btnLedRow) btnLedRow.style.display = 'flex';
    if (btnGmapTop) btnGmapTop.style.display = 'none';
    if (btnGmap) btnGmap.style.display = isCentroid ? 'none' : 'inline-flex';
  } else {
    if (btnLedRow) btnLedRow.style.display = 'none';
    if (btnGmapTop) btnGmapTop.style.display = isCentroid ? 'none' : 'inline-flex';
    if (btnGmap) btnGmap.style.display = 'none';
  }

  // Snappy movement & animation feedback
  card.classList.remove('card-pop-in', 'card-pulse-bounce', 'card-fade-out');
  void card.offsetWidth; // Force CSS reflow so animation restarts reliably

  card.classList.add('show');
  if (wasOpen) {
    card.classList.add('card-pulse-bounce');
  } else {
    card.classList.add('card-pop-in');
  }

  // Micro-pop for price and badge
  if (price) {
    price.classList.remove('content-pop');
    void price.offsetWidth;
    price.classList.add('content-pop');
  }
  if (badge) {
    badge.classList.remove('content-pop');
    void badge.offsetWidth;
    badge.classList.add('content-pop');
  }

  // Anchor popup to the exact clicked property pin coordinate
  activeCardCoord = [d.lon, d.lat];
  updatePropertyCardPosition();
  requestAnimationFrame(() => updatePropertyCardPosition());

  // Smooth camera adjustment: pan map so clicked pin is slightly left of center (~mapW / 2 - 130px)
  // leaving abundant room for the callout popup directly to the RIGHT of the pin!
  if (deckglInstance && d.lon && d.lat) {
    const mapH = window.innerHeight;
    const mapW = window.innerWidth;
    const zoom = (currentViewState && currentViewState.zoom) || 12.5;

    const desiredPinX = Math.max(80, (mapW / 2) - 130);
    const deltaX = desiredPinX - (mapW / 2); // pixels pin is LEFT of map center

    let targetCenterLon = d.lon;
    let targetCenterLat = d.lat;

    let calculated = false;
    if (deck && deck.WebMercatorViewport) {
      try {
        const tempVp = new deck.WebMercatorViewport({
          width: mapW,
          height: mapH,
          longitude: d.lon,
          latitude: d.lat,
          zoom: zoom,
          pitch: 0,
          bearing: 0
        });
        // The point that becomes map center is -deltaX pixels to the RIGHT of the pin:
        const newCenter = tempVp.unproject([(mapW / 2) - deltaX, mapH / 2]);
        if (newCenter && !isNaN(newCenter[0]) && !isNaN(newCenter[1])) {
          targetCenterLon = newCenter[0];
          targetCenterLat = newCenter[1];
          calculated = true;
        }
      } catch(e) {
        console.warn('Center offset calculation error:', e);
      }
    }

    if (!calculated) {
      const metersPerPixel = (156543.03392 * Math.cos(d.lat * Math.PI / 180)) / Math.pow(2, zoom);
      const deltaMetersX = -deltaX * metersPerPixel;
      targetCenterLon = d.lon + (deltaMetersX / (111320 * Math.cos(d.lat * Math.PI / 180)));
      targetCenterLat = d.lat;
    }

    currentViewState = {
      ...currentViewState,
      longitude: targetCenterLon,
      latitude: targetCenterLat,
      transitionDuration: 450,
      transitionInterpolator: new deck.FlyToInterpolator()
    };
    deckglInstance.setProps({ viewState: currentViewState });

    let animStartTime = performance.now();
    function followTransition() {
      updatePropertyCardPosition();
      if (performance.now() - animStartTime < 500) {
        requestAnimationFrame(followTransition);
      }
    }
    requestAnimationFrame(followTransition);
  }
}

function openPropertyLink() {
  if (!activePropertyData) return;
  const comp = String(activePropertyData._company || '').trim();
  const isLegal = (comp === 'LED Legal' || comp === 'LED_SOLD');
  let link = (activePropertyData._link || '').trim();

  if (isLegal) {
    // If not already pointing to led_legal_bridge.html, route to led_legal_bridge.html with suit_no & suit_year
    if (!link.includes('led_legal_bridge.html')) {
      let suitNo = '';
      let suitYear = '';
      const mSuit = link.match(/[?&]suit_no=([^&]+)/);
      const mYear = link.match(/[?&]suit_year=([^&]+)/);
      if (mSuit) suitNo = decodeURIComponent(mSuit[1]);
      if (mYear) suitYear = decodeURIComponent(mYear[1]);

      if (!suitNo || !suitYear) {
        const codeOrTitle = String(activePropertyData._id || activePropertyData._title || '');
        const cleanCode = codeOrTitle.replace(/_.*$/, '').trim();
        if (cleanCode.includes('/')) {
          const parts = cleanCode.split('/');
          suitNo = suitNo || parts[0].trim();
          suitYear = suitYear || parts[1].trim();
        }
      }

      if (suitNo) {
        const params = new URLSearchParams();
        params.set('suit_no', suitNo);
        if (suitYear) params.set('suit_year', suitYear);
        link = `/app/static/led_legal_bridge.html?${params.toString()}`;
      }
    }
  }

  if (link && link !== '-' && link !== 'nan' && link !== 'None') {
    if (link.startsWith('app/static/')) {
      link = '/' + link;
    }
    if (typeof resolveNovaStaticUrl === 'function' && !/^https?:\/\//i.test(link) && link.indexOf('/' + 'app/static/') !== -1) {
      link = resolveNovaStaticUrl(link);
    }
    if (isSafeNavUrl(link)) {
      window.open(link, '_blank', 'noopener,noreferrer');
    } else {
      showToast('ลิงก์ไม่ปลอดภัยหรือรูปแบบไม่ถูกต้อง');
    }
  } else {
    showToast('ไม่พบลิงก์ประกาศสำหรับทรัพย์สินนี้');
  }
}

function filterCardProject() {
  if (!activePropertyData) return;
  const prjName = (activePropertyData._project || '').trim();
  if (prjName && prjName !== '-' && !isInvalidProjectName(prjName)) {
    let canonical = null;
    if (activePropertyData._normKey && typeof normKeyToCanonicalMap !== 'undefined') {
      canonical = normKeyToCanonicalMap.get(activePropertyData._normKey);
    }
    if (!canonical) {
      canonical = cleanDisplayProjectName(prjName);
    }
    toggleProjectOption(canonical || prjName);
  }
}

function openLedMap() {
  if (!activePropertyData) {
    window.open('https://landsmaps.dol.go.th/', '_blank', 'noopener,noreferrer');
    return;
  }
  const prov = (activePropertyData._prov || '').trim();
  const dist = (activePropertyData._district || '').trim();
  const subdist = (activePropertyData._subdistrict || '').trim();
  const id = (activePropertyData._id || '').trim();
  let rawDeed = String(activePropertyData._deed || '').trim();
  let deed = (rawDeed && rawDeed !== '-' && rawDeed !== 'ไม่มีข้อมูล' && rawDeed !== 'nan' && rawDeed !== 'null') ? rawDeed : '';

  const params = new URLSearchParams();
  if (prov && prov !== '-') params.set('prov', prov);
  if (dist && dist !== '-') params.set('dist', dist);
  if (subdist && subdist !== '-') params.set('subdist', subdist);
  if (id && id !== '-') params.set('case', id);
  if (deed && deed !== '-') params.set('deed', deed);

  const hashPart = params.toString() ? '#' + params.toString() : '';
  const landsUrl = 'https://landsmaps.dol.go.th/' + hashPart;

  // Auto copy search terms to clipboard for easy fallback
  const copyText = `${prov} ${dist} ${deed}`.trim();
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(copyText).catch(() => {});
  }

  const deedMsg = deed ? ` โฉนด ${deed}` : '';
  showToast(`<i class="fa-solid fa-map-location-dot" style="color:#38bdf8; margin-right:6px;"></i>กำลังเปิด LandsMaps (${escapeHtml(prov)} - ${escapeHtml(dist)}${escapeHtml(deedMsg)}) | กด Bookmarklet เพื่อค้นหาออโต้`);
  window.open(landsUrl, '_blank', 'noopener,noreferrer');
}

function openLandsmapsHelperModal() {
  const modal = document.getElementById('lands-helper-modal');
  if (modal) modal.classList.add('show');
}

function closeLandsmapsHelperModal() {
  const modal = document.getElementById('lands-helper-modal');
  if (modal) modal.classList.remove('show');
}

function copyBookmarkletCode() {
  const link = document.getElementById('bookmarklet-link');
  if (!link) return;
  const code = link.getAttribute('href');
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(code).then(() => {
      showToast('<i class="fa-regular fa-clipboard" style="color:#34d399; margin-right:6px;"></i>คัดลอกโค้ด Bookmarklet เรียบร้อยแล้ว! นำไปวางใน URL บุ๊กมาร์กได้เลย');
    }).catch(() => {
      fallbackCopyText(code);
    });
  } else {
    fallbackCopyText(code);
  }
}

function copyCardId() {
  if (!activePropertyData || !activePropertyData._id || activePropertyData._id === '-') {
    showToast('<i class="fa-solid fa-circle-exclamation" style="color:#f59e0b; margin-right:4px;"></i>ไม่พบรหัสทรัพย์');
    return;
  }
  const code = activePropertyData._id;
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(code).then(() => {
      showToast(`<i class="fa-regular fa-copy" style="color:#34d399; margin-right:4px;"></i>คัดลอกรหัสทรัพย์: ${escapeHtml(code)} เรียบร้อยแล้ว`);
    }).catch(() => {
      fallbackCopyText(code);
    });
  } else {
    fallbackCopyText(code);
  }
}

function copyCardDeed() {
  if (!activePropertyData) return;
  const rawDeed = String(activePropertyData._deed || '').trim();
  const hasValidDeed = rawDeed && rawDeed !== '-' && rawDeed !== 'ไม่มีข้อมูล' && rawDeed !== 'nan' && rawDeed !== 'null';
  if (!hasValidDeed) {
    showToast('<i class="fa-solid fa-circle-exclamation" style="color:#f59e0b; margin-right:4px;"></i>ไม่มีข้อมูลเลขโฉนดสำหรับทรัพย์นี้');
    return;
  }
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(rawDeed).then(() => {
      showToast(`<i class="fa-regular fa-copy" style="color:#34d399; margin-right:4px;"></i>คัดลอกเลขโฉนด: ${escapeHtml(rawDeed)} เรียบร้อยแล้ว`);
    }).catch(() => {
      fallbackCopyText(rawDeed);
    });
  } else {
    fallbackCopyText(rawDeed);
  }
}

function openGoogleMaps() {
  if (!activePropertyData || !activePropertyData.lat || !activePropertyData.lon) return;
  const isCentroid = (String(activePropertyData._centroid) === '1' || activePropertyData._centroid === true || activePropertyData._centroid === 'true');
  if (isCentroid) return;
  const url = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(activePropertyData.lat)},${encodeURIComponent(activePropertyData.lon)}`;
  window.open(url, '_blank', 'noopener,noreferrer');
}

function setCardAsReferencePoint() {
  if (!activePropertyData || !activePropertyData.lat || !activePropertyData.lon) return;
  const lat = parseFloat(activePropertyData.lat);
  const lon = parseFloat(activePropertyData.lon);
  const id = (activePropertyData._id || '').trim();

  currentRefProp = activePropertyData;
  currentPriceCenterId = "";

  // Sync geographic selections from this property
  if (activePropertyData._prov && activePropertyData._prov !== '-' && activePropertyData._prov !== 'ไม่มีข้อมูล') {
    currentSelectedProv = activePropertyData._prov.trim();
    if (activePropertyData._district && activePropertyData._district !== '-' && activePropertyData._district !== 'ไม่มีข้อมูล') {
      currentSelectedDist = activePropertyData._district.trim();
    }
    if (activePropertyData._subdistrict && activePropertyData._subdistrict !== '-' && activePropertyData._subdistrict !== 'ไม่มีข้อมูล') {
      currentSelectedSubdist = activePropertyData._subdistrict.trim();
    }
    updateDistrictSubdistrictBoundaries();
    syncComboboxInputs();
  }

  const inp = document.getElementById('inmap-prop-search-input');
  const clr = document.getElementById('inmap-clear-search-btn');
  if (inp && id) inp.value = id;
  if (clr && id) clr.style.display = 'inline-flex';

  if (mapPinMode !== 'radius') {
    mapPinMode = 'radius';
    const btnLoc = document.getElementById('btn-mode-location');
    const btnRad = document.getElementById('btn-mode-radius');
    if (btnLoc) btnLoc.classList.toggle('active', false);
    if (btnRad) btnRad.classList.toggle('active', true);
  }
  setReferencePoint(lon, lat, true, false);
  showPropertyCard(activePropertyData, false);

  try {
    var u = new URL(window.parent.location.href);
    u.searchParams.set('map_ref_lat', lat.toFixed(6));
    u.searchParams.set('map_ref_lon', lon.toFixed(6));
    u.searchParams.set('map_ref_radius', currentRadiusKm);
    u.searchParams.set('map_pin_mode', 'radius');
    u.searchParams.delete('map_price_ref_id');
    if (id && id !== '-') {
      u.searchParams.set('map_ref_id', id);
    }
    if (activePropertyData && activePropertyData._prov && activePropertyData._prov !== '-' && activePropertyData._prov !== 'ไม่มีข้อมูล') {
      u.searchParams.set('map_prov', activePropertyData._prov);
    }
    if (activePropertyData && activePropertyData._district && activePropertyData._district !== '-' && activePropertyData._district !== 'ไม่มีข้อมูล') {
      u.searchParams.set('map_dist', activePropertyData._district);
    }
    if (activePropertyData && activePropertyData._subdistrict && activePropertyData._subdistrict !== '-' && activePropertyData._subdistrict !== 'ไม่มีข้อมูล') {
      u.searchParams.set('map_subdist', activePropertyData._subdistrict);
    }
    window.parent.history.replaceState({}, '', u.toString());
  } catch(e) {
    console.warn('Sync to Streamlit error:', e);
  }
  triggerStreamlitSync({
    prov: (activePropertyData && activePropertyData._prov) || '',
    dist: (activePropertyData && activePropertyData._district) || '',
    subdist: (activePropertyData && activePropertyData._subdistrict) || '',
    id: (id && id !== '-') ? id : '',
    price_center_id: '',
    lat: lat,
    lon: lon,
    radius: currentRadiusKm || 5.0,
    mode: 'radius',
    compare_active: true
  });
}

function setCardAsPriceCenter() {
  if (!activePropertyData || !activePropertyData.lat || !activePropertyData.lon) return;
  const lat = parseFloat(activePropertyData.lat);
  const lon = parseFloat(activePropertyData.lon);
  const id = (activePropertyData._id || '').trim();

  currentRefProp = activePropertyData;
  currentPriceCenterId = id;

  // Sync geographic selections from this property
  if (activePropertyData._prov && activePropertyData._prov !== '-' && activePropertyData._prov !== 'ไม่มีข้อมูล') {
    currentSelectedProv = activePropertyData._prov.trim();
    if (activePropertyData._district && activePropertyData._district !== '-' && activePropertyData._district !== 'ไม่มีข้อมูล') {
      currentSelectedDist = activePropertyData._district.trim();
    }
    if (activePropertyData._subdistrict && activePropertyData._subdistrict !== '-' && activePropertyData._subdistrict !== 'ไม่มีข้อมูล') {
      currentSelectedSubdist = activePropertyData._subdistrict.trim();
    }
    updateDistrictSubdistrictBoundaries();
    syncComboboxInputs();
  }

  const inp = document.getElementById('inmap-prop-search-input');
  const clr = document.getElementById('inmap-clear-search-btn');
  if (inp && id) inp.value = id;
  if (clr && id) clr.style.display = 'inline-flex';

  if (mapPinMode !== 'radius') {
    mapPinMode = 'radius';
    const btnLoc = document.getElementById('btn-mode-location');
    const btnRad = document.getElementById('btn-mode-radius');
    if (btnLoc) btnLoc.classList.toggle('active', false);
    if (btnRad) btnRad.classList.toggle('active', true);
  }
  setReferencePoint(lon, lat, true, false);
  showPropertyCard(activePropertyData, false);

  showToast(`<i class="fa-solid fa-scale-balanced" style="color:#e11d48; margin-right:6px;"></i>ตั้งเป็นศูนย์กลางราคา: <b>${escapeHtml(id)}</b> (รัศมี ${formatRadiusDisplay(currentRadiusKm)})`);

  try {
    var u = new URL(window.parent.location.href);
    u.searchParams.set('map_ref_lat', lat.toFixed(6));
    u.searchParams.set('map_ref_lon', lon.toFixed(6));
    u.searchParams.set('map_ref_radius', currentRadiusKm);
    u.searchParams.set('map_pin_mode', 'radius');
    if (id && id !== '-') {
      u.searchParams.set('map_ref_id', id);
      u.searchParams.set('map_price_ref_id', id);
    }
    if (activePropertyData && activePropertyData._prov && activePropertyData._prov !== '-' && activePropertyData._prov !== 'ไม่มีข้อมูล') {
      u.searchParams.set('map_prov', activePropertyData._prov);
    }
    if (activePropertyData && activePropertyData._district && activePropertyData._district !== '-' && activePropertyData._district !== 'ไม่มีข้อมูล') {
      u.searchParams.set('map_dist', activePropertyData._district);
    }
    if (activePropertyData && activePropertyData._subdistrict && activePropertyData._subdistrict !== '-' && activePropertyData._subdistrict !== 'ไม่มีข้อมูล') {
      u.searchParams.set('map_subdist', activePropertyData._subdistrict);
    }
    window.parent.history.replaceState({}, '', u.toString());
  } catch(e) {
    console.warn('Sync to Streamlit error:', e);
  }
  triggerStreamlitSync({
    prov: (activePropertyData && activePropertyData._prov) || '',
    dist: (activePropertyData && activePropertyData._district) || '',
    subdist: (activePropertyData && activePropertyData._subdistrict) || '',
    id: (id && id !== '-') ? id : '',
    price_center_id: (id && id !== '-') ? id : '',
    lat: lat,
    lon: lon,
    radius: currentRadiusKm || 5.0,
    mode: 'radius',
    compare_active: true
  });
}

function clearPriceCenter() {
  currentPriceCenterId = "";
  try {
    var u = new URL(window.parent.location.href);
    u.searchParams.delete('map_price_ref_id');
    window.parent.history.replaceState({}, '', u.toString());
  } catch(e) {}

  const btnSetPriceCenter = document.getElementById('btn-set-price-center-card');
  if (btnSetPriceCenter) {
    btnSetPriceCenter.disabled = false;
    btnSetPriceCenter.style.opacity = '1';
    btnSetPriceCenter.style.cursor = 'pointer';
    btnSetPriceCenter.style.background = 'linear-gradient(135deg, #F6BAC0, #f43f5e)';
    btnSetPriceCenter.style.boxShadow = '0 4px 12px rgba(244, 63, 94, 0.35)';
    btnSetPriceCenter.innerHTML = '<i class="fa-solid fa-scale-balanced"></i> ตั้งศูนย์กลางราคา (เทียบตรง)';
  }
  triggerStreamlitSync({ price_center_id: '' }, 0);
}
window.clearPriceCenter = clearPriceCenter;

// =========================================================================
// BOTTOM-CENTER BATCH REFERENCE SELECTOR POPUP (TAB 2)
// =========================================================================
let batchReferenceItems = [];
let batchRefCurrentIdx = -1;
let batchRefLockType = true;
let batchRefPopupOpen = false;
let batchRefSearchQuery = "";

function _syncTypeFilterChipsDom() {
  try {
    document.querySelectorAll('.filter-chip[data-group="type"][data-val]').forEach(chipEl => {
      const val = chipEl.dataset.val;
      const isAct = !!(inMapFilterState && inMapFilterState.types && inMapFilterState.types.has(val));
      chipEl.classList.toggle('active', isAct);
    });
  } catch (_e) {}
}

function _formatBatchRefPriceShort(val) {
  const n = Number(val);
  if (!Number.isFinite(n) || n <= 0) return '';
  if (n >= 1e6) return '฿' + (n / 1e6).toFixed(2).replace(/\.?0+$/, '') + 'M';
  if (n >= 1e3) return '฿' + Math.round(n / 1e3).toLocaleString('en-US') + 'K';
  return '฿' + Math.round(n).toLocaleString('en-US');
}

function updateBatchRefBarUi() {
  const nav = document.getElementById('batch-ref-navigator');
  if (!nav) return;
  if (!Array.isArray(batchReferenceItems) || batchReferenceItems.length === 0) {
    nav.style.display = 'none';
    closeBatchRefPopup();
    return;
  }
  nav.style.display = 'flex';
  const total = batchReferenceItems.length;
  const totalBadge = document.getElementById('batch-ref-popup-total');
  if (totalBadge) totalBadge.innerText = `${total} รายการ`;

  const idxPill = document.getElementById('batch-ref-idx-pill');
  const codeEl = document.getElementById('batch-ref-active-code');
  const subEl = document.getElementById('batch-ref-active-sub');

  if (batchRefCurrentIdx >= 0 && batchRefCurrentIdx < total) {
    const it = batchReferenceItems[batchRefCurrentIdx];
    if (idxPill) idxPill.innerText = `${batchRefCurrentIdx + 1} / ${total}`;
    if (codeEl) codeEl.innerText = it.code || `REF-${batchRefCurrentIdx + 1}`;
    const subParts = [it.prop_type || 'อื่นๆ'];
    if (it.price > 0) subParts.push(_formatBatchRefPriceShort(it.price));
    if (it.prov) subParts.push(it.prov);
    if (subEl) subEl.innerText = subParts.join(' • ');
  } else {
    if (idxPill) idxPill.innerText = `ชุดอ้างอิง (${total})`;
    if (codeEl) codeEl.innerText = 'เลือกดูทรัพย์อ้างอิงทีละชิ้น';
    if (subEl) subEl.innerText = 'คลิกเปิดรายการ หรือกด ◀ / ▶';
  }

  const lockBtn = document.getElementById('batch-ref-lock-type-btn');
  const lockIcon = document.getElementById('batch-ref-lock-icon');
  if (lockBtn) lockBtn.classList.toggle('active', !!batchRefLockType);
  if (lockIcon) lockIcon.className = batchRefLockType ? 'fa-solid fa-lock' : 'fa-solid fa-lock-open';
}

function renderBatchRefList() {
  const listEl = document.getElementById('batch-ref-list');
  if (!listEl) return;
  const q = (batchRefSearchQuery || '').trim().toLowerCase();
  const matched = [];
  for (let i = 0; i < batchReferenceItems.length; i++) {
    const it = batchReferenceItems[i];
    if (q) {
      const hay = `${it.idx} ${it.code || ''} ${it.prop_type || ''} ${it.project || ''} ${it.prov || ''} ${it.dist || ''} ${it.company || ''}`.toLowerCase();
      if (!hay.includes(q)) continue;
    }
    matched.push({ i, it });
  }
  if (matched.length === 0) {
    listEl.innerHTML = '<div style="padding:14px; text-align:center; font-size:12px; color:#94a3b8;">ไม่พบทรัพย์อ้างอิงที่ตรงกับคำค้นหา</div>';
    return;
  }
  const cap = matched.slice(0, 300);
  listEl.innerHTML = cap.map(({ i, it }) => {
    const isAct = i === batchRefCurrentIdx ? ' active' : '';
    const isInv = !it.valid ? ' invalid' : '';
    const safeCode = escapeHtml(it.code || `REF-${i + 1}`);
    const safeType = escapeHtml(it.prop_type || 'อื่นๆ');
    const metaParts = [safeType];
    if (it.project) metaParts.push(escapeHtml(it.project));
    if (it.prov) metaParts.push(escapeHtml(it.prov));
    const rightHtml = it.valid
      ? `<div>${escapeHtml(_formatBatchRefPriceShort(it.price) || '-')}</div>`
      : '<span class="batch-ref-item-invalid-badge">ไม่มีพิกัด</span>';
    return (
      `<div class="batch-ref-item${isAct}${isInv}" data-batch-idx="${i}" onclick="selectBatchReference(Number(this.dataset.batchIdx))">` +
      `  <div class="batch-ref-item-main">` +
      `    <div class="batch-ref-item-top"><span class="batch-ref-item-num">#${it.idx}</span><span>${safeCode}</span></div>` +
      `    <div class="batch-ref-item-meta">${metaParts.join(' • ')}</div>` +
      `  </div>` +
      `  <div class="batch-ref-item-right">${rightHtml}</div>` +
      `</div>`
    );
  }).join('');
}

function toggleBatchRefPopup() {
  const panel = document.getElementById('batch-ref-popup-panel');
  const nav = document.getElementById('batch-ref-navigator');
  if (!panel || !nav) return;
  batchRefPopupOpen = !batchRefPopupOpen;
  panel.style.display = batchRefPopupOpen ? 'flex' : 'none';
  nav.classList.toggle('popup-open', batchRefPopupOpen);
  if (batchRefPopupOpen) {
    renderBatchRefList();
    const inp = document.getElementById('batch-ref-search-input');
    if (inp) setTimeout(() => { try { inp.focus(); } catch (_e) {} }, 40);
  }
}

function closeBatchRefPopup() {
  const panel = document.getElementById('batch-ref-popup-panel');
  const nav = document.getElementById('batch-ref-navigator');
  batchRefPopupOpen = false;
  if (panel) panel.style.display = 'none';
  if (nav) nav.classList.remove('popup-open');
}

function filterBatchRefList(val) {
  batchRefSearchQuery = String(val || '');
  renderBatchRefList();
}

function selectBatchReference(idx) {
  if (!Array.isArray(batchReferenceItems) || idx < 0 || idx >= batchReferenceItems.length) return;
  const item = batchReferenceItems[idx];
  if (!item || !item.valid || !Number.isFinite(Number(item.lat)) || !Number.isFinite(Number(item.lon))) {
    showToast('<i class="fa-solid fa-triangle-exclamation" style="color:#f59e0b; margin-right:5px;"></i>รายการนี้ไม่มีพิกัดที่ถูกต้องบนแผนที่');
    return;
  }

  batchRefCurrentIdx = idx;
  closeBatchRefPopup();
  updateBatchRefBarUi();

  // Clear conflicting location/project/search states so radius + type focus cleanly on this reference asset
  currentSelectedProv = '';
  currentSelectedDist = '';
  currentSelectedSubdist = '';
  if (inMapFilterState) {
    if (inMapFilterState.samProjects) inMapFilterState.samProjects.clear();
    if (inMapFilterState.samProjectsNorm) inMapFilterState.samProjectsNorm.clear();
    inMapFilterState.samProject = '';
    if (batchRefLockType && item.prop_type) {
      inMapFilterState.types = new Set([item.prop_type]);
    }
  }
  _syncTypeFilterChipsDom();
  try { syncComboboxInputs(); } catch (_e) {}

  const propInp = document.getElementById('inmap-prop-search-input');
  const propClr = document.getElementById('inmap-clear-search-btn');
  if (propInp) propInp.value = '';
  if (propClr) propClr.style.display = 'none';
  closePropertyCard();

  currentRefId = '';
  currentPriceCenterId = '';
  currentRefProp = {
    _id: item.code || `REF-${idx + 1}`,
    _company: item.company || 'ทรัพย์อ้างอิง',
    _type: item.prop_type || 'อื่นๆ',
    _project: item.project || '',
    _price: item.price || 0,
  };

  setReferencePoint(Number(item.lon), Number(item.lat), true, false);
  applyInMapFilters(true);

  const typesArr = (inMapFilterState && inMapFilterState.types) ? Array.from(inMapFilterState.types) : [];
  triggerStreamlitSync({
    prov: '',
    dist: '',
    subdist: '',
    proj: '',
    proj_list: [],
    id: '',
    price_center_id: '',
    lat: Number(item.lat),
    lon: Number(item.lon),
    radius: currentRadiusKm || 5.0,
    mode: 'radius',
    types: typesArr,
    batch_ref: {
      code: item.code,
      company: item.company,
      prop_type: item.prop_type,
      project: item.project,
      price: item.price,
      lat: Number(item.lat),
      lon: Number(item.lon),
    },
    compare_active: true,
  }, 0);

  const typeMsg = (batchRefLockType && item.prop_type) ? ` • กรองประเภท: <b>${escapeHtml(item.prop_type)}</b>` : '';
  showToast(`<i class="fa-solid fa-crosshairs" style="color:#10b981; margin-right:5px;"></i>ทรัพย์อ้างอิง #${item.idx}: <b>${escapeHtml(item.code)}</b>${typeMsg}`);
}

function navigateBatchReference(delta) {
  const n = batchReferenceItems.length;
  if (n === 0) return;
  const step = delta >= 0 ? 1 : -1;
  let pos = batchRefCurrentIdx;
  for (let tries = 0; tries < n; tries++) {
    if (pos < 0) {
      pos = step > 0 ? 0 : n - 1;
    } else {
      pos = (pos + step + n) % n;
    }
    if (batchReferenceItems[pos] && batchReferenceItems[pos].valid) {
      selectBatchReference(pos);
      return;
    }
  }
  showToast('<i class="fa-solid fa-triangle-exclamation" style="color:#f59e0b; margin-right:5px;"></i>ไม่พบรายการที่มีพิกัดถูกต้องในไฟล์นำเข้า');
}

function toggleBatchRefTypeLock() {
  batchRefLockType = !batchRefLockType;
  updateBatchRefBarUi();
  if (batchRefCurrentIdx >= 0 && batchRefCurrentIdx < batchReferenceItems.length) {
    const item = batchReferenceItems[batchRefCurrentIdx];
    if (inMapFilterState) {
      if (batchRefLockType && item && item.prop_type) {
        inMapFilterState.types = new Set([item.prop_type]);
      } else {
        inMapFilterState.types.clear();
      }
    }
    _syncTypeFilterChipsDom();
    applyInMapFilters(false);
    showToast(
      batchRefLockType
        ? `<i class="fa-solid fa-lock" style="color:#10b981; margin-right:5px;"></i>ล็อกประเภททรัพย์: <b>${escapeHtml(item.prop_type || '-')}</b>`
        : '<i class="fa-solid fa-lock-open" style="color:#64748b; margin-right:5px;"></i>ปลดล็อกประเภททรัพย์ (แสดงทุกประเภทในรัศมี)'
    );
  }
}

function setBatchReferenceItems(items, radiusKm) {
  batchReferenceItems = Array.isArray(items) ? items : [];
  if (batchRefCurrentIdx >= batchReferenceItems.length) {
    batchRefCurrentIdx = -1;
  }
  batchRefSearchQuery = '';
  const inp = document.getElementById('batch-ref-search-input');
  if (inp) inp.value = '';
  updateBatchRefBarUi();
  if (batchRefPopupOpen) renderBatchRefList();
}

window.setBatchReferenceItems = setBatchReferenceItems;
window.toggleBatchRefPopup = toggleBatchRefPopup;
window.closeBatchRefPopup = closeBatchRefPopup;
window.filterBatchRefList = filterBatchRefList;
window.selectBatchReference = selectBatchReference;
window.navigateBatchReference = navigateBatchReference;
window.toggleBatchRefTypeLock = toggleBatchRefTypeLock;

document.addEventListener('click', function(ev) {
  if (!batchRefPopupOpen) return;
  const nav = document.getElementById('batch-ref-navigator');
  if (nav && !nav.contains(ev.target)) {
    closeBatchRefPopup();
  }
});

window.addEventListener('message', function(ev) {
  const expectedOrigin = (window.NovaMapCache && typeof window.NovaMapCache.getEffectiveSelfOrigin === 'function')
    ? window.NovaMapCache.getEffectiveSelfOrigin()
    : ((window.location && window.location.origin && window.location.origin !== 'null')
      ? window.location.origin
      : ((typeof window.origin === 'string' && window.origin !== 'null') ? window.origin : ''));
  if (!ev || !expectedOrigin || ev.origin !== expectedOrigin || ev.source !== window.parent) return;
  if (ev.data && ev.data.action === 'clear_price_center') {
    clearPriceCenter();
  } else if (ev.data && ev.data.action === 'set_batch_refs') {
    setBatchReferenceItems(ev.data.items || [], ev.data.radius_km);
  }
});

function getTileUrls(styleName) {
  if (styleName === 'google_hybrid') {
    return [
      'https://mt0.google.com/vt?lyrs=y&hl=th&x={x}&y={y}&z={z}',
      'https://mt1.google.com/vt?lyrs=y&hl=th&x={x}&y={y}&z={z}',
      'https://mt2.google.com/vt?lyrs=y&hl=th&x={x}&y={y}&z={z}',
      'https://mt3.google.com/vt?lyrs=y&hl=th&x={x}&y={y}&z={z}'
    ];
  } else if (styleName === 'google_roadmap') {
    return [
      'https://mt0.google.com/vt?lyrs=m&hl=th&x={x}&y={y}&z={z}',
      'https://mt1.google.com/vt?lyrs=m&hl=th&x={x}&y={y}&z={z}',
      'https://mt2.google.com/vt?lyrs=m&hl=th&x={x}&y={y}&z={z}',
      'https://mt3.google.com/vt?lyrs=m&hl=th&x={x}&y={y}&z={z}'
    ];
  } else if (styleName === 'satellite') {
    return [
      'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'
    ];
  } else if (styleName === 'osm') {
    return [
      'https://tile.openstreetmap.org/{z}/{x}/{y}.png'
    ];
  } else {
    // voyager → ESRI World Street Map (free, no API key)
    return [
      'https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}'
    ];
  }
}

function updateActiveButtons(styleName) {
  document.querySelectorAll('.style-btn').forEach(btn => btn.classList.remove('active'));
  const labelMap = {
    google_hybrid: { text: 'Google Hybrid (ดาวเทียม+ชื่อถนน)', icon: 'fa-earth-asia', btnId: 'btn-google-hybrid' },
    google_roadmap: { text: 'Google Maps', icon: 'fa-map-location-dot', btnId: 'btn-google-roadmap' },
    osm: { text: 'OpenStreetMap', icon: 'fa-globe', btnId: 'btn-osm' },
    satellite: { text: 'ภาพดาวเทียมล้วน ESRI', icon: 'fa-satellite', btnId: 'btn-satellite' },
    voyager: { text: 'แผนที่ถนน ESRI', icon: 'fa-road', btnId: 'btn-voyager' }
  };
  const info = labelMap[styleName] || labelMap.google_hybrid;
  const triggerLabel = document.getElementById('current-style-label');
  const triggerIcon = document.getElementById('current-style-icon');
  if (triggerLabel) triggerLabel.innerText = info.text;
  if (triggerIcon) triggerIcon.className = `fa-solid ${info.icon} style-trigger-icon-base`;

  const activeBtn = document.getElementById(info.btnId);
  if (activeBtn) activeBtn.classList.add('active');
}

let _tileErrorCount = 0;
let _tileFallbackTriggered = false;
const _decodedTileBitmapCache = new Map();
let _instantBackdropActive = false;
let _deckFirstViewportLoaded = false;
let _userInteractedWithMap = false;
let _instantBackdropSafetyTimer = null;
let _instantBackdropWakeTimer = null;

function dismissInstantMapBackdrop() {
  _instantBackdropActive = false;
  if (_instantBackdropSafetyTimer) {
    clearTimeout(_instantBackdropSafetyTimer);
    _instantBackdropSafetyTimer = null;
  }
  if (_instantBackdropWakeTimer) {
    clearTimeout(_instantBackdropWakeTimer);
    _instantBackdropWakeTimer = null;
  }
  try {
    const wrap = document.getElementById('map-instant-backdrop-wrap');
    if (wrap) wrap.style.display = 'none';
    const canvas = document.getElementById('map-instant-backdrop');
    if (canvas && (canvas.width > 1 || canvas.height > 1)) {
      canvas.width = 1;
      canvas.height = 1;
    }
  } catch (_e) {}
}

function armInstantBackdropSafetyTimer() {
  if (!_instantBackdropActive) return;
  const mapEl = document.getElementById('map');
  if (!mapEl || (mapEl.clientWidth || 0) <= 0 || (mapEl.clientHeight || 0) <= 0) return;
  if (!_instantBackdropWakeTimer) {
    _instantBackdropWakeTimer = setTimeout(() => {
      _instantBackdropWakeTimer = null;
      if (_instantBackdropActive && !_deckFirstViewportLoaded && typeof _triggerImmediateMapRedraw === 'function') {
        _triggerImmediateMapRedraw(true);
      }
    }, 1000);
  }
  if (!_instantBackdropSafetyTimer) {
    _instantBackdropSafetyTimer = setTimeout(() => {
      _instantBackdropSafetyTimer = null;
      if (!_deckFirstViewportLoaded && typeof _triggerImmediateMapRedraw === 'function') {
        _triggerImmediateMapRedraw(true);
      }
      dismissInstantMapBackdrop();
    }, 4500);
  }
}

function clearDecodedTileBitmaps() {
  try {
    _decodedTileBitmapCache.forEach((img) => {
      if (img && typeof img.close === 'function') {
        try { img.close(); } catch (_e) {}
      }
    });
    _decodedTileBitmapCache.clear();
  } catch (_e) {}
}

async function _decodeTileBlobInRealm(blob) {
  if (!blob) return null;
  if (typeof window.createImageBitmap === 'function') {
    try {
      return await window.createImageBitmap(blob);
    } catch (_e) {}
  }
  return await new Promise((resolve, reject) => {
    const objUrl = URL.createObjectURL(blob);
    const img = new window.Image();
    img.onload = () => {
      URL.revokeObjectURL(objUrl);
      resolve(img);
    };
    img.onerror = (err) => {
      URL.revokeObjectURL(objUrl);
      reject(err || new Error('Tile image decode failed'));
    };
    img.src = objUrl;
  });
}

async function prepareInstantMapBackdropAndPredecode(styleName, viewState) {
  try {
    if (!window.NovaMapCache || typeof window.NovaMapCache.getParentTileCache !== 'function') return;
    // Skip extra 2D backdrop canvas + 52 simultaneous ImageBitmap GPU allocations on iPadOS/iOS WebKit
    // to keep total tab GPU/RAM safely below Safari's Jetsam limit.
    if (typeof window.NovaMapCache.isIOSOrIPadOS === 'function' && window.NovaMapCache.isIOSOrIPadOS()) return;
    if (!viewState || styleName !== 'google_hybrid') return;

    const store = window.NovaMapCache.getParentTileCache();
    if (!store || !store.blobs) return;

    // Wait briefly for any still-inflight Welcome preload tiles for this style
    if (store.inflight && store.inflight.size > 0) {
      const pending = [];
      store.inflight.forEach((p, k) => {
        if (String(k).startsWith(styleName + '/')) pending.push(p.catch(() => null));
      });
      if (pending.length > 0) {
        await Promise.race([
          Promise.all(pending),
          new Promise((r) => setTimeout(r, 800))
        ]);
      }
    }

    const prefixZ6 = styleName + '/6/';
    const prefixZ5 = styleName + '/5/';
    const z6Entries = [];
    const z5Entries = [];

    store.blobs.forEach((blob, key) => {
      if (!blob) return;
      if (key.startsWith(prefixZ6)) {
        const parts = key.split('/');
        const x = parseInt(parts[2], 10);
        const y = parseInt(parts[3], 10);
        if (Number.isInteger(x) && Number.isInteger(y)) z6Entries.push({ key, x, y, blob });
      } else if (key.startsWith(prefixZ5)) {
        const parts = key.split('/');
        const x = parseInt(parts[2], 10);
        const y = parseInt(parts[3], 10);
        if (Number.isInteger(x) && Number.isInteger(y)) z5Entries.push({ key, x, y, blob });
      }
    });

    if (z6Entries.length === 0) return;

    // Decode all cached z=6 and z=5 tiles into Tab 2's own JS realm in parallel
    const allEntries = z6Entries.concat(z5Entries);
    const decodedList = await Promise.all(
      allEntries.map(async (item) => {
        try {
          const bmp = await _decodeTileBlobInRealm(item.blob);
          return bmp ? { key: item.key, x: item.x, y: item.y, isZ6: item.key.startsWith(prefixZ6), bmp } : null;
        } catch (_e) {
          return null;
        }
      })
    );

    const decodedZ6 = [];
    for (let i = 0; i < decodedList.length; i++) {
      const d = decodedList[i];
      if (!d) continue;
      if (d.isZ6) decodedZ6.push(d);
      if (!_decodedTileBitmapCache.has(d.key)) {
        _decodedTileBitmapCache.set(d.key, d.bmp);
      } else if (d.bmp && typeof d.bmp.close === 'function') {
        try { d.bmp.close(); } catch (_e) {}
      }
    }

    // Only stitch & show the instant 2D backdrop for the default Thailand overview view before first live WebGL render
    const isDefaultOverview = (
      Math.abs((viewState.longitude || 0) - 100.5) < 0.01 &&
      Math.abs((viewState.latitude || 0) - 13.5) < 0.01 &&
      Math.abs((viewState.zoom || 0) - 5.2) < 0.01 &&
      (!boundaryGeoJson || !boundaryGeoJson.features || boundaryGeoJson.features.length === 0)
    );
    if (!isDefaultOverview || _deckFirstViewportLoaded || _userInteractedWithMap || decodedZ6.length < 4) {
      return;
    }

    const wrap = document.getElementById('map-instant-backdrop-wrap');
    const canvas = document.getElementById('map-instant-backdrop');
    if (!wrap || !canvas) return;

    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    for (let i = 0; i < decodedZ6.length; i++) {
      const t = decodedZ6[i];
      if (t.x < minX) minX = t.x;
      if (t.x > maxX) maxX = t.x;
      if (t.y < minY) minY = t.y;
      if (t.y > maxY) maxY = t.y;
    }

    const cols = maxX - minX + 1;
    const rows = maxY - minY + 1;
    if (cols <= 0 || rows <= 0 || cols > 16 || rows > 12) return;

    canvas.width = cols * 256;
    canvas.height = rows * 256;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    for (let i = 0; i < decodedZ6.length; i++) {
      const t = decodedZ6[i];
      const imgObj = _decodedTileBitmapCache.get(t.key) || t.bmp;
      if (imgObj) {
        try {
          ctx.drawImage(imgObj, (t.x - minX) * 256, (t.y - minY) * 256, 256, 256);
        } catch (_e) {}
      }
    }

    // Align stitched z=6 grid pixel-for-pixel with Deck.gl WebMercatorViewport at (lon, lat, zoom)
    const lon = viewState.longitude;
    const lat = viewState.latitude;
    const zoom = viewState.zoom;
    const n = 64; // 2^6
    const cx = ((lon + 180) / 360) * n;
    const latRad = (lat * Math.PI) / 180;
    const cy = ((1 - Math.log(Math.tan(latRad) + 1 / Math.cos(latRad)) / Math.PI) / 2) * n;
    const tileScreenPx = 256 * Math.pow(2, zoom + 1 - 6);
    const centerOffsetX = (cx - minX) * tileScreenPx;
    const centerOffsetY = (cy - minY) * tileScreenPx;

    canvas.style.position = 'absolute';
    canvas.style.left = '50%';
    canvas.style.top = '50%';
    canvas.style.width = (cols * tileScreenPx) + 'px';
    canvas.style.height = (rows * tileScreenPx) + 'px';
    canvas.style.transform = `translate(${-centerOffsetX}px, ${-centerOffsetY}px)`;
    canvas.style.display = 'block';

    if (!_deckFirstViewportLoaded && !_userInteractedWithMap) {
      wrap.style.display = 'block';
      _instantBackdropActive = true;
      const mapEl = document.getElementById('map');
      if (mapEl && mapEl.clientWidth > 0 && mapEl.clientHeight > 0) {
        armInstantBackdropSafetyTimer();
      }
    }
  } catch (_e) {}
}

function createBasemapLayer(styleName) {
  const isGoogle = styleName && styleName.startsWith('google_');
  const isIOS = !!(window.NovaMapCache && typeof window.NovaMapCache.isIOSOrIPadOS === 'function' && window.NovaMapCache.isIOSOrIPadOS());
  const layerOpts = {
    id: `basemap-tile-layer-${styleName}`,
    data: getTileUrls(styleName),
    minZoom: 0,
    maxZoom: isGoogle ? 20 : 19,
    tileSize: 256,
    maxRequests: isIOS ? 8 : 64,
    maxCacheSize: isIOS ? 64 : 300,
    refinementStrategy: 'best-available',
    onViewportLoad: (tiles) => {
      const mapEl = document.getElementById('map');
      const hasLoadedTiles = Array.isArray(tiles) ? tiles.length > 0 : true;
      if (hasLoadedTiles && mapEl && mapEl.clientWidth > 0 && mapEl.clientHeight > 0) {
        _deckFirstViewportLoaded = true;
        if (_instantBackdropActive) {
          // Wait 2 paint frames so WebGL composites all loaded tiles before removing the pixel-identical backdrop
          requestAnimationFrame(() => requestAnimationFrame(() => dismissInstantMapBackdrop()));
        }
      }
    },
    onTileError: (err) => {
      if (err && err.name === 'AbortError') return;
      _tileErrorCount++;
      if (!_tileFallbackTriggered && _tileErrorCount >= 6) {
        _tileFallbackTriggered = true;
        if (currentStyle !== 'osm') {
          showToast('<i class="fa-solid fa-triangle-exclamation" style="color:#f59e0b; margin-right:6px;"></i>ไม่สามารถโหลดแผนที่พื้นหลังได้ กำลังสลับไปยัง OpenStreetMap');
          setTimeout(() => { setBasemapStyle('osm'); }, 50);
        }
      }
    },
    renderSubLayers: props => {
      const { bbox: {west, south, east, north} } = props.tile;
      return new deck.BitmapLayer(props, {
        data: null,
        image: props.tile.data,
        bounds: [west, south, east, north]
      });
    }
  };

  if (window.NovaMapCache && typeof window.NovaMapCache.fetchAndCacheTileBlob === 'function') {
    layerOpts.getTileData = async (tile) => {
      const idx = (tile && tile.index) ? tile.index : tile;
      if (!idx || !Number.isInteger(idx.x) || !Number.isInteger(idx.y) || !Number.isInteger(idx.z)) {
        return null;
      }
      const key = window.NovaMapCache.getTileCacheKey(styleName, idx.z, idx.x, idx.y);
      const predecoded = _decodedTileBitmapCache.get(key);
      if (predecoded) {
        // Transfer single ownership to DeckGL so tile unload cannot affect other consumers
        _decodedTileBitmapCache.delete(key);
        const isDetachedBitmap = (typeof ImageBitmap !== 'undefined' && predecoded instanceof ImageBitmap && (predecoded.width === 0 || predecoded.height === 0));
        if (!isDetachedBitmap) {
          return predecoded;
        }
      }
      const blob = await window.NovaMapCache.fetchAndCacheTileBlob(
        styleName,
        idx.z,
        idx.x,
        idx.y,
        tile && tile.url ? tile.url : null,
        tile && tile.signal ? tile.signal : null
      );
      return await _decodeTileBlobInRealm(blob);
    };
  }

  return new deck.TileLayer(layerOpts);
}

function handlePointClick(info) {
  if (info.object) {
    showPropertyCard(info.object, true);
  }
}

function getMapTooltip(info) {
  try {
    if (!info || !info.object) {
      return null;
    }
    if (info.layer && info.layer.id !== 'point-icons') {
      return null;
    }

    // Ensure .deck-tooltip is reparented to document.body so it floats above SVG boundary layers
    setTimeout(function() {
      var tt = document.querySelector('.deck-tooltip');
      if (tt && tt.parentElement && tt.parentElement !== document.body) {
        document.body.appendChild(tt);
      }
    }, 0);
    const d = (info.object && info.object.item) ? info.object.item : info.object;
    const coordKey = getCoordKey(d);
    const stack = (currentCoordMap && currentCoordMap.get(coordKey)) || [d];
    const hasOverlap = stack.length > 1;

    let overlapHtml = '';
    const fmtUnitInt = v => `฿${Math.round(v).toLocaleString()}`;
    if (hasOverlap) {
      const coCounts = Object.create(null);
      let minP = Infinity, maxP = -Infinity;
      let minPuw = Infinity, maxPuw = -Infinity;
      let minPum = Infinity, maxPum = -Infinity;
      for (let i = 0; i < stack.length; i++) {
        const item = stack[i];
        const co = item._company || 'ไม่ระบุ';
        coCounts[co] = (coCounts[co] || 0) + 1;
        const p = Number(item._price) || 0;
        if (p > 0) {
          if (p < minP) minP = p;
          if (p > maxP) maxP = p;
        }
        const puw = Number(item._puw) || 0;
        if (puw > 0) {
          if (puw < minPuw) minPuw = puw;
          if (puw > maxPuw) maxPuw = puw;
        }
        const pum = Number(item._pum) || 0;
        if (pum > 0) {
          if (pum < minPum) minPum = pum;
          if (pum > maxPum) maxPum = pum;
        }
      }
      const numCo = Object.keys(coCounts).length;
      const coSummary = Object.entries(coCounts).map(([co, c]) => `${escapeHtml(co)}: ${c}`).join(', ');
      const priceRange = (minP !== Infinity && maxP !== -Infinity)
        ? (minP === maxP ? `฿${formatPriceShort(minP)}` : `฿${formatPriceShort(minP)} - ฿${formatPriceShort(maxP)}`)
        : 'ไม่ระบุราคา';

      const unitRangeParts = [];
      if (minPuw !== Infinity && maxPuw !== -Infinity) {
        unitRangeParts.push(minPuw === maxPuw ? `${fmtUnitInt(minPuw)}/ตร.ว.` : `${fmtUnitInt(minPuw)} - ${fmtUnitInt(maxPuw)}/ตร.ว.`);
      }
      if (minPum !== Infinity && maxPum !== -Infinity) {
        unitRangeParts.push(minPum === maxPum ? `${fmtUnitInt(minPum)}/ตร.ม.` : `${fmtUnitInt(minPum)} - ${fmtUnitInt(maxPum)}/ตร.ม.`);
      }
      const unitRangeHtml = unitRangeParts.length > 0
        ? `<div style="font-size:10px; color:#fef08a; margin-top:2px; line-height:1.3;"><b>ช่วงราคา/หน่วย:</b> ${escapeHtml(unitRangeParts.join(' • '))}</div>`
        : '';

      overlapHtml = `
        <div style="background: linear-gradient(135deg, rgba(14,165,233,0.25), rgba(2,132,199,0.35)); border: 1px solid rgba(56,189,248,0.45); border-radius: 8px; padding: 6px 9px; margin-bottom: 6px;">
          <div style="display:flex; justify-content:space-between; align-items:center; font-size:11.5px; font-weight:800; color:#7dd3fc;">
            <span><i class="fa-solid fa-layer-group" style="color:#38bdf8; margin-right:4px;"></i>พิกัดร่วม ${stack.length.toLocaleString()} รายการ (${numCo} เจ้า)</span>
            <span style="color:#fef08a; font-size:11px;">${escapeHtml(priceRange)}</span>
          </div>
          <div style="font-size:10px; color:#e0f2fe; margin-top:3px; line-height:1.3;">
            <b>เจ้าของ:</b> ${coSummary}
          </div>
          ${unitRangeHtml}
        </div>
      `;
    }

    const topItem = (stack && stack.length > 0) ? stack[0] : d;
    if (!topItem._detailLoaded) {
      scheduleHoverDetailPrefetch(topItem);
    }
    const title = escapeHtml(_getDisplayItemTitle(topItem));
    const company = escapeHtml(topItem._company || '-');
    const id = escapeHtml(topItem._id || '-');
    const price = escapeHtml(topItem._price_str || 'ไม่ระบุราคา');
    const prov = escapeHtml(topItem._prov || '-');
    const type = escapeHtml(topItem._type || '-');

    const formatUnitPriceRow = (unitPrice, areaVal, label, unitSuffix, iconCls, color) => {
      const up = Number(unitPrice) || 0;
      if (up <= 0) return '';
      const ar = Number(areaVal) || 0;
      const areaText = ar > 0
        ? ` <span style="color: #94a3b8; font-weight: 400;">(${ar.toLocaleString(undefined, {minimumFractionDigits: 1, maximumFractionDigits: 1})} ${unitSuffix})</span>`
        : '';
      return `
        <span style="color: ${color}; font-weight: 600;"><i class="${iconCls}" style="margin-right:4px;"></i>${label}:</span>
        <b style="color: ${color};">${fmtUnitInt(up)} / ${unitSuffix}${areaText}</b>
      `;
    };
    const puwRowHtml = formatUnitPriceRow(topItem._puw, topItem._sqw, 'ราคา/ตร.ว.', 'ตร.ว.', 'fa-solid fa-chart-line', '#34d399');
    const pumRowHtml = formatUnitPriceRow(topItem._pum, topItem._sqm, 'ราคา/ตร.ม.', 'ตร.ม.', 'fa-solid fa-ruler-combined', '#7dd3fc');

    const isCentroid = (String(topItem._centroid) === '1');
    const centroidHtml = isCentroid
      ? `<div style="background:#fffbeb; border:1px solid #fde68a; border-radius:6px; padding:3px 8px; margin-bottom:5px; font-size:10.5px; color:#92400e; font-weight:700; display:flex; align-items:center; gap:4px;"><i class="fa-solid fa-triangle-exclamation" style="color:#d97706;"></i> พิกัดโดยประมาณ (กึ่งกลางตำบล/อำเภอ)</div>`
      : '';

    const isLed = String(topItem._company || '').startsWith('LED');
    const plaintiff = isLed ? String(topItem._plaintiff || '').trim() : '';
    const plainHtml = (plaintiff && plaintiff !== '-' && plaintiff !== 'None' && plaintiff !== 'nan' && plaintiff !== 'null')
      ? `<span style="color: #94a3b8;"><i class="fa-solid fa-user-shield" style="margin-right:4px;"></i>โจทก์:</span><span style="color: #e2e8f0;">${escapeHtml(plaintiff)}</span>`
      : '';

    const clickTip = hasOverlap
      ? `<i class="fa-solid fa-arrow-pointer" style="margin-right:4px;"></i>คลิกเพื่อเปิดดูและกดเลื่อนดูครบทั้ง ${stack.length.toLocaleString()} รายการ`
      : `<i class="fa-solid fa-arrow-pointer" style="margin-right:4px;"></i>คลิกที่จุดเพื่อดูรายละเอียดและเปิดลิงก์ประกาศ`;

    return {
      html: `
        <div style="font-family: 'Noto Sans Thai', 'Inter', sans-serif; font-size: 12px; line-height: 1.5; color: #f8fafc; padding: 2px;">
          ${overlapHtml}
          ${centroidHtml}
          <div style="font-weight: 700; font-size: 13px; margin-bottom: 5px; color: #ffffff; border-bottom: 1px solid rgba(255,255,255,0.15); padding-bottom: 4px;">
            ${title}
          </div>
          <div style="display: grid; grid-template-columns: auto 1fr; gap: 3px 8px; margin-top: 4px;">
            <span style="color: #94a3b8;"><i class="fa-solid fa-building" style="margin-right:4px;"></i>บริษัท:</span>
            <b style="color: #ffffff;">${company}</b>
            <span style="color: #94a3b8;"><i class="fa-solid fa-hashtag" style="margin-right:4px;"></i>รหัสทรัพย์:</span>
            <b style="color: #ffffff;">${id}</b>
            <span style="color: #38bdf8; font-weight: 600;"><i class="fa-solid fa-tag" style="margin-right:4px;"></i>ราคา:</span>
            <b style="color: #38bdf8;">${price}</b>
            ${puwRowHtml}
            ${pumRowHtml}
            <span style="color: #94a3b8;"><i class="fa-solid fa-location-dot" style="margin-right:4px;"></i>จังหวัด:</span>
            <span style="color: #e2e8f0;">${prov}</span>
            <span style="color: #94a3b8;"><i class="fa-solid fa-house-chimney" style="margin-right:4px;"></i>ประเภท:</span>
            <span style="color: #e2e8f0;">${type}</span>
            ${plainHtml}
          </div>
          <div style="margin-top: 7px; padding-top: 5px; border-top: 1px dashed rgba(255,255,255,0.2); font-size: 10.5px; color: #38bdf8; font-weight: 600;">
            ${clickTip}
          </div>
        </div>
      `,
      style: {
        backgroundColor: 'rgba(15, 23, 42, 0.96)',
        backdropFilter: 'blur(10px)',
        WebkitBackdropFilter: 'blur(10px)',
        color: '#ffffff',
        borderRadius: '10px',
        border: '1px solid rgba(255, 255, 255, 0.18)',
        boxShadow: '0 10px 30px rgba(0, 0, 0, 0.45)',
        padding: '10px 14px',
        maxWidth: '345px',
        zIndex: '999999',
        pointerEvents: 'none'
      }
    };
  } catch (err) {
    console.warn('getMapTooltip error:', err);
    return null;
  }
}

const PROP_TYPE_COLORS = {
  "ห้องชุดพักอาศัย": [139, 92, 246],
  "คอนโด": [139, 92, 246],
  "คอนโดมิเนียม": [139, 92, 246],
  "อาคารชุดพักอาศัย": [139, 92, 246],
  "บ้านเดี่ยว": [37, 99, 235],
  "ที่ดินพร้อมสิ่งปลูกสร้าง": [249, 115, 22],
  "ที่ดินเปล่า": [139, 69, 19],
  "ที่ดิน": [139, 69, 19],
  "ทาวน์เฮ้าส์": [245, 158, 11],
  "ทาวน์โฮม": [245, 158, 11],
  "อาคารพาณิชย์": [244, 63, 94],
  "วิลล่า": [236, 72, 153],
  "บ้านแฝด": [14, 165, 233],
  "โรงงาน/โกดัง": [6, 182, 212],
  "อพาร์ทเมนท์": [168, 85, 247],
  "อาคารสำนักงาน": [100, 116, 139],
  "โรงแรม/รีสอร์ท": [234, 179, 8],
  "ห้องชุดพาณิชยกรรม/สำนักงาน": [14, 165, 233],
  "โฮมออฟฟิศ": [79, 70, 229],
  "ปั๊มน้ำมัน": [217, 119, 6],
  "โชว์รูม": [249, 115, 22],
  "สังหาริมทรัพย์": [120, 113, 108],
  "เพิงอเนกประสงค์": [161, 98, 7],
  "สิ่งปลูกสร้าง": [100, 116, 139],
  "ฟาร์ม": [34, 197, 94],
  "โรงเรียน": [234, 88, 12],
  "อื่นๆ": [100, 116, 139]
};

function getCompanyLogoUri(co) {
  if (!companyLogos || !co) return null;
  const _hasOwn = Object.prototype.hasOwnProperty;
  if (_hasOwn.call(companyLogos, co)) return companyLogos[co];
  const lower = String(co).toLowerCase().replace(/[\s\-_]+/g, '');
  if (_hasOwn.call(companyLogos, lower)) return companyLogos[lower];
  const upper = String(co).toUpperCase().replace(/[\s\-_]+/g, '');
  if (_hasOwn.call(companyLogos, upper)) return companyLogos[upper];

  for (const [k, v] of Object.entries(companyLogos)) {
    const cleanK = String(k).toLowerCase().replace(/[\s\-_]+/g, '').replace('logo', '');
    if (cleanK === lower || lower.includes(cleanK) || cleanK.includes(lower)) {
      return v;
    }
  }
  return null;
}

const propTypeIcons = {
  "ห้องชุดพักอาศัย": '<i class="fa-solid fa-building"></i>',
  "คอนโด": '<i class="fa-solid fa-building"></i>',
  "คอนโดมิเนียม": '<i class="fa-solid fa-building"></i>',
  "อาคารชุดพักอาศัย": '<i class="fa-solid fa-building"></i>',
  "บ้านเดี่ยว": '<i class="fa-solid fa-house"></i>',
  "ที่ดินพร้อมสิ่งปลูกสร้าง": '<i class="fa-solid fa-tree-city"></i>',
  "ที่ดินเปล่า": '<i class="fa-solid fa-tree"></i>',
  "ที่ดิน": '<i class="fa-solid fa-tree"></i>',
  "ทาวน์เฮ้าส์": '<svg viewBox="0 0 64 48" width="13" height="10" fill="currentColor" style="display:inline-block;"><polygon points="16,0 0,18 32,18"/><rect x="4" y="18" width="24" height="30"/><polygon points="48,0 32,18 64,18"/><rect x="36" y="18" width="24" height="30"/></svg>',
  "ทาวน์โฮม": '<svg viewBox="0 0 64 48" width="13" height="10" fill="currentColor" style="display:inline-block;"><polygon points="16,0 0,18 32,18"/><rect x="4" y="18" width="24" height="30"/><polygon points="48,0 32,18 64,18"/><rect x="36" y="18" width="24" height="30"/></svg>',
  "อาคารพาณิชย์": '<i class="fa-solid fa-store"></i>',
  "วิลล่า": '<i class="fa-solid fa-gem"></i>',
  "บ้านแฝด": '<i class="fa-solid fa-house-chimney-window"></i>',
  "โรงงาน/โกดัง": '<i class="fa-solid fa-industry"></i>',
  "อพาร์ทเมนท์": '<i class="fa-solid fa-hotel"></i>',
  "อาคารสำนักงาน": '<i class="fa-solid fa-briefcase"></i>',
  "โรงแรม/รีสอร์ท": '<i class="fa-solid fa-umbrella-beach"></i>',
  "ห้องชุดพาณิชยกรรม/สำนักงาน": '<i class="fa-solid fa-building"></i>',
  "โฮมออฟฟิศ": '<i class="fa-solid fa-laptop-house"></i>',
  "ปั๊มน้ำมัน": '<i class="fa-solid fa-gas-pump"></i>',
  "โชว์รูม": '<i class="fa-solid fa-car"></i>',
  "สังหาริมทรัพย์": '<i class="fa-solid fa-box"></i>',
  "เพิงอเนกประสงค์": '<i class="fa-solid fa-warehouse"></i>',
  "สิ่งปลูกสร้าง": '<i class="fa-solid fa-building"></i>',
  "ฟาร์ม": '<i class="fa-solid fa-wheat-awn"></i>',
  "โรงเรียน": '<i class="fa-solid fa-school"></i>',
  "อื่นๆ": '<i class="fa-solid fa-location-dot"></i>'
};
