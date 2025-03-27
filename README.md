
# `omb`

The OpenMP benchmark suite.

This small utility program enables one to benchmark various OpenMP
things.

Currently, it expands on the [STREAM](http://www.cs.virginia.edu/stream/ref.html)
implementation. Allowing many more configurations, some changes, but also
porting it to FORTRAN.

The FORTRAN implementation is pretty standard, but a little verbose due to
using pre-processing via [fypp](https://github.com/aradi/fypp).


## Installation

Installing this small utility requires:

- A FORTRAN compiler, currently auto-detecting GNU or Intel
  - if support is needed for other compilers, please
    open an issue.
- A functional OpenMP implementation (>=4.5).
  - if support is needed for older OpenMP implementations, please
    open an issue.

That's it!


Building is straightforward, using standardized CMake variables.
`CMAKE_INSTALL_PREFIX` is obeyed.
```shell
cmake -S. -Bobj
cmake --build $obj -v
```
which builds an executable `omb` + drivers for running `omb` in
unique thread-placement combinations.

Please ensure that all optimizations are enabled to enable
a full benchmark (compiling with `-O1` will generally show
worse performance than expected).


### Controlling allocation behavior

There are certain CMake flags that allows one to compile `omb` in various
formats (e.g. `cmake ... -DOMB_INT_KIND=...`).

- `OMB_INT_KIND`
  Controls the integer kind for the loop and size counters.
  It defaults to the 64-byte integer to allow large arrays.

- `OMB_ALLOC_TYPE`
  Fortran allows 3 different ways of allocating memory.
  In `omb` all allocations and array declarations are done
  in a single subroutine. Hence, the influence of the array
  declarations can impact performance.

  - `stack`

    ```fortran
    real :: a(N)
    ```
    Be sure to set an unlimited stack size before running!

  - `allocatable`

    ```fortran
    real, allocatable :: a(:)
    allocate(a(N))
    ```

  - `pointer`

    ```fortran
    real, pointer :: a(:) => null()
    allocate(a(N))
    ```

- `OMB_TIMING`
  By default, `omb` will use the OpenMP library timing routines.
  However, one can selectively use the fortran intrinsics (`system_clock`).

  Please compile `omb`, then run `omb -env` and check the timing precision
  of both, they are typically the same precision. Select the one with
  the highest precision (smallest number).

  - `omp` (default)

    Uses the OpenMP library `omp_get_wtime`

  - `systemclock`

    Use the fortran intrinsic `system_clock`.



## Running

This benchmark system has quite a bit of options.
For the most up to date options, please refer to the help
of the program: `omb --help`.

Here are the most commonly used options for `omb`:

| Flag | Behaviour |
| ---- | --------- |
| `-help` | Show an extensive help text! |
| `-n <size>` | Specify the full size of allocated arrays. |
| | E.g. `-n 2MB` (`kB`, `MB`, `GB` are allowed). |
| `-it <count>` | Take the minimum timing out of this many iterations. |
| `-dtype 32\|64\|128` | Use the data-type with this many bytes per element. |
| `-kernel <name>` | Specify the OpenMP construct used in the benchmark. <br> Please see `omb --help` for available kernels. |

Besides the optional flags, the benchmark includes a large number of
different methods. The default method to run the benchmark is the
`triad` method.

| Method | Operation |
| ---- | --------- |
| `triad` | `a = b + c * 2` |
| `quad` | `a = b + c * d` |
| `axpy` |  `a = a + b * 2` |
| `scale` | `a = b * 2` |
| `add` |   `a = b + c` |
| `fill` |  `a = 2.` |
| `sum` |   `res = sum(a)` |
| `copy` |  `a = b` |


As an example lets invoke `omb` with

- the `triad` method,
- using the `parallel do simd` construct
- 20MB allocated memory
- taking the best timing out of 10 iterations
- use 2 threads, and the two cores, as specified by the runtime.

```shell
$> OMP_NUM_THREADS=2 OMP_PLACES=cores(2) omb triad -kernel do:simd -it 10 -n 20MB
```
The output will look something like this:
```shell
 triad do:simd 1 8   1.99999924E+01   5.18938001E-04   6.45935400E-04   1.15988655E-08   8.63896001E-04  37.63694799E+00   3.36769710E+00
```
The columns is described in this small box, `omb --help` will also show this information.
| Short name | Description |
| ---- | ------ |
| `METHOD`        | name of the method running |
| `KERNEL`        | which kernel used in `METHOD` |
| `FIRST_TOUCH`   | 0 for master thread first-touch, 1 for distributed first-touch |
| `ELEM_B`        | number of bytes per element in the array |
| `MEM_MB`        | size of all allocated arrays, in MBytes |
| `TIME_MIN`      | minimum runtime of iterations, in seconds |
| `TIME_AVG`      | average runtime of iterations, in seconds |
| `TIME_STD`      | Bessel corrected standard deviation of runtime, in seconds |
| `TIME_MAX`      | maximum runtime of iterations, in seconds |
| `BANDWIDTH_GBS` | maxmimum bandwidth in GBytes/s (using `TIME_MIN`) |
| `GFLOPS`        | maxmimum FLOPS in G/s (using `TIME_MIN`) |


### Kernels

OpenMP allows several ways to utilize parallelism.

| Kernel | OpenMP construct |
| ----- | ----- |
| `do` | `!$omp parallel do` |
| `do simd` | `!$omp parallel do simd` |
| `manual` | `!$omp parallel` |
| `workshare` | `!$omp parallel workshare` |
| `loop` | `!$omp parallel loop` |
| `taskloop` | <pre>`!$omp parallel`<br>`!$omp single`<br>`!$omp taskloop`</pre> |
| `teams:distribute` | <pre>`!$omp teams`<br>`!$omp distribute`</pre> |
| `teams:parallel` | <pre>`!$omp teams`<br>`!$omp parallel do`</pre> |

Generally the `do` and `do simd` are *best*.
The `teams` construct was mainly introduces to perform distributed
computations on GPU's due to its multi-level parallelism. However,
it can be *abused* for CPU's as well.
There will be a *wide* spread of performance depending on the compiler
used.


### Specialized methods

Some methods are not meant for showcasing performance of the system, but
rather some *bad* usage of OpenMP constructs.

There are some *false-sharing* methods available which can highlight the
performance hit by using false-sharing access patterns (bad cache usage).

| Method | Operation |
| ---- | --------- |
| `triad-fs` | `a = b + c * 2` |
| `quad-fs` | `a = b + c * d` |

And there is a limited amount of kernels allowed because of the way
it accesses the memory elements.
One can compare the `triad` with the `triad-fs` using the `do` kernel.
And then any performance hit will be due to the false-sharing access
pattern.


### Running the *driver*

Together with the `omb` executable there is a driver that enables easy
test of a set of places. The driver executable is named `omb-driver` which
is a simple `bash` script.

It is a shortcut driver for testing combinations of places of threads.
It is best shown by an example:

```shell
OMP_NUM_THREADS=3 OMP_PLACES=0,{1,2},4,5,10 omb-driver
```
will run several *tests* all with only 3 threads.
This will be equivalent to running all these (note it is the upper
triangular part of the product combination of placement):
```shell
export OMP_NUM_THREADS=3

# Example: prefix output will be
#  0 1,2 4 $(omb)
OMP_PLACES=0,{1,2},4 omb
OMP_PLACES=0,{1,2},5 omb
OMP_PLACES=0,{1,2},10 omb
OMP_PLACES=0,4,5 omb
OMP_PLACES=0,4,10 omb
OMP_PLACES=0,5,10 omb
OMP_PLACES={1,2},4,5 omb
OMP_PLACES={1,2},4,10 omb
OMP_PLACES={1,2},5,10 omb
OMP_PLACES=4,5,10 omb
```
Note that by default it amends the output by prefixing with
the placement of the threads as understood by `omb`, see
note in the snippet above. So the output will have `OMP_NUM_THREADS`
additional columns with the first columns describing each threads
placement.

If one does not wish to prefix with the placement id's of each
thread on can call it as `omb-driver -Dwithout-place-info` to
omit the prefix.



### Implementation remarks

The `omb` benchmark program is an extension/rewrite
of the [STREAM](http://www.cs.virginia.edu/stream/ref.html) program.
However, it has a different goal than just showing the memory bandwidth
limit of the system.

It, however, takes some different approaches:

- `omb` encapsulates *only* the algorithm in the timing.
  `STREAM` does a timing around the `omp parallel` pragmas/constructs.
  Hence, `STREAM` also times spawning of threads, which may,
  or may not, be desired.
- `omb` has command-line arguments to change internal allocated array
  sizes and iteration parameters etc. (no recompiling needed)
- `omb` has different kernels for each method implemented.
- `omb` has more methods implemented.
  Note the `STREAM` comments about which methods are applicable
  to benchmark bandwidth problems. The same applies to `omb`.


## License

It is released under the [MIT](https://opensource.org/license/mit).
