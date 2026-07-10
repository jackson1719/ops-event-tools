(function() {
  'use strict';

  const WINDOW_BEFORE = 30;   // minutes before now
  const WINDOW_AFTER = 240;   // minutes after now
  const TOTAL_WINDOW = WINDOW_BEFORE + WINDOW_AFTER; // 270 minutes
  const ROW_HEIGHT = 60;      // pixels per room row
  const SLOT_WIDTH = 150;     // pixels per 30-minute slot
  const REFRESH_INTERVAL = 600000; // reload page every 10 minutes

  const isTestMode = TEST_NOW_MINUTES !== null;

  function esc(str) {
    const d = document.createElement('div');
    d.textContent = str;
    return d.innerHTML;
  }

  const EVENT_COLORS = [
    '#2563eb', '#7c3aed', '#0d7377', '#b45309', '#9f1239',
    '#0891b2', '#4f46e5', '#4a6741', '#c2410c', '#7e22ce',
  ];

  function getColor(str) {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
      hash = str.charCodeAt(i) + ((hash << 5) - hash);
    }
    return EVENT_COLORS[Math.abs(hash) % EVENT_COLORS.length];
  }

  function formatTime(totalMinutes) {
    const h = Math.floor(totalMinutes / 60) % 24;
    const m = totalMinutes % 60;
    const ampm = h >= 12 ? 'PM' : 'AM';
    const h12 = h === 0 ? 12 : h > 12 ? h - 12 : h;
    return h12 + ':' + String(m).padStart(2, '0') + ' ' + ampm;
  }

  function nowMinutes() {
    if (isTestMode) return TEST_NOW_MINUTES;
    const d = new Date();
    return d.getHours() * 60 + d.getMinutes();
  }

  // Track selected rooms (null = all)
  let selectedRoomKeys = null;

  function getAllRooms() {
    const rooms = [];
    const seen = new Set();
    for (const e of EVENTS) {
      const key = e.room_name + ' ' + e.room_number;
      if (!seen.has(key)) {
        seen.add(key);
        rooms.push({ name: e.room_name, number: e.room_number, key: key });
      }
    }
    rooms.sort((a, b) => a.key.localeCompare(b.key));
    return rooms;
  }

  function getRooms(events) {
    const rooms = [];
    const seen = new Set();
    for (const e of events) {
      const key = e.room_name + ' ' + e.room_number;
      if (selectedRoomKeys && !selectedRoomKeys.has(key)) continue;
      if (!seen.has(key)) {
        seen.add(key);
        rooms.push({ name: e.room_name, number: e.room_number, key: key });
      }
    }
    rooms.sort((a, b) => a.key.localeCompare(b.key));
    return rooms;
  }

  const ROOM_FILTER_KEY = 'live_room_filter';

  function saveRoomFilter() {
    if (selectedRoomKeys === null) {
      localStorage.removeItem(ROOM_FILTER_KEY);
    } else {
      localStorage.setItem(ROOM_FILTER_KEY, JSON.stringify([...selectedRoomKeys]));
    }
  }

  function loadRoomFilter() {
    try {
      const stored = localStorage.getItem(ROOM_FILTER_KEY);
      if (stored) return new Set(JSON.parse(stored));
    } catch (_) {}
    return null;
  }

  function initRoomFilter() {
    const allRooms = getAllRooms();
    const saved = loadRoomFilter();
    const container = document.getElementById('room-checkboxes');
    let html = '';
    for (const room of allRooms) {
      const label = room.number ? esc(room.name) + ' (' + esc(room.number) + ')' : esc(room.name);
      const id = 'room-' + room.key.replace(/[^a-zA-Z0-9]/g, '_');
      const checked = saved === null || saved.has(room.key) ? 'checked' : '';
      html += `<div class="form-check mb-1">
        <input class="form-check-input room-check room-individual" type="checkbox" value="${esc(room.key)}" id="${id}" ${checked}>
        <label class="form-check-label" for="${id}">${label}</label>
      </div>`;
    }
    container.innerHTML = html;

    const allCheck = document.getElementById('room-all');
    const btn = document.getElementById('room-filter-btn');

    // Apply saved filter state
    if (saved !== null) {
      selectedRoomKeys = saved;
      const boxes = document.querySelectorAll('.room-individual');
      const checkedBoxes = document.querySelectorAll('.room-individual:checked');
      allCheck.checked = checkedBoxes.length === boxes.length;
      if (checkedBoxes.length === boxes.length || checkedBoxes.length === 0) {
        selectedRoomKeys = null;
        btn.textContent = 'Rooms: All';
      } else {
        btn.textContent = 'Rooms: ' + checkedBoxes.length + '/' + boxes.length;
      }
    }

    allCheck.addEventListener('change', function() {
      document.querySelectorAll('.room-individual').forEach(cb => { cb.checked = this.checked; });
      updateRoomFilter();
    });

    container.addEventListener('change', function() {
      const boxes = document.querySelectorAll('.room-individual');
      const checked = document.querySelectorAll('.room-individual:checked');
      allCheck.checked = checked.length === boxes.length;
      updateRoomFilter();
    });

    function updateRoomFilter() {
      const boxes = document.querySelectorAll('.room-individual');
      const checked = document.querySelectorAll('.room-individual:checked');
      if (checked.length === boxes.length || checked.length === 0) {
        selectedRoomKeys = null;
        btn.textContent = 'Rooms: All';
      } else {
        selectedRoomKeys = new Set();
        checked.forEach(cb => selectedRoomKeys.add(cb.value));
        btn.textContent = 'Rooms: ' + checked.length + '/' + boxes.length;
      }
      saveRoomFilter();
      render();
    }
  }

  function render() {
    const now = nowMinutes();
    // Snap window to half-hour boundaries
    const rawStart = now - WINDOW_BEFORE;
    const windowStart = Math.floor(rawStart / 30) * 30;
    const rawEnd = now + WINDOW_AFTER;
    const windowEnd = Math.ceil(rawEnd / 30) * 30;
    const windowTotal = windowEnd - windowStart;

    // Filter events visible in the window
    const visible = EVENTS.filter(e =>
      e.end_min > windowStart && e.start_min < windowEnd
    );

    const rooms = getRooms(visible);
    if (rooms.length === 0) {
      document.getElementById('room-labels').innerHTML =
        '<div style="padding:20px;color:#888;">No events in the current time window.</div>';
      document.getElementById('events-area').innerHTML = '';
      document.getElementById('time-header').innerHTML = '';
      return;
    }

    const numSlots = windowTotal / 30;
    const totalWidth = numSlots * SLOT_WIDTH;

    // Time header — always aligned to :00 and :30
    let headerHtml = '';
    for (let i = 0; i < numSlots; i++) {
      const slotMin = windowStart + i * 30;
      headerHtml += `<div class="time-label" style="width:${SLOT_WIDTH}px;">${formatTime(slotMin)}</div>`;
    }
    document.getElementById('time-header').innerHTML = headerHtml;

    // Room labels
    let labelsHtml = '';
    for (const room of rooms) {
      const label = room.number ? esc(room.name) + ' (' + esc(room.number) + ')' : esc(room.name);
      labelsHtml += `<div class="room-label" style="height:${ROW_HEIGHT}px;">${label}</div>`;
    }
    document.getElementById('room-labels').innerHTML = labelsHtml;

    // Events area — use pixel positioning to match the fixed-width time header
    const pxPerMin = SLOT_WIDTH / 30;
    let eventsHtml = '';
    for (let ri = 0; ri < rooms.length; ri++) {
      const room = rooms[ri];
      let rowHtml = `<div class="event-row" style="height:${ROW_HEIGHT}px;width:${totalWidth}px;">`;

      const roomEvents = visible.filter(e =>
        e.room_name === room.name && e.room_number === room.number
      );
      for (const e of roomEvents) {
        const clampStart = Math.max(e.start_min, windowStart);
        const clampEnd = Math.min(e.end_min, windowEnd);
        const leftPx = (clampStart - windowStart) * pxPerMin;
        const widthPx = (clampEnd - clampStart) * pxPerMin;
        const color = e.event_name.toUpperCase() === 'STRIKE' ? '#b91c1c' : getColor(room.key);

        const tip = esc(e.start_time) + ' - ' + esc(e.end_time) + ': ' + esc(e.event_name) + (e.description ? '\n' + esc(e.description) : '');
        rowHtml += `<div class="event-block" style="left:${leftPx}px;width:${widthPx}px;background:${color};"
                         title="${tip}">
          <span class="event-time">${esc(e.start_time)}</span>
          ${esc(e.event_name)}
        </div>`;
      }

      rowHtml += '</div>';
      eventsHtml += rowHtml;
    }

    // Half-hour lines
    for (let i = 0; i < numSlots; i++) {
      const leftPx = i * SLOT_WIDTH;
      eventsHtml += `<div class="half-hour-line" style="left:${leftPx}px;"></div>`;
    }

    // Now line
    const nowPx = (now - windowStart) * pxPerMin;
    eventsHtml += `<div class="now-line" style="left:${nowPx}px;"></div>`;

    document.getElementById('events-area').innerHTML = eventsHtml;

    // Sync scroll between room labels and events area
    const eventsArea = document.getElementById('events-area');
    const roomLabels = document.getElementById('room-labels');
    eventsArea.onscroll = function() {
      roomLabels.scrollTop = eventsArea.scrollTop;
    };
  }

  function updateClock() {
    if (isTestMode) {
      document.getElementById('clock').textContent = 'TEST: ' + formatTime(TEST_NOW_MINUTES);
      return;
    }
    const d = new Date();
    const h = d.getHours();
    const m = d.getMinutes();
    const s = d.getSeconds();
    const ampm = h >= 12 ? 'PM' : 'AM';
    const h12 = h === 0 ? 12 : h > 12 ? h - 12 : h;
    document.getElementById('clock').textContent =
      h12 + ':' + String(m).padStart(2, '0') + ':' + String(s).padStart(2, '0') + ' ' + ampm;
  }

  // Build URL from current filter state
  function buildUrl() {
    const building = document.getElementById('building-filter').value;
    const av = document.getElementById('av-filter').value;
    const date = document.getElementById('date-filter').value;
    const time = document.getElementById('time-filter').value;
    let url = LIVE_URL + '?building=' + encodeURIComponent(building) + '&av=' + encodeURIComponent(av);
    if (date) url += '&date=' + encodeURIComponent(date);
    if (time) url += '&time=' + encodeURIComponent(time);
    return url;
  }

  // Filter controls
  document.getElementById('building-filter').addEventListener('change', function() {
    window.location.href = buildUrl();
  });
  document.getElementById('av-filter').addEventListener('change', function() {
    window.location.href = buildUrl();
  });
  document.getElementById('date-filter').addEventListener('change', function() {
    window.location.href = buildUrl();
  });
  document.getElementById('time-filter').addEventListener('change', function() {
    window.location.href = buildUrl();
  });
  document.getElementById('clear-test').addEventListener('click', function() {
    const building = document.getElementById('building-filter').value;
    const av = document.getElementById('av-filter').value;
    window.location.href = LIVE_URL + '?building=' + encodeURIComponent(building) + '&av=' + encodeURIComponent(av);
  });

  // Initial render
  initRoomFilter();
  render();
  updateClock();

  // Update clock every second, re-render every 60 seconds (only in live mode)
  if (!isTestMode) {
    setInterval(updateClock, 1000);
    setInterval(render, 60000);
    setTimeout(function() { window.location.href = buildUrl(); }, REFRESH_INTERVAL);
  }
})();
