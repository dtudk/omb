#!/usr/bin/env python3

# Sample script to run analysis of output data from the code.

import logging
import typing as T
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from functools import reduce, singledispatch
from itertools import combinations, permutations
from pathlib import Path
from textwrap import dedent
from typing import Any, Literal

import click
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyparsing as pp
import xarray as xr
from pyparsing.core import Suppress
from xarray.core.dataset import Dataset

# Check that xarray works!
try:
    assert tuple(map(int, xr.__version__.split("."))) >= (2024, 9, 0), "xarray too old!"
except ValueError:
    pass

_log = logging.getLogger(__name__)


XRData: T.TypeAlias = xr.DataArray | xr.Dataset
XRGroup: T.TypeAlias = xr.core.groupby.DataArrayGroupBy | xr.core.groupby.DatasetGroupBy
XRDataT = T.TypeVar("T", *T.get_args(XRData))


def isxarrayobject(obj):
    """Small wrapper for ``isinstance(obj, (xr.{Dataset, DataArray}))``"""
    return isinstance(obj, (xr.Dataset, xr.DataArray))


def sequence_range(size, step):
    steps = []
    for _ in range(size // step):
        if steps:
            start = steps[-1].stop
        else:
            start = 0
        stop = min(start + step, size)
        steps.append(range(start, stop))
    start = steps[-1].stop
    if start != size:
        stop = min(start + step, size)
        steps.append(range(start, stop))
    return steps


def add_missing_attrs(ds: xr.Dataset):
    """Add attributes that are necessary for the complete data-knowledge

    Currently this will ensure that:

    - ``threads``
    - ``places``

    are present.
    """
    ds.attrs["threads"] = len(get_place_names(ds))
    ds.attrs["places"] = get_places(ds)


@xr.register_dataset_accessor("omb")
@xr.register_dataarray_accessor("omb")
class OMBAccessor:
    """Accessor for extracting benchmark specific data from the omb-driver utility

    This contains a set of coordinates defining their units, and their
    preferred scale (for plotting).
    """

    @dataclass
    class Coord:
        name: str
        dtype: Any
        description: str
        unit: Any = None
        scale: str | None = None

        def __eq__(self, value: str, /) -> bool:
            return self.name == value

    DATA = [
        Coord("method", "category", "Method"),
        Coord("kernel", "category", "Kernel"),
        Coord("first_touch", np.uint8, "Parallel first touch", "Y/N"),
        Coord("elem_bytes", np.uint8, "Bytes per element", "B"),
        Coord("size", np.float64, "Memory", "MB", "log"),
        Coord("time_min", np.float64, "Minimum time", "s", "log"),
        Coord("time_max", np.float64, "Maximum time", "s", "log"),
        Coord("time_avg", np.float64, "Average time", "s", "log"),
        Coord("time_std", np.float64, "Std. time", "s", "log"),
        Coord("bandwidth_gbs", np.float64, "Bandwidth", "GB/s", "linear"),
        Coord("gflops", np.float64, "Eff. FLOPS", "G/s", "log"),
    ]

    DIMS: T.Final = ["method", "kernel", "first_touch", "elem_bytes", "size"]
    DIM_DTYPES: T.Final = ["category", "category", np.uint8, np.uint8, np.float64]
    DIM_UNITS: T.Final = [None, None, "Y/N", "B", "MB"]
    DATA_COLUMNS: T.Final = DIMS + [
        "time_min",
        "time_avg",
        "time_std",
        "time_max",
        "bandwidth_gbs",
        "gflops",
    ]
    DATA_UNITS: T.Final = DIM_UNITS + ["s", "s", "s", "s", "GB/s", "G/s"]
    DATA_DTYPES: T.Final = DIM_DTYPES + [np.float64] * 6
    _obj: XRData

    def __init__(self, xarray_obj: XRData):
        self._obj = xarray_obj

    @classmethod
    def get_coord(cls, coord: str) -> Coord:
        """Return the coord object that has the key as `coord`"""
        return cls.DATA[cls.DATA.index(coord)]

    @property
    def nthreads(self) -> int:
        """Return number of threads in this run."""
        return len(self._obj.omb.place_names())

    def dims_alone(self) -> list[str]:
        """Return a list of the dimensions that are "singly" defined"""
        ds: XRData = self._obj
        dims = []
        for dim in ds.dims:
            if len(ds.coords[dim]) == 1:
                dims.append(dim)
        return dims

    def coords_alone(self) -> list[str]:
        """Return a list of the coords that are alone."""
        ds: XRData = self._obj
        coords = []
        for coord in ds.coords:
            if np.unique(ds.coords[coord].data).size == 1:
                coords.append(coord)
        return coords

    def fill_symmetric(self):
        """Fills in the missing data from a symmetric run"""
        ds: xr.Dataset = self._obj.copy()

        nbenchmarks = len(ds.coords["benchmark"])
        places = ds.omb.domain_names()
        if not places:
            places = ds.omb.place_names()

        # Get all unique places
        def uniq_union(a, b):
            """Return the union of a and the unique values of `b`"""
            return np.union1d(a, np.unique(b))

        unique_places = reduce(uniq_union, map(ds.coords.__getitem__, places))

        def get_overlapping_indices(coords, coord_places, linear_place):

            my_iter = zip(coord_places, linear_place)

            # Do a loop over the places for each of the coords
            # Consider when coord_places = [place_0, place_1]
            # and linear_place = [0, 1]
            # Then this will find the indices where we have
            #   place_0 == 0
            #   place_1 == 1
            place, value = next(my_iter)

            idx = (coords[place].values == value).nonzero()[0]
            for place, value in my_iter:
                idx = np.intersect1d(idx, (coords[place].values == value).nonzero()[0])
                if len(idx) == 0:
                    # quick escape...
                    break

            return idx

        # Common concatenation kwargs
        concat_kwargs = dict(dim="benchmark", data_vars="all", coords="all")

        # Convert to object as the length of the strings messes up things
        for place in places:
            ds.coords[place] = ds.coords[place].astype("O")

        # Loop over all place combinations.
        # This will create a lower triangular nested loop on all places.
        # If places = [0, 1, 2] and we have 2 places(threads)
        # Then it will create this loop:
        #  [0, 0]  # will never have a value
        #  [0, 1]
        #  [0, 2]
        #  [1, 1]  # will never have a value
        #  [1, 2]
        #  [2, 2]  # will never have a value
        concat_ds = []
        for ps in combinations(unique_places, len(places)):

            # Now figure out which combination that has the data!
            # This is the one that we'll copy out from
            ps_idx = []
            for comb in permutations(ps):
                ps_idx = get_overlapping_indices(ds.coords, places, comb)
                if len(ps_idx) > 0:
                    break

            if len(ps_idx) == 0:
                # We can't find any data-point, skip to next point!
                continue

            # get first matched data-point
            sub_ds = ds.isel(benchmark=ps_idx)

            # Now create the combinations
            for comb in permutations(ps):
                comb_idx = get_overlapping_indices(ds.coords, places, comb)
                if len(comb_idx) != 0:
                    # data-point already there
                    continue

                tmp_ds = sub_ds.assign_coords(dict(zip(places, comb)))

                # Reset coordinates to make it simpler to concatenate.
                concat_ds.append(tmp_ds.reset_coords(places))

        concat_ds.append(ds.reset_coords(places))

        ret_ds = xr.concat(concat_ds, **concat_kwargs).set_coords(places)

        # Convert back to string (apparently it does not work with astype(category))
        for place in places:
            ret_ds.coords[place] = ret_ds.coords[place].astype(np.str_)

        return ret_ds

    def drop_sel(self, coord, value):
        """Reduce the object to a subset based on the coordinates equal to the value"""
        ds: xr.Dataset = self._obj
        values = ds.coords[coord].values
        if isinstance(value, slice):
            start = value.start
            stop = value.stop
            if value.step != None:
                raise NotImplementedError("a defined step is not available")
            if start is None:
                idx = np.logical_not(values < stop).nonzero()[0]
            elif stop is None:
                idx = np.logical_not(start <= values).nonzero()[0]
            else:
                idx = np.logical_not(
                    np.logical_and(start <= values, values < stop)
                ).nonzero()[0]

        else:
            idx = np.logical_not(ds.coords[coord].values == value).nonzero()[0]
        return ds.isel(benchmark=idx)

    def sel(self, coord, value):
        """Reduce the object to a subset based on the coordinates equal to the value"""
        ds: xr.Dataset = self._obj
        values = ds.coords[coord].values
        if isinstance(value, slice):
            start = value.start
            stop = value.stop
            if value.step != None:
                raise NotImplementedError("a defined step is not available")
            if start is None:
                idx = (values < stop).nonzero()[0]
            elif stop is None:
                idx = (start <= values).nonzero()[0]
            else:
                idx = np.logical_and(start <= values, values < stop).nonzero()[0]

        else:
            idx = (ds.coords[coord].values == value).nonzero()[0]
        return ds.isel(benchmark=idx)

    def place_names(self, force: bool = False) -> list[str]:
        """Return the place-names of this object"""
        return get_place_names(self._obj, prefix="place", force=force)

    def domain_names(self) -> list[str]:
        """Return the place-names of this object"""
        return get_place_names(self._obj, prefix="domain", force=True)

    @staticmethod
    def read(file: str | Path) -> xr.Dataset:
        """Read a dataset benchmark and rearrange the indices"""

        # Read the benchmark and don't do anything else.
        ds = read_benchmark(file)

        # Get the dimensions that we'll use for the coordinates
        DIMS = ds.omb.DIMS
        places = ds.omb.place_names()
        ds = ds.set_coords(DIMS + places)

        # Add some default attributes
        add_missing_attrs(ds)
        return ds

    def info(self) -> dict:
        """Convert the object information into digestible data"""
        ds: xr.Dataset = self._obj
        info = {}

        MAX_LIST = 9

        # Cycle through data
        def extract_numeric(values):
            min = values.data.min()
            max = values.data.max()
            average = values.data.mean()
            uniq = np.unique(values.data)
            nuniq = len(uniq)
            # with few values, we just return the list
            if nuniq < MAX_LIST:
                return uniq.tolist()
            return dict(average=average, min=min, max=max, unique=nuniq)

        def extract_str(values):
            uniq = np.unique(values.data)
            nuniq = len(uniq)
            # with few values, we just return the list
            if nuniq < MAX_LIST:
                return uniq.tolist()
            return dict(unique=nuniq)

        def extract(values):
            try:
                if np.issubdtype(values.dtype, np.number):
                    return extract_numeric(values)
            except:
                pass
            return extract_str(values)

        coords = {}
        for coord in ds.coords:
            coords[coord] = extract(ds.coords[coord])

        info["coords"] = coords

        data = {}
        for variable, var_data in ds.data_vars.items():
            data[variable] = extract(var_data)
        info["variables"] = data

        return info


def read_benchmark(file: str | Path) -> xr.Dataset:
    """Reads a benchmark output of the benchmark run"""

    # first determine the places
    line = open(file).readline().split()

    places = line[: -len(xr.Dataset.omb.DATA_COLUMNS)]

    nplaces = len(places)
    places = [f"place_{i}" for i in range(nplaces)]
    dtypes = dict((place, str) for place in places)

    df = pd.read_csv(
        file,
        sep="\s+",
        names=places + xr.Dataset.omb.DATA_COLUMNS,
        dtype=dtypes,
        index_col=None,
    )

    df.index.rename("benchmark", inplace=True)

    # Try and create a new "size" column based
    # on rounded to nearest precision
    # This enables us to do groupby on the size.
    size = df["size"]
    min_size = size.min()
    precision = min_size / 1000
    decimals = int(np.log10(1 / precision))
    df["size"] = size.round(decimals)

    # Ensure all of the details are categories
    omb_access = xr.Dataset.omb
    conv = dict(zip(omb_access.DATA_COLUMNS, omb_access.DATA_DTYPES))
    conv.update(dict(map(lambda x: (x, "category"), places)))
    df = df.astype(conv)

    return df.to_xarray()


def merge_files(files: list[str | Path], reader=read_benchmark) -> xr.Dataset:
    """Read a list of files and merge them into a single dataarray"""

    # Read in the files, do some checks, and then merge them
    dss = [xr.DataArray.omb.read(file) for file in files]

    # Merge all data-stuff
    ds = xr.concat(dss, dim="benchmark", data_vars="all", coords="all")

    return ds


def _kill(ds: xr.Dataset) -> None:
    """Die, mainly used for debugging purposes in combination with ``.pipe(_kill)``"""
    import sys

    sys.exit(0)


def _debug(msg: T.Any, print_ds: bool = False):
    """Debug by printing additional text, used in a ``.pipe(_debug("hello"))`` call"""

    def func(ds):
        if msg in ("pack_affinities", "to_xarray"):
            print()
            print(msg)
            print(ds)
        return ds
        print()  # newline
        print(msg)
        # print(ds.coords)
        if print_ds:
            print(ds)
        return ds

    return func


def argsort_places(places) -> np.ndarray:
    """Return the indices that sorts a `places` list

    A place is a comma-separated specification.

    Examples
    --------

    Always sort according to the first thread placement:

    >>> places = ["0,4", "2,3", "2,1", "2"]
    >>> sorted_places(places)
    ['0,4', '2', '2,1', '2,3']
    """
    import re

    def convchar(arg):
        """Convert all arguments from chars to commas"""
        return re.sub(r"[^0-9]", ",", re.sub(r"^[^0-9.]", "", arg))

    # split the keys
    split_places = [list(map(int, convchar(place).split(","))) for place in places]

    # Count maximum number of places per place
    n_places = max([len(place) for place in split_places])

    # Expand split_places with the fill value for each placement
    # We use -1 one so entries with fewer places are *better*
    def expand(lst, fill: int = -1):
        if len(lst) < n_places:
            return lst + [fill] * (n_places - len(lst))
        return lst

    split_places = [expand(lst) for lst in split_places]
    # split_places = [x for x in np.array(split_places).T]
    split_places = np.array(split_places).T

    # reverse since lexsort does *last* first
    return np.lexsort(split_places[::-1])


def seq_remove(seq: list | tuple | set | dict, items) -> T.Any:
    """Remove `items` from `lst`, if they are there.

    This is a small utility for condensing the Python
    try ... except ... clause.
    """
    obj = type(seq)
    if isinstance(seq, (list, tuple, set)):
        return obj(filter(lambda x: x not in items, seq))

    # we assume it is some dict-type
    return obj(filter(lambda x: x[0] not in items, seq.items()))


@singledispatch
def sorted_places(places) -> list:
    """Return a places list where the entries are sorted

    A place is a comma-separated specification.

    Examples
    --------

    Always sort according to the first thread placement:

    >>> places = ["0,4", "2,3", "2,1", "2"]
    >>> sorted_places(places)
    ['0,4', '2', '2,1', '2,3']
    """
    idx = argsort_places(places)
    return [places[i] for i in idx]


@sorted_places.register
def _(da: XRData) -> XRDataT:
    """Returns `da` after having converted the `affinities` coordinate into separate
    coordinates.

    It also sorts each of the placements so that the data ordering is consistent.
    """
    place_names = get_place_names(da)

    # Now sort each place_name individually
    isel = {}
    for place in place_names:
        isel[place] = argsort_places(da.coords[place].values)

    return da.isel(isel)


def squeeze_coords(dx: type[XRDataT], coords: Sequence[str]) -> XRDataT:
    """Squeeze coordinates that have length 1 and in list `coords`

    Will remove any coordinates in `coords` with size 1.

    Parameters
    ----------
    dx :
        xarray data object
    coords :
        a sequence of strings for coordinate names that will be checked.

    Returns
    -------
    type(d) :
        a new data object with the len 1 coordinates moved to the attributes.
    """
    for coord in coords:
        uniq_coord = np.unique(dx[coord].data)
        if len(uniq_coord) == 1:
            dx.attrs[coord] = uniq_coord[0]
            dx = dx.reset_coords(coord, drop=True)
    return dx


def squeeze_dims(dx: type[XRDataT], dims: Sequence[str]) -> XRDataT:
    """Squeeze dims that have length 1 and in list `dims`

    Will remove any dimensions in `dims` with size 1.

    Parameters
    ----------
    dx :
        xarray data object
    dims :
        a sequence of strings for dimension names that will be checked.

    Returns
    -------
    type(d) :
        a new data object with the len 1 dimensions removed.
    """
    for dim in dims:
        if dim in dx.sizes:
            if dx.sizes[dim] == 1:
                dx = dx.squeeze(dim)
    return dx


def coords2attrs(dx: type[XRDataT], coords: Sequence[str]) -> XRDataT:
    """Convert coordinates to attributes so they won't be part of conversions to other
    data-formats"""
    for coord in coords:
        dx.attrs[coord] = dx.coords[coord].values
    return dx.drop_vars(coords)


def get_place_names(dx: XRData, prefix: str = "place", force: bool = False) -> list:
    r"""Retrieve a unique set of names for placement variables.

    For a dataset runned with :math:`n` threads, this will return a list of
    :math:`n` names.

    The list of places will be formatted as:

    >>> [f"place_{thread_id}" for thread_id in range(threads)]
    """
    threads = 0
    if force:
        pass  # just skip through
    elif "thread" in dx.dims:
        threads = dx.dims["thread"]

    elif "threads" in dx.attrs:
        threads = dx.attrs["threads"]

    elif hasattr(dx, "variables"):
        # manual discovery
        threads = 0
        while f"{prefix}_{threads}" in dx.variables:
            threads += 1

    if threads == 0:
        # manual discovery
        while f"{prefix}_{threads}" in dx.coords:
            threads += 1

    place_names = [f"{prefix}_{i}" for i in range(threads)]
    return place_names


def get_places(dx: XRData) -> list:
    """For all values of places, create a unique set of the places

    Additionally the places will be sorted using `np.lexsort` to account for
    places with multiple available placements.

    See Also
    --------
    sorted_places : the sorting algorithm once the unique places have been created
    """
    # Get the places, and split them.
    place_names = get_place_names(dx, force=True)

    # Collect the unique names
    places = set()
    for place in place_names:
        places |= set(dx.coords[place].values)

    # Convert to list
    places = list(places)

    return sorted_places(places)


def join_coords(
    dx: XRData, coords: Sequence[str], sep: str = " ", edgeitems: int = 2
) -> np.ndarray:
    """Join specific coordinates into a single coordinate element"""
    join_coords = [dx.coords[coord] for coord in coords]

    if edgeitems > 0 and len(join_coords) > edgeitems * 2 + 1:
        join_coords = join_coords[:edgeitems] + ["..."] + join_coords[-edgeitems:]

    tmp = []
    for jc in join_coords[:-1]:
        tmp.append(jc.astype(object) + sep)
    join_coords = tmp + [join_coords[-1]]

    # Merge the data
    join_coords = np.sum(join_coords, axis=0).astype(str, copy=False)

    return join_coords


def join_place_names(dx: XRData, sep: str = " ", edgeitems: int = 2) -> np.ndarray:
    """Join all combinations of places into a single place

    This will thus encompass all places into a single place array.

    E.g. ``place_0 = ['0', '1']`` and ``place_1 = ['3', '2']``
    will return ``['0 3', '1 2']``.

    This allows one to manage plots in meaningful ways, but is also powerful
    to create coordinates based on exact thread placements across all threads.

    Parameters
    ----------
    dx :
        the dataobject to work on
    sep:
        the separator used when joining the data variables.
    edgeitems:
        only concatenate the first and last `edgeitems` into a single entry.
        Add `"..."` in the middle.

    See Also
    --------
    get_place_names : method used to retrieve all the names of places
    """
    place_names = get_place_names(dx)

    return join_coords(dx, place_names, sep=sep, edgeitems=edgeitems)


debug_option = click.option("--debug", is_flag=True, default=False)


def add_options(options):
    def _add_options(func):
        for option in reversed(options):
            func = option(func)
        return func

    return _add_options


def _echo(obj):
    click.echo(obj)


def _pprint(obj):
    from rich.pretty import pprint

    pprint(obj)


# Ensure our context has the obj as a dictionary
@dataclass
class ExperimentStack:
    experiments: list[XRData] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.experiments)

    def __iter__(self):
        yield from self.experiments

    def push(self, experiment: XRData) -> None:
        """Push an experiment to the stack"""
        self.experiments.append(experiment)

    def pop(self):
        """Pops the latest experiment off the stack"""
        return self.experiments.pop()

    @property
    def experiment(self) -> XRData:
        """Returns the latest experiment off the stack"""
        return self.experiments[-1]


