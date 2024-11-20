cmake_minimum_required(VERSION 3.17 FATAL_ERROR)

# Include overwrites before setting up the project
set(CMAKE_USER_MAKE_RULES_OVERRIDE
  "${CMAKE_CURRENT_SOURCE_DIR}/cmake/ombDefaultFlags.cmake")

list(APPEND CMAKE_MESSAGE_CONTEXT omb)

project(omb
  LANGUAGES Fortran
  DESCRIPTION "OpenMP benchmarks in Fortran"
  VERSION 1.0.0
)

# Project installation follows GNU installation directory convention
include(GNUInstallDirs)

# Export CMake package file
include(CMakePackageConfigHelpers)

# Define library specific content
option(OMB_INSTALL  "Install omb (or use as sub-project)" ${PROJECT_IS_TOP_LEVEL})
set(OMB_AUTHOR      "Nick Papior")
set(OMB_DESCRIPTION "OpenMP benchmarks written in Fortran")
message(STATUS "
** PROJECT_NAME = ${PROJECT_NAME}
")

# Default build-type
if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
  set(CMAKE_BUILD_TYPE "Release" CACHE STRING "Choose the type of build" FORCE)
endif()

if (NOT DEFINED CMAKE_Fortran_MODULE_DIRECTORY)
	set(CMAKE_Fortran_MODULE_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}/include)
endif ()

# Add project options
include(cmake/ombFyppify.cmake)
include(cmake/ombOptions.cmake)
include(cmake/ombDefaultFlags.cmake)

find_package(OpenMP REQUIRED
  COMPONENTS Fortran)

include(cmake/ombOpenMPOptions.cmake)


# Now figure out how the tools should be used.
set(OMB_INT_TYPE "int64" CACHE STRING "Size of integers used in loop constructs (type
named according to iso_fortran_env).")
set_property(CACHE OMB_INT_TYPE
  PROPERTY STRINGS int32 int64)

# Append choice to fypp flags
list(APPEND OMB_FYPP_FLAGS -DOMB_INT_TYPE="'${OMB_INT_TYPE}'")

# Determine whether arrays should be allocated, or stack-bound
set(OMB_ALLOC_TYPE "stack" CACHE STRING "How the arrays are constructed
[allocatable, pointer, stack].")
set_property(CACHE OMB_ALLOC_TYPE
  PROPERTY STRINGS allocatable pointer stack)

# Append choice to fypp flags
list(APPEND OMB_FYPP_FLAGS -DOMB_ALLOC_TYPE="'${OMB_ALLOC_TYPE}'")


# Generally we do not need the rt library.
# However, it should provide extended runtime precision for timers.
# For GCC this is implicitly linked when using OpenMP.
# So currently not really used...
find_library(SysLib_rt
  rt
  DOC "The runtime library for extended timing precision."
)


find_package(MPI
  COMPONENTS Fortran)

option(OMB_WITH_MPI "Install omb with MPI support" FALSE)
if( OMB_WITH_MPI )
  list(APPEND OMB_FYPP_FLAGS "-DOMB_MPI=1")
endif()


# Add the sources for the binary
add_subdirectory(src)


# Globally define a place where we will install
# cmake configuration stuff, *Target.cmake *Version.cmake etc.
set(OMB_INSTALL_CMAKECONFIG_DIR
  "${CMAKE_INSTALL_LIBDIR}/cmake/${PROJECT_NAME}"
  CACHE STRING
  "Determine where the CMake configuration files will be installed"
)
mark_as_advanced(OMB_INSTALL_CMAKECONFIG_DIR)


# Require API compatibility via semantic versioning for static linking.
set(COMPATIBILITY SameMajorVersion)


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
