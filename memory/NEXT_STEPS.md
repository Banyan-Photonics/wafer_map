# Next Steps

This file tracks the current work queue. Keep it current when major work
finishes.

## Immediate Target

Implement die-level selection after array selection.

Recommended path:

1. Add die-level selection state to `Wafer`.
2. Create a real die selector using the current selector pattern.
3. Open it from right-click or Control-click in the array selector.
4. Pass the selected array's existing `array.dies` dictionary into it.
5. Export all available dies by default when no die selection record exists.
6. Keep serpentine export ordering in `main.py` unchanged.

## Then

1. Decide whether selection state should persist when geometry inputs change.
2. Decide whether to save selections to a sidecar file.

## Open Questions

- Should the UI use only click-to-toggle, or include explicit Include/Exclude
  modes?
- Should selected items always be blue and excluded/default items gray?
- How should the user navigate back up from bar, array, or die views?
- Should lower-level selections be visible as a summary on the cluster view?

## Maintenance Reminder

After finishing a feature:

1. Move completed items out of `Immediate Target`.
2. Add durable design choices to `DECISIONS.md`.
3. Update `PROJECT_CONTEXT.md` if the current state changed.
4. Leave detailed behavior in `README.md` or the appropriate memory file.