class CacheLevel(IntEnum):
    """Enum representing cache levels"""

    L1 = 1
    L2 = 2
    L3 = 3
    L4 = 4


class CacheType(Enum):
    """Enum representing cache types"""

    DATA = "data"
    INSTRUCTION = "instruction"
    UNIFIED = "unified"


@dataclass
class CPUCacheInfo:
    """
    A class to store CPU cache information.

    Attributes:
        level: Cache level (L1, L2, L3, L4)
        cache_type: Type of cache (data, instruction, or unified)
        size_kb: Cache size in kilobytes
        all_size_kb: Full cache size in kilobytes
        line_size: Cache line size in bytes (typically 64)
        associativity: Cache associativity (e.g., 8-way, 16-way)
        shared_cores: Number of CPU cores sharing this cache
        latency_cycles: Access latency in CPU cycles
        write_policy: Write policy (e.g., "write-back", "write-through")
        replacement_policy: Replacement policy (e.g., "LRU", "pseudo-LRU")
    """

    level: CacheLevel
    cache_type: CacheType
    size_kb: float
    shared_cores: int
    line_size: int = 64
    associativity: int = 8
    all_size_kb: float | None = None

    def __post_init__(self):
        """Validate cache information after initialization"""
        if self.size_kb <= 0:
            raise ValueError("Cache size must be positive")
        if self.shared_cores <= 0:
            raise ValueError("Number of shared cores must be positive")
        if self.line_size <= 0:
            raise ValueError("Cache line size must be positive")
        if self.all_size_kb is None:
            self.all_size_kb = self.shared_cores * self.size_kb

    @property
    def size_mb(self) -> float:
        """Return cache size in megabytes"""
        return self.size_kb / 1024

    @property
    def size_bytes(self) -> int:
        """Return cache size in bytes"""
        return self.size_kb * 1024

    def __str__(self) -> str:
        """Human-readable representation"""
        return (
            f"{self.level.name} {self.cache_type.value} cache: "
            f"{self.size_kb}KB, {self.associativity}-way, "
            f"shared by {self.shared_cores} core(s)"
        )

    def __gt__(self, other):
        return self.level > other.level

    def __lt__(self, other):
        return self.level < other.level

    def __eq__(self, other):
        return self.level == other.level


