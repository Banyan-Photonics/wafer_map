"""
Created on Fri May 8th 2026

@author: Steven Li

=======================================================

Build wafer-map rows by selecting available dies on a wafer.

Coordinate and dimension convention:
    `width` always means the X-direction dimension.
    `height` always means the Y-direction dimension.

Coordinates are stored as `(x, y)` points in millimeters. Positive X points
right. Positive Y points up, so moving down from a top-left point subtracts
from Y.

Export row dictionaries also use millimeter-keyed fields such as `xc_ref[mm]`.
The GUI CSV writer may label those columns as micrometers for compatibility,
but the numeric values remain millimeters.
"""
from __future__ import annotations
import re
from math import ceil, hypot, sqrt
from typing import Literal

from xlsx_reader import read_xlsx_as_dicts as rx
Point = tuple[float, float]
ClusterWaferStatus = Literal["inside", "edge", "outside"]
ArrayTable = list[dict[str, str]]
ExportTable = list[dict[str, float]]


class Cluster:
    """One cluster footprint containing bars keyed by bar label.

    The cluster label is intentionally not stored here; it belongs to the key in
    a cluster dictionary. `top_left` is the full cluster footprint's top-left
    corner. Build order is bottom-up: `Die` objects are grouped into `Array`
    objects, `Array` objects are grouped into `Bar` objects, and `Bar` objects
    are passed here as `bars`.
    """

    top_left: Point
    width: float
    height: float
    quadrant: int
    bars_per_cluster: int
    bars: dict[str, Bar]

    def __init__(
            self,
            top_left: Point,
            bars: dict[str, Bar],
            width: float | None = None,
            height: float | None = None,
            quadrant: int | None = None,
    ):
        """Create a cluster from its bars.

        Preconditions:
            `bars` is keyed by bar label from the imported XLSX file.
            Bars in one cluster are expected to have the same width.
            `width`, `height`, and `quadrant` may be passed to preserve the
            original footprint when a cluster contains filtered edge arrays.
        """
        if not bars:
            raise ValueError("Cluster must contain at least one bar.")

        bar_iter = iter(bars.items())
        first_label, first_bar = next(bar_iter)
        if not first_label:
            raise ValueError("Bar labels cannot be empty.")

        first_width = first_bar.width
        for bar_label, bar in bar_iter:
            if not bar_label:
                raise ValueError("Bar labels cannot be empty.")
            if bar.width != first_width:
                raise ValueError("All bars in a cluster must have the same width.")

        self.bars = bars
        self.top_left = top_left
        self.bars_per_cluster = len(bars)
        self.width = self.find_width() if width is None else width
        self.height = self.find_height() if height is None else height
        self.quadrant = self.find_quadrant() if quadrant is None else quadrant

    def find_width(self) -> float:
        """Return the full X-direction cluster footprint width."""
        return next(iter(self.bars.values())).find_width()

    def find_height(self) -> float:
        """Return the full Y-direction cluster footprint height."""
        return sum(bar.find_height() for bar in self.bars.values())

    def find_quadrant(self) -> int:
        """Return the quadrant that contains the cluster center.

        Quadrants follow the wafer-map convention:

        - 1: top right
        - 2: top left
        - 3: bottom left
        - 4: bottom right

        >>> acceptor = Acceptor("circle", (0.025, 0.0), 0.1, 0.1, 0.016, 0.016, 1)
        >>> die = Die(0.25, 0.25, acceptor)
        >>> array = Array((0.0, 0.0), 1, 0.05, "demo", {1: die})
        >>> bar = Bar((0.0, 0.0), {"A": array})
        >>> Cluster((0.0, 0.25), {"1": bar}).quadrant
        1
        >>> Cluster((-0.3, 0.25), {"1": bar}).quadrant
        2
        >>> Cluster((-0.3, 0.0), {"1": bar}).quadrant
        3
        >>> Cluster((0.0, 0.0), {"1": bar}).quadrant
        4
        """
        left_x, top_y = self.top_left
        center_x = left_x + self.width / 2
        center_y = top_y - self.height / 2

        if center_y >= 0:
            if center_x >= 0:
                return 1
            return 2
        if center_x < 0:
            return 3
        return 4


