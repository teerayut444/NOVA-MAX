function updateSvgBoundaries() {
  const svg = document.getElementById('boundary-svg');
  if (!svg) return;

  const viewport = getDeckViewport();
  if (!viewport) return;

  const w = window.innerWidth;
  const h = window.innerHeight;

  let svgContent = '';

  // 1. SPOTLIGHT / INVERTED MASK
  // Dims area outside selected province/district OR outside inspection radius
  let maskHoles = '';

  if (referencePoint) {
    // When reference point is set: spotlight around inspection radius circle
    const [cx, cy] = viewport.project([referencePoint[0], referencePoint[1]]);
    const rPx = getPixelRadius(referencePoint[0], referencePoint[1], currentRadiusKm, viewport);

    maskHoles += ` M ${cx.toFixed(1)} ${(cy - rPx).toFixed(1)} A ${rPx.toFixed(1)} ${rPx.toFixed(1)} 0 1 0 ${cx.toFixed(1)} ${(cy + rPx).toFixed(1)} A ${rPx.toFixed(1)} ${rPx.toFixed(1)} 0 1 0 ${cx.toFixed(1)} ${(cy - rPx).toFixed(1)} Z`;
  } else if (boundaryGeoJson && boundaryGeoJson.features && boundaryGeoJson.features.length > 0) {
    // When province/district/subdistrict selected: spotlight around boundary!
    boundaryGeoJson.features.forEach(feat => {
      if (!feat.geometry) return;
      const geomType = feat.geometry.type;
      const coords = feat.geometry.coordinates;

      function ringToPath(ring) {
        if (!ring || ring.length < 2) return '';
        let d = '';
        for (let i = 0; i < ring.length; i++) {
          const pt = ring[i];
          if (typeof pt[0] !== 'number' || typeof pt[1] !== 'number') continue;
          const [px, py] = viewport.project([pt[0], pt[1]]);
          d += (i === 0 ? 'M ' : ' L ') + px.toFixed(1) + ' ' + py.toFixed(1);
        }
        return d ? d + ' Z' : '';
      }

      if (geomType === 'Polygon') {
        coords.forEach(ring => { maskHoles += ' ' + ringToPath(ring); });
      } else if (geomType === 'MultiPolygon') {
        coords.forEach(poly => {
          poly.forEach(ring => { maskHoles += ' ' + ringToPath(ring); });
        });
      }
    });
  }

  if (maskHoles) {
    const outerRect = `M -120 -120 L ${w + 120} -120 L ${w + 120} ${h + 120} L -120 ${h + 120} Z`;
    const dimFill = "rgba(15, 23, 42, 0.65)";
    svgContent += `<path d="${outerRect} ${maskHoles}" fill="${dimFill}" fill-rule="evenodd" pointer-events="none" />`;
  }

  // 2. BOUNDARY LINES (Dashed for subdistricts / districts, solid for single boundary)
  if (boundaryGeoJson && boundaryGeoJson.features && boundaryGeoJson.features.length > 0) {
    boundaryGeoJson.features.forEach(feat => {
      if (!feat.geometry) return;
      const geomType = feat.geometry.type;
      const coords = feat.geometry.coordinates;
      const level = (feat.properties && feat.properties.level) || (boundaryGeoJson.features.length > 1 ? 'district' : 'province');

      function ringToPathD(ring) {
        if (!ring || ring.length < 2) return '';
        let d = '';
        for (let i = 0; i < ring.length; i++) {
          const pt = ring[i];
          if (typeof pt[0] !== 'number' || typeof pt[1] !== 'number') continue;
          const [px, py] = viewport.project([pt[0], pt[1]]);
          d += (i === 0 ? 'M ' : ' L ') + px.toFixed(1) + ' ' + py.toFixed(1);
        }
        return d ? d + ' Z' : '';
      }

      let featD = '';
      if (geomType === 'Polygon') {
        coords.forEach(ring => { featD += ' ' + ringToPathD(ring); });
      } else if (geomType === 'MultiPolygon') {
        coords.forEach(poly => {
          poly.forEach(ring => { featD += ' ' + ringToPathD(ring); });
        });
      }

      if (featD) {
        if (level === 'subdistrict' || level === 'single_subdistrict') {
          // Simple dashed emerald line for subdistrict boundaries
          svgContent += `<path d="${featD}" fill="none" stroke="#10b981" stroke-width="2" stroke-dasharray="6, 5" stroke-linejoin="round" pointer-events="none" />`;
        } else if (level === 'district' || level === 'single_district') {
          // Simple dashed green line for district boundaries
          svgContent += `<path d="${featD}" fill="none" stroke="#34d399" stroke-width="2.2" stroke-dasharray="7, 5" stroke-linejoin="round" pointer-events="none" />`;
        } else {
          // Province outer boundary: simple solid green line
          svgContent += `<path d="${featD}" fill="none" stroke="#059669" stroke-width="2.5" stroke-linejoin="round" pointer-events="none" />`;
        }
      }
    });
  }

  // 3. LIVE RADIUS PREVIEW CIRCLE (Dashed circle when pendingReferencePoint is active!)
  if (pendingReferencePoint) {
    const [cx, cy] = viewport.project([pendingReferencePoint[0], pendingReferencePoint[1]]);
    const rPx = getPixelRadius(pendingReferencePoint[0], pendingReferencePoint[1], currentRadiusKm, viewport);

    svgContent += `
      <circle cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="${rPx.toFixed(1)}"
              fill="rgba(245, 158, 11, 0.12)" stroke="#f59e0b" stroke-width="2.2"
              stroke-dasharray="7, 5" pointer-events="none" />
    `;
  }

  // 4. DISTRICT & SUBDISTRICT NAME LABELS (Pill Badges)
  const labelsContainer = document.getElementById('district-labels-container');
  let labelsHtml = '';

  if (districtLabels && districtLabels.length > 0 && !referencePoint) {
    const bndLevel = (boundaryGeoJson && boundaryGeoJson.level) || 'district';
    const isSubdist = bndLevel === 'subdistrict' || bndLevel === 'single_subdistrict';
    const activeClass = bndLevel === 'single_subdistrict' ? 'active-subdist' : '';
    const labelPrefix = isSubdist ? 'ต.' : 'อ.';

    districtLabels.forEach(lbl => {
      if (typeof lbl.lon !== 'number' || typeof lbl.lat !== 'number') return;
      let lon = lbl.lon;
      let lat = lbl.lat;
      if (lbl.name === 'คลองเตย' && (lon > 100.565 || lat > 13.725)) {
        lon = 100.5598;
        lat = 13.71995;
      }
      const [px, py] = viewport.project([lon, lat]);
      if (px >= -60 && px <= w + 60 && py >= -60 && py <= h + 60) {
        labelsHtml += `
          <div class="district-label-pill ${activeClass}" style="left: ${px.toFixed(1)}px; top: ${py.toFixed(1)}px;">
            ${labelPrefix} ${escapeHtml(lbl.name || '')}
          </div>
        `;
      }
    });
  }

  svg.innerHTML = svgContent;
  if (labelsContainer) labelsContainer.innerHTML = labelsHtml;
  updateConfirmBubblePosition();
}

let initialCompanyLegendHtml = '';

let _memoMarkersCoordMap = null;
let _memoMarkersDataLen = -1;
let _memoMarkersResult = null;
function getUniqueCoordMarkers(data) {
  if (!data || data.length === 0) return { pins: [], multiPins: [] };
  const coordMap = currentCoordMap || buildCoordMap(data);
  if (_memoMarkersCoordMap === coordMap && _memoMarkersDataLen === data.length && _memoMarkersResult) {
    return _memoMarkersResult;
  }
  const pins = [];
  const multiPins = [];

  for (const [key, stack] of coordMap.entries()) {
    if (!stack || stack.length === 0) continue;
    const topItem = stack[0];
    const count = stack.length;
    const isCentroid = String(topItem._centroid) === '1';

    const pinObj = {
      item: topItem,
      lon: topItem.lon,
      lat: topItem.lat,
      count: count,
      isCentroid: isCentroid,
      key: key
    };
    pins.push(pinObj);

    if (count > 1 || isCentroid) {
      multiPins.push(pinObj);
    }
  }
  _memoMarkersCoordMap = coordMap;
  _memoMarkersDataLen = data.length;
  _memoMarkersResult = { pins, multiPins };
  return _memoMarkersResult;
}

function renderHtmlMarkers() {
  // Pins are now hardware-accelerated via WebGL IconLayer and TextLayer
  const container = document.getElementById('html-markers-container');
  if (container) container.innerHTML = '';
}

function updateHtmlMarkerPositions() {
  // No-op: GPU handles projection on every frame with 0 lag
}

function createPointLayers(data) {
  if (!data || data.length === 0 || !atlasBase64 || !iconMapping) {
    return [];
  }

  const { pins, multiPins } = getUniqueCoordMarkers(data);
  if (!pins || pins.length === 0) return [];

  const layers = [];

  // 1. Hardware-Accelerated WebGL IconLayer (128px Retina Atlas, 0 Lag, Anchored to map)
  layers.push(new deck.IconLayer({
    id: 'point-icons',
    data: pins,
    iconAtlas: atlasBase64,
    iconMapping: iconMapping,
    updateTriggers: {
      getIcon: [markerDisplayMode]
    },
    getIcon: d => {
      if (!iconMapping) return null;
      const src = d.item || d;
      const _hasOwn = Object.prototype.hasOwnProperty;
      if (markerDisplayMode === 'logo') {
        const co = (src._company || '').trim();
        if (_hasOwn.call(iconMapping, co)) return co;
        const coUp = co.toUpperCase();
        if (_hasOwn.call(iconMapping, coUp)) return coUp;
        const coLow = co.toLowerCase();
        if (_hasOwn.call(iconMapping, coLow)) return coLow;
        if (_hasOwn.call(iconMapping, 'ไฟล์นำเข้า')) return 'ไฟล์นำเข้า';
        return 'SAM';
      } else {
        const tp = (src._type || '').trim();
        if (_hasOwn.call(iconMapping, tp)) return tp;
        for (let kIdx = 0; kIdx < sortedIconMappingKeys.length; kIdx++) {
          const key = sortedIconMappingKeys[kIdx];
          if (tp.includes(key)) return key;
        }
        return 'อื่นๆ';
      }
    },
    getPosition: d => [d.lon, d.lat],
    getSize: d => (d.count > 1 ? 40 : 34),
    sizeScale: 1,
    pickable: true,
    billboard: true,
    useDevicePixels: (window.NovaMapCache && typeof window.NovaMapCache.isIOSOrIPadOS === 'function' && window.NovaMapCache.isIOSOrIPadOS()) ? 1 : true,
    autoHighlight: true,
    highlightColor: [255, 255, 255, 60]
  }));

  // 2. Hardware-Accelerated WebGL TextLayer (Duplicate counts and centroid badges)
  if (multiPins && multiPins.length > 0) {
    layers.push(new deck.TextLayer({
      id: 'point-badges',
      data: multiPins,
      getText: d => (d.isCentroid ? (d.count > 1 ? '~' + d.count : '~') : '+' + d.count),
      getPosition: d => [d.lon, d.lat],
      getPixelOffset: [14, -14],
      getSize: 11.5,
      getColor: [255, 255, 255, 255],
      backgroundColor: d => (d.isCentroid ? [217, 119, 6, 245] : [5, 150, 105, 245]),
      backgroundPadding: [4, 2, 4, 2],
      fontFamily: "'Inter', 'Noto Sans Thai', sans-serif",
      fontWeight: 800,
      pickable: false,
      billboard: true,
      characterSet: 'auto'
    }));
  }

  return layers;
}

function createPointLayer(data) {
  return createPointLayers(data)[0] || null;
}

function createScatterLayer(data) {
  return createPointLayer(data);
}

// View State & Compass Control Functions
let currentViewState = {
  longitude: 100.52,
  latitude: 13.75,
  zoom: 8.5,
  minZoom: 4,
  maxZoom: 20,
  bearing: 0,
  pitch: 0
};

function updateCompass(bearing) {
  const dial = document.getElementById('compass-dial');
  if (dial) {
    dial.style.transform = `rotate(${-bearing}deg)`;
  }
}

function resetNorth() {
  if (!deckglInstance) return;
  const lon = currentViewState.longitude || 100.52;
  const lat = currentViewState.latitude || 13.75;
  const zoom = currentViewState.zoom || 8.5;

  currentViewState = {
    ...currentViewState,
    longitude: lon,
    latitude: lat,
    zoom: zoom,
    bearing: 0,
    pitch: 0,
    transitionDuration: 500,
    transitionInterpolator: new deck.FlyToInterpolator()
  };

  deckglInstance.setProps({
    viewState: currentViewState
  });
  updateCompass(0);
}

let isLegendCollapsed = false;

function toggleLegendCollapse() {
  isLegendCollapsed = !isLegendCollapsed;
  const body = document.getElementById('legend-body-collapsible');
  const icon = document.getElementById('legend-collapse-icon');
  if (body) {
    body.style.display = isLegendCollapsed ? 'none' : 'block';
  }
  if (icon) {
    icon.className = isLegendCollapsed ? 'fa-solid fa-chevron-up' : 'fa-solid fa-chevron-down';
  }
}

