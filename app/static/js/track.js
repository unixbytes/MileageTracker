(() => {
  const state = {
    watchId: null,
    sessionId: null,
    meters: 0,
    lastLat: null,
    lastLon: null,
    pendingPoint: false,
    pollTimer: null,
    wakeLock: null,
    queuedPoints: [],
    lastPointSent: 0,
  };

  const els = {
    startForm: document.getElementById('start-form'),
    stopBtn: document.getElementById('stop-btn'),
    liveControls: document.getElementById('live-controls'),
    statusText: document.getElementById('status-text'),
    activeDetails: document.getElementById('active-details'),
    sessionIdEl: document.getElementById('session-id'),
    pointsCount: document.getElementById('points-count'),
    distanceMiles: document.getElementById('distance-miles'),
    errorBox: document.getElementById('error-box'),
  };

  function formatMetersToMiles(m) {
    const unitEl = document.getElementById('distance-unit');
    const unit = unitEl && unitEl.textContent ? unitEl.textContent.trim() : 'mi';
    if (unit === 'km') {
      return (m / 1000).toFixed(2);
    }
    return (m / 1609.344).toFixed(2);
  }

  function showError(msg) {
    if (!els.errorBox) return;
    els.errorBox.textContent = msg;
    els.errorBox.classList.remove('d-none');
  }

  function clearError() {
    if (!els.errorBox) return;
    els.errorBox.classList.add('d-none');
    els.errorBox.textContent = '';
  }

  async function requestWakeLock() {
    try {
      if ('wakeLock' in navigator) {
        state.wakeLock = await navigator.wakeLock.request('screen');
      }
    } catch (e) {
      console.warn('Wake Lock failed:', e);
    }
  }

  async function releaseWakeLock() {
    if (state.wakeLock) {
      try {
        await state.wakeLock.release();
      } catch (e) {
        // ignore
      }
      state.wakeLock = null;
    }
  }

  async function sendPoint({ lat, lon, accuracy }) {
    if (!state.sessionId) return;
    if (state.pendingPoint) {
      state.queuedPoints.push({ lat, lon, accuracy });
      return;
    }
    state.pendingPoint = true;
    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 15000);
      const payload = {
        session_id: state.sessionId,
        lat,
        lon,
        accuracy,
      };

      const resp = await fetch('/api/track/point', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        signal: controller.signal,
      });
      clearTimeout(timeout);

      state.lastPointSent = Date.now();
      const data = await resp.json();
      if (!resp.ok) {
        console.error('point error', data);
        state.queuedPoints.push({ lat, lon, accuracy });
        return;
      }

      state.meters = data.total_meters;
      state.lastLat = lat;
      state.lastLon = lon;

      if (els.pointsCount) els.pointsCount.textContent = String(data.points);
      if (els.distanceMiles) els.distanceMiles.textContent = formatMetersToMiles(data.total_meters);
    } catch (e) {
      console.error('sendPoint failed', e);
      state.queuedPoints.push({ lat, lon, accuracy });
    } finally {
      state.pendingPoint = false;
    }
  }

  async function ensureWatch() {
    if (!state.sessionId || state.watchId !== null || !navigator.geolocation) return;
    try {
      state.watchId = navigator.geolocation.watchPosition(
        (pos) => onPosition(pos),
        (err) => {
          console.error('watchPosition error', err);
          state.watchId = null;
          ensureWatch();
        },
        {
          enableHighAccuracy: true,
          maximumAge: 0,
          distanceFilter: 10,
        }
      );
    } catch (e) {
      console.error('watchPosition start failed', e);
      state.watchId = null;
    }
  }

  async function onPosition(pos) {
    if (!state.sessionId) return;
    await sendPoint({
      lat: pos.coords.latitude,
      lon: pos.coords.longitude,
      accuracy: pos.coords.accuracy,
    });
  }

  async function pollPosition() {
    if (!state.sessionId) return;
    if (!navigator.geolocation) return;

    try {
      const pos = await new Promise((resolve, reject) => {
        navigator.geolocation.getCurrentPosition(resolve, reject, {
          enableHighAccuracy: true,
          timeout: 20000,
          maximumAge: 0,
        });
      });
      await onPosition(pos);
    } catch (e) {
      console.warn('pollPosition error', e);
    }
  }

  function startPolling() {
    stopPolling();
    state.pollTimer = setInterval(pollPosition, 5000);
  }

  function stopPolling() {
    if (state.pollTimer) {
      clearInterval(state.pollTimer);
      state.pollTimer = null;
    }
  }

  async function retryQueuedPoints() {
    if (!state.queuedPoints.length) return;
    const queue = state.queuedPoints.slice();
    state.queuedPoints = [];
    for (const pt of queue) {
      await sendPoint(pt);
    }
  }

  async function startTracking() {
    clearError();
    const vehicle = document.getElementById('vehicle').value.trim();
    const note = document.getElementById('note').value.trim();
    const tripTypeInput = document.getElementById('trip_type');
    const tripType = tripTypeInput ? tripTypeInput.value : 'personal';
    if (!vehicle) {
      showError('Vehicle is required.');
      return;
    }

    if (!navigator.geolocation) {
      showError('Geolocation is not supported by this browser.');
      return;
    }

    try {
      const first = await new Promise((resolve, reject) => {
        navigator.geolocation.getCurrentPosition(resolve, reject, {
          enableHighAccuracy: true,
          timeout: 20000,
          maximumAge: 0,
        });
      });

      const payload = {
        vehicle,
        note: note || null,
        trip_type: tripType,
        lat: first.coords.latitude,
        lon: first.coords.longitude,
        accuracy: first.coords.accuracy,
      };

      const resp = await fetch('/api/track/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      const data = await resp.json();
      if (!resp.ok) {
        showError(data.error || 'Failed to start tracking.');
        return;
      }

      state.sessionId = data.session_id;
      state.meters = 0;
      state.lastLat = payload.lat;
      state.lastLon = payload.lon;
      state.queuedPoints = [];

      els.startForm.classList.add('d-none');
      els.liveControls.classList.remove('d-none');
      els.statusText.textContent = 'Active';
      els.activeDetails.classList.remove('d-none');
      els.sessionIdEl.textContent = state.sessionId;
      els.pointsCount.textContent = '1';
      els.distanceMiles.textContent = '0.00';

      ensureWatch();
      startPolling();
      await requestWakeLock();
    } catch (e) {
      showError('Failed to start tracking: ' + (e.message || e));
    }
  }

  async function stopTracking() {
    if (!state.sessionId) return;

    clearError();
    try {
      const resp = await fetch('/api/track/stop', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: state.sessionId }),
      });

      const data = await resp.json();
      if (!resp.ok) {
        showError(data.error || 'Failed to stop tracking.');
        return;
      }

      if (state.watchId !== null && navigator.geolocation) {
        navigator.geolocation.clearWatch(state.watchId);
      }

      state.watchId = null;
      state.sessionId = null;
      state.queuedPoints = [];

      els.liveControls.classList.add('d-none');
      els.startForm.classList.remove('d-none');
      els.statusText.textContent = 'Idle';
      els.activeDetails.classList.add('d-none');
      els.distanceMiles.textContent = '0.00';

      const savedTrip = document.createElement('div');
      savedTrip.className = 'alert alert-success mt-3';
      const unitEl = document.getElementById('distance-unit');
      const unit = unitEl && unitEl.textContent ? unitEl.textContent.trim() : 'mi';
      savedTrip.textContent = `Trip saved: ${formatMetersToMiles(data.meters ? data.meters : 0)} ${unit} (trip #${data.trip_id})`;
      els.errorBox.parentNode.insertBefore(savedTrip, els.errorBox.nextSibling);

      if (document.getElementById('vehicle')) {
        document.getElementById('vehicle').value = '';
      }
      if (document.getElementById('note')) {
        document.getElementById('note').value = '';
      }
    } catch (e) {
      showError('Failed to stop tracking: ' + (e.message || e));
    } finally {
      stopPolling();
      await releaseWakeLock();
    }
  }

  async function refreshStatus() {
    try {
      const resp = await fetch('/api/track/status');
      const data = await resp.json();
      if (data.active) {
        state.sessionId = data.session_id;
        state.meters = data.total_meters;
        els.startForm.classList.add('d-none');
        els.liveControls.classList.remove('d-none');
        els.statusText.textContent = 'Active';
        els.activeDetails.classList.remove('d-none');
        els.sessionIdEl.textContent = data.session_id;
        els.pointsCount.textContent = String(data.points);
        els.distanceMiles.textContent = formatMetersToMiles(data.total_meters);
        startPolling();
        ensureWatch();
        await retryQueuedPoints();
      } else {
        state.sessionId = null;
        stopPolling();
      }
    } catch (e) {
      console.error('status refresh failed', e);
    }
  }

  function handleVisibility() {
    if (document.visibilityState === 'visible') {
      refreshStatus();
    }
  }

  if (els.startForm) {
    els.startForm.addEventListener('submit', (e) => {
      e.preventDefault();
      startTracking();
    });
  }

  if (els.stopBtn) {
    els.stopBtn.addEventListener('click', (e) => {
      e.preventDefault();
      stopTracking();
    });
  }

  const typePersonal = document.getElementById('type-personal');
  const typeBusiness = document.getElementById('type-business');
  const tripTypeInput = document.getElementById('trip_type');

  function setTripType(value) {
    if (!tripTypeInput) return;
    tripTypeInput.value = value;
    if (value === 'personal') {
      typePersonal.classList.add('active');
      typeBusiness.classList.remove('active');
    } else {
      typePersonal.classList.remove('active');
      typeBusiness.classList.add('active');
    }
  }

  if (typePersonal && typeBusiness) {
    typePersonal.addEventListener('click', () => setTripType('personal'));
    typeBusiness.addEventListener('click', () => setTripType('business'));
    setTripType('business');
  }

  document.addEventListener('visibilitychange', handleVisibility);
  refreshStatus();
  setInterval(refreshStatus, 10000);
})();