class Bar:
    """One bar footprint containing arrays keyed by array label.

    The bar label is intentionally not stored here; it belongs to the key in
    `Cluster.bars`. `top_left` is the full bar footprint's top-left corner.
    Build `Array` objects first, then pass them here as `arrays`.
    """

    top_left: Point
    width: float
    height: float
    arrays_per_bar: int
    arrays: dict[str, Array]

    def __init__(
            self,
            top_left: Point,
            arrays: dict[str, Array],
            width: float | None = None,
            height: float | None = None,
    ):
        """Create a bar from its arrays.

        Preconditions:
            `arrays` is keyed by array label, such as "A", "B", or "J".
            All arrays in one bar are expected to have the same height.
            `width` and `height` may be passed to preserve the original
            footprint when a bar contains filtered edge arrays.
        """
        if not arrays:
            raise ValueError("Bar must contain at least one array.")

        array_iter = iter(arrays.items())
        first_label, first_array = next(array_iter)
        if not first_label:
            raise ValueError("Array labels cannot be empty.")

        first_height = first_array.find_height()
        for array_label, array in array_iter:
            if not array_label:
                raise ValueError("Array labels cannot be empty.")
            if array.find_height() != first_height:
                raise ValueError("All arrays in a bar must have the same height.")

        self.arrays = arrays
        self.top_left = top_left
        self.arrays_per_bar = len(arrays)
        self.width = self.find_width() if width is None else width
        self.height = self.find_height() if height is None else height

    def find_width(self) -> float:
        """Return the full X-direction bar footprint width."""
        return sum(array.find_width() for array in self.arrays.values())

    def find_height(self) -> float:
        """Return the full Y-direction bar footprint height."""
        return next(iter(self.arrays.values())).find_height()


class Array:
    """One array footprint, including array-side margins in X.

    The array label is intentionally not stored here; it belongs to the key in
    `Bar.arrays`.

    An array contains positioned `Die` objects keyed by die number. `array_side`
    is half of the Cluster Cleave Street. The full array pitch in X is:

        half cleave street + dies + half cleave street

    `top_left` is the full array pitch's top-left corner, before that left-side
    half-street. Build positioned `Die` objects first, then pass them here as
    `dies`.
    """

    top_left: Point
    width: float
    height: float
    dies_per_array: Literal[1, 2, 4]
    array_side: float
    detail: str
    dies: dict[int, Die]

    def __init__(self, top_left: Point,
                 dies_per_array: Literal[1, 2, 4],
                 array_side: float, detail: str, dies: dict[int, Die]):
        """Create an array from its positioned dies.

        Preconditions:
            `dies` is keyed by die number, starting at 1. Each die already has
            its own full-footprint top-left position encoded in its calculated
            acceptor center.
            `array_side` is half of the Cluster Cleave Street.
        """
        if dies_per_array not in (1, 2, 4):
            raise ValueError("Dies per array must be 1, 2, or 4.")
        if array_side < 0:
            raise ValueError("Array side cannot be negative.")
        if len(dies) != dies_per_array:
            raise ValueError("Die count must match dies per array.")
        if set(dies) != set(range(1, dies_per_array + 1)):
            raise ValueError("Die numbers must be consecutive and start at 1.")

        self.dies = dies
        self.top_left = top_left
        self.dies_per_array = dies_per_array
        self.array_side = array_side
        self.detail = detail
        self.width = self.find_width()
        self.height = self.find_height()

    def find_width(self) -> float:
        """Return the full X-direction array footprint width."""
        die = self.dies[1]
        return self.array_side * 2 + die.width * self.dies_per_array

    def find_height(self) -> float:
        """Return the full Y-direction array footprint height."""
        die = self.dies[1]
        return die.height


class Acceptor:
    """One acceptor shape, its center, and its wafer-edge test point.

    Circle inputs give the delta from die top-left to the circle center.
    Rectangle inputs give the delta from die top-left to the rectangle top-left;
    this class converts that to a center point.

    `test_point` is the quadrant-facing point used for wafer-edge filtering.
    For a circle, it is the quadrant-facing corner of the circle's bounding box,
    matching the old center-marker behavior.
    """

    shape: Literal["circle", "rectangle"]
    center: Point
    width: float
    height: float
    test_point: Point

    def __init__(
            self,
            shape: Literal["circle", "rectangle"],
            die_top_left: Point,
            delta_x: float,
            delta_y: float,
            width: float,
            height: float,
            quadrant: int,
    ):
        """Create an acceptor from die-relative inputs.

        Args:
            shape: Circle or rectangle acceptor.
            die_top_left: Top-left corner of the full die footprint.
            delta_x: Circle center X offset, or rectangle top-left X offset.
            delta_y: Circle center Y offset, or rectangle top-left Y offset.
            width: Circle diameter or rectangle width.
            height: Circle diameter or rectangle height.
            quadrant: Cluster quadrant that decides the wafer-edge test point.
        """
        if shape not in ("circle", "rectangle"):
            raise ValueError(f"Unsupported acceptor shape: {shape}")
        if delta_x < 0:
            raise ValueError("Acceptor delta X cannot be negative.")
        if delta_y < 0:
            raise ValueError("Acceptor delta Y cannot be negative.")
        if width <= 0:
            raise ValueError("Acceptor width must be greater than zero.")
        if height <= 0:
            raise ValueError("Acceptor height must be greater than zero.")
        if quadrant not in (1, 2, 3, 4):
            raise ValueError(f"Unsupported quadrant: {quadrant}")

        self.shape = shape
        self.width = width
        self.height = height
        self.center = self.find_center(die_top_left, delta_x, delta_y)
        self.test_point = self.find_test_point(quadrant)

    def find_center(
            self,
            die_top_left: Point,
            delta_x: float,
            delta_y: float,
    ) -> Point:
        """Return the acceptor center in wafer coordinates."""
        left_x, top_y = die_top_left
        if self.shape == "circle":
            return (
                left_x + delta_x,
                top_y - delta_y,
            )
        return (
            left_x + delta_x + self.width / 2,
            top_y - delta_y - self.height / 2,
        )

    def find_test_point(self, quadrant: int) -> Point:
        """Return the quadrant-facing point used for wafer-edge testing."""
        center_x, center_y = self.center
        half_width = self.width / 2
        half_height = self.height / 2

        if quadrant == 1:
            return center_x + half_width, center_y + half_height
        if quadrant == 2:
            return center_x - half_width, center_y + half_height
        if quadrant == 3:
            return center_x - half_width, center_y - half_height
        if quadrant == 4:
            return center_x + half_width, center_y - half_height

        raise ValueError(f"Unsupported quadrant: {quadrant}")


