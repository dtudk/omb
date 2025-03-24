# Here we define all options that are related to fdict

# --- compiler feature checks
include(CheckFortranSourceCompiles)
include(CheckFortranSourceRuns)


# Ensure we have the program fypp installed
find_program(OMB_FYPP fypp
  HINTS "${PROJECT_SOURCE_DIR}/utils"
  DOC
    "A fortran pre-processor required for building the source code before compilation."
  REQUIRED
  )

# Internal variable to signal a problem of, some sort, then we can run through them
# all, then break
set(error_fortran FALSE)

macro(check_start msg)
  message(CHECK_START "${msg}")
  list(APPEND CMAKE_MESSAGE_INDENT "  ")
endmacro()
macro(check_pass_fail)
  cmake_parse_arguments(_cf "REQUIRED" "PASS;FAIL" "" ${ARGN})
  if( NOT DEFINED _cf_PASS )
    set(_cf_PASS "found")
  endif()
  if( NOT DEFINED _cf_FAIL )
    set(_cf_FAIL "not found")
  endif()
  list(POP_FRONT _cf_UNPARSED_ARGUMENTS _cpf_VARIABLE)

  list(POP_BACK CMAKE_MESSAGE_INDENT)
  if( ${${_cpf_VARIABLE}} )
    message(CHECK_PASS "${_cf_PASS}")
  else()
    if( _cf_REQUIRED )
      message(CHECK_FAIL "${_cf_FAIL} [required]")
      set(error_fortran TRUE)
    else()
      message(CHECK_FAIL "${_cf_FAIL}")
    endif()
  endif()
endmacro()


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


if( error_fortran )
  message(FATAL_ERROR "Some fortran features are not available, please select another compiler")
endif()
list(POP_BACK CMAKE_MESSAGE_INDENT)
