// ==========================================
// SEARCHABLE COMBOBOX ENGINE (PROVINCE, DISTRICT, SUBDISTRICT, PROJECT)
// ==========================================
let allProjectsList = [];
let allSamProjectsList = [];
let allOtherProjectsList = [];
let samProjectStatsMap = new Map(); // stores { sam: number, other: number, normKey: string }
let globalProjToNormMap = new Map();
let globalNormToItemsMap = new Map();
let globalProjToItemsMap = new Map();
let globalNormToCompaniesMap = new Map();
let globalProjToCompaniesMap = new Map();
let projCompanyCountsMap = new Map();
let normKeyToCanonicalMap = new Map();
let cachedScopedProjectsKey = '';
let cachedScopedProjectsList = null;
let currentActiveCombo = null;

function applyPrebuiltProjectIndex(idx) {
  if (!idx) return;
  allSamProjectsList = idx.allSamProjectsList || [];
  allOtherProjectsList = idx.allOtherProjectsList || [];
  allProjectsList = idx.allProjectsList || [];
  samProjectStatsMap = idx.samProjectStatsMap || new Map();
  globalProjToNormMap = idx.globalProjToNormMap || new Map();
  globalNormToItemsMap = idx.globalNormToItemsMap || new Map();
  globalProjToItemsMap = idx.globalProjToItemsMap || new Map();
  globalNormToCompaniesMap = idx.globalNormToCompaniesMap || new Map();
  globalProjToCompaniesMap = idx.globalProjToCompaniesMap || new Map();
  projCompanyCountsMap = idx.projCompanyCountsMap || new Map();
  normKeyToCanonicalMap = idx.normKeyToCanonicalMap || new Map();
  cachedScopedProjectsKey = '';
  cachedScopedProjectsList = null;
  syncComboboxInputs();
}

function buildSamProjectOptions(data, lut) {
  if (window.NovaMapCache && typeof window.NovaMapCache.buildProjectIndex === 'function') {
    applyPrebuiltProjectIndex(window.NovaMapCache.buildProjectIndex(data, lut));
    return;
  }
  syncComboboxInputs();
}

function isProjectMatchingCompanySharing(d) {
  if (!d) return false;
  const p = (d._project || '').trim();
  if (!p || isInvalidProjectName(p)) return false;

  if (inMapFilterState && inMapFilterState.companies && inMapFilterState.companies.size >= 2) {
    const selectedCos = inMapFilterState.companies;
    const nk = d._normKey || globalProjToNormMap.get(p) || normalizeProjectKeyword(p);
    const coSet = (nk ? globalNormToCompaniesMap.get(nk) : null) || globalProjToCompaniesMap.get(p);
    if (!coSet) return false;

    let matchCount = 0;
    selectedCos.forEach(co => {
      if (coSet.has(co)) matchCount++;
    });
    // If 2 companies selected (e.g. SAM and BAM), require both to be present in this project
    if (selectedCos.size === 2) {
      return matchCount === 2;
    }
    // If 3+ companies selected, require at least 2 of the selected companies to share the project
    return matchCount >= 2;
  }

  return true;
}

function getScopedProjectsList() {
  const hasProv = !!(currentSelectedProv && currentSelectedProv.trim() !== '' && currentSelectedProv !== '__ALL__');
  const hasDist = !!(currentSelectedDist && currentSelectedDist.trim() !== '' && currentSelectedDist !== '__ALL__');
  const hasSub = !!(currentSelectedSubdist && currentSelectedSubdist.trim() !== '' && currentSelectedSubdist !== '__ALL__');
  const hasCo = !!(inMapFilterState && inMapFilterState.companies && inMapFilterState.companies.size > 0);
  const hasTy = !!(inMapFilterState && inMapFilterState.types && inMapFilterState.types.size > 0);
  const hasOnlyProj = !!(inMapFilterState && inMapFilterState.onlyWithProject);

  if (!hasProv && !hasDist && !hasSub && !hasCo && !hasTy && !hasOnlyProj) {
    return allProjectsList || [];
  }

  const cacheKey = [
    hasProv ? currentSelectedProv : '',
    hasDist ? currentSelectedDist : '',
    hasSub ? currentSelectedSubdist : '',
    hasCo ? Array.from(inMapFilterState.companies).sort().join(',') : '',
    hasTy ? Array.from(inMapFilterState.types).sort().join(',') : '',
    hasOnlyProj ? 'onlyProj' : ''
  ].join('||');

  if (cachedScopedProjectsList && cachedScopedProjectsKey === cacheKey) {
    return cachedScopedProjectsList;
  }

  const cleanDist = hasDist ? currentSelectedDist.split(' (')[0].trim() : '';
  const cleanSub = hasSub ? currentSelectedSubdist.split(' (')[0].trim() : '';
  const matchedCanonicals = new Set();
  if (cachedData && cachedData.length > 0) {
    for (let i = 0; i < cachedData.length; i++) {
      const d = cachedData[i];
      if (hasProv && d._prov !== currentSelectedProv) continue;
      if (hasDist && d._district !== currentSelectedDist && d._district !== cleanDist) continue;
      if (hasSub && d._subdistrict !== currentSelectedSubdist && d._subdistrict !== cleanSub) continue;
      if (hasCo && !inMapFilterState.companies.has(d._company)) continue;
      if (hasTy && !inMapFilterState.types.has(d._type)) continue;

      if (hasOnlyProj) {
        const p = (d._project || '').trim();
        if (!p || p === '-' || isInvalidProjectName(p)) continue;
        if (inMapFilterState.companies && inMapFilterState.companies.size >= 2) {
          if (!isProjectMatchingCompanySharing(d)) continue;
        }
      }

      const nk = d._normKey;
      if (nk) {
        const cName = normKeyToCanonicalMap.get(nk);
        if (cName) matchedCanonicals.add(cName);
      }
    }
  }

  const scopedList = (allProjectsList || []).filter(p => matchedCanonicals.has(p));
  cachedScopedProjectsKey = cacheKey;
  cachedScopedProjectsList = scopedList;
  return scopedList;
}

function closeAllComboboxes() {
  ['prov', 'dist', 'subdist', 'prj'].forEach(type => {
    const menu = document.getElementById(`combo-menu-${type}`);
    const chev = document.getElementById(`combo-chevron-${type}`);
    if (menu) menu.style.display = 'none';
    if (chev) chev.classList.remove('open');
  });
  window._showAllOtherPrj = false;
  const locGroup = document.getElementById('map-location-group');
  if (locGroup) locGroup.style.zIndex = '1000';
  const subrow2 = document.querySelector('.map-filter-controls-stack > .map-filter-subrow:nth-child(2)');
  if (subrow2) subrow2.style.zIndex = '900';
  const subrow3 = document.querySelector('.map-filter-controls-stack > .map-filter-subrow:nth-child(3)');
  if (subrow3) subrow3.style.zIndex = '800';
  const prjGroup = document.getElementById('map-project-group');
  if (prjGroup) prjGroup.style.zIndex = '';
  currentActiveCombo = null;
  syncComboboxInputs();
}

function toggleStyleDropdown(e) {
  if (e) e.stopPropagation();
  document.getElementById('map-style-controls')?.classList.toggle('open');
}

// ==========================================
// OpenStreetMap Nominatim Place Search
// ==========================================
let placeSearchTimer = null;
let placeSearchAbortCtrl = null;
const placeSearchCache = new Map();

function handlePlaceSearchInput(val) {
  const clearBtn = document.getElementById('place-search-clear');
  if (clearBtn) clearBtn.style.display = val.trim().length > 0 ? 'inline-block' : 'none';

  if (placeSearchTimer) {
    clearTimeout(placeSearchTimer);
    placeSearchTimer = null;
  }

  const q = val.trim();
  if (q.length < 3) {
    hidePlaceSearchResults();
    return;
  }

  placeSearchTimer = setTimeout(() => {
    executePlaceSearch(q, false);
  }, 450);
}

function handlePlaceSearchKeydown(e) {
  if (e.key === 'Enter') {
    e.preventDefault();
    if (placeSearchTimer) {
      clearTimeout(placeSearchTimer);
      placeSearchTimer = null;
    }
    const q = (e.target.value || '').trim();
    if (q.length >= 2) {
      executePlaceSearch(q, true);
    }
  } else if (e.key === 'Escape') {
    hidePlaceSearchResults();
  }
}

function triggerPlaceSearch() {
  const inp = document.getElementById('place-search-input');
  if (!inp) return;
  const q = (inp.value || '').trim();
  if (q.length >= 2) {
    if (placeSearchTimer) {
      clearTimeout(placeSearchTimer);
      placeSearchTimer = null;
    }
    executePlaceSearch(q, true);
  } else {
    inp.focus();
  }
}

function clearPlaceSearch() {
  const inp = document.getElementById('place-search-input');
  if (inp) {
    inp.value = '';
    inp.focus();
  }
  const clearBtn = document.getElementById('place-search-clear');
  if (clearBtn) clearBtn.style.display = 'none';
  const spinner = document.getElementById('place-search-spinner');
  if (spinner) spinner.style.display = 'none';
  if (placeSearchAbortCtrl) {
    placeSearchAbortCtrl.abort();
    placeSearchAbortCtrl = null;
  }
  hidePlaceSearchResults();
}

function hidePlaceSearchResults() {
  const resultsEl = document.getElementById('place-search-results');
  if (resultsEl) resultsEl.style.display = 'none';
}

function getPlaceCategoryIcon(item) {
  const type = (item.type || '').toLowerCase();
  const cat = (item.class || '').toLowerCase();
  if (type.includes('station') || type.includes('subway') || type.includes('halt') || type.includes('stop') || cat === 'railway' || cat === 'public_transport') {
    return 'fa-train-subway';
  }
  if (type.includes('hospital') || type.includes('clinic') || type.includes('pharmacy') || type.includes('doctor')) {
    return 'fa-hospital';
  }
  if (type.includes('school') || type.includes('university') || type.includes('college') || type.includes('kindergarten')) {
    return 'fa-graduation-cap';
  }
  if (type.includes('mall') || type.includes('supermarket') || type.includes('department_store') || cat === 'shop') {
    return 'fa-bag-shopping';
  }
  if (type.includes('airport') || type.includes('aerodrome')) {
    return 'fa-plane-departure';
  }
  if (type.includes('place_of_worship') || type.includes('temple') || type.includes('monastery')) {
    return 'fa-place-of-worship';
  }
  if (type.includes('park') || type.includes('garden') || cat === 'leisure') {
    return 'fa-tree';
  }
  if (type.includes('hotel') || type.includes('resort') || cat === 'tourism') {
    return 'fa-hotel';
  }
  if (cat === 'amenity' || cat === 'building') {
    return 'fa-building';
  }
  return 'fa-location-dot';
}

async function executePlaceSearch(query, autoSelectIfSingle = false) {
  if (!query) return;
  const spinner = document.getElementById('place-search-spinner');
  const clearBtn = document.getElementById('place-search-clear');
  const resultsEl = document.getElementById('place-search-results');

  if (spinner) spinner.style.display = 'inline-block';
  if (clearBtn) clearBtn.style.display = 'none';

  if (placeSearchAbortCtrl) {
    placeSearchAbortCtrl.abort();
  }
  placeSearchAbortCtrl = new AbortController();

  try {
    const cacheKey = query.trim().toLowerCase();
    let data = placeSearchCache.get(cacheKey);
    if (!data) {
      const url = `https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(query)}&countrycodes=th&accept-language=th&addressdetails=1&limit=6`;
      const resp = await fetch(url, {
        signal: placeSearchAbortCtrl.signal,
        headers: {
          'Accept': 'application/json'
        }
      });
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      data = await resp.json();
      if (Array.isArray(data)) {
        if (placeSearchCache.size >= 64) {
          const firstKey = placeSearchCache.keys().next().value;
          placeSearchCache.delete(firstKey);
        }
        placeSearchCache.set(cacheKey, data);
      }
    }

    if (!Array.isArray(data) || data.length === 0) {
      if (resultsEl) {
        resultsEl.innerHTML = `<div class="place-results-empty"><i class="fa-solid fa-circle-exclamation" style="margin-right:4px;"></i>ไม่พบสถานที่ "${escapeHtml(query)}"</div>`;
        resultsEl.style.display = 'flex';
      }
      return;
    }

    if (autoSelectIfSingle && data.length === 1) {
      selectPlaceResult(data[0]);
      return;
    }

    if (resultsEl) {
      resultsEl.innerHTML = '';
      data.forEach(item => {
        const row = document.createElement('div');
        row.className = 'place-result-item';

        const iconCls = getPlaceCategoryIcon(item);
        const displayName = item.display_name || '';
        const parts = displayName.split(',').map(s => s.trim());
        const mainTitle = parts[0] || query;
        const subDesc = parts.slice(1, 4).join(', ') || parts.slice(1).join(', ') || 'ประเทศไทย';

        row.innerHTML = `
          <i class="fa-solid ${iconCls} place-result-icon"></i>
          <div class="place-result-info">
            <div class="place-result-title">${escapeHtml(mainTitle)}</div>
            <div class="place-result-desc">${escapeHtml(subDesc)}</div>
          </div>
        `;
        row.onclick = () => selectPlaceResult(item);
        resultsEl.appendChild(row);
      });
      resultsEl.style.display = 'flex';
    }
  } catch(err) {
    if (err.name !== 'AbortError') {
      console.warn('Place search error:', err);
      if (resultsEl) {
        resultsEl.innerHTML = `<div class="place-results-empty"><i class="fa-solid fa-triangle-exclamation" style="color:#ef4444; margin-right:4px;"></i>ค้นหาไม่สำเร็จ กรุณาลองใหม่อีกครั้ง</div>`;
        resultsEl.style.display = 'flex';
      }
    }
  } finally {
    if (spinner) spinner.style.display = 'none';
    const inp = document.getElementById('place-search-input');
    if (clearBtn && inp && inp.value.trim().length > 0) {
      clearBtn.style.display = 'inline-block';
    }
  }
}

function selectPlaceResult(item) {
  const lat = parseFloat(item.lat);
  const lon = parseFloat(item.lon);
  if (isNaN(lat) || isNaN(lon)) return;

  const displayName = item.display_name || '';
  const mainTitle = displayName.split(',')[0].trim() || 'สถานที่ที่เลือก';

  const inp = document.getElementById('place-search-input');
  if (inp) inp.value = mainTitle;
  const clearBtn = document.getElementById('place-search-clear');
  if (clearBtn) clearBtn.style.display = 'inline-block';

  hidePlaceSearchResults();

  setReferencePoint(lon, lat, true, true);
  showToast(`<i class="fa-solid fa-location-dot" style="color:#10b981; margin-right:6px;"></i>ปักหมุดอ้างอิง: <b>${escapeHtml(mainTitle)}</b> (รัศมี ${formatRadiusDisplay(currentRadiusKm)})`);
}

document.addEventListener('click', function(e) {
  const path = e.composedPath ? e.composedPath() : [];
  const clickedInsideCombo = path.some(el => el && el.classList && (
    el.classList.contains('combobox-container') ||
    el.classList.contains('combobox-menu') ||
    el.classList.contains('combobox-option') ||
    el.classList.contains('combobox-header-bar') ||
    el.classList.contains('map-loc-item')
  ));
  if (!clickedInsideCombo && !e.target.closest('.combobox-container') && !e.target.closest('.combobox-menu')) {
    closeAllComboboxes();
  }
  if (!e.target.closest('#map-style-controls')) {
    document.getElementById('map-style-controls')?.classList.remove('open');
  }
  if (!e.target.closest('#place-search-controls')) {
    hidePlaceSearchResults();
  }
});