class Die:
    """One die footprint and its acceptor.

    The die number is intentionally not stored here; it belongs to the key in
    `Array.dies`.

    The die coordinate contract is intentionally based on the full die
    footprint, not only the active die area. In this class:

    - `die_top_left` means the top-left corner of the full die footprint.
    - `width` is the full X-direction die width.
    - `height` is the full Y-direction die footprint height.
    - `acceptor` stores shape-specific center and wafer-edge test-point data.
    """

    width: float
    height: float
    acceptor: Acceptor

    def __init__(
            self,
            width: float,
            height: float,
            acceptor: Acceptor,
    ):
        """Create a die from its full footprint dimensions and acceptor.

        Args:
            width: Full X-direction die width in mm.
            height: Full Y-direction die footprint height in mm.
            acceptor: Shape-specific acceptor geometry for this die.
        """
        if width <= 0:
            raise ValueError("Die width must be greater than zero.")
        if height <= 0:
            raise ValueError("Die height must be greater than zero.")

        self.width = width
        self.height = height
        self.acceptor = acceptor


ClusterMap = dict[str, tuple[Cluster, ClusterWaferStatus]]


class _NoAvailableArraysError(ValueError):
    """Raised when availability filtering removes every array in a cluster."""


class Wafer:
    """Top-level wafer state containing geometry and cluster inclusion."""

    diameter: float
    clusters: ClusterMap
    selected_cluster_labels: set[str]
    selected_bars_by_cluster: dict[str, set[str]]
    selected_arrays_by_bar: dict[tuple[str, str], set[str]]
    arrays_filtered: bool

    def __init__(
            self,
            diameter: float,
            clusters: ClusterMap,
            selected_cluster_labels: set[str] | None = None,
    ):
        """Create a wafer from a complete labeled cluster map."""
        if diameter <= 0:
            raise ValueError("Wafer diameter must be greater than zero.")

        self.diameter = diameter
        self.clusters = clusters
        self.selected_cluster_labels: set[str] = set()
        self.selected_bars_by_cluster: dict[str, set[str]] = {}
        self.selected_arrays_by_bar: dict[tuple[str, str], set[str]] = {}
        self.arrays_filtered = False
        if selected_cluster_labels is not None:
            self.set_selected_clusters(selected_cluster_labels)

    @property
    def radius(self) -> float:
        """Return the wafer radius in millimeters."""
        return self.diameter / 2

    def set_selected_clusters(self, selected_labels: set[str]) -> None:
        """Store cluster labels selected for inclusion."""
        self.selected_cluster_labels = {
            label
            for label in selected_labels
            if label in self.clusters and self.clusters[label][1] != "outside"
        }
        self.selected_bars_by_cluster = {
            label: selected_bars
            for label, selected_bars in self.selected_bars_by_cluster.items()
            if label in self.selected_cluster_labels
        }
        self.selected_arrays_by_bar = {
            (cluster_label, bar_label): selected_arrays
            for (cluster_label, bar_label), selected_arrays
            in self.selected_arrays_by_bar.items()
            if cluster_label in self.selected_cluster_labels
        }

    def set_selected_bars(self, cluster_label: str, selected_labels: set[str]) -> None:
        """Store bar labels selected inside one selected cluster."""
        if cluster_label not in self.selected_cluster_labels:
            return
        cluster, status = self.clusters[cluster_label]
        if status == "outside":
            self.selected_cluster_labels.discard(cluster_label)
            self.selected_bars_by_cluster.pop(cluster_label, None)
            self._clear_array_selection_for_cluster(cluster_label)
            return

        selected_bars = {
            label
            for label in selected_labels
            if label in cluster.bars
        }
        if not selected_bars:
            self.selected_cluster_labels.discard(cluster_label)
            self.selected_bars_by_cluster.pop(cluster_label, None)
            self._clear_array_selection_for_cluster(cluster_label)
            return

        self.selected_bars_by_cluster[cluster_label] = selected_bars
        self.selected_arrays_by_bar = {
            key: selected_arrays
            for key, selected_arrays in self.selected_arrays_by_bar.items()
            if key[0] != cluster_label or key[1] in selected_bars
        }

    def set_selected_arrays(
            self,
            cluster_label: str,
            bar_label: str,
            selected_labels: set[str],
    ) -> None:
        """Store array labels selected inside one selected bar."""
        if cluster_label not in self.selected_cluster_labels:
            return
        cluster, status = self.clusters[cluster_label]
        if status == "outside" or bar_label not in cluster.bars:
            return

        selected_bars = self.selected_bars_by_cluster.get(cluster_label)
        if selected_bars is None or bar_label not in selected_bars:
            return

        bar = cluster.bars[bar_label]
        selected_arrays = {
            label
            for label in selected_labels
            if label in bar.arrays
        }
        key = (cluster_label, bar_label)
        if selected_arrays:
            self.selected_arrays_by_bar[key] = selected_arrays
            return

        self.selected_arrays_by_bar.pop(key, None)
        selected_bars.discard(bar_label)
        if selected_bars:
            self.selected_bars_by_cluster[cluster_label] = selected_bars
            return

        self.selected_cluster_labels.discard(cluster_label)
        self.selected_bars_by_cluster.pop(cluster_label, None)
        self._clear_array_selection_for_cluster(cluster_label)

    def _clear_array_selection_for_cluster(self, cluster_label: str) -> None:
        """Remove all stored array selections for one cluster."""
        self.selected_arrays_by_bar = {
            key: selected_arrays
            for key, selected_arrays in self.selected_arrays_by_bar.items()
            if key[0] != cluster_label
        }

    def selected_clusters_for_export(self) -> ClusterMap:
        """Return selected clusters in wafer-grid order."""
        selected_clusters: ClusterMap = {}
        for label, (cluster, status) in self.clusters.items():
            if label not in self.selected_cluster_labels:
                continue

            selected_bars = self.selected_bars_by_cluster.get(label)
            if selected_bars is None:
                selected_clusters[label] = (cluster, status)
                continue

            bars: dict[str, Bar] = {}
            for bar_label, bar in cluster.bars.items():
                if bar_label not in selected_bars:
                    continue
                export_bar = self._bar_for_export(label, bar_label, bar)
                if export_bar is not None:
                    bars[bar_label] = export_bar
            if bars:
                selected_clusters[label] = (
                    Cluster(
                        top_left=cluster.top_left,
                        bars=bars,
                        width=cluster.width,
                        height=cluster.height,
                        quadrant=cluster.quadrant,
                    ),
                    status,
                )
        return selected_clusters

    def _bar_for_export(self, cluster_label: str, bar_label: str, bar: Bar) -> Bar | None:
        """Return a bar filtered by array selection, if one exists."""
        selected_arrays = self.selected_arrays_by_bar.get((cluster_label, bar_label))
        if selected_arrays is None:
            return bar

        arrays = {
            array_label: array
            for array_label, array in bar.arrays.items()
            if array_label in selected_arrays
        }
        if not arrays:
            return None
        return Bar(
            top_left=bar.top_left,
            arrays=arrays,
            width=bar.width,
            height=bar.height,
        )

    def has_selected_clusters(self) -> bool:
        """Return whether any selectable clusters are selected."""
        return bool(self.selected_cluster_labels)


