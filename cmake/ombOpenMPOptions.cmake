# This code depends on ombOptions.cmake
# But also on OpenMP... What is clearest, find_package(OpenMP) here, or?
# For now it is at the top-level (for user clarity)

# This code segments relies on OpenMP
set(CMAKE_REQUIRED_LIBRARIES OpenMP::OpenMP_Fortran)

message(STATUS "Checking OpenMP fortran features")
list(APPEND CMAKE_MESSAGE_INDENT "  ")

CHECK_START("* has places information")
set(source "
use omp_lib
!$omp parallel
print * , omp_get_place_num()
print * , omp_get_place_num_procs(0)
!$omp end parallel
end")
check_fortran_source_compiles("${source}" f_omp_places SRC_EXT f90)
CHECK_PASS_FAIL( f_omp_places REQUIRED )

CHECK_START("* has device information")
set(source "
use omp_lib
!$omp parallel
print * , omp_get_num_devices()
print * , omp_get_default_device()
print * , omp_get_device_num()
!$omp end parallel
end")
check_fortran_source_compiles("${source}" f_omp_device SRC_EXT f90)
CHECK_PASS_FAIL( f_omp_device )
if( NOT f_omp_device )
  list(APPEND OMB_FYPP_FLAGS "-DOMB_OMP_DEVICE=0")
endif()

CHECK_START("* has team information")
set(source "
use omp_lib
!$omp parallel
print * , omp_get_num_teams()
print * , omp_get_team_num()
!$omp end parallel
end")
check_fortran_source_compiles("${source}" f_omp_teams SRC_EXT f90)
CHECK_PASS_FAIL( f_omp_teams )
if( NOT f_omp_teams )
  list(APPEND OMB_FYPP_FLAGS "-DOMB_OMP_TEAMS=0")
endif()

CHECK_START("* has partition information")
set(source "
use omp_lib
!$omp parallel
print * , omp_get_partition_num_places()
!$omp end parallel
end")
check_fortran_source_compiles("${source}" f_omp_partition SRC_EXT f90)
CHECK_PASS_FAIL( f_omp_partition )
if( NOT f_omp_partition )
  list(APPEND OMB_FYPP_FLAGS "-DOMB_OMP_PARTITION=0")
endif()

CHECK_START("* has masked construct (master deprecated [5.1])")
set(source "
use omp_lib
!$omp parallel
!$omp masked
print * , omp_get_num_threads()
!$omp end masked
!$omp end parallel
end")
check_fortran_source_compiles("${source}" f_omp_masked SRC_EXT f90)
CHECK_PASS_FAIL( f_omp_masked )
if( f_omp_masked )
  list(APPEND OMB_FYPP_FLAGS "-DOMB_OMP_MASKED=\"'masked'\"")
else()
  list(APPEND OMB_FYPP_FLAGS "-DOMB_OMP_MASKED=\"'master'\"")
endif()


if( error_fortran )
  message(FATAL_ERROR "Some fortran features are not available, please select another compiler")
endif()
list(POP_BACK CMAKE_MESSAGE_INDENT)
