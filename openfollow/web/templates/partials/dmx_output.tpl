% # Moving lights: the output's own settings, then one row per light. Every
% # moving-light route returns this whole partial, so ``focus_id`` re-opens
% # the light that changed.
% dmx = config.dmx_output
<div id="dmx-output-section" class="experimental-feature">
<form class="section {{'saved' if defined('saved') and saved else ''}}" data-fold-key="dmx_output" data-help="dmx_output"
      hx-post="/section/dmx_output" hx-target="#dmx-output-section" hx-swap="outerHTML" hx-trigger="submit">
    <div class="section-head">
        <h2>Moving Lights <span class="badge-experimental">Experimental</span></h2>
        <span class="section-note">Pan and tilt over sACN, Art-Net or grandMA2 Telnet</span>
    </div>

    <div class="group">
        <h3 class="group-title">Output</h3>
        <div class="row">
            <div class="field checkbox-field">
                <label>Enabled</label>
                <div class="checkbox-wrap"><input type="checkbox" name="enabled" {{'checked' if dmx.enabled else ''}}></div>
            </div>
            <div class="field">
                <label for="dmx-output-protocol">Protocol</label>
                <select id="dmx-output-protocol" name="protocol">
                    <option value="sacn" {{'selected' if dmx.protocol == 'sacn' else ''}}>sACN (E1.31)</option>
                    <option value="artnet" {{'selected' if dmx.protocol == 'artnet' else ''}}>Art-Net</option>
                    <option value="ma2" {{'selected' if dmx.protocol == 'ma2' else ''}}>grandMA2 (Telnet)</option>
                </select>
            </div>
            <div class="field">
                <label for="dmx-output-host">Destination Host</label>
                <input id="dmx-output-host" type="text" name="host" value="{{dmx.host}}" placeholder="Multicast / broadcast" maxlength="255"
                       hx-get="/api/validate/dmx_output/host" hx-trigger="blur changed delay:200ms"
                       hx-target="#dmx-output-host-error" hx-swap="innerHTML" hx-include="closest form"
                       aria-describedby="dmx-output-host-error" aria-invalid="false">
                <span id="dmx-output-host-error" class="field-error"></span>
            </div>
            <div class="field">
                <label for="dmx-output-fps">Send Rate (FPS)</label>
                <input id="dmx-output-fps" type="number" name="fps" value="{{dmx.fps}}" min="1" max="44" step="1"
                       hx-get="/api/validate/dmx_output/fps" hx-trigger="blur changed delay:200ms"
                       hx-target="#dmx-output-fps-error" hx-swap="innerHTML" hx-include="closest form"
                       aria-describedby="dmx-output-fps-error" aria-invalid="false">
                <span id="dmx-output-fps-error" class="field-error"></span>
            </div>
            <div class="field">
                <label for="dmx-output-priority">sACN Priority</label>
                <input id="dmx-output-priority" type="number" name="priority" value="{{dmx.priority}}" min="1" max="200" step="1"
                       hx-get="/api/validate/dmx_output/priority" hx-trigger="blur changed delay:200ms"
                       hx-target="#dmx-output-priority-error" hx-swap="innerHTML" hx-include="closest form"
                       aria-describedby="dmx-output-priority-error" aria-invalid="false">
                <span id="dmx-output-priority-error" class="field-error"></span>
            </div>
        </div>
    </div>

    <div class="group">
        <h3 class="group-title">grandMA2 Telnet</h3>
        <div class="row">
            <div class="field">
                <label for="dmx-output-ma2-port">Telnet Port</label>
                <input id="dmx-output-ma2-port" type="number" name="ma2_port" value="{{dmx.ma2_port}}" min="1" max="65535" step="1"
                       hx-get="/api/validate/dmx_output/ma2_port" hx-trigger="blur changed delay:200ms"
                       hx-target="#dmx-output-ma2-port-error" hx-swap="innerHTML" hx-include="closest form"
                       aria-describedby="dmx-output-ma2-port-error" aria-invalid="false">
                <span id="dmx-output-ma2-port-error" class="field-error"></span>
            </div>
            <div class="field">
                <label for="dmx-output-ma2-user">User</label>
                <input id="dmx-output-ma2-user" type="text" name="ma2_user" value="{{dmx.ma2_user}}" maxlength="64" autocomplete="off"
                       hx-get="/api/validate/dmx_output/ma2_user" hx-trigger="blur changed delay:200ms"
                       hx-target="#dmx-output-ma2-user-error" hx-swap="innerHTML" hx-include="closest form"
                       aria-describedby="dmx-output-ma2-user-error" aria-invalid="false">
                <span id="dmx-output-ma2-user-error" class="field-error"></span>
            </div>
            <div class="field">
                <label for="dmx-output-ma2-password">Password</label>
                <input id="dmx-output-ma2-password" type="password" name="ma2_password" value="{{dmx.ma2_password}}" maxlength="64" autocomplete="off"
                       hx-get="/api/validate/dmx_output/ma2_password" hx-trigger="blur changed delay:200ms"
                       hx-target="#dmx-output-ma2-password-error" hx-swap="innerHTML" hx-include="closest form"
                       aria-describedby="dmx-output-ma2-password-error" aria-invalid="false">
                <span id="dmx-output-ma2-password-error" class="field-error"></span>
            </div>
        </div>
    </div>

    <div class="actions">
        <button type="submit" class="save-btn">Save</button>
    </div>
</form>
% include('partials/moving_lights.tpl', config=config, focus_id=focus_id if defined('focus_id') else '', calibration_marks=calibration_marks if defined('calibration_marks') else [])
</div>