def _csv_number(value: float) -> float:
    """Return a clean numeric value for CSV export."""
    return round(value, 6)


def build_wafer(
        wafer_diameter: float,
        array_table: ArrayTable,
        die_width: float,
        die_height: float,
        dies_per_array: Literal[1, 2, 4],
        array_side: float,
        acceptor_shape: Literal["circle", "rectangle"],
        acceptor_delta_x: float,
        acceptor_delta_y: float,
        acceptor_width: float,
        acceptor_height: float,
) -> Wafer:
    """Build the complete wafer with labeled cluster geometry.

    The returned wafer stores a cluster dictionary that maps stable wafer-grid
    labels such as `"AB"` to `(Cluster, ClusterWaferStatus)` tuples. The grid is
    preserved even when a cluster is outside the wafer so the selector can
    display the full layout. Automatic fab-area and wafer-edge array filtering
    can be applied once before visual selection with
    `filter_available_arrays_for_selection(...)`.

    >>> rows = [{"Array position": "1", "A": "demo"}]
    >>> wafer = build_wafer(
    ...     wafer_diameter=1.0,
    ...     array_table=rows,
    ...     die_width=0.25,
    ...     die_height=0.25,
    ...     dies_per_array=1,
    ...     array_side=0.0125,
    ...     acceptor_shape="circle",
    ...     acceptor_delta_x=0.1,
    ...     acceptor_delta_y=0.1,
    ...     acceptor_width=0.016,
    ...     acceptor_height=0.016,
    ... )
    >>> sorted(wafer.clusters)[:2]
    ['AA', 'AB']
    >>> first_cluster, first_status = wafer.clusters["AA"]
    >>> first_cluster.width, first_cluster.height, first_cluster.bars_per_cluster
    (0.275, 0.25, 1)
    >>> first_status
    'edge'
    >>> first_die = first_cluster.bars["1"].arrays["A"].dies[1]
    >>> tuple(round(value, 3) for value in first_die.acceptor.center)
    (-0.438, 0.4)
    >>> tuple(round(value, 3) for value in first_die.acceptor.test_point)
    (-0.446, 0.408)
    """
    if wafer_diameter <= 0:
        raise ValueError("Wafer diameter must be greater than zero.")
    if not array_table:
        raise ValueError("Array table must contain at least one row.")
    if dies_per_array not in (1, 2, 4):
        raise ValueError("Dies per array must be 1, 2, or 4.")
    if array_side < 0:
        raise ValueError("Array side cannot be negative.")

    if acceptor_shape not in ("circle", "rectangle"):
        raise ValueError(f"Unsupported acceptor shape: {acceptor_shape}")

    # Only numeric "Array position" rows represent physical bars. Other XLSX
    # rows are labels, notes, or spacing rows and should not create geometry.
    bar_rows: list[dict[str, str]] = []
    for row in array_table:
        bar_label = row.get("Array position", "")
        try:
            int(bar_label)
        except ValueError:
            continue
        bar_rows.append(row)

    if not bar_rows:
        raise ValueError("Array table must contain at least one numeric bar row.")

    def array_labels_for_row(row: dict[str, str]) -> list[str]:
        """Return array-column labels in their imported XLSX order."""
        return [
            label
            for label in row
            if label != "Array position"
        ]

    # These are local footprint dimensions used for stepping from one object to
    # the next. The object instances also store their derived width and height.
    array_width = array_side * 2 + die_width * dies_per_array
    bar_height = die_height

    def quadrant_for_cluster_bounds(
            cluster_top_left: Point,
            cluster_width: float,
            cluster_height: float,
    ) -> int:
        """Return the quadrant for cluster bounds before the Cluster exists."""
        left_x, top_y = cluster_top_left
        center_x = left_x + cluster_width / 2
        center_y = top_y - cluster_height / 2

        if center_y >= 0:
            if center_x >= 0:
                return 1
            return 2
        if center_x < 0:
            return 3
        return 4

    def build_cluster_at(cluster_top_left: Point, quadrant: int) -> Cluster:
        """Build one fully positioned cluster at the requested top-left point."""
        cluster_left_x, cluster_top_y = cluster_top_left
        bars: dict[str, Bar] = {}

        for bar_index, row in enumerate(bar_rows):
            bar_label = row["Array position"]
            # Bars are stacked vertically inside the cluster. Moving down means
            # subtracting from Y.
            bar_top_left = (
                cluster_left_x,
                cluster_top_y - bar_index * bar_height,
            )
            bar_left_x, bar_top_y = bar_top_left
            arrays: dict[str, Array] = {}

            for array_index, array_label in enumerate(array_labels_for_row(row)):
                # Arrays are laid out left-to-right inside a bar.
                array_top_left = (
                    bar_left_x + array_index * array_width,
                    bar_top_y,
                )
                array_left_x, array_top_y = array_top_left
                dies: dict[int, Die] = {}

                for die_number in range(1, dies_per_array + 1):
                    # `array_side` is half of the Cluster Cleave Street, so dies
                    # begin after the left half-street.
                    die_top_left = (
                        array_left_x
                        + array_side
                        + (die_number - 1) * die_width,
                        array_top_y,
                    )
                    acceptor = Acceptor(
                        shape=acceptor_shape,
                        die_top_left=die_top_left,
                        delta_x=acceptor_delta_x,
                        delta_y=acceptor_delta_y,
                        width=acceptor_width,
                        height=acceptor_height,
                        quadrant=quadrant,
                    )
                    dies[die_number] = Die(
                        width=die_width,
                        height=die_height,
                        acceptor=acceptor,
                    )

                arrays[array_label] = Array(
                    top_left=array_top_left,
                    dies_per_array=dies_per_array,
                    array_side=array_side,
                    detail=row.get(array_label, ""),
                    dies=dies,
                )

            bars[bar_label] = Bar(
                top_left=bar_top_left,
                arrays=arrays,
            )

        return Cluster(
            top_left=cluster_top_left,
            bars=bars,
        )

    template_cluster = build_cluster_at((0.0, 0.0), 4)
    # Use the template's derived footprint to choose an even square grid large
    # enough to cover the wafer diameter in both X and Y.
    cluster_count = ceil(max(
        wafer_diameter / template_cluster.width,
        wafer_diameter / template_cluster.height,
    ))
    if cluster_count % 2 != 0:
        cluster_count += 1

    full_width = cluster_count * template_cluster.width
    full_height = cluster_count * template_cluster.height
    clusters: ClusterMap = {}
    wafer_radius = wafer_diameter / 2

    # Place the square cluster grid around wafer center (0, 0), ordered
    # row-major: top row left-to-right, then the next row. Labels are assigned
    # here so the GUI and exporter share one source of truth.
    for row_index in range(cluster_count):
        cluster_top_y = full_height / 2 - row_index * template_cluster.height
        for column_index in range(cluster_count):
            cluster_left_x = -full_width / 2 + column_index * template_cluster.width
            cluster_top_left = (cluster_left_x, cluster_top_y)
            quadrant = quadrant_for_cluster_bounds(
                cluster_top_left,
                template_cluster.width,
                template_cluster.height,
            )
            cluster = build_cluster_at(cluster_top_left, quadrant)
            cluster_label = (
                chr(ord("A") + row_index)
                + chr(ord("A") + column_index)
            )
            clusters[cluster_label] = (
                cluster,
                _cluster_in_wafer(wafer_radius, cluster),
            )

    return Wafer(
        diameter=wafer_diameter,
        clusters=clusters,
    )