function syncComboboxInputs() {
  const pInp = document.getElementById('inmap-province-input');
  if (pInp && currentActiveCombo !== 'prov') pInp.value = currentSelectedProv || '';

  const dInp = document.getElementById('inmap-district-input');
  if (dInp) {
    dInp.disabled = !currentSelectedProv;
    if (currentActiveCombo !== 'dist') dInp.value = currentSelectedDist || '';
    dInp.placeholder = currentSelectedProv ? 'ทุกอำเภอ/เขต' : 'เลือกจังหวัดก่อน';
  }

  const sInp = document.getElementById('inmap-subdistrict-input');
  if (sInp) {
    sInp.disabled = !currentSelectedDist;
    if (currentActiveCombo !== 'subdist') sInp.value = currentSelectedSubdist || '';
    sInp.placeholder = currentSelectedDist ? 'ทุกตำบล/แขวง' : 'เลือกอำเภอก่อน';
  }

  const prjInp = document.getElementById('inmap-project-input');
  if (prjInp) {
    const prjCount = inMapFilterState.samProjects ? inMapFilterState.samProjects.size : 0;
    const scopedList = getScopedProjectsList();
    const totalPrj = (scopedList && scopedList.length) ? scopedList.length : 0;

    const defaultLabel = `โครงการ (${totalPrj.toLocaleString()})`;

    let displayLabel = '';
    if (prjCount === 0) {
      displayLabel = '';
    } else if (prjCount === 1) {
      displayLabel = Array.from(inMapFilterState.samProjects)[0];
    } else {
      displayLabel = `โครงการ (${prjCount})`;
    }

    prjInp.placeholder = defaultLabel;
    prjInp.value = displayLabel;
    prjInp.title = prjCount > 0 ? (prjCount === 1 ? displayLabel : `เลือก ${prjCount} โครงการ`) : defaultLabel;

    // Dynamically adjust input width so it expands to comfortably fit the text without clipping
    const activeText = displayLabel || defaultLabel;
    const charLen = activeText.length;
    const dynamicWidth = Math.min(320, Math.max(120, charLen * 8.5 + 24));
    prjInp.style.width = `${Math.round(dynamicWidth)}px`;

    const prjClearBtn = document.getElementById('inmap-clear-project-btn');
    if (prjClearBtn) {
      prjClearBtn.style.display = prjCount > 0 ? 'inline-flex' : 'none';
    }
  }
}

function initProvinceDropdown() { syncComboboxInputs(); }
function initDistrictDropdown() { syncComboboxInputs(); }
function initSubdistrictDropdown() { syncComboboxInputs(); }

function getComboboxItems(type) {
  if (type === 'prov') {
    return (allProvincesList || []).filter(p => p && p !== '-' && p !== 'ไม่มีข้อมูล');
  } else if (type === 'dist') {
    if (!currentSelectedProv) return [];
    const distSet = new Set();
    if (cachedData && cachedData.length > 0) {
      cachedData.forEach(d => {
        if (d._prov === currentSelectedProv && d._district && d._district !== '-' && d._district !== 'ไม่มีข้อมูล') {
          distSet.add(d._district);
        }
      });
    }
    const boundariesDict = window.ALL_PROVINCES_BOUNDARIES || {};
    if (boundariesDict[currentSelectedProv] && boundariesDict[currentSelectedProv].district_labels) {
      boundariesDict[currentSelectedProv].district_labels.forEach(l => {
        if (l.name && l.name !== '-' && l.name !== 'ไม่มีข้อมูล') {
          distSet.add(l.name);
        }
      });
    }
    return Array.from(distSet).sort((a, b) => a.localeCompare(b, 'th'));
  } else if (type === 'subdist') {
    if (!currentSelectedDist) return [];
    const subdistSet = new Set();
    if (cachedData && cachedData.length > 0) {
      cachedData.forEach(d => {
        if (d._prov === currentSelectedProv && d._district === currentSelectedDist && d._subdistrict && d._subdistrict !== '-' && d._subdistrict !== 'ไม่มีข้อมูล') {
          subdistSet.add(d._subdistrict);
        }
      });
    }
    const subdistObj = getSubdistrictBoundaryForDistrict(currentSelectedProv, currentSelectedDist);
    if (subdistObj && subdistObj.district_labels) {
      subdistObj.district_labels.forEach(l => {
        if (l.name && l.name !== '-' && l.name !== 'ไม่มีข้อมูล') {
          subdistSet.add(l.name);
        }
      });
    }
    return Array.from(subdistSet).sort((a, b) => a.localeCompare(b, 'th'));
  } else if (type === 'prj') {
    return getScopedProjectsList();
  }
  return [];
}

function getCurrentComboboxValue(type) {
  if (type === 'prov') return currentSelectedProv;
  if (type === 'dist') return currentSelectedDist;
  if (type === 'subdist') return currentSelectedSubdist;
  if (type === 'prj') return inMapFilterState.samProject;
  return '';
}

function getComboboxAllLabel(type) {
  if (type === 'prov') return 'ทุกจังหวัด';
  if (type === 'dist') return 'ทุกอำเภอ/เขต';
  if (type === 'subdist') return 'ทุกตำบล/แขวง';
  if (type === 'prj') {
    const total = (allProjectsList && allProjectsList.length) ? allProjectsList.length : 0;
    return total > 0 ? `ทุกโครงการ (${total.toLocaleString()} โครงการ)` : 'ทุกโครงการ';
  }
  return 'ทั้งหมด';
}

// BRAND_TAG_RULES, getBrandSearchTag, and normalizeProjectKeyword are loaded from /app/static/map_cache_builder.js

function matchProjectSearchItem(itemName, rawQuery) {
  if (!rawQuery) return true;
  const lowItem = (itemName || '').toLowerCase();
  const lowQ = (rawQuery || '').toLowerCase().trim();
  if (lowItem.includes(lowQ)) return true;

  const stats = samProjectStatsMap.get(itemName);
  if (stats && stats.tag && stats.tag.toLowerCase().includes(lowQ)) return true;
  if (stats && stats.normKey && stats.normKey.includes(lowQ)) return true;

  const normItem = (stats && stats.normKey) ? stats.normKey : normalizeProjectKeyword(itemName);
  const normQ = normalizeProjectKeyword(rawQuery);
  if (!normQ) return false;
  return normItem.includes(normQ);
}

let projSearchDebounceTimer = null;
function onProjectSearchInput(val) {
  if (projSearchDebounceTimer) clearTimeout(projSearchDebounceTimer);
  projSearchDebounceTimer = setTimeout(() => {
    renderProjectOptionsList(val);
    projSearchDebounceTimer = null;
  }, 140);
}

function clearAllSamProjects(event) {
  if (event) {
    try { event.stopPropagation(); event.preventDefault(); } catch(e) {}
  }
  toggleProjectOption('', '');
  const s = document.getElementById('combo-menu-search-prj');
  if (s) {
    s.value = '';
    s.focus();
  }
}

function renderProjectOptionsList(query = '') {
  const list = document.getElementById('combo-options-list-prj');
  if (!list) return;

  const allItems = getScopedProjectsList();
  const cleanQuery = (query || '').trim().toLowerCase();
  let filtered = allItems;
  if (cleanQuery) {
    filtered = allItems.filter(item => matchProjectSearchItem(item, cleanQuery));
  }

  const selSet = inMapFilterState.samProjects || new Set();
  const isAll = (selSet.size === 0);

  const totalCount = allItems.length;

  let locScopeLabel = '';
  if (currentSelectedSubdist && currentSelectedSubdist !== '__ALL__') {
    locScopeLabel = `ต.${currentSelectedSubdist}`;
  } else if (currentSelectedDist && currentSelectedDist !== '__ALL__') {
    locScopeLabel = `อ.${currentSelectedDist}`;
  } else if (currentSelectedProv && currentSelectedProv !== '__ALL__') {
    locScopeLabel = `จ.${currentSelectedProv}`;
  }

  const selectedItems = [];
  const unselectedSam = [];
  const unselectedOther = [];

  for (let i = 0; i < filtered.length; i++) {
    const item = filtered[i];
    if (selSet.has(item)) {
      selectedItems.push(item);
    } else {
      const stats = samProjectStatsMap.get(item);
      if (stats && stats.sam > 0) {
        unselectedSam.push(item);
      } else {
        unselectedOther.push(item);
      }
    }
  }

  const totalSamCount = unselectedSam.length + selectedItems.filter(item => {
    const s = samProjectStatsMap.get(item);
    return s && s.sam > 0;
  }).length;

  const titleEl = document.getElementById('combo-header-title-prj');
  if (titleEl) {
    if (selSet.size > 0) {
      titleEl.innerHTML = `<i class="fa-solid fa-square-check" style="color:#059669;"></i> โครงการ (${selSet.size})`;
    } else if (cleanQuery) {
      titleEl.innerHTML = `<i class="fa-solid fa-magnifying-glass" style="color:#059669;"></i> โครงการ (${filtered.length.toLocaleString()})`;
    } else {
      titleEl.innerHTML = `<i class="fa-solid fa-city" style="color:#059669;"></i> โครงการ (${totalCount.toLocaleString()})`;
    }
  }
  const clearBtn = document.getElementById('combo-clear-btn-prj');
  if (clearBtn) {
    clearBtn.style.display = selSet.size > 0 ? 'inline-block' : 'none';
  }

  const renderItemBadges = (item, fallbackStats) => {
    const stats = samProjectStatsMap.get(item) || fallbackStats;
    const nk = (stats && stats.normKey) || normalizeProjectKeyword(item);
    const coCounts = projCompanyCountsMap.get(nk) || {};

    if (inMapFilterState.companies && inMapFilterState.companies.size >= 2) {
      const parts = [];
      inMapFilterState.companies.forEach(c => {
        const cnt = coCounts[c] || 0;
        const isSam = (c.toUpperCase() === 'SAM');
        const bg = isSam ? 'rgba(16,185,129,0.18)' : 'rgba(59,130,246,0.15)';
        const col = isSam ? '#047857' : '#1d4ed8';
        const border = isSam ? '1px solid rgba(16,185,129,0.35)' : '1px solid rgba(59,130,246,0.3)';
        parts.push(`<span style="font-size:9px; font-weight:700; background:${bg}; color:${col}; border:${border}; padding:1px 5px; border-radius:4px; margin-left:4px; flex-shrink:0;">${escapeHtml(c)}: ${cnt}</span>`);
      });
      return parts.join('');
    }
    if (stats && stats.sam > 0) {
      const samBadge = `<span style="font-size:9px; font-weight:800; background:rgba(16,185,129,0.18); color:#047857; border:1px solid rgba(16,185,129,0.35); padding:1px 6px; border-radius:4px; margin-left:6px; flex-shrink:0;">SAM: ${stats.sam}</span>`;
      const compBadge = stats.other > 0
        ? `<span style="font-size:9px; font-weight:600; background:rgba(100,116,139,0.14); color:#334155; padding:1px 5px; border-radius:4px; margin-left:4px; flex-shrink:0;">คู่แข่ง: ${stats.other}</span>`
        : `<span style="font-size:8.5px; color:#94a3b8; margin-left:4px; flex-shrink:0;">ไม่มีคู่แข่ง</span>`;
      return samBadge + compBadge;
    }
    const othCnt = stats ? stats.other : 1;
    return `<span style="font-size:9px; font-weight:600; background:rgba(100,116,139,0.12); color:#475569; padding:1px 5px; border-radius:4px; margin-left:6px; flex-shrink:0;">${othCnt} ทรัพย์</span>`;
  };

  let html = '';
  const safeCleanQueryAttr = escapeHtml(cleanQuery);

  // Option: "ทุกโครงการ"
  if (!cleanQuery || 'ทั้งหมด'.includes(cleanQuery) || 'ทุกโครงการ'.includes(cleanQuery)) {
    const totalLabel = totalCount > 0 ? `ทุกโครงการ (${totalCount.toLocaleString()})` : 'ทุกโครงการ';
    html += `<div class="combobox-option ${isAll ? 'selected' : ''}" data-proj="" data-query="${safeCleanQueryAttr}" onclick="toggleProjectOption(this.dataset.proj, this.dataset.query, event)" style="display:flex; align-items:center; font-weight:700; border-bottom:1px solid rgba(148,163,184,0.2); margin-bottom:4px; padding:7px 10px;">` +
      `<i class="fa-solid fa-list-check" style="margin-right:8px; font-size:12px; color:#059669;"></i>` +
      `<span style="flex:1;">${escapeHtml(totalLabel)}</span>` +
      `<span style="font-size:9.5px; font-weight:700; color:#059669; background:rgba(16,185,129,0.15); padding:2px 7px; border-radius:10px;">SAM ${totalSamCount}</span>` +
      `</div>`;
  }

  if (filtered.length === 0) {
    html += `<div class="combobox-empty"><i class="fa-solid fa-circle-question" style="margin-right:4px;"></i>ไม่พบ "${escapeHtml(query)}" ในรายชื่อโครงการ</div>`;
  } else {
    // 1. Render Selected Items (if any)
    if (selectedItems.length > 0) {
      html += `<div style="font-size:10.5px; font-weight:800; color:#059669; padding:5px 10px 3px; display:flex; align-items:center; gap:5px; background:rgba(16,185,129,0.08); border-radius:4px; margin-bottom:3px;">` +
        `<i class="fa-solid fa-square-check" style="color:#059669;"></i>` +
        `<span>โครงการที่เลือกไว้ (${selectedItems.length})</span>` +
        `</div>`;

      selectedItems.forEach(item => {
        const safeHtmlItem = escapeHtml(item);
        const badges = renderItemBadges(item, { sam: 0, other: 1 });
        html += `<div class="combobox-option selected" data-proj="${safeHtmlItem}" data-query="${safeCleanQueryAttr}" onclick="toggleProjectOption(this.dataset.proj, this.dataset.query, event)" style="display:flex; align-items:center; margin-bottom:2px;">` +
          `<i class="fa-solid fa-square-check" style="color:#ffffff; font-size:13px; margin-right:8px; flex-shrink:0;"></i>` +
          `<span class="combobox-opt-text">${safeHtmlItem}</span>` +
          badges +
          `</div>`;
      });
    }

    // 2. Render ALL SAM Projects (100% complete! No cutoff! Every single one scrollable!)
    if (unselectedSam.length > 0) {
      html += `<div class="prj-group-hdr-sam">` +
        `<span style="display:flex; align-items:center; gap:5px;">` +
          `<i class="fa-solid fa-city" style="color:#059669; font-size:12px;"></i>` +
          `<span>โครงการ SAM (${unselectedSam.length.toLocaleString()})</span>` +
        `</span>` +
        `</div>`;

      unselectedSam.forEach(item => {
        const safeHtmlItem = escapeHtml(item);
        const badges = renderItemBadges(item, { sam: 1, other: 0 });
        html += `<div class="combobox-option sam-option" data-proj="${safeHtmlItem}" data-query="${safeCleanQueryAttr}" onclick="toggleProjectOption(this.dataset.proj, this.dataset.query, event)" style="display:flex; align-items:center;">` +
          `<i class="fa-regular fa-square" style="opacity:0.45; font-size:13px; margin-right:8px; flex-shrink:0; color:#059669;"></i>` +
          `<span class="combobox-opt-text">${safeHtmlItem}</span>` +
          badges +
          `</div>`;
      });
    }

    // 3. Render Other / Competitor Projects (where SAM has 0 assets)
    if (unselectedOther.length > 0) {
      html += `<div class="prj-group-hdr-other">` +
        `<span style="display:flex; align-items:center; gap:5px;">` +
          `<i class="fa-solid fa-city" style="opacity:0.7;"></i>` +
          `<span>โครงการอื่นๆ (${unselectedOther.length.toLocaleString()})</span>` +
        `</span>` +
        `</div>`;

      const maxOther = !cleanQuery ? (window._showAllOtherPrj ? 9999 : 40) : 150;
      const renderOther = unselectedOther.slice(0, maxOther);

      renderOther.forEach(item => {
        const safeHtmlItem = escapeHtml(item);
        const badges = renderItemBadges(item, { sam: 0, other: 1 });
        html += `<div class="combobox-option" data-proj="${safeHtmlItem}" data-query="${safeCleanQueryAttr}" onclick="toggleProjectOption(this.dataset.proj, this.dataset.query, event)" style="display:flex; align-items:center;">` +
          `<i class="fa-regular fa-square" style="opacity:0.35; font-size:13px; margin-right:8px; flex-shrink:0;"></i>` +
          `<span class="combobox-opt-text">${safeHtmlItem}</span>` +
          badges +
          `</div>`;
      });

      if (unselectedOther.length > maxOther) {
        const remaining = unselectedOther.length - maxOther;
        html += `<div class="combobox-empty" onclick="window._showAllOtherPrj = true; renderProjectOptionsList(''); if(event){event.stopPropagation();}" style="font-size:11px; font-weight:700; color:#059669; padding:8px 10px; cursor:pointer; text-align:center; background:rgba(16,185,129,0.06); border-radius:6px; margin:4px 6px;">` +
          `<i class="fa-solid fa-chevron-down" style="margin-right:5px;"></i>แสดงโครงการอื่นๆ อีก ${remaining.toLocaleString()} โครงการ (หรือพิมพ์ค้นหาด้านบน)` +
          `</div>`;
      }
    }
  }

  const prevScroll = list.scrollTop;
  list.innerHTML = html;
  list.scrollTop = prevScroll;
}

