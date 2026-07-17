#!/usr/bin/env python3
"""
Created on Fri May 8th 2026

@author: Steven Li

=======================================================

Tkinter GUI for exporting wafer-map CSV files from an XLSX array table."""

from __future__ import annotations

import csv
import threading
from pathlib import Path
from tkinter import Tk, StringVar, Toplevel, filedialog, messagebox
from tkinter import ttk

from main import Wafer, build_wafer, export_wafer, filter_available_arrays_for_selection
from wafer_map_selector import ClusterSelector
from xlsx_reader import read_xlsx_as_dicts


MILLIMETERS_PER_INCH = 25.4
DEFAULT_SHEET_NAME = "Cluster"


#GeometrySettings = dict[str, float | int | str]

CSV_METADATA_FIELDS = [
    "ID_PROJECT",
    "ID_BATCH",
    "ID_WAFER",
    "WAFER_ROTATION",
    "TILE_WIDTH",
    "TILE_HEIGHT",
    "TEST_STRUCTURE",
    "LINES_DATA",
]

EDITABLE_METADATA_FIELDS = [
    "ID_PROJECT",
    "ID_BATCH",
    "ID_WAFER",
    "WAFER_ROTATION",
    "TEST_STRUCTURE",
    "LINES_DATA",
]

# Keys used to read values from the geometry engine's export rows. These are
# not necessarily the labels written to the final CSV header.
CSV_DATA_FIELDNAMES = [
    "tile_id",
    "die_id",
    "xc_ref[mm]",
    "yc_ref[mm]",
    "xc_chip[mm]",
    "yc_chip[mm]",
    "width[mm]",
    "height[mm]",
    "Array detail",
]

# Public CSV labels requested by the prober workflow. These labels say
# micrometers even though values are copied from millimeter-valued fields.
CSV_DATA_HEADERS = [
    "tile_id",
    "die_id",
    "xc_ref[um]",
    "yc_ref[um]",
    "xc_chip[um]",
    "yc_chip[um]",
    "width[um]",
    "height[um]",
    "Array detail",
]


def write_export_csv(
        export_rows: list[dict[str, str | float]],
        output_path: Path,
        header_meta: dict[str, str],
) -> None:
    """Write the GUI export format with metadata above the data.

    The CSV data headers intentionally label coordinate and size columns as
    micrometers, but the row values are written directly from the millimeter
    values produced by the geometry engine.
    """
    with output_path.open("w", newline="") as csv_file:
        # Write the eight header-meta rows before the actual data table.
        writer = csv.writer(csv_file)
        for field in CSV_METADATA_FIELDS:
            writer.writerow([field, header_meta.get(field, "")])

        # Write micrometer-labeled headers, then copy the millimeter values
        # without converting them.
        writer.writerow(CSV_DATA_HEADERS)
        for row in export_rows:
            writer.writerow([row.get(field, "") for field in CSV_DATA_FIELDNAMES])


