
# Do the preprocessing
omb_fyppify(
  COMMENT "declaring fypp sources in src/"
  FILES
    benchmarks_helpers.fypp
    benchmarks_read.fypp
    benchmarks_sum.fypp
    benchmarks_fill.fypp
    benchmarks_copy.fypp
    benchmarks_scale.fypp
    benchmarks_add.fypp
    benchmarks_triadd.fypp
    benchmarks_tetradd.fypp
    benchmarks_pentadd.fypp
    benchmarks_axpy.fypp
    benchmarks_false_sharing_triadd.fypp
    benchmarks_false_sharing_tetradd.fypp
    benchmarks_false_sharing_pentadd.fypp
    benchmarks.fypp
    options.fypp
    results.fypp
    info_omp.fypp
    omb.fypp
    timing.fypp
    dummies.fypp
  OUTPUT omb_fypp_sources
)


# Finally define the omb executable
add_executable(
  omb
  ${omb_fypp_sources}
  )

target_link_libraries(
  omb
  PRIVATE
  OpenMP::OpenMP_Fortran
  $<$<BOOL:${OMB_WITH_MPI}>:MPI::MPI_Fortran>
  )

# Install the library targets
# It also exports to the name ${PROJECT_NAME}-targets
# for subsequent usage in the installation of the library etc.
install(
  TARGETS omb
  EXPORT ${PROJECT_NAME}-targets
)