function toggleFilterFromLegend(group, val) {
  const cssEsc = (s) => (window.CSS && typeof window.CSS.escape === 'function')
    ? window.CSS.escape(String(s))
    : String(s).replace(/["\\]/g, '\\$&');
  let chip = document.querySelector(`.filter-chip[data-group="${cssEsc(group)}"][data-val="${cssEsc(val)}"]`);
  toggleFilterChip(group, val, chip);
}

function setMarkerDisplayMode(mode, btnEl) {
  markerDisplayMode = mode || 'logo';
  _memoMarkersResult = null;
  const btnLogo = document.getElementById('btn-mode-logo');
  const btnType = document.getElementById('btn-mode-type');
  if (btnLogo) btnLogo.classList.toggle('active', markerDisplayMode === 'logo');
  if (btnType) btnType.classList.toggle('active', markerDisplayMode === 'type');

  updateLegendContent();
  updateDeckLayers();
}

function updateLegendContent() {
  const box = document.getElementById('legend-items-box');
  if (!box) return;

  // Strictly determine mode from markerDisplayMode (Logo vs Property Type) to ensure 100% synchronization
  const effectiveMode = markerDisplayMode || 'logo';
  const hasCompanyFilter = inMapFilterState && inMapFilterState.companies && inMapFilterState.companies.size > 0;
  const hasTypeFilter = inMapFilterState && inMapFilterState.types && inMapFilterState.types.size > 0;

  // Ensure top toggle buttons match effectiveMode
  const btnLogo = document.getElementById('btn-mode-logo');
  const btnType = document.getElementById('btn-mode-type');
  if (btnLogo) btnLogo.classList.toggle('active', effectiveMode === 'logo');
  if (btnType) btnType.classList.toggle('active', effectiveMode === 'type');

  // Update legend header title to indicate what is shown
  const titleEl = document.getElementById('legend-header-title');
  if (titleEl) {
    if (effectiveMode === 'logo') {
      titleEl.innerHTML = '<i class="fa-solid fa-building" style="color:#059669; margin-right:5px;"></i>ตามบริษัท';
    } else {
      titleEl.innerHTML = '<i class="fa-solid fa-house" style="color:#2563eb; margin-right:5px;"></i>ตามประเภททรัพย์';
    }
  }

  // Determine data currently visible on the map
  const hasProjFilter = Boolean(inMapFilterState && (
    (inMapFilterState.samProjects && inMapFilterState.samProjects.size > 0) ||
    (inMapFilterState.samProject && inMapFilterState.samProject !== '')
  ));

  let dataForLegend = [];
  if (hasProjFilter) {
    dataForLegend = (currentNearbyData && currentNearbyData.length > 0) ? currentNearbyData : (currentScopePool || []);
  } else if (mapPinMode === 'location') {
    const hasProvSelected = currentSelectedProv && currentSelectedProv.trim() !== '' && currentSelectedProv !== '__ALL__';
    if (!hasProvSelected) {
      dataForLegend = [];
    } else {
      dataForLegend = currentNearbyData || [];
    }
  } else {
    // radius mode
    if (referencePoint) {
      dataForLegend = currentNearbyData || [];
    } else {
      dataForLegend = (currentNearbyData && currentNearbyData.length > 0) ? currentNearbyData : [];
    }
  }

  const totalItems = (currentNearbyData && currentNearbyData.length > 0) ? currentNearbyData.length : dataForLegend.length;
  const totalBadge = document.getElementById('legend-header-total');
  if (totalBadge) {
    totalBadge.innerText = totalItems.toLocaleString();
  }

  if (dataForLegend.length === 0) {
    let emptyMsg = 'คลิกบนแผนที่เพื่อดูทรัพย์สิน';
    if (hasProjFilter) {
      emptyMsg = 'ไม่พบพิกัดทรัพย์สินในโครงการที่เลือก';
    } else if (mapPinMode === 'location') {
      emptyMsg = (currentSelectedProv && currentSelectedProv !== '__ALL__')
        ? 'ไม่พบทรัพย์สินตามเงื่อนไขที่เลือก'
        : 'กรุณาเลือกจังหวัดในแถบด้านบน';
    } else {
      emptyMsg = referencePoint ? 'ไม่พบทรัพย์สินในรัศมีที่กำหนด' : 'คลิกบนแผนที่เพื่อปักหมุดรัศมี';
    }
    box.innerHTML = `<div style="padding: 12px 6px; text-align: center; color: #94a3b8; font-size: 11px; font-style: italic;"><i class="fa-solid fa-map-location-dot" style="font-size:16px; margin-bottom:4px; display:block; opacity:0.6;"></i>${emptyMsg}</div>`;
    return;
  }

  // Use scope pool when filtering by company/type so other choices remain visible in the legend with full filter parity
  let poolForLegend = dataForLegend;
  if (effectiveMode === 'logo' && hasCompanyFilter && typeof currentScopePool !== 'undefined' && currentScopePool && currentScopePool.length > 0) {
    poolForLegend = currentScopePool.filter(d => filterItemPasses(d, 'company'));
  } else if (effectiveMode === 'type' && hasTypeFilter && typeof currentScopePool !== 'undefined' && currentScopePool && currentScopePool.length > 0) {
    poolForLegend = currentScopePool.filter(d => filterItemPasses(d, 'type'));
  }
  if (!poolForLegend || poolForLegend.length === 0) {
    poolForLegend = dataForLegend;
  }

  if (effectiveMode === 'logo') {
    // Group by Company (null-prototype maps prevent Object.prototype collisions on 'constructor'/'toString')
    const coCounts = Object.create(null);
    const coCentroids = Object.create(null);
    for (let i = 0; i < poolForLegend.length; i++) {
      const d = poolForLegend[i];
      const co = (d._company || 'อื่นๆ').trim();
      coCounts[co] = (coCounts[co] || 0) + 1;
      if (String(d._centroid) === '1' || d._centroid === true) {
        coCentroids[co] = (coCentroids[co] || 0) + 1;
      }
    }

    const sortedCompanies = Object.keys(coCounts).sort((a, b) => {
      const cntA = coCounts[a] || 0;
      const cntB = coCounts[b] || 0;
      if (cntB !== cntA) return cntB - cntA;
      let idxA = typeof SIDEBAR_COMPANY_PRIORITY !== 'undefined' ? SIDEBAR_COMPANY_PRIORITY.indexOf(a) : -1;
      let idxB = typeof SIDEBAR_COMPANY_PRIORITY !== 'undefined' ? SIDEBAR_COMPANY_PRIORITY.indexOf(b) : -1;
      if (idxA === -1) idxA = 999;
      if (idxB === -1) idxB = 999;
      return idxA - idxB;
    });

    const _hasOwn = Object.prototype.hasOwnProperty;
    let html = '';
    for (const co of sortedCompanies) {
      const cnt = coCounts[co];
      const cCentroid = coCentroids[co] || 0;
      const logoUri = getCompanyLogoUri(co);
      const dotColor = (companyColors && _hasOwn.call(companyColors, co) && companyColors[co]) || '#94a3b8';
      const isFiltered = inMapFilterState && inMapFilterState.companies && inMapFilterState.companies.has(co);
      const activeCls = isFiltered ? ' active-filtered' : '';

      const safeCo = escapeHtml(co);
      let visualHtml = '';
      if (logoUri && typeof logoUri === 'string' && logoUri.startsWith('data:image/')) {
        visualHtml = `<img src="${escapeHtml(logoUri)}" class="legend-logo-mini" alt="${safeCo}" onerror="this.style.display='none';">`;
      } else {
        visualHtml = `<span class="legend-color-dot" style="background:${escapeHtml(dotColor)};"></span>`;
      }

      let centroidTag = '';
      if (cCentroid > 0) {
        centroidTag = `<span class="legend-centroid-badge" title="มีพิกัดกึ่งกลาง/โดยประมาณ ${cCentroid.toLocaleString()} จุด">&#9651; ${cCentroid.toLocaleString()}</span>`;
      }

      html += `
        <div class="legend-item${activeCls}" data-legend-kind="company" data-legend-val="${safeCo}" onclick="toggleFilterFromLegend(this.dataset.legendKind, this.dataset.legendVal)" title="คลิกเพื่อกรองเฉพาะบริษัท ${safeCo} (${cnt.toLocaleString()} ทรัพย์)">
          <div class="legend-item-left">
            ${visualHtml}
            <span class="legend-item-name">${safeCo}</span>
          </div>
          <div class="legend-item-right">
            <span class="legend-count-pill">${cnt.toLocaleString()}</span>
            ${centroidTag}
          </div>
        </div>
      `;
    }
    box.innerHTML = html;
  } else {
    // Group by Property Type
    const typeCounts = Object.create(null);
    for (let i = 0; i < poolForLegend.length; i++) {
      const d = poolForLegend[i];
      const t = (d._type || 'อื่นๆ').trim();
      typeCounts[t] = (typeCounts[t] || 0) + 1;
    }

    const sortedTypes = Object.keys(typeCounts).sort((a, b) => {
      return (typeCounts[b] || 0) - (typeCounts[a] || 0);
    });

    const _hasOwn = Object.prototype.hasOwnProperty;
    let html = '';
    for (const t of sortedTypes) {
      const cnt = typeCounts[t];
      const rgb = (typeof PROP_TYPE_COLORS !== 'undefined' && _hasOwn.call(PROP_TYPE_COLORS, t) && PROP_TYPE_COLORS[t]) || [148, 163, 184];
      const colorRgbStr = `rgb(${rgb[0]},${rgb[1]},${rgb[2]})`;
      const iconHtml = (typeof propTypeIcons !== 'undefined' && _hasOwn.call(propTypeIcons, t) && propTypeIcons[t]) || '<i class="fa-solid fa-house"></i>';
      const isFiltered = inMapFilterState && inMapFilterState.types && inMapFilterState.types.has(t);
      const activeCls = isFiltered ? ' active-filtered' : '';
      const safeT = escapeHtml(t);

      html += `
        <div class="legend-item${activeCls}" data-legend-kind="type" data-legend-val="${safeT}" onclick="toggleFilterFromLegend(this.dataset.legendKind, this.dataset.legendVal)" title="คลิกเพื่อกรองเฉพาะประเภท ${safeT} (${cnt.toLocaleString()} ทรัพย์)">
          <div class="legend-item-left">
            <span class="legend-icon-badge" style="background:rgba(${rgb[0]},${rgb[1]},${rgb[2]},0.15); color:${colorRgbStr};">${iconHtml}</span>
            <span class="legend-item-name">${safeT}</span>
          </div>
          <div class="legend-item-right">
            <span class="legend-count-pill">${cnt.toLocaleString()}</span>
          </div>
        </div>
      `;
    }
    box.innerHTML = html;
  }
}

// Milestone reference points: 50m (0.05 km), 0.5 km, 2 km, 5 km, 10 km, 20 km
const RADIUS_MILESTONES = [0.05, 0.5, 2, 5, 10, 20];

function formatRadiusDisplay(r) {
  if (r < 0.1) {
    const m = Math.round(r * 1000);
    return `${m} ม. (${r.toFixed(2)} กม.)`;
  } else if (r < 1.0) {
    const m = Math.round(r * 1000);
    return `${r.toFixed(1)} กม. (${m} ม.)`;
  } else if (r % 1 === 0) {
    return `${r.toFixed(0)} กม.`;
  } else {
    return `${r.toFixed(1)} กม.`;
  }
}

function posToRadius(p) {
  p = Math.max(0, Math.min(100, Number(p)));
  let r = 5.0;
  if (p <= 20) {
    // 0 to 20 maps to 0.05 to 0.5 (step 0.05: 50m, 100m, 150m, ... 500m)
    const ratio = p / 20;
    r = 0.05 + ratio * (0.5 - 0.05);
    r = Math.round(r * 20) / 20;
  } else if (p <= 40) {
    // 20 to 40 maps to 0.5 to 2.0 (step 0.1: 0.6, 0.7, 0.8 ... 1.2 ... 2.0)
    const ratio = (p - 20) / 20;
    r = 0.5 + ratio * (2.0 - 0.5);
    r = Math.round(r * 10) / 10;
  } else if (p <= 60) {
    // 40 to 60 maps to 2.0 to 5.0 (step 0.1: 2.1 ... 3.5 ... 5.0)
    const ratio = (p - 40) / 20;
    r = 2.0 + ratio * (5.0 - 2.0);
    r = Math.round(r * 10) / 10;
  } else if (p <= 80) {
    // 60 to 80 maps to 5.0 to 10.0 (step 0.5: 5.5, 6.0 ... 7.0 ... 10.0)
    const ratio = (p - 60) / 20;
    r = 5.0 + ratio * (10.0 - 5.0);
    r = Math.round(r * 2) / 2;
  } else {
    // 80 to 100 maps to 10.0 to 20.0 (step 0.5: 10.5, 11.0 ... 20.0)
    const ratio = (p - 80) / 20;
    r = 10.0 + ratio * (20.0 - 10.0);
    r = Math.round(r * 2) / 2;
  }
  return Number(r.toFixed(2));
}

function radiusToPos(r) {
  r = Math.max(0.05, Math.min(20, Number(r)));
  if (r <= 0.5) {
    return ((r - 0.05) / (0.5 - 0.05)) * 20;
  } else if (r <= 2.0) {
    return 20 + ((r - 0.5) / (2.0 - 0.5)) * 20;
  } else if (r <= 5.0) {
    return 40 + ((r - 2.0) / (5.0 - 2.0)) * 20;
  } else if (r <= 10.0) {
    return 60 + ((r - 5.0) / (10.0 - 5.0)) * 20;
  } else {
    return 80 + ((r - 10.0) / (20.0 - 10.0)) * 20;
  }
}

function updateRadiusSliderUi(radiusKm) {
  const val = Math.max(0.05, Math.min(20, Number(radiusKm) || 5));
  const pos = radiusToPos(val);

  const slider = document.getElementById('radius-range-slider');
  if (slider && Math.abs(parseFloat(slider.value) - pos) > 0.4) {
    slider.value = pos.toFixed(1);
  }

  const labelEl = document.getElementById('radius-slider-val');
  if (labelEl) labelEl.innerText = formatRadiusDisplay(val);

  // Highlight nearest tick mark
  let closestMilestone = RADIUS_MILESTONES[0];
  let minDiff = Math.abs(val - closestMilestone);
  for (let i = 1; i < RADIUS_MILESTONES.length; i++) {
    const diff = Math.abs(val - RADIUS_MILESTONES[i]);
    if (diff < minDiff) {
      minDiff = diff;
      closestMilestone = RADIUS_MILESTONES[i];
    }
  }

  document.querySelectorAll('.radius-track-tick').forEach(el => {
    const tickVal = parseFloat(el.getAttribute('data-val'));
    el.classList.toggle('active', Math.abs(tickVal - closestMilestone) < 0.01);
  });
  document.querySelectorAll('.radius-tick-num').forEach(el => {
    const tickVal = parseFloat(el.getAttribute('data-val'));
    el.classList.toggle('active', Math.abs(tickVal - closestMilestone) < 0.01);
  });
}

let radiusInputDebounceTimer = null;
function onContinuousRadiusInput(posVal) {
  const r = posToRadius(parseFloat(posVal));
  currentRadiusKm = Math.max(0.05, Math.min(20, Number(r) || 5));
  updateRadiusSliderUi(currentRadiusKm);
  try { updateSvgBoundaries(); } catch(e) {}
  if (radiusInputDebounceTimer) clearTimeout(radiusInputDebounceTimer);
  radiusInputDebounceTimer = setTimeout(() => {
    radiusInputDebounceTimer = null;
    setInspectionRadius(currentRadiusKm, null, false);
    scheduleParentKpiUpdate();
  }, 160);
}

function onContinuousRadiusCommit(posVal) {
  if (radiusInputDebounceTimer) {
    clearTimeout(radiusInputDebounceTimer);
    radiusInputDebounceTimer = null;
  }
  const r = posToRadius(parseFloat(posVal));
  setInspectionRadius(r, null, false);
  scheduleParentKpiUpdate();
}

function promptCustomRadius() {
  const current = currentRadiusKm < 1 ? currentRadiusKm.toFixed(2) : currentRadiusKm.toFixed(1);
  const input = prompt(`ระบุรัศมีที่ต้องการตรวจ (กม.) เช่น 0.05 (50 เมตร), 0.8, 1.2, 3.5, 7.0 (ต่ำสุด 0.05 ถึง 20 กม.):`, current);
  if (input !== null) {
    const val = parseFloat(input);
    if (!isNaN(val) && val >= 0.05 && val <= 20) {
      setInspectionRadius(val);
    } else if (!isNaN(val)) {
      showToast('<i class="fa-solid fa-circle-exclamation" style="color:#f59e0b; margin-right:4px;"></i>กรุณาระบุรัศมีระหว่าง 0.05 ถึง 20 กม.');
    }
  }
}

// Reference Point & Radius Inspection State
let currentRadiusKm = 5;
let referencePoint = null; // [lon, lat] - set only upon clicking the map or from input!
let userCurrentLocation = null; // { lon, lat, accuracy } - GPS Blue Dot marker (persisted even when referencePoint moves)
let currentRefProp = null; // object of active reference property if selected
let pendingReferencePoint = null; // [lon, lat] - click confirmation preview
let mousePreviewCoord = null; // [lon, lat] - preview circle follows mouse before clicking
let currentNearbyData = [];
let currentScopePool = [];
let spatialGrid = null;
const GRID_CELL_SIZE = (window.NovaMapCache && window.NovaMapCache.GRID_CELL_SIZE) || 0.2; // ~22 km grid buckets for instantaneous spatial lookup
// buildSpatialGrid is loaded from /app/static/map_cache_builder.js

function haversineDistanceKm(lat1, lon1, lat2, lon2) {
  const R = 6371.0;
  const toRad = 0.017453292519943295;
  const dLat = (lat2 - lat1) * toRad;
  const dLon = (lon2 - lon1) * toRad;
  const sinDLat = Math.sin(dLat / 2);
  const sinDLon = Math.sin(dLon / 2);
  const a = sinDLat * sinDLat + Math.cos(lat1 * toRad) * Math.cos(lat2 * toRad) * sinDLon * sinDLon;
  return 2.0 * R * Math.asin(Math.sqrt(Math.min(1.0, Math.max(0.0, a))));
}

function queryPointsInRadius(centerLon, centerLat, radiusKm) {
  if (!spatialGrid) return [];
  const toRad = 0.017453292519943295;
  const dLat = (radiusKm / 111.195) + 0.002;
  const cosLat = Math.cos(centerLat * toRad);
  const dLon = (radiusKm / (111.320 * (cosLat > 0.01 ? cosLat : 1.0))) + 0.002;
  const minLat = centerLat - dLat, maxLat = centerLat + dLat;
  const minLon = centerLon - dLon, maxLon = centerLon + dLon;

  const minGx = Math.floor(minLon / GRID_CELL_SIZE);
  const maxGx = Math.floor(maxLon / GRID_CELL_SIZE);
  const minGy = Math.floor(minLat / GRID_CELL_SIZE);
  const maxGy = Math.floor(maxLat / GRID_CELL_SIZE);

  const results = [];
  for (let gx = minGx; gx <= maxGx; gx++) {
    for (let gy = minGy; gy <= maxGy; gy++) {
      const cell = spatialGrid.get(gx + '_' + gy);
      if (!cell) continue;
      for (let i = 0; i < cell.length; i++) {
        const d = cell[i];
        if (d.lat >= minLat && d.lat <= maxLat && d.lon >= minLon && d.lon <= maxLon) {
          if (haversineDistanceKm(centerLat, centerLon, d.lat, d.lon) <= radiusKm) {
            results.push(d);
          }
        }
      }
    }
  }
  return results;
}

// 1. Locked Radius Circle around referencePoint
function createReferenceRadiusLayer() {
  if (!referencePoint || mapPinMode !== 'radius') return null;
  return new deck.ScatterplotLayer({
    id: 'reference-radius-circle',
    data: [{ lon: referencePoint[0], lat: referencePoint[1] }],
    getPosition: d => [d.lon, d.lat],
    getRadius: currentRadiusKm * 1000,
    radiusUnits: 'meters',
    stroked: true,
    filled: false,
    getFillColor: [0, 0, 0, 0],
    getLineColor: [5, 150, 105, 235],
    getLineWidth: 2.5,
    lineWidthUnits: 'pixels',
    lineWidthMinPixels: 2,
    pickable: false
  });
}

// --- Comparison State & Map Highlights ---
function createComparisonPinsHaloLayer() {
  if (!selectedComparisonProps || selectedComparisonProps.size === 0) return null;
  const data = Array.from(selectedComparisonProps.values()).filter(d => d && d.lat && d.lon && !isNaN(d.lat) && !isNaN(d.lon));
  if (data.length === 0) return null;
  return new deck.ScatterplotLayer({
    id: 'comparison-pins-halo',
    data: data,
    getPosition: d => [parseFloat(d.lon), parseFloat(d.lat)],
    getRadius: 28,
    radiusUnits: 'pixels',
    stroked: true,
    filled: true,
    getFillColor: [245, 158, 11, 45],       // Soft glowing golden amber fill
    getLineColor: [245, 158, 11, 245],      // High-contrast gold ring
    getLineWidth: 3.5,
    lineWidthUnits: 'pixels',
    pickable: false
  });
}

function createComparisonPinsBadgeLayer() {
  if (!selectedComparisonProps || selectedComparisonProps.size === 0) return null;
  const data = Array.from(selectedComparisonProps.values())
    .filter(d => d && d.lat && d.lon && !isNaN(d.lat) && !isNaN(d.lon))
    .map((d, idx) => ({
      ...d,
      orderText: `${idx + 1}`
    }));
  if (data.length === 0) return null;
  return new deck.TextLayer({
    id: 'comparison-pins-order',
    data: data,
    getPosition: d => [parseFloat(d.lon), parseFloat(d.lat)],
    getText: d => d.orderText,
    getSize: 12,
    getColor: [255, 255, 255, 255],
    backgroundColor: [217, 119, 6, 245],    // Amber badge
    backgroundPadding: [4, 3, 4, 3],
    getPixelOffset: [16, -16],
    fontFamily: "'Inter', sans-serif",
    fontWeight: 800,
    billboard: true,
    pickable: false,
    characterSet: 'auto'
  });
}

function toggleCardPropertyComparison() {
  if (!activePropertyData || !activePropertyData._id) return;
  const id = String(activePropertyData._id).trim();
  if (!id || id === '-') return;

  if (selectedComparisonProps.has(id)) {
    selectedComparisonProps.delete(id);
    showToast(`<i class="fa-solid fa-xmark" style="color:#ef4444; margin-right:6px;"></i>ยกเลิกการเลือกทรัพย์ <b>${escapeHtml(id)}</b>`);
  } else {
    selectedComparisonProps.set(id, {
      id: id,
      _id: id,
      lat: parseFloat(activePropertyData.lat),
      lon: parseFloat(activePropertyData.lon),
      title: activePropertyData._title || (activePropertyData._project && activePropertyData._project !== '-' ? activePropertyData._project : activePropertyData._type) || '',
      price: activePropertyData._price_str || '',
      company: activePropertyData._company || '',
      type: activePropertyData._type || '',
      sqw: activePropertyData._sqw || 0,
      sqm: activePropertyData._sqm || 0
    });
    showToast(`<i class="fa-solid fa-scale-balanced" style="color:#f59e0b; margin-right:6px;"></i>เพิ่มทรัพย์ <b>${escapeHtml(id)}</b> ในรายการเปรียบเทียบ (รวม ${selectedComparisonProps.size} ทรัพย์)`);
  }

  updateComparisonUi();
  updateDeckLayers();
  syncComparisonToStreamlit();
}

function updateComparisonUi() {
  const btnToggleComp = document.getElementById('btn-toggle-compare-card');
  if (btnToggleComp && activePropertyData && activePropertyData._id) {
    const propId = String(activePropertyData._id).trim();
    const isSelected = selectedComparisonProps && selectedComparisonProps.has(propId);
    if (isSelected) {
      btnToggleComp.classList.add('selected');
      btnToggleComp.innerHTML = '<i class="fa-solid fa-square-check"></i> เลือกอยู่ (ยกเลิก)';
    } else {
      btnToggleComp.classList.remove('selected');
      btnToggleComp.innerHTML = '<i class="fa-regular fa-square-check"></i> ติ๊กเลือกเปรียบเทียบ';
    }
  }

  const bar = document.getElementById('floating-compare-bar');
  const countEl = document.getElementById('floating-compare-count');
  const chipsEl = document.getElementById('floating-compare-chips');
  const filterPanel = document.getElementById('map-filter-panel');
  const specFilterPanel = document.getElementById('map-spec-filter-panel');
  if (bar && countEl) {
    const count = selectedComparisonProps ? selectedComparisonProps.size : 0;
    if (count > 0) {
      bar.style.display = 'flex';
      if (filterPanel) filterPanel.classList.add('with-compare-bar');
      if (specFilterPanel) specFilterPanel.classList.add('with-compare-bar');
      countEl.innerText = `เลือกเปรียบเทียบ ${count} ทรัพย์`;
      if (chipsEl) {
        const ids = Array.from(selectedComparisonProps.keys());
        chipsEl.innerHTML = ids.slice(0, 4).map((cid, i) =>
          `<span style="background:rgba(245,158,11,0.22); color:#fbbf24; border:1px solid rgba(245,158,11,0.45); font-size:10.5px; font-weight:700; padding:1px 6px; border-radius:9999px;">${i+1}. ${escapeHtml(cid)}</span>`
        ).join('') + (ids.length > 4 ? `<span style="font-size:10px; color:#94a3b8; font-weight:700;">+${ids.length - 4}</span>` : '');
      }
    } else {
      bar.style.display = 'none';
      if (filterPanel) filterPanel.classList.remove('with-compare-bar');
      if (specFilterPanel) specFilterPanel.classList.remove('with-compare-bar');
    }
  }
}

function clearAllComparison() {
  if (!selectedComparisonProps || selectedComparisonProps.size === 0) return;
  selectedComparisonProps.clear();
  updateComparisonUi();
  updateDeckLayers();
  syncComparisonToStreamlit();
  showToast('<i class="fa-solid fa-rotate-left" style="color:#38bdf8; margin-right:6px;"></i>ล้างรายการเปรียบเทียบทั้งหมดแล้ว');
}

function scrollToComparisonTable() {
  try {
    if (window.parent) {
      const tableTitle = window.parent.document.getElementById('median-table-title') ||
                         window.parent.document.querySelector('[data-testid="stDataFrame"]') ||
                         window.parent.document.querySelector('.st-key-tab2_compare_banner');
      if (tableTitle) {
        tableTitle.scrollIntoView({ behavior: 'smooth', block: 'start' });
      } else {
        window.parent.scrollTo({ top: window.parent.innerHeight * 0.95, behavior: 'smooth' });
      }
    }
  } catch(e) {}
}

function syncComparisonToStreamlit() {
  const ids = selectedComparisonProps ? Array.from(selectedComparisonProps.keys()) : [];
  const idStr = ids.join(',');
  try {
    var u = new URL(window.parent.location.href);
    if (ids.length > 0) {
      u.searchParams.set('map_compare_ids', idStr);
    } else {
      u.searchParams.delete('map_compare_ids');
    }
    window.parent.history.replaceState({}, '', u.toString());
  } catch(e) {}

  triggerStreamlitSync({
    compare_ids: ids
  }, 120);
}

// 2. Reference Pin Marker Layers (Concentric Bullseye Pin)
function createReferencePinHaloLayer() {
  if (!referencePoint || mapPinMode !== 'radius') return null;
  return new deck.ScatterplotLayer({
    id: 'reference-pin-halo',
    data: [{ lon: referencePoint[0], lat: referencePoint[1] }],
    getPosition: d => [d.lon, d.lat],
    getRadius: 18,
    radiusUnits: 'pixels',
    stroked: true,
    filled: true,
    getFillColor: [239, 68, 68, 38],
    getLineColor: [239, 68, 68, 210],
    getLineWidth: 2,
    lineWidthUnits: 'pixels',
    pickable: false
  });
}

function createReferencePinDotLayer() {
  if (!referencePoint || mapPinMode !== 'radius') return null;
  return new deck.ScatterplotLayer({
    id: 'reference-pin-dot',
    data: [{ lon: referencePoint[0], lat: referencePoint[1] }],
    getPosition: d => [d.lon, d.lat],
    getRadius: 8,
    radiusUnits: 'pixels',
    stroked: true,
    filled: true,
    getFillColor: [239, 68, 68, 255],
    getLineColor: [255, 255, 255, 255],
    getLineWidth: 2.5,
    lineWidthUnits: 'pixels',
    pickable: false
  });
}

function createReferencePinCoreLayer() {
  if (!referencePoint || mapPinMode !== 'radius') return null;
  return new deck.ScatterplotLayer({
    id: 'reference-pin-core',
    data: [{ lon: referencePoint[0], lat: referencePoint[1] }],
    getPosition: d => [d.lon, d.lat],
    getRadius: 3,
    radiusUnits: 'pixels',
    stroked: false,
    filled: true,
    getFillColor: [255, 255, 255, 255],
    pickable: false
  });
}

// Pending Reference Point Pin (Preview before confirming)
function createPendingReferencePinLayer() {
  if (!pendingReferencePoint) return null;
  return new deck.ScatterplotLayer({
    id: 'pending-reference-pin',
    data: [{ lon: pendingReferencePoint[0], lat: pendingReferencePoint[1] }],
    getPosition: d => [d.lon, d.lat],
    getRadius: 18,
    radiusUnits: 'pixels',
    stroked: true,
    filled: true,
    getFillColor: [245, 158, 11, 230], // Amber
    getLineColor: [255, 255, 255, 255],
    getLineWidth: 3,
    lineWidthUnits: 'pixels',
    pickable: false
  });
}

// User Current GPS Location Layers (Blue Dot + Accuracy Circle)
function createUserLocationAccuracyLayer() {
  if (!userCurrentLocation || !Number.isFinite(userCurrentLocation.accuracy) || userCurrentLocation.accuracy <= 0) return null;
  const clampedMeters = Math.min(Math.max(userCurrentLocation.accuracy, 10), 5000);
  return new deck.ScatterplotLayer({
    id: 'user-location-accuracy',
    data: [{ lon: userCurrentLocation.lon, lat: userCurrentLocation.lat, radius: clampedMeters }],
    getPosition: d => [d.lon, d.lat],
    getRadius: d => d.radius,
    radiusUnits: 'meters',
    stroked: true,
    filled: true,
    getFillColor: [37, 99, 235, 28],
    getLineColor: [59, 130, 246, 130],
    getLineWidth: 1.5,
    lineWidthUnits: 'pixels',
    lineWidthMinPixels: 1,
    pickable: false
  });
}

function createUserLocationHaloLayer() {
  if (!userCurrentLocation) return null;
  return new deck.ScatterplotLayer({
    id: 'user-location-halo',
    data: [{ lon: userCurrentLocation.lon, lat: userCurrentLocation.lat }],
    getPosition: d => [d.lon, d.lat],
    getRadius: 15,
    radiusUnits: 'pixels',
    stroked: true,
    filled: true,
    getFillColor: [59, 130, 246, 55],
    getLineColor: [59, 130, 246, 175],
    getLineWidth: 1.5,
    lineWidthUnits: 'pixels',
    pickable: false
  });
}

function createUserLocationDotLayer() {
  if (!userCurrentLocation) return null;
  return new deck.ScatterplotLayer({
    id: 'user-location-dot',
    data: [{ lon: userCurrentLocation.lon, lat: userCurrentLocation.lat }],
    getPosition: d => [d.lon, d.lat],
    getRadius: 7,
    radiusUnits: 'pixels',
    stroked: true,
    filled: true,
    getFillColor: [37, 99, 235, 255],
    getLineColor: [255, 255, 255, 255],
    getLineWidth: 2.5,
    lineWidthUnits: 'pixels',
    pickable: false
  });
}

// 3. Hover Preview Cursor (Before clicking: NO points, just faint preview circle & dot)
function createPreviewCursorLayer() {
  if (referencePoint || !mousePreviewCoord) return null;
  return new deck.ScatterplotLayer({
    id: 'preview-cursor-circle',
    data: [{ lon: mousePreviewCoord[0], lat: mousePreviewCoord[1] }],
    getPosition: d => [d.lon, d.lat],
    getRadius: currentRadiusKm * 1000,
    radiusUnits: 'meters',
    stroked: true,
    filled: true,
    getFillColor: [16, 185, 129, 14],
    getLineColor: [16, 185, 129, 160],
    getLineWidth: 1.5,
    lineWidthUnits: 'pixels',
    lineWidthMinPixels: 1.5,
    pickable: false
  });
}

function createPreviewDotLayer() {
  if (referencePoint || !mousePreviewCoord) return null;
  return new deck.ScatterplotLayer({
    id: 'preview-cursor-dot',
    data: [{ lon: mousePreviewCoord[0], lat: mousePreviewCoord[1] }],
    getPosition: d => [d.lon, d.lat],
    getRadius: 5,
    radiusUnits: 'pixels',
    stroked: true,
    filled: true,
    getFillColor: [16, 185, 129, 220],
    getLineColor: [255, 255, 255, 255],
    getLineWidth: 1.5,
    lineWidthUnits: 'pixels',
    pickable: false
  });
}

function isProvinceOnlyLocationState() {
  if (mapPinMode !== 'location') return false;
  const hasProjFilter = Boolean(inMapFilterState && (
    (inMapFilterState.samProjects && inMapFilterState.samProjects.size > 0) ||
    (inMapFilterState.samProject && inMapFilterState.samProject !== '')
  ));
  if (hasProjFilter || referencePoint || currentRefProp) return false;
  const hasProvSelected = Boolean(currentSelectedProv && currentSelectedProv.trim() !== '' && currentSelectedProv !== '__ALL__');
  const hasDistSelected = Boolean(currentSelectedDist && currentSelectedDist.trim() !== '' && currentSelectedDist !== '__ALL__');
  const hasSubdistSelected = Boolean(currentSelectedSubdist && currentSelectedSubdist.trim() !== '' && currentSelectedSubdist !== '__ALL__');
  return hasProvSelected && !hasDistSelected && !hasSubdistSelected;
}

function hasActiveParentAnalyticsFragment() {
  try {
    return Boolean(window.parent && window.parent.document && window.parent.document.getElementById('median-card-1'));
  } catch (_e) {
    return false;
  }
}

function shouldRenderMapPins() {
  if (!currentNearbyData || currentNearbyData.length === 0) return false;
  const hasProjFilter = Boolean(inMapFilterState && (
    (inMapFilterState.samProjects && inMapFilterState.samProjects.size > 0) ||
    (inMapFilterState.samProject && inMapFilterState.samProject !== '')
  ));
  if (hasProjFilter) return true;
  if (mapPinMode === 'radius') return Boolean(referencePoint);

  const hasProvSelected = Boolean(currentSelectedProv && currentSelectedProv.trim() !== '' && currentSelectedProv !== '__ALL__');
  if (hasProvSelected) {
    // Render pins immediately when a province (or district/subdistrict) is selected
    return true;
  }

  const hasOnlyProjFilter = Boolean(inMapFilterState && inMapFilterState.onlyWithProject);
  const hasCompaniesFilter = Boolean(inMapFilterState && inMapFilterState.companies && inMapFilterState.companies.size > 0);
  return hasOnlyProjFilter || (hasCompaniesFilter && inMapFilterState.companies.size <= 2);
}

let _lastStaticDeckLayers = [];

function updatePreviewCursorOnly() {
  if (!deckglInstance || mapPinMode !== 'radius' || referencePoint || !mousePreviewCoord) return;
  const layers = _lastStaticDeckLayers ? _lastStaticDeckLayers.slice() : [];
  const prevCircle = createPreviewCursorLayer();
  if (prevCircle) layers.push(prevCircle);
  const prevDot = createPreviewDotLayer();
  if (prevDot) layers.push(prevDot);
  deckglInstance.setProps({ layers });
}

function updateDeckLayers() {
  if (!deckglInstance) return;
  const basemapLayer = createBasemapLayer(currentStyle);
  const layers = [basemapLayer];

  // Boundary Frame (GeoJsonLayer) for selected Province / District / Subdistrict
  const boundaryLayer = createBoundaryLayer();
  if (boundaryLayer) layers.push(boundaryLayer);

  // User GPS accuracy ring (underneath property pins & reference circle)
  const userAccLayer = createUserLocationAccuracyLayer();
  if (userAccLayer) layers.push(userAccLayer);

  if (referencePoint && mapPinMode === 'radius') {
    // When reference point is set: render locked radius circle + target bullseye pin + points
    const refCircle = createReferenceRadiusLayer();
    if (refCircle) layers.push(refCircle);

    const refHalo = createReferencePinHaloLayer();
    if (refHalo) layers.push(refHalo);

    const refDot = createReferencePinDotLayer();
    if (refDot) layers.push(refDot);

    const refCore = createReferencePinCoreLayer();
    if (refCore) layers.push(refCore);
  } else if (mapPinMode === 'location' && currentRefProp && currentRefProp.lat && currentRefProp.lon) {
    // In location mode with a selected property: render original halo on that pin
    const pLat = parseFloat(currentRefProp.lat);
    const pLon = parseFloat(currentRefProp.lon);
    const selHalo = new deck.ScatterplotLayer({
      id: 'selected-prop-location-halo',
      data: [{ lon: pLon, lat: pLat }],
      getPosition: d => [d.lon, d.lat],
      getRadius: 22,
      radiusUnits: 'pixels',
      stroked: true,
      filled: false,
      getFillColor: [0, 0, 0, 0],
      getLineColor: [5, 150, 105, 240],
      getLineWidth: 2.5,
      lineWidthUnits: 'pixels',
      pickable: false
    });
    layers.push(selHalo);
  } else if (mapPinMode === 'radius') {
    // When in radius mode and NOT clicked yet: show preview cursor following mouse
    const prevCircle = createPreviewCursorLayer();
    if (prevCircle) layers.push(prevCircle);

    const prevDot = createPreviewDotLayer();
    if (prevDot) layers.push(prevDot);
  }

  // Render Property Points (in location mode: when province/district/subdistrict is selected; in radius/project mode: matching pins)
  if (shouldRenderMapPins()) {
    const ptLayers = createPointLayers(currentNearbyData);
    if (ptLayers && ptLayers.length > 0) {
      layers.push(...ptLayers);
    }
  }

  // User GPS Blue Dot (persists even if referencePoint moves to another property)
  const userHalo = createUserLocationHaloLayer();
  if (userHalo) layers.push(userHalo);
  const userDot = createUserLocationDotLayer();
  if (userDot) layers.push(userDot);

  // If user has clicked to propose a new reference point, show pending marker
  const pendingPin = createPendingReferencePinLayer();
  if (pendingPin) layers.push(pendingPin);

  // Highlight selected comparison pins with glowing gold ring and order badge
  const compHalo = createComparisonPinsHaloLayer();
  if (compHalo) layers.push(compHalo);
  const compBadge = createComparisonPinsBadgeLayer();
  if (compBadge) layers.push(compBadge);

  _lastStaticDeckLayers = layers.filter(
    l => l && l.id !== 'preview-cursor-circle' && l.id !== 'preview-cursor-dot'
  );

  deckglInstance.setProps({ layers });
  updateSvgBoundaries();
  renderHtmlMarkers();
}

// In-Map Realtime Filters State & Management
let inMapFilterState = {
  companies: new Set(),
  types: new Set(),
  sales: new Set(),
  samProjects: new Set(),
  samProject: null,
  onlyWithProject: false,
  includeCentroids: false,
  minPrice: null,
  maxPrice: null,
  minSqw: null,
  maxSqw: null,
  minSqm: null,
  maxSqm: null,
  minPuw: null,
  maxPuw: null,
  minPum: null,
  maxPum: null,
  floors: new Set(),
  minFloor: null,
  maxFloor: null,
  bedrooms: new Set(),
  bathrooms: new Set(),
  parkings: new Set(),
  agePreset: null,
  maxAge: null
};

function updatePanelArrowPosition(panelId, btnId, defaultOffset) {
  const panel = document.getElementById(panelId);
  const btn = document.getElementById(btnId);
  if (!panel || !btn) return;
  try {
    const btnRect = btn.getBoundingClientRect();
    const panelRect = panel.getBoundingClientRect();
    if (panelRect.width > 0 && btnRect.width > 0) {
      const arrowLeft = Math.round((btnRect.left + btnRect.width / 2) - panelRect.left);
      const clampedLeft = Math.max(20, Math.min(panelRect.width - 20, arrowLeft));
      panel.style.setProperty('--arrow-left', `${clampedLeft}px`);
      return;
    }
  } catch (e) {}
  panel.style.setProperty('--arrow-left', `${defaultOffset}px`);
}

function _setFilterSubrowOpenState(panelEl, isOpen) {
  try {
    document.querySelectorAll('.map-filter-subrow.panel-open').forEach(r => r.classList.remove('panel-open'));
    if (isOpen && panelEl) {
      const subrow = panelEl.closest('.map-filter-subrow');
      if (subrow) subrow.classList.add('panel-open');
    }
  } catch(e) {}
}

function toggleFilterPanel() {
  const panel = document.getElementById('map-filter-panel');
  const specPanel = document.getElementById('map-spec-filter-panel');
  const btn = document.getElementById('map-filter-toggle-btn');
  const specBtn = document.getElementById('map-spec-filter-toggle-btn');
  if (specPanel) specPanel.style.display = 'none';
  if (specBtn) specBtn.classList.remove('open');
  closeAllComboboxes();
  if (!panel) return;
  const isOpen = (panel.style.display === 'block');
  if (isOpen) {
    panel.style.display = 'none';
    if (btn) btn.classList.remove('open');
    _setFilterSubrowOpenState(panel, false);
  } else {
    panel.style.display = 'block';
    if (btn) btn.classList.add('open');
    _setFilterSubrowOpenState(panel, true);
    updatePanelArrowPosition('map-filter-panel', 'map-filter-toggle-btn', 55);
  }
}

function toggleSpecFilterPanel() {
  const specPanel = document.getElementById('map-spec-filter-panel');
  const panel = document.getElementById('map-filter-panel');
  const btn = document.getElementById('map-filter-toggle-btn');
  const specBtn = document.getElementById('map-spec-filter-toggle-btn');
  if (panel) panel.style.display = 'none';
  if (btn) btn.classList.remove('open');
  closeAllComboboxes();
  if (!specPanel) return;
  const isOpen = (specPanel.style.display === 'block');
  if (isOpen) {
    specPanel.style.display = 'none';
    if (specBtn) specBtn.classList.remove('open');
    _setFilterSubrowOpenState(specPanel, false);
  } else {
    specPanel.style.display = 'block';
    if (specBtn) specBtn.classList.add('open');
    _setFilterSubrowOpenState(specPanel, true);
    updatePanelArrowPosition('map-spec-filter-panel', 'map-spec-filter-toggle-btn', 195);
  }
}

const SIDEBAR_COMPANY_PRIORITY = [
  "LED", "LED_SOLD", "SAM", "BAM", "Chayo555", "Chayo", "Chayo NPA", "GHB", "KBANK", "KTB", "SCB", "GSB", "DDproperty", "Livinginsider", "NaYoo", "ZmyHome", "Baania"
];

const INMAP_COMPANY_PRIORITY = [
  "LED", "LED Legal", "LED_SOLD", "SAM", "BAM", "Chayo555", "Chayo", "Chayo NPA", "GHB", "KBANK", "KTB", "SCB", "GSB", "DDproperty", "Livinginsider", "NaYoo", "ZmyHome", "Baania"
];

function initInMapFilterChips(lut, data, precomputedTypeCounts) {
  const compGrid = document.getElementById('filter-company-chips');
  if (compGrid && lut && lut.co) {
    const sortedCompanies = lut.co.filter(c => c && c !== '-').slice().sort((a, b) => {
      let idxA = INMAP_COMPANY_PRIORITY.indexOf(a);
      let idxB = INMAP_COMPANY_PRIORITY.indexOf(b);
      if (idxA === -1) idxA = 999;
      if (idxB === -1) idxB = 999;
      if (idxA !== idxB) return idxA - idxB;
      return a.localeCompare(b, 'th');
    });
    compGrid.innerHTML = sortedCompanies.map(c => {
      const isAct = inMapFilterState && inMapFilterState.companies && inMapFilterState.companies.has(c) ? ' active' : '';
      const safeC = escapeHtml(c);
      return `<span class="filter-chip${isAct}" data-group="company" data-val="${safeC}" onclick="toggleFilterChip(this.dataset.group, this.dataset.val, this)">${safeC}</span>`;
    }).join('');
  }

  const typeGrid = document.getElementById('filter-type-chips');
  if (typeGrid && lut && lut.ty) {
    let typeCounts = precomputedTypeCounts;
    if (!typeCounts) {
      const sourceData = (data && data.length > 0) ? data : (cachedData || []);
      typeCounts = (window.NovaMapCache && typeof window.NovaMapCache.computeTypeCounts === 'function')
        ? window.NovaMapCache.computeTypeCounts(sourceData)
        : {};
    }
    const sortedTypes = lut.ty.filter(t => t && t !== '-').slice().sort((a, b) => {
      const cntA = typeCounts[a] || 0;
      const cntB = typeCounts[b] || 0;
      if (cntB !== cntA) return cntB - cntA; // Most properties to least
      return a.localeCompare(b, 'th');
    });
    typeGrid.innerHTML = sortedTypes.map(t => {
      const isAct = inMapFilterState && inMapFilterState.types && inMapFilterState.types.has(t) ? ' active' : '';
      const safeT = escapeHtml(t);
      return `<span class="filter-chip${isAct}" data-group="type" data-val="${safeT}" onclick="toggleFilterChip(this.dataset.group, this.dataset.val, this)">${safeT}</span>`;
    }).join('');
  }

  const saleGrid = document.getElementById('filter-sale-chips');
  if (saleGrid && lut && lut.st) {
    saleGrid.innerHTML = lut.st.filter(s => s && s !== '-').map(s => {
      const isAct = inMapFilterState && inMapFilterState.sales && inMapFilterState.sales.has(s) ? ' active' : '';
      const safeS = escapeHtml(s);
      return `<span class="filter-chip${isAct}" data-group="sale" data-val="${safeS}" onclick="toggleFilterChip(this.dataset.group, this.dataset.val, this)">${safeS}</span>`;
    }).join('');
  }

  // Filter 9: Floor Chips
  const flGrid = document.getElementById('filter-floor-chips');
  if (flGrid) {
    const floorOptions = [
      { val: '1', label: '1 ชั้น' },
      { val: '2', label: '2 ชั้น' },
      { val: '3', label: '3 ชั้น' },
      { val: '4+', label: '4+ ชั้น' },
      { val: 'none', label: 'ไม่ระบุ' }
    ];
    flGrid.innerHTML = floorOptions.map(opt => {
      const isAct = inMapFilterState && inMapFilterState.floors && inMapFilterState.floors.has(opt.val) ? ' active' : '';
      return `<span class="filter-chip${isAct}" data-group="floor" data-val="${opt.val}" onclick="toggleFilterChip(this.dataset.group, this.dataset.val, this)">${opt.label}</span>`;
    }).join('');
  }

  // Filter 10: Bedroom Chips
  const bedGrid = document.getElementById('filter-bedroom-chips');
  if (bedGrid) {
    const bedOptions = [
      { val: '0', label: 'สตูดิโอ' },
      { val: '1', label: '1 นอน' },
      { val: '2', label: '2 นอน' },
      { val: '3', label: '3 นอน' },
      { val: '4', label: '4 นอน' },
      { val: '5+', label: '5+ นอน' },
      { val: 'none', label: 'ไม่ระบุ' }
    ];
    bedGrid.innerHTML = bedOptions.map(opt => {
      const isAct = inMapFilterState && inMapFilterState.bedrooms && inMapFilterState.bedrooms.has(opt.val) ? ' active' : '';
      return `<span class="filter-chip${isAct}" data-group="bedroom" data-val="${opt.val}" onclick="toggleFilterChip(this.dataset.group, this.dataset.val, this)">${opt.label}</span>`;
    }).join('');
  }

  // Filter 11: Bathroom Chips
  const bathGrid = document.getElementById('filter-bathroom-chips');
  if (bathGrid) {
    const bathOptions = [
      { val: '1', label: '1 น้ำ' },
      { val: '2', label: '2 น้ำ' },
      { val: '3', label: '3 น้ำ' },
      { val: '4', label: '4 น้ำ' },
      { val: '5+', label: '5+ น้ำ' },
      { val: 'none', label: 'ไม่ระบุ' }
    ];
    bathGrid.innerHTML = bathOptions.map(opt => {
      const isAct = inMapFilterState && inMapFilterState.bathrooms && inMapFilterState.bathrooms.has(opt.val) ? ' active' : '';
      return `<span class="filter-chip${isAct}" data-group="bathroom" data-val="${opt.val}" onclick="toggleFilterChip(this.dataset.group, this.dataset.val, this)">${opt.label}</span>`;
    }).join('');
  }

  // Filter 12: Parking Chips
  const pkgGrid = document.getElementById('filter-parking-chips');
  if (pkgGrid) {
    const pkgOptions = [
      { val: '1', label: '1 คัน' },
      { val: '2', label: '2 คัน' },
      { val: '3', label: '3 คัน' },
      { val: '4+', label: '4+ คัน' },
      { val: 'none', label: 'ไม่ระบุ' }
    ];
    pkgGrid.innerHTML = pkgOptions.map(opt => {
      const isAct = inMapFilterState && inMapFilterState.parkings && inMapFilterState.parkings.has(opt.val) ? ' active' : '';
      return `<span class="filter-chip${isAct}" data-group="parking" data-val="${opt.val}" onclick="toggleFilterChip(this.dataset.group, this.dataset.val, this)">${opt.label}</span>`;
    }).join('');
  }

  // Filter 13: Listing Age Chips
  const ageGrid = document.getElementById('filter-age-chips');
  if (ageGrid) {
    const ageOptions = [
      { val: '30', label: '<= 30 วัน' },
      { val: '60', label: '<= 60 วัน' },
      { val: '90', label: '<= 90 วัน' },
      { val: '180', label: '<= 180 วัน' },
      { val: '365', label: '<= 1 ปี' }
    ];
    ageGrid.innerHTML = ageOptions.map(opt => {
      const isAct = inMapFilterState && inMapFilterState.agePreset === opt.val ? ' active' : '';
      return `<span class="filter-chip${isAct}" data-group="age" data-val="${opt.val}" onclick="toggleFilterChip(this.dataset.group, this.dataset.val, this)">${opt.label}</span>`;
    }).join('');
  }

  if (!allProjectsList || allProjectsList.length === 0) {
    if (lut || cachedData) buildSamProjectOptions(cachedData, lut);
  }
  syncComboboxInputs();
  updateHasProjectButtonUI();
}

function toggleIncludeCentroidsFilter() {
  inMapFilterState.includeCentroids = !inMapFilterState.includeCentroids;
  updateIncludeCentroidsButtonUI();
  applyInMapFilters();
  notifyParentFilterChange();
}

function updateIncludeCentroidsButtonUI() {
  const chip = document.getElementById('filter-chip-include-centroids');
  const isAct = !!(inMapFilterState && inMapFilterState.includeCentroids);
  if (chip) {
    chip.classList.toggle('active', isAct);
  }
}

function toggleOnlyWithProjectFilter() {
  inMapFilterState.onlyWithProject = !inMapFilterState.onlyWithProject;
  updateHasProjectButtonUI();
  cachedScopedProjectsKey = '';
  syncComboboxInputs();
  applyInMapFilters();
  notifyParentFilterChange();
}

function updateHasProjectButtonUI() {
  const chip = document.getElementById('filter-chip-has-proj');
  const chipTxt = document.getElementById('filter-chip-has-proj-txt');

  const isAct = inMapFilterState && inMapFilterState.onlyWithProject;
  const cos = (inMapFilterState && inMapFilterState.companies) || new Set();

  let label = 'มีโครงการ';
  if (isAct && cos.size >= 2) {
    label = `มีโครงการเดียวกัน (${Array.from(cos).join('+')})`;
  } else if (isAct && cos.size === 1) {
    label = `มีโครงการ (${Array.from(cos)[0]})`;
  }

  if (chip) {
    if (isAct) {
      chip.classList.add('active');
    } else {
      chip.classList.remove('active');
    }
  }
  if (chipTxt) chipTxt.innerText = label;
}

function toggleFilterChip(group, val, el) {
  let targetSet = null;
  if (group === 'company') targetSet = inMapFilterState.companies;
  else if (group === 'type') targetSet = inMapFilterState.types;
  else if (group === 'sale') targetSet = inMapFilterState.sales;
  else if (group === 'floor') targetSet = inMapFilterState.floors;
  else if (group === 'bedroom') targetSet = inMapFilterState.bedrooms;
  else if (group === 'bathroom') targetSet = inMapFilterState.bathrooms;
  else if (group === 'parking') targetSet = inMapFilterState.parkings;
  else if (group === 'age') {
    if (inMapFilterState.agePreset === val) {
      inMapFilterState.agePreset = null;
      if (el) el.classList.remove('active');
    } else {
      inMapFilterState.agePreset = val;
      const parent = el ? el.parentElement : document.getElementById('filter-age-chips');
      if (parent) parent.querySelectorAll('.filter-chip').forEach(c => c.classList.remove('active'));
      if (el) el.classList.add('active');
    }
    applyInMapFilters();
    notifyParentFilterChange();
    return;
  }
  if (!targetSet) return;

  if (targetSet.has(val)) {
    targetSet.delete(val);
    if (el) el.classList.remove('active');
  } else {
    targetSet.add(val);
    if (el) el.classList.add('active');
  }
  if (group === 'company') {
    updateHasProjectButtonUI();
  }
  cachedScopedProjectsKey = '';
  syncComboboxInputs();
  applyInMapFilters();
}

function resetGeneralFilters() {
  inMapFilterState.companies.clear();
  inMapFilterState.types.clear();
  inMapFilterState.sales.clear();
  inMapFilterState.onlyWithProject = false;
  inMapFilterState.includeCentroids = false;
  inMapFilterState.agePreset = null;
  inMapFilterState.maxAge = null;

  const genPanel = document.getElementById('map-filter-panel');
  if (genPanel) {
    genPanel.querySelectorAll('.filter-chip').forEach(c => c.classList.remove('active'));
  }
  const ageInp = document.getElementById('filter-max-age');
  if (ageInp) ageInp.value = '';

  updateHasProjectButtonUI();
  updateIncludeCentroidsButtonUI();
  cachedScopedProjectsKey = '';
  syncComboboxInputs();
  applyInMapFilters();
  notifyParentFilterChange();
}

function resetSpecFilters() {
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
  if (inMapFilterState.floors) inMapFilterState.floors.clear();
  inMapFilterState.minFloor = null;
  inMapFilterState.maxFloor = null;
  if (inMapFilterState.bedrooms) inMapFilterState.bedrooms.clear();
  if (inMapFilterState.bathrooms) inMapFilterState.bathrooms.clear();
  if (inMapFilterState.parkings) inMapFilterState.parkings.clear();

  const specPanel = document.getElementById('map-spec-filter-panel');
  if (specPanel) {
    specPanel.querySelectorAll('.filter-chip').forEach(c => c.classList.remove('active'));
  }
  ['filter-min-price', 'filter-max-price', 'filter-min-sqw', 'filter-max-sqw', 'filter-min-sqm', 'filter-max-sqm', 'filter-min-puw', 'filter-max-puw', 'filter-min-pum', 'filter-max-pum', 'filter-min-floor', 'filter-max-floor'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = '';
  });

  applyInMapFilters();
  notifyParentFilterChange();
}

function resetAllInMapFilters() {
  inMapFilterState.companies.clear();
  inMapFilterState.types.clear();
  inMapFilterState.sales.clear();
  if (inMapFilterState.samProjects) inMapFilterState.samProjects.clear();
  inMapFilterState.samProject = null;
  inMapFilterState.samProjectsNorm = new Set();
  inMapFilterState.onlyWithProject = false;
  inMapFilterState.includeCentroids = false;
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
  if (inMapFilterState.floors) inMapFilterState.floors.clear();
  inMapFilterState.minFloor = null;
  inMapFilterState.maxFloor = null;
  if (inMapFilterState.bedrooms) inMapFilterState.bedrooms.clear();
  if (inMapFilterState.bathrooms) inMapFilterState.bathrooms.clear();
  if (inMapFilterState.parkings) inMapFilterState.parkings.clear();
  inMapFilterState.agePreset = null;
  inMapFilterState.maxAge = null;

  cachedScopedProjectsKey = '';
  document.querySelectorAll('.filter-chip').forEach(c => c.classList.remove('active'));
  updateHasProjectButtonUI();
  updateIncludeCentroidsButtonUI();
  syncComboboxInputs();

  ['filter-min-price', 'filter-max-price', 'filter-min-sqw', 'filter-max-sqw', 'filter-min-sqm', 'filter-max-sqm', 'filter-min-puw', 'filter-max-puw', 'filter-min-pum', 'filter-max-pum', 'filter-min-floor', 'filter-max-floor', 'filter-max-age'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = '';
  });

  applyInMapFilters();
  notifyParentFilterChange();
}