class WaferMapGUI:
    """Small Tkinter app for selecting an XLSX file and exporting the CSV."""

    def __init__(self, root: Tk) -> None:
        """Initialize shared GUI state and build the main window."""
        # ======== Root and file paths ========
        self.root = root
        default_input_path = Path(__file__).with_name("array_position_table.xlsx")
        self.input_path = StringVar(value=str(default_input_path))
        #self.output_path = StringVar(value=str(default_input_path.with_suffix(".csv"))) #FA 2026-07-17: COMMENTED OUT, REPLACED BY THE LINE BELOW. !!DELETE!! ONCE FUNCTIONALITY IS CONFIRMED
        self.output_directory = StringVar(value=str(default_input_path.parent)) #FA 2026-07-17: CHANGED THE CSV EXPORT FIELD TO ACCEPT A DIRECTORY RATHER THAN HAVINT TO SPECIFY FILE NAME

        # ======== Applied geometry settings ========
        # Store validated application state as numbers. StringVars are only
        # used at editable widget boundaries.
        self.wafer_diameter_text = StringVar(value="3.0")
        self.array_width: float = 1.05
        self.array_height: float = 0.25
        self.array_side: float = 0.025
        self.dies_per_array: int = 4
        self.acceptance_shape: str = "circle"
        self.circle_acceptor_diameter: float = 0.016
        self.rectangle_acceptor_width: float | None = None
        self.rectangle_acceptor_height: float | None = None
        self.acceptance_delta_x: float = 0.125
        self.acceptance_delta_y: float = 0.0725

        # ======== Header metadata ========
        self.header_meta = {
            field: StringVar()
            for field in EDITABLE_METADATA_FIELDS
        }

        # ======== GUI state ========
        self.status = StringVar(value="Select an XLSX file to begin.")
        self.wafer: Wafer | None = None
        self.array_settings_applied = False
        self.die_settings_applied = False
        self.input_path.trace_add("write", self._invalidate_clusters)
        self.wafer_diameter_text.trace_add("write", self._invalidate_clusters)

        # Configure the main window before creating widgets.
        self.root.title("Wafer Map CSV Exporter")
        self.root.geometry("760x640")
        self.root.minsize(680, 600)

        self._build_layout()

    def _build_layout(self) -> None:
        """Build the main file, geometry, metadata, and export controls."""
        # ======== Main frame ========
        self.root.columnconfigure(0, weight=1)

        frame = ttk.Frame(self.root, padding=18)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(1, weight=1)

        # ======== Input and output files ========
        ttk.Label(frame, text="XLSX file").grid(row=0, column=0, sticky="w", padx=(0, 10))
        ttk.Entry(frame, textvariable=self.input_path).grid(row=0, column=1, sticky="ew")
        ttk.Button(frame, text="Browse", command=self._select_input).grid(
            row=0,
            column=2,
            padx=(10, 0),
        )

        # ttk.Label(frame, text="CSV export").grid(row=1, column=0, sticky="w", padx=(0, 10),
        #                                          pady=(12, 0)) #FA 2026-07-17: COMMENTED OUT AND REPLACED WITH BELOW. !!DELETE!! ONCE FUNCTIONALITY IS CONFIRMED
        
        ttk.Label(frame, text="Export folder").grid(row=1, column=0, sticky="w", padx=(0, 10),
                                         pady=(12, 0)) #FA 2026-07-17: SETS FIELD FOR EXPORT FOLDER ON LEFT OF STRING BOX
        
        # ttk.Entry(frame, textvariable=self.output_path).grid(row=1, column=1, sticky="ew",
        #                                                      pady=(12, 0)) #FA 2026-07-17: COMMENTED OUT AND REPLACED WITH BELOW. !!DELETE!! ONCE FUNCTIONALITY IS CONFIRMED
        
        ttk.Entry(frame, textvariable=self.output_directory).grid(row=1, column=1, sticky="ew",
                                                             pady=(12, 0)) #FA 2026-07-17: SETS THE CSV SAVE PATH
        
        # ttk.Button(frame, text="Save As", command=self._select_output).grid( #FA 2026-07-17: COMMENTED OUT AND REPLACED WITH BELOW. !!DELETE!! ONCE FUNCTIONALITY IS CONFIRMED
        ttk.Button(frame, text="Browse", command=self._select_output).grid( #FA 2026-07-17: SAVE AS DIRECTORY BUTTON
            row=1,
            column=2,
            padx=(10, 0),
            pady=(12, 0),
        )

        # ======== Geometry controls ========
        ttk.Label(frame, text="Wafer diameter [in]").grid(
            row=2,
            column=0,
            sticky="w",
            padx=(0, 10),
            pady=(12, 0),
        )
        ttk.Entry(frame, textvariable=self.wafer_diameter_text, width=18).grid(
            row=2,
            column=1,
            sticky="w",
            pady=(12, 0),
        )

        # Additional geometry controls live in popups to keep the main window
        # focused on file selection, wafer diameter, metadata, and export.
        ttk.Button(frame, text="Array settings", command=self._open_array_settings_popup).grid(
            row=3,
            column=1,
            sticky="w",
            pady=(12, 0),
        )

        ttk.Button(frame, text="Die settings", command=self._open_die_settings_popup).grid(
            row=4,
            column=1,
            sticky="w",
            pady=(12, 0),
        )

        self.cluster_selector_button = ttk.Button(
            frame,
            text="Select clusters",
            command=self._open_cluster_selector,
            state="disabled",
        )
        self.cluster_selector_button.grid(
            row=5,
            column=1,
            sticky="w",
            pady=(12, 0),
        )

        # ======== Header metadata ========
        meta_frame = ttk.LabelFrame(frame, text="Header meta", padding=12)
        meta_frame.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(18, 0))
        meta_frame.columnconfigure(1, weight=1)
        meta_frame.columnconfigure(3, weight=1)

        for index, field in enumerate(EDITABLE_METADATA_FIELDS):
            row = index // 2
            label_column = (index % 2) * 2
            entry_column = label_column + 1
            ttk.Label(meta_frame, text=field).grid(
                row=row,
                column=label_column,
                sticky="w",
                padx=(0, 8),
                pady=4,
            )
            ttk.Entry(meta_frame, textvariable=self.header_meta[field]).grid(
                row=row,
                column=entry_column,
                sticky="ew",
                padx=(0, 14),
                pady=4,
            )

        # ======== Export and status ========
        self.export_button = ttk.Button(
            frame,
            text="Export CSV",
            command=self._start_export,
            state="disabled",
        )
        self.export_button.grid(row=7, column=2, sticky="e", pady=(22, 0))

        ttk.Separator(frame).grid(row=8, column=0, columnspan=3, sticky="ew", pady=(18, 12))
        ttk.Label(frame, textvariable=self.status).grid(row=9, column=0, columnspan=3, sticky="w")

    def _open_array_settings_popup(self) -> None:
        """Open the modal popup for array pitch and spacing inputs."""
        # ======== Popup setup ========
        popup = Toplevel(self.root)
        popup.title("Array settings")
        popup.resizable(False, False)
        popup.transient(self.root)
        popup.grab_set()

        frame = ttk.Frame(popup, padding=16)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(1, weight=1)

        # ======== Helper dialog ========
        def show_array_helper() -> None:
            """Show explanatory text for the array geometry fields."""
            messagebox.showinfo(
                "Array setting helper",
                "\n".join(
                    [
                        "- Width is X; height is Y.",
                        "- Array side is This is the X-direction side spacing before the first die."
                        "- One array pitch is: array side + dies + array side.",
                        "- Array width must be greater than 2 x array side.",
                        "- Die width = (array width - 2 x array side) / dies per array.",
                    ]
                ),
                parent=popup,
            )

        ttk.Button(
            frame,
            text="Helper",
            command=show_array_helper,
        ).grid(row=0, column=2, sticky="ne", padx=(24, 0))

        # ======== Temporary entry values ========
        # Local StringVars let users cancel without changing the main state.
        array_width_value = StringVar(value=str(self.array_width))
        array_height_value = StringVar(value=str(self.array_height))
        array_side_value = StringVar(value=str(self.array_side))

        # ======== Array fields ========
        ttk.Label(frame, text="Array width [mm]").grid(
            row=0,
            column=0,
            sticky="w",
            padx=(0, 10),
        )
        ttk.Entry(frame, textvariable=array_width_value, width=18).grid(
            row=0,
            column=1,
            sticky="ew",
        )
        ttk.Label(frame, text="Array height [mm]").grid(row=1, column=0, sticky="w", padx=(0, 10),
                                                        pady=(10, 0))
        ttk.Entry(frame, textvariable=array_height_value, width=18).grid(row=1, column=1,
                                                                         sticky="ew", pady=(10, 0))
        ttk.Label(frame, text="Array side [mm]").grid(
            row=2,
            column=0,
            sticky="w",
            padx=(0, 10),
            pady=(10, 0),
        )
        ttk.Entry(frame, textvariable=array_side_value, width=18).grid(
            row=2,
            column=1,
            sticky="ew",
            pady=(10, 0),
        )

        # ======== Apply or cancel ========
        button_frame = ttk.Frame(frame)
        button_frame.grid(row=3, column=0, columnspan=2, sticky="e", pady=(18, 0))

        def apply_values() -> None:
            """Validate and apply array settings from the popup."""
            try:
                # Validate popup values before copying them back to the main
                # window state.
                array_width = self._number_from_entry(array_width_value, "Array width")
                array_height = self._number_from_entry(array_height_value, "Array height")
                array_side = self._number_from_entry(array_side_value, "Array side")
            except ValueError as exc:
                messagebox.showerror("Array settings", str(exc), parent=popup)
                return

            # Apply validated popup values to the shared GUI state.
            self.array_width = array_width
            self.array_height = array_height
            self.array_side = array_side
            self.array_settings_applied = True
            self._invalidate_clusters()
            popup.destroy()

        ttk.Button(button_frame, text="Cancel", command=popup.destroy).grid(row=0, column=0,
                                                                            padx=(0, 8))
        ttk.Button(button_frame, text="Apply", command=apply_values).grid(row=0, column=1)

    def _open_die_settings_popup(self) -> None:
        """Open the modal popup for die count and acceptor inputs."""
        # ======== Popup setup ========
        popup = Toplevel(self.root)
        popup.title("Die settings")
        popup.resizable(False, False)
        popup.transient(self.root)
        popup.grab_set()

        frame = ttk.Frame(popup, padding=16)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(1, weight=1)

        # ======== Helper dialog ========
        def show_die_helper() -> None:
            """Show explanatory text for the die and acceptor fields."""
            messagebox.showinfo(
                "Die setting helper",
                "\n".join(
                    [
                        "- Deltas start at the full die top-left corner.",
                        "- Circle delta X/Y points to the circle center.",
                        "- Rectangle delta X/Y points to the rectangle top-left.",
                        "- Acceptor must be symmetric from left/right die sides.",
                        "- Dies per array must be 1, 2, or 4.",
                    ]
                ),
                parent=popup,
            )

        ttk.Button(
            frame,
            text="Helper",
            command=show_die_helper,
        ).grid(row=0, column=2, sticky="ne", padx=(24, 0))

        # ======== Temporary entry values ========
        # Local StringVars let users cancel without changing the main state.
        dies_per_array_value = StringVar(value=str(self.dies_per_array))
        shape_value = StringVar(value=self.acceptance_shape)
        circle_diameter_value = StringVar(value=str(self.circle_acceptor_diameter))
        rectangle_width_value = StringVar(
            value="" if self.rectangle_acceptor_width is None
            else str(self.rectangle_acceptor_width)
        )
        rectangle_height_value = StringVar(
            value="" if self.rectangle_acceptor_height is None
            else str(self.rectangle_acceptor_height)
        )
        delta_x_value = StringVar(value=str(self.acceptance_delta_x))
        delta_y_value = StringVar(value=str(self.acceptance_delta_y))

        # ======== Die and acceptor fields ========
        ttk.Label(frame, text="Dies per array").grid(row=0, column=0, sticky="w", padx=(0, 10))
        ttk.Combobox(
            frame,
            textvariable=dies_per_array_value,
            values=("1", "2", "4"),
            state="readonly",
            width=16,
        ).grid(row=0, column=1, sticky="ew")

        ttk.Separator(frame).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(16, 12))
        ttk.Label(frame, text="Acceptor shape").grid(row=2, column=0, sticky="w", padx=(0, 10))
        shape_select = ttk.Combobox(
            frame,
            textvariable=shape_value,
            values=("circle", "rectangle"),
            state="readonly",
            width=16,
        )
        shape_select.grid(row=2, column=1, sticky="ew")

        circle_diameter_label = ttk.Label(frame, text="Circle acceptor diameter [mm]")
        circle_diameter_label.grid(row=3, column=0, sticky="w", padx=(0, 10), pady=(10, 0))
        circle_diameter_entry = ttk.Entry(frame, textvariable=circle_diameter_value, width=18)
        circle_diameter_entry.grid(row=3, column=1, sticky="ew", pady=(10, 0))

        rectangle_width_label = ttk.Label(frame, text="Rectangle acceptor width [mm]")
        rectangle_width_label.grid(row=4, column=0, sticky="w", padx=(0, 10), pady=(10, 0))
        rectangle_width_entry = ttk.Entry(frame, textvariable=rectangle_width_value, width=18)
        rectangle_width_entry.grid(row=4, column=1, sticky="ew", pady=(10, 0))

        rectangle_height_label = ttk.Label(frame, text="Rectangle acceptor height [mm]")
        rectangle_height_label.grid(row=5, column=0, sticky="w", padx=(0, 10), pady=(10, 0))
        rectangle_height_entry = ttk.Entry(frame, textvariable=rectangle_height_value, width=18)
        rectangle_height_entry.grid(row=5, column=1, sticky="ew", pady=(10, 0))

        delta_x_label = ttk.Label(frame)
        delta_x_label.grid(row=6, column=0, sticky="w", padx=(0, 10), pady=(10, 0))
        ttk.Entry(frame, textvariable=delta_x_value, width=18).grid(row=6, column=1, sticky="ew",
                                                                    pady=(10, 0))
        delta_y_label = ttk.Label(frame)
        delta_y_label.grid(row=7, column=0, sticky="w", padx=(0, 10), pady=(10, 0))
        ttk.Entry(frame, textvariable=delta_y_value, width=18).grid(row=7, column=1,
                                                                    sticky="ew", pady=(10, 0))

        # ======== Shape-dependent field visibility ========
        def update_delta_labels() -> None:
            """Update visible acceptor fields for circle vs rectangle mode."""
            # The delta labels depend on whether the point refers to a circle
            # center or a rectangle top-left corner.
            if shape_value.get() == "rectangle":
                circle_diameter_label.grid_remove()
                circle_diameter_entry.grid_remove()
                rectangle_width_label.grid()
                rectangle_width_entry.grid()
                rectangle_height_label.grid()
                rectangle_height_entry.grid()
                delta_x_label.configure(text="Rect top-left delta X [mm]")
                delta_y_label.configure(text="Rect top-left delta Y [mm]")
            else:
                circle_diameter_label.grid()
                circle_diameter_entry.grid()
                rectangle_width_label.grid_remove()
                rectangle_width_entry.grid_remove()
                rectangle_height_label.grid_remove()
                rectangle_height_entry.grid_remove()
                delta_x_label.configure(text="Circle center delta X [mm]")
                delta_y_label.configure(text="Circle center delta Y [mm]")

        def shape_changed(_event: object | None = None) -> None:
            """Clear shape-specific values when the acceptor shape changes."""
            # Clear stale values when the meaning of the delta fields changes.
            delta_x_value.set(str(""))
            delta_y_value.set(str(""))
            circle_diameter_value.set(str(""))
            rectangle_width_value.set(str(""))
            rectangle_height_value.set(str(""))
            update_delta_labels()

        shape_select.bind("<<ComboboxSelected>>", shape_changed)
        update_delta_labels()

        # ======== Apply or cancel ========
        button_frame = ttk.Frame(frame)
        button_frame.grid(row=8, column=0, columnspan=2, sticky="e", pady=(18, 0))

        def apply_values() -> None:
            """Validate and apply die settings from the popup."""
            try:
                # Validate popup values before copying them back to the main
                # window state.
                acceptor_shape = shape_value.get()
                if acceptor_shape == "circle":
                    circle_acceptor_diameter = self._number_from_entry(
                        circle_diameter_value,
                        "Circle acceptor diameter",
                    )
                else:
                    rectangle_acceptor_width = self._number_from_entry(
                        rectangle_width_value,
                        "Rectangle acceptor width",
                    )
                    rectangle_acceptor_height = self._number_from_entry(
                        rectangle_height_value,
                        "Rectangle acceptor height",
                    )
                acceptance_delta_x = self._number_from_entry(
                    delta_x_value,
                    "Acceptance delta X",
                )
                acceptance_delta_y = self._number_from_entry(
                    delta_y_value,
                    "Acceptance delta Y",
                )
            except ValueError as exc:
                messagebox.showerror("Die settings", str(exc), parent=popup)
                return

            # Apply validated popup values to the shared GUI state.
            self.dies_per_array = int(dies_per_array_value.get())
            self.acceptance_shape = acceptor_shape
            if acceptor_shape == "circle":
                self.circle_acceptor_diameter = circle_acceptor_diameter
            else:
                self.rectangle_acceptor_width = rectangle_acceptor_width
                self.rectangle_acceptor_height = rectangle_acceptor_height
            self.acceptance_delta_x = acceptance_delta_x
            self.acceptance_delta_y = acceptance_delta_y
            self.die_settings_applied = True
            self._invalidate_clusters()
            popup.destroy()

        ttk.Button(button_frame, text="Cancel", command=popup.destroy).grid(row=0, column=0,
                                                                            padx=(0, 8))
        ttk.Button(button_frame, text="Apply", command=apply_values).grid(row=0, column=1)

    def _select_input(self) -> None:
        """Prompt the user for the source XLSX workbook."""
        # Let the user choose the source workbook.
        selected = filedialog.askopenfilename(
            title="Select array position XLSX",
            filetypes=[("Excel workbook", "*.xlsx"), ("All files", "*.*")],
        )
        if not selected:
            return

        # Store the chosen input and suggest a matching CSV path if the user
        # has not already selected one.
        input_path = Path(selected)
        self.input_path.set(str(input_path))

        # if not self.output_path.get():
        #     self.output_path.set(str(input_path.with_suffix(".csv"))) #FA 2026-07-17: COMMENTED OUT AND REPLACED WITH BELOW. !!DELETE!! ONCE FUNCTIONALITY IS CONFIRMED
        
        if not self.output_directory.get():
            self.output_directory.set(str(input_path.parent)) #FA 2026-07-17: SETS A DEFAULT LOCATION INSTEAD OF A CSV INCASE NON IS SELECTED

        if self.array_settings_applied and self.die_settings_applied:
            self.status.set("Input selected. Select clusters to rebuild the wafer map.")
        else:
            self.status.set("Input selected. Apply array and die settings before selecting clusters.")

    # def _select_output(self) -> None: #FA 2026-07-17: COMMENTED OUT AND REPLACED WITH BELOW. !!DELETE!! ONCE FUNCTIONALITY IS CONFIRMED
    #     """Prompt the user for the output CSV path."""
    #     # Start the save dialog near the selected input workbook when possible.
    #     initial_dir = Path(self.input_path.get()).parent if self.input_path.get() else Path.cwd()
    #     selected = filedialog.asksaveasfilename(
    #         title="Save wafer map CSV",
    #         defaultextension=".csv",
    #         initialdir=initial_dir,
    #         filetypes=[("CSV file", "*.csv"), ("All files", "*.*")],
    #     )
    #     if selected:
    #         self.output_path.set(selected)
    #         if (
    #                 self.wafer is not None
    #                 and self.wafer.has_selected_clusters()
    #                 and self.export_button.instate(["!disabled"])
    #         ):
    #             self.status.set("Ready to export selected clusters.")
    
    def _select_output(self) -> None: #FA 2026-07-17: SELECTS A FOLDER INSTEAD OF A FILENAME
        """Prompt the user for the output folder."""
        # Start the browse dialog near the selected input workbook when possible.
        initial_dir = (
            self.output_directory.get()
            or (Path(self.input_path.get()).parent if self.input_path.get() else str(Path.cwd()))
        )
        selected = filedialog.askdirectory(
            title="Select export folder",
            initialdir=initial_dir,
        )
        if selected:
            self.output_directory.set(selected)
            if (
                    self.wafer is not None
                    and self.wafer.has_selected_clusters()
                    and self.export_button.instate(["!disabled"])
            ):
                self.status.set("Ready to export selected clusters.")

    def _invalidate_clusters(self, *_args: object) -> None:
        """Clear built clusters after a geometry input changes."""
        self.wafer = None

        if hasattr(self, "cluster_selector_button"):
            self._update_cluster_selector_state()
        if hasattr(self, "export_button"):
            self.export_button.configure(state="disabled")
        if hasattr(self, "status"):
            if self.array_settings_applied and self.die_settings_applied:
                self.status.set("Geometry changed. Select clusters to rebuild the wafer map.")
            else:
                self.status.set("Apply array and die settings before selecting clusters.")

    def _update_cluster_selector_state(self) -> None:
        """Enable cluster selection only after both settings popups are applied."""
        state = (
            "normal"
            if self.array_settings_applied and self.die_settings_applied
            else "disabled"
        )
        self.cluster_selector_button.configure(state=state)

    def _build_cluster_data(self) -> bool:
        """Build and store labeled clusters immediately before selection."""
        if self.wafer is not None:
            try:
                filter_available_arrays_for_selection(self.wafer)
            except ValueError as exc:
                messagebox.showerror("Select clusters", str(exc))
                return False
            self.export_button.configure(
                state="normal" if self.wafer.has_selected_clusters() else "disabled"
            )
            return True

        try:
            input_path = self._validated_input_path()
            wafer_diameter_inches = self._number_from_entry(
                self.wafer_diameter_text,
                "Wafer diameter",
            )
            wafer_diameter = wafer_diameter_inches * MILLIMETERS_PER_INCH
            geometry_settings = self._geometry_settings()
            array_table = read_xlsx_as_dicts(input_path, DEFAULT_SHEET_NAME)
            wafer = build_wafer(
                wafer_diameter=wafer_diameter,
                array_table=array_table,
                die_width=float(geometry_settings["die_width"]),
                die_height=float(geometry_settings["die_height"]),
                dies_per_array=int(geometry_settings["dies_per_array"]),
                array_side=float(geometry_settings["array_side"]),
                acceptor_shape=str(geometry_settings["acceptor_shape"]),
                acceptor_delta_x=float(geometry_settings["acceptor_delta_x"]),
                acceptor_delta_y=float(geometry_settings["acceptor_delta_y"]),
                acceptor_width=float(geometry_settings["acceptor_width"]),
                acceptor_height=float(geometry_settings["acceptor_height"]),
            )
            filter_available_arrays_for_selection(wafer)
        except ValueError as exc:
            messagebox.showerror("Select clusters", str(exc))
            return False

        self.wafer = wafer
        self.export_button.configure(
            state="normal" if self.wafer.has_selected_clusters() else "disabled"
        )
        return True

    def _open_cluster_selector(self) -> None:
        """Build fresh geometry, then open the cluster selector."""
        if not self.array_settings_applied or not self.die_settings_applied:
            messagebox.showerror(
                "Select clusters",
                "Apply Array settings and Die settings before selecting clusters.",
            )
            return

        if not self._build_cluster_data():
            return

        ClusterSelector(
            self.root,
            wafer=self.wafer,
            on_done=self._cluster_selection_finished,
        )

    def _cluster_selection_finished(self, selected_labels: set[str]) -> None:
        """Store the cluster labels selected in the popup."""
        if self.wafer is None:
            self.export_button.configure(state="disabled")
            self.status.set("Select clusters to rebuild the wafer map.")
            return

        self.wafer.set_selected_clusters(selected_labels)
        if self.wafer.has_selected_clusters():
            self.export_button.configure(state="normal")
            self.status.set(
                f"Selected {len(self.wafer.selected_cluster_labels)} clusters for export."
            )
        else:
            self.export_button.configure(state="disabled")
            self.status.set("No clusters selected for export.")

    # def _start_export(self) -> None:
    #     """Write the selected cluster tree to CSV in a worker thread."""
    #     try:
    #         output_path = self._validated_output_path()
    #         geometry_settings = self._geometry_settings()
    #         header_meta = self._header_meta_values(geometry_settings)
    #     except ValueError as exc:
    #         messagebox.showerror("Export CSV", str(exc))
    #         return
    
    def _start_export(self) -> None: #FA 2026-07-17: BUILD THE PATH FROM DIRECTORY + FIELDS IN THE GUI
        """Write the selected cluster tree to CSV in a worker thread."""
        try:
            output_directory = self._validated_output_directory()
            geometry_settings = self._geometry_settings()
            header_meta = self._header_meta_values(geometry_settings)
            output_path = output_directory / self._build_export_filename(header_meta)
        except ValueError as exc:
            messagebox.showerror("Export CSV", str(exc))
            return

        if self.wafer is None:
            messagebox.showerror("Export CSV", "Select clusters first.")
            return
        if not self.wafer.has_selected_clusters():
            messagebox.showerror("Export CSV", "Select at least one cluster first.")
            return

        self.export_button.configure(state="disabled")
        self.status.set("Exporting CSV...")

        # Run the export in a worker thread so the Tk window stays responsive.
        worker = threading.Thread(
            target=self._export_worker,
            args=(
                output_path,
                self.wafer,
                header_meta,
            ),
            daemon=True,
        )
        worker.start()

    def _validated_input_path(self) -> Path:
        """Return the selected XLSX path after validating it exists."""
        # Confirm the user selected an existing XLSX workbook.
        raw_path = self.input_path.get().strip()
        if not raw_path:
            raise ValueError("Choose an XLSX file first.")

        input_path = Path(raw_path)
        if input_path.suffix.lower() != ".xlsx":
            raise ValueError("The input file must be an .xlsx file.")
        if not input_path.exists():
            raise ValueError("The selected XLSX file does not exist.")

        return input_path

    # def _validated_output_path(self) -> Path:
    #     """Return the output CSV path, adding the extension if needed."""
    #     # Normalize the output path and force a .csv extension when omitted.
    #     raw_path = self.output_path.get().strip()
    #     if not raw_path:
    #         raise ValueError("Choose where to save the CSV file.")

    #     output_path = Path(raw_path)
    #     if output_path.suffix.lower() != ".csv":
    #         output_path = output_path.with_suffix(".csv")
    #         self.output_path.set(str(output_path))

    #     return output_path
    
    def _validated_output_directory(self) -> Path: 
        """Return the export folder after validating it exists."""
        raw_path = self.output_directory.get().strip()
        if not raw_path:
            raise ValueError("Choose an export folder first.")

        output_directory = Path(raw_path)
        if not output_directory.exists():
            raise ValueError("The selected export folder does not exist.")
        if not output_directory.is_dir():
            raise ValueError("The selected export path is not a folder.")

        return output_directory

    def _build_export_filename(self, header_meta: dict[str, str]) -> str: #FA 2026-07-17: !!!CHANGE THIS IF YOU WANT TO CHANGE NAME ORDER!!!
        """Return the auto-generated CSV filename from header metadata."""
        # Filename format: {ID_PROJECT}_{ID_BATCH}_{ID_WAFER}_{WAFER_ROTATION}.csv
        required_fields = ("ID_PROJECT", "ID_BATCH", "ID_WAFER", "WAFER_ROTATION")
        values = [header_meta.get(field, "").strip() for field in required_fields]
        if not all(values):
            raise ValueError(
                "Enter ID_PROJECT, ID_BATCH, ID_WAFER, and WAFER_ROTATION "
                "before exporting."
            )

        return "_".join(values) + ".csv"

    def _number_from_entry(self, value: StringVar, label: str) -> float:
        """Parse a required floating-point Entry value."""
        raw_value = value.get().strip()
        if not raw_value:
            raise ValueError(f"Enter a {label.lower()}.")

        try:
            number = float(raw_value)
        except ValueError as exc:
            raise ValueError(f"{label} must be a number.") from exc

        return number

    def _geometry_settings(self) -> GeometrySettings:
        """Return applied geometry settings in the engine-ready format."""
        array_width = self.array_width
        array_height = self.array_height
        array_side = self.array_side
        dies_per_array = self.dies_per_array
        if dies_per_array not in (1, 2, 4):
            raise ValueError("Dies per array must be 1, 2, or 4.")

        acceptor_shape = self.acceptance_shape
        acceptor_delta_x = self.acceptance_delta_x
        acceptor_delta_y = self.acceptance_delta_y

        if acceptor_shape == "circle":
            acceptor_width = self.circle_acceptor_diameter
            acceptor_height = acceptor_width
        elif acceptor_shape == "rectangle":
            acceptor_width = self.rectangle_acceptor_width
            acceptor_height = self.rectangle_acceptor_height
            if acceptor_width is None or acceptor_height is None:
                raise ValueError("Enter rectangle acceptor dimensions.")
        else:
            raise ValueError("Acceptor shape must be circle or rectangle.")

        #die_width = (array_width - 2 * array_side) / dies_per_array
        die_width = (array_width) #FA 2026-07-16: REMOVED CLEAVE STREET
        if die_width <= 0:
            raise ValueError("Array width must be greater than 2 x array side.")
        if acceptor_shape == "circle":
            acceptor_center_x = acceptor_delta_x
        else:
            acceptor_center_x = acceptor_delta_x + acceptor_width / 2

