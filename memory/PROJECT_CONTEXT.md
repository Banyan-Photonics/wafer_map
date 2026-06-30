# Project Context

## Goal

Build a Tkinter wafer-map CSV exporter for wafer probing workflows.

The application reads an Excel array-position table, builds wafer geometry,
lets the user visually choose what should be included, and exports a CSV for
downstream probing or measurement scripts.

## Current State

- The main GUI runs from `Wafer_Map_GUI.py`.
- The geometry engine lives in `main.py`.
- XLSX reading is handled by `xlsx_reader.py`.
- Real cluster-level visual selection is implemented in `wafer_map_selector.py`.
- Real bar-level visual selection is implemented in `bar_selector_demo.py`.
- Real array-level visual selection is implemented in `array_selector.py`.
- The visual-selection roadmap is tracked in `NEXT_STEPS.md` and `DECISIONS.md`.
- The GUI stores a top-level `Wafer` object containing prepared geometry plus
  selected cluster, bar, and array labels.

## Main Workflow

1. User chooses an `.xlsx` workbook.
2. The workbook must contain a sheet named `Cluster`.
3. User applies array settings and die settings.
4. The app builds a complete `Wafer` with a labeled cluster grid.
5. The `Wafer` filters unavailable arrays once before visual selection.
6. The user opens the cluster selector.
7. Selected cluster labels are stored on the `Wafer`.
8. The user can right-click or Control-click a selected cluster to refine bars.
9. The user can right-click or Control-click a selected bar to refine arrays.
10. Export derives a filtered view from the selected clusters, bars, and arrays.
11. Export rows are sorted in serpentine probe order.
12. The GUI writes metadata rows and die rows to CSV.

## Core Architecture

- `Wafer_Map_GUI.py`
  - Owns Tkinter UI, file paths, user inputs, metadata, cluster selection, and
    CSV writing.
- `main.py`
  - Owns the `Wafer` object, geometry objects, wafer generation, wafer filtering, Fab Area
    exclusion, die-row flattening, and serpentine sorting.
- `wafer_map_selector.py`
  - Draws real clusters from `main.build_wafer(...).clusters`.
  - Lets the user click or drag to include clusters.
  - Opens bar selection from right-click or Control-click on selected clusters.
- `bar_selector_demo.py`
  - Contains the real `BarSelector`.
  - Still contains the standalone `BarSelectorDemo` visual test.
- `array_selector.py`
  - Contains the real `ArraySelector`.
- `xlsx_reader.py`
  - Reads `.xlsx` files directly from workbook XML into row dictionaries.

## Important Vocabulary

- Cluster: one repeated wafer-grid footprint containing bars.
- Bar: one horizontal row inside a cluster.
- Array: one slot inside a bar.
- Die: one or more devices inside an array.
- Acceptor: the circle or rectangle geometry used for center coordinates and
  wafer-edge availability checks.

## Detailed Docs

- Use `README.md` for full input/output behavior and user-facing explanations.
- Use `NEXT_STEPS.md` and `DECISIONS.md` for visual selector direction.
