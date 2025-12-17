#!/usr/bin/env python3

# Sample script to run analysis of output data from the code.

from dataclasses import dataclass, field
import logging
from textwrap import dedent
import typing as T
from collections.abc import Sequence
from functools import reduce, singledispatch
from itertools import combinations, permutations
from pathlib import Path
from typing import Any

import click
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xarray as xr
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
    place_names = get_place_names(dx)

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
class ExperimentSelector:
    experiments: list[XRData] = field(default_factory=list)
    options: dict = field(default_factory=dict)

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


# Define basic stuff
CONTEXT_SETTINGS = dict(help_option_names=["-h", "--help"])
pass_exps = click.make_pass_decorator(ExperimentSelector, ensure=True)
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
def cli(exps: ExperimentSelector, debug, experiment):
    """Initial formulation of the CLI used for the analyzation."""
    exps.push(experiment)
    if debug:
        _pprint(experiment)


@cli.command("push")
@debug_option
@arg_experiment
@pass_exps
def push_experiment(exps: ExperimentSelector, debug, experiment):
    """Add a new experiment to the stack to analyze"""
    exps.push(experiment)
    if debug:
        _pprint(experiment)


@cli.command("pop")
@pass_exps
def pop_experiment(exps: ExperimentSelector):
    """Removes the latest experiment from the stack"""
    exps.pop()


@cli.command("merge")
@debug_option
@arg_experiment
@pass_exps
def merge_experiment(exps: ExperimentSelector, debug, experiment):
    """Merge more experiments together"""
    old_experiment = exps.pop()
    experiment = xr.concat([old_experiment, experiment])
    if debug:
        _pprint(experiment)
    exps.append(experiment)


@cli.command("select")
@click.argument("select", type=str)
@pass_exps
def select_experiment(exps: ExperimentSelector, select: str):
    """Reduce the data-array by selecting a certain value from a coordinate."""
    # Get latest experiment
    ds = exps.experiment

    try:
        name_coord, value = select.split("=", maxsplit=1)
        # extract coord
        coord = ds.coords[name_coord]
    except ValueError:
        name_coord = select
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
        ds = ds[name_coord]

    elif ":" in value:
        # We are doing a ranged selection
        r_min, r_max = value.split(":")
        r_min = conv(coord, r_min)
        r_max = conv(coord, r_max)
        ds = ds.omb.sel(name_coord, slice(r_min, r_max))

    else:
        value = conv(coord, value)
        ds = ds.groupby(name_coord)[value]

    exps.push(ds)


@cli.command("domain")
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
    exps: ExperimentSelector, domains: str, reduce_func: str, debug: bool
):
    """Combine several places into separate *domains*."""
    import pyparsing as pp

    # Get latest experiment
    ds = exps.experiment
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
    max_res = np.array(ds.attrs["places"], dtype=np.int32).max()
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
        return lr(cur_res + 1, toks[0], 1)

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

    def has_keys(result, *keys):
        for key in keys:
            if key not in result:
                return False
        return True

    place_domains = []

    def extract_domain(result):
        return reduce(lambda a, b: a + list(b), result, [])

    for result in grammar.parse_string(domains, parse_all=True):
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
        else:
            place_domains.append(list(result))

    def add_domain(ds, domains):
        """Add domains as new coords."""
        add_coords = {}
        domains = [domain.astype(np.str_) for domain in domains]
        for place in ds.omb.place_names():
            place_id = place.split("_")[1]
            place_coord = ds.coords[place]
            domain_coord = place_coord.copy().astype(np.str_)
            domain_coord.name = f"domain_{place_id}"
            # clean the actual place
            domain_coord[:] = ""
            for i, domain in enumerate(domains):
                # print(f"{i = } {domain = }")
                idx = place_coord.isin(domain)
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
    exps.push(ds.dropna("benchmark", how="all"))


@cli.command("groupby")
@click.argument("groupby", type=str)
@pass_exps
def groupby_experiment(exps: ExperimentSelector, groupby: str):
    """Create a groupby object that will be used for subsequent details."""

    # Get latest experiment
    ds = exps.experiment

    ds = ds.groupby(groupby.split(","))
    exps.push(ds)


@cli.command()
@pass_exps
def symmetrize(exps):
    """Symmetrizes placement data"""
    ds: xr.Dataset = exps.experiment.omb.fill_symmetric()
    exps.push(ds)


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


def info(exps, coord, variable):
    """Shows information for the current experiment (after any grouping etc.)"""
    ds: XRData | XRGroup = exps.experiment

    if isinstance(ds, XRGroup):
        for value, grp in ds:
            _pprint(f"groupers = {[g.group.name for g in ds.groupers]}")
            exps.push(grp)
            info(exps, coord, variable)
            exps.pop()
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
def info_command(exps, coord, variable):
    """Shows information for the current experiment (after any grouping etc.)"""
    info(exps, coord, variable)


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
@debug_option
@common_plot_options(
    "--row",
    "--col",
    "--xscale",
    "--yscale",
    __x="place_0",
    __y="place_1",
    __data="bandwidth_gbs",
)
@pass_exps
def imshow_command(exps, debug, x, y, data, xscale, yscale, row, col):
    """Create a faceted imshow

    Advanced plotting functionality for plotting row/col data.
    It respects the `groupby` command and will create a plot *per group*.
    """

    # get latest experiment in stack
    ds: XRData | XRGroup = exps.experiment

    # Gather all coords that are requested.
    all_axis_coords = [x, y, row, col]
    all_axis_coords = list(filter(lambda coord: coord, all_axis_coords))

    def _plot(ds):
        da = _prepare_data(ds, data, all_axis_coords)
        if debug:
            _pprint(da)
        return imshow(da, x, y, data, col, row, xscale, yscale)

    plots = []
    if isinstance(ds, XRGroup):
        name = ds.groupers[0].group.name
        name_data = OMBAccessor.get_coord(name)

        for value, grp in ds:
            p = _plot(grp)
            p.fig.suptitle(f"{name_data.description} = {value}")
            plots.append(p)

    else:
        p = _plot(ds)
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
    "--row", "--col", "--xscale", "--yscale", "--hue", __x="size", y="bandwidth_gbs"
)
@pass_exps
def line_command(exps, debug, x, y, xscale, yscale, row, col, hue):
    """Create a faceted line plot

    Advanced plotting functionality for plotting row/col data.
    It respects the `groupby` command and will create a plot *per group*.
    """

    # get latest experiment in stack
    ds: XRData | XRGroup = exps.experiment

    # Gather all coords that are requested.
    all_axis_coords = [x, row, col, hue]
    all_axis_coords = list(filter(lambda coord: coord, all_axis_coords))

    def _plot(ds):
        da = _prepare_data(ds, y, all_axis_coords)
        if debug:
            _pprint(da)
        return line(da, x, y, col, row, xscale, yscale, hue)

    plots = []
    if isinstance(ds, XRGroup):
        name = ds.groupers[0].group.name
        name_data = OMBAccessor.get_coord(name)

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
