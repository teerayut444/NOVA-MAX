// =========================================================================
// REALTIME SYNCHRONIZATION WITH TOP KPI CARDS (Parent Window Streamlit)
// =========================================================================
function getParentKpiElements() {
  try {
    if (!window.parent || !window.parent.document) return null;
    const pdoc = window.parent.document;
    const container = pdoc.querySelector('.floating-kpi-container');
    if (!container) return null;
    return {
      doc: pdoc,
      container: container,
      countCard: pdoc.getElementById('kpi-card-count') || container.children[0],
      totalValCard: pdoc.getElementById('kpi-card-total-val') || container.children[1],
      minPriceCard: pdoc.getElementById('kpi-card-min-price') || container.children[2],
      medianPriceCard: pdoc.getElementById('kpi-card-median-price') || container.children[3],
      meanPriceCard: pdoc.getElementById('kpi-card-mean-price') || container.children[4],
      maxPriceCard: pdoc.getElementById('kpi-card-max-price') || container.children[5],
      sdPriceCard: pdoc.getElementById('kpi-card-sd-price') || container.children[6],
    };
  } catch(e) {
    return null;
  }
}

function formatKpiPrice(val) {
  if (!val || isNaN(val) || val <= 0) return '฿0';
  if (val >= 1e9) {
    const num = (val / 1e9).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    return '฿' + num + 'B';
  } else if (val >= 1e6) {
    const num = (val / 1e6).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    return '฿' + num + 'M';
  } else if (val >= 1e3) {
    const num = (val / 1e3).toLocaleString('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
    return '฿' + num + 'K';
  } else {
    return '฿' + Math.round(val).toLocaleString('en-US');
  }
}

function calculateKpiStats(data) {
  if (!data || data.length === 0) {
    return { count: 0, totalVal: 0, minPrice: 0, medianPrice: 0, meanPrice: 0, maxPrice: 0, sdPrice: 0 };
  }
  const count = data.length;
  const prices = [];
  let totalVal = 0;
  for (let i = 0; i < count; i++) {
    const p = data[i]._price;
    if (p && !isNaN(p) && p > 0) {
      prices.push(p);
      totalVal += p;
    }
  }

  if (prices.length === 0) {
    return { count, totalVal: 0, minPrice: 0, medianPrice: 0, meanPrice: 0, maxPrice: 0, sdPrice: 0 };
  }

  prices.sort((a, b) => a - b);
  const minPrice = prices[0];
  const maxPrice = prices[prices.length - 1];
  const meanPrice = totalVal / prices.length;
  const mid = Math.floor(prices.length / 2);
  const medianPrice = (prices.length % 2 !== 0) ? prices[mid] : ((prices[mid - 1] + prices[mid]) / 2);

  let sdPrice = 0;
  if (prices.length > 1) {
    let sumSqDiff = 0;
    for (let i = 0; i < prices.length; i++) {
      const diff = prices[i] - meanPrice;
      sumSqDiff += diff * diff;
    }
    sdPrice = Math.sqrt(sumSqDiff / (prices.length - 1));
  }

  return { count, totalVal, minPrice, medianPrice, meanPrice, maxPrice, sdPrice };
}

function _getSharedActiveParentData() {
  const hasRef = !!referencePoint;
  const isRadiusMode = (mapPinMode === 'radius');
  const hasProv = !!(currentSelectedProv && currentSelectedProv.trim() !== '' && currentSelectedProv !== '__ALL__');
  const hasProjFilter = inMapFilterState && ((inMapFilterState.samProjects && inMapFilterState.samProjects.size > 0) || (inMapFilterState.samProject && inMapFilterState.samProject !== ''));
  if (hasProjFilter || (isRadiusMode && hasRef) || (mapPinMode === 'location' && hasProv)) {
    return (currentNearbyData && currentNearbyData.length > 0) ? currentNearbyData : [];
  }
  return (cachedData || []).filter(filterItemPasses);
}

function updateParentKpiCards(sharedActiveData) {
  const els = getParentKpiElements();
  if (!els) return;

  // Check if Tab 2 (Map) is currently active in Streamlit tablist
  try {
    const tablist = els.doc.querySelector('.st-key-main_tabs_container [role="tablist"]');
    if (tablist) {
      const tabs = tablist.querySelectorAll('[role="tab"]');
      if (tabs.length >= 2 && tabs[1].getAttribute('aria-selected') !== 'true') {
        return; // Another tab is active, do not overwrite
      }
    }
  } catch(e) {}

  let activeData = [];
  let scopeBadgeText = '';
  let subCountDesc = '';
  let subTotalDesc = '';

  const hasProjFilter = inMapFilterState && ((inMapFilterState.samProjects && inMapFilterState.samProjects.size > 0) || (inMapFilterState.samProject && inMapFilterState.samProject !== ''));
  const hasOtherFilters = inMapFilterState && (
    (inMapFilterState.companies && inMapFilterState.companies.size > 0) ||
    (inMapFilterState.types && inMapFilterState.types.size > 0) ||
    (inMapFilterState.sales && inMapFilterState.sales.size > 0) ||
    inMapFilterState.minPrice !== null || inMapFilterState.maxPrice !== null ||
    inMapFilterState.minSqw !== null || inMapFilterState.maxSqw !== null ||
    inMapFilterState.minSqm !== null || inMapFilterState.maxSqm !== null ||
    inMapFilterState.minPuw !== null || inMapFilterState.maxPuw !== null ||
    inMapFilterState.minPum !== null || inMapFilterState.maxPum !== null
  );

  if (mapPinMode === 'radius' && referencePoint) {
    activeData = Array.isArray(sharedActiveData) ? sharedActiveData : ((currentNearbyData && currentNearbyData.length > 0) ? currentNearbyData : []);
    const rDisp = formatRadiusDisplay(currentRadiusKm);
    scopeBadgeText = `รัศมี ${rDisp}`;
    subCountDesc = `ในรัศมี ${rDisp} (จุดอ้างอิง)`;
    subTotalDesc = `มูลค่าในรัศมีที่ตรวจ`;
  } else if (hasProjFilter) {
    activeData = Array.isArray(sharedActiveData) ? sharedActiveData : ((currentNearbyData && currentNearbyData.length > 0) ? currentNearbyData : []);
    const prjCount = inMapFilterState.samProjects ? inMapFilterState.samProjects.size : 1;
    const projDesc = prjCount > 1 ? `${prjCount} โครงการ` : (Array.from(inMapFilterState.samProjects)[0] || inMapFilterState.samProject);
    scopeBadgeText = projDesc;
    subCountDesc = `โครงการ: ${projDesc}`;
    subTotalDesc = `มูลค่ารวมในโครงการ`;
  } else if (mapPinMode === 'location' && currentSelectedProv && currentSelectedProv !== '__ALL__') {
    activeData = Array.isArray(sharedActiveData) ? sharedActiveData : ((currentNearbyData && currentNearbyData.length > 0) ? currentNearbyData : []);
    let locDesc = currentSelectedProv;
    if (currentSelectedDist) locDesc += ' > ' + currentSelectedDist;
    scopeBadgeText = locDesc;
    subCountDesc = `ตามทำเล: ${locDesc}`;
    subTotalDesc = `มูลค่ารวมในพื้นที่เลือก`;
  } else if (hasOtherFilters) {
    activeData = Array.isArray(sharedActiveData) ? sharedActiveData : (cachedData || []).filter(filterItemPasses);
    scopeBadgeText = 'ตัวกรองแผนที่';
    subCountDesc = `ตามตัวกรองบนแผนที่`;
    subTotalDesc = `มูลค่าทั้งหมด`;
  } else {
    // Default nationwide map scope: sync with nationwide map pins
    activeData = Array.isArray(sharedActiveData) ? sharedActiveData : (cachedData || []).filter(filterItemPasses);
    scopeBadgeText = 'ทั่วประเทศ (มีหมุด)';
    subCountDesc = 'ทรัพย์สินที่มีพิกัดบนแผนที่';
    subTotalDesc = 'มูลค่ารวมทรัพย์ที่มีหมุด';
  }

  const stats = calculateKpiStats(activeData);

  const updateCard = (card, valStr, subStr, badgeText) => {
    if (!card) return;
    card.classList.add('kpi-synced-map');
    const valEl = card.querySelector('.floating-card-value');
    if (valEl) valEl.innerText = valStr;

    let badge = card.querySelector('.kpi-scope-badge');
    if (!badge) {
      const titleEl = card.querySelector('.floating-card-title');
      if (titleEl) {
        badge = els.doc.createElement('span');
        badge.className = 'kpi-scope-badge';
        titleEl.appendChild(badge);
      }
    }
    if (badge) {
      badge.innerHTML = '<span class="kpi-live-dot"></span>';
      badge.title = 'สถานะ Live: ' + badgeText;
      badge.style.display = 'inline-flex';
    }
  };

  updateCard(els.countCard, stats.count.toLocaleString('en-US') + ' รายการ', subCountDesc, scopeBadgeText);
  updateCard(els.totalValCard, formatKpiPrice(stats.totalVal), subTotalDesc, scopeBadgeText);
  updateCard(els.minPriceCard, formatKpiPrice(stats.minPrice), 'ราคาเริ่มต้นต่ำสุด', scopeBadgeText);
  updateCard(els.medianPriceCard, formatKpiPrice(stats.medianPrice), 'ค่ามัธยฐานของกลุ่ม', scopeBadgeText);
  updateCard(els.meanPriceCard, formatKpiPrice(stats.meanPrice), 'ค่าเฉลี่ยเลขคณิต', scopeBadgeText);
  updateCard(els.maxPriceCard, formatKpiPrice(stats.maxPrice), 'มูลค่าสูงสุดในกลุ่ม', scopeBadgeText);
  updateCard(els.sdPriceCard, stats.sdPrice > 0 ? `±${formatKpiPrice(stats.sdPrice)}` : '฿0', 'การกระจายตัวของราคา', scopeBadgeText);
}

function restoreDefaultParentKpiCards() {
  const els = getParentKpiElements();
  if (!els) return;

  const restoreCard = (card) => {
    if (!card) return;
    card.classList.remove('kpi-synced-map');
    const defVal = card.getAttribute('data-default-val');
    const valEl = card.querySelector('.floating-card-value');
    const badge = card.querySelector('.kpi-scope-badge');
    if (valEl && defVal !== null) valEl.innerText = defVal;
    if (badge) {
      badge.style.display = 'none';
      badge.title = '';
    }
  };

  restoreCard(els.countCard);
  restoreCard(els.totalValCard);
  restoreCard(els.minPriceCard);
  restoreCard(els.medianPriceCard);
  restoreCard(els.meanPriceCard);
  restoreCard(els.maxPriceCard);
  restoreCard(els.sdPriceCard);
}

function updateParentFilterStatusBanner(sharedActiveData) {
  try {
    if (!window.parent || !window.parent.document) return;
    const pdoc = window.parent.document;
    const banner = pdoc.getElementById('map-active-filters-banner');
    if (!banner) return;

    const hasRef = !!referencePoint;
    const isRadiusMode = (mapPinMode === 'radius');
    const prov = (currentSelectedProv && currentSelectedProv !== '__ALL__') ? currentSelectedProv.trim() : '';
    const dist = (currentSelectedDist && currentSelectedDist !== '__ALL__') ? currentSelectedDist.trim() : '';
    const subdist = (currentSelectedSubdist && currentSelectedSubdist !== '__ALL__') ? currentSelectedSubdist.trim() : '';
    const hasLocSelection = !!(prov || dist || subdist);
    const hasProjFilter = !!(inMapFilterState && ((inMapFilterState.samProjects && inMapFilterState.samProjects.size > 0) || (inMapFilterState.samProject && inMapFilterState.samProject !== '')));
    const cosArr = (inMapFilterState && inMapFilterState.companies) ? Array.from(inMapFilterState.companies) : [];
    const onlyProj = !!(inMapFilterState && inMapFilterState.onlyWithProject);
    const isRadiusEffective = !!(hasRef && !hasProjFilter && (isRadiusMode || !hasLocSelection));
    const activeData = Array.isArray(sharedActiveData) ? sharedActiveData : _getSharedActiveParentData();

    const setChipActive = (valEl, isActive) => {
      if (!valEl) return;
      const chip = valEl.closest ? valEl.closest('.map-filter-chip') : valEl.parentElement;
      if (!chip) return;
      chip.classList.toggle('is-inactive', !isActive);
      chip.setAttribute('data-active', isActive ? 'true' : 'false');
    };

    const matchedCount = activeData.length;

    // 1. Mode Badge
    const modeBadgeEl = pdoc.getElementById('active-filter-mode-val');
    if (modeBadgeEl) {
      const modeText = (isRadiusMode && hasRef) ? "ตามรัศมี (Radius)" : "ตามทำเล (Location)";
      modeBadgeEl.innerHTML = `โหมด: <b>${modeText}</b>`;
    }

    // 2. Count
    const countEl = pdoc.getElementById('active-filter-count-val');
    if (countEl) {
      countEl.innerHTML = `<i class="fa-solid fa-layer-group"></i> ทรัพย์ที่ตรงเงื่อนไข: <b>${matchedCount.toLocaleString('en-US')}</b> รายการ`;
    }

    // 3. Location (ทำเล)
    const locEl = pdoc.getElementById('active-filter-loc-val');
    if (locEl) {
      let locStr = "ทุกทำเล (ทั่วประเทศ)";
      const isSharedProjNationwide = !hasProjFilter && !isRadiusEffective && !hasLocSelection && onlyProj && cosArr.length >= 2;

      if (isRadiusEffective) {
        if (subdist) {
          const cleanS = subdist.split(' (')[0].trim();
          const cleanD = dist ? dist.split(' (')[0].trim() : '-';
          locStr = `จุดศูนย์กลาง: จ.${prov || '-'} > อ.${cleanD} > ต.${cleanS}`;
        } else if (dist) {
          const cleanD = dist.split(' (')[0].trim();
          locStr = `จุดศูนย์กลาง: จ.${prov || '-'} > อ.${cleanD}`;
        } else if (prov) {
          locStr = `จุดศูนย์กลาง: จ.${prov}`;
        } else {
          locStr = `ตามพิกัดจุดศูนย์กลาง (ครอบคลุมตามรัศมี)`;
        }
      } else if (subdist) {
        const cleanS = subdist.split(' (')[0].trim();
        const cleanD = dist ? dist.split(' (')[0].trim() : '-';
        locStr = `จ.${prov || '-'} > อ.${cleanD} > ต.${cleanS}`;
      } else if (dist) {
        const cleanD = dist.split(' (')[0].trim();
        locStr = `จ.${prov || '-'} > อ.${cleanD}`;
      } else if (prov) {
        locStr = `จ.${prov}`;
      } else if (isSharedProjNationwide) {
        locStr = `โครงการร่วมกัน (${cosArr.join(' + ')}) ทั่วประเทศ`;
      }

      if (hasProjFilter) {
        const prjCount = inMapFilterState.samProjects ? inMapFilterState.samProjects.size : 1;
        const prjList = (inMapFilterState.samProjects && inMapFilterState.samProjects.size > 0)
          ? (prjCount > 1 ? `${prjCount} โครงการ` : Array.from(inMapFilterState.samProjects)[0])
          : inMapFilterState.samProject;
        locEl.innerHTML = `${escapeHtml(locStr)} &bull; โครงการ: ${escapeHtml(prjList)}`;
      } else {
        locEl.innerText = locStr;
      }
      setChipActive(locEl, hasProjFilter || isRadiusEffective || hasLocSelection || isSharedProjNationwide);
    }

    // 4. Radius (รัศมีตรวจ)
    const radEl = pdoc.getElementById('active-filter-rad-val');
    if (radEl) {
      let radStr = '';
      const rVal = currentRadiusKm < 1 ? currentRadiusKm.toFixed(2) : currentRadiusKm.toFixed(1);
      if (hasRef) {
        if (currentRefProp && currentRefProp._id) {
          const comp = currentRefProp._company || '-';
          radStr = `${rVal} กม. รอบ [${comp}] ${currentRefProp._id}`;
        } else {
          radStr = `${rVal} กม. (${referencePoint[1].toFixed(4)}, ${referencePoint[0].toFixed(4)})`;
        }
      } else {
        radStr = `รัศมี ${rVal} กม. (ยังไม่ได้ปักหมุด)`;
      }
      radEl.innerText = radStr;
      setChipActive(radEl, isRadiusEffective);
    }

    // 5. Company (บริษัท)
    const coEl = pdoc.getElementById('active-filter-co-val');
    if (coEl) {
      if (onlyProj && cosArr.length >= 2) {
        coEl.innerText = `${cosArr.join(', ')} (โครงการร่วมกัน)`;
      } else if (onlyProj) {
        coEl.innerText = cosArr.length > 0 ? `${cosArr.join(', ')} (เฉพาะมีโครงการ)` : "ทุกบริษัท (เฉพาะมีโครงการ)";
      } else if (cosArr.length > 0) {
        coEl.innerText = `${cosArr.join(', ')} (${cosArr.length} บริษัท)`;
      } else {
        coEl.innerText = "ทุกบริษัท";
      }
      setChipActive(coEl, cosArr.length > 0 || onlyProj);
    }

    // 6. Property Type (ประเภททรัพย์)
    const typeEl = pdoc.getElementById('active-filter-type-val');
    if (typeEl) {
      const hasTypes = !!(inMapFilterState && inMapFilterState.types && inMapFilterState.types.size > 0);
      if (hasTypes) {
        typeEl.innerText = Array.from(inMapFilterState.types).join(', ');
      } else {
        typeEl.innerText = "ทุกประเภททรัพย์";
      }
      setChipActive(typeEl, hasTypes);
    }

    // 7. Price (ราคา)
    const priceEl = pdoc.getElementById('active-filter-price-val');
    if (priceEl) {
      const minP = (inMapFilterState && inMapFilterState.minPrice > 0) ? inMapFilterState.minPrice : null;
      const maxP = (inMapFilterState && inMapFilterState.maxPrice > 0) ? inMapFilterState.maxPrice : null;
      const minPuw = (inMapFilterState && inMapFilterState.minPuw > 0) ? inMapFilterState.minPuw : null;
      const maxPuw = (inMapFilterState && inMapFilterState.maxPuw > 0) ? inMapFilterState.maxPuw : null;
      const minPum = (inMapFilterState && inMapFilterState.minPum > 0) ? inMapFilterState.minPum : null;
      const maxPum = (inMapFilterState && inMapFilterState.maxPum > 0) ? inMapFilterState.maxPum : null;
      let priceParts = [];
      if (minP && maxP) {
        priceParts.push(`${formatKpiPrice(minP)} - ${formatKpiPrice(maxP)}`);
      } else if (minP) {
        priceParts.push(`>= ${formatKpiPrice(minP)}`);
      } else if (maxP) {
        priceParts.push(`<= ${formatKpiPrice(maxP)}`);
      }
      if (minPuw && maxPuw) {
        priceParts.push(`${formatKpiPrice(minPuw)}-${formatKpiPrice(maxPuw)}/ตร.ว.`);
      } else if (minPuw) {
        priceParts.push(`>= ${formatKpiPrice(minPuw)}/ตร.ว.`);
      } else if (maxPuw) {
        priceParts.push(`<= ${formatKpiPrice(maxPuw)}/ตร.ว.`);
      }
      if (minPum && maxPum) {
        priceParts.push(`${formatKpiPrice(minPum)}-${formatKpiPrice(maxPum)}/ตร.ม.`);
      } else if (minPum) {
        priceParts.push(`>= ${formatKpiPrice(minPum)}/ตร.ม.`);
      } else if (maxPum) {
        priceParts.push(`<= ${formatKpiPrice(maxPum)}/ตร.ม.`);
      }
      priceEl.innerText = priceParts.length > 0 ? priceParts.join(' · ') : "ทุกช่วงราคา";
      setChipActive(priceEl, priceParts.length > 0);
    }

    // 8. Area (ขนาด/Plan)
    const areaEl = pdoc.getElementById('active-filter-area-val');
    if (areaEl) {
      const minSqw = inMapFilterState ? inMapFilterState.minSqw : null;
      const maxSqw = inMapFilterState ? inMapFilterState.maxSqw : null;
      const minSqm = inMapFilterState ? inMapFilterState.minSqm : null;
      const maxSqm = inMapFilterState ? inMapFilterState.maxSqm : null;
      let areaParts = [];
      if (minSqw || maxSqw) {
        areaParts.push(maxSqw ? `${(minSqw || 0).toLocaleString()}-${maxSqw.toLocaleString()} ตร.ว.` : `>= ${(minSqw || 0).toLocaleString()} ตร.ว.`);
      }
      if (minSqm || maxSqm) {
        areaParts.push(maxSqm ? `${(minSqm || 0).toLocaleString()}-${maxSqm.toLocaleString()} ตร.ม.` : `>= ${(minSqm || 0).toLocaleString()} ตร.ม.`);
      }
      areaEl.innerText = areaParts.length > 0 ? areaParts.join(' / ') : "ทุกขนาด (ทุก Plan)";
      setChipActive(areaEl, areaParts.length > 0);
    }

    // 9. Floor (ชั้น)
    const floorEl = pdoc.getElementById('active-filter-floor-val');
    if (floorEl) {
      let floorParts = [];
      if (inMapFilterState && inMapFilterState.floors && inMapFilterState.floors.size > 0) {
        const flMap = {'1': '1 ชั้น', '2': '2 ชั้น', '3': '3 ชั้น', '4+': '4+ ชั้น', 'none': 'ไม่ระบุ'};
        floorParts.push(Array.from(inMapFilterState.floors).map(c => flMap[c] || c).join(', '));
      }
      const minFl = inMapFilterState ? inMapFilterState.minFloor : null;
      const maxFl = inMapFilterState ? inMapFilterState.maxFloor : null;
      if (minFl && maxFl) {
        floorParts.push(`ชั้น ${minFl}-${maxFl}`);
      } else if (minFl) {
        floorParts.push(`>= ชั้น ${minFl}`);
      } else if (maxFl) {
        floorParts.push(`<= ชั้น ${maxFl}`);
      }
      floorEl.innerText = floorParts.length > 0 ? floorParts.join(' / ') : "ทุกชั้น";
      setChipActive(floorEl, floorParts.length > 0);
    }

    // 10. Spec (ห้อง/ที่จอด)
    const specEl = pdoc.getElementById('active-filter-spec-val');
    if (specEl) {
      let specParts = [];
      if (inMapFilterState && inMapFilterState.bedrooms && inMapFilterState.bedrooms.size > 0) {
        const bMap = {'0': 'สตูดิโอ', '1': '1 นอน', '2': '2 นอน', '3': '3 นอน', '4': '4 นอน', '5+': '5+ นอน', 'none': 'นอน(ไม่ระบุ)'};
        specParts.push(Array.from(inMapFilterState.bedrooms).map(b => bMap[b] || b).join(', '));
      }
      if (inMapFilterState && inMapFilterState.bathrooms && inMapFilterState.bathrooms.size > 0) {
        const baMap = {'1': '1 น้ำ', '2': '2 น้ำ', '3': '3 น้ำ', '4': '4 น้ำ', '5+': '5+ น้ำ', 'none': 'น้ำ(ไม่ระบุ)'};
        specParts.push(Array.from(inMapFilterState.bathrooms).map(b => baMap[b] || b).join(', '));
      }
      if (inMapFilterState && inMapFilterState.parkings && inMapFilterState.parkings.size > 0) {
        const pkMap = {'1': '1 จอด', '2': '2 จอด', '3': '3 จอด', '4+': '4+ จอด', 'none': 'จอด(ไม่ระบุ)'};
        specParts.push(Array.from(inMapFilterState.parkings).map(p => pkMap[p] || p).join(', '));
      }
      specEl.innerText = specParts.length > 0 ? specParts.join(' · ') : "ทุกสเปกห้อง/ที่จอด";
      setChipActive(specEl, specParts.length > 0);
    }

    // 11. Age (อายุประกาศ)
    const ageEl = pdoc.getElementById('active-filter-age-val');
    if (ageEl) {
      const effMax = (inMapFilterState && inMapFilterState.maxAge !== null && inMapFilterState.maxAge > 0) ? inMapFilterState.maxAge : (inMapFilterState && inMapFilterState.agePreset ? parseFloat(inMapFilterState.agePreset) : null);
      const hasAge = effMax !== null && !isNaN(effMax) && effMax > 0;
      if (hasAge) {
        ageEl.innerText = effMax >= 365 ? `<= ${(effMax/365).toFixed(1).replace('.0', '')} ปี` : `<= ${Math.round(effMax)} วัน`;
      } else {
        ageEl.innerText = "ทุกระยะเวลา";
      }
      setChipActive(ageEl, hasAge);
    }
  } catch (e) {
    console.warn("Failed to update parent filter status banner:", e);
  }
}

function isPureLandProperty(typeStr) {
  if (!typeStr) return false;
  const s = String(typeStr);
  const hasLand = /ที่ดินเปล่า|ที่ดิน/.test(s);
  const hasBld = /บ้าน|อาคาร|ทาวน์|คอนโด|ตึก|โรงงาน|พาณิชย์|หอพัก|สิ่งปลูกสร้าง|พร้อมสิ่งปลูกสร้าง/.test(s);
  return hasLand && !hasBld;
}

function calcMedianMinMax(rates) {
  if (!rates || rates.length === 0) {
    return { count: 0, median: 0, min: 0, max: 0, has: false };
  }
  const sorted = rates.slice().sort((a, b) => a - b);
  const count = sorted.length;
  const min = sorted[0];
  const max = sorted[count - 1];
  const mid = Math.floor(count / 2);
  const median = (count % 2 !== 0) ? sorted[mid] : ((sorted[mid - 1] + sorted[mid]) / 2);
  return { count, median, min, max, has: true };
}

function updateParentMedianCards(sharedActiveData) {
  try {
    if (!window.parent || !window.parent.document) return;
    const pdoc = window.parent.document;

    const card1 = pdoc.getElementById('median-card-1');
    if (!card1) return;

    // If Price Center mode is active in parent, do NOT overwrite the price center cards with median metrics!
    if (card1.classList.contains('metric-card-pink') || (currentPriceCenterId && String(currentPriceCenterId).trim() !== '')) {
      return;
    }

    // 1. Determine active comparison dataset (reusing shared scan when provided)
    const activeData = Array.isArray(sharedActiveData) ? sharedActiveData : _getSharedActiveParentData();
    let scopeHeader = '';
    const hasRef = !!referencePoint;
    const isRadiusMode = (mapPinMode === 'radius');
    const hasProv = !!(currentSelectedProv && currentSelectedProv.trim() !== '' && currentSelectedProv !== '__ALL__');
    const hasProjFilter = inMapFilterState && ((inMapFilterState.samProjects && inMapFilterState.samProjects.size > 0) || (inMapFilterState.samProject && inMapFilterState.samProject !== ''));

    if (hasProjFilter) {
      const prjCount = inMapFilterState.samProjects ? inMapFilterState.samProjects.size : 1;
      const projDesc = prjCount > 1 ? `${prjCount} โครงการ` : (Array.from(inMapFilterState.samProjects)[0] || inMapFilterState.samProject);
      scopeHeader = `(โครงการ: ${projDesc})`;
    } else if (isRadiusMode && hasRef) {
      const rDisp = formatRadiusDisplay(currentRadiusKm);
      scopeHeader = `(ในรัศมี ${rDisp} จากจุดอ้างอิง)`;
    } else if (mapPinMode === 'location' && hasProv) {
      let locDesc = currentSelectedProv;
      if (currentSelectedDist) locDesc += ' > ' + currentSelectedDist;
      if (currentSelectedSubdist) locDesc += ' > ' + currentSelectedSubdist;
      scopeHeader = `(ทำเล ${locDesc})`;
    } else {
      scopeHeader = '(ภาพรวมทั่วประเทศ)';
    }

    // Update Scope Header Text
    const scopeHeaderEl = pdoc.getElementById('median-scope-header-text');
    if (scopeHeaderEl) scopeHeaderEl.innerText = scopeHeader;

    // Card 1: Reference Info (Total Count as Primary Metric)
    const totalNearbyCnt = activeData.length;
    const card1Val = pdoc.getElementById('median-card1-val');
    if (card1Val) {
      card1Val.innerHTML = `${totalNearbyCnt.toLocaleString('en-US')} <span style='font-size:0.85rem; font-weight:600; color:#64748b;'>รายการ</span>`;
    }
    const card1Loc = pdoc.getElementById('median-card1-loc');
    if (card1Loc) {
      let locStr = '';
      if (hasRef) {
        locStr = `${referencePoint[1].toFixed(5)}, ${referencePoint[0].toFixed(5)} (รัศมี ${formatRadiusDisplay(currentRadiusKm)})`;
      } else {
        locStr = scopeHeader.replace(/^\(/, '').replace(/\)$/, '');
      }
      card1Loc.innerHTML = `<i class='fa-solid fa-location-dot' style='color:#10b981; font-size:0.72rem; margin-right:3px;'></i>${escapeHtml(locStr)}`;
    }
    const card1Sub = pdoc.getElementById('median-card1-sub');
    if (card1Sub) {
      if (currentRefProp && currentRefProp._id) {
        const pCo = currentRefProp._company || '-';
        const pCode = currentRefProp._id || '-';
        const pType = currentRefProp._type || '-';
        card1Sub.innerHTML = `[${escapeHtml(pCo)}] ${escapeHtml(pCode)} &bull; ${escapeHtml(pType)}`;
      } else if (hasRef) {
        card1Sub.innerText = 'กำหนดจากพิกัดแผนที่';
      } else {
        card1Sub.innerText = scopeHeader.replace(/^\(/, '').replace(/\)$/, '');
      }
    }

    // Card 2: ราคากลาง / ตร.ม. (Median Sq. Metre for All Properties with sqm > 0 and price > 0)
    const card2Badge = pdoc.getElementById('median-card2-badge');
    const card2Val = pdoc.getElementById('median-card2-val');
    const card2Sub = pdoc.getElementById('median-card2-sub');
    if (card2Val) {
      const sqmRates = [];
      for (let i = 0; i < activeData.length; i++) {
        const d = activeData[i];
        if (d._price > 0 && d._sqm > 0) {
          const r = d._price / d._sqm;
          if (r > 0) sqmRates.push(r);
        }
      }
      const sqmStats = calcMedianMinMax(sqmRates);
      if (sqmStats.has) {
        if (card2Badge) card2Badge.innerHTML = `<span style='font-size:0.74rem; font-weight:600; color:#10b981;'>(${sqmStats.count.toLocaleString('en-US')} แปลง)</span>`;
        card2Val.innerHTML = `฿${Math.round(sqmStats.median).toLocaleString('en-US')} <span style='font-size:0.85rem; font-weight:600; color:#64748b;'>/ตร.ม.</span>`;
        if (card2Sub) card2Sub.innerHTML = `ต่ำสุด ฿${Math.round(sqmStats.min).toLocaleString('en-US')} &bull; สูงสุด ฿${Math.round(sqmStats.max).toLocaleString('en-US')}`;
      } else {
        if (card2Badge) card2Badge.innerHTML = '';
        card2Val.innerHTML = `-`;
        if (card2Sub) card2Sub.innerText = 'ไม่มีข้อมูลพื้นที่ใช้สอย';
      }
    }

    // Card 3 (rendered as Card 2 in Column 2): Landed / Sq. Wah Median (Strictly /ตร.ว. only, never /ตร.ม.)
    let targetType = null;
    const selectedTypesSet = (inMapFilterState && inMapFilterState.types && inMapFilterState.types.size > 0) ? inMapFilterState.types : null;
    if (currentRefProp && currentRefProp._type && currentRefProp._type !== '-') {
      targetType = currentRefProp._type;
    } else if (selectedTypesSet && selectedTypesSet.size === 1) {
      targetType = Array.from(selectedTypesSet)[0];
    }

    const isCondoType = (val) => /คอนโด|ห้องชุด/i.test(String(val || ''));
    const targetIsCondo = !!(targetType && isCondoType(targetType));
    const targetIsPureLand = !!(targetType && isPureLandProperty(targetType));
    const userFilteredPureLand = !!(selectedTypesSet && selectedTypesSet.size > 0 && Array.from(selectedTypesSet).every(t => isPureLandProperty(t)));

    let targetTypeTitle = 'ราคากลางตร.ว. บ้านและสิ่งปลูกสร้าง';
    let matchCard3Fn = null;

    if (targetType && !targetIsCondo && !targetIsPureLand) {
      targetTypeTitle = `ราคากลางตร.ว. ${targetType}`;
      const tTrim = targetType.trim();
      matchCard3Fn = (d) => (d._type || '').trim() === tTrim;
    } else if (selectedTypesSet && selectedTypesSet.size > 0) {
      const landedActive = Array.from(selectedTypesSet).filter(t => !isPureLandProperty(t) && !isCondoType(t));
      if (landedActive.length > 0) {
        targetTypeTitle = `ราคากลางตร.ว. ${landedActive.join(', ')}`;
        const landedSet = new Set(landedActive);
        matchCard3Fn = (d) => landedSet.has(d._type);
      } else if (userFilteredPureLand) {
        targetTypeTitle = 'ราคากลางตร.ว. ที่ดินเปล่า';
        matchCard3Fn = (d) => isPureLandProperty(d._type);
      } else {
        targetTypeTitle = 'ราคากลางตร.ว. บ้านและสิ่งปลูกสร้าง';
        matchCard3Fn = null;
      }
    } else if (targetIsPureLand) {
      targetTypeTitle = 'ราคากลางตร.ว. ที่ดินเปล่า';
      matchCard3Fn = (d) => isPureLandProperty(d._type);
    } else if (targetIsCondo) {
      targetTypeTitle = 'ราคากลางตร.ว. บ้านและสิ่งปลูกสร้าง';
      matchCard3Fn = null;
    } else {
      targetTypeTitle = 'ราคากลางตร.ว. บ้านและสิ่งปลูกสร้าง';
      matchCard3Fn = (d) => !isPureLandProperty(d._type) && !isCondoType(d._type);
    }

    const targetRates = [];
    if (matchCard3Fn) {
      for (let i = 0; i < activeData.length; i++) {
        const d = activeData[i];
        if (d._price <= 0 || !matchCard3Fn(d)) continue;
        const r = (d._sqw && d._sqw > 0) ? (d._price / d._sqw) : ((d._puw && d._puw > 0) ? d._puw : null);
        if (r && r > 0) targetRates.push(r);
      }
    }

    const targetStats = calcMedianMinMax(targetRates);
    const card3Title = pdoc.getElementById('median-card3-title');
    const card3Val = pdoc.getElementById('median-card3-val');
    const card3Sub = pdoc.getElementById('median-card3-sub');

    if (card3Title) {
      card3Title.innerHTML = `<i class='fa-solid fa-house' style='color: #10b981; margin-right:4px;'></i> ${escapeHtml(targetTypeTitle)} <span id='median-card3-badge'></span>`;
    }
    const activeBadgeEl = pdoc.getElementById('median-card3-badge');

    if (targetStats.has) {
      if (activeBadgeEl) activeBadgeEl.innerHTML = `<span style='font-size:0.74rem; font-weight:600; color:#10b981;'>(${targetStats.count.toLocaleString('en-US')} แปลง)</span>`;
      if (card3Val) card3Val.innerHTML = `฿${Math.round(targetStats.median).toLocaleString('en-US')} <span style='font-size:0.85rem; font-weight:600; color:#64748b;'>/ตร.ว.</span>`;
      if (card3Sub) card3Sub.innerHTML = `ต่ำสุด ฿${Math.round(targetStats.min).toLocaleString('en-US')} &bull; สูงสุด ฿${Math.round(targetStats.max).toLocaleString('en-US')}`;
    } else {
      if (activeBadgeEl) activeBadgeEl.innerHTML = '';
      if (card3Val) card3Val.innerHTML = `-`;
      if (card3Sub) card3Sub.innerText = `-`;
    }

    // Card 4: Pure Land Median (Strictly separated & ALWAYS computed)
    let sourceIcon = 'fa-circle-dot';
    let landSourceDesc = '';
    let pureLandRates = [];

    function getPureLandRatesFromList(itemList) {
      const rList = [];
      if (!itemList || itemList.length === 0) return rList;
      for (let i = 0; i < itemList.length; i++) {
        const d = itemList[i];
        if (!isPureLandProperty(d._type) || !d._price || d._price <= 0) continue;
        const r = (d._puw && d._puw > 0) ? d._puw : ((d._sqw && d._sqw > 0) ? d._price / d._sqw : null);
        if (r && r > 0) rList.push(r);
      }
      return rList;
    }

    function filterByActiveCoIfAny(itemList, baseRates) {
      if (!inMapFilterState || !inMapFilterState.companies || inMapFilterState.companies.size === 0) {
        return baseRates;
      }
      const activeCos = inMapFilterState.companies;
      const coRates = [];
      for (let i = 0; i < itemList.length; i++) {
        const d = itemList[i];
        if (!activeCos.has(d._company)) continue;
        if (!isPureLandProperty(d._type) || !d._price || d._price <= 0) continue;
        const r = (d._puw && d._puw > 0) ? d._puw : ((d._sqw && d._sqw > 0) ? d._price / d._sqw : null);
        if (r && r > 0) coRates.push(r);
      }
      return coRates.length > 0 ? coRates : baseRates;
    }

    const allDbData = cachedData || [];

    if (isRadiusMode && hasRef) {
      const landRadius = Math.max(parseFloat(currentRadiusKm) || 5.0, 1.0);
      sourceIcon = 'fa-circle-dot';
      landSourceDesc = `ตามรัศมี ${landRadius.toFixed(1)} กม. รอบจุดอ้างอิง`;
      // MUST query UNFILTERED spatial pool, NEVER currentNearbyData (which is filtered by type/company/price!)
      let candPool = queryPointsInRadius(referencePoint[0], referencePoint[1], landRadius);
      pureLandRates = getPureLandRatesFromList(candPool);

      // If empty, expand radius progressively: 10, 15, 20, 30, 50 km
      if (pureLandRates.length === 0) {
        const expRadii = [10.0, 15.0, 20.0, 30.0, 50.0];
        for (let ri = 0; ri < expRadii.length; ri++) {
          const expR = expRadii[ri];
          if (expR <= landRadius) continue;
          const expCand = queryPointsInRadius(referencePoint[0], referencePoint[1], expR);
          const expRates = getPureLandRatesFromList(expCand);
          if (expRates.length > 0) {
            candPool = expCand;
            pureLandRates = expRates;
            landSourceDesc = `ที่ดินเปล่าในรัศมี ${expR.toFixed(0)} กม. รอบจุดอ้างอิง`;
            sourceIcon = 'fa-circle-dot';
            break;
          }
        }
      }

      // If still empty, fall back to District / Province of reference point or nearest properties
      if (pureLandRates.length === 0) {
        let pDist = currentRefProp ? (currentRefProp._district || '') : '';
        let pProv = currentRefProp ? (currentRefProp._prov || '') : '';
        if (!pDist || !pProv || pDist === '-' || pProv === '-' || pDist === 'ไม่มีข้อมูล' || pProv === 'ไม่มีข้อมูล') {
          const nearest = queryPointsInRadius(referencePoint[0], referencePoint[1], 50.0);
          for (let ni = 0; ni < nearest.length; ni++) {
            if (!pDist && nearest[ni]._district && nearest[ni]._district !== '-' && nearest[ni]._district !== 'ไม่มีข้อมูล') pDist = nearest[ni]._district.trim();
            if (!pProv && nearest[ni]._prov && nearest[ni]._prov !== '-' && nearest[ni]._prov !== 'ไม่มีข้อมูล') pProv = nearest[ni]._prov.trim();
            if (pDist && pProv) break;
          }
        }
        if (pDist && pProv && pDist !== '-' && pProv !== '-' && pDist !== 'ไม่มีข้อมูล' && pProv !== 'ไม่มีข้อมูล') {
          const distCand = allDbData.filter(d => (d._district || '').trim() === pDist && (d._prov || '').trim() === pProv);
          const distRates = getPureLandRatesFromList(distCand);
          if (distRates.length > 0) {
            candPool = distCand;
            pureLandRates = distRates;
            landSourceDesc = `ที่ดินเปล่าใน อ.${pDist} จ.${pProv}`;
            sourceIcon = 'fa-location-dot';
          }
        }
        if (pureLandRates.length === 0 && pProv && pProv !== '-' && pProv !== 'ไม่มีข้อมูล') {
          const provCand = allDbData.filter(d => (d._prov || '').trim() === pProv);
          const provRates = getPureLandRatesFromList(provCand);
          if (provRates.length > 0) {
            candPool = provCand;
            pureLandRates = provRates;
            landSourceDesc = `ที่ดินเปล่าใน จ.${pProv}`;
            sourceIcon = 'fa-location-dot';
          }
        }
      }

      // Check if active company has pure land in this pool
      pureLandRates = filterByActiveCoIfAny(candPool, pureLandRates);

    } else if (hasProjFilter) {
      sourceIcon = 'fa-mountain-sun';
      const prjCount = inMapFilterState.samProjects ? inMapFilterState.samProjects.size : 1;
      const projDesc = prjCount > 1 ? `${prjCount} โครงการ` : (Array.from(inMapFilterState.samProjects)[0] || inMapFilterState.samProject);

      // Get UNFILTERED project items from global maps
      let pNameList = inMapFilterState.samProjects ? Array.from(inMapFilterState.samProjects) : [inMapFilterState.samProject];
      let projAllItems = [];
      let seenProjIds = new Set();
      pNameList.forEach(pn => {
        const itms = globalProjToItemsMap.get(pn) || [];
        itms.forEach(it => {
          const uKey = _itemUniqueKey(it);
          if (!seenProjIds.has(uKey)) { seenProjIds.add(uKey); projAllItems.push(it); }
        });
      });
      if (projAllItems.length === 0 && inMapFilterState.samProject) {
        const tNk = normalizeProjectKeyword(inMapFilterState.samProject);
        projAllItems = (globalNormToItemsMap.get(tNk) || globalProjToItemsMap.get(inMapFilterState.samProject) || []).slice();
      }

      let candPool = projAllItems;
      pureLandRates = getPureLandRatesFromList(projAllItems);
      if (pureLandRates.length > 0) {
        landSourceDesc = `ในโครงการ: ${projDesc}`;
      } else {
        // Project has no pure land -> search radius around project centroid
        let pLats = [], pLons = [];
        let pProv = '', pDist = '';
        for (let i = 0; i < projAllItems.length; i++) {
          const item = projAllItems[i];
          if (item.lat && item.lon) { pLats.push(item.lat); pLons.push(item.lon); }
          if (!pProv && item._prov && item._prov !== '-' && item._prov !== 'ไม่มีข้อมูล') pProv = item._prov.trim();
          if (!pDist && item._district && item._district !== '-' && item._district !== 'ไม่มีข้อมูล') pDist = item._district.trim();
        }
        if (pLats.length > 0 && pLons.length > 0) {
          const cLat = pLats.reduce((a, b) => a + b, 0) / pLats.length;
          const cLon = pLons.reduce((a, b) => a + b, 0) / pLons.length;
          const expRadii = [5.0, 10.0, 15.0, 20.0, 30.0];
          for (let ri = 0; ri < expRadii.length; ri++) {
            const rDist = expRadii[ri];
            const cand = queryPointsInRadius(cLon, cLat, rDist);
            const candRates = getPureLandRatesFromList(cand);
            if (candRates.length >= 2 || (ri === expRadii.length - 1 && candRates.length > 0)) {
              candPool = cand;
              pureLandRates = candRates;
              landSourceDesc = `ที่ดินเปล่ารอบโครงการ (รัศมี ${rDist.toFixed(0)} กม.)`;
              break;
            }
          }
        }
        if (pureLandRates.length === 0 && pDist && pProv) {
          const distCand = allDbData.filter(d => (d._district || '').trim() === pDist && (d._prov || '').trim() === pProv);
          const distRates = getPureLandRatesFromList(distCand);
          if (distRates.length > 0) {
            candPool = distCand;
            pureLandRates = distRates;
            landSourceDesc = `ที่ดินเปล่ารอบโครงการ (อ.${pDist} จ.${pProv})`;
          }
        }
        if (pureLandRates.length === 0 && pProv) {
          const provCand = allDbData.filter(d => (d._prov || '').trim() === pProv);
          const provRates = getPureLandRatesFromList(provCand);
          if (provRates.length > 0) {
            candPool = provCand;
            pureLandRates = provRates;
            landSourceDesc = `ที่ดินเปล่ารอบโครงการ (จ.${pProv})`;
          }
        }
      }

    } else {
      // Location mode or Nationwide
      sourceIcon = 'fa-location-dot';
      let candPool = allDbData;
      const hasSub = !!(currentSelectedSubdist && currentSelectedSubdist !== '__ALL__');
      const hasDist = !!(currentSelectedDist && currentSelectedDist !== '__ALL__');
      const hasProv = !!(currentSelectedProv && currentSelectedProv !== '__ALL__');

      if (hasSub) {
        const subCand = allDbData.filter(d =>
          (d._subdistrict || '').trim() === currentSelectedSubdist.trim() &&
          (!hasDist || (d._district || '').trim() === currentSelectedDist.trim()) &&
          (!hasProv || (d._prov || '').trim() === currentSelectedProv.trim())
        );
        pureLandRates = getPureLandRatesFromList(subCand);
        if (pureLandRates.length > 0) {
          candPool = subCand;
          landSourceDesc = `ตามทำเล ต.${currentSelectedSubdist}` + (hasDist ? ` อ.${currentSelectedDist}` : '');
        }
      }
      if (pureLandRates.length === 0 && hasDist) {
        const distCand = allDbData.filter(d =>
          (d._district || '').trim() === currentSelectedDist.trim() &&
          (!hasProv || (d._prov || '').trim() === currentSelectedProv.trim())
        );
        pureLandRates = getPureLandRatesFromList(distCand);
        if (pureLandRates.length > 0) {
          candPool = distCand;
          landSourceDesc = `ที่ดินเปล่าใน อ.${currentSelectedDist}` + (hasProv ? ` จ.${currentSelectedProv}` : '');
        }
      }
      if (pureLandRates.length === 0 && hasProv) {
        const provCand = allDbData.filter(d => (d._prov || '').trim() === currentSelectedProv.trim());
        pureLandRates = getPureLandRatesFromList(provCand);
        if (pureLandRates.length > 0) {
          candPool = provCand;
          landSourceDesc = `ที่ดินเปล่าใน จ.${currentSelectedProv}`;
        }
      }
      if (pureLandRates.length === 0) {
        candPool = allDbData;
        pureLandRates = getPureLandRatesFromList(allDbData);
        sourceIcon = 'fa-globe';
        landSourceDesc = 'ที่ดินเปล่า ภาพรวมทั่วประเทศ';
      }
      pureLandRates = filterByActiveCoIfAny(candPool, pureLandRates);
    }

    // FINAL GUARANTEE: If pureLandRates is still empty, fallback to nationwide
    if (pureLandRates.length === 0) {
      pureLandRates = getPureLandRatesFromList(allDbData);
      sourceIcon = 'fa-globe';
      landSourceDesc = 'ที่ดินเปล่า ภาพรวมทั่วประเทศ';
    }

    const landStats = calcMedianMinMax(pureLandRates);
    const card4Badge = pdoc.getElementById('median-card4-badge');
    const card4Val = pdoc.getElementById('median-card4-val');
    const card4Source = pdoc.getElementById('median-card4-source');
    const card4Sub = pdoc.getElementById('median-card4-sub');

    if (card4Source) {
      card4Source.innerHTML = `<i class='fa-solid ${escapeHtml(sourceIcon)}' style='font-size:0.72rem; margin-right:3px; color: #b45309;'></i>${escapeHtml(landSourceDesc)}`;
      card4Source.title = landSourceDesc;
      card4Source.style.display = 'block';
    }

    if (landStats.has) {
      if (card4Badge) card4Badge.innerHTML = `<span style='font-size:0.74rem; font-weight:600; color:#92400e;'>(${landStats.count.toLocaleString('en-US')} แปลง)</span>`;
      if (card4Val) card4Val.innerHTML = `฿${Math.round(landStats.median).toLocaleString('en-US')} <span style='font-size:0.85rem; font-weight:600; color:#78716c;'>/ตร.ว.</span>`;
      if (card4Sub) card4Sub.innerHTML = `ต่ำสุด ฿${Math.round(landStats.min).toLocaleString('en-US')} &bull; สูงสุด ฿${Math.round(landStats.max).toLocaleString('en-US')}`;
    } else {
      if (card4Badge) card4Badge.innerHTML = '';
      if (card4Val) card4Val.innerHTML = `-`;
      if (card4Sub) card4Sub.innerText = '-';
    }

    // Table Title realtime update
    const tableTitleEl = pdoc.getElementById('median-table-title');
    if (tableTitleEl) {
      tableTitleEl.innerText = `รายการทรัพย์สิน (${totalNearbyCnt.toLocaleString('en-US')} รายการ ${scopeHeader})`;
    }
  } catch(e) {
    console.warn('updateParentMedianCards error:', e);
  }
}

let kpiUpdateRaf = null;
let _parentTabRetryTimer = null;
let _ttObserverInstance = null;

function scheduleParentKpiUpdate() {
  if (kpiUpdateRaf) cancelAnimationFrame(kpiUpdateRaf);
  kpiUpdateRaf = requestAnimationFrame(() => {
    kpiUpdateRaf = null;
    const sharedData = _getSharedActiveParentData();
    updateParentKpiCards(sharedData);
    updateParentFilterStatusBanner(sharedData);
    updateParentMedianCards(sharedData);
  });
}

let _mapResizeObserver = null;
let _mapResizeRaf = null;
let _deferredBoundaryTimer = null;

function _triggerImmediateMapRedraw() {
  if (!deckglInstance) return;
  if (typeof armInstantBackdropSafetyTimer === 'function') {
    armInstantBackdropSafetyTimer();
  }
  if (_mapResizeRaf) cancelAnimationFrame(_mapResizeRaf);
  _mapResizeRaf = requestAnimationFrame(() => {
    _mapResizeRaf = null;
    try {
      window.dispatchEvent(new Event('resize'));
      if (deckglInstance && typeof deckglInstance.redraw === 'function') {
        deckglInstance.redraw(true);
      }
      updateSvgBoundaries();
    } catch (_e) {}
  });
}

function setupParentTabListeners() {
  try {
    if (!window.parent || !window.parent.document) return;
    const pWin = window.parent;
    const pdoc = pWin.document;

    // Abort & disconnect any previous iframe's parent listeners/observers before rebinding
    if (typeof pWin.__NOVA_TAB_LISTENER_CLEANUP__ === 'function') {
      try { pWin.__NOVA_TAB_LISTENER_CLEANUP__(); } catch (_ce) {}
      pWin.__NOVA_TAB_LISTENER_CLEANUP__ = null;
    }

    updateParentFilterStatusBanner();

    const tryBind = () => {
      const tablist = pdoc.querySelector('.st-key-main_tabs_container [role="tablist"]');
      if (!tablist) return false;
      const tabs = tablist.querySelectorAll('[role="tab"]');
      if (tabs.length < 2) return false;

      const ac = (typeof AbortController === 'function') ? new AbortController() : null;
      const listenerOpts = ac ? { signal: ac.signal } : false;

      tabs.forEach((t, idx) => {
        t.addEventListener('click', () => {
          requestAnimationFrame(() => {
            if (idx === 1) {
              scheduleParentKpiUpdate();
              _triggerImmediateMapRedraw();
            } else {
              restoreDefaultParentKpiCards();
            }
          });
        }, listenerOpts);
      });

      const obs = new MutationObserver(() => {
        const isTab2Active = tabs[1] && tabs[1].getAttribute('aria-selected') === 'true';
        if (isTab2Active) {
          scheduleParentKpiUpdate();
          _triggerImmediateMapRedraw();
        } else {
          restoreDefaultParentKpiCards();
        }
      });
      obs.observe(tablist, { attributes: true, subtree: true, attributeFilter: ['aria-selected'] });

      pWin.__NOVA_TAB_LISTENER_CLEANUP__ = () => {
        try { if (ac) ac.abort(); } catch (_e) {}
        try { obs.disconnect(); } catch (_e) {}
      };

      // If Tab 2 is already active right now, apply immediately
      if (tabs[1] && tabs[1].getAttribute('aria-selected') === 'true') {
        scheduleParentKpiUpdate();
        _triggerImmediateMapRedraw();
      }

      return true;
    };

    if (!tryBind()) {
      let attempts = 0;
      if (_parentTabRetryTimer) clearInterval(_parentTabRetryTimer);
      _parentTabRetryTimer = setInterval(() => {
        attempts++;
        if (tryBind() || attempts > 20) {
          clearInterval(_parentTabRetryTimer);
          _parentTabRetryTimer = null;
        }
      }, 250);
    }
  } catch(e) {
    console.warn('setupParentTabListeners error:', e);
  }
}

function cleanupMapResources() {
  try {
    if (kpiUpdateRaf) { cancelAnimationFrame(kpiUpdateRaf); kpiUpdateRaf = null; }
    if (_mapResizeRaf) { cancelAnimationFrame(_mapResizeRaf); _mapResizeRaf = null; }
    if (typeof mapAnimRaf !== 'undefined' && mapAnimRaf) { cancelAnimationFrame(mapAnimRaf); mapAnimRaf = null; }
    if (typeof hoverRaf !== 'undefined' && hoverRaf) { cancelAnimationFrame(hoverRaf); hoverRaf = null; }
    if (streamlitSyncTimer) { clearTimeout(streamlitSyncTimer); streamlitSyncTimer = null; }
    if (streamlitSyncBtnTimer) { clearTimeout(streamlitSyncBtnTimer); streamlitSyncBtnTimer = null; }
    if (radiusInputDebounceTimer) { clearTimeout(radiusInputDebounceTimer); radiusInputDebounceTimer = null; }
    if (projSearchDebounceTimer) { clearTimeout(projSearchDebounceTimer); projSearchDebounceTimer = null; }
    if (placeSearchTimer) { clearTimeout(placeSearchTimer); placeSearchTimer = null; }
    if (placeSearchAbortCtrl) { try { placeSearchAbortCtrl.abort(); } catch (_e) {} placeSearchAbortCtrl = null; }
    if (_parentTabRetryTimer) { clearInterval(_parentTabRetryTimer); _parentTabRetryTimer = null; }
    if (_deferredBoundaryTimer) { clearTimeout(_deferredBoundaryTimer); _deferredBoundaryTimer = null; }
    if (typeof _hoverDetailPrefetchTimer !== 'undefined' && _hoverDetailPrefetchTimer) { clearTimeout(_hoverDetailPrefetchTimer); _hoverDetailPrefetchTimer = null; }
    if (_ttObserverInstance) { _ttObserverInstance.disconnect(); _ttObserverInstance = null; }
    if (_mapResizeObserver) { _mapResizeObserver.disconnect(); _mapResizeObserver = null; }
    if (typeof dismissInstantMapBackdrop === 'function') { dismissInstantMapBackdrop(); }
    if (typeof clearDecodedTileBitmaps === 'function') { clearDecodedTileBitmaps(); }
    if (window.parent && typeof window.parent.__NOVA_TAB_LISTENER_CLEANUP__ === 'function') {
      window.parent.__NOVA_TAB_LISTENER_CLEANUP__();
      window.parent.__NOVA_TAB_LISTENER_CLEANUP__ = null;
    }
    if (deckglInstance) {
      if (typeof deckglInstance.finalize === 'function') {
        deckglInstance.finalize();
      }
      deckglInstance = null;
    }
  } catch (_e) {}
}
window.addEventListener('pagehide', cleanupMapResources);
window.addEventListener('beforeunload', cleanupMapResources);

function setReferencePoint(lon, lat, flyTo = true, triggerSync = true) {
  if (typeof _userInteractedWithMap !== 'undefined') _userInteractedWithMap = true;
  if (typeof dismissInstantMapBackdrop === 'function') dismissInstantMapBackdrop();
  referencePoint = [lon, lat];
  updateSavedCoordsPillsActiveState(lat, lon);
  pendingReferencePoint = null;
  mousePreviewCoord = null;

  if (mapPinMode !== 'radius') {
    mapPinMode = 'radius';
    const btnLoc = document.getElementById('btn-mode-location');
    const btnRad = document.getElementById('btn-mode-radius');
    if (btnLoc) btnLoc.classList.toggle('active', false);
    if (btnRad) btnRad.classList.toggle('active', true);
  }

  const rawNearby = queryPointsInRadius(lon, lat, currentRadiusKm);
  currentScopePool = rawNearby;
  currentNearbyData = rawNearby.filter(filterItemPasses);
  currentCoordMap = buildCoordMap(currentNearbyData);
  updateDuplicateStats(currentNearbyData, currentCoordMap);

  const coordPill = document.getElementById('active-ref-pill');
  const coordText = document.getElementById('active-ref-coord-text');
  if (coordPill && coordText) {
    coordText.innerText = `${lat.toFixed(5)}, ${lon.toFixed(5)}`;
    coordPill.style.display = 'inline-flex';
  }

  const coordInp = document.getElementById('inmap-coord-input');
  const coordClr = document.getElementById('inmap-clear-coord-btn');
  if (coordInp) {
    coordInp.value = `${lat.toFixed(5)}, ${lon.toFixed(5)}`;
    if (coordClr) coordClr.style.display = 'inline-flex';
  }

  const statusEl = document.getElementById('radius-status-text');
  if (statusEl) {
    statusEl.style.display = 'inline-block';
    statusEl.innerHTML = `<span style="color:#10b981; font-weight:800;"><i class="fa-solid fa-crosshairs"></i> จุดอ้างอิง:</span> <b>${lat.toFixed(5)}, ${lon.toFixed(5)}</b> (พบ <b>${currentNearbyData.length.toLocaleString()}</b> รายการ ในรัศมี <b>${formatRadiusDisplay(currentRadiusKm)}</b>)`;
  }

  const clearBtn = document.getElementById('btn-clear-ref');
  if (clearBtn) {
    clearBtn.style.display = 'inline-flex';
  }

  const countEl = document.getElementById('points-count');
  if (countEl) {
    countEl.innerText = `จุดอ้างอิง: แสดง ${currentNearbyData.length.toLocaleString()} รายการ (ในรัศมี ${formatRadiusDisplay(currentRadiusKm)})`;
  }

  updateLegendContent();
  updateDeckLayers();
  updatePropertyCardPosition();
  scheduleParentKpiUpdate();

  // Push coordinate to parent window URL for Streamlit synchronization
  try {
    var u = new URL(window.parent.location.href);
    u.searchParams.set('map_ref_lat', lat.toFixed(6));
    u.searchParams.set('map_ref_lon', lon.toFixed(6));
    u.searchParams.set('map_ref_radius', currentRadiusKm);
    u.searchParams.set('map_pin_mode', mapPinMode || 'radius');
    u.searchParams.delete('map_ref_cleared');
    window.parent.history.replaceState({}, '', u.toString());
  } catch(e) {}

  if (triggerSync) {
    triggerStreamlitSync();
  }

  if (flyTo && deckglInstance) {
    const targetZoom = calculateZoomForRadius(lat, currentRadiusKm);
    smoothFlyTo(lon, lat, targetZoom, 1500);
  }
}

function clearReferencePoint() {
  referencePoint = null;
  updateSavedCoordsPillsActiveState(null, null);
  currentRefProp = null;
  currentRefId = "";
  currentPriceCenterId = "";
  pendingReferencePoint = null;
  mousePreviewCoord = null;

  const coordPill = document.getElementById('active-ref-pill');
  if (coordPill) coordPill.style.display = 'none';

  const statusEl = document.getElementById('radius-status-text');
  if (statusEl) statusEl.style.display = 'none';

  const clearBtn = document.getElementById('btn-clear-ref');
  if (clearBtn) {
    clearBtn.style.display = 'none';
  }

  const searchInp = document.getElementById('inmap-prop-search-input');
  if (searchInp) searchInp.value = '';
  const searchClr = document.getElementById('inmap-clear-search-btn');
  if (searchClr) searchClr.style.display = 'none';

  const coordInp = document.getElementById('inmap-coord-input');
  if (coordInp) coordInp.value = '';
  const coordClr = document.getElementById('inmap-clear-coord-btn');
  if (coordClr) coordClr.style.display = 'none';

  const bubble = document.getElementById('in-map-confirm-bubble');
  if (bubble) bubble.style.display = 'none';

  const bar = document.getElementById('ref-confirm-bar');
  if (bar) bar.style.display = 'none';

  const overlapText = document.getElementById('legend-overlap-text');
  if (overlapText) {
    overlapText.innerHTML = `ยังไม่ได้เลือกจุดอ้างอิง`;
  }

  closePropertyCard();
  applyInMapFilters(true);
  scheduleParentKpiUpdate();

  try {
    var u = new URL(window.parent.location.href);
    u.searchParams.delete('map_ref_lat');
    u.searchParams.delete('map_ref_lon');
    u.searchParams.delete('map_ref_id');
    u.searchParams.delete('map_price_ref_id');
    u.searchParams.set('map_ref_cleared', '1');
    window.parent.history.replaceState({}, '', u.toString());
  } catch(e) {}
  triggerStreamlitSync({
    prov: (currentSelectedProv && currentSelectedProv !== '__ALL__') ? currentSelectedProv.trim() : '',
    dist: (currentSelectedDist && currentSelectedDist !== '__ALL__') ? currentSelectedDist.trim() : '',
    subdist: (currentSelectedSubdist && currentSelectedSubdist !== '__ALL__') ? currentSelectedSubdist.trim() : '',
    id: '',
    price_center_id: '',
    lat: 0,
    lon: 0,
    radius: currentRadiusKm || 5.0,
    mode: mapPinMode || 'location',
    compare_active: false
  });
}

function confirmPendingReferencePoint() {
  if (pendingReferencePoint) {
    const [lon, lat] = pendingReferencePoint;
    pendingReferencePoint = null;
    currentRefProp = null;
    const bubble = document.getElementById('in-map-confirm-bubble');
    if (bubble) bubble.style.display = 'none';
    const bar = document.getElementById('ref-confirm-bar');
    if (bar) bar.style.display = 'none';
    setReferencePoint(lon, lat, true, false);

    // Synchronize to Streamlit analytics cards and table below map
    try {
      var u = new URL(window.parent.location.href);
      u.searchParams.set('map_ref_lat', lat.toFixed(6));
      u.searchParams.set('map_ref_lon', lon.toFixed(6));
      u.searchParams.set('map_ref_radius', currentRadiusKm);
      window.parent.history.replaceState({}, '', u.toString());
    } catch(e) {
      console.warn('Sync to Streamlit error:', e);
    }
    triggerStreamlitSync();
  }
}

function cancelPendingReferencePoint() {
  pendingReferencePoint = null;
  const bubble = document.getElementById('in-map-confirm-bubble');
  if (bubble) bubble.style.display = 'none';
  const bar = document.getElementById('ref-confirm-bar');
  if (bar) bar.style.display = 'none';
  updateDeckLayers();
}

let hoverRaf = null;
function handleMapHover(info) {
  // If reference point already set, do not move preview circle
  if (referencePoint) return;
  if (!info || !info.coordinate) return;

  const [lon, lat] = info.coordinate;
  if (hoverRaf) cancelAnimationFrame(hoverRaf);
  hoverRaf = requestAnimationFrame(() => {
    mousePreviewCoord = [lon, lat];
    updateDeckLayers();
  });
}

function handleMapClick(info, event) {
  // 1. If user clicks on an existing property point, view its card ONLY (keeps reference point and radius intact)
  if (info && info.object && info.layer && (info.layer.id === 'point-icons' || info.layer.id === 'point-badges')) {
    cancelPendingReferencePoint();
    showPropertyCard(info.object, true);
    return;
  }

  // 2. If user clicks on the map background, show anchored confirmation bubble and radius preview!
  if (info && info.coordinate) {
    const [lon, lat] = info.coordinate;
    pendingReferencePoint = [lon, lat];

    const coordEl = document.getElementById('bubble-coord-val');
    const radiusEl = document.getElementById('bubble-radius-val');
    if (coordEl) coordEl.innerText = `${lat.toFixed(5)}, ${lon.toFixed(5)}`;
    if (radiusEl) radiusEl.innerText = formatRadiusDisplay(currentRadiusKm);

    updateDeckLayers();
    updateConfirmBubblePosition();
  }
}

function setInspectionRadius(radiusKm, btnEl, syncSlider = true) {
  currentRadiusKm = Math.max(0.05, Math.min(20, Number(radiusKm) || 5));
  if (syncSlider) {
    updateRadiusSliderUi(currentRadiusKm);
  }

  if (referencePoint) {
    setReferencePoint(referencePoint[0], referencePoint[1]);
  } else {
    const disp = formatRadiusDisplay(currentRadiusKm);
    const statusEl = document.getElementById('radius-status-text');
    if (statusEl) {
      statusEl.innerHTML = `คลิกบนแผนที่เพื่อกำหนดจุดอ้างอิง (รัศมี ${disp})`;
    }
    const countEl = document.getElementById('points-count');
    if (countEl) {
      countEl.innerText = `คลิกบนแผนที่เพื่อกำหนดจุดอ้างอิง (รัศมี ${disp})`;
    }
    updateDeckLayers();
    scheduleParentKpiUpdate();
  }
  notifyParentFilterChange();
}

function scrollParentPage(target) {
  try {
    const pWin = window.parent;
    const pDoc = pWin && pWin.document;
    if (!pDoc) return;

    const scrollEl =
      pDoc.querySelector('section[data-testid="stMain"]') ||
      pDoc.querySelector('div[data-testid="stAppViewContainer"]') ||
      pDoc.scrollingElement ||
      pDoc.documentElement;

    if (target === 'top') {
      if (scrollEl && typeof scrollEl.scrollTo === 'function') {
        scrollEl.scrollTo({ top: 0, behavior: 'smooth' });
      }
      if (typeof pWin.scrollTo === 'function') {
        pWin.scrollTo({ top: 0, behavior: 'smooth' });
      }
      return;
    }

    // Scroll down to Median analytics cards / nearby table right below the map
    const anchor =
      pDoc.getElementById('map-active-filters-banner') ||
      pDoc.getElementById('median-card-1') ||
      pDoc.getElementById('median-table-title');
    if (anchor && typeof anchor.scrollIntoView === 'function') {
      anchor.scrollIntoView({ behavior: 'smooth', block: 'start' });
      return;
    }
    if (scrollEl && typeof scrollEl.scrollBy === 'function') {
      scrollEl.scrollBy({ top: 620, behavior: 'smooth' });
    } else if (typeof pWin.scrollBy === 'function') {
      pWin.scrollBy({ top: 620, behavior: 'smooth' });
    }
  } catch (_e) {}
}

function setBasemapStyle(styleName) {
  if (typeof _userInteractedWithMap !== 'undefined') _userInteractedWithMap = true;
  if (typeof dismissInstantMapBackdrop === 'function') dismissInstantMapBackdrop();
  currentStyle = styleName;
  updateActiveButtons(styleName);
  updateDeckLayers();
  document.getElementById('map-style-controls')?.classList.remove('open');
}

async function initMap() {
  try {
    if (!window.NovaMapCache) {
      const _builderUrl = '/app/static/map_cache_builder.js?v=' + encodeURIComponent(cacheBuilderVerToken || '1');
      await _loadScriptAsync(typeof resolveNovaStaticUrl === 'function' ? resolveNovaStaticUrl(_builderUrl) : _builderUrl);
    }

    let _lut = { co: [], ty: [], pv: [], st: [], rg: [], dt: [], subdt: [], prj: [], plaintiff: [], co_rgb: [] };
    let data = [];
    const hasInlinePayload = !!(csvBase64 && csvBase64.length > 0);

    if (!hasInlinePayload && window.NovaMapCache) {
      // Hydrate boundaries immediately if already cached on parent from Welcome Screen
      const pBound = window.NovaMapCache.getParentBoundaryCache();
      if (pBound) {
        if (pBound.provinces && (!window.ALL_PROVINCES_BOUNDARIES || Object.keys(window.ALL_PROVINCES_BOUNDARIES).length === 0)) {
          window.ALL_PROVINCES_BOUNDARIES = pBound.provinces;
        }
        if (pBound.subdistricts && (!window.ALL_SUBDISTRICTS_BOUNDARIES || Object.keys(window.ALL_SUBDISTRICTS_BOUNDARIES).length === 0)) {
          window.ALL_SUBDISTRICTS_BOUNDARIES = pBound.subdistricts;
        }
        if (currentSelectedProv && currentSelectedProv !== '__ALL__' && (!boundaryGeoJson || !boundaryGeoJson.features)) {
          try { updateDistrictSubdistrictBoundaries(); } catch(e) {}
        }
      }

      let cacheObj = window.NovaMapCache.getValidParentCache(dataMtimeToken);
      if (cacheObj) {
        // Fast 0ms path: hide loader immediately before constructing DeckGL
        loader.style.display = 'none';
      } else {
        loaderText.innerText = "กำลังโหลดข้อมูลพิกัดแผนที่...";
        const resolvedPayloadUrl = (mapPayloadUrl && mapPayloadUrl !== ("MAP_PAYLOAD_URL_" + "PLACEHOLDER")) ? mapPayloadUrl : "";
        if (resolvedPayloadUrl && typeof window.NovaMapCache.fetchAndBuildParentCache === 'function') {
          cacheObj = await window.NovaMapCache.fetchAndBuildParentCache(
            dataMtimeToken,
            resolvedPayloadUrl,
            (_pct, msg) => { loaderText.innerText = msg; }
          );
        } else {
          throw new Error('ไม่สามารถโหลดไฟล์แคชข้อมูลแผนที่ได้ กรุณารีเฟรชหน้าเว็บ');
        }
      }

      _lut = cacheObj.lut;
      data = cacheObj.data;
      cachedData = data;
      window._activeMapCacheObj = cacheObj;
      const _isIOSCache = !!(window.NovaMapCache && typeof window.NovaMapCache.isIOSOrIPadOS === 'function' && window.NovaMapCache.isIOSOrIPadOS());
      if (cacheObj.idExactLookupMap && cacheObj.idStrippedLookupMap) {
        idExactLookupMap = cacheObj.idExactLookupMap;
        idStrippedLookupMap = cacheObj.idStrippedLookupMap;
      } else if (!_isIOSCache) {
        buildIdLookupIndex(data);
      } else {
        idExactLookupMap = null;
        idStrippedLookupMap = null;
      }
      spatialGrid = cacheObj.spatialGrid;
      applyPrebuiltProjectIndex(cacheObj.projIndex);
      restoreInMapFiltersFromParentUrl();
      initInMapFilterChips(_lut, data, cacheObj.typeCounts);
    } else {
      // Inline payload path (custom imports, filtered subsets, or static-write fallback)
      loaderText.innerText = "GZIP: ถอดรหัส และ Decompress ข้อมูลพิกัด...";
      const [lutJsonStr, csvText] = await Promise.all([
        decompressGzip(lookupBase64).catch(e => { console.warn('Lookup decode failed', e); return null; }),
        decompressGzip(csvBase64)
      ]);
      if (lutJsonStr) {
        try { _lut = JSON.parse(lutJsonStr); } catch(e) { console.warn('Lookup JSON parse failed', e); }
      }

      buildSamProjectOptions(null, _lut);
      restoreInMapFiltersFromParentUrl();
      initInMapFilterChips(_lut);

      loaderText.innerText = "กำลังประมวลผลตารางพิกัด (Parsing CSV)...";
      data = d3.csvParse(csvText);

      loaderText.innerText = "กำลังจัดเตรียมจุดแสดงผลพิกัด...";
      if (window.NovaMapCache && typeof window.NovaMapCache.hydrateMapRows === 'function') {
        window.NovaMapCache.hydrateMapRows(data, _lut);
      }

      cachedData = data;
      window._activeMapCacheObj = null;
      buildIdLookupIndex(data);
      spatialGrid = buildSpatialGrid(data);
      buildSamProjectOptions(data, _lut);
      initInMapFilterChips(_lut, data);
    }
    currentNearbyData = [];
    currentCoordMap = new Map();
    setupParentTabListeners();
    scheduleParentKpiUpdate();

    const legendBox = document.getElementById('legend-items-box');
    if (legendBox) {
      initialCompanyLegendHtml = legendBox.innerHTML;
    }

    loaderText.innerText = "กำลังเริ่มต้นแผนที่ (WebGL)...";

    if (mapPinMode === 'location') {
      applyInMapFilters(true);
    } else {
      const ptCountEl = document.getElementById('points-count');
      if (ptCountEl) ptCountEl.innerText = `คลิกบนแผนที่เพื่อกำหนดจุดอ้างอิง (รัศมี ${currentRadiusKm} กม.)`;
      const radStatusEl = document.getElementById('radius-status-text');
      if (radStatusEl) radStatusEl.innerHTML = `คลิกบนแผนที่เพื่อกำหนดจุดอ้างอิง (รัศมี ${currentRadiusKm} กม.)`;
      updateLegendContent();
    }
    const overlapInit = document.getElementById('legend-overlap-text');
    if (overlapInit) overlapInit.innerHTML = `ยังไม่ได้เลือกจุดอ้างอิง`;

    updateActiveButtons(currentStyle);

    const basemapLayer = createBasemapLayer(currentStyle);
    const scatterLayer = createPointLayer([]);

    let initialLon = 100.5;
    let initialLat = 13.5;
    let initialZoom = 5.2;

    const initLatNum = parseFloat(initRefLatStr);
    const initLonNum = parseFloat(initRefLonStr);
    const initRadNum = parseFloat(initRadiusStr);

    if (!isNaN(initRadNum) && initRadNum > 0) {
      currentRadiusKm = Math.max(0.05, Math.min(20, initRadNum));
      updateRadiusSliderUi(currentRadiusKm);
    }

    if (!isNaN(initLatNum) && !isNaN(initLonNum) && initLatNum > 0 && initLonNum > 0) {
      initialLat = initLatNum;
      initialLon = initLonNum;
      initialZoom = calculateZoomForRadius(initLatNum, currentRadiusKm);
    } else if (boundaryGeoJson && boundaryGeoJson.features && boundaryGeoJson.features.length > 0) {
      // Auto-center view to the selected boundary
      let minLon = Infinity, minLat = Infinity, maxLon = -Infinity, maxLat = -Infinity;
      function scanCoords(coords) {
        if (!Array.isArray(coords)) return;
        if (typeof coords[0] === 'number' && typeof coords[1] === 'number') {
          const lon = coords[0], lat = coords[1];
          if (lon < minLon) minLon = lon;
          if (lon > maxLon) maxLon = lon;
          if (lat < minLat) minLat = lat;
          if (lat > maxLat) maxLat = lat;
        } else {
          for (let i = 0; i < coords.length; i++) scanCoords(coords[i]);
        }
      }
      boundaryGeoJson.features.forEach(f => {
        if (f.geometry && f.geometry.coordinates) scanCoords(f.geometry.coordinates);
      });
      if (minLon !== Infinity && maxLon !== -Infinity) {
        initialLon = (minLon + maxLon) / 2;
        initialLat = (minLat + maxLat) / 2;
        const maxDiff = Math.max(maxLon - minLon, maxLat - minLat);
        if (maxDiff > 2.0) initialZoom = 7.5;
        else if (maxDiff > 1.0) initialZoom = 8.8;
        else if (maxDiff > 0.5) initialZoom = 9.8;
        else if (maxDiff > 0.2) initialZoom = 11.2;
        else if (maxDiff > 0.08) initialZoom = 12.5;
        else initialZoom = 13.5;
      }
    }

    currentViewState = {
      longitude: initialLon,
      latitude: initialLat,
      zoom: initialZoom,
      minZoom: 4,
      maxZoom: 20,
      bearing: 0,
      pitch: 0
    };

    // Stitch preloaded Thailand basemap tiles into the Frame-0 instant 2D canvas & pre-decode ImageBitmaps in Tab 2 realm
    if (typeof prepareInstantMapBackdropAndPredecode === 'function') {
      prepareInstantMapBackdropAndPredecode(currentStyle, currentViewState);
    }

    const initialBoundaryL = createBoundaryLayer();
    const initialLayers = [basemapLayer];
    if (initialBoundaryL) initialLayers.push(initialBoundaryL);

    const _isIOSDevice = !!(window.NovaMapCache && typeof window.NovaMapCache.isIOSOrIPadOS === 'function' && window.NovaMapCache.isIOSOrIPadOS());
    deckglInstance = new deck.DeckGL({
      container: 'map',
      mapboxApiAccessToken: false,
      useDevicePixels: _isIOSDevice ? 1 : true,
      glOptions: _isIOSDevice ? { antialias: false, preserveDrawingBuffer: false, powerPreference: 'default' } : undefined,
      viewState: currentViewState,
      controller: true,
      getTooltip: getMapTooltip,
      onHover: handleMapHover,
      onClick: handleMapClick,
      onViewStateChange: ({ viewState, interactionState }) => {
        if (typeof _userInteractedWithMap !== 'undefined') _userInteractedWithMap = true;
        if (typeof dismissInstantMapBackdrop === 'function') dismissInstantMapBackdrop();
        if (interactionState && (interactionState.isDragging || interactionState.isPanning || interactionState.isZooming || interactionState.isRotating)) {
          if (mapAnimRaf) {
            cancelAnimationFrame(mapAnimRaf);
            mapAnimRaf = null;
          }
        }
        currentViewState = viewState;
        deckglInstance.setProps({ viewState: currentViewState });
        updateCompass(viewState.bearing || 0);
        try { updateConfirmBubblePosition(); } catch(e) {}
        try { updateSvgBoundaries(); } catch(e) {}
        try { updatePropertyCardPosition(); } catch(e) {}
        return viewState;
      },
      layers: initialLayers
    });

    // Ensure deck.gl tooltip is always attached to document.body,
    // guaranteeing it stays above boundary-svg (z-index: 10) and all overlays
    try {
      var mapContainer = document.getElementById('map');
      if (mapContainer) {
        _ttObserverInstance = new MutationObserver(function(mutations) {
          var tt = mapContainer.querySelector('.deck-tooltip');
          if (tt) {
            tt.style.zIndex = '999999';
            document.body.appendChild(tt);
          }
        });
        _ttObserverInstance.observe(mapContainer, { childList: true });

        // Prevent uncaught WebGL context loss on iPadOS Safari from crashing the tab
        try {
          const glCanvas = mapContainer.querySelector('canvas');
          if (glCanvas) {
            glCanvas.addEventListener('webglcontextlost', (ev) => {
              ev.preventDefault();
            }, false);
            glCanvas.addEventListener('webglcontextrestored', () => {
              _triggerImmediateMapRedraw();
            }, false);
          }
        } catch (_e) {}

        // Immediately resize & redraw DeckGL on the exact first frame Tab 2 becomes visible (0x0 -> real size)
        if (typeof ResizeObserver === 'function') {
          let lastW = mapContainer.clientWidth || 0;
          let lastH = mapContainer.clientHeight || 0;
          _mapResizeObserver = new ResizeObserver((entries) => {
            const rect = entries && entries[0] && entries[0].contentRect;
            const w = rect ? Math.round(rect.width) : (mapContainer.clientWidth || 0);
            const h = rect ? Math.round(rect.height) : (mapContainer.clientHeight || 0);
            if (w > 0 && h > 0 && (w !== lastW || h !== lastH)) {
              lastW = w;
              lastH = h;
              _triggerImmediateMapRedraw();
            }
          });
          _mapResizeObserver.observe(mapContainer);
        }

        // If Tab 2 is mounted hidden (e.g. ?portal=skip while Tab 1 is open), warm tiles & stitch instant backdrop in background
        if ((mapContainer.clientWidth || 0) === 0 && window.NovaMapCache && typeof window.NovaMapCache.preloadBasemapTiles === 'function') {
          window.NovaMapCache.preloadBasemapTiles(currentStyle, {
            lon: initialLon,
            lat: initialLat,
            zoom: initialZoom,
            height: 870,
            concurrency: 16
          }).then(() => {
            if (typeof prepareInstantMapBackdropAndPredecode === 'function') {
              prepareInstantMapBackdropAndPredecode(currentStyle, currentViewState);
            }
          }).catch(() => {});
        }
      }
    } catch(e) {}

    setTimeout(() => {
      try { updateSvgBoundaries(); } catch(e) {}
      try { updateConfirmBubblePosition(); } catch(e) {}
      try { updatePropertyCardPosition(); } catch(e) {}
      try { initProvinceDropdown(); } catch(e) {}
      try { initDistrictDropdown(); } catch(e) {}
      try { initSubdistrictDropdown(); } catch(e) {}
    }, 80);

    setTimeout(() => {
      try { hideParentSyncButton(); } catch(e) {}
    }, 400);

    if (boundaryGeoJson && boundaryGeoJson.features && boundaryGeoJson.features.length > 0) {
      setTimeout(() => {
        try {
          smoothFlyTo(initialLon, initialLat, initialZoom, 1200);
        } catch(e) {}
      }, 80);
    }

    loader.style.display = 'none';
    // Defer 8 MB GeoJSON boundary scripts slightly so initial basemap tiles & WebGL textures get full priority
    _deferredBoundaryTimer = setTimeout(() => {
      _deferredBoundaryTimer = null;
      if (typeof window.requestIdleCallback === 'function') {
        window.requestIdleCallback(() => { try { loadBoundaryScriptsInBackground(); } catch(_e) {} }, { timeout: 1500 });
      } else {
        try { loadBoundaryScriptsInBackground(); } catch(_e) {}
      }
    }, 700);

    const effRefId = currentRefId || (initRefIdStr && initRefIdStr !== ("INIT_REF_ID_" + "PLACEHOLDER") ? initRefIdStr : "");
    if (effRefId && effRefId.trim()) {
      const inp = document.getElementById('inmap-prop-search-input');
      const clr = document.getElementById('inmap-clear-search-btn');
      if (inp) inp.value = effRefId.trim();
      if (clr) clr.style.display = 'inline-flex';
      if (idExactLookupMap) {
        currentRefProp = idExactLookupMap.get(effRefId.trim().toLowerCase()) || null;
      } else if (cachedData && cachedData.length > 0) {
        currentRefProp = cachedData.find(x => (x._id || '').trim() === effRefId.trim()) || null;
      }
    }

    if (initialCompareIds && initialCompareIds.length > 0 && cachedData && cachedData.length > 0) {
      if (!idExactLookupMap) buildIdLookupIndex(cachedData);
      initialCompareIds.forEach(rawId => {
        const key = String(rawId || '').trim().toLowerCase();
        const d = (key && idExactLookupMap) ? idExactLookupMap.get(key) : null;
        if (d && d._id) {
          selectedComparisonProps.set(String(d._id).trim(), {
            id: String(d._id).trim(),
            _id: String(d._id).trim(),
            lat: parseFloat(d.lat),
            lon: parseFloat(d.lon),
            title: d._title || (d._project && d._project !== '-' ? d._project : d._type) || '',
            price: d._price_str || '',
            company: d._company || '',
            type: d._type || '',
            sqw: d._sqw || 0,
            sqm: d._sqm || 0
          });
        }
      });
      updateComparisonUi();
      updateDeckLayers();
    }

    renderSavedCoordinatesPills();

    if (!isNaN(initLatNum) && !isNaN(initLonNum) && initLatNum > 0 && initLonNum > 0) {
      setTimeout(() => {
        try {
          setReferencePoint(initLonNum, initLatNum, false, false);
          setupParentTabListeners();
          scheduleParentKpiUpdate();
          renderSavedCoordinatesPills();
        } catch(e) {
          console.warn('Deferred setReferencePoint warning:', e);
        }
      }, 60);
    } else {
      setTimeout(() => {
        setupParentTabListeners();
        scheduleParentKpiUpdate();
      }, 100);
    }
  } catch(err) {
    loader.style.display = 'flex';
    loaderText.innerHTML = `<span style="color: #ef4444;"><i class="fa-solid fa-circle-xmark" style="margin-right: 6px;"></i>โหลดแผนที่ล้มเหลว: ${escapeHtml(err && err.message ? err.message : String(err))}</span> <button type="button" onclick="loaderText.innerText='กำลังลองโหลดแผนที่ใหม่...'; initMap();" style="margin-left: 10px; padding: 4px 12px; border-radius: 9999px; border: none; background: #059669; color: #ffffff; font-weight: 700; font-size: 12px; cursor: pointer;">ลองโหลดใหม่</button>`;
    console.error(err);
  }
}

initMap();
