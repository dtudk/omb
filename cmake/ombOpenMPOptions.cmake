# This code depends on ombOptions.cmake
# But also on OpenMP... What is clearest, find_package(OpenMP) here, or?
# For now it is at the top-level (for user clarity)

# This code segments relies on OpenMP
cmake_push_check_state()

# Append to the list of libraries required to compile the test sources
list(APPEND CMAKE_REQUIRED_LIBRARIES OpenMP::OpenMP_Fortran)

message(STATUS "OpenMP fortran")
list(APPEND CMAKE_MESSAGE_INDENT "  ")

# Print out information related to the Fortran standard
cmake_print_variables(OpenMP_Fortran_SPEC_DATE)
cmake_print_variables(OpenMP_Fortran_VERSION)

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
if( f_omp_device )
  list(APPEND OMB_FYPP_FLAGS "-DOMB_OMP_DEVICE")
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
if( f_omp_partition )
  list(APPEND OMB_FYPP_FLAGS "-DOMB_OMP_PARTITION")
endif()

CHECK_START("* has masked construct (master deprecated since 5.1)")
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

CHECK_START("* has nontemporal simd clause (5.0)")
set(source "
use omp_lib
real :: a(10)
integer :: i
!$omp parallel
!$omp do simd nontemporal(a)
do i = 1, 10
   a(i) = 0.0
end do
!$omp end do simd
!$omp end parallel
end")
check_fortran_source_compiles("${source}" f_omp_simd_nontemporal SRC_EXT f90)
CHECK_PASS_FAIL( f_omp_simd_nontemporal )
if( f_omp_simd_nontemporal )
  list(APPEND OMB_FYPP_FLAGS "-DOMB_OMP_SIMD_NONTEMPORAL")
endif()

# In case we have nvfortran < 26, we won't allow masked
# It merely states the *masked* construct as a warning, not a
# compilation error.
if(CMAKE_Fortran_COMPILER_ID MATCHES "^NVHPC")
  if(CMAKE_Fortran_COMPILER_VERSION VERSION_LESS 26)
    message(STATUS "  nvfortran compiles omp masked construct, but does not support it")
    message(STATUS "    forcefully disabling it")
    set( f_omp_masked FALSE)
  endif()
endif()
if( f_omp_masked )
  list(APPEND OMB_FYPP_FLAGS -DOMB_OMP_MASKED="masked")
else()
  list(APPEND OMB_FYPP_FLAGS -DOMB_OMP_MASKED="master")
endif()

CHECK_START("* has orphan construct")
set(source "
subroutine mysub(n, a)
integer, intent(in) :: n
real, intent(inout) :: a(n)
integer :: i
!$omp do private(i)
do i = 1, 100
   a(i) = i
end do
!$omp end do
end

program test
real :: a(100)
!$omp parallel shared(a)
call mysub(100, a)
!$omp end parallel
print *, sum(a)
end")
check_fortran_source_compiles("${source}" f_omp_orphan SRC_EXT f90)
CHECK_PASS_FAIL( f_omp_orphan REQUIRED )

CHECK_START("* has CPU loop construct")
set(source "
real :: a(100)
integer :: i
!$omp parallel shared(a)
!$omp loop private(i)
do i = 1, 100
   a(i) = i
end do
!$omp end loop
!$omp end parallel
print *, sum(a)
end")
check_fortran_source_compiles("${source}" f_omp_cpu_loop
  SRC_EXT f90)
CHECK_PASS_FAIL( f_omp_cpu_loop REQUIRED )

CHECK_START("* has taskloop construct")
set(source "
real :: a(100)
integer :: i
!$omp parallel shared(a)
!$omp single
!$omp taskloop private(i)
do i = 1, 100
   a(i) = i
end do
!$omp end taskloop
!$omp end single
!$omp end parallel
print *, sum(a)
end")
check_fortran_source_compiles("${source}" f_omp_taskloop SRC_EXT f90)
CHECK_PASS_FAIL( f_omp_taskloop )
if( f_omp_taskloop )
  list(APPEND OMB_FYPP_FLAGS "-DOMB_OMP_TASKLOOP")

  CHECK_START("* has taskloop simd construct")
set(source "
real :: a(100)
integer :: i
!$omp parallel shared(a)
!$omp single
!$omp taskloop simd private(i)
do i = 1, 100
   a(i) = i
end do
!$omp end taskloop simd
!$omp end single
!$omp end parallel
print *, sum(a)
end")
  check_fortran_source_compiles("${source}" f_omp_taskloop_simd SRC_EXT f90)
  CHECK_PASS_FAIL( f_omp_taskloop_simd REQUIRED )
  if( f_omp_taskloop_simd )
    list(APPEND OMB_FYPP_FLAGS "-DOMB_OMP_TASKLOOP_SIMD")
  endif()
endif()

CHECK_START("* has CPU teams construct")
set(source "
use omp_lib
!$omp parallel
print * , omp_get_num_teams()
print * , omp_get_team_num()
!$omp end parallel
!$omp teams
print *, omp_get_team_num()
!$omp end teams
end")
check_fortran_source_compiles("${source}" f_omp_cpu_teams SRC_EXT f90)
CHECK_PASS_FAIL( f_omp_cpu_teams )
if( f_omp_cpu_teams )
  list(APPEND OMB_FYPP_FLAGS "-DOMB_OMP_TEAMS")

  # Only check if teams is available
  CHECK_START("* has CPU teams distribute construct")
  set(source "
use omp_lib
real :: a(100)
integer :: i, nt, team
!$omp parallel
!$omp single
  nt = omp_get_num_threads()
!$omp end single
!$omp end parallel
!$omp teams private(i,team) shared(a) num_teams(nt) thread_limit(1)
team = omp_get_team_num()
!$omp distribute dist_schedule(static) private(i)
do i = 1, 100
   a(i) = i
end do
!$omp end distribute
!$omp end teams
print *, sum(a)
end")
  check_fortran_source_compiles("${source}" f_omp_cpu_teams_distribute SRC_EXT f90)
  CHECK_PASS_FAIL( f_omp_cpu_teams_distribute )
  if( f_omp_cpu_teams_distribute )
    list(APPEND OMB_FYPP_FLAGS "-DOMB_OMP_TEAMS_DISTRIBUTE")
  endif()

  CHECK_START("* has CPU teams parallel construct")
  set(source "
use omp_lib
real :: a(100)
integer :: i, nt, team
!$omp parallel
!$omp single
  nt = omp_get_num_threads()
!$omp end single
!$omp end parallel
!$omp teams private(i,team) shared(a) num_teams(1) thread_limit(nt)
team = omp_get_team_num()
!$omp parallel do private(i) shared(a)
do i = 1, 100
   a(i) = i
end do
!$omp end parallel do
!$omp end teams
print *, sum(a)
end")
  check_fortran_source_compiles("${source}" f_omp_cpu_teams_parallel SRC_EXT f90)
  CHECK_PASS_FAIL( f_omp_cpu_teams_parallel )
  if( f_omp_cpu_teams_parallel )
    list(APPEND OMB_FYPP_FLAGS "-DOMB_OMP_TEAMS_PARALLEL")
  endif()

endif()

if( error_omb )
  message(FATAL_ERROR "Some OpenMP fortran features are not available, please select another compiler")
endif()

list(POP_BACK CMAKE_MESSAGE_INDENT)
cmake_pop_check_state()