def parse_lscpu_c(text):
    """Parses the `lscpu -C` output in a consistent manner."""
    columns = None
    caches = []
    column_idx = {}
    for line in text.splitlines():
        fields = line.split()
        if not fields:
            continue

        if line.startswith("NAME"):
            columns = fields
            column_idx = dict((col, i) for i, col in enumerate(columns))
            continue

        # We are ready to parse!
        level = fields[column_idx["LEVEL"]]
        one_size = parse_size(fields[column_idx["ONE-SIZE"]])
        all_size = parse_size(fields[column_idx["ALL-SIZE"]])
        shared_cores = int(round(all_size / one_size))
        associativity = int(fields[column_idx["WAYS"]])
        type = fields[column_idx["TYPE"]]
        level = fields[column_idx["LEVEL"]]
        line_size = int(fields[column_idx["COHERENCY-SIZE"]])
        caches.append(
            CPUCacheInfo(
                CacheLevel["L" + level],
                cache_type=CacheType[type.upper()],
                size_kb=one_size,
                all_size_kb=all_size,
                line_size=line_size,
                associativity=associativity,
                shared_cores=shared_cores,
            )
        )
    return caches


def parse_size(
    size: str, default: Literal["B", "KB", "MB", "GB", "TB"] | None = None
) -> float:
    """Parse a size K|M|G into kB"""

    # Create the float word
    p_int = pp.Word(pp.nums)
    p_float = pp.Combine(p_int + "." + pp.Optional(p_int))

    number = pp.Or([p_int, p_float]).add_parse_action(lambda toks: float(toks[0]))

    if default is None:
        default = "none"
    default = default.upper()

    def suppress_suffixes(*suffixes):
        suffixes = [pp.Suppress(pp.CaselessLiteral(suffix)) for suffix in suffixes]
        match = pp.MatchFirst(suffixes)
        if suffixes[0] == default:
            return pp.Optional(match)
        return match

    b = number.copy().add_parse_action(lambda toks: toks[0] / 1024) + suppress_suffixes(
        "B"
    )
    kb = number.copy().add_parse_action(lambda toks: toks[0]) + suppress_suffixes(
        "KB", "K"
    )
    mb = number.copy().add_parse_action(
        lambda toks: toks[0] * 1024
    ) + suppress_suffixes("MB", "M")
    gb = number.copy().add_parse_action(
        lambda toks: toks[0] * 1024**2
    ) + suppress_suffixes("GB", "G")
    tb = number.copy().add_parse_action(
        lambda toks: toks[0] * 1024**3
    ) + suppress_suffixes("TB", "T")

    return (mb | gb | tb | kb | b)[1].parse_string(size)[0]


