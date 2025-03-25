# This code segments relies on MPI
cmake_push_check_state()

# Append to the list of libraries required to compile the test sources
list(APPEND CMAKE_REQUIRED_LIBRARIES MPI::MPI_Fortran)

message(STATUS "Checking MPI mpi_f08 module")
list(APPEND CMAKE_MESSAGE_INDENT "  ")

CHECK_START("* has places information")
set(source "
use mpi_f08
integer :: size, ierr
call MPI_Comm_size(MPI_COMM_WORLD, size, ierr)
end")
check_fortran_source_compiles("${source}" f_mpi_f08_mod SRC_EXT f90)
CHECK_PASS_FAIL( f_mpi_f08_mod REQUIRED )


if( error_omb )
  message(FATAL_ERROR "Some MPI fortran features are not available, please update your
  MPI provider")
endif()
list(POP_BACK CMAKE_MESSAGE_INDENT)
cmake_pop_check_state()