function renderComboboxMenu(type, query = '') {
  if (type === 'prj') {
    renderProjectOptionsList(query);
    const menu = document.getElementById('combo-menu-prj');
    if (menu && currentActiveCombo === 'prj') {
      menu.style.display = 'flex';
      const chev = document.getElementById('combo-chevron-prj');
      if (chev) chev.classList.add('open');
    }
    return;
  }

  const menu = document.getElementById(`combo-menu-${type}`);
  if (!menu) return;

  const allItems = getComboboxItems(type);
  const currentVal = getCurrentComboboxValue(type);
  const allLabel = getComboboxAllLabel(type);

  const cleanQuery = (query || '').trim().toLowerCase();
  let filtered = allItems;
  if (cleanQuery) {
    filtered = allItems.filter(item => item.toLowerCase().includes(cleanQuery));
  }

  let html = '';
  const safeTypeAttr = escapeHtml(type);
  if (!cleanQuery || allLabel.toLowerCase().includes(cleanQuery)) {
    const isSel = !currentVal || currentVal === '__ALL__' || currentVal === '';
    html += `<div class="combobox-option ${isSel ? 'selected' : ''}" data-combo-type="${safeTypeAttr}" data-combo-val="" onclick="selectComboboxOption(this.dataset.comboType, this.dataset.comboVal)"><i class="fa-solid fa-list" style="margin-right:6px; font-size:10px; opacity:0.6;"></i>${escapeHtml(allLabel)}</div>`;
  }

  if (filtered.length === 0 && (!html || cleanQuery)) {
    html += `<div class="combobox-empty"><i class="fa-solid fa-circle-question" style="margin-right:4px;"></i>ไม่พบ "${escapeHtml(query)}"</div>`;
  } else {
    const maxRender = 250;
    const sliceItems = filtered.slice(0, maxRender);
    sliceItems.forEach(item => {
      const isSel = (item === currentVal);
      const safeHtmlItem = escapeHtml(item);
      html += `<div class="combobox-option ${isSel ? 'selected' : ''}" data-combo-type="${safeTypeAttr}" data-combo-val="${safeHtmlItem}" onclick="selectComboboxOption(this.dataset.comboType, this.dataset.comboVal)">${safeHtmlItem}</div>`;
    });
    if (filtered.length > maxRender) {
      html += `<div class="combobox-empty" style="font-size:10.5px; opacity:0.75;">และอีก ${(filtered.length - maxRender).toLocaleString()} รายการ (พิมพ์เพื่อเจาะจงผลลัพธ์)</div>`;
    }
  }

  const prevScrollTop = menu.scrollTop;
  menu.innerHTML = html;
  menu.scrollTop = prevScrollTop;

  if (type === 'prj' && currentActiveCombo === 'prj') {
    menu.style.display = 'flex';
    const chev = document.getElementById('combo-chevron-prj');
    if (chev) chev.classList.add('open');
  }
}

function openCombobox(type) {
  closeAllComboboxes();
  const p1 = document.getElementById('map-filter-panel');
  if (p1) p1.style.display = 'none';
  const p2 = document.getElementById('map-spec-filter-panel');
  if (p2) p2.style.display = 'none';
  document.getElementById('map-filter-toggle-btn')?.classList.remove('open');
  document.getElementById('map-spec-filter-toggle-btn')?.classList.remove('open');
  currentActiveCombo = type;
  const menu = document.getElementById(`combo-menu-${type}`);
  const chev = document.getElementById(`combo-chevron-${type}`);
  const inputId = `inmap-${type === 'prov' ? 'province' : (type === 'dist' ? 'district' : (type === 'subdist' ? 'subdistrict' : 'project'))}-input`;
  const input = document.getElementById(inputId);

  if (input && input.disabled) return;

  // Elevate parent row z-index so dropdown is always rendered on top of other floating rows
  if (type === 'prov' || type === 'dist' || type === 'subdist') {
    const locGroup = document.getElementById('map-location-group');
    if (locGroup) locGroup.style.zIndex = '30000';
  } else if (type === 'prj') {
    const subrow3 = document.querySelector('.map-filter-controls-stack > .map-filter-subrow:nth-child(3)');
    if (subrow3) subrow3.style.zIndex = '35000';
    const subrow2 = document.querySelector('.map-filter-controls-stack > .map-filter-subrow:nth-child(2)');
    if (subrow2) subrow2.style.zIndex = '1000';
    const prjGroup = document.getElementById('map-project-group');
    if (prjGroup) prjGroup.style.zIndex = '35000';
  }

  // Always show full list with "ทุก..." first like before
  renderComboboxMenu(type, '');
  if (menu) {
    menu.style.display = (type === 'prj') ? 'flex' : 'block';
    if (type !== 'prj') {
      const selOpt = menu.querySelector('.combobox-option.selected');
      if (selOpt) {
        selOpt.scrollIntoView({ block: 'nearest' });
      }
    }
  }
  if (chev) chev.classList.add('open');

  if (input && type !== 'prj') {
    try {
      const len = input.value.length;
      input.setSelectionRange(len, len);
    } catch(e) {}
  }
  if (type === 'prj') {
    requestAnimationFrame(() => {
      const menuSearch = document.getElementById('combo-menu-search-prj');
      if (menuSearch) {
        menuSearch.focus();
      }
    });
  }
}

function toggleCombobox(type) {
  const menu = document.getElementById(`combo-menu-${type}`);
  if (menu && (menu.style.display === 'block' || menu.style.display === 'flex')) {
    closeAllComboboxes();
  } else {
    openCombobox(type);
  }
}

function selectComboboxOption(type, value) {
  closeAllComboboxes();
  const inputId = `inmap-${type === 'prov' ? 'province' : (type === 'dist' ? 'district' : (type === 'subdist' ? 'subdistrict' : 'project'))}-input`;
  const input = document.getElementById(inputId);
  if (input) {
    input.value = value || '';
  }

  if (type === 'prov') {
    onMapProvinceChange(value);
  } else if (type === 'dist') {
    onMapDistrictChange(value);
  } else if (type === 'subdist') {
    onMapSubdistrictChange(value);
  } else if (type === 'prj') {
    onMapProjectChange(value);
  }
}

function handleComboboxInput(type, inputEl) {
  const query = inputEl.value;
  const menu = document.getElementById(`combo-menu-${type}`);
  if (menu) menu.style.display = 'block';
  const chev = document.getElementById(`combo-chevron-${type}`);
  if (chev) chev.classList.add('open');
  renderComboboxMenu(type, query);

  if (!query || !query.trim()) {
    renderComboboxMenu(type, '');
    if (type === 'prov' && currentSelectedProv) onMapProvinceChange('');
    else if (type === 'dist' && currentSelectedDist) onMapDistrictChange('');
    else if (type === 'subdist' && currentSelectedSubdist) onMapSubdistrictChange('');
  }
}

function handleComboboxKeydown(type, e) {
  if (e.key === 'Enter') {
    e.preventDefault();
    const menu = document.getElementById(`combo-menu-${type}`);
    if (menu) {
      const firstOpt = menu.querySelector('.combobox-option');
      if (firstOpt) {
        firstOpt.click();
      }
    }
  } else if (e.key === 'Escape') {
    closeAllComboboxes();
  }
}

// Display Mode for Property Pins: 'radius' (default, pins within circle) vs 'location' (pins in location)
let mapPinMode = 'radius';

function setMapPinMode(mode) {
  mapPinMode = mode;
  const btnLoc = document.getElementById('btn-mode-location');
  const btnRad = document.getElementById('btn-mode-radius');
  if (btnLoc) btnLoc.classList.toggle('active', mode === 'location');
  if (btnRad) btnRad.classList.toggle('active', mode === 'radius');

  if (mode === 'radius') {
    if (currentRefProp && currentRefProp.lat && currentRefProp.lon) {
      const lat = parseFloat(currentRefProp.lat);
      const lon = parseFloat(currentRefProp.lon);
      setReferencePoint(lon, lat, true);
    } else if (!referencePoint) {
      showToast('<i class="fa-solid fa-bullseye" style="color:#10b981; margin-right:6px;"></i>โหมดตามรัศมี: คลิกบนแผนที่เพื่อกำหนดจุดอ้างอิง');
    }
  } else if (mode === 'location') {
    if (currentRefProp) {
      if (currentRefProp._prov && currentRefProp._prov !== '-' && currentRefProp._prov !== 'ไม่มีข้อมูล') {
        currentSelectedProv = currentRefProp._prov.trim();
        if (currentRefProp._district && currentRefProp._district !== '-' && currentRefProp._district !== 'ไม่มีข้อมูล') {
          currentSelectedDist = currentRefProp._district.trim();
        }
        if (currentRefProp._subdistrict && currentRefProp._subdistrict !== '-' && currentRefProp._subdistrict !== 'ไม่มีข้อมูล') {
          currentSelectedSubdist = currentRefProp._subdistrict.trim();
        }
        updateDistrictSubdistrictBoundaries();
        syncComboboxInputs();
      }
      if (currentRefProp.lat && currentRefProp.lon) {
        smoothFlyTo(parseFloat(currentRefProp.lon), parseFloat(currentRefProp.lat), 14.5, 1200);
      }
    }
    referencePoint = null;
    updateDeckLayers();
    updateSvgBoundaries();
    const hasProvSelected = currentSelectedProv && currentSelectedProv.trim() !== '' && currentSelectedProv !== '__ALL__';
    const hasDistOrSubdist = (currentSelectedDist && currentSelectedDist.trim() !== '' && currentSelectedDist !== '__ALL__')
      || (currentSelectedSubdist && currentSelectedSubdist.trim() !== '' && currentSelectedSubdist !== '__ALL__');
    if (!hasProvSelected) {
      showToast('<i class="fa-solid fa-hand-pointer" style="color:#059669; margin-right:6px;"></i>กรุณาเลือกจังหวัด และอำเภอ/ตำบลทางซ้ายบน เพื่อแสดงหมุดตามทำเล');
    } else if (!hasDistOrSubdist && !currentRefProp) {
      showToast('<i class="fa-solid fa-hand-pointer" style="color:#059669; margin-right:6px;"></i>กรุณาเลือกอำเภอ/เขต หรือตำบล/แขวง เพื่อแสดงหมุดบนแผนที่');
    }
  }

  applyInMapFilters();
  notifyParentFilterChange();
}

function getSubdistrictBoundaryForDistrict(prov, dist) {
  if (!window.ALL_SUBDISTRICTS_BOUNDARIES || !prov || !dist) return null;
  const cleanProv = prov.trim();
  const cleanDist = dist.trim().split(' (')[0].trim();
  const stripDist = cleanDist.replace(/^(อำเภอ|เขต)/, '').trim();

  const candidates = [
    `${cleanProv}::${cleanDist}`,
    `${cleanProv}::${stripDist}`,
    `${cleanProv}::อำเภอ${stripDist}`,
    `${cleanProv}::เขต${stripDist}`
  ];

  for (const k of candidates) {
    if (window.ALL_SUBDISTRICTS_BOUNDARIES[k]) {
      return window.ALL_SUBDISTRICTS_BOUNDARIES[k];
    }
  }

  // Fallback: prefix match under the province
  const pPrefix = cleanProv + '::';
  for (const k of Object.keys(window.ALL_SUBDISTRICTS_BOUNDARIES)) {
    if (k.startsWith(pPrefix)) {
      const dName = k.substring(pPrefix.length).trim();
      if (dName === stripDist || dName === cleanDist || stripDist.includes(dName) || dName.includes(stripDist)) {
        return window.ALL_SUBDISTRICTS_BOUNDARIES[k];
      }
    }
  }
  return null;
}

function updateDistrictSubdistrictBoundaries() {
  if (!currentSelectedProv) {
    boundaryGeoJson = null;
    districtLabels = [];
    return;
  }

  if (currentSelectedDist) {
    // Check if subdistricts GeoJSON is loaded for this district!
    const subdistObj = getSubdistrictBoundaryForDistrict(currentSelectedProv, currentSelectedDist);
    if (subdistObj && subdistObj.features && subdistObj.features.length > 0) {
      const sanitizedLabels = (subdistObj.district_labels || []).map(l => {
        if (l.name === 'คลองเตย' && (l.lon > 100.565 || l.lat > 13.725)) {
          return { ...l, lon: 100.5598, lat: 13.71995 };
        }
        return l;
      });
      boundaryGeoJson = {
        type: 'FeatureCollection',
        level: 'subdistrict',
        features: subdistObj.features,
        district_labels: sanitizedLabels
      };
      districtLabels = sanitizedLabels;
      return;
    }

    // Fallback to district boundary from ALL_PROVINCES_BOUNDARIES
    const boundariesDict = window.ALL_PROVINCES_BOUNDARIES || {};
    if (boundariesDict[currentSelectedProv]) {
      const provObj = boundariesDict[currentSelectedProv];
      const cleanTarget = currentSelectedDist.split(' (')[0].trim();
      const stripTarget = cleanTarget.replace(/^(อำเภอ|เขต)/, '').trim();
      const distFeats = provObj.features.filter(f => {
        const a = (f.properties && f.properties.amp_th) || '';
        const cleanA = a.replace(/^(อำเภอ|เขต)/, '').trim();
        return cleanA === stripTarget || cleanA === cleanTarget || a === currentSelectedDist || a === cleanTarget;
      });
      const distLbls = (provObj.district_labels || []).filter(l => {
        const cleanL = (l.name || '').replace(/^(อำเภอ|เขต)/, '').trim();
        return cleanL === stripTarget || l.name === currentSelectedDist || l.name === cleanTarget;
      });
      if (distFeats.length > 0) {
        boundaryGeoJson = {
          type: 'FeatureCollection',
          level: 'single_district',
          features: distFeats,
          district_labels: distLbls
        };
        districtLabels = distLbls;
        return;
      }
    }
  }

  // Province level (all districts in province)
  const boundariesDict = window.ALL_PROVINCES_BOUNDARIES || {};
  if (boundariesDict[currentSelectedProv]) {
    boundaryGeoJson = boundariesDict[currentSelectedProv];
    districtLabels = boundaryGeoJson.district_labels || [];
  } else {
    boundaryGeoJson = null;
    districtLabels = [];
  }
}

function initSubdistrictDropdown() {
  syncComboboxInputs();
}