def filter_available_arrays_for_selection(wafer: Wafer) -> None:
    """Remove unavailable arrays from a wafer once before visual selection.

    The operation is destructive for the current wafer object. It removes
    arrays blocked by Fab Area markers or wafer-edge checks, marks clusters with
    no available arrays as `"outside"`, and sets `wafer.arrays_filtered` so the
    same wafer is not filtered again when the selector reopens.
    """
    if wafer.arrays_filtered:
        return

    filtered_clusters: ClusterMap = {}
    for cluster_label, (cluster, status) in wafer.clusters.items():
        if status == "outside":
            filtered_clusters[cluster_label] = (cluster, status)
            continue

        try:
            filtered_clusters[cluster_label] = (
                _select_array_include(cluster, wafer.radius),
                status,
            )
        except _NoAvailableArraysError:
            filtered_clusters[cluster_label] = (cluster, "outside")

    wafer.clusters = filtered_clusters
    wafer.arrays_filtered = True
    wafer.set_selected_clusters(wafer.selected_cluster_labels)


def _cluster_in_wafer(
        wafer_radius: float,
        cluster: Cluster,
) -> ClusterWaferStatus:
    """Classify one cluster by whether it is inside, outside, or on the wafer edge.

    The cluster position is its full-footprint top-left corner. The cluster's
    quadrant is stored on `cluster.quadrant`.

    >>> acceptor = Acceptor("circle", (0.025, 0.0), 0.1, 0.1, 0.016, 0.016, 1)
    >>> die = Die(0.25, 0.25, acceptor)
    >>> array = Array((0.0, 0.0), 1, 0.05, "demo", {1: die})
    >>> bar = Bar((0.0, 0.0), {"A": array})
    >>> _cluster_in_wafer(1.0, Cluster((0.0, 0.25), {"1": bar}))
    'inside'
    >>> _cluster_in_wafer(0.1, Cluster((0.0, 0.25), {"1": bar}))
    'edge'
    """
    # Expand the upper-left coordinate into all four corners of the cluster.
    left_x, upper_y = cluster.top_left
    right_x = left_x + cluster.width
    lower_y = upper_y - cluster.height

    upper_left = (left_x, upper_y)
    upper_right = (right_x, upper_y)
    lower_left = (left_x, lower_y)
    lower_right = (right_x, lower_y)
    quadrant = cluster.quadrant

    if quadrant == 1:
        d_max = hypot(*upper_right)
        d_min = hypot(*lower_left)
    elif quadrant == 2:
        d_max = hypot(*upper_left)
        d_min = hypot(*lower_right)
    elif quadrant == 3:
        d_max = hypot(*lower_left)
        d_min = hypot(*upper_right)
    elif quadrant == 4:
        d_max = hypot(*lower_right)
        d_min = hypot(*upper_left)
    else:
        raise ValueError(f"Unsupported quadrant: {quadrant}")

    # Nearest corner outside means the whole cluster is outside; farthest
    # corner outside means the cluster crosses the wafer edge.
    if d_min >= wafer_radius:
        return "outside"
    if d_min < wafer_radius < d_max:
        return "edge"
    return "inside"


