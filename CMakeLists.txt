# IntelLLVM was introduced in 3.20
cmake_minimum_required(VERSION 3.20 FATAL_ERROR)

# Include overwrites before setting up the project
set(CMAKE_USER_MAKE_RULES_OVERRIDE
  "${CMAKE_CURRENT_SOURCE_DIR}/cmake/ombDefaultFlags.cmake")

list(APPEND CMAKE_MESSAGE_CONTEXT omb)

# Default the build-type to be of release
set(CMAKE_BUILD_TYPE_INIT Release)
# In order to access the STRINGS property, we have to denote
# it a cache variable. Which it isn't by default.
set(CMAKE_BUILD_TYPE "${CMAKE_BUILD_TYPE_INIT}"
  CACHE STRING "Choose the type of build")

set_property(
  CACHE CMAKE_BUILD_TYPE
  PROPERTY
    STRINGS
      Release # optimal flags without using fast-math
      Fast # optimal flags with using fast-math
      Debug # only for debug purposes
)

project(omb
  LANGUAGES Fortran
  DESCRIPTION "OpenMP benchmarks in Fortran"
  VERSION 1.0.0
)

# Project installation follows GNU installation directory convention
include(GNUInstallDirs)
include(CMakePrintHelpers)

# Export CMake package file
include(CMakePackageConfigHelpers)
include(CMakePushCheckState)

# Initialize the check-state
# We don't reset, in case a parent project wishes to push down
# variables
cmake_push_check_state()

# Define library specific content
set(OMB_AUTHOR      "Nick Papior")
set(OMB_DESCRIPTION "OpenMP benchmarks written in Fortran")

# Require API compatibility via semantic versioning for static linking.
set(COMPATIBILITY SameMajorVersion)

# Print-out information about the build-properties
include(cmake/ombDefaultFlags.cmake)
include(cmake/ombInfo.cmake)

# Add project options
include(cmake/ombChecks.cmake)
include(cmake/ombFyppify.cmake)
include(cmake/ombOptions.cmake)

find_package(OpenMP
  COMPONENTS Fortran
  REQUIRED
)

include(cmake/ombOpenMPOptions.cmake)

find_package(MPI
  COMPONENTS Fortran
)

option(OMB_WITH_MPI "Install omb with MPI support" FALSE)
if( OMB_WITH_MPI )
  if( MPI_Fortran_FOUND )
    include(cmake/ombMPIOptions.cmake)
  else()
    message(FATAL_ERROR "The fortran MPI library is not found...")
  endif()
  list(APPEND OMB_FYPP_FLAGS "-DOMB_MPI=1")
endif()

option(OMB_INSTALL  "Install omb (or use as sub-project)" ${PROJECT_IS_TOP_LEVEL})

# Now figure out how the tools should be used.
set(OMB_INT_KIND "int64" CACHE STRING
  "Size of integers used in loop constructs (type named according to iso_fortran_env).")
set_property(CACHE OMB_INT_KIND
  PROPERTY STRINGS int32 int64)

# Append choice to fypp flags
list(APPEND OMB_FYPP_FLAGS -DOMB_INT_KIND="${OMB_INT_KIND}")

