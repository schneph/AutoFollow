% # One collapsible row per moving light, each with its own form and a
% # Calibrate panel: aim the light by hand at floor marks, then fit where it
% # hangs. Recorded marks live in the page until Solve fills the form.
% fixtures = config.dmx_output.fixtures
% focus = focus_id if defined('focus_id') else ''
% marks = calibration_marks if defined('calibration_marks') else []
<div class="section" data-fold-key="moving_lights" data-help="dmx_output">
    <div class="section-head">
        <h2>Lights</h2>
        <span class="section-note">Each light follows one marker</span>
    </div>
    % if not fixtures:
    <p class="empty-state">No moving lights set up. Use <em>+ Add light</em> below to add one.</p>
    % end
    % for f in fixtures:
    <details class="osc-destination-row" data-row-id="{{f.id}}" {{'open' if focus == f.id else ''}}>
        <summary class="osc-destination-summary">
            <span class="osc-destination-title">{{f.name or '(unnamed)'}}</span>
            <span class="osc-destination-addr">Universe {{f.universe}} / {{f.address}} &middot; Marker {{f.marker_id}}</span>
            % if not f.enabled:
            <span class="osc-destination-proto-badge">Off</span>
            % end
        </summary>
        <form class="moving-light-form" hx-post="/section/moving_light/{{f.id}}" hx-target="#dmx-output-section" hx-swap="outerHTML" hx-trigger="submit">
            <div class="row">
                <div class="field checkbox-field">
                    <label>Enabled</label>
                    <div class="checkbox-wrap"><input type="checkbox" name="enabled" {{'checked' if f.enabled else ''}}></div>
                </div>
                <div class="field">
                    <label for="ml-name-{{f.id}}">Name</label>
                    <input id="ml-name-{{f.id}}" type="text" name="name" value="{{f.name}}" maxlength="64"
                           hx-get="/api/validate/moving_light/name" hx-trigger="blur changed delay:200ms"
                           hx-target="#ml-name-{{f.id}}-error" hx-swap="innerHTML" hx-include="closest form"
                           aria-describedby="ml-name-{{f.id}}-error" aria-invalid="false">
                    <span id="ml-name-{{f.id}}-error" class="field-error"></span>
                </div>
                <div class="field">
                    <label for="ml-marker-{{f.id}}">Follows Marker</label>
                    <select id="ml-marker-{{f.id}}" name="marker_id">
                    % if f.marker_id not in config.controlled_marker_ids:
                        <option value="{{f.marker_id}}" selected disabled>Marker {{f.marker_id}} (unavailable)</option>
                    % end
                    % for marker_id in config.controlled_marker_ids:
                        <option value="{{marker_id}}" {{'selected' if f.marker_id == marker_id else ''}}>Marker {{marker_id}}</option>
                    % end
                    </select>
                </div>
            </div>

            <h3 class="group-title">Patch</h3>
            <div class="row">
            % for fname, label, lo, hi in (('universe', 'Universe', 0, 63999), ('address', 'Address', 1, 512), ('pan_channel', 'Pan Channel', 1, 512), ('tilt_channel', 'Tilt Channel', 1, 512)):
                <div class="field">
                    <label for="ml-{{fname}}-{{f.id}}">{{label}}</label>
                    <input id="ml-{{fname}}-{{f.id}}" type="number" name="{{fname}}" value="{{getattr(f, fname)}}" min="{{lo}}" max="{{hi}}" step="1"
                           hx-get="/api/validate/moving_light/{{fname}}" hx-trigger="blur changed delay:200ms"
                           hx-target="#ml-{{fname}}-{{f.id}}-error" hx-swap="innerHTML" hx-include="closest form"
                           aria-describedby="ml-{{fname}}-{{f.id}}-error" aria-invalid="false">
                    <span id="ml-{{fname}}-{{f.id}}-error" class="field-error"></span>
                </div>
            % end
                <div class="field">
                    <label for="ml-ma2_fixture-{{f.id}}">grandMA2 Fixture ID</label>
                    <input id="ml-ma2_fixture-{{f.id}}" type="number" name="ma2_fixture" value="{{f.ma2_fixture}}" min="0" max="99999" step="1"
                           hx-get="/api/validate/moving_light/ma2_fixture" hx-trigger="blur changed delay:200ms"
                           hx-target="#ml-ma2_fixture-{{f.id}}-error" hx-swap="innerHTML" hx-include="closest form"
                           aria-describedby="ml-ma2_fixture-{{f.id}}-error" aria-invalid="false">
                    <span id="ml-ma2_fixture-{{f.id}}-error" class="field-error"></span>
                </div>
                <div class="field checkbox-field">
                    <label>16-bit</label>
                    <div class="checkbox-wrap"><input type="checkbox" name="fine" {{'checked' if f.fine else ''}}></div>
                </div>
            </div>

            <h3 class="group-title">Travel</h3>
            <div class="row">
            % for fname, label, lo, hi in (('pan_range', 'Pan Range (°)', 1, 720), ('tilt_range', 'Tilt Range (°)', 1, 360)):
                <div class="field">
                    <label for="ml-{{fname}}-{{f.id}}">{{label}}</label>
                    <input id="ml-{{fname}}-{{f.id}}" type="number" name="{{fname}}" value="{{getattr(f, fname)}}" min="{{lo}}" max="{{hi}}" step="any"
                           hx-get="/api/validate/moving_light/{{fname}}" hx-trigger="blur changed delay:200ms"
                           hx-target="#ml-{{fname}}-{{f.id}}-error" hx-swap="innerHTML" hx-include="closest form"
                           aria-describedby="ml-{{fname}}-{{f.id}}-error" aria-invalid="false">
                    <span id="ml-{{fname}}-{{f.id}}-error" class="field-error"></span>
                </div>
            % end
                <div class="field checkbox-field">
                    <label>Invert Pan</label>
                    <div class="checkbox-wrap"><input type="checkbox" name="invert_pan" {{'checked' if f.invert_pan else ''}}></div>
                </div>
                <div class="field checkbox-field">
                    <label>Invert Tilt</label>
                    <div class="checkbox-wrap"><input type="checkbox" name="invert_tilt" {{'checked' if f.invert_tilt else ''}}></div>
                </div>
            </div>

            <h3 class="group-title">Position</h3>
            <div class="row">
                <div class="field">
                    <label for="ml-mounting-{{f.id}}">Mounting</label>
                    <select id="ml-mounting-{{f.id}}" name="mounting">
                        <option value="hung" {{'selected' if f.mounting == 'hung' else ''}}>Hung (base up)</option>
                        <option value="floor" {{'selected' if f.mounting == 'floor' else ''}}>On the floor (base down)</option>
                    </select>
                </div>
            % for fname, label, lo, hi in (('pos_x', 'X (m)', -1000, 1000), ('pos_y', 'Y (m)', -1000, 1000), ('pos_z', 'Z (m)', -1000, 1000), ('heading', 'Heading (°)', -360, 360), ('base_pitch', 'Base Pitch (°)', -45, 45), ('base_roll', 'Base Roll (°)', -45, 45)):
                <div class="field">
                    <label for="ml-{{fname}}-{{f.id}}">{{label}}</label>
                    <input id="ml-{{fname}}-{{f.id}}" type="number" name="{{fname}}" value="{{getattr(f, fname)}}" min="{{lo}}" max="{{hi}}" step="any"
                           hx-get="/api/validate/moving_light/{{fname}}" hx-trigger="blur changed delay:200ms"
                           hx-target="#ml-{{fname}}-{{f.id}}-error" hx-swap="innerHTML" hx-include="closest form"
                           aria-describedby="ml-{{fname}}-{{f.id}}-error" aria-invalid="false">
                    <span id="ml-{{fname}}-{{f.id}}-error" class="field-error"></span>
                </div>
            % end
            </div>

            <details class="inline-advanced">
                <summary>Calibrate</summary>
                <div class="inline-advanced-content" data-ml-calibrate="{{f.id}}">
                    <div class="row">
                        <div class="field">
                            <label for="ml-aim-pan-{{f.id}}">Pan <span data-ml-pan-readout>50.00</span>%</label>
                            <input id="ml-aim-pan-{{f.id}}" type="range" min="0" max="100" step="0.01" value="50" data-ml-pan>
                        </div>
                        <div class="field">
                            <label for="ml-aim-tilt-{{f.id}}">Tilt <span data-ml-tilt-readout>50.00</span>%</label>
                            <input id="ml-aim-tilt-{{f.id}}" type="range" min="0" max="100" step="0.01" value="50" data-ml-tilt>
                        </div>
                    </div>
                    <div class="row">
                        <div class="field">
                            <label for="ml-mark-{{f.id}}">Mark</label>
                            <select id="ml-mark-{{f.id}}" data-ml-mark>
                            % for m in marks:
                                <option value="{{m['x']}},{{m['y']}},{{m['z']}}">{{m['label']}}</option>
                            % end
                                <option value="custom">Another point</option>
                            </select>
                        </div>
                        <div class="field" data-ml-custom hidden>
                            <label for="ml-custom-x-{{f.id}}">X (m)</label>
                            <input id="ml-custom-x-{{f.id}}" type="number" step="any" value="0" data-ml-custom-x>
                        </div>
                        <div class="field" data-ml-custom hidden>
                            <label for="ml-custom-y-{{f.id}}">Y (m)</label>
                            <input id="ml-custom-y-{{f.id}}" type="number" step="any" value="0" data-ml-custom-y>
                        </div>
                        <div class="field" data-ml-custom hidden>
                            <label for="ml-custom-z-{{f.id}}">Z (m)</label>
                            <input id="ml-custom-z-{{f.id}}" type="number" step="any" value="0" data-ml-custom-z>
                        </div>
                    </div>
                    <table class="slot-table data-table" data-ml-marks-table hidden>
                        <thead>
                            <tr>
                                <th scope="col">Mark</th>
                                <th scope="col">Pan</th>
                                <th scope="col">Tilt</th>
                                <th scope="col">Error</th>
                                <th scope="col" aria-label="Actions"></th>
                            </tr>
                        </thead>
                        <tbody data-ml-marks></tbody>
                    </table>
                    <p data-ml-result hidden></p>
                    <div class="actions">
                        <button type="button" class="secondary small" data-ml-action="record">Record Mark</button>
                        <button type="button" class="secondary small" data-ml-action="solve">Solve Position</button>
                        <button type="button" class="secondary small" data-ml-action="release">Hand Back to Marker</button>
                    </div>
                </div>
            </details>

            <div class="actions">
                <button type="submit" class="save-btn">Save</button>
                <button type="button" class="secondary" hx-post="/section/moving_light/{{f.id}}/delete" hx-target="#dmx-output-section" hx-swap="outerHTML">Delete</button>
            </div>
        </form>
    </details>
    % end
    <div class="actions">
        <button type="button" class="secondary" hx-post="/section/moving_lights/add" hx-target="#dmx-output-section" hx-swap="outerHTML">+ Add light</button>
    </div>
