% rebase('base.tpl')

<style>
  .cal-header { display: flex; align-items: center; gap: 1rem; margin-bottom: 1rem; flex-wrap: wrap; }
  .cal-header a { color: var(--muted); text-decoration: none; font-size: 0.88rem; font-weight: 600; }
  .cal-header a:hover { color: var(--text); }
  .cal-preview { position: relative; width: 100%; margin-bottom: 1rem; background: var(--bg-deep);
    border-radius: 0.75rem; border: 1px solid var(--border); overflow: hidden; }
  .cal-preview img { display: block; width: 100%; height: auto; }
  .cal-overlay { position: absolute; top: 0; left: 0; width: 100%; height: 100%; touch-action: none; }
  .cal-quad { fill: none; stroke: var(--accent); stroke-width: 1.5; stroke-dasharray: 6 4; pointer-events: none; }
  .cal-expected { fill: none; stroke: var(--muted); stroke-width: 1.5; pointer-events: none; }
  .cal-mark { cursor: grab; outline: none; }
  .cal-mark:active { cursor: grabbing; }
  .cal-mark circle.dot { fill: var(--accent); stroke: var(--text); stroke-width: 1.5; }
  .cal-mark.ok circle.dot { stroke: var(--success-line); stroke-width: 3; }
  .cal-mark.caution circle.dot { stroke: var(--caution-line); stroke-width: 3; }
  .cal-mark.error circle.dot { stroke: var(--error-line); stroke-width: 3; }
  .cal-mark .ring { display: none; fill: none; stroke: var(--accent); stroke-width: 2; }
  .cal-mark:focus .ring { display: block; }
  .cal-mark text { fill: var(--text); font-size: 12px; font-weight: 700; pointer-events: none; }
  .cal-results { margin-bottom: 0.72rem; }
  .cal-actions { display: flex; gap: 0.5rem; flex-wrap: wrap; }
</style>

<div class="cal-header">
  <a href="/">&larr; Back to settings</a>
</div>

<div class="section" data-help="calibration_check" id="calibration-check">
  <h2>Calibration Check <span class="section-note">Floor marks over the live video</span></h2>

  <div id="cal-preview" class="cal-preview" style="display:none;">
    <img id="cal-image" alt="Live video snapshot">
    <svg id="cal-overlay" class="cal-overlay" xmlns="http://www.w3.org/2000/svg" role="group" aria-label="Floor marks"></svg>
  </div>
  <div id="cal-no-feed" class="notice" style="display:none;">No video feed available.<div class="notice-sub">Configure a video source, then press Refresh Image.</div></div>

  <table class="data-table cal-results" aria-live="polite">
    <thead><tr><th scope="col">Mark</th><th scope="col">Error</th></tr></thead>
    <tbody id="cal-rows"></tbody>
  </table>

  <div class="actions cal-actions">
    <button type="button" class="secondary" id="cal-refresh">Refresh Image</button>
    <button type="button" class="secondary" id="cal-reset">Reset Marks</button>
    <a href="/wizard" class="btn-link btn-secondary">Open Setup Wizard</a>
  </div>
</div>

