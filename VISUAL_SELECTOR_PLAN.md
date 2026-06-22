# Visual Wafer Selector Plan

This document tracks the planned visual selection workflow for the wafer-map
exporter.

## Goal

Add a layered visual selector so the user can inspect the wafer layout and mark
clusters, bars, arrays, or dies to include before exporting the CSV.

## Selection Meaning

Selection means **include in export**.

Default behavior:

- All wafer positions are excluded by default.
- User-selected clusters/bars/arrays/dies are included.
- Export keeps the existing wafer filtering, then keeps only the user-included
  selections.

## Layered UI

Planned drill-down layers:

1. Wafer/cluster view
   - Show wafer circle.
   - Show cluster rectangles.
   - Click clusters to mark them for inclusion.
   - Drag a box to mark multiple clusters for inclusion.

2. Cluster/bar view
   - Zoom into one cluster.
   - Show bars.
   - Click bars to include whole bars.

3. Bar/array view
   - Zoom into one bar.
   - Show arrays.
   - Click arrays to include whole arrays.

4. Array/die view
   - Zoom into one array or visible die region.
   - Show dies and acceptor positions.
   - Single-click a die for fine correction.
   - Drag box to include or remove groups of dies from the included set.

## Current Cluster State

Current implementation supports real cluster-level export inclusion:

- File: `wafer_map_selector.py`
- Imported by: `Wafer_Map_GUI.py`
- Button: `Select clusters`, enabled after array and die settings are applied
- `main.build_clusters(...)` returns
  `dict[str, tuple[Cluster, ClusterWaferStatus]]`, keyed by labels such as
  `AB`.
- The GUI stores the built dictionary and passes it into the selector.
- Draws real cluster geometry from the stored dictionary.
- Allows clicking clusters to toggle them.
- Allows drag-box selection to mark multiple clusters for inclusion.
- Dragging from a selected cluster removes clusters from the included set.
- Uses persistent canvas items: resize updates coordinates, and selection only
  updates item styles.
- Stores selected labels in the selector.
- Returns the selected labels when the user clicks `Done`.
- The GUI keeps only those labels in its cluster dictionary.
- CSV export passes that selected cluster dictionary into `main.main(...)`.
- Reopening the selector rebuilds the complete cluster grid before drawing it.
- Double-clicking a cluster marks the future entry point for its bar selector.

## Recommended Next Implementation

Recommended changes:

1. Add a bar-selector file that receives the selected cluster's existing bars:

   ```python
   cluster.bars: dict[str, Bar]
   ```

2. Let the bar selector return a filtered dictionary:

   ```python
   dict[str, Bar]
   ```

   Then update the selected cluster's `bars` attribute with that filtered
   dictionary.

3. Add the same pattern for arrays:

   ```python
   bar.arrays: dict[str, Array]
   ```

4. Keep the existing serpentine CSV ordering after lower-layer inclusions are
   applied.

## Open Questions

- Should included items be blue and default-excluded items gray, or another
  color pairing?
- Should clicking toggle inclusion, or should the UI have explicit Include and
  Exclude modes?
- Should selections persist if geometry inputs change?
- Should inclusions be saved to a sidecar file for repeat use?