@dataclass
class CPUInfo:
    cores: int = 1
    threads: int = 1
    caches: CPUCacheInfo | None = None
    sockets: int = 1


@dataclass
class ExperimentContext:
    stack: ExperimentStack = field(default_factory=ExperimentStack)
    progress: Any = None
    cpuinfo: Any = None
    debug: bool = False

    def create_progressbar(self, *args, **kwargs):
        """Creates a context progress bar for tracking details."""
        self.progress = click.progressbar(*args, **kwargs)


# Define basic stuff
CONTEXT_SETTINGS = dict(help_option_names=["-h", "--help"])
pass_exps = click.make_pass_decorator(ExperimentContext, ensure=True)
arg_experiment = click.argument(
    "experiment",
    type=click.Path(exists=True),
    nargs=1,
    # Ensure the files gets processed upon call!
    # TODO ensure it allows multiple=True
    callback=lambda ctx, param, value: merge_files([value]),
)


# Define our command groups
@click.group(chain=True, invoke_without_command=True, context_settings=CONTEXT_SETTINGS)
@debug_option
@arg_experiment
@pass_exps
def cli(exps: ExperimentContext, debug: bool, experiment):
    """Initial formulation of the CLI used for the analyzation."""
    exps.stack.push(experiment)
    exps.debug = debug
    if debug:
        _pprint(experiment)