function resetInMapFilters() {
  resetAllInMapFilters();
}

function isItemInCurrentLocation(d) {
  if (!d) return false;
  if (currentSelectedProv && currentSelectedProv !== '' && currentSelectedProv !== '__ALL__') {
    if (d._prov !== currentSelectedProv) return false;
  }
  if (currentSelectedDist && currentSelectedDist !== '' && currentSelectedDist !== '__ALL__') {
    const cleanD = currentSelectedDist.split(' (')[0].trim();
    if (d._district !== currentSelectedDist && d._district !== cleanD) return false;
  }
  if (currentSelectedSubdist && currentSelectedSubdist !== '' && currentSelectedSubdist !== '__ALL__') {
    const cleanS = currentSelectedSubdist.split(' (')[0].trim();
    if (d._subdistrict !== currentSelectedSubdist && d._subdistrict !== cleanS) return false;
  }
  return true;
}

function filterItemPasses(d, excludeAxis) {
  if (mapPinMode === 'location') {
    if (!isItemInCurrentLocation(d)) return false;
  }
  if (inMapFilterState.samProjects && inMapFilterState.samProjects.size > 0) {
    const pName = (d._project || '').trim();
    if (!inMapFilterState.samProjects.has(pName)) {
      const nk = d._normKey || globalProjToNormMap.get(pName) || '';
      if (!nk || !inMapFilterState.samProjectsNorm || !inMapFilterState.samProjectsNorm.has(nk)) return false;
    }
  } else if (inMapFilterState.samProject && inMapFilterState.samProject !== '') {
    const pName = (d._project || '').trim();
    if (pName !== inMapFilterState.samProject) {
      const nk = d._normKey || globalProjToNormMap.get(pName) || '';
      const targetNk = inMapFilterState.samProjectsNorm ? Array.from(inMapFilterState.samProjectsNorm)[0] : normalizeProjectKeyword(inMapFilterState.samProject);
      if (!nk || !targetNk || nk !== targetNk) return false;
    }
  }

  const _isCentroidItem = (String(d._centroid) === '1' || d._centroid === true || d._centroid === 'true');
  if (_isCentroidItem && !(inMapFilterState && inMapFilterState.includeCentroids)) {
    return false;
  }

  if (inMapFilterState.onlyWithProject) {
    const p = (d._project || '').trim();
    if (!p || p === '-' || p === 'ไม่มีข้อมูล' || p === 'ไม่ระบุ' || p === 'null' || isInvalidProjectName(p)) {
      return false;
    }
    if (normKeyToCanonicalMap && normKeyToCanonicalMap.size > 0) {
      const nk = d._normKey;
      if (!nk || !normKeyToCanonicalMap.has(nk)) {
        return false;
      }
    }
    if (excludeAxis !== 'company' && inMapFilterState.companies && inMapFilterState.companies.size >= 2) {
      if (!isProjectMatchingCompanySharing(d)) return false;
    }
  }

  if (excludeAxis !== 'company' && inMapFilterState.companies.size > 0 && !inMapFilterState.companies.has(d._company)) {
    return false;
  }
  if (excludeAxis !== 'type' && inMapFilterState.types.size > 0 && !inMapFilterState.types.has(d._type)) {
    return false;
  }
  if (inMapFilterState.sales.size > 0 && !inMapFilterState.sales.has(d._sale)) {
    return false;
  }
  const minP = inMapFilterState.minPrice;
  if (minP !== null && !isNaN(minP) && minP > 0) {
    if ((d._price || 0) < minP) return false;
  }
  const maxP = inMapFilterState.maxPrice;
  if (maxP !== null && !isNaN(maxP) && maxP > 0) {
    if ((d._price || 0) > maxP) return false;
  }

  // Filter 5: ขนาดเนื้อที่ดิน (ตร.ว.)
  const minSqw = inMapFilterState.minSqw;
  if (minSqw !== null && !isNaN(minSqw) && minSqw > 0) {
    if ((d._sqw || 0) < minSqw) return false;
  }
  const maxSqw = inMapFilterState.maxSqw;
  if (maxSqw !== null && !isNaN(maxSqw) && maxSqw > 0) {
    if ((d._sqw || 0) > maxSqw) return false;
  }

  // Filter 6: พื้นที่ใช้สอย (ตร.ม.)
  const minSqm = inMapFilterState.minSqm;
  if (minSqm !== null && !isNaN(minSqm) && minSqm > 0) {
    if ((d._sqm || 0) < minSqm) return false;
  }
  const maxSqm = inMapFilterState.maxSqm;
  if (maxSqm !== null && !isNaN(maxSqm) && maxSqm > 0) {
    if ((d._sqm || 0) > maxSqm) return false;
  }

  // Filter 7: ราคาต่อ ตร.ว.
  const minPuw = inMapFilterState.minPuw;
  if (minPuw !== null && !isNaN(minPuw) && minPuw > 0) {
    if ((d._puw || 0) < minPuw) return false;
  }
  const maxPuw = inMapFilterState.maxPuw;
  if (maxPuw !== null && !isNaN(maxPuw) && maxPuw > 0) {
    if ((d._puw || 0) > maxPuw) return false;
  }

  // Filter 8: ราคาต่อ ตร.ม.
  const minPum = inMapFilterState.minPum;
  if (minPum !== null && !isNaN(minPum) && minPum > 0) {
    if ((d._pum || 0) < minPum) return false;
  }
  const maxPum = inMapFilterState.maxPum;
  if (maxPum !== null && !isNaN(maxPum) && maxPum > 0) {
    if ((d._pum || 0) > maxPum) return false;
  }

  // Filter 9: ชั้น
  if (inMapFilterState.floors && inMapFilterState.floors.size > 0) {
    const fl = (d._fl !== undefined && d._fl !== null) ? +d._fl : -1;
    let passFl = false;
    if (fl < 0) {
      if (inMapFilterState.floors.has('none')) passFl = true;
    } else {
      if (inMapFilterState.floors.has('1') && Math.floor(fl) === 1) passFl = true;
      if (inMapFilterState.floors.has('2') && Math.floor(fl) === 2) passFl = true;
      if (inMapFilterState.floors.has('3') && Math.floor(fl) === 3) passFl = true;
      if (inMapFilterState.floors.has('4+') && fl >= 4) passFl = true;
    }
    if (!passFl) return false;
  }
  if (inMapFilterState.minFloor !== null && !isNaN(inMapFilterState.minFloor) && inMapFilterState.minFloor > 0) {
    const fl = (d._fl !== undefined && d._fl !== null) ? +d._fl : -1;
    if (fl < 0 || fl < inMapFilterState.minFloor) return false;
  }
  if (inMapFilterState.maxFloor !== null && !isNaN(inMapFilterState.maxFloor) && inMapFilterState.maxFloor > 0) {
    const fl = (d._fl !== undefined && d._fl !== null) ? +d._fl : -1;
    if (fl < 0 || fl > inMapFilterState.maxFloor) return false;
  }

  // Filter 10: ห้องนอน
  if (inMapFilterState.bedrooms && inMapFilterState.bedrooms.size > 0) {
    const bed = (d._bed !== undefined && d._bed !== null) ? +d._bed : -1;
    let passBed = false;
    if (bed < 0) {
      if (inMapFilterState.bedrooms.has('none')) passBed = true;
    } else {
      if (inMapFilterState.bedrooms.has('0') && bed === 0) passBed = true;
      if (inMapFilterState.bedrooms.has('1') && Math.round(bed) === 1) passBed = true;
      if (inMapFilterState.bedrooms.has('2') && Math.round(bed) === 2) passBed = true;
      if (inMapFilterState.bedrooms.has('3') && Math.round(bed) === 3) passBed = true;
      if (inMapFilterState.bedrooms.has('4') && Math.round(bed) === 4) passBed = true;
      if (inMapFilterState.bedrooms.has('5+') && bed >= 5) passBed = true;
    }
    if (!passBed) return false;
  }

  // Filter 11: ห้องน้ำ
  if (inMapFilterState.bathrooms && inMapFilterState.bathrooms.size > 0) {
    const bath = (d._bath !== undefined && d._bath !== null) ? +d._bath : -1;
    let passBath = false;
    if (bath < 0) {
      if (inMapFilterState.bathrooms.has('none')) passBath = true;
    } else {
      if (inMapFilterState.bathrooms.has('1') && Math.round(bath) === 1) passBath = true;
      if (inMapFilterState.bathrooms.has('2') && Math.round(bath) === 2) passBath = true;
      if (inMapFilterState.bathrooms.has('3') && Math.round(bath) === 3) passBath = true;
      if (inMapFilterState.bathrooms.has('4') && Math.round(bath) === 4) passBath = true;
      if (inMapFilterState.bathrooms.has('5+') && bath >= 5) passBath = true;
    }
    if (!passBath) return false;
  }

  // Filter 12: ที่จอดรถ
  if (inMapFilterState.parkings && inMapFilterState.parkings.size > 0) {
    const pkg = (d._pkg !== undefined && d._pkg !== null) ? +d._pkg : -1;
    let passPkg = false;
    if (pkg < 0) {
      if (inMapFilterState.parkings.has('none')) passPkg = true;
    } else {
      if (inMapFilterState.parkings.has('1') && Math.round(pkg) === 1) passPkg = true;
      if (inMapFilterState.parkings.has('2') && Math.round(pkg) === 2) passPkg = true;
      if (inMapFilterState.parkings.has('3') && Math.round(pkg) === 3) passPkg = true;
      if (inMapFilterState.parkings.has('4+') && pkg >= 4) passPkg = true;
    }
    if (!passPkg) return false;
  }

  // Filter 13: อายุวันประกาศ
  const effMaxAge = (inMapFilterState.maxAge !== null && inMapFilterState.maxAge > 0) ? inMapFilterState.maxAge : (inMapFilterState.agePreset ? parseFloat(inMapFilterState.agePreset) : null);
  if (effMaxAge !== null && !isNaN(effMaxAge) && effMaxAge >= 0) {
    const age = (d._age !== undefined && d._age !== null) ? +d._age : -1;
    if (age < 0 || age > effMaxAge) return false;
  }

  return true;
}

