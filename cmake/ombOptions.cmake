# Here we define all options that are related to fdict

# --- compiler feature checks
include(CheckFortranSourceCompiles)
include(CheckFortranSourceRuns)


# Ensure we have the program fypp installed
find_program(OMPBENCH_FYPP fypp
  HINTS "${PROJECT_SOURCE_DIR}/utils"
  )
if(NOT OMPBENCH_FYPP)
  message(FATAL_ERROR "Could not find executable fypp -- it is required for the pre-processing step")
endif()

# Internal variable to signal a problem of, some sort, then we can run through them
# all, then break
set(error_fortran FALSE)

macro(check_start msg)
  message(CHECK_START "${msg}")
  list(APPEND CMAKE_MESSAGE_INDENT "  ")
endmacro()
macro(check_pass msg)
  list(POP_BACK CMAKE_MESSAGE_INDENT)
  message(CHECK_PASS "${msg}")
endmacro()
macro(check_fail msg)
  list(POP_BACK CMAKE_MESSAGE_INDENT)
  message(CHECK_FAIL "${msg}")
endmacro()


message(STATUS "Checking fortran features")

# Whether we should use the iso_fortran_env for data-types
list(APPEND CMAKE_MESSAGE_INDENT "  ")

CHECK_START("* has iso_fortran_env")
# Check that it iso_fortran_env works
set(source "
use, intrinsic :: iso_fortran_env, only : real64, int32, real128
real(real64) :: x
x = x+1._real64
end")
check_fortran_source_compiles("${source}" f90_iso_fortran_env SRC_EXT f90)
if( f90_iso_fortran_env )
  CHECK_PASS("found")
else()
  CHECK_FAIL("not found")
  set(error_fortran TRUE)
endif()


CHECK_START("* has CONTIGUOUS")
# Check that it iso_fortran_env works
set(source "
real, pointer, contiguous :: x(:)
end")
check_fortran_source_compiles("${source}" f90_contiguous SRC_EXT f90)
if( f90_contiguous )
  CHECK_PASS("found")
else()
  CHECK_FAIL("not found")
  set(error_fortran TRUE)
endif()

if( error_fortran )
  message(FATAL_ERROR "Some fortran features are not available, please select another compiler")
endif()


list(POP_BACK CMAKE_MESSAGE_INDENT)