function _loadScriptAsync(src) {
  const cands = (typeof window.resolveStaticUrlCandidates === 'function' && String(src).includes('app/static'))
    ? window.resolveStaticUrlCandidates(src)
    : [src];
  return (async () => {
    for (let i = 0; i < cands.length; i++) {
      const ok = await new Promise((resolve) => {
        const s = document.createElement('script');
        s.src = cands[i];
        s.async = true;
        s.onload = () => resolve(true);
        s.onerror = () => resolve(false);
        document.head.appendChild(s);
      });
      if (ok) return true;
    }
    return false;
  })();
}

let _provBoundariesPromise = null;
let _subdistBoundariesPromise = null;

function _isIOSLowRamDevice() {
  return !!(window.NovaMapCache && typeof window.NovaMapCache.isIOSOrIPadOS === 'function' && window.NovaMapCache.isIOSOrIPadOS());
}

function loadProvinceBoundariesAsync() {
  if (window.ALL_PROVINCES_BOUNDARIES && Object.keys(window.ALL_PROVINCES_BOUNDARIES).length > 0) {
    return Promise.resolve(window.ALL_PROVINCES_BOUNDARIES);
  }
  if (_provBoundariesPromise) return _provBoundariesPromise;
  _provBoundariesPromise = (async () => {
    const pBound = window.NovaMapCache && typeof window.NovaMapCache.getParentBoundaryCache === 'function'
      ? window.NovaMapCache.getParentBoundaryCache()
      : null;
    if (pBound && pBound.provinces && Object.keys(pBound.provinces).length > 0) {
      window.ALL_PROVINCES_BOUNDARIES = pBound.provinces;
    }
    const _resStatic = (typeof resolveNovaStaticUrl === 'function') ? resolveNovaStaticUrl : (u => u);
    if (!window.ALL_PROVINCES_BOUNDARIES || Object.keys(window.ALL_PROVINCES_BOUNDARIES).length === 0) {
      await _loadScriptAsync(_resStatic('/app/static/provinces_geojson.js?v=20261001'));
    }
    if (!window.ALL_PROVINCES_BOUNDARIES || Object.keys(window.ALL_PROVINCES_BOUNDARIES).length === 0) {
      const _bUrls = (typeof window.resolveStaticUrlCandidates === 'function')
        ? window.resolveStaticUrlCandidates(_resStatic('/app/static/provinces_geojson.json'))
        : [_resStatic('/app/static/provinces_geojson.json'), '/app/static/provinces_geojson.json', '/~/+/app/static/provinces_geojson.json'];
      for (const u of _bUrls) {
        try {
          const resp = await fetch(u);
          const ct = (resp.headers && resp.headers.get('content-type') || '').toLowerCase();
          if (resp.ok && !ct.includes('text/html')) {
            window.ALL_PROVINCES_BOUNDARIES = await resp.json();
            break;
          }
        } catch(e) {}
      }
    }
    if (window.ALL_PROVINCES_BOUNDARIES && window.NovaMapCache && window.NovaMapCache.storeParentBoundaryCache) {
      window.NovaMapCache.storeParentBoundaryCache('provinces', window.ALL_PROVINCES_BOUNDARIES);
    }
    if (currentSelectedProv && currentSelectedProv !== '__ALL__') {
      const hadBoundaryBefore = !!(boundaryGeoJson && boundaryGeoJson.features && boundaryGeoJson.features.length > 0);
      try { updateDistrictSubdistrictBoundaries(); } catch(e) {}
      try { initDistrictDropdown(); } catch(e) {}
      try { updateSvgBoundaries(); } catch(e) {}
      if (!hadBoundaryBefore && !referencePoint) {
        try { flyToCurrentLocation(); } catch(e) {}
      }
    }
    return window.ALL_PROVINCES_BOUNDARIES || null;
  })().finally(() => { _provBoundariesPromise = null; });
  return _provBoundariesPromise;
}

function loadSubdistrictBoundariesAsync() {
  if (window.ALL_SUBDISTRICTS_BOUNDARIES && Object.keys(window.ALL_SUBDISTRICTS_BOUNDARIES).length > 0) {
    return Promise.resolve(window.ALL_SUBDISTRICTS_BOUNDARIES);
  }
  if (_subdistBoundariesPromise) return _subdistBoundariesPromise;
  _subdistBoundariesPromise = (async () => {
    const pBound = window.NovaMapCache && typeof window.NovaMapCache.getParentBoundaryCache === 'function'
      ? window.NovaMapCache.getParentBoundaryCache()
      : null;
    if (pBound && pBound.subdistricts && Object.keys(pBound.subdistricts).length > 0) {
      window.ALL_SUBDISTRICTS_BOUNDARIES = pBound.subdistricts;
    }
    const _resStatic = (typeof resolveNovaStaticUrl === 'function') ? resolveNovaStaticUrl : (u => u);
    if (!window.ALL_SUBDISTRICTS_BOUNDARIES || Object.keys(window.ALL_SUBDISTRICTS_BOUNDARIES).length === 0) {
      await _loadScriptAsync(_resStatic('/app/static/subdistricts_geojson.js?v=20261001'));
    }
    if (!window.ALL_SUBDISTRICTS_BOUNDARIES || Object.keys(window.ALL_SUBDISTRICTS_BOUNDARIES).length === 0) {
      const _subUrls = (typeof window.resolveStaticUrlCandidates === 'function')
        ? window.resolveStaticUrlCandidates(_resStatic('/app/static/subdistricts_geojson.json?v=20261001'))
        : [_resStatic('/app/static/subdistricts_geojson.json?v=20261001'), '/app/static/subdistricts_geojson.json?v=20261001', '/~/+/app/static/subdistricts_geojson.json?v=20261001'];
      for (const u of _subUrls) {
        try {
          const resp = await fetch(u);
          const ct = (resp.headers && resp.headers.get('content-type') || '').toLowerCase();
          if (resp.ok && !ct.includes('text/html')) {
            window.ALL_SUBDISTRICTS_BOUNDARIES = await resp.json();
            break;
          }
        } catch(e) {}
      }
    }
    if (window.ALL_SUBDISTRICTS_BOUNDARIES && window.NovaMapCache && window.NovaMapCache.storeParentBoundaryCache) {
      window.NovaMapCache.storeParentBoundaryCache('subdistricts', window.ALL_SUBDISTRICTS_BOUNDARIES);
    }
    if (currentSelectedDist && currentSelectedDist !== '__ALL__') {
      try { updateDistrictSubdistrictBoundaries(); } catch(e) {}
      try { initSubdistrictDropdown(); } catch(e) {}
      try { updateSvgBoundaries(); } catch(e) {}
    }
    return window.ALL_SUBDISTRICTS_BOUNDARIES || null;
  })().finally(() => { _subdistBoundariesPromise = null; });
  return _subdistBoundariesPromise;
}

function loadBoundaryScriptsInBackground() {
  const pBound = window.NovaMapCache && typeof window.NovaMapCache.getParentBoundaryCache === 'function'
    ? window.NovaMapCache.getParentBoundaryCache()
    : null;
  if (pBound) {
    if (pBound.provinces && (!window.ALL_PROVINCES_BOUNDARIES || Object.keys(window.ALL_PROVINCES_BOUNDARIES).length === 0)) {
      window.ALL_PROVINCES_BOUNDARIES = pBound.provinces;
    }
    if (pBound.subdistricts && (!window.ALL_SUBDISTRICTS_BOUNDARIES || Object.keys(window.ALL_SUBDISTRICTS_BOUNDARIES).length === 0)) {
      window.ALL_SUBDISTRICTS_BOUNDARIES = pBound.subdistricts;
    }
  }

  // On iPadOS/iOS Safari, skip eager background loading of the ~8 MB (~180 MB RAM) GeoJSON bundles
  // unless a province/district is already active; load them on-demand when the user filters by location.
  if (_isIOSLowRamDevice()) {
    if (currentSelectedProv && currentSelectedProv !== '__ALL__') {
      loadProvinceBoundariesAsync();
    }
    if (currentSelectedDist && currentSelectedDist !== '__ALL__') {
      loadSubdistrictBoundariesAsync();
    }
    return;
  }

  loadProvinceBoundariesAsync();
  loadSubdistrictBoundariesAsync();
}

function flyToCurrentLocation() {
  if (!currentSelectedProv || currentSelectedProv === '__ALL__') {
    // ซูมออกมาเห็นทั้งประเทศไทย (Nationwide Thailand full view)
    smoothFlyTo(100.5, 13.5, 5.2, 1200);
    return;
  }

  let flyTarget = null;
  if (cachedData && cachedData.length > 0) {
    const matchingPins = cachedData.filter(d => {
      if (currentSelectedProv && d._prov !== currentSelectedProv) return false;
      if (currentSelectedDist && d._district !== currentSelectedDist) return false;
      if (currentSelectedSubdist && d._subdistrict !== currentSelectedSubdist) return false;
      return d.lon && d.lat;
    });
    if (matchingPins.length > 0) {
      let minLon = Infinity, minLat = Infinity, maxLon = -Infinity, maxLat = -Infinity;
      matchingPins.forEach(p => {
        if (p.lon < minLon) minLon = p.lon;
        if (p.lon > maxLon) maxLon = p.lon;
        if (p.lat < minLat) minLat = p.lat;
        if (p.lat > maxLat) maxLat = p.lat;
      });
      const cLon = (minLon + maxLon) / 2;
      const cLat = (minLat + maxLat) / 2;
      const maxDiff = Math.max(maxLon - minLon, maxLat - minLat);
      let z = 10.0;
      if (currentSelectedSubdist) {
        z = 13.5;
      } else if (currentSelectedDist) {
        z = maxDiff > 0.4 ? 10.5 : (maxDiff > 0.2 ? 11.2 : 12.0);
      } else if (currentSelectedProv) {
        if (maxDiff > 2.0) z = 7.5;
        else if (maxDiff > 1.0) z = 8.8;
        else if (maxDiff > 0.5) z = 9.8;
        else if (maxDiff > 0.2) z = 11.2;
        else z = 12.5;
      }
      flyTarget = { lon: cLon, lat: cLat, zoom: z };
    }
  }

  if (!flyTarget && boundaryGeoJson && boundaryGeoJson.features && boundaryGeoJson.features.length > 0) {
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
      const cLon = (minLon + maxLon) / 2;
      const cLat = (minLat + maxLat) / 2;
      const maxDiff = Math.max(maxLon - minLon, maxLat - minLat);
      let z = 10.0;
      if (maxDiff > 2.0) z = 7.5;
      else if (maxDiff > 1.0) z = 8.8;
      else if (maxDiff > 0.5) z = 9.8;
      else if (maxDiff > 0.2) z = 11.2;
      else z = 12.5;
      flyTarget = { lon: cLon, lat: cLat, zoom: z };
    }
  }

  if (flyTarget) {
    smoothFlyTo(flyTarget.lon, flyTarget.lat, flyTarget.zoom, 1000);
  } else if (!currentSelectedProv || currentSelectedProv === '__ALL__') {
    smoothFlyTo(100.5, 13.5, 5.2, 1200);
  }
}

function onMapProvinceChange(prov) {
  const selectedProv = (prov && prov.trim() !== '' && prov.trim() !== 'all' && prov.trim() !== '__ALL__') ? prov.trim() : '';
  try {
    currentSelectedProv = selectedProv;
    currentSelectedDist = '';
    currentSelectedSubdist = '';
    currentRefProp = null;
    referencePoint = null;
    if (typeof closePropertyCard === 'function') closePropertyCard();

    cachedScopedProjectsKey = '';
    if (inMapFilterState && inMapFilterState.samProjects && inMapFilterState.samProjects.size > 0) {
      const scopedList = getScopedProjectsList();
      const scopedSet = new Set(scopedList);
      const toKeep = new Set();
      for (const p of inMapFilterState.samProjects) {
        if (scopedSet.has(p)) {
          toKeep.add(p);
        }
      }
      inMapFilterState.samProjects = toKeep;
      const cnt = inMapFilterState.samProjects.size;
      inMapFilterState.samProject = cnt === 1 ? Array.from(inMapFilterState.samProjects)[0] : (cnt > 1 ? `เลือก ${cnt} โครงการ` : null);
      inMapFilterState.samProjectsNorm = new Set(
        Array.from(inMapFilterState.samProjects || []).map(p => normalizeProjectKeyword(p)).filter(Boolean)
      );
    }

    mapPinMode = 'location';
    const btnLoc = document.getElementById('btn-mode-location');
    const btnRad = document.getElementById('btn-mode-radius');
    if (btnLoc) btnLoc.classList.toggle('active', true);
    if (btnRad) btnRad.classList.toggle('active', false);

    // 1. Swap Boundary GeoJSON & districtLabels in memory (lazy-load on iPad if not yet loaded)
    const boundariesDict = window.ALL_PROVINCES_BOUNDARIES || {};
    if (selectedProv && boundariesDict[selectedProv]) {
      boundaryGeoJson = boundariesDict[selectedProv];
      districtLabels = boundariesDict[selectedProv].district_labels || [];
    } else {
      boundaryGeoJson = null;
      districtLabels = [];
      if (selectedProv && typeof loadProvinceBoundariesAsync === 'function') {
        loadProvinceBoundariesAsync();
      }
    }

    // 2. Cascade Dropdowns: Sync inputs
    syncComboboxInputs();

    // 3. Immediately filter map points and update legend in memory (0.01 sec)
    applyInMapFilters(true);

    // 4. Immediately redraw SVG boundaries
    updateSvgBoundaries();

    // 5. Center & Fly to province
    flyToCurrentLocation();

    const hasActiveProj = inMapFilterState && (
      (inMapFilterState.samProjects && inMapFilterState.samProjects.size > 0) ||
      (inMapFilterState.samProject && inMapFilterState.samProject !== '') ||
      inMapFilterState.onlyWithProject
    );
    if (selectedProv && !hasActiveProj) {
      showToast(`<i class="fa-solid fa-map-location-dot" style="color:#059669; margin-right:6px;"></i>จังหวัด${escapeHtml(selectedProv)}: กรุณาเลือกอำเภอ/เขต เพื่อแสดงหมุดทรัพย์สิน`);
    }

    // 6. Update Parent Window URL parameter quietly without page reload
    if (window.parent) {
      const u = new URL(window.parent.location.href);
      if (selectedProv) {
        u.searchParams.set('map_prov', selectedProv);
      } else {
        u.searchParams.set('map_prov', '__ALL__');
      }
      u.searchParams.delete('map_dist');
      u.searchParams.delete('map_subdist');
      u.searchParams.delete('map_ref_id');
      u.searchParams.delete('map_ref_lat');
      u.searchParams.delete('map_ref_lon');
      if (inMapFilterState && inMapFilterState.samProjects && inMapFilterState.samProjects.size > 0) {
        u.searchParams.set('map_proj', Array.from(inMapFilterState.samProjects).join(','));
      } else if (inMapFilterState && inMapFilterState.samProject) {
        u.searchParams.set('map_proj', inMapFilterState.samProject);
      } else {
        u.searchParams.delete('map_proj');
      }
      window.parent.history.replaceState({}, '', u.toString());
    }
  } catch(e) {
    console.warn('onMapProvinceChange error:', e);
  }
  // 7. Auto-sync to Streamlit only when clearing province, when a project is active,
  //    or when an existing analytics fragment is currently open and needs to be hidden
  const curProjProv = (inMapFilterState && inMapFilterState.samProjects && inMapFilterState.samProjects.size > 0)
    ? Array.from(inMapFilterState.samProjects).join(',')
    : (inMapFilterState && inMapFilterState.samProject ? inMapFilterState.samProject : '');
  const shouldSyncProvChange = !selectedProv
    || Boolean(curProjProv)
    || (typeof hasActiveParentAnalyticsFragment === 'function' && hasActiveParentAnalyticsFragment());
  if (shouldSyncProvChange) {
    triggerStreamlitSync({
      prov: (selectedProv && selectedProv !== '__ALL__') ? selectedProv.trim() : '__ALL__',
      dist: '',
      subdist: '',
      proj: curProjProv,
      cos: (inMapFilterState && inMapFilterState.companies && inMapFilterState.companies.size > 0) ? Array.from(inMapFilterState.companies) : [],
      types: (inMapFilterState && inMapFilterState.types && inMapFilterState.types.size > 0) ? Array.from(inMapFilterState.types) : [],
      id: '',
      price_center_id: '',
      lat: 0,
      lon: 0,
      mode: 'location',
      compare_active: true
    });
  }
}