function applyInMapFilters(skipParentNotify = false) {
  const getInpVal = (id) => {
    const el = document.getElementById(id);
    const v = el ? parseFloat(el.value) : NaN;
    return (!isNaN(v) && v > 0) ? v : null;
  };

  inMapFilterState.minPrice = getInpVal('filter-min-price');
  inMapFilterState.maxPrice = getInpVal('filter-max-price');
  inMapFilterState.minSqw   = getInpVal('filter-min-sqw');
  inMapFilterState.maxSqw   = getInpVal('filter-max-sqw');
  inMapFilterState.minSqm   = getInpVal('filter-min-sqm');
  inMapFilterState.maxSqm   = getInpVal('filter-max-sqm');
  inMapFilterState.minPuw   = getInpVal('filter-min-puw');
  inMapFilterState.maxPuw   = getInpVal('filter-max-puw');
  inMapFilterState.minPum   = getInpVal('filter-min-pum');
  inMapFilterState.maxPum   = getInpVal('filter-max-pum');
  inMapFilterState.minFloor = getInpVal('filter-min-floor');
  inMapFilterState.maxFloor = getInpVal('filter-max-floor');
  inMapFilterState.maxAge   = getInpVal('filter-max-age');

  // General Filters Count:
  let generalCount = inMapFilterState.companies.size + inMapFilterState.types.size + inMapFilterState.sales.size;
  if (inMapFilterState.onlyWithProject) generalCount++;
  if (inMapFilterState.includeCentroids) generalCount++;
  if (inMapFilterState.agePreset !== null || (inMapFilterState.maxAge !== null && inMapFilterState.maxAge > 0)) generalCount++;

  // Spec & Pricing Filters Count:
  let specCount = 0;
  ['minPrice', 'maxPrice', 'minSqw', 'maxSqw', 'minSqm', 'maxSqm', 'minPuw', 'maxPuw', 'minPum', 'maxPum', 'minFloor', 'maxFloor'].forEach(k => {
    if (inMapFilterState[k] !== null && inMapFilterState[k] > 0) specCount++;
  });
  specCount += (inMapFilterState.floors ? inMapFilterState.floors.size : 0);
  specCount += (inMapFilterState.bedrooms ? inMapFilterState.bedrooms.size : 0);
  specCount += (inMapFilterState.bathrooms ? inMapFilterState.bathrooms.size : 0);
  specCount += (inMapFilterState.parkings ? inMapFilterState.parkings.size : 0);

  const hasProjFilter = (inMapFilterState.samProjects && inMapFilterState.samProjects.size > 0) || (inMapFilterState.samProject && inMapFilterState.samProject !== '');
  let filterCount = generalCount + specCount + (hasProjFilter ? 1 : 0);

  const badgeEl = document.getElementById('inmap-filter-badge');
  if (badgeEl) {
    if (generalCount > 0) {
      badgeEl.innerText = generalCount;
      badgeEl.style.display = 'inline-block';
    } else {
      badgeEl.style.display = 'none';
    }
  }

  const badgeSpec = document.getElementById('inmap-spec-filter-badge');
  if (badgeSpec) {
    if (specCount > 0) {
      badgeSpec.innerText = specCount;
      badgeSpec.style.display = 'inline-block';
    } else {
      badgeSpec.style.display = 'none';
    }
  }

  if (hasProjFilter) {
    // Project filter takes highest priority: show all properties belonging to the selected project(s)
    const prjCount = inMapFilterState.samProjects ? inMapFilterState.samProjects.size : 1;
    const projDesc = prjCount > 1 ? `${prjCount} โครงการ` : (Array.from(inMapFilterState.samProjects)[0] || inMapFilterState.samProject);

    let candidatePool = [];
    const seenIds = new Set();
    const targetNorms = inMapFilterState.samProjectsNorm || new Set();

    if (targetNorms.size > 0) {
      targetNorms.forEach(nk => {
        const items = globalNormToItemsMap.get(nk);
        if (items) {
          for (let i = 0; i < items.length; i++) {
            const it = items[i];
            const uKey = _itemUniqueKey(it);
            if (!seenIds.has(uKey)) {
              seenIds.add(uKey);
              candidatePool.push(it);
            }
          }
        }
        // Also match items whose normalized project key contains or starts with nk
        if (nk && nk.length >= 6) {
          for (const [otherNk, otherItems] of globalNormToItemsMap.entries()) {
            if (otherNk !== nk && (otherNk.startsWith(nk) || nk.startsWith(otherNk))) {
              for (let i = 0; i < otherItems.length; i++) {
                const it = otherItems[i];
                const uKey = _itemUniqueKey(it);
                if (!seenIds.has(uKey)) {
                  seenIds.add(uKey);
                  candidatePool.push(it);
                }
              }
            }
          }
        }
      });
    }

    if (inMapFilterState.samProjects && inMapFilterState.samProjects.size > 0) {
      inMapFilterState.samProjects.forEach(pName => {
        const items = globalProjToItemsMap.get(pName);
        if (items) {
          for (let i = 0; i < items.length; i++) {
            const it = items[i];
            const uKey = _itemUniqueKey(it);
            if (!seenIds.has(uKey)) {
              seenIds.add(uKey);
              candidatePool.push(it);
            }
          }
        }
      });
    }

    if (candidatePool.length === 0 && inMapFilterState.samProject) {
      const targetNk = normalizeProjectKeyword(inMapFilterState.samProject);
      const items = globalNormToItemsMap.get(targetNk) || globalProjToItemsMap.get(inMapFilterState.samProject);
      if (items) candidatePool = items.slice();
    }

    if (candidatePool.length === 0) {
      candidatePool = cachedData || [];
    }

    currentScopePool = candidatePool || [];
    currentNearbyData = candidatePool.filter(filterItemPasses);
    currentCoordMap = buildCoordMap(currentNearbyData);
    updateDuplicateStats(currentNearbyData, currentCoordMap);

    let locDesc = '';
    const locParts = [currentSelectedProv, currentSelectedDist, currentSelectedSubdist].filter(x => x && x !== '__ALL__');
    if (locParts.length > 0) {
      locDesc = ` (${locParts.join(' > ')})`;
    }

    const statusEl = document.getElementById('radius-status-text');
    if (statusEl) {
      statusEl.innerHTML = `<span style="color:#059669; font-weight:800;"><i class="fa-solid fa-building-flag" style="margin-right:4px;"></i> โครงการ: ${escapeHtml(projDesc)}${escapeHtml(locDesc)}</span> พบ <b>${currentNearbyData.length.toLocaleString()}</b> รายการ`;
    }
    const countEl = document.getElementById('points-count');
    if (countEl) {
      countEl.innerText = `โครงการ: ${projDesc}${locDesc} (${currentNearbyData.length.toLocaleString()} รายการ)`;
    }
  } else if (mapPinMode === 'location') {
    const hasProvSelected = Boolean(currentSelectedProv && currentSelectedProv.trim() !== '' && currentSelectedProv !== '__ALL__');
    const hasDistSelected = Boolean(currentSelectedDist && currentSelectedDist.trim() !== '' && currentSelectedDist !== '__ALL__');
    const hasSubdistSelected = Boolean(currentSelectedSubdist && currentSelectedSubdist.trim() !== '' && currentSelectedSubdist !== '__ALL__');
    const hasOnlyProjFilter = !!(inMapFilterState && inMapFilterState.onlyWithProject);
    const hasCompaniesFilter = !!(inMapFilterState && inMapFilterState.companies && inMapFilterState.companies.size > 0);
    const allowNationwidePins = hasOnlyProjFilter || (hasCompaniesFilter && inMapFilterState.companies.size <= 2);

    if (!hasProvSelected && !allowNationwidePins) {
      currentScopePool = [];
      currentNearbyData = [];
      currentCoordMap = new Map();
      updateDuplicateStats(currentNearbyData, currentCoordMap);

      const statusEl = document.getElementById('radius-status-text');
      if (statusEl) {
        statusEl.innerHTML = `<span style="color:#059669; font-weight:800;"><i class="fa-solid fa-map-location-dot" style="margin-right:4px;"></i> ทุกจังหวัด:</span> กรุณาเลือกจังหวัด เพื่อแสดงหมุดตามทำเล`;
      }
      const countEl = document.getElementById('points-count');
      if (countEl) {
        countEl.innerText = `ทุกจังหวัด: กรุณาเลือกจังหวัด เพื่อแสดงหมุด`;
      }
    } else {
      // Location mode with province/district/subdistrict selected (or nationwide with specific filters e.g. onlyWithProject)
      currentScopePool = hasProvSelected ? (cachedData || []).filter(isItemInCurrentLocation) : (cachedData || []);
      currentNearbyData = currentScopePool.filter(filterItemPasses);
      currentCoordMap = buildCoordMap(currentNearbyData);
      updateDuplicateStats(currentNearbyData, currentCoordMap);

      let locDesc = '';
      if (hasProvSelected) {
        locDesc = currentSelectedProv;
        if (currentSelectedDist) locDesc += ' > ' + currentSelectedDist;
        if (currentSelectedSubdist) locDesc += ' > ' + currentSelectedSubdist;
      } else {
        locDesc = 'ทั่วประเทศ';
      }

      let titlePrefix = 'หมุดตามทำเล';
      let titleIcon = 'fa-map-pin';
      if (hasOnlyProjFilter) {
        titleIcon = 'fa-building-circle-check';
        if (hasCompaniesFilter && inMapFilterState.companies.size >= 2) {
          const coNames = Array.from(inMapFilterState.companies).join(' + ');
          titlePrefix = `โครงการเดียวกัน (${coNames})`;
        } else if (hasCompaniesFilter && inMapFilterState.companies.size === 1) {
          titlePrefix = `เฉพาะทรัพย์มีโครงการ (${Array.from(inMapFilterState.companies)[0]})`;
        } else {
          titlePrefix = 'เฉพาะทรัพย์มีโครงการ';
        }
      }

      const statusEl = document.getElementById('radius-status-text');
      if (statusEl) {
        statusEl.innerHTML = `<span style="color:#10b981; font-weight:800;"><i class="fa-solid ${escapeHtml(titleIcon)}"></i> ${escapeHtml(titlePrefix)} (${escapeHtml(locDesc)}):</span> พบ <b>${currentNearbyData.length.toLocaleString()}</b> รายการ`;
      }
      const countEl = document.getElementById('points-count');
      if (countEl) {
        countEl.innerText = `${titlePrefix}: แสดง ${currentNearbyData.length.toLocaleString()} รายการ (${locDesc})`;
      }
    }
  } else {
    // Radius mode: strictly within reference radius
    if (referencePoint) {
      const rawNearby = queryPointsInRadius(referencePoint[0], referencePoint[1], currentRadiusKm);
      currentScopePool = rawNearby || [];
      currentNearbyData = rawNearby.filter(filterItemPasses);
      currentCoordMap = buildCoordMap(currentNearbyData);
      updateDuplicateStats(currentNearbyData, currentCoordMap);

      const statusEl = document.getElementById('radius-status-text');
      if (statusEl) {
        statusEl.innerHTML = `<span style="color:#ef4444; font-weight:800;"><i class="fa-solid fa-bullseye"></i> จุดอ้างอิง (ตามรัศมี):</span> พบ <b>${currentNearbyData.length.toLocaleString()}</b> รายการ (ในรัศมี <b>${formatRadiusDisplay(currentRadiusKm)}</b>)`;
      }
      const countEl = document.getElementById('points-count');
      if (countEl) {
        countEl.innerText = `จุดอ้างอิง: แสดง ${currentNearbyData.length.toLocaleString()} รายการ (ในรัศมี ${formatRadiusDisplay(currentRadiusKm)})`;
      }
    } else {
      currentScopePool = [];
      currentNearbyData = [];
      currentCoordMap = new Map();
      const disp = formatRadiusDisplay(currentRadiusKm);
      const statusEl = document.getElementById('radius-status-text');
      if (statusEl) {
        statusEl.innerHTML = `คลิกบนแผนที่เพื่อกำหนดจุดอ้างอิง (รัศมี ${disp})`;
      }
      const countEl = document.getElementById('points-count');
      if (countEl) {
        countEl.innerText = `คลิกบนแผนที่เพื่อกำหนดจุดอ้างอิง (รัศมี ${disp})`;
      }
    }
  }

  updateLegendContent();
  updateDeckLayers();
  updatePropertyCardPosition();
  scheduleParentKpiUpdate();
  if (!skipParentNotify) {
    notifyParentFilterChange();
  }
}