@cli.command("push")
@debug_option
@arg_experiment
@pass_exps
def push_experiment(exps: ExperimentContext, debug: bool, experiment):
    """Add a new experiment to the stack to analyze"""
    debug = debug or exps.debug
    exps.stack.push(experiment)
    if debug:
        _pprint("pushing experiment to stack:")
        _pprint(experiment)


@cli.command("pop")
@debug_option
@pass_exps
def pop_experiment(exps: ExperimentContext, debug: bool):
    """Removes the latest experiment from the stack"""
    debug = debug or exps.debug
    if debug:
        _pprint("popping experiment from stack...")
    exps.stack.pop()


@cli.command("merge")
@debug_option
@arg_experiment
@pass_exps
def merge_experiment(exps: ExperimentContext, debug: bool, experiment):
    """Merge more experiments together"""
    debug = debug or exps.debug

    old_experiment = exps.stack.pop()
    experiment = xr.concat([old_experiment, experiment])
    if debug:
        _pprint("merge_experiment:")
        _pprint(experiment)
    exps.stack.push(experiment)


@cli.command("select")
@debug_option
@click.argument("select", type=str)
@pass_exps
def select_experiment(exps: ExperimentContext, debug: bool, select: str):
    """Reduce the data-array by selecting a certain value from a coordinate."""
    debug = debug or exps.debug

    # Get latest experiment
    ds = exps.stack.experiment

    try:
        name_coord, value = select.split("=", maxsplit=1)
        if debug:
            _pprint(f"select_experiment: {select} -> {name_coord} = {value}")
        # extract coord
        coord = ds.coords[name_coord]
    except ValueError:
        name_coord = select
        if debug:
            _pprint(f"select_experiment: {select} -> {name_coord}")
        value = None

    def conv(coord, value):
        try:
            # try and see if the value is a size
            # To MB, parse_size defaults to kB
            value = parse_size(value) / 1024
        except pp.ParseException:
            pass
        try:
            return coord.dtype.type(value)
        except TypeError:
            pass  # likely not a numpy dtype, so we assume it's a string
        except ValueError:
            return None
        return value

    if value is None:
        # variable extraction
        ds = ds[name_coord]

    elif ":" in value:
        # We are doing a ranged selection
        r_min, r_max = value.split(":")
        r_min = conv(coord, r_min)
        r_max = conv(coord, r_max)
        sl = slice(r_min, r_max)
        ds = ds.omb.sel(name_coord, sl)
        if debug:
            _pprint(f"select_experiment: {value} -> {sl!s}")

    else:
        value = conv(coord, value)
        ds = ds.groupby(name_coord)[value]
        if debug:
            _pprint(f"select_experiment: {name_coord}={value!s}")

    exps.stack.push(ds)