function onMapDistrictChange(dist) {
  const selectedDist = (dist && dist.trim() !== '' && dist.trim() !== 'all' && dist.trim() !== '__ALL__') ? dist.trim() : '';
  try {
    currentSelectedDist = selectedDist;
    currentSelectedSubdist = '';
    currentRefProp = null;
    referencePoint = null;
    if (!selectedDist && typeof closePropertyCard === 'function') closePropertyCard();

    cachedScopedProjectsKey = '';
    if (inMapFilterState && inMapFilterState.samProjects && inMapFilterState.samProjects.size > 0) {
      const scopedList = getScopedProjectsList();
      const scopedSet = new Set(scopedList);
      const toKeep = new Set();
      for (const p of inMapFilterState.samProjects) {
        if (scopedSet.has(p)) {
          toKeep.add(p);
        }
      }
      inMapFilterState.samProjects = toKeep;
      const cnt = inMapFilterState.samProjects.size;
      inMapFilterState.samProject = cnt === 1 ? Array.from(inMapFilterState.samProjects)[0] : (cnt > 1 ? `เลือก ${cnt} โครงการ` : null);
      inMapFilterState.samProjectsNorm = new Set(
        Array.from(inMapFilterState.samProjects || []).map(p => normalizeProjectKeyword(p)).filter(Boolean)
      );
    }

    if (selectedDist) {
      mapPinMode = 'location';
      const btnLoc = document.getElementById('btn-mode-location');
      const btnRad = document.getElementById('btn-mode-radius');
      if (btnLoc) btnLoc.classList.toggle('active', true);
      if (btnRad) btnRad.classList.toggle('active', false);
    }

    // 1. Update boundary GeoJSON to subdivide into subdistricts (ตำบล) with dashed lines!
    if (selectedDist && (!window.ALL_SUBDISTRICTS_BOUNDARIES || Object.keys(window.ALL_SUBDISTRICTS_BOUNDARIES).length === 0)) {
      if (typeof loadSubdistrictBoundariesAsync === 'function') loadSubdistrictBoundariesAsync();
    }
    updateDistrictSubdistrictBoundaries();

    // 2. Cascade Dropdown: Sync inputs
    syncComboboxInputs();

    // 3. Immediately filter map points in memory
    applyInMapFilters(true);

    // 4. Immediately redraw SVG boundaries
    updateSvgBoundaries();

    // 5. Center & Fly to district
    flyToCurrentLocation();

    // 6. Update Parent Window URL parameter quietly without page reload
    if (window.parent) {
      const u = new URL(window.parent.location.href);
      if (selectedDist) {
        u.searchParams.set('map_dist', selectedDist);
      } else {
        u.searchParams.delete('map_dist');
      }
      u.searchParams.delete('map_subdist');
      u.searchParams.delete('map_ref_id');
      if (inMapFilterState && inMapFilterState.samProjects && inMapFilterState.samProjects.size > 0) {
        u.searchParams.set('map_proj', Array.from(inMapFilterState.samProjects).join(','));
      } else if (inMapFilterState && inMapFilterState.samProject) {
        u.searchParams.set('map_proj', inMapFilterState.samProject);
      } else {
        u.searchParams.delete('map_proj');
      }
      window.parent.history.replaceState({}, '', u.toString());
    }
  } catch(e) {
    console.warn('onMapDistrictChange error:', e);
  }
  // 7. Auto-sync to Streamlit when a district/project is selected or when an existing fragment needs to be hidden
  const curProjDist = (inMapFilterState && inMapFilterState.samProjects && inMapFilterState.samProjects.size > 0)
    ? Array.from(inMapFilterState.samProjects).join(',')
    : (inMapFilterState && inMapFilterState.samProject ? inMapFilterState.samProject : '');
  const shouldSyncDistChange = Boolean(selectedDist)
    || Boolean(curProjDist)
    || (typeof hasActiveParentAnalyticsFragment === 'function' && hasActiveParentAnalyticsFragment());
  if (shouldSyncDistChange) {
    triggerStreamlitSync({
      prov: (currentSelectedProv && currentSelectedProv !== '__ALL__') ? currentSelectedProv.trim() : '',
      dist: (selectedDist && selectedDist !== '__ALL__') ? selectedDist.trim() : '',
      subdist: '',
      proj: curProjDist,
      cos: (inMapFilterState && inMapFilterState.companies && inMapFilterState.companies.size > 0) ? Array.from(inMapFilterState.companies) : [],
      types: (inMapFilterState && inMapFilterState.types && inMapFilterState.types.size > 0) ? Array.from(inMapFilterState.types) : [],
      id: '',
      mode: 'location',
      compare_active: true
    });
  }
}

function onMapSubdistrictChange(subdist) {
  const selectedSubdist = (subdist && subdist.trim() !== '' && subdist.trim() !== 'all' && subdist.trim() !== '__ALL__') ? subdist.trim() : '';
  try {
    currentSelectedSubdist = selectedSubdist;
    currentRefProp = null;
    referencePoint = null;

    cachedScopedProjectsKey = '';
    if (inMapFilterState && inMapFilterState.samProjects && inMapFilterState.samProjects.size > 0) {
      const scopedList = getScopedProjectsList();
      const scopedSet = new Set(scopedList);
      const toKeep = new Set();
      for (const p of inMapFilterState.samProjects) {
        if (scopedSet.has(p)) {
          toKeep.add(p);
        }
      }
      inMapFilterState.samProjects = toKeep;
      const cnt = inMapFilterState.samProjects.size;
      inMapFilterState.samProject = cnt === 1 ? Array.from(inMapFilterState.samProjects)[0] : (cnt > 1 ? `เลือก ${cnt} โครงการ` : null);
      inMapFilterState.samProjectsNorm = new Set(
        Array.from(inMapFilterState.samProjects || []).map(p => normalizeProjectKeyword(p)).filter(Boolean)
      );
    }

    if (selectedSubdist) {
      mapPinMode = 'location';
      const btnLoc = document.getElementById('btn-mode-location');
      const btnRad = document.getElementById('btn-mode-radius');
      if (btnLoc) btnLoc.classList.toggle('active', true);
      if (btnRad) btnRad.classList.toggle('active', false);
    }

    syncComboboxInputs();

    // 1. Immediately filter map points in memory
    applyInMapFilters(true);

    // 2. Immediately redraw SVG boundaries (highlights selected subdistrict polygon)
    updateSvgBoundaries();

    // 3. Center & Fly to subdistrict
    flyToCurrentLocation();

    // 4. Update Parent Window URL parameter quietly without page reload
    if (window.parent) {
      const u = new URL(window.parent.location.href);
      if (selectedSubdist) {
        u.searchParams.set('map_subdist', selectedSubdist);
      } else {
        u.searchParams.delete('map_subdist');
      }
      u.searchParams.delete('map_ref_id');
      if (inMapFilterState && inMapFilterState.samProjects && inMapFilterState.samProjects.size > 0) {
        u.searchParams.set('map_proj', Array.from(inMapFilterState.samProjects).join(','));
      } else if (inMapFilterState && inMapFilterState.samProject) {
        u.searchParams.set('map_proj', inMapFilterState.samProject);
      } else {
        u.searchParams.delete('map_proj');
      }
      window.parent.history.replaceState({}, '', u.toString());
    }
  } catch(e) {
    console.warn('onMapSubdistrictChange error:', e);
  }
  // 5. Auto-sync to Streamlit for realtime comparison
  const curProjSub = (inMapFilterState && inMapFilterState.samProjects && inMapFilterState.samProjects.size > 0)
    ? Array.from(inMapFilterState.samProjects).join(',')
    : (inMapFilterState && inMapFilterState.samProject ? inMapFilterState.samProject : '');
  triggerStreamlitSync({
    prov: (currentSelectedProv && currentSelectedProv !== '__ALL__') ? currentSelectedProv.trim() : '',
    dist: (currentSelectedDist && currentSelectedDist !== '__ALL__') ? currentSelectedDist.trim() : '',
    subdist: (selectedSubdist && selectedSubdist !== '__ALL__') ? selectedSubdist.trim() : '',
    proj: curProjSub,
    cos: (inMapFilterState && inMapFilterState.companies && inMapFilterState.companies.size > 0) ? Array.from(inMapFilterState.companies) : [],
    types: (inMapFilterState && inMapFilterState.types && inMapFilterState.types.size > 0) ? Array.from(inMapFilterState.types) : [],
    id: '',
    mode: 'location',
    compare_active: true
  });
}

function clearNonProjectMapFilters() {
  // 1. Clear location selection
  currentSelectedProv = '';
  currentSelectedDist = '';
  currentSelectedSubdist = '';
  boundaryGeoJson = null;
  districtLabels = [];

  // 2. Clear reference point & radius marker/circle & property search
  referencePoint = null;
  currentRefProp = null;
  currentRefId = '';
  pendingReferencePoint = null;
  mousePreviewCoord = null;

  const coordPill = document.getElementById('active-ref-pill');
  if (coordPill) coordPill.style.display = 'none';

  const clearBtn = document.getElementById('btn-clear-ref');
  if (clearBtn) clearBtn.style.display = 'none';

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

  closePropertyCard();

  // 3. Reset mode to radius mode (non-location mode)
  mapPinMode = 'radius';
  const btnLoc = document.getElementById('btn-mode-location');
  const btnRad = document.getElementById('btn-mode-radius');
  if (btnLoc) btnLoc.classList.remove('active');
  if (btnRad) btnRad.classList.add('active');

  // 4. Clear other in-map filters (companies, types, sales, prices, sqw, sqm)
  if (inMapFilterState) {
    inMapFilterState.companies.clear();
    inMapFilterState.types.clear();
    inMapFilterState.sales.clear();
    inMapFilterState.minPrice = null;
    inMapFilterState.maxPrice = null;
    inMapFilterState.minSqw = null;
    inMapFilterState.maxSqw = null;
    inMapFilterState.minSqm = null;
    inMapFilterState.maxSqm = null;
    inMapFilterState.minPuw = null;
    inMapFilterState.maxPuw = null;
    inMapFilterState.minPum = null;
    inMapFilterState.maxPum = null;
  }

  document.querySelectorAll('.filter-chip').forEach(c => c.classList.remove('active'));
  ['filter-min-price', 'filter-max-price', 'filter-min-sqw', 'filter-max-sqw', 'filter-min-sqm', 'filter-max-sqm', 'filter-min-puw', 'filter-max-puw', 'filter-min-pum', 'filter-max-pum', 'filter-min-floor', 'filter-max-floor', 'filter-max-age'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = '';
  });

  // 5. Update SVG boundaries and comboboxes
  updateSvgBoundaries();
  syncComboboxInputs();

  // 6. Clean URL parameters on parent
  try {
    if (window.parent) {
      var u = new URL(window.parent.location.href);
      u.searchParams.delete('map_prov');
      u.searchParams.delete('map_dist');
      u.searchParams.delete('map_subdist');
      u.searchParams.delete('map_ref_id');
      u.searchParams.delete('map_ref_lat');
      u.searchParams.delete('map_ref_lon');
      u.searchParams.delete('map_filter_cos');
      u.searchParams.delete('map_filter_types');
      u.searchParams.delete('map_filter_min_p');
      u.searchParams.delete('map_filter_max_p');
      u.searchParams.delete('map_filter_min_sqw');
      u.searchParams.delete('map_filter_max_sqw');
      u.searchParams.delete('map_filter_min_sqm');
      u.searchParams.delete('map_filter_max_sqm');
      window.parent.history.replaceState({}, '', u.toString());
    }
  } catch(e) {}
}