FAB_AREA_PATTERN = re.compile(
    r"Fab Area\s*\(\s*([0-9]*\.?[0-9]+)\s*mm\s*x\s*([0-9]*\.?[0-9]+)\s*mm\s*\)",
    re.IGNORECASE,
)
FAB_AREA_LABEL_PATTERN = re.compile(r"Fab Area", re.IGNORECASE)


def _fab_area_excluded_slots(cluster: Cluster) -> set[tuple[str, str]]:
    """Return `(bar_label, array_label)` slots occupied by Fab Area markers.

    Format requirement:
        Fab area cells must use `Fab Area (<width>mm x <height>mm)`.

    Preconditions:
        The value before `x` is the fab-area width in millimeters.
        The value after `x` is the fab-area height in millimeters.
        Both values must be greater than zero.

    Examples:
        Valid: `Fab Area (2.1mm x 0.5mm)`
        Valid: `Fab Area (2.1 mm x 0.5 mm)`
        Invalid: `Fab Area (2.1mm width x 0.5mm height)`
    """
    excluded_slots: set[tuple[str, str]] = set()
    bar_items = [
        (bar_label, bar, list(bar.arrays.items()), list(bar.arrays))
        for bar_label, bar in cluster.bars.items()
    ]

    # Scan each imported array detail cell. When a Fab Area marker is found,
    # that cell is treated as the upper-left occupied slot of the fab area.
    for bar_index, (_bar_label, bar, array_items, _array_labels) in enumerate(bar_items):
        for array_index, (array_label, array) in enumerate(array_items):
            match = FAB_AREA_PATTERN.search(array.detail)
            if match is None:
                if FAB_AREA_LABEL_PATTERN.search(array.detail):
                    raise ValueError(
                        "Fab Area must use format "
                        "'Fab Area (<width>mm x <height>mm)'."
                    )
                continue

            # In `Fab Area (<width>mm x <height>mm)`, the value before `x`
            # is the X-direction width and the value after `x` is Y height.
            fab_width = float(match.group(1))
            fab_height = float(match.group(2))
            if fab_width <= 0:
                raise ValueError("Fab Area width must be greater than zero.")
            if fab_height <= 0:
                raise ValueError("Fab Area height must be greater than zero.")

            # Convert physical Fab Area dimensions into whole occupied
            # array/bar slots. `ceil` ensures partial overlap excludes the slot.
            array_span = ceil(fab_width / array.width)
            bar_span = ceil(fab_height / bar.height)

            # Mark every slot covered by the fab area, clipping at the imported
            # table boundaries in case the declared area reaches past the edge.
            for occupied_bar_index in range(bar_index, bar_index + bar_span):
                if occupied_bar_index >= len(bar_items):
                    break

                occupied_bar_label, _occupied_bar, _occupied_array_items, occupied_array_labels = (
                    bar_items[occupied_bar_index]
                )
                for occupied_array_index in range(array_index, array_index + array_span):
                    if occupied_array_index >= len(occupied_array_labels):
                        break
                    excluded_slots.add((
                        occupied_bar_label,
                        occupied_array_labels[occupied_array_index],
                    ))

    return excluded_slots