@cli.command("drop")
@debug_option
@click.argument("drop", type=str)
@pass_exps
def drop_experiment(exps: ExperimentContext, debug: bool, drop: str):
    """Reduce the data-array by removing a certain value from a coordinate."""
    debug = debug or exps.debug

    # Get latest experiment
    ds = exps.stack.experiment

    try:
        name_coord, value = drop.split("=", maxsplit=1)
        # extract coord
        coord = ds.coords[name_coord]
    except ValueError:
        name_coord = drop
        value = None

    def conv(coord, value):
        try:
            return coord.dtype.type(value)
        except TypeError:
            pass  # likely not a numpy dtype, so we assume it's a string
        except ValueError:
            return None
        return value

    if value is None:
        # variable extraction
        ds = ds.drop_vars(name_coord)

    elif ":" in value:
        # We are doing a ranged selection
        r_min, r_max = value.split(":")
        r_min = conv(coord, r_min)
        r_max = conv(coord, r_max)
        ds = ds.omb.drop_sel(name_coord, slice(r_min, r_max))

    else:
        value = conv(coord, value)
        ds = ds.omb.drop_sel(name_coord, value)

    exps.stack.push(ds)


@cli.command("domain")
@debug_option
@click.argument("domains", type=str)
@click.option("--debug", is_flag=True, default=False)
@click.option(
    "--reduce",
    "reduce_func",
    type=click.Choice(["max", "min", "avg", "mean", "average", "median"]),
    default="max",
    show_choices=True,
)
@pass_exps
def domain_experiment(
    exps: ExperimentContext, debug: bool, domains: str, reduce_func: str
):
    """Combine several places into separate *domains*."""
    debug = debug or exps.debug
    if debug:
        _pprint("domain_experiment: {domains}")

    # Get latest experiment
    ds = exps.stack.experiment
    reduce_func = {"avg": "mean", "average": "mean"}.get(reduce_func, reduce_func)

    pint = pp.Word(pp.nums).add_parse_action(lambda toks: int(toks[0]))
    COLON = pp.Suppress(":")
    NOT_COLON = pp.NotAny(":")
    LBRACE, RBRACE = pp.Literal.using_each("{}")
    BRACES = pp.Or([LBRACE, RBRACE])
    NOT_BRACES = pp.NotAny(BRACES)

    def OrGroups(*exprs):
        return pp.Or([pp.Group(expr) for expr in exprs])

    delim: str = ","
    max_res = len(ds.attrs["places"])
    cur_res = -1

    def res_i(toks):
        return int(toks[0])

    def lr(start, stop, stride):
        nonlocal cur_res
        res = list(range(start, stop, stride))
        if not res:
            print(res)
            raise ValueError(
                "Unspecified domain stride, resulting in a domain of 0 places"
            )
        cur_res = max(max(res), cur_res)
        return res

    def res_iCiCi(toks):
        start, stop, stride = toks
        return lr(start, stop, stride)

    def res_iCi(toks):
        start, stop = toks
        return lr(start, stop, 1)

    def res_CiCi(toks):
        nonlocal cur_res
        stop, stride = toks
        return lr(cur_res + 1, stop, stride)

    def res_Ci(toks):
        nonlocal cur_res
        return lr(cur_res + 1, cur_res + 1 + toks[0], 1)

    def res_CCi(toks):
        nonlocal cur_res, max_res
        return lr(cur_res + 1, max_res, toks[0])

    res = pint("res")
    res_interval = OrGroups(
        (res + COLON + pint("num-places") + COLON + pint("stride")).add_parse_action(
            res_iCiCi
        )  # MatchFirst
        | (res + COLON + pint("num-places")).add_parse_action(res_iCi)
        | res,
        # The following are specific to our usage (automatic handling
        # of start resource)
        (COLON + pint("num-places") + COLON + pint("stride")).add_parse_action(
            res_CiCi
        )  # MatchFirst
        | (COLON + pint("num-places")).add_parse_action(res_Ci),
        (COLON + COLON + pint("stride")).add_parse_action(res_CCi),
    )("res-interval")
    res_list = pp.DelimitedList(res_interval, delim=delim + NOT_BRACES)

    place = pp.nested_expr(LBRACE, RBRACE, content=res_list)("place")
    p_interval = (
        OrGroups(
            place + pp.Group(COLON + COLON + pint("stride")),
            place
            + pp.Group(
                COLON + pint("num-places") + COLON + pint("stride")
            )  # MatchFirst
            | place + pp.Group(COLON + pint("num-places")),
        )
        | place
    )("p-interval")

    grammar = pp.DelimitedList(p_interval | res_interval)

    place_domains = []

    def extract_domain(result):
        if debug:
            _pprint(f"extract_domain: {result}")
        return reduce(lambda a, b: a + list(b), result, [])

    for result in grammar.parse_string(domains, parse_all=True):
        if debug:
            _pprint(f"domain_result: {result}")
        if isinstance(result[0], pp.ParseResults):
            if not isinstance(result[0][0], pp.ParseResults):
                # a direct subset
                place_domains.append(extract_domain(result))
            else:
                # nested, so {..}:?
                assert len(result) == 2
                # a simple domain
                domain = np.array(extract_domain(result[0]), dtype=np.int32)

                cur_res = max(cur_res, domain.max())
                stride = len(domain)
                strides = result[1]
                cur_range = max_res - cur_res
                if "stride" in strides:
                    num_places = cur_range // strides["stride"]
                    stride = strides["stride"]
                if "num-places" in strides:
                    num_places = strides["num-places"]

                for dist in range(num_places):
                    place_domains.append(domain + dist * stride)
                    max_res = max(max_res, place_domains[-1].max())
            max_res = max(max_res, place_domains[-1].max())
        else:
            place_domains.append(list(result))

    def add_domain(ds, domains):
        """Add domains as new coords."""
        add_coords = {}
        domains = [np.asarray(domain).astype(np.str_) for domain in domains]
        for place in ds.omb.place_names(force=True):
            if debug:
                _pprint(f"domain_place: {place}")
            place_id = place.split("_")[1]
            # For places where there are multiple locations (e.g. 0,1)
            place_coord = ds.coords[place].astype(np.str_).str.split("split", ",")
            # Copy it so we can re-create a new domain specification.
            domain_coord = ds.coords[place].copy().astype(np.str_)
            domain_coord.name = f"domain_{place_id}"
            # clean the actual place, we'll fill it later.
            domain_coord[:] = ""
            for i, domain in enumerate(domains):
                # check along the split and reduce along split dimension
                idx = place_coord.isin(domain).any(dim="split")
                domain_coord[idx] = domain_coord[idx].str.cat(" ", str(i))
            add_coords[domain_coord.name] = domain_coord.str.lstrip()

        return ds.assign_coords(add_coords)

    if isinstance(ds, XRGroup):
        # we will create a new group
        raise NotImplementedError
    else:
        if debug:
            _pprint(ds)
        ds = add_domain(ds, place_domains)
        places = ds.omb.place_names()
        domains = ds.omb.domain_names()
        if debug:
            _pprint(np.unique(places))
            _pprint(np.unique(domains))

        # get the rest of the coords which we will
        # group over
        coords = list(filter(lambda c: c not in places, ds.coords))
        del coords[coords.index("benchmark")]
        if debug:
            _pprint("reduce on grouped: " + str(coords))
        ds = ds.drop_vars(places).groupby(coords)
        ds = (
            getattr(ds, reduce_func)()
            .to_dataframe()
            .reset_index()
            .rename_axis("benchmark")
            .to_xarray()
            .set_coords(coords)
        )

    # Finally, we need to remove all na along the variables
    exps.stack.push(ds.dropna("benchmark", how="all"))