function toggleProjectOption(proj, query = '', event = null) {
  if (event) {
    try {
      event.stopPropagation();
    } catch(e) {}
  }
  const cleanPrj = (proj && proj.trim()) ? proj.trim() : null;
  if (!inMapFilterState.samProjects) {
    inMapFilterState.samProjects = new Set();
  }

  if (!cleanPrj) {
    inMapFilterState.samProjects.clear();
    inMapFilterState.samProject = null;
    inMapFilterState.samProjectsNorm = new Set();
    showToast('<i class="fa-solid fa-rotate-left" style="color:#64748b; margin-right:4px;"></i>ล้างตัวกรองโครงการทั้งหมด');
    cachedScopedProjectsKey = '';
    applyInMapFilters();
    syncComboboxInputs();
    notifyParentFilterChange();
    return;
  }

  // Only clear manual reference point / pin, DO NOT wipe location, company, or type filters!
  referencePoint = null;
  currentRefProp = null;
  currentRefId = '';
  pendingReferencePoint = null;
  mousePreviewCoord = null;
  const coordPill = document.getElementById('active-ref-pill');
  if (coordPill) coordPill.style.display = 'none';
  const clearBtn = document.getElementById('btn-clear-ref');
  if (clearBtn) clearBtn.style.display = 'none';
  const bubble = document.getElementById('in-map-confirm-bubble');
  if (bubble) bubble.style.display = 'none';
  const bar = document.getElementById('ref-confirm-bar');
  if (bar) bar.style.display = 'none';

  mapPinMode = 'location';
  const btnLoc = document.getElementById('btn-mode-location');
  const btnRad = document.getElementById('btn-mode-radius');
  if (btnLoc) btnLoc.classList.add('active');
  if (btnRad) btnRad.classList.remove('active');

  if (inMapFilterState.samProjects.has(cleanPrj)) {
    inMapFilterState.samProjects.delete(cleanPrj);
  } else {
    inMapFilterState.samProjects.add(cleanPrj);

    // Find matching items for the newly selected project
    if (cachedData && cachedData.length > 0) {
      const cleanNorm = globalProjToNormMap.get(cleanPrj) || normalizeProjectKeyword(cleanPrj);
      let matchingItems = (cleanNorm && globalNormToItemsMap.get(cleanNorm)) || globalProjToItemsMap.get(cleanPrj) || [];
      if (matchingItems.length === 0) {
        matchingItems = cachedData.filter(d => {
          if (!d.lat || !d.lon || isNaN(d.lat) || isNaN(d.lon)) return false;
          const p = (d._project || '').trim();
          return p === cleanPrj || (d._normKey && cleanNorm && d._normKey === cleanNorm);
        });
      }

      if (matchingItems.length > 0) {
        // Auto-detect project's location hierarchy if no province is explicitly selected yet
        const provCounts = {};
        const distCounts = {};
        const subdistCounts = {};
        matchingItems.forEach(d => {
          if (d._prov && d._prov !== '-' && d._prov !== 'ไม่มีข้อมูล') {
            provCounts[d._prov] = (provCounts[d._prov] || 0) + 1;
          }
          if (d._district && d._district !== '-' && d._district !== 'ไม่มีข้อมูล') {
            distCounts[d._district] = (distCounts[d._district] || 0) + 1;
          }
          if (d._subdistrict && d._subdistrict !== '-' && d._subdistrict !== 'ไม่มีข้อมูล') {
            subdistCounts[d._subdistrict] = (subdistCounts[d._subdistrict] || 0) + 1;
          }
        });

        let topProv = '';
        let maxProvCount = 0;
        for (const [p, c] of Object.entries(provCounts)) {
          if (c > maxProvCount) { maxProvCount = c; topProv = p; }
        }

        if (topProv && (!currentSelectedProv || currentSelectedProv === '__ALL__')) {
          currentSelectedProv = topProv;
          const boundariesDict = window.ALL_PROVINCES_BOUNDARIES || {};
          if (boundariesDict[currentSelectedProv]) {
            boundaryGeoJson = boundariesDict[currentSelectedProv];
            districtLabels = boundariesDict[currentSelectedProv].district_labels || [];
          }

          let topDist = '';
          let maxDistCount = 0;
          for (const [d, c] of Object.entries(distCounts)) {
            if (c > maxDistCount) { maxDistCount = c; topDist = d; }
          }
          if (topDist && (maxDistCount / matchingItems.length) >= 0.5) {
            currentSelectedDist = topDist;
            updateDistrictSubdistrictBoundaries();

            let topSubdist = '';
            let maxSubCount = 0;
            for (const [s, c] of Object.entries(subdistCounts)) {
              if (c > maxSubCount) { maxSubCount = c; topSubdist = s; }
            }
            if (topSubdist && (maxSubCount / matchingItems.length) >= 0.5) {
              currentSelectedSubdist = topSubdist;
            }
          }
          cachedScopedProjectsKey = '';
          updateSvgBoundaries();
        }

        // Calculate centroid of all project properties (prioritizing SAM properties if present)
        const samMatches = matchingItems.filter(d => d._company === 'SAM');
        const targetPool = samMatches.length > 0 ? samMatches : matchingItems;

        let sumLon = 0, sumLat = 0;
        let minLon = Infinity, maxLon = -Infinity;
        let minLat = Infinity, maxLat = -Infinity;

        targetPool.forEach(d => {
          const lon = Number(d.lon);
          const lat = Number(d.lat);
          sumLon += lon;
          sumLat += lat;
          if (lon < minLon) minLon = lon;
          if (lon > maxLon) maxLon = lon;
          if (lat < minLat) minLat = lat;
          if (lat > maxLat) maxLat = lat;
        });

        const centerLon = sumLon / targetPool.length;
        const centerLat = sumLat / targetPool.length;

        const spanLon = maxLon - minLon;
        const spanLat = maxLat - minLat;
        const maxSpan = Math.max(spanLon, spanLat);

        let targetZoom = 15.2;
        if (maxSpan > 0.05) targetZoom = 12.8;
        else if (maxSpan > 0.02) targetZoom = 13.8;
        else if (maxSpan > 0.008) targetZoom = 14.5;
        else if (maxSpan > 0.002) targetZoom = 15.0;

        smoothFlyTo(centerLon, centerLat, targetZoom);
        showToast(`<i class="fa-solid fa-plane-departure" style="color:#059669; margin-right:5px;"></i>บินไปโครงการ: <b>${cleanPrj}</b> (${targetPool.length} รายการ)`);
      }
    }
  }

  const cnt = inMapFilterState.samProjects.size;
  inMapFilterState.samProject = cnt === 1 ? Array.from(inMapFilterState.samProjects)[0] : (cnt > 1 ? `เลือก ${cnt} โครงการ` : null);
  inMapFilterState.samProjectsNorm = new Set(
    Array.from(inMapFilterState.samProjects || []).map(p => normalizeProjectKeyword(p)).filter(Boolean)
  );

  currentActiveCombo = 'prj';
  syncComboboxInputs();
  renderComboboxMenu('prj', query);

  // Keep combobox menu explicitly open and visible for multi-selection
  const menu = document.getElementById('combo-menu-prj');
  if (menu) menu.style.display = 'flex';
  const chev = document.getElementById('combo-chevron-prj');
  if (chev) chev.classList.add('open');

  const subrow3 = document.querySelector('.map-filter-controls-stack > .map-filter-subrow:nth-child(3)');
  if (subrow3) subrow3.style.zIndex = '35000';
  const prjGroup = document.getElementById('map-project-group');
  if (prjGroup) prjGroup.style.zIndex = '35000';

  // Ensure bottom-right breakdown widget is expanded when project is selected
  const legendBody = document.getElementById('legend-body-collapsible');
  const legendIcon = document.getElementById('legend-collapse-icon');
  if (legendBody && isLegendCollapsed) {
    isLegendCollapsed = false;
    legendBody.style.display = 'block';
    if (legendIcon) legendIcon.className = 'fa-solid fa-chevron-down';
  }

  applyInMapFilters();
  notifyParentFilterChange();
}

function onMapProjectChange(proj) {
  toggleProjectOption(proj, '');
}

function onMapSamProjectChange(proj) {
  onMapProjectChange(proj);
}

let idExactLookupMap = null;
let idStrippedLookupMap = null;
function buildIdLookupIndex(data) {
  idExactLookupMap = new Map();
  idStrippedLookupMap = new Map();
  if (!data || !data.length) return;
  for (let i = 0; i < data.length; i++) {
    const d = data[i];
    const raw = (d._id || '').trim().toLowerCase();
    if (!raw) continue;
    if (!idExactLookupMap.has(raw)) idExactLookupMap.set(raw, d);
    const stripped = raw.replace(/[^a-z0-9\u0E00-\u0E7F]/g, '');
    if (stripped && !idStrippedLookupMap.has(stripped)) idStrippedLookupMap.set(stripped, d);
  }
}

function searchPropertyIdAsReference(idStr) {
  if (!idStr || !idStr.trim()) {
    showToast('<i class="fa-solid fa-circle-exclamation" style="color:#f59e0b; margin-right:4px;"></i>กรุณากรอกรหัสทรัพย์สิน');
    return;
  }
  const rawQ = idStr.trim();
  const cleanId = rawQ.toLowerCase();
  const strippedQ = cleanId.replace(/[^a-z0-9\u0E00-\u0E7F]/g, '');
  const inputEl = document.getElementById('inmap-prop-search-input');
  const clearBtn = document.getElementById('inmap-clear-search-btn');

  if (!cachedData || cachedData.length === 0) {
    showToast('กำลังโหลดข้อมูลแผนที่ กรุณารอสักครู่...');
    return;
  }
  if (!idExactLookupMap) buildIdLookupIndex(cachedData);

  // ค้นหารหัสทรัพย์สิน (_id) อย่างเดียวเท่านั้น
  // Tier 1: O(1) Exact match on _id (เช่น 3A1291)
  let match = idExactLookupMap.get(cleanId) || null;

  // Tier 2: O(1) Stripped punctuation alphanumeric match on _id (เช่น 3A-1291, 3A 1291)
  if (!match && strippedQ) {
    match = idStrippedLookupMap.get(strippedQ) || null;
  }

  // Tier 3: Substring / Prefix / Suffix match on _id
  if (!match && cleanId.length >= 2) {
    match = cachedData.find(d => {
      const did = (d._id || '').trim().toLowerCase();
      return did.startsWith(cleanId) || did.endsWith(cleanId) || did.includes(cleanId);
    });
  }

  // Tier 4: Stripped substring match on _id
  if (!match && strippedQ.length >= 3) {
    match = cachedData.find(d => {
      const did = (d._id || '').trim().toLowerCase().replace(/[^a-z0-9\u0E00-\u0E7F]/g, '');
      return did.includes(strippedQ) || strippedQ.includes(did);
    });
  }

  if (match && match.lat && match.lon) {
    const lat = parseFloat(match.lat);
    const lon = parseFloat(match.lon);
    if (inputEl) inputEl.value = match._id || rawQ;
    if (clearBtn) clearBtn.style.display = 'inline-flex';

    // 1. Do NOT auto-filter by project on property ID search; clear project filter so properties in location/radius are shown
    if (inMapFilterState && inMapFilterState.samProjects) {
      inMapFilterState.samProjects.clear();
    }
    if (inMapFilterState) {
      inMapFilterState.samProject = null;
      inMapFilterState.samProjectsNorm = new Set();
    }
    cachedScopedProjectsKey = '';
    const prjInp = document.getElementById('inmap-project-input');
    if (prjInp) prjInp.value = '';
    const clearPrjBtn = document.getElementById('inmap-clear-project-btn');
    if (clearPrjBtn) clearPrjBtn.style.display = 'none';

    // 2. Sync geographic dropdowns to the found property's Province, District, and Subdistrict!
    if (match._prov && match._prov !== '-' && match._prov !== 'ไม่มีข้อมูล') {
      currentSelectedProv = match._prov.trim();

      const boundariesDict = window.ALL_PROVINCES_BOUNDARIES || {};
      if (boundariesDict[currentSelectedProv]) {
        boundaryGeoJson = boundariesDict[currentSelectedProv];
        districtLabels = boundariesDict[currentSelectedProv].district_labels || [];
      }

      if (match._district && match._district !== '-' && match._district !== 'ไม่มีข้อมูล') {
        currentSelectedDist = match._district.trim();
        if (match._subdistrict && match._subdistrict !== '-' && match._subdistrict !== 'ไม่มีข้อมูล') {
          currentSelectedSubdist = match._subdistrict.trim();
        }
        updateDistrictSubdistrictBoundaries();
      }
      syncComboboxInputs();
    }

    // 3. Set active reference property
    currentRefProp = match;

    // 4. Display according to current pin mode (radius vs location)
    if (mapPinMode === 'radius') {
      setReferencePoint(lon, lat, true, false);
    } else {
      referencePoint = null;
      applyInMapFilters(true);
      updateDeckLayers();
      updateSvgBoundaries();
      smoothFlyTo(lon, lat, 14.5, 1200);
    }
    showPropertyCard(match, true);

    const locDetail = [match._subdistrict, match._district, match._prov].filter(x => x && x !== '-' && x !== 'ไม่มีข้อมูล').join(' ');
    const toastTitle = match._title || (match._project && match._project !== '-' ? match._project : match._type) || '';
    showToast(`<i class="fa-solid fa-location-crosshairs" style="color:#10b981; margin-right:4px;"></i>พบรหัส [${match._company}] ${match._id}: ${toastTitle} (${locDetail})`);

    try {
      if (window.parent) {
        var u = new URL(window.parent.location.href);
        u.searchParams.set('map_ref_id', match._id);
        u.searchParams.set('map_ref_lat', lat.toFixed(6));
        u.searchParams.set('map_ref_lon', lon.toFixed(6));
        u.searchParams.set('map_ref_radius', currentRadiusKm);
        u.searchParams.set('map_pin_mode', mapPinMode || 'location');
        u.searchParams.delete('map_proj');
        if (match._prov && match._prov !== '-' && match._prov !== 'ไม่มีข้อมูล') {
          u.searchParams.set('map_prov', match._prov);
        }
        if (match._district && match._district !== '-' && match._district !== 'ไม่มีข้อมูล') {
          u.searchParams.set('map_dist', match._district);
        }
        if (match._subdistrict && match._subdistrict !== '-' && match._subdistrict !== 'ไม่มีข้อมูล') {
          u.searchParams.set('map_subdist', match._subdistrict);
        }
        window.parent.history.replaceState({}, '', u.toString());
      }
    } catch(e) {}
    triggerStreamlitSync({
      prov: (match._prov && match._prov !== '-' && match._prov !== 'ไม่มีข้อมูล') ? match._prov.trim() : '',
      dist: (match._district && match._district !== '-' && match._district !== 'ไม่มีข้อมูล') ? match._district.trim() : '',
      subdist: (match._subdistrict && match._subdistrict !== '-' && match._subdistrict !== 'ไม่มีข้อมูล') ? match._subdistrict.trim() : '',
      proj: '',
      cos: (inMapFilterState && inMapFilterState.companies && inMapFilterState.companies.size > 0)
        ? Array.from(inMapFilterState.companies)
        : [],
      types: (inMapFilterState && inMapFilterState.types && inMapFilterState.types.size > 0)
        ? Array.from(inMapFilterState.types)
        : [],
      id: match._id || '',
      lat: lat,
      lon: lon,
      radius: currentRadiusKm || 5.0,
      mode: mapPinMode || 'location',
      compare_active: true
    });
  } else {
    showToast(`<i class="fa-solid fa-triangle-exclamation" style="color:#ef4444; margin-right:4px;"></i>ไม่พบรหัสทรัพย์ "${idStr.trim()}" ในฐานข้อมูล`);
  }
}

function clearInMapPropSearch() {
  const inputEl = document.getElementById('inmap-prop-search-input');
  const clearBtn = document.getElementById('inmap-clear-search-btn');
  if (inputEl) inputEl.value = '';
  if (clearBtn) clearBtn.style.display = 'none';
  currentRefProp = null;
  currentRefId = "";
  clearReferencePoint();
  updateSvgBoundaries();
}

function validateAndOrientCoords(v1, v2) {
  if (isNaN(v1) || isNaN(v2)) return null;
  // Auto-orient: if v1 looks like Lon in Thailand (90-115) and v2 looks like Lat (0-30), swap
  if ((v1 >= 90 && v1 <= 115) && (v2 >= 0 && v2 <= 30)) {
    return { lat: v2, lon: v1 };
  }
  if (v1 >= -90 && v1 <= 90 && v2 >= -180 && v2 <= 180) {
    return { lat: v1, lon: v2 };
  }
  return null;
}