<script>
(function() {
  'use strict';
  var NAMES = ['DSL', 'DSR', 'USR', 'USL', 'REF'];
  var LABELS = {
    DSL: 'Downstage left', DSR: 'Downstage right', USR: 'Upstage right', USL: 'Upstage left', REF: 'Centre stage'
  };
  var CHIP = { ok: 'ok', caution: 'warn', error: 'off' };
  var svg = document.getElementById('cal-overlay');
  var img = document.getElementById('cal-image');
  var rows = document.getElementById('cal-rows');
  var section = document.getElementById('calibration-check');
  var saveError = window.OpenFollow.saveError;
  var width = 0, height = 0, imageUrl = null;
  var expected = {}, placed = {}, levels = {};
  var checkTimer = null;

  function ns(tag) { return document.createElementNS('http://www.w3.org/2000/svg', tag); }

  function failed(response) {
    if (!response) { saveError.show(section, saveError.UNREACHABLE, 'Not checked.'); return; }
    saveError.fromResponse(response).then(function(info) { saveError.show(section, info, 'Not checked.'); });
  }

  function render() {
    svg.innerHTML = '';
    svg.setAttribute('viewBox', '0 0 ' + width + ' ' + height);
    var corners = ['DSL', 'DSR', 'USR', 'USL'].map(function(n) { return expected[n]; });
    if (corners.every(Boolean)) {
      var quad = ns('polygon');
      quad.setAttribute('class', 'cal-quad');
      quad.setAttribute('points', corners.map(function(p) { return p[0] + ',' + p[1]; }).join(' '));
      svg.appendChild(quad);
    }
    NAMES.forEach(function(name) {
      var exp = expected[name];
      if (!exp) return;
      var pos = placed[name] || exp;
      var ghost = ns('circle');
      ghost.setAttribute('class', 'cal-expected');
      ghost.setAttribute('cx', exp[0]);
      ghost.setAttribute('cy', exp[1]);
      ghost.setAttribute('r', 5);
      svg.appendChild(ghost);
      var g = ns('g');
      g.setAttribute('class', 'cal-mark ' + (levels[name] || ''));
      g.setAttribute('tabindex', '0');
      g.setAttribute('role', 'button');
      g.setAttribute('aria-label', LABELS[name] + ' mark, move with the arrow keys');
      g.dataset.name = name;
      g.setAttribute('transform', 'translate(' + pos[0] + ',' + pos[1] + ')');
      var hit = ns('rect');
      hit.setAttribute('x', -22); hit.setAttribute('y', -22);
      hit.setAttribute('width', 44); hit.setAttribute('height', 44);
      hit.setAttribute('fill', 'transparent');
      g.appendChild(hit);
      var ring = ns('circle'); ring.setAttribute('class', 'ring'); ring.setAttribute('r', 14); g.appendChild(ring);
      var dot = ns('circle'); dot.setAttribute('class', 'dot'); dot.setAttribute('r', 7); g.appendChild(dot);
      var label = ns('text'); label.setAttribute('x', 12); label.setAttribute('y', 4); label.textContent = name;
      g.appendChild(label);
      svg.appendChild(g);
    });
  }

  function renderRows(result) {
    rows.innerHTML = '';
    var byName = {};
    (result ? result.marks : []).forEach(function(m) { byName[m.name] = m; });
    NAMES.forEach(function(name) {
      if (!expected[name]) return;
      var tr = document.createElement('tr');
      var th = document.createElement('td');
      th.textContent = LABELS[name] + ' (' + name + ')';
      var td = document.createElement('td');
      var m = byName[name];
      if (m) {
        var chip = document.createElement('span');
        chip.className = 'stat-chip ' + CHIP[m.level];
        chip.textContent = m.error_text;
        td.appendChild(chip);
      } else {
        td.textContent = 'Drag onto the tape mark';
      }
      tr.appendChild(th); tr.appendChild(td);
      rows.appendChild(tr);
    });
  }

  function check() {
    var marks = {};
    Object.keys(placed).forEach(function(n) { marks[n] = placed[n]; });
    if (!Object.keys(marks).length) { levels = {}; renderRows(null); render(); return; }
    fetch('/api/calibration/check', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ image_width: width, image_height: height, marks: marks })
    }).then(function(r) {
      if (!r.ok) { failed(r); return; }
      return r.json().then(function(body) {
        saveError.clear(section);
        levels = {};
        body.marks.forEach(function(m) { levels[m.name] = m.level; });
        renderRows(body);
        render();
      });
    }).catch(function() { failed(null); });
  }

  function scheduleCheck() {
    clearTimeout(checkTimer);
    checkTimer = setTimeout(check, 150);
  }

  function loadMarks() {
    fetch('/api/calibration/marks?image_width=' + width + '&image_height=' + height).then(function(r) {
      if (!r.ok) { failed(r); return; }
      return r.json().then(function(body) {
        saveError.clear(section);
        expected = body.marks;
        placed = {};
        levels = {};
        render();
        renderRows(null);
      });
    }).catch(function() { failed(null); });
  }

  function loadSnapshot() {
    fetch('/api/video/snapshot/full?t=' + Date.now()).then(function(r) {
      if (!r.ok) throw new Error('No feed');
      return r.blob();
    }).then(function(blob) {
      var next = URL.createObjectURL(blob);
      img.onload = function() {
        if (imageUrl) URL.revokeObjectURL(imageUrl);
        imageUrl = next;
        var resized = width !== img.naturalWidth || height !== img.naturalHeight;
        width = img.naturalWidth;
        height = img.naturalHeight;
        document.getElementById('cal-preview').style.display = '';
        document.getElementById('cal-no-feed').style.display = 'none';
        if (resized || !Object.keys(expected).length) loadMarks(); else render();
      };
      img.src = next;
    }).catch(function() {
      document.getElementById('cal-preview').style.display = 'none';
      document.getElementById('cal-no-feed').style.display = '';
    });
  }

  function svgPoint(e) {
    var pt = svg.createSVGPoint();
    pt.x = e.clientX; pt.y = e.clientY;
    var p = pt.matrixTransform(svg.getScreenCTM().inverse());
    return [Math.max(0, Math.min(width, p.x)), Math.max(0, Math.min(height, p.y))];
  }

  var dragging = null;
  svg.addEventListener('pointerdown', function(e) {
    var mark = e.target.closest('.cal-mark');
    if (!mark) return;
    e.preventDefault();
    dragging = mark.dataset.name;
    svg.setPointerCapture(e.pointerId);
  });
  svg.addEventListener('pointermove', function(e) {
    if (!dragging) return;
    placed[dragging] = svgPoint(e);
    render();
    scheduleCheck();
  });
  svg.addEventListener('pointerup', function() {
    if (!dragging) return;
    var name = dragging;
    dragging = null;
    var el = svg.querySelector('.cal-mark[data-name="' + name + '"]');
    if (el) el.focus();
  });
  svg.addEventListener('keydown', function(e) {
    var mark = e.target.closest('.cal-mark');
    var step = e.shiftKey ? 10 : 1;
    var delta = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] }[e.key];
    if (!mark || !delta) return;
    e.preventDefault();
    var name = mark.dataset.name;
    var pos = (placed[name] || expected[name]).slice();
    placed[name] = [pos[0] + delta[0], pos[1] + delta[1]];
    render();
    var el = svg.querySelector('.cal-mark[data-name="' + name + '"]');
    if (el) el.focus();
    scheduleCheck();
  });

  document.getElementById('cal-refresh').addEventListener('click', loadSnapshot);
  document.getElementById('cal-reset').addEventListener('click', function() {
    placed = {}; levels = {}; render(); renderRows(null);
  });
  loadSnapshot();
})();
</script>
