# Wafer Map CSV Exporter

This project generates wafer-map CSV files from an Excel array-position table.
The exported CSV can be used as a coordinate list for wafer probing or downstream
measurement scripts.

## Main Files

- `Wafer_Map_GUI.py` - Tkinter GUI for selecting an XLSX file, entering wafer
  geometry, and exporting a wafer-map CSV.
- `main.py` - wafer-map geometry engine. It builds clusters, bars, arrays, dies,
  and filters out positions outside the wafer.
- `xlsx_reader.py` - lightweight XLSX reader used by the geometry engine.
- `WP motion and function.py` - separate ElectroGlas 2001 prober script that
  consumes a wafer-map CSV and moves/measures hardware.

## Starting the GUI

Run:

```bash
python3 Wafer_Map_GUI.py
```

The GUI opens as **Wafer Map CSV Exporter**.

## XLSX Input Requirements

The input file must be an `.xlsx` workbook.

The required worksheet name is exactly:

```text
Cluster
```

The first row of the `Cluster` sheet must be the header row. One header must be:

```text
Array position
```

Every other column is treated as an array label. The wafer-map geometry is read
from the actual table shape.

Common array headers are:

```text
A, B, C, D, E, F, G, H, I, J
```

Example sheet:

```csv
Array position,A,B,C,D,E,F,G,H,I,J
1,D01,D01,D01,D01,D01,D01,Fab Area (2.1mm x 0.5mm),'','',''
2,D01,D01,D01,D01,D01,D01,'','','',''
3,D01,D01,D01,D01,D01,D01,D01,D01,D01,D01
4,D02,D02,D02,D02,D02,D02,D02,D02,D02,D02
```

Rows where `Array position` is numeric become physical bar rows. Rows where
`Array position` is not numeric are ignored. The number of numeric rows controls
how many bars are used in one cluster, and the number of non-`Array position`
columns controls how many arrays are used in each bar.

Each data cell becomes the exported `Array detail` value for that array slot.
Blank cells are still treated as array slots, but the exported `Array detail`
will be blank.

## Fab Area Markers

To exclude fabrication-area regions, put a marker in the upper-left occupied
array slot:

```text
Fab Area (<width>mm x <height>mm)
```

Valid examples:

```text
Fab Area (2.1mm x 0.5mm)
Fab Area (2.1 mm x 0.5 mm)
```

The first number is the X-direction width. The second number is the Y-direction
height. The program converts that physical area into whole array/bar slots and
excludes those positions from export.

## GUI Fields

### Main Window

- **XLSX file** - source workbook containing the `Cluster` sheet.
- **CSV export** - output path for the generated wafer-map CSV.
- **Wafer diameter [in]** - wafer diameter entered in inches. The geometry engine
  converts this to millimeters internally.
- **Select clusters** - after applying array and die settings, build the
  labeled cluster dictionary and open the wafer view to choose which clusters
  to include in CSV export.
- **Header meta** - metadata written at the top of the CSV:
  - `ID_PROJECT`
  - `ID_BATCH`
  - `ID_WAFER`
  - `WAFER_ROTATION`
  - `TEST_STRUCTURE`
  - `LINES_DATA`

`TILE_WIDTH` and `TILE_HEIGHT` are calculated automatically from the array
settings.

For the current 10-array by 42-bar cluster table, `TILE_WIDTH` is calculated as
`array_width * 10`, and `TILE_HEIGHT` is calculated as `array_height * 42`.

### Array Settings

- **Array width [mm]** - full X-direction width of one array, including side
  margins.
- **Array height [mm]** - Y-direction die/bar height used for vertical spacing
  and exported `height[mm]`.
- **Array side [mm]** - half of the Cluster Cleave Street. This is the
  X-direction side spacing before the first die and after the last die in each
  array pitch.

The die width is calculated as:

```text
(array width - 2 * array side) / dies per array
```

### Die Settings

- **Dies per array** - must be `1`, `2`, or `4`.
- **Acceptor shape** - `circle` or `rectangle`.
- **Circle acceptor diameter [mm]** - used when the acceptor is circular.
- **Rectangle acceptor width/height [mm]** - used when the acceptor is
  rectangular.
- **Circle center delta X/Y [mm]** - for circular acceptors, offset from the full
  die top-left corner to the circle center.
- **Rect top-left delta X/Y [mm]** - for rectangular acceptors, offset from the
  full die top-left corner to the rectangle top-left corner.

The acceptor must be symmetric in X inside the die. In practice, the acceptor
center X must equal half the die width.

## Exported CSV Format

The exported CSV starts with metadata rows:

```csv
ID_PROJECT,<value>
ID_BATCH,<value>
ID_WAFER,<value>
WAFER_ROTATION,<value>
TILE_WIDTH,<calculated value>
TILE_HEIGHT,<calculated value>
TEST_STRUCTURE,<value>
LINES_DATA,<value>
```

Then the data table is written with these columns:

```csv
tile_id,die_id,xc_ref[um],yc_ref[um],xc_chip[um],yc_chip[um],width[um],height[um],Array detail
```

Important unit convention: the coordinate and size headers are intentionally
labeled with `[um]` for compatibility with the downstream prober workflow, but
the numeric data values are still millimeters. The exporter does not multiply
coordinates or sizes by `1000`.

For example, a die width of `0.25` mm is written as:

```csv
width[um]
0.25
```

not:

```csv
width[um]
250
```

## How Positions Are Generated

The geometry engine:

1. Reads the `Cluster` sheet from the XLSX file.
2. Uses numeric `Array position` rows as bar rows.
3. Treats each array column as an array slot.
4. Places dies inside each array using the entered geometry.
5. Builds a square cluster grid centered on wafer coordinate `(0, 0)`.
6. Removes clusters fully outside the wafer.
7. Filters edge arrays using the acceptor point closest to the wafer edge.
8. Removes any slots covered by `Fab Area` markers.
9. Exports one row per selected die.

Cluster labels are generated in row/column form, such as `AA`, `AB`, `AC`.
Die IDs are generated from bar number, array label, and die number, such as
`24J1`.