# Determine whether arrays should be allocated, or stack-bound
set(OMB_ALLOC_TYPE "stack" CACHE STRING "How the arrays are constructed
[allocatable, pointer, stack].")
set_property(CACHE OMB_ALLOC_TYPE
  PROPERTY STRINGS allocatable pointer stack)

# Append choice to fypp flags
list(APPEND OMB_FYPP_FLAGS -DOMB_ALLOC_TYPE="${OMB_ALLOC_TYPE}")


# Now figure out how the tools should be used.
set(OMB_TIMING "omp" CACHE STRING
  "Which method to time the benchmarks with [omp,systemclock].")
set_property(CACHE OMB_TIMING
  PROPERTY STRINGS omp systemclock)

string(TOUPPER "${OMB_TIMING}" omb_timing_upper)
# Remove underscore, allows system_clock
string(REPLACE "_" "" omb_timing_upper "${omb_timing_upper}")
if( "${omb_timing_upper}" STREQUAL "SYSTEMCLOCK" )
  list(APPEND OMB_FYPP_FLAGS -DOMB_TIMING_SYSTEM_CLOCK)
elseif( "${omb_timing_upper}" STREQUAL "OMP" )
  # pass
else()
  message(FATAL_ERROR "OMB_TIMING not one of omp|systemclock

  Got OMB_TIMING='${OMB_TIMING}'!")
endif()


# Generally we do not need the rt library.
# However, it should provide extended runtime precision for timers.
# For GCC this is implicitly linked when using OpenMP.
# So currently not really used...
find_library(SysLib_rt
  rt
  DOC "The runtime library for extended timing precision."
)


message(STATUS "${PROJECT_NAME} options:")
list(APPEND CMAKE_MESSAGE_INDENT "  ")

#message(STATUS "Install: ${OMB_INSTALL}")
message(STATUS "Loop integers will be declared using: ${OMB_INT_KIND}")
message(STATUS "Arrays will be declared using: ${OMB_ALLOC_TYPE}")
message(STATUS "Timing benchmarks will use: ${OMB_TIMING}")
message(STATUS "Flags passed to fypp:")
list(APPEND CMAKE_MESSAGE_INDENT "  ")
foreach(flag IN LISTS OMB_FYPP_FLAGS)
  message(STATUS "${flag}")
endforeach()
list(POP_BACK CMAKE_MESSAGE_INDENT)

list(POP_BACK CMAKE_MESSAGE_INDENT)


# Add the sources for the binary and drivers
add_subdirectory(src)
add_subdirectory(driver)

option(OMB_CHECK_COMPILER
  "Also compile some test files, simply to check for compiler bugs"
  FALSE
)
mark_as_advanced(OMB_CHECK_COMPILER)
if( OMB_CHECK_COMPILER )
  message(STATUS "Also builds the separate kernels for a simple compiler check")
  add_subdirectory(check_compiler)
endif()

# Globally define a place where we will install
# cmake configuration stuff, *Target.cmake *Version.cmake etc.
set(OMB_INSTALL_CMAKECONFIG_DIR
  "${CMAKE_INSTALL_LIBDIR}/cmake/${PROJECT_NAME}"
  CACHE STRING
  "Determine where the CMake configuration files will be installed"
)
mark_as_advanced(OMB_INSTALL_CMAKECONFIG_DIR)



# Export a cmake package configure file
configure_package_config_file(
  "${CMAKE_CURRENT_SOURCE_DIR}/cmake/Config.cmake.in"
  "${CMAKE_CURRENT_BINARY_DIR}/${PROJECT_NAME}Config.cmake"
  INSTALL_DESTINATION "${OMB_INSTALL_CMAKECONFIG_DIR}"
)

# Export a package version file
write_basic_package_version_file(
  "${CMAKE_CURRENT_BINARY_DIR}/${PROJECT_NAME}ConfigVersion.cmake"
  VERSION ${PROJECT_VERSION}
  COMPATIBILITY ${COMPATIBILITY}
)

# Install cmake configuration files
install(
  FILES
    "${CMAKE_CURRENT_BINARY_DIR}/${PROJECT_NAME}Config.cmake"
    "${CMAKE_CURRENT_BINARY_DIR}/${PROJECT_NAME}ConfigVersion.cmake"
  DESTINATION "${OMB_INSTALL_CMAKECONFIG_DIR}"
)

install(
  FILES "LICENSE"
  DESTINATION "${CMAKE_INSTALL_DATADIR}/licences/${PROJECT_NAME}"
)


# Install project
install(
  EXPORT ${PROJECT_NAME}-targets
  FILE ${PROJECT_NAME}Targets.cmake
  NAMESPACE ${PROJECT_NAME}::
  DESTINATION "${OMB_INSTALL_CMAKECONFIG_DIR}"
)

# Export a cmake configuration for the targets if used as a sub-project
export(
  EXPORT ${PROJECT_NAME}-targets
  NAMESPACE ${PROJECT_NAME}::
  FILE "${PROJECT_NAME}Targets.cmake"
)

list(POP_BACK CMAKE_MESSAGE_CONTEXT)

# Restore the original state
# in case we are in a sub-project
cmake_pop_check_state()
