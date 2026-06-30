"""Display built wafer clusters and let the user choose which ones to export.

The main GUI builds the wafer geometry before opening this popup. It passes a
`Wafer`, which owns a cluster dictionary such as:

    {
        "AA": (cluster_aa, "outside"),
        "AB": (cluster_ab, "edge"),
    }

This module does not calculate geometry. It draws the existing `Cluster`
objects using their stored wafer statuses, stores the labels selected by the
user, and returns those labels to the main GUI when the user clicks `Done`.
"""

from __future__ import annotations

from tkinter import Canvas, Event, StringVar, Toplevel
from tkinter import ttk
from typing import Callable, Literal

from bar_selector_demo import BarSelector
from main import Cluster, ClusterMap, Wafer


DragAction = Literal["select", "deselect"]
Point = tuple[float, float]
CanvasRect = tuple[float, float, float, float]
CanvasTransform = tuple[float, float, float, float, float]
CONTROL_MASK = 0x0004


class ClusterSelector(Toplevel):
    """Tkinter popup for selecting real clusters to include in CSV export.

    The selector keeps two related forms of state:

    - `clusters` stores every grid cluster and its wafer status.
    - `selected_labels` stores only the dictionary keys chosen by the user.

    When selection is finished, the selector sends `selected_labels` back
    through the `on_done` callback.
    """

    # ======== Geometry attributes ========
    clusters: ClusterMap
    wafer: Wafer
    grid_bounds: CanvasRect
    cluster_canvas_rects: dict[str, CanvasRect]

    # ======== Selection callback and state ========
    on_done: Callable[[set[str]], None]  # Receives the selected cluster labels.

    selected_labels: set[str]  # Labels currently selected for export.

    # ======== Canvas item lookup ========
    item_to_label: dict[int, str]  # Canvas item ID -> cluster label,
    # used to turn mouse events into cluster selections.

    cluster_items: dict[str, tuple[int, int]]  # Cluster label -> (text ID, rectangle ID).

    # ======== Drag state ========
    drag_start: Point | None  # Canvas coordinate where the current click/drag gesture started.

    drag_rect_id: int | None  # Canvas item ID for the temporary dashed drag rectangle.

    drag_action: DragAction  # Whether the current drag box is adding or removing selected clusters.

    drag_moved: bool  # False for a simple click; true once pointer movement passes the threshold.

    # ======== Widgets ========
    status: StringVar
    canvas: Canvas

    # ======== Initialization ========
    def __init__(
            self,
            parent,
            wafer: Wafer,
            on_done: Callable[[set[str]], None],
    ) -> None:
        """Create the selector window and draw the currently built clusters.

        Args:
            parent: Main Tkinter window. Passing it to `Toplevel` makes this
                selector a child popup of the wafer-map GUI.
            wafer: Complete wafer object with labeled cluster geometry and any
                previous cluster selection.
            on_done: Callback owned by the main GUI. The selector calls it with
                the selected cluster labels when the user clicks `Done`.

        The method also initializes lookup dictionaries for canvas item IDs,
        drag state, and footer text before creating and positioning widgets.
        """
        super().__init__(parent)
        self.title("Cluster selector")
        self.geometry("860x700")
        self.minsize(720, 560)
        self.transient(parent)

        self.wafer = wafer
        self.clusters = wafer.clusters
        cluster_labels = list(self.clusters)
        first_cluster = self.clusters[cluster_labels[0]][0]
        last_cluster = self.clusters[cluster_labels[-1]][0]
        self.grid_bounds = (
            first_cluster.top_left[0],
            first_cluster.top_left[1],
            last_cluster.top_left[0] + last_cluster.width,
            last_cluster.top_left[1] - last_cluster.height,
        )
        self.on_done = on_done
        self.selected_labels: set[str] = {
            label
            for label in wafer.selected_cluster_labels
            if label in self.clusters and self.clusters[label][1] != "outside"
        }
        self.item_to_label: dict[int, str] = {}
        self.cluster_items: dict[str, tuple[int, int]] = {}
        self.cluster_canvas_rects: dict[str, CanvasRect] = {}
        self.drag_start: Point | None = None
        self.drag_rect_id: int | None = None
        self.drag_action: DragAction = "select"
        self.drag_moved = False
        self.status = StringVar()

        self._build_layout()
        self._create_canvas_items()
        self._layout_canvas_items()
        self._update_status()

    # ======== Layout ========
    def _build_layout(self) -> None:
        """Create widgets and connect mouse events to selection handlers.

        The popup contains:

        - a toolbar with instructions, `Clear`, and `Done`
        - a resizable `Canvas` that displays the cluster rectangles
        - a footer linked to `self.status`

        Canvas bindings divide a mouse gesture into press, motion, and release
        steps. Right-click opens the bar selector for a selected cluster.
        """
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(self, padding=(12, 10))
        toolbar.grid(row=0, column=0, sticky="ew")
        toolbar.columnconfigure(0, weight=1)

        ttk.Label(
            toolbar,
            text=(
                "Click to toggle export inclusion. Drag to update a group. "
                "Right-click or Control-click a selected cluster to enter its bar layer."
            ),
        ).grid(row=0, column=0, sticky="w")
        ttk.Button(toolbar, text="Clear", command=self._clear_selection).grid(
            row=0,
            column=1,
            padx=(12, 0),
        )
        ttk.Button(toolbar, text="Done", command=self._done).grid(
            row=0,
            column=2,
            padx=(8, 0),
        )

        self.canvas = Canvas(self, background="#f7f7f7", highlightthickness=0)
        self.canvas.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 8))
        self.canvas.bind("<Configure>", self._layout_canvas_items)
        self.canvas.bind("<ButtonPress-1>", self._start_drag)
        self.canvas.bind("<B1-Motion>", self._drag_selection_box)
        self.canvas.bind("<ButtonRelease-1>", self._finish_drag)
        self.canvas.bind("<Button-3>", self._open_bar_selector_at)
        self.canvas.bind("<Control-Button-1>", self._open_bar_selector_at)

        footer = ttk.Frame(self, padding=(12, 0, 12, 10))
        footer.grid(row=2, column=0, sticky="ew")
        ttk.Label(footer, textvariable=self.status).grid(row=0, column=0, sticky="w")

    # ======== Coordinate conversion ========
    def _canvas_transform(self) -> CanvasTransform:
        """Return values used to convert millimeters into canvas pixels.

        The complete cluster grid must fit inside both the canvas width and
        height with padding around its edges. Taking the smaller of the
        horizontal and vertical scale factors preserves cluster proportions
        when the window is resized. The layout pass calculates these values
        once and reuses them for every cluster.
        """
        canvas_width = max(self.canvas.winfo_width(), 1)
        canvas_height = max(self.canvas.winfo_height(), 1)
        padding = 44
        grid_left_x, grid_top_y, grid_right_x, grid_bottom_y = self.grid_bounds
        grid_width = grid_right_x - grid_left_x
        grid_height = grid_top_y - grid_bottom_y
        scale = min(
            (canvas_width - padding * 2) / grid_width,
            (canvas_height - padding * 2) / grid_height,
        )
        return (
            scale,
            canvas_width / 2,
            canvas_height / 2,
            (grid_left_x + grid_right_x) / 2,
            (grid_top_y + grid_bottom_y) / 2,
        )

    def _to_canvas(self, point: Point, transform: CanvasTransform) -> Point:
        """Convert one `(x, y)` wafer coordinate into one canvas pixel point.

        Wafer geometry uses `(0, 0)` at the wafer center, positive X to the
        right, and positive Y upward. Tkinter canvas coordinates use `(0, 0)`
        at the top-left and positive Y downward. The subtraction in the
        returned Y value performs that vertical-axis conversion.
        """
        scale, center_x, center_y, grid_center_x, grid_center_y = transform
        x, y = point
        return (
            center_x + (x - grid_center_x) * scale,
            center_y - (y - grid_center_y) * scale,
        )

    def _cluster_rect(self, cluster: Cluster, transform: CanvasTransform) -> CanvasRect:
        """Return the pixel bounding box for one real `Cluster` object.

        `Cluster.top_left`, `Cluster.width`, and `Cluster.height` are stored in
        millimeters. This method calculates the lower-right wafer coordinate
        and converts both corners into Tkinter canvas coordinates.
        """
        left_x, top_y = cluster.top_left
        x1, y1 = self._to_canvas((left_x, top_y), transform)
        x2, y2 = self._to_canvas((left_x + cluster.width, top_y - cluster.height), transform)
        return x1, y1, x2, y2

    # ======== Canvas items ========
    def _create_canvas_items(self) -> None:
        """Create cluster rectangles, labels, and the legend.

        Canvas drawing calls return integer item IDs. The method stores those
        IDs so later methods can move and recolor existing items rather than
        deleting and recreating them.

        The lookup directions are intentionally different:

        - `item_to_label[rect_id] -> "AC"` identifies a clicked rectangle.
        - `cluster_items["AC"] -> (text_id, rect_id)` finds both canvas items
          that visually represent one cluster.

        All drawing items initially use placeholder coordinates. The next call
        to `_layout_canvas_items()` positions them using real geometry.
        """
        self.item_to_label.clear()
        self.cluster_items.clear()

        # Store rectangle item IDs so click and drag handlers can map canvas
        # events back to cluster labels.
        for label in self.clusters:
            rect_id = self.canvas.create_rectangle(0, 0, 0, 0)
            text_id = self.canvas.create_text(
                0,
                0,
                text=label,
                fill="#333333",
                font=("TkDefaultFont", 9),
            )
            self.cluster_items[label] = (text_id, rect_id)
            self.item_to_label[rect_id] = label

        self.canvas.create_text(
            16,
            16,
            text=(
                "gray=inside  amber=edge  dark gray=outside and disabled  "
                "blue=selected for inclusion"
            ),
            anchor="nw",
            fill="#333333",
        )

    def _layout_canvas_items(self, _event: Event | None = None) -> None:
        """Position existing canvas items using the current canvas dimensions.

        Tkinter calls this method when the canvas emits `<Configure>`, usually
        after a resize. `__init__()` also calls it once after creating items.

        The method:

        1. converts each real cluster footprint into a pixel rectangle
        2. centers each visible cluster label inside its rectangle
        3. hides labels that would be too small to read
        4. reapplies selected or status-based styling

        `_event` is optional because Tkinter supplies it during resize events,
        while the constructor calls this method directly without an event.
        """
        transform = self._canvas_transform()
        for label in self.clusters:
            cluster, _status = self.clusters[label]
            x1, y1, x2, y2 = self._cluster_rect(cluster, transform)
            self.cluster_canvas_rects[label] = (x1, y1, x2, y2)
            text_id, rect_id = self.cluster_items[label]
            self.canvas.coords(rect_id, x1, y1, x2, y2)
            self.canvas.coords(text_id, (x1 + x2) / 2, (y1 + y2) / 2)

            # Tiny labels become clutter, so hide them when the cluster is too
            # small to read comfortably.
            if abs(x2 - x1) >= 28 and abs(y2 - y1) >= 18:
                self.canvas.itemconfigure(text_id, state="normal")
            else:
                self.canvas.itemconfigure(text_id, state="hidden")
            self._update_cluster_style(label)

    # ======== Cluster styling ========
    def _update_cluster_style(self, label: str) -> None:
        """Restyle one cluster rectangle from its selected-label state.

        Selected clusters are blue with a darker, thicker outline. Unselected
        clusters use their inside, edge, or outside status color. The method
        changes only the existing canvas rectangle; it does not rebuild any
        geometry.
        """
        _text_id, rect_id = self.cluster_items[label]
        outline = "#222222" if label in self.selected_labels else "#9a9a9a"
        width = 2 if label in self.selected_labels else 1
        self.canvas.itemconfigure(
            rect_id,
            fill=self._cluster_fill(label),
            outline=outline,
            width=width,
        )

    def _update_cluster_styles(self, labels: Iterable[str]) -> None:
        """Restyle each label in an iterable after a group selection change.

        Drag selection and `Clear` may affect many rectangles at once. This
        helper applies `_update_cluster_style()` to only the changed labels.
        """
        for label in labels:
            self._update_cluster_style(label)

    def _cluster_fill(self, label: str) -> str:
        """Return a fill color for the label's selection and wafer status."""
        if label in self.selected_labels:
            return "#6ea8fe"
        _cluster, status = self.clusters[label]
        if status == "edge":
            return "#e8d19a"
        if status == "inside":
            return "#d9d9d9"
        return "#bdbdbd"

    # ======== Mouse gestures ========
    def _start_drag(self, event: Event) -> None:
        """Record the starting point and mode for a new mouse gesture.

        A press may become either a click or a drag:

        - Press and release without enough movement toggles one cluster.
        - Press, move, and release applies a drag box to multiple clusters.

        Starting on a selected cluster sets `drag_action` to `"deselect"`.
        Starting anywhere else sets it to `"select"`.
        """
        if event.state & CONTROL_MASK:
            self.drag_start = None
            return

        self.drag_start = (event.x, event.y)
        self.drag_moved = False
        start_label = self._label_at(event.x, event.y)
        # Starting from an already-selected cluster makes a drag box remove
        # inclusions. Starting anywhere else makes the box add inclusions.
        self.drag_action = (
            "deselect"
            if start_label is not None and start_label in self.selected_labels
            else "select"
        )
        if self.drag_rect_id is not None:
            self.canvas.delete(self.drag_rect_id)
            self.drag_rect_id = None

    def _drag_selection_box(self, event: Event) -> None:
        """Create or resize the dashed rectangle shown during a mouse drag.

        Movement must exceed three pixels before the gesture counts as a drag.
        This threshold prevents slight pointer movement during a normal click
        from unexpectedly selecting a group of clusters.
        """
        if self.drag_start is None:
            return

        start_x, start_y = self.drag_start
        if abs(event.x - start_x) > 3 or abs(event.y - start_y) > 3:
            self.drag_moved = True

        if not self.drag_moved:
            return

        if self.drag_rect_id is None:
            self.drag_rect_id = self.canvas.create_rectangle(
                start_x,
                start_y,
                event.x,
                event.y,
                outline="#1f6feb",
                dash=(4, 3),
                width=2,
            )
            return

        self.canvas.coords(self.drag_rect_id, start_x, start_y, event.x, event.y)

    def _finish_drag(self, event: Event) -> None:
        """Complete the active mouse gesture and reset temporary drag state.

        If the pointer moved beyond the threshold, the method applies the
        selection box. Otherwise, it toggles the single cluster under the
        release point. Any temporary dashed rectangle is removed afterward.
        """
        if self.drag_start is None:
            return

        start_x, start_y = self.drag_start
        if self.drag_rect_id is not None:
            self.canvas.delete(self.drag_rect_id)
            self.drag_rect_id = None

        if self.drag_moved:
            self._apply_drag_box(start_x, start_y, event.x, event.y)
        else:
            self._toggle_cluster_at(event.x, event.y)

        self.drag_start = None
        self.drag_action = "select"
        self.drag_moved = False

    def _label_at(self, x: float, y: float) -> str | None:
        """Return the cluster label under a canvas pixel point, if one exists.

        `Canvas.find_overlapping(...)` returns item IDs that touch the point.
        This method scans them from topmost to bottommost and uses
        `item_to_label` to ignore non-cluster items such as the legend and text
        labels.
        """
        items = self.canvas.find_overlapping(x, y, x, y)
        for item_id in reversed(items):
            label = self.item_to_label.get(item_id)
            if label is not None:
                return label
        return None

    def _toggle_cluster_at(self, x: float, y: float) -> None:
        """Handle a single-click selection change at a canvas point.

        If the point lands on a cluster rectangle, flip that cluster's
        selected-for-inclusion state: selected clusters become unselected, and
        unselected clusters become selected. Then update that rectangle's style
        and refresh the footer count.
        """
        label = self._label_at(x, y)
        if label is None or self.clusters[label][1] == "outside":
            return

        if label in self.selected_labels:
            self.selected_labels.remove(label)
        else:
            self.selected_labels.add(label)
        self._update_cluster_style(label)
        self._update_status()

    def _apply_drag_box(
            self,
            start_x: float,
            start_y: float,
            end_x: float,
            end_y: float,
    ) -> None:
        """Apply the current select-or-deselect mode to every touched cluster.

        The four input values are the drag start and end pixel coordinates.
        The method normalizes them into left, right, top, and bottom edges so
        dragging works in any direction.

        Each selectable cluster uses the cached canvas rectangle produced by
        `_layout_canvas_items()` and is tested for overlap with the drag box.
        Outside clusters are skipped. Only changed labels are restyled.
        """
        left = min(start_x, end_x)
        right = max(start_x, end_x)
        top = min(start_y, end_y)
        bottom = max(start_y, end_y)

        changed_labels: list[str] = []
        for label in self.clusters:
            _cluster, status = self.clusters[label]
            if status == "outside":
                continue

            cluster_left, cluster_top, cluster_right, cluster_bottom = (
                self.cluster_canvas_rects[label]
            )
            if (
                    cluster_right < left
                    or cluster_left > right
                    or cluster_bottom < top
                    or cluster_top > bottom
            ):
                continue
            if self.drag_action == "select":
                if label not in self.selected_labels:
                    self.selected_labels.add(label)
                    changed_labels.append(label)
            elif label in self.selected_labels:
                self.selected_labels.remove(label)
                changed_labels.append(label)

        if changed_labels:
            self._update_cluster_styles(changed_labels)
            self._update_status()

    # ======== Selection output ========
    def _clear_selection(self) -> None:
        """Remove every selected label and return affected rectangles to gray."""
        cleared_labels = list(self.selected_labels)
        self.selected_labels.clear()
        self._update_cluster_styles(cleared_labels)
        self._update_status()

    def _done(self) -> None:
        """Return the user's selected cluster labels and close the popup.

        `self.on_done(...)` calls the main GUI callback that was passed into the
        constructor. The callback stores the selected labels in the GUI.
        """
        self.on_done(self.selected_labels)
        self.destroy()

    # ======== Bar navigation ========
    def _open_bar_selector_at(self, event: Event) -> None:
        """Open the real bar selector for a selected cluster."""
        self.drag_start = None
        if self.drag_rect_id is not None:
            self.canvas.delete(self.drag_rect_id)
            self.drag_rect_id = None

        label = self._label_at(event.x, event.y)
        if label is None:
            return
        if label not in self.selected_labels:
            self.status.set("Select the cluster before entering its bar layer.")
            return

        self.wafer.set_selected_clusters(self.selected_labels)
        cluster, _status = self.clusters[label]
        BarSelector(
            self,
            wafer=self.wafer,
            cluster_label=label,
            cluster=cluster,
            selected_labels=self.wafer.selected_bars_by_cluster.get(label, set()),
            on_done=self._bar_selection_finished,
        )

    def _bar_selection_finished(self, cluster_label: str, selected_bars: set[str]) -> None:
        """Store bar selection and refresh cluster state after the bar popup."""
        self.wafer.set_selected_bars(cluster_label, selected_bars)
        if cluster_label in self.wafer.selected_cluster_labels:
            self.selected_labels.add(cluster_label)
        else:
            self.selected_labels.discard(cluster_label)
        self._update_cluster_style(cluster_label)
        self._update_status()
        self.status.set(
            f"Selected {len(selected_bars)} bars in cluster {cluster_label}."
        )

    # ======== Status ========
    def _update_status(self) -> None:
        """Refresh the footer with the current selected and available counts."""
        self.status.set(
            f"Selected {len(self.selected_labels)} of {len(self.clusters)} clusters."
        )