@cli.command("groupby")
@debug_option
@click.argument("groupby", type=str)
@pass_exps
def groupby_experiment(exps: ExperimentContext, debug: bool, groupby: str):
    """Create a groupby object that will be used for subsequent details."""
    debug = debug or exps.debug

    groupby = groupby.split(",")
    if debug:
        _pprint(f"groupby_experiment: {groupby!s}")

    # Get latest experiment and group it
    ds = exps.stack.experiment
    print(ds)
    ds = ds.groupby(groupby)

    exps.stack.push(ds)


@cli.command()
@pass_exps
def symmetrize(exps: ExperimentContext):
    """Symmetrizes placement data"""
    ds: xr.Dataset = exps.stack.experiment.omb.fill_symmetric()
    exps.stack.push(ds)


@cli.result_callback()
def call_show_if_applicable(plots, *arguments, **kwargs):
    """Forcefully call .show in case any plotting utilities has been called.

    This will check if the plots have return values and whether they are plots.
    If the command `show` hasn't been called, it will call it..
    """
    show = False
    if not all([p is None for p in plots]):
        show = True

    if "plt.show()" in plots:
        show = False
    if show:
        plt.show()


@cli.command()
def show():
    """Shows the plots that has been collected so far.

    This will automatically be called if plots have been produced but not
    shown.
    """
    plt.show()
    return "plt.show()"


def info(exps: ExperimentContext, coord, variable):
    """Shows information for the current experiment (after any grouping etc.)"""
    ds: XRData | XRGroup = exps.stack.experiment

    if isinstance(ds, XRGroup):
        for value, grp in ds:
            _pprint(f"groupers = {[g.group.name for g in ds.groupers]}")
            exps.stack.push(grp)
            info(exps, coord, variable)
            exps.stack.pop()
            _pprint("\n")
        return

    if not coord and not variable:
        _pprint(ds)
        _pprint(ds.omb.info())
        return

    for c in coord:
        C = ds.coords[c]
        _echo(f"Coord: {c} shape={C.shape}")
        _pprint(C)

    for v in variable:
        V = ds.variables[v]
        _echo(f"Variable: {v} shape={V.shape}")
        _echo(V)


@cli.command("info")
@click.option("-c", "--coord", type=str, multiple=True)
@click.option("-v", "--variable", type=str, multiple=True)
@pass_exps
def info_command(exps: ExperimentContext, coord: str, variable: str):
    """Shows information for the current experiment (after any grouping etc.)"""
    info(exps, coord, variable)


plot_save = click.option(
    "-s",
    "--save",
    type=str,
    default=None,
    help=dedent(
        """Store the images in a output file using 'plt.savefig`.

                         Use {group} to input the currently grabbed group values in the
                         filename."""
    ),
)


def save_fig(fig, filename):
    """Save `plot` as the filename `filename`"""
    if Path(filename).suffix not in ".png .svg .pdf":
        filename = filename + ".png"
    fig.savefig(filename)


@dataclass
class OptionDataArrayHasCoords:
    options: list[str] = field(default_factory=list)

    def get_default(self, ds) -> str:
        """Determine which of the options are the required ones"""
        if isinstance(ds, XRData):
            for option in self.options:
                if option in ds.coords:
                    return option
        else:
            idx = next(iter(ds.groups.keys()))
            ds = ds[idx]
            return self.get_default(ds)
        raise ValueError("Could not find a suitable key")


def common_plot_options(*options, **arguments):
    opts = []
    append = opts.append

    def parse_name(arg):
        if arg.startswith("__"):
            arg = arg.replace("_", "-")
            if len(arg) == 3:  # single letter option
                return arg[1:], arg
        return [arg]

    for argument, default in arguments.items():

        if argument.startswith("__"):
            args = parse_name(argument)
            append(click.option(*args, type=str, default=default))
        else:
            append(click.argument(argument, type=str, default=default))

    for option in options:
        append(click.option(option, type=str, default=None))

    return add_options(opts)


def _get_coord_scale(da, coord, scale) -> str:
    """Retrieve the scale of a certain coordinate through the omb.DATA field."""
    try:
        info = da.omb.get_coord(coord)
        return scale or info.scale
    except:
        return scale


def _get_coord_wrap(da, coord) -> int:
    """Calculate the optimal # of cols for splitting a faceted grid."""
    coord = da.coords[coord]

    n = len(coord)
    if n == 0:
        # nothing to plot...
        return None

    n = max(1, int(n**0.5 + 0.51))
    return n