function serializeMultiFilterParam(iter) {
  const arr = Array.from(iter || []).map(x => String(x || '').trim()).filter(Boolean);
  if (!arr.length) return '';
  return arr.some(item => item.includes(',')) ? JSON.stringify(arr) : arr.join(',');
}

function parseMultiFilterParam(raw) {
  const s = String(raw || '').trim();
  if (!s) return [];
  if (s.startsWith('[')) {
    try {
      const parsed = JSON.parse(s);
      if (Array.isArray(parsed)) {
        return parsed.map(x => String(x || '').trim()).filter(Boolean);
      }
    } catch (_e) {}
  }
  return s.split(',').map(x => x.trim()).filter(Boolean);
}

let syncFilterDebounceTimer = null;
function notifyParentFilterChange() {
  clearTimeout(syncFilterDebounceTimer);
  syncFilterDebounceTimer = setTimeout(() => {
    try {
      if (!window.parent) return;
      var u = new URL(window.parent.location.href);
      u.searchParams.set('map_ref_radius', currentRadiusKm);
      u.searchParams.set('map_pin_mode', mapPinMode || 'radius');

      // Location parameters
      if (currentSelectedProv && currentSelectedProv !== '__ALL__') {
        u.searchParams.set('map_prov', currentSelectedProv);
      } else {
        u.searchParams.set('map_prov', '__ALL__');
        u.searchParams.delete('map_dist');
        u.searchParams.delete('map_subdist');
      }
      if (currentSelectedDist && currentSelectedDist !== '__ALL__') {
        u.searchParams.set('map_dist', currentSelectedDist);
      } else {
        u.searchParams.delete('map_dist');
      }
      if (currentSelectedSubdist && currentSelectedSubdist !== '__ALL__') {
        u.searchParams.set('map_subdist', currentSelectedSubdist);
      } else {
        u.searchParams.delete('map_subdist');
      }

      // Project parameter
      if (inMapFilterState && inMapFilterState.samProjects && inMapFilterState.samProjects.size > 0) {
        u.searchParams.set('map_proj', serializeMultiFilterParam(inMapFilterState.samProjects));
      } else if (inMapFilterState && inMapFilterState.samProject) {
        u.searchParams.set('map_proj', serializeMultiFilterParam([inMapFilterState.samProject]));
      } else {
        u.searchParams.delete('map_proj');
      }

      if (referencePoint) {
        const latVal = referencePoint.lat !== undefined ? referencePoint.lat : referencePoint[1];
        const lonVal = referencePoint.lon !== undefined ? referencePoint.lon : referencePoint[0];
        if (latVal && lonVal) {
          u.searchParams.set('map_ref_lat', Number(latVal).toFixed(6));
          u.searchParams.set('map_ref_lon', Number(lonVal).toFixed(6));
        }
      } else {
        u.searchParams.delete('map_ref_lat');
        u.searchParams.delete('map_ref_lon');
        u.searchParams.delete('map_ref_id');
      }

      if (inMapFilterState && inMapFilterState.companies && inMapFilterState.companies.size > 0) {
        u.searchParams.set('map_filter_cos', serializeMultiFilterParam(inMapFilterState.companies));
      } else {
        u.searchParams.delete('map_filter_cos');
      }
      if (inMapFilterState && inMapFilterState.types && inMapFilterState.types.size > 0) {
        u.searchParams.set('map_filter_types', serializeMultiFilterParam(inMapFilterState.types));
      } else {
        u.searchParams.delete('map_filter_types');
      }
      if (inMapFilterState && inMapFilterState.minPrice) {
        u.searchParams.set('map_filter_min_p', inMapFilterState.minPrice);
      } else {
        u.searchParams.delete('map_filter_min_p');
      }
      if (inMapFilterState && inMapFilterState.maxPrice) {
        u.searchParams.set('map_filter_max_p', inMapFilterState.maxPrice);
      } else {
        u.searchParams.delete('map_filter_max_p');
      }
      if (inMapFilterState && inMapFilterState.minSqw) {
        u.searchParams.set('map_filter_min_sqw', inMapFilterState.minSqw);
      } else {
        u.searchParams.delete('map_filter_min_sqw');
      }
      if (inMapFilterState && inMapFilterState.maxSqw) {
        u.searchParams.set('map_filter_max_sqw', inMapFilterState.maxSqw);
      } else {
        u.searchParams.delete('map_filter_max_sqw');
      }
      if (inMapFilterState && inMapFilterState.minSqm) {
        u.searchParams.set('map_filter_min_sqm', inMapFilterState.minSqm);
      } else {
        u.searchParams.delete('map_filter_min_sqm');
      }
      if (inMapFilterState && inMapFilterState.maxSqm) {
        u.searchParams.set('map_filter_max_sqm', inMapFilterState.maxSqm);
      } else {
        u.searchParams.delete('map_filter_max_sqm');
      }
      if (inMapFilterState && inMapFilterState.sales && inMapFilterState.sales.size > 0) {
        u.searchParams.set('map_filter_sales', serializeMultiFilterParam(inMapFilterState.sales));
      } else {
        u.searchParams.delete('map_filter_sales');
      }
      if (inMapFilterState && inMapFilterState.minPuw) {
        u.searchParams.set('map_filter_min_puw', inMapFilterState.minPuw);
      } else {
        u.searchParams.delete('map_filter_min_puw');
      }
      if (inMapFilterState && inMapFilterState.maxPuw) {
        u.searchParams.set('map_filter_max_puw', inMapFilterState.maxPuw);
      } else {
        u.searchParams.delete('map_filter_max_puw');
      }
      if (inMapFilterState && inMapFilterState.minPum) {
        u.searchParams.set('map_filter_min_pum', inMapFilterState.minPum);
      } else {
        u.searchParams.delete('map_filter_min_pum');
      }
      if (inMapFilterState && inMapFilterState.maxPum) {
        u.searchParams.set('map_filter_max_pum', inMapFilterState.maxPum);
      } else {
        u.searchParams.delete('map_filter_max_pum');
      }
      if (inMapFilterState && inMapFilterState.onlyWithProject) {
        u.searchParams.set('map_filter_only_proj', '1');
      } else {
        u.searchParams.delete('map_filter_only_proj');
      }
      if (inMapFilterState && inMapFilterState.includeCentroids) {
        u.searchParams.set('map_include_centroids', '1');
      } else {
        u.searchParams.delete('map_include_centroids');
      }
      if (inMapFilterState && inMapFilterState.floors && inMapFilterState.floors.size > 0) {
        u.searchParams.set('map_filter_floors', serializeMultiFilterParam(inMapFilterState.floors));
      } else {
        u.searchParams.delete('map_filter_floors');
      }
      if (inMapFilterState && inMapFilterState.minFloor) {
        u.searchParams.set('map_filter_min_fl', inMapFilterState.minFloor);
      } else {
        u.searchParams.delete('map_filter_min_fl');
      }
      if (inMapFilterState && inMapFilterState.maxFloor) {
        u.searchParams.set('map_filter_max_fl', inMapFilterState.maxFloor);
      } else {
        u.searchParams.delete('map_filter_max_fl');
      }
      if (inMapFilterState && inMapFilterState.bedrooms && inMapFilterState.bedrooms.size > 0) {
        u.searchParams.set('map_filter_beds', serializeMultiFilterParam(inMapFilterState.bedrooms));
      } else {
        u.searchParams.delete('map_filter_beds');
      }
      if (inMapFilterState && inMapFilterState.bathrooms && inMapFilterState.bathrooms.size > 0) {
        u.searchParams.set('map_filter_baths', serializeMultiFilterParam(inMapFilterState.bathrooms));
      } else {
        u.searchParams.delete('map_filter_baths');
      }
      if (inMapFilterState && inMapFilterState.parkings && inMapFilterState.parkings.size > 0) {
        u.searchParams.set('map_filter_pkgs', serializeMultiFilterParam(inMapFilterState.parkings));
      } else {
        u.searchParams.delete('map_filter_pkgs');
      }
      const effAgeUrl = (inMapFilterState && inMapFilterState.maxAge !== null && inMapFilterState.maxAge > 0)
        ? String(inMapFilterState.maxAge)
        : (inMapFilterState && inMapFilterState.agePreset ? String(inMapFilterState.agePreset) : '');
      if (effAgeUrl) {
        u.searchParams.set('map_filter_max_age', effAgeUrl);
      } else {
        u.searchParams.delete('map_filter_max_age');
      }
      window.parent.history.replaceState({}, '', u.toString());
      triggerStreamlitSync(null, 80);
    } catch(e) {
      console.warn('notifyParentFilterChange error:', e);
    }
  }, 150);
}

