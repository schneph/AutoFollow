%# The All Performers panel: each performer marker, whether it holds a person,
%# and which one the spotlight follows.
% performers = view.get('performers', [])
% spot = view.get('spotlight')
% swap_from = view.get('swap_from')
% if spot is None:
<p class="slot-empty">Choose a spotlight marker to follow one performer.</p>
% end
% if not performers:
<p class="slot-empty">No performer markers. Take control of markers under Markers.</p>
% else:
<table class="slot-table data-table"{{!' data-swap-from="%d"' % swap_from if swap_from is not None else ''}}>
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
            % if swap_from is not None:
            %   if p['marker_id'] == swap_from:
                <button type="button" class="secondary small" hx-get="/section/detection/performers" hx-target="#performers-content" hx-swap="innerHTML">Cancel</button>
            %   else:
                <button type="button" class="secondary small" hx-post="/section/detection/swap/{{swap_from}}/{{p['marker_id']}}" hx-target="#performers-content" hx-swap="innerHTML">Swap with this</button>
            %   end
            % else:
            %   if len(performers) > 1:
                <button type="button" class="secondary small" hx-post="/section/detection/swap/{{p['marker_id']}}" hx-target="#performers-content" hx-swap="innerHTML">Swap</button>
            %   end
            % if spot is not None and p['followed']:
                <button type="button" class="secondary small" hx-post="/section/detection/follow/none" hx-target="#performers-content" hx-swap="innerHTML">Stop following</button>
            % elif spot is not None:
                <button type="button" class="secondary small" hx-post="/section/detection/follow/{{p['marker_id']}}" hx-target="#performers-content" hx-swap="innerHTML">Follow</button>
            % end
            % end
            </td>
        </tr>
    % end
    </tbody>
</table>
% end
