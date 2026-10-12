%# The All Performers panel: each performer marker, whether it holds a person,
%# and which one each spotlight follows. With one spotlight its buttons read
%# Follow / Stop following; with several each button names its spot.
% performers = view.get('performers', [])
% spot = view.get('spotlight')
% spots = view.get('spotlights') or ([spot] if spot is not None else [])
% numbered = len(spots) > 1
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
            % followed_by = p.get('followed_by') or []
            % if numbered and followed_by:
            %     followed_text = ' - followed by ' + ' and '.join('Spot %d' % n for n in followed_by)
            % else:
            %     followed_text = ' - followed' if p['followed'] else ''
            % end
            <td>{{'Tracking a person' if p['tracking'] else 'No person'}}{{followed_text}}</td>
            <td class="row-actions">
            % for s in spots:
            %     number = s.get('number', 1)
            %     if number in followed_by or (not numbered and p['followed']):
                <button type="button" class="secondary small" hx-post="/section/detection/follow/none?spot={{number}}" hx-target="#performers-content" hx-swap="innerHTML">{{'Stop Spot %d' % number if numbered else 'Stop following'}}</button>
            %     else:
                <button type="button" class="secondary small" hx-post="/section/detection/follow/{{p['marker_id']}}?spot={{number}}" hx-target="#performers-content" hx-swap="innerHTML">{{'Spot %d' % number if numbered else 'Follow'}}</button>
            %     end
            % end
            </td>
        </tr>
    % end
    </tbody>
</table>
% end
