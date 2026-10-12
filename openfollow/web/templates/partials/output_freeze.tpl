%# Freeze / release every output. Polls the main loop's state, so a freeze from
%# the Operator Screen or a desk shows here too.
<div id="output-freeze" class="output-freeze" hx-get="/section/output_freeze" hx-trigger="every 1s" hx-swap="outerHTML">
    % if frozen:
    <div class="notice warning" role="status">
        <div>Outputs frozen</div>
        <div class="notice-sub">Every controlled marker is held where it is.</div>
        <div class="actions">
            <button type="button" class="secondary small" hx-post="/section/output_freeze/release"
                    hx-target="#output-freeze" hx-swap="outerHTML">Release</button>
        </div>
    </div>
    % else:
    <div class="actions">
        <button type="button" class="secondary small" hx-post="/section/output_freeze/freeze"
                hx-target="#output-freeze" hx-swap="outerHTML">Freeze outputs</button>
    </div>
    % end
</div>
