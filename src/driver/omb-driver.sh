#!/bin/bash
#

_prefix="omb: "
# Driver for creating comprehensive benchmarks.
[ -z "$OMB_EXE" ] && OMB_EXE=$(which omb 2>/dev/null)
[ -z "$OMB_EXE" ] && OMB_EXE=$(dirname $(readlink -f "$0"))/omb
if [ ! -x "$OMB_EXE" ]; then
  echo "$_prefix OMB_EXE=$OMB_EXE"
  echo "$_prefix is not defined or not executable?"
  exit 1
fi

if [ -z "$OMP_PLACES" ]; then
  echo "$_prefix OMP_PLACES not defined, defaulting to: cores(2048)" >&2
  export OMP_PLACES="cores(2048)"
fi
if [ -z "$OMP_SCHEDULE" ]; then
  echo "$_prefix OMP_SCHEDULE not defined, defaulting to: STATIC" >&2
  export OMP_SCHEDULE=static
fi

loop=1
if [ "$1" == "no-loop" ]; then
  loop=0
  shift
fi

# Create a nested loop-construct based on the OMP_PLACES.
# Currently, only the comma-separated one is acceptable.
tmpfile=$(mktemp)
# Ask openmp how the places are located.
# Then, we will collect them through scripts.
$OMB_EXE -omp 2>/dev/null > $tmpfile

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
  echo "$_prefix got fewer places than threads"
  echo "$_prefix omp_num_places  = $num_places"
  echo "$_prefix omp_num_threads = $num_threads"
  echo "$_prefix cannot perform a meaningful benchmark... Quitting..."
  exit 1
fi


# Parse the places constructs
place_proc_ids=()
place_num_procs=()

# Reg-exp for handling the format
# An example line looks something like this:
# omp place_proc_ids [1] : 0 2 4
# - [1] == 2nd place specification
# - 0 2 4 == can be located either places
place_proc_ids_re="omp place_proc_ids[ ]+\[([ 0-9]*)\][ ]*:[ ]*(.*)"
while IFS= read -r omp_place_proc_ids
do
  if [[ $omp_place_proc_ids =~ $place_proc_ids_re ]]; then
    place_proc_ids[${BASH_REMATCH[1]}]="${BASH_REMATCH[2]}"
    tmp=(${BASH_REMATCH[2]/,/ })
    place_num_procs[${BASH_REMATCH[1]}]="${#tmp[@]}"
  fi
done < $tmpfile

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

loop_bench_places_step() {
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
    local prev_id=$((id-1))
    loop_bench_places_step $prev_id
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
      loop_bench_places_step $id
      retval=$?
    fi
    return $retval
  else
    let bench_places[$id]++
    return 0
  fi
}

loop_bench_places() {
  if [ ${#bench_places[@]} -eq 0 ]; then
    # Setup the nested loop construct
    for id in $(seq 1 $num_threads)
    do
      let id--
      bench_places[$id]=$id
    done
    return 0
  fi
  loop_bench_places_step $((num_threads - 1))
  return $?
}

function run_bench_places {
  OMP_PLACES=
  for id in ${bench_places[@]}
  do
    # Print out the fields
    printf "$fmt " "${place_proc_ids[$id]}"
    OMP_PLACES="$OMP_PLACES,{${place_proc_ids[$id]}}"
  done

  # Write out so it can be tabularized
  # Remove initial `,`, then run!
  OMP_PLACES="${OMP_PLACES:1}" $OMB_EXE $@
}

# Start our loop
loop_bench_places
while [ $? -eq 0 ]; do

  run_bench_places $@

  [ $loop -eq 0 ] && break
  loop_bench_places
done