def _select_array_include(
        cluster: Cluster,
        wafer_radius: float,
) -> Cluster:
    """Select arrays that are not fab area and whose acceptor is inside wafer.

    Fab Area cells use details such as `Fab Area (2.1mm x 0.5mm)`, where the
    number before `x` is width and the number after `x` is height. That physical
    area is converted to occupied array/bar slots and excluded. Empty bars are
    removed too.
    """
    selected_bars: dict[str, Bar] = {}
    fab_area_slots = _fab_area_excluded_slots(cluster)

    for bar_label, bar in cluster.bars.items():
        selected_arrays = {
            array_label: array
            for array_label, array in bar.arrays.items()
            if (bar_label, array_label) not in fab_area_slots
            if _array_is_available(array, cluster.quadrant, wafer_radius)
        }
        if selected_arrays:
            selected_bars[bar_label] = Bar(
                top_left=bar.top_left,
                arrays=selected_arrays,
                width=bar.width,
                height=bar.height,
            )

    if not selected_bars:
        raise _NoAvailableArraysError("Cluster has no selected arrays.")

    return Cluster(
        top_left=cluster.top_left,
        bars=selected_bars,
        width=cluster.width,
        height=cluster.height,
        quadrant=cluster.quadrant,
    )


def _test_die_center_from_array(
        array: Array,
        quadrant: int,
) -> Point:
    """Choose the acceptor center used for wafer-edge testing.

    Quadrants 1 and 4 use the rightmost die. Quadrants 2 and 3 use the
    leftmost die.
    """
    # For edge filtering, test the die closest to the outside of the wafer.
    if not array.dies:
        raise ValueError("Array must contain at least one die.")

    if quadrant in (1, 4):
        return max(
            (die.acceptor.center for die in array.dies.values()),
            key=lambda center: center[0],
        )
    if quadrant in (2, 3):
        return min(
            (die.acceptor.center for die in array.dies.values()),
            key=lambda center: center[0],
        )

    raise ValueError(f"Unsupported quadrant: {quadrant}")


def _point_inside_wafer_by_circle_y(
        point: Point,
        wafer_radius: float,
) -> bool:
    """Check whether a point is inside the wafer circle using its x value."""
    # For a wafer centered at the origin, compute the allowed y boundary at x.
    x, y = point
    if abs(x) > wafer_radius:
        return False

    wafer_abs_y = sqrt(wafer_radius ** 2 - x ** 2)
    return abs(y) <= wafer_abs_y


def _array_is_available(
        array: Array,
        quadrant: int,
        wafer_radius: float,
) -> bool:
    """Return whether one array should be kept for an edge cluster."""
    # Test the acceptor's precomputed edge-facing point rather than only the
    # acceptor center, so clipped acceptors are rejected.
    center = _test_die_center_from_array(array, quadrant)
    test_die = next(
        die
        for die in array.dies.values()
        if die.acceptor.center == center
    )
    return _point_inside_wafer_by_circle_y(test_die.acceptor.test_point, wafer_radius)


