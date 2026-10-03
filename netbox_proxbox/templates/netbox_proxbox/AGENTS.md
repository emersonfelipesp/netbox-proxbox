# Template Guide

Templates inherit NetBox layout, permission, accessibility, and escaping
conventions. Do not render plaintext secrets or internal deployment details.
Operational controls must be hidden or disabled when the user lacks the exact
permission, while server-side views enforce the same permission independently.

Links opened in a new tab use `rel="noopener noreferrer"`. Interactive behavior
must tolerate missing optional data and must not weaken server-side validation.
Add template-rendering or source-contract coverage for new controls and states.
