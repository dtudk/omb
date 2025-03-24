if (NOT DEFINED CMAKE_Fortran_MODULE_DIRECTORY)
  set(CMAKE_Fortran_MODULE_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}/include)
endif ()


if(CMAKE_Fortran_COMPILER_ID STREQUAL "GNU")
  # GNU compiler gfortran
  set(
    CMAKE_Fortran_FLAGS_INIT
    "-fimplicit-none"
  )
  set(
    CMAKE_Fortran_FLAGS_RELEASE_INIT
    "-O3"
    "-march=native"
    "-ftree-vectorize"
    "-fprefetch-loop-arrays"
  )
  set(
    CMAKE_Fortran_FLAGS_FAST_INIT
    "-O3"
    "-march=native"
    "-ftree-vectorize"
    "-fprefetch-loop-arrays"
    "-ffast-math"
  )
  set(
    CMAKE_Fortran_FLAGS_DEBUG_INIT
    "-g"
    "-Og"
    "-Wall"
    "-Wextra"
    "-Wimplicit-procedure"
  )
elseif(CMAKE_Fortran_COMPILER_ID MATCHES "^IntelLLVM")
  # Intel (LLVM based) compiler ifx
  set(
    CMAKE_Fortran_FLAGS_INIT
  )
  set(
    CMAKE_Fortran_FLAGS_RELEASE_INIT
    "-O3"
    "-xHost"
    "-fp-model=strict"
  )
  set(
    CMAKE_Fortran_FLAGS_FAST_INIT
    "-O3"
    "-xHost"
    "-fp-model=fast"
  )
  set(
    CMAKE_Fortran_FLAGS_DEBUG_INIT
    "-g"
    "-Og"
    "-warn declarations,general,usage,interfaces,unused"
  )
elseif(CMAKE_Fortran_COMPILER_ID MATCHES "^Intel")
  # Intel-classic compiler ifort
  set(
    CMAKE_Fortran_FLAGS_INIT
  )
  set(
    CMAKE_Fortran_FLAGS_RELEASE_INIT
    "-O3"
    "-xHost"
    "-fp-model=strict"
    "-prec-div"
    "-prec-sqrt"
  )
  set(
    CMAKE_Fortran_FLAGS_FAST_INIT
    "-O3"
    "-xHost"
    "-fp-model=fast"
  )
  set(
    CMAKE_Fortran_FLAGS_DEBUG_INIT
    "-g"
    "-Og"
    "-warn declarations,general,usage,interfaces,unused"
  )
elseif(CMAKE_Fortran_COMPILER_ID MATCHES "^LFortran")
  # LFortran compiler
  set(
    CMAKE_Fortran_FLAGS_INIT
  )
  set(
    CMAKE_Fortran_FLAGS_RELEASE_INIT
    "-O3"
  )
  set(
    CMAKE_Fortran_FLAGS_FAST_INIT
    "--fast"
  )
  set(
    CMAKE_Fortran_FLAGS_DEBUG_INIT
    "-g"
    "-Og"
  )
elseif(CMAKE_Fortran_COMPILER_ID MATCHES "^NVHPC")
  # NVIDIA SDK compiler
  set(
    CMAKE_Fortran_FLAGS_INIT
  )
  set(
    CMAKE_Fortran_FLAGS_RELEASE_INIT
    "-O3"
  )
  set(
    CMAKE_Fortran_FLAGS_FAST_INIT
    "-fast"
  )
  set(
    CMAKE_Fortran_FLAGS_DEBUG_INIT
    "-g"
    "-Og"
  )
else()
  # unknown compiler (possibly)
  set(
    CMAKE_Fortran_FLAGS_INIT
  )
  set(
    CMAKE_Fortran_FLAGS_RELEASE_INIT
  )
  set(
    CMAKE_Fortran_FLAGS_FAST_INIT
  )
  set(
    CMAKE_Fortran_FLAGS_DEBUG_INIT
  )
endif()

# Get the allowed values for CMAKE_BUILD_TYPE
get_property(build_types
  CACHE CMAKE_BUILD_TYPE
  PROPERTY STRINGS
)

# Convert the init variables to strings
list(JOIN CMAKE_Fortran_FLAGS_INIT " " CMAKE_Fortran_FLAGS_INIT)
foreach(build_type IN LISTS build_types)
  string(TOUPPER ${build_type} upper_bt)
  list(JOIN CMAKE_Fortran_FLAGS_${upper_bt}_INIT
    " " CMAKE_Fortran_FLAGS_${upper_bt}_INIT
  )
endforeach()