def _prepare_data(ds, data, all_axis_coords):
    """Prepare data consistently across different plotting functionality."""
    # Extract y
    if isinstance(ds, xr.Dataset):
        da = ds[data]
    else:
        # it should already be a DataArray
        da = ds

    # Remove single coords so the plotting won't get confused
    lone_coords = da.omb.coords_alone()
    # Do not remove coords that we wish to plot.
    lone_coords = seq_remove(lone_coords, all_axis_coords)

    # When squeezing the coordinates, we are moving them to the attributes.
    da = squeeze_coords(da, lone_coords)

    # Group them together
    try:
        da = da.to_dataframe().set_index(all_axis_coords).to_xarray()[data]
    except ValueError as ve:
        if "non-unique MultiIndex into xarray" in str(ve):
            da = da.to_dataframe().set_index(all_axis_coords)
            cols = da.columns.to_numpy()
            cols = cols[cols != data]
            raise ValueError(
                dedent(
                    f"""\

                    The dataset contains columns that should be grouped/selected.

                    Please look at data in the columns: {" ".join(cols)}."""
                )
            ) from None

    # Sort the place names (just to ensure its aligned)
    da: XRData = sorted_places(da)

    # xarray/matplotlib can't plot category elements (has to be converted to str)
    conv = {}
    for place in da.omb.place_names() + da.omb.domain_names():
        if place in da.coords:
            conv[place] = da.coords[place].astype(np.str_)
    da = da.assign_coords(conv)
    return da


def imshow(da, x, y, data, col, row, xscale, yscale):
    """Actual imshow-plot function"""
    defaults = dict(
        x=x,
        y=y,
        col=col,
        cmap="cividis",
        xscale=_get_coord_scale(da, x, xscale),
        yscale=_get_coord_scale(da, y, yscale),
    )
    if row is None:
        defaults["col_wrap"] = _get_coord_wrap(da, col)
    else:
        defaults["row"] = row

    data_info = da.omb.get_coord(data)
    da.attrs["standard_name"] = data_info.description
    da.attrs["units"] = data_info.unit

    return da.plot.imshow(**defaults)


@cli.command("imshow")
@common_plot_options(
    "--row",
    "--col",
    "--xscale",
    "--yscale",
    __x="not-found",
    __y="not-found",
    __data="bandwidth_gbs",
)
@plot_save
@pass_exps
def imshow_command(exps, x, y, data, xscale, yscale, row, col, save):
    """Create a faceted imshow

    Advanced plotting functionality for plotting row/col data.
    It respects the `groupby` command and will create a plot *per group*.
    """

    # get latest experiment in stack
    ds: XRData | XRGroup = exps.stack.experiment

    x = OptionDataArrayHasCoords([x, "place_0", "domain_0"])
    x = x.get_default(ds)
    y = OptionDataArrayHasCoords([y, "place_1", "domain_1"])
    y = y.get_default(ds)

    # Gather all coords that are requested.
    all_axis_coords = [x, y, row, col]
    all_axis_coords = list(filter(lambda coord: coord, all_axis_coords))
    if exps.debug:
        _pprint(f"all_axis_coords {all_axis_coords!s}")

    def _plot(ds):
        da = _prepare_data(ds, data, all_axis_coords)
        if exps.debug:
            _pprint(da)
        return imshow(da, x, y, data, col, row, xscale, yscale)

    plots = []
    if isinstance(ds, XRGroup):
        name = ds.groupers[0].group.name
        name_data = OMBAccessor.get_coord(name)

        for value, grp in ds:
            p = _plot(grp)
            p.fig.suptitle(f"{name_data.description} = {value}")
            if save:
                save_fig(p.fig, save.format(group=value))
            plots.append(p)

    else:
        p = _plot(ds)
        if save:
            save_fig(p.fig, save.format(group=""))
        plots.append(p)
    return plots


def line(da, x, y, col, row, xscale, yscale, hue):
    """Actual line-plot function"""

    defaults = dict(
        x=x,
        col=col,
        xscale=_get_coord_scale(da, x, xscale),
        yscale=_get_coord_scale(da, y, yscale),
    )
    if row is None:
        defaults["col_wrap"] = _get_coord_wrap(da, col)
    else:
        defaults["row"] = row

    if hue is not None:
        defaults["hue"] = hue

    y_info = da.omb.get_coord(y)
    da.attrs["standard_name"] = y_info.description
    da.attrs["units"] = y_info.unit

    return da.plot.line(**defaults)


@cli.command("line")
@debug_option
@common_plot_options(
    "--row", "--col", "--xscale", "--yscale", "--hue", __x="size", __y="bandwidth_gbs"
)
@pass_exps
def line_command(exps, debug: bool, x, y, xscale, yscale, row, col, hue):
    """Create a faceted line plot

    Advanced plotting functionality for plotting row/col data.
    It respects the `groupby` command and will create a plot *per group*.
    """
    debug = debug or exps.debug

    # get latest experiment in stack
    ds: XRData | XRGroup = exps.stack.experiment

    # Gather all coords that are requested.
    all_axis_coords = [x, row, col, hue]
    all_axis_coords = list(filter(lambda coord: coord, all_axis_coords))

    def _plot(ds):
        da = _prepare_data(ds, y, all_axis_coords)
        if debug:
            _pprint("line_command:")
            _pprint(da)
        return line(da, x, y, col, row, xscale, yscale, hue)

    plots = []
    if isinstance(ds, XRGroup):
        name = ds.groupers[0].group.name
        try:
            name_data = OMBAccessor.get_coord(name)
        except ValueError:
            # We have to create a fake one
            name_data = OMBAccessor.Coord(name, name, name)

        for value, grp in ds:
            p = _plot(grp)
            p.fig.suptitle(f"{name_data.description} = {value}")
            plots.append(p)

    else:
        p = _plot(ds)
        plots.append(p)

    return plots


if __name__ == "__main__":
    cli()