def _export_rows_for_cluster(
        cluster_label: str,
        cluster: Cluster,
) -> ExportTable:
    """Convert one cluster object to CSV-ready rows with millimeter values.

    The dictionary keys use `[mm]` because these are the internal geometry
    values. The GUI writer can emit different header labels without changing
    these numeric values.
    """
    rows: ExportTable = []

    for bar_label, bar in cluster.bars.items():
        for array_label, array in bar.arrays.items():
            for die_number, die in array.dies.items():
                center_x, center_y = die.acceptor.center
                # Flatten one die into one CSV-ready row.
                rows.append(
                    {
                        "tile_id": cluster_label,
                        "die_id": f"{int(bar_label):02d}{array_label}", #FA 2026-07-16: REMOVED PD DIE NUMBER FROM WAFER MAP
                        #"die_id": f"{int(bar_label):02d}{array_label}{die_number}", #FA 2026-07-16: COMMENTED OUT LINE THAT ADDS PD DIE NUMBER TO WAFER MAP
                        "xc_ref[mm]": _csv_number(center_x),
                        "yc_ref[mm]": _csv_number(center_y),
                        "xc_chip[mm]": _csv_number(center_x),
                        "yc_chip[mm]": _csv_number(center_y),
                        "width[mm]": _csv_number(die.width),
                        "height[mm]": _csv_number(die.height),
                        "Array detail": array.detail,
                    }
                )

    return rows


def _sort_rows_for_serpentine_probe_path(rows: ExportTable) -> ExportTable:
    """Return millimeter-valued CSV rows in a serpentine probe path.

    The prober starts at the highest Y row, moves left-to-right across X, then
    steps down to the next Y row and moves right-to-left. The X direction
    alternates for each lower Y row.

    >>> rows = [
    ...     {"die_id": "top-right", "xc_ref[mm]": 1.0, "yc_ref[mm]": 1.0},
    ...     {"die_id": "top-left", "xc_ref[mm]": 0.0, "yc_ref[mm]": 1.0},
    ...     {"die_id": "bottom-left", "xc_ref[mm]": 0.0, "yc_ref[mm]": 0.0},
    ...     {"die_id": "bottom-right", "xc_ref[mm]": 1.0, "yc_ref[mm]": 0.0},
    ... ]
    >>> [row["die_id"] for row in _sort_rows_for_serpentine_probe_path(rows)]
    ['top-left', 'top-right', 'bottom-right', 'bottom-left']
    """
    rows_by_y: dict[float, ExportTable] = {}
    for row in rows:
        y = float(row["yc_ref[mm]"])
        rows_by_y.setdefault(y, []).append(row)

    sorted_rows: ExportTable = []
    for y_index, y in enumerate(sorted(rows_by_y, reverse=True)):
        y_rows = sorted(
            rows_by_y[y],
            key=lambda row: (float(row["xc_ref[mm]"]), str(row["die_id"])),
        )
        if y_index % 2 == 1:
            y_rows.reverse()
        sorted_rows.extend(y_rows)

    return sorted_rows


def _export_clusters(
        clusters: ClusterMap,
        wafer_diameter: float,
        filter_arrays: bool = True,
) -> ExportTable:
    """Filter selected clusters and flatten them into serpentine export rows."""
    wafer_radius = wafer_diameter / 2
    export_rows: ExportTable = []
    for cluster_label, (cluster, status) in clusters.items():
        if status == "outside":
            continue

        if filter_arrays:
            try:
                cluster = _select_array_include(cluster, wafer_radius)
            except ValueError:
                continue

        export_rows.extend(
            _export_rows_for_cluster(
                cluster_label,
                cluster,
            )
        )

    return _sort_rows_for_serpentine_probe_path(export_rows)


def export_wafer(wafer: Wafer) -> ExportTable:
    """Filter the selected clusters on a wafer and flatten them for export."""
    return _export_clusters(
        wafer.selected_clusters_for_export(),
        wafer_diameter=wafer.diameter,
        filter_arrays=not wafer.arrays_filtered,
    )


if __name__ == '__main__':
    wafer_diameter_input = input("Wafer diameter [mm]: ").strip()
    array_table = rx("array_position_table.xlsx", "Cluster", 1)
    wafer = build_wafer(
        wafer_diameter=float(wafer_diameter_input),
        array_table=array_table,
        die_width=0.25,
        die_height=0.25,
        dies_per_array=4,
        array_side=0.025,
        acceptor_shape="circle",
        acceptor_delta_x=0.125,
        acceptor_delta_y=0.0725,
        acceptor_width=0.016,
        acceptor_height=0.016,
    )
    wafer.set_selected_clusters(set(wafer.clusters))
    export_data = export_wafer(wafer)
    print(f"Generated {len(export_data)} export rows.")
    if export_data:
        print(export_data[0])
