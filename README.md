
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
  However, one can selectively use the fortran intrinsic (`system_clock`).

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
| | E.g. `-n 2MB` (`kB`, `MB`, `GB`, `TB` are allowed). |
| `-it <count>` | Take the minimum timing out of this many iterations. |
| `-dtype 32\|64\|128` | Use the data-type with this many bits per element. |
| `-kernel <name>` | Specify the OpenMP construct used in the benchmark. <br> Please see `omb --help` for available kernels. |
| `-method <name>` | Specify the benchmark to run, <br> see `omb --help` for available methods. |

Besides the optional flags, the benchmark includes a large number of
different methods. The default method to run the benchmark is the
`triad` method.

Here `dtypes/elem` is the number of basic `dtype` byte sizes for each
element. E.g. a `-dtype 64` equals 8 bytes per element. Hence, `dtypes/elem=3` results
in `3*8=24` bytes per element operation (equivalent to STREAMS way of counting).

| Method   | Operation       | dtypes/elem | FLOP/elem | MOP/elem |
| -------- | --------------- | -----------:| --------:| ------: |
| `triad`  | `a = b + c*2`   | 3 | 2 | 3 |
| `tetrad` | `a = b + c*d`   | 4 | 2 | 4 |
| `pentad` | `a = b*c + d*e` | 5 | 3 | 5 |
| `axpy`   | `a = a + b*2`   | 2 | 2 | 3 |
| `scale`  | `a = b*2`       | 2 | 1 | 2 |
| `add`    | `a = b + c`     | 3 | 1 | 3 |
| `fill`   | `a = 2.`        | 1 | 0 | 1 |
| `sum`    | `res = sum(a)`  | 1 | 1 | 1 |
| `copy`   |  `a = b`        | 2 | 0 | 2 |


As an example lets invoke `omb` with

- the `triad` method,
- using the `parallel do simd` construct
- 20MB allocated memory
- taking the best timing out of 10 iterations
- use 2 threads, and the two cores, as specified by the runtime.

```shell
$> OMP_NUM_THREADS=2 OMP_PLACES=cores(2) omb -m triad -kernel do:simd -it 10 -n 20MB
 triad do:simd 1 8   1.99999924E+01   5.18938001E-04   6.45935400E-04   1.15988655E-08   8.63896001E-04  37.63694799E+00   3.36769710E+00
```
The columns are described in this small box, `omb --help` will also show this information.
| Short name      | Description |
| --------------- | ------ |
| `METHOD`        | name of the method running |
| `KERNEL`        | which kernel used in `METHOD` |
| `FIRST_TOUCH`   | 0 for master thread first-touch, 1 for distributed first-touch |
| `ELEM_B`        | number of bytes per element in the array [B] |
| `MEM_MB`        | size of all allocated arrays, in [MB] |
| `TIME_MIN`      | minimum runtime of iterations [s] |
| `TIME_AVG`      | average runtime of iterations [s] |
| `TIME_STD`      | Bessel corrected standard deviation of runtime [s] |
| `TIME_MAX`      | maximum runtime of iterations [s] |
| `BANDWIDTH_GBS` | maximum bandwidth using `TIME_MIN` [GB/s] |
| `GFLOPS`        | maximum FLOPS using `TIME_MIN` [G/s] |


### Kernels

OpenMP allows several ways to utilize parallelism.

| Kernel | OpenMP construct |
| ----- | ----- |
| `serial`                  |  |
| `do`                      | `!$omp parallel do` |
| `do:simd`                 | `!$omp parallel do simd` |
| `do:simd+nontemporal`     | `!$omp parallel do simd nontemporal` |
| `manual`                  | `!$omp parallel` |
| `manual:simd`             | <pre>`!$omp parallel`<br>`!$omp simd`</pre> |
| `manual:simd+nontemporal` | <pre>`!$omp parallel`<br>`!$omp simd nontemporal`</pre> |
| `loop`                    | `!$omp parallel loop` |
| `workshare`               | `!$omp parallel workshare` |
| `taskloop`                | <pre>`!$omp parallel`<br>`!$omp single`<br>`!$omp taskloop`</pre> |
| `taskloop:simd`           | <pre>`!$omp parallel`<br>`!$omp single`<br>`!$omp taskloop simd`</pre> |
| `teams:manual`            | `!$omp teams` |
| `teams:distribute`        | <pre>`!$omp teams`<br>`!$omp distribute`</pre> |
| `teams:distribute:do`     | <pre>`!$omp teams`<br>`!$omp distribute parallel do`</pre> |
| `teams:distribute:manual` | <pre>`!$omp teams`<br>`!$omp distribute parallel`</pre> |
| `teams:parallel:do`       | <pre>`!$omp teams`<br>`!$omp parallel do`</pre> |
| `teams:parallel:manual`   | <pre>`!$omp teams`<br>`!$omp parallel`</pre> |
| `teams:parallel:loop`     | <pre>`!$omp teams`<br>`!$omp parallel loop`</pre> |

