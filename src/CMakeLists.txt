
# Do the preprocessing
omb_fyppify(
  COMMENT "fyppifying source codes"
  FILES
    benchmarks.fypp
    options.fypp
    results.fypp
    omb.fypp
  OUTPUT omb_fypp_sources
)


# Finally define the fdict library
add_executable(
  omb
  ${omb_fypp_sources}
  timing.f90
  )

target_link_libraries(
  omb
  PRIVATE
  OpenMP::OpenMP_Fortran
  )

# Install the library targets
# It also exports to the name ${PROJECT_NAME}-targets
# for subsequent usage in the installation of the library etc.
install(
  TARGETS omb
  EXPORT ${PROJECT_NAME}-targets
)

add_subdirectory(driver)
