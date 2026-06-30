# Decisions

This file records durable project decisions. Keep it short and update it when a
choice affects future implementation.

## D001 - Markdown Memory System

Use short Markdown files as the project memory system.

Reason:
- Transparent and easy to edit.
- Works across Codex sessions without relying on chat history.
- Appropriate for the current project size.

Implications:
- Start new sessions by reading `memory/MEMORY_INDEX.md`.
- Keep memory files under 200 lines.
- Archive only stable facts, rules, decisions, and next steps.

## D002 - Selection Means Include

Visual selection means the item should be included in export.

Reason:
- This is the selected design for the visual selector workflow.
- It gives a consistent behavior for clusters, bars, arrays, and dies.

Implications:
- Default unselected items are excluded.
- Future bar, array, and die selectors should use the same meaning.
- Drag selection should add or remove inclusion depending on gesture mode.

## D003 - GUI Builds Geometry Before Selection

The GUI builds the complete cluster grid before opening the visual selector.

Reason:
- Selectors should draw real geometry from the engine instead of duplicating
  wafer calculations.

Implications:
- `main.build_wafer(...)` remains the source of truth for wafer and cluster geometry.
- `wafer_map_selector.py` should stay focused on display and selection.
- Future selectors should receive existing `Cluster`, `Bar`, or `Array` data.

## D004 - CSV Labels Stay Compatible With Prober Workflow

CSV coordinate and size headers use `[um]`, but values remain millimeters.

Reason:
- The downstream workflow expects the `[um]` labels.
- The current numeric convention is millimeter-valued data.

Implications:
- Do not convert exported values to micrometers unless this decision changes.
- Keep the internal geometry fields labeled `[mm]`.
- Let the GUI writer map internal fields to public CSV headers.

## D005 - Export Filters Existing Object Trees From Selection State

Bar, array, and die selection should store label selections on `Wafer`; export
then builds filtered views from the existing object tree.

Reason:
- The user needs to reopen selectors and see/edit previous choices.
- The geometry tree should not be repeatedly rebuilt for selection changes.
- This keeps export compatible with existing flattening and serpentine sorting.

Implications:
- `Wafer.selected_cluster_labels` stores cluster inclusion.
- `Wafer.selected_bars_by_cluster` stores bar refinements.
- `Wafer.selected_arrays_by_bar` stores array refinements.
- Missing lower-level records mean include all available children at that level.
- Export preserves original footprint width and height when filtering children.

## D006 - Wafer Owns Selection State And Prepared Geometry

The GUI should store one top-level `Wafer` object. Prepared wafer geometry
should remain intact after user selection, while selected labels live on the
`Wafer`.

Reason:
- Users need to reopen selectors with previous choices highlighted.
- Future bar, array, and die selectors need prepared geometry for editing.
- Export can build a filtered view without destroying the source tree.

Implications:
- `main.build_wafer(...)` returns a `Wafer`.
- `WaferMapGUI.wafer` stores the current wafer object.
- `Wafer.selected_cluster_labels`, `Wafer.selected_bars_by_cluster`, and
  `Wafer.selected_arrays_by_bar` store selection state.
- `export_wafer(...)` derives the export cluster map from selected labels.

## D007 - Filter Available Arrays Once Before Selection

Fab Area and wafer-edge array filtering should run before visual selection and
only once for the current `Wafer`.

Reason:
- Users should not be able to select arrays that cannot be exported.
- Reopening the cluster selector should not redo destructive array filtering.

Implications:
- `filter_available_arrays_for_selection(wafer)` removes unavailable arrays in place.
- `Wafer.arrays_filtered` prevents repeat filtering on the same wafer object.
- Clusters with no available arrays are marked `"outside"` and are not
  selectable in the cluster selector.
- Export skips repeat array filtering when `Wafer.arrays_filtered` is true.

## D008 - Bar Selection Refines Selected Clusters

Bar selection is available only from clusters already selected for inclusion.

Reason:
- Bar selection is a refinement workflow for choosing specific bars.
- Selecting zero bars should not leave an apparently selected cluster that
  exports no data.

Implications:
- Right-click or Control-click opens bar selection only for currently selected
  clusters.
- If no bar selection record exists for a selected cluster, export includes all
  available bars in that cluster.
- The bar selector opens with no bars selected when no previous bar record
  exists.
- Saving zero selected bars unselects the cluster.

## D009 - Array Selection Refines Selected Bars

Array selection is available only from bars already selected for inclusion.

Reason:
- Array selection is a refinement workflow for choosing specific arrays.
- Selecting zero arrays should not leave an apparently selected bar that
  exports no data.

Implications:
- Right-click or Control-click opens array selection only for currently selected
  bars.
- If no array selection record exists for a selected bar, export includes all
  available arrays in that bar.
- The array selector opens with no arrays selected when no previous array
  record exists.
- Saving zero selected arrays unselects the bar. If that leaves the cluster
  with zero selected bars, the cluster is unselected too.
