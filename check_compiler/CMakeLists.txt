
# The code has these kernels inserted
set(triad_kernels
  serial
  do
  do_simd
  workshare
  taskloop
  loop
  teams_distribute
  teams_parallel
)
foreach(kernel IN LISTS triad_kernels)
  # Do the preprocessing
  omb_fyppify(
    FILES
      check_triad_kernels.fypp
    # Make all output files unique
    EXTOUT "${kernel}.f90"
    FLAGS
      ${OMB_FYPP_FLAGS}
      # We need to include common.fypp
      -I${CMAKE_CURRENT_SOURCE_DIR}/../src
      -DOMB_CHECK_KERNEL="${kernel}"
    OUTPUT omb_fypp_sources
  )

  add_library(check_triad_${kernel}
    # This is just to create a static library
    STATIC
    ${omb_fypp_sources}
  )
  target_link_libraries(
    check_triad_${kernel}
    PRIVATE
    OpenMP::OpenMP_Fortran
    $<$<BOOL:${OMB_WITH_MPI}>:MPI::MPI_Fortran>
    )
endforeach()