</div>
<script>
(function () {
    'use strict';
    if (window.OpenFollowMovingLights) {
        window.OpenFollowMovingLights.restore();
        return;
    }
    // Recorded marks per light, kept across re-renders of this section.
    var recorded = {};
    var timers = {};

    function panelOf(el) { return el && el.closest ? el.closest('[data-ml-calibrate]') : null; }
    function aimOf(panel) {
        return {
            pan: parseFloat(panel.querySelector('[data-ml-pan]').value) / 100,
            tilt: parseFloat(panel.querySelector('[data-ml-tilt]').value) / 100,
        };
    }
    function fmt(value) { return (value * 100).toFixed(2); }

    async function post(panel, url, body, lead) {
        var saveError = window.OpenFollow.saveError;
        try {
            var res = await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            if (!res.ok) {
                saveError.show(panel, await saveError.fromResponse(res), lead);
                return null;
            }
            saveError.clear(panel);
            return await res.json();
        } catch (err) {
            saveError.show(panel, saveError.UNREACHABLE, lead);
            return null;
        }
    }

    function sendAim(panel) {
        var id = panel.dataset.mlCalibrate;
        clearTimeout(timers[id]);
        timers[id] = setTimeout(function () {
            post(panel, '/api/moving_light/' + id + '/aim', aimOf(panel), 'Not aimed.');
        }, 40);
    }

    function markPoint(panel) {
        var choice = panel.querySelector('[data-ml-mark]');
        if (choice.value === 'custom') {
            return {
                label: 'Point',
                x: parseFloat(panel.querySelector('[data-ml-custom-x]').value),
                y: parseFloat(panel.querySelector('[data-ml-custom-y]').value),
                z: parseFloat(panel.querySelector('[data-ml-custom-z]').value),
            };
        }
        var xyz = choice.value.split(',').map(parseFloat);
        return { label: choice.options[choice.selectedIndex].text, x: xyz[0], y: xyz[1], z: xyz[2] };
    }

    function render(panel) {
        var id = panel.dataset.mlCalibrate;
        var list = recorded[id] || [];
        var body = panel.querySelector('[data-ml-marks]');
        panel.querySelector('[data-ml-marks-table]').hidden = list.length === 0;
        body.replaceChildren();
        list.forEach(function (mark, index) {
            var row = document.createElement('tr');
            [mark.label + ' (' + mark.x + ', ' + mark.y + ')', fmt(mark.pan) + '%', fmt(mark.tilt) + '%',
             mark.error === undefined ? '' : mark.error.toFixed(2) + '°'].forEach(function (text) {
                var cell = document.createElement('td');
                cell.textContent = text;
                row.appendChild(cell);
            });
            var actions = document.createElement('td');
            actions.className = 'row-actions';
            var remove = document.createElement('button');
            remove.type = 'button';
            remove.className = 'secondary small';
            remove.dataset.mlAction = 'remove';
            remove.dataset.mlIndex = String(index);
            remove.textContent = 'Remove';
            actions.appendChild(remove);
            row.appendChild(actions);
            body.appendChild(row);
        });
    }

    async function solve(panel) {
        var id = panel.dataset.mlCalibrate;
        var list = recorded[id] || [];
        var result = await post(panel, '/api/moving_light/' + id + '/solve', { marks: list }, 'Not solved.');
        if (!result) return;
        var form = panel.closest('form');
        ['pos_x', 'pos_y', 'pos_z', 'heading', 'base_pitch', 'base_roll'].forEach(function (name) {
            var input = form.querySelector('[name="' + name + '"]');
            if (input) input.value = result[name];
        });
        list.forEach(function (mark, index) { mark.error = result.errors_deg[index]; });
        render(panel);
        var line = panel.querySelector('[data-ml-result]');
        line.hidden = false;
        line.textContent = 'Worst error ' + result.worst_deg.toFixed(2) + '° over ' + list.length
            + ' marks. Position filled in above: press Save to keep it.';
    }

    document.addEventListener('input', function (event) {
        var panel = panelOf(event.target);
        if (!panel) return;
        if (event.target.matches('[data-ml-pan], [data-ml-tilt]')) {
            var aim = aimOf(panel);
            panel.querySelector('[data-ml-pan-readout]').textContent = fmt(aim.pan);
            panel.querySelector('[data-ml-tilt-readout]').textContent = fmt(aim.tilt);
            sendAim(panel);
        }
    });
    document.addEventListener('change', function (event) {
        var panel = panelOf(event.target);
        if (!panel || !event.target.matches('[data-ml-mark]')) return;
        var custom = event.target.value === 'custom';
        panel.querySelectorAll('[data-ml-custom]').forEach(function (el) { el.hidden = !custom; });
    });
    document.addEventListener('click', function (event) {
        var button = event.target.closest('[data-ml-action]');
        var panel = panelOf(button);
        if (!panel) return;
        var id = panel.dataset.mlCalibrate;
        var action = button.dataset.mlAction;
        if (action === 'record') {
            var point = markPoint(panel);
            var aim = aimOf(panel);
            (recorded[id] = recorded[id] || []).push({
                label: point.label, x: point.x, y: point.y, z: point.z, pan: aim.pan, tilt: aim.tilt,
            });
            render(panel);
        } else if (action === 'remove') {
            (recorded[id] || []).splice(parseInt(button.dataset.mlIndex, 10), 1);
            render(panel);
        } else if (action === 'solve') {
            solve(panel);
        } else if (action === 'release') {
            post(panel, '/api/moving_light/' + id + '/aim', { release: true }, 'Not handed back.');
        }
    });

    window.OpenFollowMovingLights = {
        restore: function () {
            document.querySelectorAll('[data-ml-calibrate]').forEach(render);
        },
    };
})();
</script>