The `teams` construct was mainly introduced in OpenMP to perform distributed
computations on GPU's due to its multi-level parallelism. For those `teams`
constructs where there is no subsequent distribution on individual teams, there
can happen incorrect timing results because those constructs does not have synchronization
through OpenMP. I.e. `barrier` calls are not available in a `teams` construct, only
in a `teams ... parallel` where all threads of a team is participating.
We have it here to showcase how `teams` can be *abused* for CPU's as well.
There will be a *wide* spread of performance depending on the compiler
used.


### Specialized methods

Some methods are not meant for showcasing performance of the system, but
rather some *bad* usage of OpenMP constructs.

There are some *false-sharing* methods available which can highlight the
performance hit by using false-sharing access patterns (bad cache usage).

| Method | Operation |
| ---- | --------- |
| `fs:triad` | `a = b + c*2` |
| `fs:tetrad` | `a = b + c*d` |

And there is a limited amount of kernels allowed because of the way
it accesses the memory elements.
One can compare the `triad` with the `fs:triad` using the `do` kernel.
And then any performance hit will be due to the false-sharing access
pattern.


### Running the *driver*

Together with the `omb` executable there is a driver that enables easy
test of a set of places. The driver executable is named `omb-driver` which
is a simple `bash` script.

It is a shortcut driver for testing combinations of places of threads.
It is best shown by an example:
```shell
$> OMP_NUM_THREADS=3 OMP_PLACES=0,{1,2},4,5,10 omb-driver
  0 1,2   4  triad do 1 8   3.07200000E+03   9.40218100E-02   9.44088364E-02   2.60900939E-07   9.56927400E-02  31.90749040E+00   2.85503391E+00
  0 1,2   5  triad do 1 8   3.07200000E+03   9.40824550E-02   9.59592584E-02   1.36111673E-05   1.06213985E-01  31.88692302E+00   2.85319357E+00
  0 1,2  10  triad do 1 8   3.07200000E+03   9.41941960E-02   9.46193575E-02   4.79454067E-08   9.49652460E-02  31.84909610E+00   2.84980888E+00
  0   4   5  triad do 1 8   3.07200000E+03   1.01350198E-01   1.06201720E-01   6.39561026E-06   1.08226976E-01  29.60033684E+00   2.64859331E+00
  0   4  10  triad do 1 8   3.07200000E+03   7.81628790E-02   7.99320207E-02   2.31608466E-06   8.19245620E-02  38.38139074E+00   3.43430871E+00
  0   5  10  triad do 1 8   3.07200000E+03   7.77361840E-02   8.02890019E-02   2.61882319E-06   8.24161840E-02  38.59206673E+00   3.45315968E+00
1,2   4   5  triad do 1 8   3.07200000E+03   1.06380118E-01   1.07770293E-01   2.96683275E-07   1.08236085E-01  28.20075834E+00   2.52336114E+00
1,2   4  10  triad do 1 8   3.07200000E+03   7.79563530E-02   8.13598654E-02   1.34486237E-05   8.89212030E-02  38.48307270E+00   3.44340706E+00
1,2   5  10  triad do 1 8   3.07200000E+03   7.77943770E-02   7.87795150E-02   7.42053940E-07   7.98704600E-02  38.56319847E+00   3.45057659E+00
  4   5  10  triad do 1 8   3.07200000E+03   1.08133645E-01   1.13019056E-01   3.07201868E-06   1.14062300E-01  27.74344655E+00   2.48244157E+00
```
will run several *tests* all with only 3 threads (note example output
just after).  
This will be equivalent to running all the upper triangular
part of the product combination of placements:
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
Note that by default, the `omb-driver` prepends the placement
of each thread by adding `OMP_NUM_THREADS` columns.
These first `OMP_NUM_THREADS` describes each thread
placement.

If one does not wish to prefix with the placement id's of each
thread on can use the option `omb-driver -Dwithout-place-info` to
omit the first `OMP_NUM_THREADS` placement columns.

By default, if `OMP_PLACES` is unset, `omb-driver` will set `OMP_PLACES=cores`.
```shell
# CPU 2 hw-threads x 4 cores
# The below 3 invocations are equivalent:
OMP_PLACES={0:2}:4:2 omb-driver
OMP_PLACES={0,1},{2,3},{4,5},{6,7} omb-driver
omb-driver
```
If one wishes to distinguish hardware-threads as thread domains, simply
call it with `omb-driver -Ddomains threads` which will make all threads
a place.



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

  In particular, `omb`, enables cache discovery for small memory footprints.
  In these cases it is vital to not time thread-spawning.
- `omb` has command-line arguments to change internal allocated array
  sizes and iteration parameters etc. (no recompiling needed)
- `omb` has different kernels for each method implemented.
- `omb` has more methods implemented.
  Note the `STREAM` comments about which methods are applicable
  to benchmark bandwidth problems. The same applies to `omb`.


## License

It is released under the [MIT](https://opensource.org/license/mit).
