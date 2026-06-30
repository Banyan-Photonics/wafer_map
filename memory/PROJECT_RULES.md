# Project Rules

## Selection Rules

- Selection means include in export.
- Default state is excluded.
- User-selected clusters, bars, arrays, or dies are included.
- Current implementation supports cluster-, bar-, and array-level inclusion.
- Die-level selection should follow the same include-by-selection pattern.
- Selected cluster with no bar selection record includes all available bars.
- Selected bar with no array selection record includes all available arrays.
- Saving zero bars unselects the cluster.
- Saving zero arrays unselects the bar; if no selected bars remain, the cluster
  is unselected too.

## XLSX Input Rules

- Input must be an `.xlsx` workbook.
- Required worksheet name is exactly `Cluster`.
- First row is the header row.
- One header must be `Array position`.
- Numeric `Array position` rows become physical bar rows.
- Non-numeric `Array position` rows are ignored by geometry generation.
- Every other column is treated as an array slot.
- Blank cells are valid array slots with blank `Array detail`.

## Geometry Rules

- Coordinate units are millimeters internally.
- Wafer center is `(0, 0)`.
- Positive X points right.
- Positive Y points up.
- Moving down from a top-left point subtracts from Y.
- `width` always means X-direction dimension.
- `height` always means Y-direction dimension.
- Wafer diameter is entered in inches in the GUI and converted to millimeters.

## Array And Die Rules

- Array width includes both side margins.
- Array side is half of the Cluster Cleave Street.
- Die width is `(array_width - 2 * array_side) / dies_per_array`.
- Dies per array must be `1`, `2`, or `4`.
- Acceptor shape is `circle` or `rectangle`.
- Circle deltas point from die top-left to circle center.
- Rectangle deltas point from die top-left to rectangle top-left.
- Acceptor must be symmetric in X inside the die.

## Fab Area Rules

- Fab Area markers exclude occupied array/bar slots from export.
- Required marker format is `Fab Area (<width>mm x <height>mm)`.
- The first number is X-direction width.
- The second number is Y-direction height.
- Physical Fab Area dimensions are rounded up to whole array/bar slots.

## CSV Export Rules

- Metadata rows appear before the data table.
- Exported data headers use `[um]` labels for downstream compatibility.
- Numeric coordinate and size values remain millimeters.
- Do not multiply exported coordinates or sizes by `1000`.
- Die IDs use bar number, array label, and die number, such as `24J1`.
- Export rows are sorted in serpentine probe order.

## Coding Rules

- Preserve existing geometry contracts when adding selectors.
- Keep GUI selection state separate from geometry generation.
- Use existing `Cluster`, `Bar`, `Array`, and `Die` objects where possible.
- Do not rebuild unrelated project structure while implementing selector layers.