function parseCoordinateString(str) {
  if (!str || typeof str !== 'string') return null;
  let s = str.trim();
  if (!s) return null;

  // URL format e.g. https://www.google.com/maps/...@13.7563,100.5018,15z
  const urlMatch = s.match(/@(-?\d+\.?\d*),\s*(-?\d+\.?\d*)/);
  if (urlMatch) {
    return validateAndOrientCoords(parseFloat(urlMatch[1]), parseFloat(urlMatch[2]));
  }

  // DMS format e.g. 13°45'22.8"N 100°30'06.3"E
  if (s.includes('°') || s.includes('N') || s.includes('E')) {
    const dmsRegex = /(\d+)[°\s]+(\d+)['\s]+([0-9.]+)["]?\s*([NSEW])/gi;
    const matches = [...s.matchAll(dmsRegex)];
    if (matches.length === 2) {
      const convertDms = (deg, min, sec, dir) => {
        let dec = parseFloat(deg) + parseFloat(min) / 60 + parseFloat(sec) / 3600;
        if (dir.toUpperCase() === 'S' || dir.toUpperCase() === 'W') dec = -dec;
        return dec;
      };
      const c1 = convertDms(matches[0][1], matches[0][2], matches[0][3], matches[0][4]);
      const c2 = convertDms(matches[1][1], matches[1][2], matches[1][3], matches[1][4]);
      if (matches[0][4].toUpperCase() === 'N' || matches[0][4].toUpperCase() === 'S') {
        return { lat: c1, lon: c2 };
      } else {
        return { lat: c2, lon: c1 };
      }
    }
  }

  // Generic decimal coordinates separated by comma, space, slash, or semicolon
  const cleaned = s.replace(/[^\d.\-,\s;/]/g, ' ');
  const nums = cleaned.match(/-?\d+\.?\d*/g);
  if (nums && nums.length >= 2) {
    return validateAndOrientCoords(parseFloat(nums[0]), parseFloat(nums[1]));
  }

  return null;
}

function searchCustomCoordinatesAsReference(coordStr) {
  if (!coordStr || !coordStr.trim()) {
    showToast('<i class="fa-solid fa-circle-exclamation" style="color:#f59e0b; margin-right:4px;"></i>กรุณากรอกพิกัด เช่น 13.7563, 100.5018');
    return;
  }

  const coords = parseCoordinateString(coordStr);
  if (!coords) {
    showToast('<i class="fa-solid fa-triangle-exclamation" style="color:#ef4444; margin-right:4px;"></i>รูปแบบพิกัดไม่ถูกต้อง กรุณากรอก เช่น 13.7563, 100.5018');
    return;
  }

  const { lat, lon } = coords;
  const inputEl = document.getElementById('inmap-coord-input');
  const clearBtn = document.getElementById('inmap-clear-coord-btn');
  if (inputEl) inputEl.value = `${lat.toFixed(5)}, ${lon.toFixed(5)}`;
  if (clearBtn) clearBtn.style.display = 'inline-flex';

  // Clear prop id search input if any
  const propInp = document.getElementById('inmap-prop-search-input');
  const propClr = document.getElementById('inmap-clear-search-btn');
  if (propInp) propInp.value = '';
  if (propClr) propClr.style.display = 'none';

  closePropertyCard();

  // Display according to pin mode
  if (mapPinMode !== 'radius') {
    mapPinMode = 'radius';
    const btnLoc = document.getElementById('btn-mode-location');
    const btnRad = document.getElementById('btn-mode-radius');
    if (btnLoc) btnLoc.classList.toggle('active', false);
    if (btnRad) btnRad.classList.toggle('active', true);
  }

  currentRefProp = null;
  setReferencePoint(lon, lat, true);

  showToast(`<i class="fa-solid fa-location-crosshairs" style="color:#10b981; margin-right:4px;"></i>ปักหมุดจุดอ้างอิงที่พิกัด: <b>${lat.toFixed(5)}, ${lon.toFixed(5)}</b>`);
}

function clearInMapCustomCoord() {
  const inputEl = document.getElementById('inmap-coord-input');
  const clearBtn = document.getElementById('inmap-clear-coord-btn');
  if (inputEl) inputEl.value = '';
  if (clearBtn) clearBtn.style.display = 'none';
  clearReferencePoint();
}

// ==========================================
// CURRENT LOCATION (BROWSER GPS GEOLOCATION)
// ==========================================
let _isLocatingCurrentPos = false;

function _setLocateBtnState(state) {
  const btn = document.getElementById('map-locate-btn');
  const icon = document.getElementById('map-locate-icon');
  if (!btn) return;
  if (state === 'loading') {
    btn.classList.add('locating');
    btn.disabled = true;
    if (icon) icon.className = 'fa-solid fa-spinner fa-spin';
  } else if (state === 'located') {
    btn.classList.remove('locating');
    btn.classList.add('located');
    btn.disabled = false;
    if (icon) icon.className = 'fa-solid fa-location-crosshairs';
  } else {
    btn.classList.remove('locating');
    btn.classList.toggle('located', Boolean(typeof userCurrentLocation !== 'undefined' && userCurrentLocation));
    btn.disabled = false;
    if (icon) icon.className = 'fa-solid fa-location-crosshairs';
  }
}

function _resolveBrowserGeolocation() {
  let parentWin = null;
  try {
    if (window.parent && window.parent !== window && window.parent.navigator && window.parent.navigator.geolocation) {
      parentWin = window.parent;
    }
  } catch (_e) {
    parentWin = null;
  }

  const hostWin = parentWin || window;
  const geo = (parentWin && parentWin.navigator && parentWin.navigator.geolocation)
    ? parentWin.navigator.geolocation
    : (navigator && navigator.geolocation ? navigator.geolocation : null);

  let isSecure = true;
  try {
    if (typeof hostWin.isSecureContext === 'boolean') {
      isSecure = hostWin.isSecureContext;
    } else if (hostWin.location) {
      const proto = hostWin.location.protocol;
      const host = hostWin.location.hostname;
      isSecure = (proto === 'https:' || host === 'localhost' || host === '127.0.0.1' || host === '[::1]');
    }
  } catch (_e) {}

  return { geo, isSecure };
}

function _formatGpsAccuracy(accMeters) {
  if (!Number.isFinite(accMeters) || accMeters <= 0) return '';
  if (accMeters >= 1000) return `±${(accMeters / 1000).toFixed(1)} กม.`;
  return `±${Math.round(accMeters)} ม.`;
}

function locateCurrentPosition() {
  if (_isLocatingCurrentPos) return;

  const { geo, isSecure } = _resolveBrowserGeolocation();
  if (!isSecure) {
    showToast('<i class="fa-solid fa-shield-halved" style="color:#f59e0b; margin-right:5px;"></i>เบราว์เซอร์บล็อก GPS บน HTTP — กรุณาเปิดผ่าน <b>HTTPS</b> หรือ <b>localhost</b> เพื่อใช้ตำแหน่งปัจจุบัน');
    return;
  }
  if (!geo) {
    showToast('<i class="fa-solid fa-triangle-exclamation" style="color:#ef4444; margin-right:5px;"></i>เบราว์เซอร์นี้ไม่รองรับการดึงตำแหน่งปัจจุบัน (Geolocation)');
    return;
  }

  _isLocatingCurrentPos = true;
  _setLocateBtnState('loading');
  showToast('<i class="fa-solid fa-spinner fa-spin" style="color:#2563eb; margin-right:6px;"></i>กำลังค้นหาตำแหน่งปัจจุบัน (GPS)...');

  const handleSuccess = (pos) => {
    _isLocatingCurrentPos = false;
    const coords = pos && pos.coords ? pos.coords : null;
    const lat = coords ? Number(coords.latitude) : NaN;
    const lon = coords ? Number(coords.longitude) : NaN;
    const accuracy = coords && Number.isFinite(Number(coords.accuracy)) ? Number(coords.accuracy) : null;

    if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
      _setLocateBtnState('idle');
      showToast('<i class="fa-solid fa-triangle-exclamation" style="color:#ef4444; margin-right:5px;"></i>ไม่ได้รับค่าพิกัดจากอุปกรณ์ กรุณาลองใหม่อีกครั้ง');
      return;
    }

    if (lat < 5.0 || lat > 21.0 || lon < 97.0 || lon > 106.0) {
      _setLocateBtnState('idle');
      showToast(`<i class="fa-solid fa-triangle-exclamation" style="color:#f59e0b; margin-right:5px;"></i>ตำแหน่งปัจจุบัน (${lat.toFixed(5)}, ${lon.toFixed(5)}) อยู่นอกประเทศไทย จึงไม่สามารถปักหมุดค้นหาทรัพย์ได้`);
      return;
    }

    userCurrentLocation = { lon, lat, accuracy };

    // Update coordinate input box & clear previous property/place search state
    const inputEl = document.getElementById('inmap-coord-input');
    const clearBtn = document.getElementById('inmap-clear-coord-btn');
    if (inputEl) inputEl.value = `${lat.toFixed(5)}, ${lon.toFixed(5)}`;
    if (clearBtn) clearBtn.style.display = 'inline-flex';

    const propInp = document.getElementById('inmap-prop-search-input');
    const propClr = document.getElementById('inmap-clear-search-btn');
    if (propInp) propInp.value = '';
    if (propClr) propClr.style.display = 'none';

    const placeInp = document.getElementById('place-search-input');
    const placeClr = document.getElementById('place-search-clear');
    if (placeInp) placeInp.value = '';
    if (placeClr) placeClr.style.display = 'none';
    if (typeof hidePlaceSearchResults === 'function') hidePlaceSearchResults();

    if (typeof closePropertyCard === 'function') closePropertyCard();

    currentRefProp = null;
    currentRefId = '';
    setReferencePoint(lon, lat, true, true);
    _setLocateBtnState('located');

    const accLabel = _formatGpsAccuracy(accuracy);
    const accSuffix = accLabel ? ` (${accLabel})` : '';
    showToast(`<i class="fa-solid fa-location-crosshairs" style="color:#2563eb; margin-right:5px;"></i>ปักหมุดตำแหน่งปัจจุบัน: <b>${lat.toFixed(5)}, ${lon.toFixed(5)}</b>${accSuffix}`);
  };

  const handleFinalError = (err) => {
    _isLocatingCurrentPos = false;
    _setLocateBtnState('idle');
    const code = err && typeof err.code === 'number' ? err.code : 0;
    const msg = (err && err.message ? String(err.message) : '').toLowerCase();
    if (code === 1) {
      if (msg.includes('secure') || msg.includes('https')) {
        showToast('<i class="fa-solid fa-shield-halved" style="color:#f59e0b; margin-right:5px;"></i>เบราว์เซอร์บล็อก GPS บน HTTP — กรุณาเปิดผ่าน <b>HTTPS</b> หรือ <b>localhost</b>');
      } else {
        showToast('<i class="fa-solid fa-location-crosshairs" style="color:#ef4444; margin-right:5px;"></i>ไม่ได้รับสิทธิ์เข้าถึงตำแหน่ง — กรุณากดอนุญาตสิทธิ์ตำแหน่ง (Location) ในเบราว์เซอร์แล้วลองใหม่');
      }
    } else if (code === 2) {
      showToast('<i class="fa-solid fa-satellite-dish" style="color:#f59e0b; margin-right:5px;"></i>ไม่สามารถระบุตำแหน่งได้ในขณะนี้ กรุณาเปิดบริการตำแหน่ง (Location Service) ของอุปกรณ์');
    } else if (code === 3) {
      showToast('<i class="fa-solid fa-clock" style="color:#f59e0b; margin-right:5px;"></i>หมดเวลาการค้นหาตำแหน่ง GPS กรุณาลองกดใหม่อีกครั้ง');
    } else {
      showToast('<i class="fa-solid fa-triangle-exclamation" style="color:#ef4444; margin-right:5px;"></i>ไม่สามารถดึงตำแหน่งปัจจุบันได้ กรุณาลองใหม่อีกครั้ง');
    }
  };

  const requestPosition = (highAccuracy, allowFallback) => {
    try {
      geo.getCurrentPosition(
        handleSuccess,
        (err) => {
          // On desktops without GPS hardware, high-accuracy can timeout or report unavailable; retry once with standard accuracy
          if (allowFallback && err && (err.code === 2 || err.code === 3)) {
            requestPosition(false, false);
            return;
          }
          handleFinalError(err);
        },
        {
          enableHighAccuracy: highAccuracy,
          timeout: highAccuracy ? 10000 : 12000,
          maximumAge: highAccuracy ? 15000 : 60000,
        }
      );
    } catch (e) {
      handleFinalError(e);
    }
  };

  requestPosition(true, true);
}

// ==========================================
// SAVED REFERENCE COORDINATES (LOCALSTORAGE)
// ==========================================
const SAVED_COORDS_LEGACY_KEY = 'nova_saved_reference_coords';
function getSavedCoordsStorageKey() {
  try {
    const pdoc = window.parent && window.parent.document;
    const userEl = pdoc && pdoc.querySelector('[data-nova-user]');
    const uname = userEl ? (userEl.getAttribute('data-nova-user') || '').trim().toLowerCase().replace(/[^a-z0-9_.-]/g, '') : '';
    if (uname) return SAVED_COORDS_LEGACY_KEY + ':' + uname;
  } catch (_e) {}
  return SAVED_COORDS_LEGACY_KEY;
}
const SAVED_COORDS_STORAGE_KEY = getSavedCoordsStorageKey();

function getSavedCoordinates() {
  try {
    let raw = localStorage.getItem(SAVED_COORDS_STORAGE_KEY);
    if (!raw && SAVED_COORDS_STORAGE_KEY !== SAVED_COORDS_LEGACY_KEY) {
      raw = localStorage.getItem(SAVED_COORDS_LEGACY_KEY);
    }
    if (!raw) return [];
    const list = JSON.parse(raw);
    return Array.isArray(list) ? list.filter(item => item && typeof item === 'object' && Number.isFinite(Number(item.lat)) && Number.isFinite(Number(item.lon))) : [];
  } catch (e) {
    console.error('Error reading saved coordinates:', e);
    return [];
  }
}

function saveCoordinatesList(list) {
  try {
    localStorage.setItem(SAVED_COORDS_STORAGE_KEY, JSON.stringify(list));
  } catch (e) {
    console.error('Error saving coordinates to localStorage:', e);
  }
}

function getNextDefaultCoordName(list) {
  let n = 1;
  while (list.some(item => item && item.name === `พิกัดอ้างอิง ${n}`)) {
    n++;
  }
  return `พิกัดอ้างอิง ${n}`;
}

function renderSavedCoordinatesPills() {
  const bar = document.getElementById('saved-coords-bar');
  const container = document.getElementById('saved-coords-container');
  if (!bar || !container) return;

  const list = getSavedCoordinates();
  if (!list || list.length === 0) {
    bar.style.display = 'none';
    container.innerHTML = '';
    return;
  }

  bar.style.display = 'flex';
  const curLat = referencePoint ? referencePoint[1] : null;
  const curLon = referencePoint ? referencePoint[0] : null;

  container.innerHTML = list.map(item => {
    const latNum = Number(item.lat);
    const lonNum = Number(item.lon);
    const isActive = (curLat !== null && curLon !== null &&
      Math.abs(latNum - curLat) < 0.0001 &&
      Math.abs(lonNum - curLon) < 0.0001);
    const safeId = escapeHtml(item.id || '');
    const safeName = escapeHtml(item.name || 'พิกัดอ้างอิง');
    const safeDesc = item.desc ? escapeHtml(item.desc) : '';
    const tooltip = safeDesc ? `${safeName}: ${safeDesc} (${latNum.toFixed(5)}, ${lonNum.toFixed(5)})` : `${safeName} (${latNum.toFixed(5)}, ${lonNum.toFixed(5)})`;
    const radiusText = item.radius ? `${parseFloat(item.radius).toFixed(1).replace(/\.0$/, '')} กม.` : '5 กม.';

    return `
      <div class="saved-coord-pill ${isActive ? 'active' : ''}"
           data-id="${safeId}"
           data-coord-id="${safeId}"
           onclick="activateSavedCoordinate(this.dataset.coordId)"
           title="${tooltip}">
        <i class="fa-solid fa-location-dot pill-icon"></i>
        <span>${safeName}</span>
        <span class="pill-radius">(${radiusText})</span>
        <button type="button" class="pill-del-btn" data-coord-id="${safeId}" onclick="deleteSavedCoordinate(event, this.dataset.coordId)" title="ลบพิกัดนี้">
          <i class="fa-solid fa-xmark"></i>
        </button>
      </div>
    `;
  }).join('');
}

function updateSavedCoordsPillsActiveState(lat, lon) {
  const pills = document.querySelectorAll('#saved-coords-container .saved-coord-pill');
  if (!pills || pills.length === 0) return;
  const list = getSavedCoordinates();
  const map = new Map(list.map(i => [i.id, i]));

  pills.forEach(pill => {
    const id = pill.getAttribute('data-id');
    const item = map.get(id);
    if (item && lat !== null && lon !== null &&
        Math.abs(item.lat - lat) < 0.0001 &&
        Math.abs(item.lon - lon) < 0.0001) {
      pill.classList.add('active');
    } else {
      pill.classList.remove('active');
    }
  });
}

function openSaveCoordinateModal() {
  let lat = null;
  let lon = null;

  if (referencePoint && referencePoint.length >= 2) {
    lon = parseFloat(referencePoint[0]);
    lat = parseFloat(referencePoint[1]);
  } else {
    const inp = document.getElementById('inmap-coord-input');
    const val = inp ? inp.value.trim() : '';
    if (val) {
      const parsed = parseCoordinateString(val);
      if (parsed) {
        lat = parsed.lat;
        lon = parsed.lon;
      }
    }
  }

  if (lat === null || lon === null || isNaN(lat) || isNaN(lon)) {
    showToast('<i class="fa-solid fa-circle-exclamation" style="color:#f59e0b; margin-right:4px;"></i>กรุณากรอกพิกัดหรือปักหมุดบนแผนที่ก่อนบันทึก');
    const inp = document.getElementById('inmap-coord-input');
    if (inp) inp.focus();
    return;
  }

  const list = getSavedCoordinates();
  const defaultName = getNextDefaultCoordName(list);
  const nameInp = document.getElementById('save-coord-name-input');
  const posInp = document.getElementById('save-coord-pos-input');
  const radInp = document.getElementById('save-coord-radius-input');
  const descInp = document.getElementById('save-coord-desc-input');

  if (nameInp) nameInp.value = defaultName;
  if (posInp) {
    posInp.value = `${lat.toFixed(5)}, ${lon.toFixed(5)}`;
    posInp.setAttribute('data-lat', lat);
    posInp.setAttribute('data-lon', lon);
  }
  if (radInp) radInp.value = currentRadiusKm ? currentRadiusKm.toFixed(1) : '5.0';
  if (descInp) descInp.value = '';

  const modal = document.getElementById('save-coord-modal');
  if (modal) {
    modal.classList.add('show');
    setTimeout(() => { if (nameInp) nameInp.select(); }, 100);
  }
}

