%# The All Performers panel: each performer marker, whether it holds a person,
%# and which one the spotlight follows.
% performers = view.get('performers', [])
% spot = view.get('spotlight')
% if spot is None:
<p class="slot-empty">Choose a spotlight marker to follow one performer.</p>
% end
% if not performers:
<p class="slot-empty">No performer markers. Take control of markers under Markers.</p>
% else:
<table class="slot-table data-table">
    <thead>
        <tr>
            <th scope="col">Performer</th>
            <th scope="col">Status</th>
            <th scope="col" aria-label="Actions"></th>
        </tr>
    </thead>
    <tbody>
    % for p in performers:
        <tr class="slot-row{{' is-followed' if p['followed'] else ''}}">
            <th scope="row"><span class="slot-marker"><span class="slot-marker-dot" style="--marker-color: {{p['color']}}"></span>{{p['label']}}</span></th>
            <td>{{'Tracking a person' if p['tracking'] else 'No person'}}{{' - followed' if p['followed'] else ''}}</td>
            <td class="row-actions">
            % if spot is not None and p['followed']:
                <button type="button" class="secondary small" hx-post="/section/detection/follow/none" hx-target="#performers-content" hx-swap="innerHTML">Stop following</button>
            % elif spot is not None:
                <button type="button" class="secondary small" hx-post="/section/detection/follow/{{p['marker_id']}}" hx-target="#performers-content" hx-swap="innerHTML">Follow</button>
            % end
            </td>
        </tr>
    % end
    </tbody>
</table>
% end
