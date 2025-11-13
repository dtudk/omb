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
#    - OMP_PLACES [=cores]
#
#      If not set, this will be defaulted to 'cores',
#      meaning that the run will cycle through all cores available.
#
#    - OMP_SCHEDULE [=static]
#
#      Specifies how the internal OpenMP schedule is done for the
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
# Notes:
#
# The driver can figure out if the places requested are hardware threads
# and whether they are allowed to be further filled.
# Consider a system, without hardware threads, and a request:
#
#   OMP_PLACES={1,2},{3,4} OMP_NUM_THREADS=3 omb-driver
#
# This will run the triangular part:
#
#   OMP_PLACES={1,2},{3,4},{1,2} omb $@
#   OMP_PLACES={1,2},{3,4},{3,4} omb $@

readonly _prefix="omb:"
readonly _prefix_debug="omb-debug:"

# Variable used for regexp of the place_proc_ids
# It will be used to extract the placement ID's of
# the processors.
readonly PLACE_PROC_IDS_RE="omp \[([ 0-9]*)\] place_proc_ids[ ]*:[ ]*(.*)"

# Driver for creating comprehensive benchmarks.
[ -z "$OMB_EXE" ] && OMB_EXE=$(which omb 2>/dev/null)
[ -z "$OMB_EXE" ] && OMB_EXE=$(dirname $(readlink -f "$0"))/omb
if [ ! -x "$OMB_EXE" ]; then
  echo >&2 "$_prefix OMB_EXE=$OMB_EXE"
  echo >&2 "$_prefix is not defined or not executable?"
  exit 1
fi

# Define options here
_args=()
_domains=cores
_single=0
_without_place_info=0
while [ $# -gt 0 ]; do
  case $1 in
    -Ddomains)
      shift
      if [[ $# -lt 1 ]]; then
        echo >&2 "$_prefix missing argument to -Ddomains <>"
      fi
      _domains="$1"
      ;;
    -Dcores)
      # Same as -Ddomains cores
      _domains=cores
      ;;
    -Dthreads)
      # Same as -Ddomains threads
      _domains=threads
      ;;
    -Dsingle)
      _single=1
      ;;
    -Dwithout-place-info)
      _without_place_info=1
      ;;
    -h|--help)

      echo "$0 help information"

      shift
      exit 0
      ;;
    *)
      _args+=($1)
      ;;
  esac
  shift
done

if [ -z "$OMP_PLACES" ]; then
  echo >&2 "$_prefix OMP_PLACES not defined, defaulting to: $_domains"
  export OMP_PLACES="$_domains"
fi
# Store input OMP_PLACES
readonly INPUT_OMP_PLACES="$OMP_PLACES"

if [ -z "$OMP_SCHEDULE" ]; then
  echo >&2 "$_prefix OMP_SCHEDULE not defined, defaulting to: STATIC"
  export OMP_SCHEDULE=static
fi

if [[ -n "$DEBUG" ]]; then
  echo >&2 "$_prefix_debug OMB_EXE=$OMB_EXE"
  echo >&2 "$_prefix_debug OMP_NUM_THREADS=$OMP_NUM_THREADS"
  echo >&2 "$_prefix_debug OMP_PLACES=$OMB_PLACES"
  echo >&2 "$_prefix_debug OMP_SCHEDULE=$OMP_SCHEDULE"
  echo >&2 "$_prefix_debug domains=$_domains"
  echo >&2 "$_prefix_debug single=$_single"
  echo >&2 "$_prefix_debug without-place-info=$_without_place_info"
  echo >&2 "$_prefix_debug arguments passed to 'omb': $@"
fi

