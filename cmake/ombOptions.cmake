# --- compiler feature checks
include(CheckFortranSourceCompiles)
include(CheckFortranSourceRuns)

message(STATUS "Checking fortran features")
list(APPEND CMAKE_MESSAGE_INDENT "  ")

# We will prefix all options with omb_HAS_Fortran_<feature>
# This will be used at the compilation stage where we will add
# these flags.
# Some compilers may have these details.

CHECK_START("* has iso_fortran_env: int32, int64")
set(source "
use, intrinsic :: iso_fortran_env, only : int32, int64
integer(int32) :: i32
integer(int64) :: i64
i32 = 1
i64 = 1
print *, i32, i64
end")
check_fortran_source_compiles("${source}" f_iso_fortran_env_int SRC_EXT f90)
CHECK_PASS_FAIL( f_iso_fortran_env_int REQUIRED )


CHECK_START("* has iso_fortran_env: real${prec}")
macro(CHECK_REAL prec)
set(source "
use, intrinsic :: iso_fortran_env, only : real${prec}
real(real${prec}) :: r
r = 1.
print *, sin(r)
end")
check_fortran_source_compiles("${source}" f_iso_fortran_env_${prec} SRC_EXT f90)
CHECK_PASS_FAIL( f_iso_fortran_env_${prec} QUIET ${ARGN} )
endmacro()

# Check all the real* variants from iso_fortran_env
CHECK_REAL(16)
CHECK_REAL(32 REQUIRED)
CHECK_REAL(64 REQUIRED)
CHECK_REAL(128)
if( f_iso_fortran_env_16 )
  list(APPEND OMB_FYPP_FLAGS "-DOMB_REAL16")
endif()
if( f_iso_fortran_env_128 )
  list(APPEND OMB_FYPP_FLAGS "-DOMB_REAL128")
endif()
list(POP_BACK CMAKE_MESSAGE_INDENT)


CHECK_START("* has CONTIGUOUS")
# Check that the contiguous attribute works
set(source "
real, pointer, contiguous :: x(:) => null()
allocate(x(100))
x = 1
print *, sum(x)
end")
check_fortran_source_compiles("${source}" f_contiguous SRC_EXT f90)
CHECK_PASS_FAIL( f_contiguous )


CHECK_START("* has OOP")
# Check that object oriented programming is functional
set(source "
type :: options_t
end type
type, extends(options_t) :: options_1_t
integer :: i
end type
type(options_1_t) :: t
t%i = 1
print *, t%i
end")
check_fortran_source_compiles("${source}" f_oop SRC_EXT f90)
CHECK_PASS_FAIL( f_oop REQUIRED )


if( error_omb )
  message(FATAL_ERROR "Some fortran features are not available, please select another compiler")
endif()
list(POP_BACK CMAKE_MESSAGE_INDENT)