function getMapSyncPayload() {
  var p = (currentSelectedProv && currentSelectedProv !== '__ALL__') ? currentSelectedProv.trim() : '__ALL__';
  var d = (currentSelectedDist && currentSelectedDist !== '__ALL__') ? currentSelectedDist.trim() : '';
  var s = (currentSelectedSubdist && currentSelectedSubdist !== '__ALL__') ? currentSelectedSubdist.trim() : '';
  var id = currentRefProp ? (currentRefProp._id || '') : (currentRefId || '');
  var lat = referencePoint ? (referencePoint.lat !== undefined ? referencePoint.lat : (referencePoint[1] || 0)) : (currentRefProp && currentRefProp.lat ? parseFloat(currentRefProp.lat) : 0);
  var lon = referencePoint ? (referencePoint.lon !== undefined ? referencePoint.lon : (referencePoint[0] || 0)) : (currentRefProp && currentRefProp.lon ? parseFloat(currentRefProp.lon) : 0);
  var projArr = [];
  if (inMapFilterState && inMapFilterState.samProjects && inMapFilterState.samProjects.size > 0) {
    projArr = Array.from(inMapFilterState.samProjects);
  } else if (inMapFilterState && inMapFilterState.samProject) {
    projArr = [inMapFilterState.samProject];
  }
  var projStr = serializeMultiFilterParam(projArr);
  var cosList = (inMapFilterState && inMapFilterState.companies && inMapFilterState.companies.size > 0) ? Array.from(inMapFilterState.companies) : [];
  var typesList = (inMapFilterState && inMapFilterState.types && inMapFilterState.types.size > 0) ? Array.from(inMapFilterState.types) : [];
  var salesList = (inMapFilterState && inMapFilterState.sales && inMapFilterState.sales.size > 0) ? Array.from(inMapFilterState.sales) : [];
  var minP = inMapFilterState ? (inMapFilterState.minPrice || 0) : 0;
  var maxP = inMapFilterState ? (inMapFilterState.maxPrice || 0) : 0;
  var minSqw = inMapFilterState ? (inMapFilterState.minSqw || 0) : 0;
  var maxSqw = inMapFilterState ? (inMapFilterState.maxSqw || 0) : 0;
  var minSqm = inMapFilterState ? (inMapFilterState.minSqm || 0) : 0;
  var maxSqm = inMapFilterState ? (inMapFilterState.maxSqm || 0) : 0;
  var minPuw = inMapFilterState ? (inMapFilterState.minPuw || 0) : 0;
  var maxPuw = inMapFilterState ? (inMapFilterState.maxPuw || 0) : 0;
  var minPum = inMapFilterState ? (inMapFilterState.minPum || 0) : 0;
  var maxPum = inMapFilterState ? (inMapFilterState.maxPum || 0) : 0;
  var flChips = (inMapFilterState && inMapFilterState.floors && inMapFilterState.floors.size > 0) ? Array.from(inMapFilterState.floors) : [];
  var bedChips = (inMapFilterState && inMapFilterState.bedrooms && inMapFilterState.bedrooms.size > 0) ? Array.from(inMapFilterState.bedrooms) : [];
  var bathChips = (inMapFilterState && inMapFilterState.bathrooms && inMapFilterState.bathrooms.size > 0) ? Array.from(inMapFilterState.bathrooms) : [];
  var pkgChips = (inMapFilterState && inMapFilterState.parkings && inMapFilterState.parkings.size > 0) ? Array.from(inMapFilterState.parkings) : [];
  var effMaxAge = (inMapFilterState && inMapFilterState.maxAge !== null && inMapFilterState.maxAge > 0) ? inMapFilterState.maxAge : (inMapFilterState && inMapFilterState.agePreset ? parseFloat(inMapFilterState.agePreset) : 0);
  var minFl = inMapFilterState ? (inMapFilterState.minFloor || 0) : 0;
  var maxFl = inMapFilterState ? (inMapFilterState.maxFloor || 0) : 0;
  return {
    prov: p,
    dist: d,
    subdist: s,
    proj: projStr,
    proj_list: projArr,
    id: id,
    price_center_id: currentPriceCenterId || '',
    lat: lat,
    lon: lon,
    radius: currentRadiusKm || 5.0,
    mode: mapPinMode || 'location',
    cos: cosList,
    types: typesList,
    sales: salesList,
    min_p: minP,
    max_p: maxP,
    min_sqw: minSqw,
    max_sqw: maxSqw,
    min_sqm: minSqm,
    max_sqm: maxSqm,
    min_puw: minPuw,
    max_puw: maxPuw,
    min_pum: minPum,
    max_pum: maxPum,
    floors: flChips,
    min_fl: minFl,
    max_fl: maxFl,
    beds: bedChips,
    baths: bathChips,
    pkgs: pkgChips,
    max_age: effMaxAge,
    only_with_proj: (inMapFilterState && !!inMapFilterState.onlyWithProject),
    include_centroids: (inMapFilterState && !!inMapFilterState.includeCentroids),
    compare_active: true,
    compare_ids: (selectedComparisonProps ? Array.from(selectedComparisonProps.keys()) : [])
  };
}