function error_show_tmp() {
  # Simple function to show the temporary content, mainly for debugging
  echo >&2 "$_prefix Temporary files with content of the $OMB_EXE -env"
  echo >&2 "$_prefix    $tmpdomains contains export for OMP_PLACES=$_domains"
  echo >&2 "$_prefix    $tmpplaces contains export for OMP_PLACES=$INPUT_OMP_PLACES"
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


# Retrieve information from the environment file that omb --env spits out.
function get_env {
  local var_name="$1"
  local -n var="$1"
  local file="$2"
  shift 2
  local tmp
  local idx

  case $1 in
    -num-threads)
      # Retrieve total number of threads that this test should encompass

      var=$(grep "omp num_threads" $file)
      var=${var##*:}
      var=${var// /}
      ;;

    -num-places)
      # Determine how many different places are defined
      # in the environment.
      # Note, that by default the domains are *cores* (see -Ddomains).

      var=$(grep "omp num_places" $file)
      var=${var##*:}
      var=${var// /}
      ;;

    -place-proc-ids)
      # Read a file and put in array `var` the placements allowed
      # for each place ID.
      #   var[0]=0,1,2
      #   var[1]=3,4

      while IFS= read -r omp_place_proc_ids
      do
        if [[ $omp_place_proc_ids =~ $PLACE_PROC_IDS_RE ]]; then
          var[${BASH_REMATCH[1]}]="${BASH_REMATCH[2]}"
        fi
      done <<< $(grep -e "omp \[[ 0-9]*\] place_proc_ids" $file)
      ;;

    -place-num-places)
      # Extract the number of places

      local -n file=$file
      for idx in ${!file[@]}
      do
        # convert '0,1,3' into (0 1 3)
        # then get the length of the array
        tmp=(${file[$idx]//,/ })
        var[$idx]=${#tmp[@]}
      done
      ;;

    -place-num-domains)

      local -n file=$file
      for idx in ${!file[@]}
      do
        # convert '0,1,3' into (0 1 3)
        # then get the length of the array
        tmp=(${file[$idx]//,/ })
        var[$idx]=${#tmp[@]}
      done
      ;;

    *)
      echo >&2 "$_prefix unknown argument to get_env: $1"
      ;;
  esac
  shift
}


# Create a nested loop-construct based on the OMP_PLACES.
# Currently, only the comma-separated one is acceptable.
tmpdomains=$(mktemp)
tmpplaces=$(mktemp)

# Ask OpenMP how the places are located.
# Then, we will collect them through scripts.
# We use this first invocation to figure out if the hardware has HW-threads
# or not.
# It will also be used to figure out if round-robin places are available.
OMP_PLACES="$_domains" OMP_NUM_THREADS=1 $OMB_EXE -env 2>/dev/null > $tmpdomains
OMP_PLACES="$INPUT_OMP_PLACES" $OMB_EXE -env 2>/dev/null > $tmpplaces

# Get all available places depending on the _domains variable.
# If the hardware has HW-threads, and _domains=cores, then
# we'll get a list of {0,1},{2,3},...,{NT-2,NT-1}
# Afterwards we'll use this to determine whether a requested
# place is overlapping several domains.
get_env domains_place_proc_ids $tmpdomains -place-proc-ids

_debug_array domains_place_proc_ids "Processor ID's per domain (irrespective of OMP_PLACES)"


# Get information on the user-requested allowed places.
# An example line looks something like this:
# omp [1] place_proc_ids  : 0,2,4
# - [1] == 2nd place specification
# - 0 2 4 == the 2nd place consists of either of these core IDs
# In this case the read proc id's and num-places are with respect
# to the user defined OMP_PLACES
get_env place_proc_ids $tmpplaces -place-proc-ids
get_env num_threads $tmpplaces -num-threads
num_threads_m1=$num_threads
let num_threads_m1--

_debug_array place_proc_ids "Processor ID's per place (user defined)"


# We need to assert that all `place_proc_ids` only overlaps with
# a single domain in `domains_place_proc_ids`.
# The below loop will check for each place list how many domains
# they overlap with.
# For example:
#   Thread domains yields {0,1},{2,3},4,5
# then
#   OMP_PLACES={0,1},{2,4}
# will have the first place ({0,1}) overlap with 1 domain.
# and will have the second place ({2,4}) overlap with 2 domains.
# This is influenced by domains=threads|cores etc.
declare -a place_ndomains
max_ndomains=0
for idx in ${!place_proc_ids[@]}
do
  # Reset counter
  ndomain_counter=0

  for didx in ${!domains_place_proc_ids[@]}
  do
    # convert the places into column data, compare them (comm)
    # then map the overlapping lines into the array `tmp`
    mapfile -t tmp < \
      <(comm -12 \
        <(IFS=$'\n' ; echo ${place_proc_ids[$idx]} | tr ',' '\n' | sort) \
        <(IFS=$'\n' ; echo ${domains_place_proc_ids[$didx]} | tr ',' '\n' | sort)
      )

    if [ ${#tmp[@]} -gt 0 ]; then
      let ndomain_counter++
    fi

  done
  # Store the number of domains for this place
  place_ndomains[$idx]=$ndomain_counter
  if [ $ndomain_counter -gt $max_ndomains ]; then
    # track the maximum number of spanning domains for any place
    max_ndomains=$ndomain_counter
  fi

  if [ $ndomain_counter -lt 1 ]; then
    echo >&2 "$_prefix place index ${idx} with places: ${place_proc_ids[$idx]}"
    echo >&2 "$_prefix overlapped with ${ndomain_counter} domains."
    echo >&2 "$_prefix The requested placement *must* overlap with at least 1 domain!"
    exit 5
  fi
done
_debug_array place_ndomains "Number of overlapping domains for each place."


# If the # of places < # of thread
# we will append the places by the places which spans multiple domains.
# We can only append more places if it overlaps multiple domains.
# This will *NOT* ensure that there is no over subscription.
# That has to be the users responsibility for the time being.

# Add all places which spans more than 1 domain.
# This will put its domain in as many times as needed until the place
for idomain in $(seq 2 $max_ndomains)
do
  for idx in ${!place_proc_ids[@]}
  do
    newidx=${#place_proc_ids[@]}
    #if [ $newidx -ge $num_threads ]; then
      # Only add new places if the number of available
      # places are below the number of threads
    #  break
    #fi

    # Check if this place has enough domains to add a new
    # place to the list.
    if [ $idomain -le ${place_ndomains[$idx]} ]; then
      place_proc_ids[$newidx]="${place_proc_ids[$idx]}"
      place_ndomains[$newidx]=${place_ndomains[$idx]}
    fi
  done
done
_debug_array place_proc_ids "Processor ID's per place (after duplicating missing places)"

# This is the total number of unique areas
num_places=${#place_proc_ids[@]}
num_places_m1=$((num_places - 1))

if [ $num_places -lt $num_threads ]; then

  echo >&2 "$_prefix got fewer places than threads"
  echo >&2 "$_prefix   omp_num_places  = $num_places"
  echo >&2 "$_prefix   omp_num_threads = $num_threads"
  echo >&2 "$_prefix cannot perform a meaningful benchmark... Quitting..."

  error_show_tmp

  exit 1
fi


# Figure out the max size of the format specifier.
# And then construct the actual format specifier that is used to
# create a consistent table of output.
max_len=0
for i in $(seq 0 $num_places_m1)
do
  len=${#place_proc_ids[$i]}
  [[ $len -gt $max_len ]] && max_len=$len
done
# This ensures that each thread placement has the same format.
# This is important when cycling through all of the places.
fmt="%${max_len}s"

# Now we define a custom loop construct, which will create
# an array with the indices of the places that should be created
# for the run.
# This custom loop construct will be equivalent to a
#   OMP_NUM_THREADS X-nested loop construct.

# Define the array.
declare -a bench_places=($(seq 0 $num_threads_m1 ))

# Create a nested loop construct.
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
  OMP_PLACES=""
  for id in ${bench_places[@]}
  do
    # Print out the fields
    if [[ $_without_place_info -eq 0 ]]; then
      # Explicitly do not put in a line-feed
      printf "$fmt " "${place_proc_ids[$id]}"
    fi
    OMP_PLACES="$OMP_PLACES,{${place_proc_ids[$id]}}"
  done
  # Remove initial ','
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

  [ $_single -eq 1 ] && break
  loop_bench_places $num_threads_m1
  # Check if we should continue
  [ $? -ne 0 ] && break
done

exit 0
