# --- compiler feature checks
include(CheckFortranSourceCompiles)
include(CheckFortranSourceRuns)

message(STATUS "Checking fortran features")
list(APPEND CMAKE_MESSAGE_INDENT "  ")

# We will prefix all options with omb_HAS_Fortran_<feature>
# This will be used at the compilation stage where we will add
# these flags.
# Some compilers may have these details.

# Whether we should use the iso_fortran_env for data-types

CHECK_START("* has iso_fortran_env")
# Check that iso_fortran_env is present
set(source "
use, intrinsic :: iso_fortran_env, only : real64, int32, real128
real(real64) :: x
x = x+1._real64
end")
check_fortran_source_compiles("${source}" f_iso_fortran_env SRC_EXT f90)
CHECK_PASS_FAIL( f_iso_fortran_env REQUIRED)


CHECK_START("* has CONTIGUOUS")
# Check that the contiguous attribute works
set(source "
real, pointer, contiguous :: x(:)
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
end")
check_fortran_source_compiles("${source}" f_oop SRC_EXT f90)
CHECK_PASS_FAIL( f_oop REQUIRED)


if( error_omb )
  message(FATAL_ERROR "Some fortran features are not available, please select another compiler")
endif()
list(POP_BACK CMAKE_MESSAGE_INDENT)