#        if not self._numbers_close(acceptor_center_x, die_width / 2):
 #           raise ValueError(
  #              "Acceptor must be symmetric from left/right die sides: "
   #             "its center X must equal half the die width."
    #        )

        return {
            "array_width": array_width,
            "array_height": array_height,
            "die_width": die_width,
            "die_height": array_height,
            "dies_per_array": dies_per_array,
            "array_side": array_side,
            "acceptor_shape": acceptor_shape,
            "acceptor_delta_x": acceptor_delta_x,
            "acceptor_delta_y": acceptor_delta_y,
            "acceptor_width": acceptor_width,
            "acceptor_height": acceptor_height,
        }

    def _numbers_close(self, left: float, right: float) -> bool:
        """Return whether two floating-point values are effectively equal."""
        return abs(left - right) <= 1e-9

    def _header_meta_values(self, geometry_settings: GeometrySettings) -> dict[str, str]:
        """Return CSV header metadata, including calculated tile dimensions."""
        # Convert Tk variables into a plain dictionary for CSV writing.
        header_meta = {
            field: value.get().strip()
            for field, value in self.header_meta.items()
        }
        # The current cluster workbook contains ten array columns and forty-two
        # bar rows per cluster; the builder reads the same shape from the XLSX.
        header_meta["TILE_WIDTH"] = str(round(float(geometry_settings["array_width"]) * 10, 6))
        header_meta["TILE_HEIGHT"] = str(round(float(geometry_settings["array_height"]) * 42, 6))
        return header_meta

    def _export_worker(
            self,
            output_path: Path,
            wafer: Wafer,
            header_meta: dict[str, str],
    ) -> None:
        """Flatten selected clusters and write their export rows."""
        try:
            export_rows = export_wafer(wafer)
            write_export_csv(export_rows, output_path, header_meta)
        except Exception as exc:
            # UI updates must happen back on the Tk main thread.
            self.root.after(0, self._export_failed, exc)
            return

        # Notify the main thread that the export completed successfully.
        self.root.after(0, self._export_finished, output_path, len(export_rows))

    def _export_finished(self, output_path: Path, row_count: int) -> None:
        """Handle successful export completion on the Tk main thread."""
        # Re-enable controls and show the user the export result.
        self.export_button.configure(state="normal")
        self.status.set(f"Exported {row_count} rows to {output_path}")
        messagebox.showinfo("Export CSV", f"Exported {row_count} rows.")

    def _export_failed(self, error: Exception) -> None:
        """Handle export failure on the Tk main thread."""
        # Restore the export button and show the failure reason.
        self.export_button.configure(state="normal")
        self.status.set("Export failed.")
        messagebox.showerror("Export CSV", str(error))


def run() -> None:
    """Create and run the Tkinter application."""
    # Create the Tk app and hand control to Tk's event loop.
    root = Tk()
    WaferMapGUI(root)
    root.mainloop()


if __name__ == "__main__":
    run()