function restoreInMapFiltersFromParentUrl() {
  try {
    if (window.__NOVA_FORCE_FRESH_RESET__) return;
    if (!window.parent || !window.parent.location) return;
    const sp = new URL(window.parent.location.href).searchParams;
    const parseSet = (k) => parseMultiFilterParam(sp.get(k));
    const parsePosNum = (k) => {
      const raw = (sp.get(k) || '').trim();
      if (!raw) return null;
      const n = parseFloat(raw);
      return Number.isFinite(n) && n > 0 ? n : null;
    };
    const pinMode = (sp.get('map_pin_mode') || '').trim();
    if (pinMode === 'radius' || pinMode === 'location') {
      mapPinMode = pinMode;
    }
    const cos = parseSet('map_filter_cos');
    if (cos.length) inMapFilterState.companies = new Set(cos);
    const types = parseSet('map_filter_types');
    if (types.length) inMapFilterState.types = new Set(types);
    const sales = parseSet('map_filter_sales');
    if (sales.length) inMapFilterState.sales = new Set(sales);
    const floors = parseSet('map_filter_floors');
    if (floors.length && inMapFilterState.floors) inMapFilterState.floors = new Set(floors);
    const beds = parseSet('map_filter_beds');
    if (beds.length && inMapFilterState.bedrooms) inMapFilterState.bedrooms = new Set(beds);
    const baths = parseSet('map_filter_baths');
    if (baths.length && inMapFilterState.bathrooms) inMapFilterState.bathrooms = new Set(baths);
    const pkgs = parseSet('map_filter_pkgs');
    if (pkgs.length && inMapFilterState.parkings) inMapFilterState.parkings = new Set(pkgs);
    const projs = parseSet('map_proj');
    if (projs.length) {
      inMapFilterState.samProjects = new Set(projs);
      inMapFilterState.samProject = projs[0];
      inMapFilterState.samProjectsNorm = new Set(projs.map(p => normalizeProjectKeyword(p)).filter(Boolean));
    }
    const numFields = [
      ['map_filter_min_p', 'minPrice', 'filter-min-price'],
      ['map_filter_max_p', 'maxPrice', 'filter-max-price'],
      ['map_filter_min_sqw', 'minSqw', 'filter-min-sqw'],
      ['map_filter_max_sqw', 'maxSqw', 'filter-max-sqw'],
      ['map_filter_min_sqm', 'minSqm', 'filter-min-sqm'],
      ['map_filter_max_sqm', 'maxSqm', 'filter-max-sqm'],
      ['map_filter_min_puw', 'minPuw', 'filter-min-puw'],
      ['map_filter_max_puw', 'maxPuw', 'filter-max-puw'],
      ['map_filter_min_pum', 'minPum', 'filter-min-pum'],
      ['map_filter_max_pum', 'maxPum', 'filter-max-pum'],
      ['map_filter_min_fl', 'minFloor', 'filter-min-floor'],
      ['map_filter_max_fl', 'maxFloor', 'filter-max-floor']
    ];
    numFields.forEach(([paramKey, stateKey, inputId]) => {
      const v = parsePosNum(paramKey);
      if (v !== null) {
        inMapFilterState[stateKey] = v;
        const inp = document.getElementById(inputId);
        if (inp) inp.value = String(v);
      }
    });
    const maxAgeVal = parsePosNum('map_filter_max_age');
    if (maxAgeVal !== null) {
      const agePresetKey = String(Math.round(maxAgeVal));
      if (['30', '60', '90', '180', '365'].includes(agePresetKey) && Math.abs(maxAgeVal - Number(agePresetKey)) < 1e-6) {
        inMapFilterState.agePreset = agePresetKey;
        inMapFilterState.maxAge = null;
      } else {
        inMapFilterState.maxAge = maxAgeVal;
        const ageInp = document.getElementById('filter-max-age');
        if (ageInp) ageInp.value = String(maxAgeVal);
      }
    }
    if (sp.get('map_filter_only_proj') === '1') {
      inMapFilterState.onlyWithProject = true;
    }
    if (sp.get('map_include_centroids') === '1') {
      inMapFilterState.includeCentroids = true;
    }
    // Sync .filter-chip active classes in case chips were rendered before URL restore
    const groupStateMap = {
      company: inMapFilterState.companies,
      type: inMapFilterState.types,
      sale: inMapFilterState.sales,
      floor: inMapFilterState.floors,
      bedroom: inMapFilterState.bedrooms,
      bathroom: inMapFilterState.bathrooms,
      parking: inMapFilterState.parkings
    };
    document.querySelectorAll('.filter-chip[data-group][data-val]').forEach(chipEl => {
      const g = chipEl.dataset.group;
      const v = chipEl.dataset.val;
      if (g === 'age') {
        chipEl.classList.toggle('active', Boolean(inMapFilterState.agePreset && inMapFilterState.agePreset === v));
      } else if (groupStateMap[g]) {
        chipEl.classList.toggle('active', groupStateMap[g].has(v));
      }
    });
    updateHasProjectButtonUI();
    updateIncludeCentroidsButtonUI();
  } catch (e) {
    console.warn('restoreInMapFiltersFromParentUrl warning:', e);
  }
}

