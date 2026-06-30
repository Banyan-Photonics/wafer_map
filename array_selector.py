"""Visual selector for choosing arrays inside one selected bar."""

from __future__ import annotations

from dataclasses import dataclass
from tkinter import Canvas, Event, StringVar, Toplevel
from tkinter import ttk
from typing import Callable, Iterable, Literal

from main import Bar


DragAction = Literal["select", "deselect"]
Point = tuple[float, float]
CanvasRect = tuple[float, float, float, float]


@dataclass(frozen=True)
class DisplayArray:
    """One array rectangle in wafer coordinates."""

    label: str
    top_left: Point
    width: float
    height: float


class ArraySelector(Toplevel):
    """Tkinter popup for selecting real arrays inside one bar."""

    cluster_label: str
    bar_label: str
    bar_top_left: Point
    bar_width: float
    bar_height: float
    selected_labels: set[str]
    item_to_label: dict[int, str]
    array_rect_items: dict[str, int]
    array_text_items: dict[str, int]
    bar_outline_item: int | None
    legend_item: int | None
    drag_start: Point | None
    drag_rect_id: int | None
    drag_action: DragAction
    drag_moved: bool
    status: StringVar
    arrays: list[DisplayArray]
    canvas: Canvas
    on_done: Callable[[str, str, set[str]], None]

    def __init__(
            self,
            parent,
            cluster_label: str,
            bar_label: str,
            bar: Bar,
            selected_labels: Iterable[str] | None,
            on_done: Callable[[str, str, set[str]], None],
    ) -> None:
        """Create an array selector for one real bar."""
        super().__init__(parent)
        self.title(f"Array selector - {cluster_label} bar {bar_label}")
        self.geometry("820x420")
        self.minsize(620, 320)
        self.transient(parent)

        self.cluster_label = cluster_label
        self.bar_label = bar_label
        self.bar_top_left = bar.top_left
        self.bar_width = bar.width
        self.bar_height = bar.height
        self.selected_labels = {
            label
            for label in (selected_labels or ())
            if label in bar.arrays
        }
        self.item_to_label = {}
        self.array_rect_items = {}
        self.array_text_items = {}
        self.bar_outline_item = None
        self.legend_item = None
        self.drag_start = None
        self.drag_rect_id = None
        self.drag_action = "select"
        self.drag_moved = False
        self.status = StringVar()
        self.on_done = on_done
        self.arrays = [
            DisplayArray(
                label=label,
                top_left=array.top_left,
                width=array.width,
                height=array.height,
            )
            for label, array in bar.arrays.items()
        ]

        self._build_layout()
        self._create_canvas_items()
        self._layout_canvas_items()
        self._update_status()

    def _build_layout(self) -> None:
        """Create toolbar, canvas, and status footer."""
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(self, padding=(12, 10))
        toolbar.grid(row=0, column=0, sticky="ew")
        toolbar.columnconfigure(0, weight=1)

        ttk.Label(
            toolbar,
            text=(
                f"Cluster {self.cluster_label}, bar {self.bar_label}: "
                "click to toggle arrays. Drag to update a group."
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

        footer = ttk.Frame(self, padding=(12, 0, 12, 10))
        footer.grid(row=2, column=0, sticky="ew")
        ttk.Label(footer, textvariable=self.status).grid(row=0, column=0, sticky="w")

    def _scale(self) -> float:
        """Return the current millimeter-to-canvas-pixel scale."""
        canvas_width = max(self.canvas.winfo_width(), 1)
        canvas_height = max(self.canvas.winfo_height(), 1)
        padding = 56
        return min(
            (canvas_width - padding * 2) / self.bar_width,
            (canvas_height - padding * 2) / self.bar_height,
        )

    def _to_canvas(self, point: Point) -> Point:
        """Convert wafer coordinates to canvas coordinates centered on this bar."""
        scale = self._scale()
        center_x = self.canvas.winfo_width() / 2
        center_y = self.canvas.winfo_height() / 2
        bar_left_x, bar_top_y = self.bar_top_left
        bar_center_x = bar_left_x + self.bar_width / 2
        bar_center_y = bar_top_y - self.bar_height / 2
        x, y = point
        return (
            center_x + (x - bar_center_x) * scale,
            center_y - (y - bar_center_y) * scale,
        )

    def _array_rect(self, array: DisplayArray) -> CanvasRect:
        """Return the array rectangle in canvas coordinates."""
        left_x, top_y = array.top_left
        x1, y1 = self._to_canvas((left_x, top_y))
        x2, y2 = self._to_canvas((left_x + array.width, top_y - array.height))
        return x1, y1, x2, y2

    def _create_canvas_items(self) -> None:
        """Create persistent canvas items for the array layer."""
        self.item_to_label.clear()
        self.array_rect_items.clear()
        self.array_text_items.clear()

        self.bar_outline_item = self.canvas.create_rectangle(
            0,
            0,
            0,
            0,
            fill="#ffffff",
            outline="#333333",
            width=2,
        )

        for array in self.arrays:
            rect_id = self.canvas.create_rectangle(0, 0, 0, 0)
            text_id = self.canvas.create_text(
                0,
                0,
                text=array.label,
                fill="#333333",
                font=("TkDefaultFont", 9),
            )
            self.array_rect_items[array.label] = rect_id
            self.array_text_items[array.label] = text_id
            self.item_to_label[rect_id] = array.label

        self.legend_item = self.canvas.create_text(
            16,
            16,
            text="gray=included by bar default  blue=selected specific arrays",
            anchor="nw",
            fill="#333333",
        )

    def _layout_canvas_items(self, _event: Event | None = None) -> None:
        """Move existing canvas items to match the current canvas size."""
        bar_left, bar_top = self.bar_top_left
        x1, y1 = self._to_canvas((bar_left, bar_top))
        x2, y2 = self._to_canvas((bar_left + self.bar_width, bar_top - self.bar_height))

        if self.bar_outline_item is not None:
            self.canvas.coords(self.bar_outline_item, x1, y1, x2, y2)

        for array in self.arrays:
            ax1, ay1, ax2, ay2 = self._array_rect(array)
            rect_id = self.array_rect_items[array.label]
            text_id = self.array_text_items[array.label]
            self.canvas.coords(rect_id, ax1, ay1, ax2, ay2)
            self.canvas.coords(text_id, (ax1 + ax2) / 2, (ay1 + ay2) / 2)

            if abs(ax2 - ax1) >= 20 and abs(ay2 - ay1) >= 12:
                self.canvas.itemconfigure(text_id, state="normal")
            else:
                self.canvas.itemconfigure(text_id, state="hidden")
            self._update_array_style(array.label)

        if self.legend_item is not None:
            self.canvas.coords(self.legend_item, 16, 16)

    def _update_array_style(self, label: str) -> None:
        """Update one array's color and outline."""
        rect_id = self.array_rect_items[label]
        selected = label in self.selected_labels
        self.canvas.itemconfigure(
            rect_id,
            fill="#6ea8fe" if selected else "#d9d9d9",
            outline="#222222" if selected else "#b5b5b5",
            width=2 if selected else 1,
        )

    def _update_array_styles(self, labels: Iterable[str]) -> None:
        """Update multiple array styles without rebuilding canvas items."""
        for label in labels:
            self._update_array_style(label)

    def _start_drag(self, event: Event) -> None:
        """Begin a click or drag gesture."""
        self.drag_start = (event.x, event.y)
        self.drag_moved = False
        start_label = self._label_at(event.x, event.y)
        self.drag_action = (
            "deselect"
            if start_label is not None and start_label in self.selected_labels
            else "select"
        )
        if self.drag_rect_id is not None:
            self.canvas.delete(self.drag_rect_id)
            self.drag_rect_id = None

    def _drag_selection_box(self, event: Event) -> None:
        """Update the temporary drag-selection rectangle."""
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
        """Finish a gesture as either a click toggle or drag-box action."""
        if self.drag_start is None:
            return

        start_x, start_y = self.drag_start
        if self.drag_rect_id is not None:
            self.canvas.delete(self.drag_rect_id)
            self.drag_rect_id = None

        if self.drag_moved:
            self._apply_drag_box(start_x, start_y, event.x, event.y)
        else:
            self._toggle_array_at(event.x, event.y)

        self.drag_start = None
        self.drag_action = "select"
        self.drag_moved = False

    def _label_at(self, x: float, y: float) -> str | None:
        """Return the topmost array label at a canvas point, if any."""
        items = self.canvas.find_overlapping(x, y, x, y)
        for item_id in reversed(items):
            label = self.item_to_label.get(item_id)
            if label is not None:
                return label
        return None

    def _toggle_array_at(self, x: float, y: float) -> None:
        """Handle a single-click selection change at a canvas point."""
        label = self._label_at(x, y)
        if label is None:
            return
        if label in self.selected_labels:
            self.selected_labels.remove(label)
        else:
            self.selected_labels.add(label)
        self._update_array_style(label)
        self._update_status()

    def _apply_drag_box(
            self,
            start_x: float,
            start_y: float,
            end_x: float,
            end_y: float,
    ) -> None:
        """Apply the active drag action to all arrays touched by the box."""
        left = min(start_x, end_x)
        right = max(start_x, end_x)
        top = min(start_y, end_y)
        bottom = max(start_y, end_y)

        changed_labels: list[str] = []
        for array in self.arrays:
            array_left, array_top, array_right, array_bottom = self._array_rect(array)
            if (
                    array_right < left
                    or array_left > right
                    or array_bottom < top
                    or array_top > bottom
            ):
                continue
            if self.drag_action == "select":
                if array.label not in self.selected_labels:
                    self.selected_labels.add(array.label)
                    changed_labels.append(array.label)
            elif array.label in self.selected_labels:
                self.selected_labels.remove(array.label)
                changed_labels.append(array.label)

        if changed_labels:
            self._update_array_styles(changed_labels)
            self._update_status()

    def _clear_selection(self) -> None:
        """Clear all array inclusions."""
        cleared_labels = list(self.selected_labels)
        self.selected_labels.clear()
        self._update_array_styles(cleared_labels)
        self._update_status()

    def _done(self) -> None:
        """Return selected arrays for this bar and close the popup."""
        self.on_done(self.cluster_label, self.bar_label, self.selected_labels)
        self.destroy()

    def _update_status(self) -> None:
        """Refresh the footer summary counts."""
        self.status.set(
            f"Selected {len(self.selected_labels)} of {len(self.arrays)} arrays."
        )