function closeSaveCoordinateModal() {
  const modal = document.getElementById('save-coord-modal');
  if (modal) modal.classList.remove('show');
}

function confirmSaveCoordinate() {
  const nameInp = document.getElementById('save-coord-name-input');
  const posInp = document.getElementById('save-coord-pos-input');
  const radInp = document.getElementById('save-coord-radius-input');
  const descInp = document.getElementById('save-coord-desc-input');

  const lat = parseFloat(posInp ? posInp.getAttribute('data-lat') : 0);
  const lon = parseFloat(posInp ? posInp.getAttribute('data-lon') : 0);
  if (isNaN(lat) || isNaN(lon) || lat === 0 || lon === 0) {
    showToast('<i class="fa-solid fa-triangle-exclamation" style="color:#ef4444; margin-right:4px;"></i>ไม่พบค่าพิกัดที่ถูกต้อง');
    return;
  }

  const list = getSavedCoordinates();
  const defaultName = getNextDefaultCoordName(list);
  const name = (nameInp && nameInp.value.trim()) ? nameInp.value.trim() : defaultName;
  const radius = parseFloat(radInp && radInp.value ? radInp.value : 5.0) || 5.0;
  const desc = descInp ? descInp.value.trim() : '';

  const newRecord = {
    id: 'coord_' + Date.now() + '_' + Math.random().toString(36).substr(2, 5),
    name: name,
    lat: lat,
    lon: lon,
    radius: radius,
    desc: desc,
    createdAt: new Date().toISOString()
  };

  list.push(newRecord);
  saveCoordinatesList(list);
  closeSaveCoordinateModal();

  // Pin to this coordinate if not already there
  if (!referencePoint || Math.abs(referencePoint[1] - lat) > 0.0001 || Math.abs(referencePoint[0] - lon) > 0.0001) {
    if (currentRadiusKm !== radius) {
      currentRadiusKm = Math.max(0.05, Math.min(20, radius));
      updateRadiusSliderUi(currentRadiusKm);
    }
    setReferencePoint(lon, lat, true, true);
  } else {
    renderSavedCoordinatesPills();
  }

  showToast(`<i class="fa-solid fa-circle-check" style="color:#10b981; margin-right:4px;"></i>บันทึก "<b>${escapeHtml(name)}</b>" เรียบร้อยแล้ว`);
}

function activateSavedCoordinate(id) {
  const list = getSavedCoordinates();
  const item = list.find(x => x.id === id);
  if (!item) return;

  // Apply radius
  if (item.radius && item.radius > 0) {
    currentRadiusKm = Math.max(0.05, Math.min(20, parseFloat(item.radius) || 5));
    updateRadiusSliderUi(currentRadiusKm);
  }

  // Apply pin
  currentRefProp = null;
  setReferencePoint(item.lon, item.lat, true, true);

  // Update coordinate input
  const inputEl = document.getElementById('inmap-coord-input');
  const clearBtn = document.getElementById('inmap-clear-coord-btn');
  if (inputEl) inputEl.value = `${item.lat.toFixed(5)}, ${item.lon.toFixed(5)}`;
  if (clearBtn) clearBtn.style.display = 'inline-flex';

  // Clear property search
  const propInp = document.getElementById('inmap-prop-search-input');
  const propClr = document.getElementById('inmap-clear-search-btn');
  if (propInp) propInp.value = '';
  if (propClr) propClr.style.display = 'none';

  updateSavedCoordsPillsActiveState(item.lat, item.lon);
  showToast(`<i class="fa-solid fa-location-crosshairs" style="color:#10b981; margin-right:4px;"></i>ปักหมุด: <b>${escapeHtml(item.name)}</b> (${item.lat.toFixed(5)}, ${item.lon.toFixed(5)})`);
}

function deleteSavedCoordinate(event, id) {
  if (event) {
    event.stopPropagation();
    event.preventDefault();
  }

  const list = getSavedCoordinates();
  const idx = list.findIndex(x => x.id === id);
  if (idx === -1) return;
  const deletedName = list[idx].name;

  list.splice(idx, 1);
  saveCoordinatesList(list);

  renderSavedCoordinatesPills();

  // If manage modal is currently open, refresh it
  const manageModal = document.getElementById('manage-coords-modal');
  if (manageModal && manageModal.classList.contains('show')) {
    renderManageCoordinatesList();
  }

  showToast(`<i class="fa-solid fa-trash-can" style="color:#ef4444; margin-right:4px;"></i>ลบ "<b>${escapeHtml(deletedName)}</b>" เรียบร้อยแล้ว`);
}

function openManageSavedCoordsModal() {
  renderManageCoordinatesList();
  const modal = document.getElementById('manage-coords-modal');
  if (modal) modal.classList.add('show');
}

function closeManageSavedCoordsModal() {
  const modal = document.getElementById('manage-coords-modal');
  if (modal) modal.classList.remove('show');
}

function renderManageCoordinatesList() {
  const container = document.getElementById('manage-coords-list-container');
  const countBadge = document.getElementById('manage-coords-count-badge');
  if (!container) return;

  const list = getSavedCoordinates();
  if (countBadge) countBadge.innerText = `${list.length} รายการ`;

  if (!list || list.length === 0) {
    container.innerHTML = `
      <div style="text-align: center; padding: 36px 16px; color: #94a3b8; font-size: 13px;">
        <i class="fa-regular fa-folder-open" style="font-size: 32px; display: block; margin-bottom: 8px; opacity: 0.6;"></i>
        ยังไม่มีพิกัดอ้างอิงที่บันทึกไว้<br>
        <span style="font-size: 11.5px; opacity: 0.8;">คุณสามารถกรอกพิกัดหรือปักหมุดบนแผนที่ แล้วกดปุ่มไอคอน Bookmark เพื่อบันทึกได้ทันที</span>
      </div>
    `;
    const btnClear = document.getElementById('btn-clear-all-saved-coords');
    if (btnClear) btnClear.style.display = 'none';
    return;
  }

  const btnClear = document.getElementById('btn-clear-all-saved-coords');
  if (btnClear) btnClear.style.display = 'inline-flex';

  const curLat = referencePoint ? referencePoint[1] : null;
  const curLon = referencePoint ? referencePoint[0] : null;

  container.innerHTML = list.map(item => {
    const latNum = Number(item.lat);
    const lonNum = Number(item.lon);
    const radNum = Number(item.radius) || 5;
    const safeId = escapeHtml(item.id || '');
    const isActive = (curLat !== null && curLon !== null &&
      Math.abs(latNum - curLat) < 0.0001 &&
      Math.abs(lonNum - curLon) < 0.0001);

    return `
      <div class="saved-coord-card ${isActive ? 'active-pin' : ''}" id="card-coord-${safeId}">
        <div style="flex: 1; min-width: 0;" id="view-coord-${safeId}">
          <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 3px;">
            <i class="fa-solid fa-location-dot" style="color: ${isActive ? '#059669' : '#10b981'}; font-size: 12px;"></i>
            <span style="font-weight: 800; font-size: 13px; color: inherit; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
              ${escapeHtml(item.name)}
            </span>
            ${isActive ? '<span style="font-size: 10px; font-weight: 800; background: #10b981; color: #fff; padding: 1px 6px; border-radius: 9999px;">ปักหมุดอยู่</span>' : ''}
          </div>
          <div style="font-size: 11px; color: #64748b; display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
            <span><i class="fa-solid fa-location-crosshairs" style="color: #94a3b8; font-size: 10px;"></i> ${latNum.toFixed(5)}, ${lonNum.toFixed(5)}</span>
            <span><i class="fa-solid fa-circle-dot" style="color: #3b82f6; font-size: 10px;"></i> รัศมี ${radNum} กม.</span>
          </div>
          ${item.desc ? `<div class="saved-coord-desc" style="font-size: 11px; color: #475569; margin-top: 4px; font-style: italic; background: rgba(0,0,0,0.03); padding: 2px 6px; border-radius: 4px; display: inline-block;">${escapeHtml(item.desc)}</div>` : ''}
        </div>

        <!-- Inline Edit Form (Hidden by default) -->
        <div style="flex: 1; display: none; flex-direction: column; gap: 6px;" id="edit-coord-${safeId}">
          <input type="text" id="edit-name-${safeId}" class="save-coord-input" style="padding: 4px 8px; font-size: 12px;" value="${escapeHtml(item.name)}" placeholder="ชื่อพิกัด" />
          <div style="display: flex; gap: 6px;">
            <input type="number" id="edit-rad-${safeId}" class="save-coord-input" style="padding: 4px 8px; font-size: 11px; width: 85px;" value="${radNum}" min="0.5" max="50" step="0.5" placeholder="รัศมี (กม.)" />
            <input type="text" id="edit-desc-${safeId}" class="save-coord-input" style="padding: 4px 8px; font-size: 11px; flex: 1;" value="${escapeHtml(item.desc || '')}" placeholder="รายละเอียด (ไม่บังคับ)" />
          </div>
          <div style="display: flex; gap: 4px; margin-top: 2px;">
            <button type="button" class="saved-coord-card-btn pin-btn" data-coord-id="${safeId}" onclick="saveEditSavedCoord(this.dataset.coordId)">
              <i class="fa-solid fa-check"></i> บันทึก
            </button>
            <button type="button" class="saved-coord-card-btn" style="background:#e2e8f0; color:#475569;" data-coord-id="${safeId}" onclick="cancelEditSavedCoord(this.dataset.coordId)">
              <i class="fa-solid fa-xmark"></i> ยกเลิก
            </button>
          </div>
        </div>

        <!-- Action buttons -->
        <div style="display: flex; align-items: center; gap: 4px; flex-shrink: 0;" id="actions-coord-${safeId}">
          <button type="button" class="saved-coord-card-btn pin-btn" data-coord-id="${safeId}" onclick="activateSavedCoordinate(this.dataset.coordId); closeManageSavedCoordsModal();" title="ปักหมุดพิกัดนี้">
            <i class="fa-solid fa-location-crosshairs"></i> ปักหมุด
          </button>
          <button type="button" class="saved-coord-card-btn edit-btn" data-coord-id="${safeId}" onclick="startEditSavedCoord(this.dataset.coordId)" title="แก้ไข">
            <i class="fa-solid fa-pen"></i> แก้ไข
          </button>
          <button type="button" class="saved-coord-card-btn delete-btn" data-coord-id="${safeId}" onclick="deleteSavedCoordinate(event, this.dataset.coordId)" title="ลบพิกัดนี้">
            <i class="fa-solid fa-trash-can"></i> ลบ
          </button>
        </div>
      </div>
    `;
  }).join('');
}

function startEditSavedCoord(id) {
  const viewEl = document.getElementById('view-coord-' + id);
  const editEl = document.getElementById('edit-coord-' + id);
  const actEl = document.getElementById('actions-coord-' + id);
  if (viewEl && editEl && actEl) {
    viewEl.style.display = 'none';
    actEl.style.display = 'none';
    editEl.style.display = 'flex';
  }
}

function cancelEditSavedCoord(id) {
  const viewEl = document.getElementById('view-coord-' + id);
  const editEl = document.getElementById('edit-coord-' + id);
  const actEl = document.getElementById('actions-coord-' + id);
  if (viewEl && editEl && actEl) {
    editEl.style.display = 'none';
    viewEl.style.display = 'block';
    actEl.style.display = 'flex';
  }
}

function saveEditSavedCoord(id) {
  const nameInp = document.getElementById('edit-name-' + id);
  const radInp = document.getElementById('edit-rad-' + id);
  const descInp = document.getElementById('edit-desc-' + id);

  const list = getSavedCoordinates();
  const item = list.find(x => x.id === id);
  if (!item) return;

  if (nameInp && nameInp.value.trim()) item.name = nameInp.value.trim();
  if (radInp && parseFloat(radInp.value) > 0) item.radius = parseFloat(radInp.value);
  if (descInp) item.desc = descInp.value.trim();

  saveCoordinatesList(list);
  renderSavedCoordinatesPills();
  renderManageCoordinatesList();
  showToast(`<i class="fa-solid fa-circle-check" style="color:#10b981; margin-right:4px;"></i>อัปเดตข้อมูล "<b>${escapeHtml(item.name)}</b>" เรียบร้อย`);
}

function clearAllSavedCoordinates() {
  if (!confirm('คุณต้องการลบรายการพิกัดอ้างอิงที่บันทึกไว้ทั้งหมดใช่หรือไม่?')) return;
  saveCoordinatesList([]);
  renderSavedCoordinatesPills();
  renderManageCoordinatesList();
  showToast('<i class="fa-solid fa-trash-can" style="color:#ef4444; margin-right:4px;"></i>ลบรายการพิกัดทั้งหมดเรียบร้อย');
}

function createBoundaryLayer() {
  // Handled by vector-crisp SVG overlay with dashed lines (stroke-dasharray="6, 5") and transparent fill
  return null;
}

function getDeckViewport() {
  if (deck && deck.WebMercatorViewport && currentViewState) {
    try {
      const mapEl = document.getElementById('map');
      const w = (mapEl && mapEl.clientWidth) || window.innerWidth || 800;
      const h = (mapEl && mapEl.clientHeight) || window.innerHeight || 600;
      return new deck.WebMercatorViewport({
        width: w,
        height: h,
        longitude: currentViewState.longitude,
        latitude: currentViewState.latitude,
        zoom: currentViewState.zoom,
        pitch: currentViewState.pitch || 0,
        bearing: currentViewState.bearing || 0
      });
    } catch(e) {}
  }
  if (!deckglInstance) return null;
  try {
    if (deckglInstance.getViewports && deckglInstance.getViewports().length > 0) {
      return deckglInstance.getViewports()[0];
    }
    if (deckglInstance.deck && deckglInstance.deck.viewManager && deckglInstance.deck.viewManager.getViewports && deckglInstance.deck.viewManager.getViewports().length > 0) {
      return deckglInstance.deck.viewManager.getViewports()[0];
    }
    if (deckglInstance.deck && deckglInstance.deck.getViewports && deckglInstance.deck.getViewports().length > 0) {
      return deckglInstance.deck.getViewports()[0];
    }
  } catch(e) {}
  return null;
}

function updateConfirmBubblePosition() {
  const bubble = document.getElementById('in-map-confirm-bubble');
  if (!bubble) return;
  if (!pendingReferencePoint || !deckglInstance) {
    bubble.style.display = 'none';
    return;
  }
  const viewport = getDeckViewport();
  if (!viewport) return;
  const [bx, by] = viewport.project([pendingReferencePoint[0], pendingReferencePoint[1]]);
  bubble.style.display = 'flex';
  bubble.style.left = `${bx.toFixed(1)}px`;
  bubble.style.top = `${by.toFixed(1)}px`;
}

function getPixelRadius(lon, lat, radiusKm, viewport) {
  if (!viewport) return 10;
  const latDelta = (radiusKm * 1000) / 111319.5;
  const [cx, cy] = viewport.project([lon, lat]);
  const [ex, ey] = viewport.project([lon, lat + latDelta]);
  return Math.max(5, Math.abs(cy - ey));
}