var streamlitSyncTimer = null;
var streamlitSyncBtnTimer = null;
var lastSyncPayload = null;
var lastExecutedSyncJson = null;

function triggerStreamlitSync(customPayload, delayMs) {
  var delay = (delayMs !== undefined) ? delayMs : 320;
  var basePayload = getMapSyncPayload();
  lastSyncPayload = (customPayload && typeof customPayload === 'object')
    ? Object.assign({}, basePayload, customPayload)
    : basePayload;
  if (streamlitSyncTimer) {
    clearTimeout(streamlitSyncTimer);
    streamlitSyncTimer = null;
  }
  if (delay <= 0) {
    executeStreamlitSync(lastSyncPayload);
    return;
  }
  streamlitSyncTimer = setTimeout(function() {
    executeStreamlitSync(lastSyncPayload);
    streamlitSyncTimer = null;
  }, delay);
}

function executeStreamlitSync(payload) {
  try {
    if (!window.parent) return;
    var pWin = window.parent;
    var pdoc = pWin.document;
    var finalPayload = payload || lastSyncPayload || getMapSyncPayload();
    var jsonStr = JSON.stringify(finalPayload);
    if (jsonStr === lastExecutedSyncJson) {
      return;
    }
    lastExecutedSyncJson = jsonStr;

    // Set hidden bridge input to pass exact data directly to Streamlit Python fragment (never dispatch popstate on window.parent, which would trigger a full-app rerun)
    try {
      if (pdoc) {
        var bridgeInput = pdoc.querySelector('.st-key-map_sync_bridge_payload input') ||
                          pdoc.querySelector('input[aria-label="map_sync_bridge"]') ||
                          (function() {
                            var inps = pdoc.querySelectorAll('input');
                            for (var i = 0; i < inps.length; i++) {
                              if (inps[i].getAttribute('aria-label') === 'map_sync_bridge') return inps[i];
                            }
                            return null;
                          })();
        if (bridgeInput) {
          var pProto = (pWin.HTMLInputElement && pWin.HTMLInputElement.prototype) ||
                       (bridgeInput.ownerDocument && bridgeInput.ownerDocument.defaultView && bridgeInput.ownerDocument.defaultView.HTMLInputElement && bridgeInput.ownerDocument.defaultView.HTMLInputElement.prototype) ||
                       window.HTMLInputElement.prototype;
          var nativeSetter = Object.getOwnPropertyDescriptor(pProto, 'value').set;
          if (nativeSetter) {
            nativeSetter.call(bridgeInput, jsonStr);
          } else {
            bridgeInput.value = jsonStr;
          }
          if (bridgeInput._valueTracker) {
            bridgeInput._valueTracker.setValue('');
          }
          bridgeInput.dispatchEvent(new Event('input', { bubbles: true }));
          bridgeInput.dispatchEvent(new Event('change', { bubbles: true }));
          // Streamlit TextInput commits widget value on Enter key and on Blur!
          try {
            bridgeInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }));
            bridgeInput.dispatchEvent(new Event('blur', { bubbles: true }));
            if (typeof bridgeInput.blur === 'function') bridgeInput.blur();
          } catch(ke) {}
        }
      }
    } catch(ie) {
      console.warn('bridgeInput sync error:', ie);
    }

    // 3. Click sync button after 80ms so React text_input commits value to Streamlit (cancel any stale timer)
    if (streamlitSyncBtnTimer) {
      clearTimeout(streamlitSyncBtnTimer);
      streamlitSyncBtnTimer = null;
    }
    streamlitSyncBtnTimer = setTimeout(function() {
      streamlitSyncBtnTimer = null;
      try {
        var syncBtn = pdoc.querySelector('.st-key-btn_map_filter_sync button') ||
                      pdoc.querySelector('button[key="btn_map_filter_sync"]');
        if (!syncBtn) {
          var anchor = pdoc.querySelector('#map-sync-anchor');
          if (anchor) {
            var parentContainer = anchor.closest('[data-testid="stElementContainer"]') || anchor.parentElement;
            if (parentContainer) {
              var sib = parentContainer.nextElementSibling;
              while (sib) {
                var b = sib.querySelector('button');
                if (b) { syncBtn = b; break; }
                sib = sib.nextElementSibling;
              }
            }
          }
        }
        if (!syncBtn) {
          var allBtns = pdoc.querySelectorAll('button');
          for (var i = 0; i < allBtns.length; i++) {
            var txt = allBtns[i].textContent ? allBtns[i].textContent.trim() : '';
            if (txt === 'sync_map_filter') {
              syncBtn = allBtns[i];
              break;
            }
          }
        }
        if (syncBtn) {
          syncBtn.click();
        }
      } catch(be) {
        console.warn('syncBtn click error:', be);
      }
    }, 80);
  } catch(e) {
    console.warn('executeStreamlitSync error:', e);
  }
}

function hideParentSyncButton() {
  try {
    if (!window.parent) return;
    var allBtns = window.parent.document.querySelectorAll('button');
    for (var i = 0; i < allBtns.length; i++) {
      var txt = allBtns[i].textContent ? allBtns[i].textContent.trim() : '';
      if (txt === 'sync_map_filter') {
        var el = allBtns[i].closest('[data-testid="stElementContainer"]') || allBtns[i];
        el.style.position = 'absolute';
        el.style.left = '-99999px';
        el.style.top = '-99999px';
        el.style.height = '1px';
        el.style.width = '1px';
        el.style.overflow = 'hidden';
        el.style.opacity = '0';
      }
    }
  } catch(e) {}
}

let mapAnimRaf = null;
function smoothFlyTo(targetLon, targetLat, targetZoom, duration, onComplete) {
  if (!deckglInstance) return;
  if (typeof _userInteractedWithMap !== 'undefined') _userInteractedWithMap = true;
  if (typeof dismissInstantMapBackdrop === 'function') dismissInstantMapBackdrop();
  if (mapAnimRaf) {
    cancelAnimationFrame(mapAnimRaf);
    mapAnimRaf = null;
  }

  const startLon = Number(currentViewState.longitude) || 100.52;
  const startLat = Number(currentViewState.latitude) || 13.75;
  const startZoom = Number(currentViewState.zoom) || 8.5;
  const startPitch = Number(currentViewState.pitch) || 0;
  const startBearing = Number(currentViewState.bearing) || 0;

  const dLon = targetLon - startLon;
  const dLat = targetLat - startLat;
  const dZoom = targetZoom - startZoom;

  // Calculate distance in kilometers
  const midLatRad = ((startLat + targetLat) / 2) * (Math.PI / 180);
  const kx = 111.320 * Math.cos(midLatRad);
  const ky = 110.574;
  const distKm = Math.sqrt(Math.pow(dLon * kx, 2) + Math.pow(dLat * ky, 2));

  // Smooth direct flight duration based on physical distance
  let flightDuration = duration;
  if (!flightDuration || flightDuration === 1500 || flightDuration === 900 || flightDuration === 1000 || flightDuration === 1200) {
    if (distKm < 0.5) flightDuration = 600;
    else if (distKm < 5.0) flightDuration = 800;
    else if (distKm < 30.0) flightDuration = 1000;
    else flightDuration = 1200;
  }

  const startTime = performance.now();

  // Smooth cubic ease-in-out: starts gently, accelerates, then decelerates into place
  function easeInOutCubic(t) {
    return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
  }

  let frameCount = 0;
  function stepAnim(now) {
    const elapsed = now - startTime;
    const progress = Math.min(1.0, elapsed / flightDuration);
    const ease = easeInOutCubic(progress);

    const curLon = startLon + dLon * ease;
    const curLat = startLat + dLat * ease;
    // Direct smooth zoom transition to target (no zooming out into the sky)
    const curZoom = startZoom + dZoom * ease;

    const curPitch = startPitch * (1 - ease);
    const curBearing = startBearing * (1 - ease);

    currentViewState = {
      ...currentViewState,
      longitude: curLon,
      latitude: curLat,
      zoom: curZoom,
      pitch: curPitch,
      bearing: curBearing
    };

    deckglInstance.setProps({ viewState: currentViewState });
    updateCompass(curBearing);

    frameCount++;
    // Throttle overlay re-rendering during flight for 60fps smoothness
    if (frameCount % 4 === 0 || progress >= 1.0) {
      try { updateConfirmBubblePosition(); } catch(e) {}
      try { updateSvgBoundaries(); } catch(e) {}
      try { updatePropertyCardPosition(); } catch(e) {}
    }

    if (progress < 1.0) {
      mapAnimRaf = requestAnimationFrame(stepAnim);
    } else {
      mapAnimRaf = null;
      try { updateConfirmBubblePosition(); } catch(e) {}
      try { updateSvgBoundaries(); } catch(e) {}
      try { updatePropertyCardPosition(); } catch(e) {}
      if (onComplete) onComplete();
    }
  }

  mapAnimRaf = requestAnimationFrame(stepAnim);
}

function calculateZoomForRadius(lat, radiusKm) {
  const r = parseFloat(radiusKm) || 5;
  if (r <= 0.5) return 15.6;
  if (r <= 1.0) return 14.8;
  if (r <= 2.0) return 14.0;
  if (r <= 3.0) return 13.5;
  if (r <= 5.0) return 12.8;
  if (r <= 8.0) return 12.2;
  if (r <= 10.0) return 11.8;
  if (r <= 15.0) return 11.2;
  if (r <= 20.0) return 10.6;
  if (r <= 30.0) return 9.8;
  return 9.0;
}
