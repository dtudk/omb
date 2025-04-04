#!/bin/bash
#
# This driver runs the 'omb' executable by varying the places that are available.
# The idea is to make a simple wrapper for running 'omb' with specific
# places of the threads.
#
# It works in a 3 step process:
#
# 1. Detect whether the user has specified some env-vars:
#    - OMP_EXE [=$(pwd of script)/omb]
#
#      Specifies the executable 'omp' from this project.
#
#    - OMP_PLACES [=cores(2048)]
#
#      If not set, this will be defaulted to 'cores(2048)',
#      meaning that the run will cycle through all cores available,
#      up to the first 2048 cores!
#
#    - OMP_SCHEDULE [=static]
#
#      Specifies how the internal openmp schedule is done for the
#      loops. If not specified it will default to 'static'.
#      The chunk-size is by default determined by the implementation.
#
# 2. Then the 'omb' code is executed to get information about the
#    allowed places and how many threads etc.
#
#    It does this by running a first *informational* run.
#    It only gets information from the 'omb' executable as to
#    which *places* [omp_get_num_places + omp_get_place_proc_ids].
#    E.g. if one has set 'OMP_PLACES=cores(4)' one will have 4 places,
#    each of them using consecutive core-ids as viable places.
#    It would be equivalent to do 'OMP_PLACES=0,1,2,3' (provided there
#    are no HWthreads).
#
#    The script will also detect the number of available threads, which
#    is controlled by 'OMP_NUM_THREADS'.
#
#    So after this step, the driver has information about:
#
#    a) number of threads the experiment should be runned with
#    b) how many *different* places/configurations the threads
#       can be placed on (see example in next step).
#
# 3. The final step is to run the experiment with the information
#    retrieved from 2.
#
#    Best to show this with an example:
#
#       OMP_NUM_THREADS=3 OMP_PLACES=0,{1,2},4,5,10 omb-driver $@
#
#    This will run a combination of runs, equivalent to:
#
#       export OMP_NUM_THREADS=3
#
#       OMP_PLACES=0,{1,2},4 omb $@
#       OMP_PLACES=0,{1,2},5 omb $@
#       OMP_PLACES=0,{1,2},10 omb $@
#       OMP_PLACES=0,4,5 omb $@
#       OMP_PLACES=0,4,10 omb $@
#       OMP_PLACES=0,5,10 omb $@
#       OMP_PLACES={1,2},4,5 omb $@
#       OMP_PLACES={1,2},4,10 omb $@
#       OMP_PLACES={1,2},5,10 omb $@
#       OMP_PLACES=4,5,10 omb $@
#
#     so it will run through the unique combinations of the initial
#     available places (upper triangular part of the combination matrix).
#

_prefix="omb: "
_prefix_debug="omb-debug: "

# Driver for creating comprehensive benchmarks.
[ -z "$OMB_EXE" ] && OMB_EXE=$(which omb 2>/dev/null)
[ -z "$OMB_EXE" ] && OMB_EXE=$(dirname $(readlink -f "$0"))/omb
if [ ! -x "$OMB_EXE" ]; then
  echo >&2 "$_prefix OMB_EXE=$OMB_EXE"
  echo >&2 "$_prefix is not defined or not executable?"
  exit 1
fi

if [ -z "$OMP_PLACES" ]; then
  echo >&2 "$_prefix OMP_PLACES not defined, defaulting to: cores(2048)"
  export OMP_PLACES="cores(2048)"
fi
if [ -z "$OMP_SCHEDULE" ]; then
  echo >&2 "$_prefix OMP_SCHEDULE not defined, defaulting to: STATIC"
  export OMP_SCHEDULE=static
fi

# Define options here
_args=()
_only_one=0
_no_place_info=0
while [ $# -gt 0 ]; do
  case $1 in
    -Dsingle)
      _only_one=1
      ;;
    -Dwithout-place-info)
      _no_place_info=1
      ;;
    *)
      _args+=($1)
      ;;
  esac
  shift
done

if [[ -n "$DEBUG" ]]; then
  echo >&2 "$_prefix_debug OMB_EXE=$OMB_EXE"
  echo >&2 "$_prefix_debug OMP_NUM_THREADS=$OMP_NUM_THREADS"
  echo >&2 "$_prefix_debug OMP_PLACES=$OMB_PLACES"
  echo >&2 "$_prefix_debug OMP_SCHEDULE=$OMP_SCHEDULE"
  echo >&2 "$_prefix_debug single=$_only_one"
  echo >&2 "$_prefix_debug without-place-info=$_no_place_info"
  echo >&2 "$_prefix_debug arguments passed to 'omb': $@"
fi

function error_show_tmp() {
  # Simple function to show the temporary content, mainly for debugging
  echo >&2 "$_prefix Content of the $OMB_EXE -env for figuring out places.."
  cat >&2 $tmpfile
}

function _debug_array {
  local name="$1"
  local -n array="$1"
  shift
  if [ -z "$DEBUG" ]; then
    return
  fi

  if [ $# -gt 0 ]; then
    echo >&2 "$_prefix_debug $@"
  fi
  case ${#array[@]} in
    0)
      echo >&2 "$_prefix_debug  $name is empty"
      ;;
    *)
      for i in $(seq 1 ${#array[@]})
      do
        let i--
        echo >&2 "$_prefix_debug  $name[$i]  = ${array[$i]}"
      done
      ;;
  esac
}

# Create a nested loop-construct based on the OMP_PLACES.
# Currently, only the comma-separated one is acceptable.
tmpfile=$(mktemp)
# Ask openmp how the places are located.
# Then, we will collect them through scripts.
$OMB_EXE -env 2>/dev/null > $tmpfile

# Retrieve total number of threads that this test should encompass
num_threads=$(grep "omp num_threads" $tmpfile)
num_threads=${num_threads##*:}
num_threads=${num_threads/ /}

# Check whether places has been set correctly
# I.e. we do not allow *no* placement, as that won't loop
# anything.
num_places=$(grep "omp num_places" $tmpfile)
num_places=${num_places##*:}
num_places=${num_places/ /}

# If the # of places < # of thread
# then we can't really do the benchmark.
# At least not in this script.
if [ $num_places -lt $num_threads ]; then
  echo >&2 "$_prefix got fewer places than threads"
  echo >&2 "$_prefix   omp_num_places  = $num_places"
  echo >&2 "$_prefix   omp_num_threads = $num_threads"
  echo >&2 "$_prefix cannot perform a meaningful benchmark... Quitting..."

  error_show_tmp

  exit 1
fi


# Parse the places constructs
place_proc_ids=()
place_num_procs=()

# Reg-exp for handling the format
# An example line looks something like this:
# omp [1] place_proc_ids  : 0,2,4
# - [1] == 2nd place specification
# - 0 2 4 == the 2nd thread can be places on either of these core IDs
place_proc_ids_re="omp \[([ 0-9]*)\] place_proc_ids[ ]*:[ ]*(.*)"
while IFS= read -r omp_place_proc_ids
do
  if [[ $omp_place_proc_ids =~ $place_proc_ids_re ]]; then
    place_proc_ids[${BASH_REMATCH[1]}]="${BASH_REMATCH[2]}"
    tmp=(${BASH_REMATCH[2]/,/ })
    place_num_procs[${BASH_REMATCH[1]}]="${#tmp[@]}"
  fi
done < $tmpfile


_debug_array place_num_procs "Number of processor places per place"
_debug_array place_proc_ids "Processor ID's per place"

# Create a hash-array that can be used to check for double runs.
# Possible scenarios are:
#  OMP_PLACES={0:4}:2:4,{0:4}:2:4
# the above should do something similar to this:
#  OMP_PLACES={0:4},{4:4},{0:4},{4:4}
declare -A place_proc_ids_runned=()

# This is the total number of unique areas
num_places=${#place_proc_ids[@]}
num_places_m1=$((num_places - 1))

# Figure out the max size of the format specifier
# And then construct the actual format specifier that is used to
# create a consistent table of output.
max_len=0
for i in $(seq 0 $num_places_m1)
do
  len=${#place_proc_ids[$i]}
  [[ $len -gt $max_len ]] && max_len=$len
done
fmt="%${max_len}s"

# Now we define a custom loop construct, which will create
# an array with the indices of the places that should be created
# for the run.
# This custom loop construct will be equivalent to a
# OMP_NUM_THREADS X-nested loop construct.
declare -a bench_places

# Setup the initial benchmark
for id in $(seq 1 $num_threads)
do
  let id--
  bench_places[$id]=$id
done

function loop_bench_places {
  local id=$1
  shift

  if [[ $id -lt 0 ]]; then
    return 1
  fi

  local cur_place=${bench_places[$id]}

  # figure out the next *allowed* place.
  if [[ $cur_place -ge $num_places_m1 ]]; then

    # We have tried all places for this entry
    # step previous element
    local prev_id=$id
    let prev_id--
    loop_bench_places $prev_id
    local retval=$?

    # Check that the stepping of the previous elements
    # actually worked.
    if [[ $retval -eq 0 ]]; then
      # all is good, we can step this one now
      # we also know that prev_id exists.
      # Otherwise it would have returned 1!
      local prev_cur_place=${bench_places[$prev_id]}
      # set it to equal the previous place.
      # Then we can just call us a gain.
      bench_places[$id]=${bench_places[$prev_id]}
      loop_bench_places $id
      retval=$?
    fi
    return $retval
  else
    let bench_places[$id]++
    return 0
  fi
}

function run_bench_places {
  local id

  # Incrementally add to OMP_PLACES until all places has been
  # specified.
  OMP_PLACES=
  for id in ${bench_places[@]}
  do
    # Print out the fields
    if [[ $_no_place_info -eq 0 ]]; then
      # Explicitly do not put in a line-feed
      printf "$fmt " "${place_proc_ids[$id]}"
    fi
    OMP_PLACES="$OMP_PLACES,{${place_proc_ids[$id]}}"
  done
  # Remove initial ,
  OMP_PLACES="${OMP_PLACES:1}"

  if [[ -n "$DEBUG" ]]; then
    echo >&2 "$_prefix_debug benchmark: OMP_PLACES=${OMP_PLACES}"
  fi

  # Write out so it can be tabularized
  OMP_PLACES="${OMP_PLACES}" $OMB_EXE ${_args[@]}
  return $?
}

# Start our loop
while :
do

  run_bench_places
  retval=$?
  if [[ $retval -ne 0 ]]; then
    echo >&2 "$_prefix failed to run place = ${bench_places[@]}"

    error_show_tmp

    exit $retval
  fi

  [ $_only_one -eq 1 ] && break
  loop_bench_places $((num_threads - 1))
  # Check if we should continue
  [ $? -ne 0 ] && break
done

_debug_array bench_places "The final benchmark places"

exit 0
