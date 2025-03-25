# Ensure we have the program fypp installed
find_program(OMB_FYPP fypp
  HINTS "${PROJECT_SOURCE_DIR}/utils"
  DOC
    "A fortran pre-processor required for building the source code before compilation."
  REQUIRED
)

CHECK_START("Checking ${OMB_FYPP}")
# If we are on a windows machine, we have to use the Python executable to
# Execute it.
execute_process(
  COMMAND "${OMB_FYPP}" --version
  RESULT_VARIABLE fypp_ret
  OUTPUT_VARIABLE fypp_stdout
)
if( NOT ${fypp_ret} EQUAL 0 )
  CHECK_START("Checking Python + fypp")

  message(CHECK_START "Searching for Python")

  # We likely need the Python executable in front...
  find_package(Python COMPONENTS Interpreter)

  if( Python_Interpreter_FOUND )
    message(CHECK_PASS "found")

    execute_process(
      COMMAND "${Python_EXECUTABLE}" "${OMB_FYPP}" --version
      RESULT_VARIABLE fypp_ret
      OUTPUT_VARIABLE fypp_stdout
    )
    if( ${fypp_ret} EQUAL 0 )
      set(OMB_FYPP "${Python_EXECUTABLE}" "${OMB_FYPP}")
    endif()
  else()
    message(CHECK_FAIL "not found")
  endif()

endif()
CHECK_PASS_FAIL(fypp_ret EXIT_CODE REQUIRED
  PASS "works"
)
message(STATUS "fypp --version: ${fypp_stdout}")
list(POP_BACK CMAKE_MESSAGE_INDENT)


# Below we setup the functions required to create the fyppified sources

# Preprocesses a list of files with given preprocessor and preprocessor options
#
# Args:
#     preproc [in]: Preprocessor program
#     preprocopts [in]: Preprocessor options
#     srcext [in]: File extension of the source files
#     trgext [in]: File extension of the target files
#     srcfiles [in]: List of the source files
#     trgfiles [out]: Contains the list of the preprocessed files on exit
#
function(omb_preprocess preproc preprocopts srcext trgext srcfiles trgfiles)

  set(_trgfiles)
  foreach(srcfile IN LISTS srcfiles)
    string(REGEX REPLACE "\\.${srcext}$" ".${trgext}" trgfile ${srcfile})

    add_custom_command(
      OUTPUT "${CMAKE_CURRENT_BINARY_DIR}/${trgfile}"
      COMMAND ${preproc} ${preprocopts} "${CMAKE_CURRENT_SOURCE_DIR}/${srcfile}" "${CMAKE_CURRENT_BINARY_DIR}/${trgfile}"
      WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
      MAIN_DEPENDENCY "${CMAKE_CURRENT_SOURCE_DIR}/${srcfile}"
    )

    # Collect files
    list(APPEND _trgfiles "${CMAKE_CURRENT_BINARY_DIR}/${trgfile}")
  endforeach()
  set(${trgfiles} ${_trgfiles} PARENT_SCOPE)

endfunction()

# Define a function for fyppifying sources
function(omb_fyppify)
 # Parse arguments
 set(options "")
 set(oneValueArgs FYPP EXTIN EXTOUT COMMENT OUTPUT)
 set(multiValueArgs FLAGS FILES)
 cmake_parse_arguments(
   _fyppify "${options}" "${oneValueArgs}" "${multiValueArgs}"
   ${ARGN}
   )

 # Now handle arguments
 #[==[
 message(INFO "Before parsing inputs:
 comment=${_fyppify_COMMENT}
 fypp=${_fyppify_FYPP}
 EXTIN=${_fyppify_EXTIN}
 EXTOUT=${_fyppify_EXTOUT}
 FLAGS=${_fyppify_FLAGS}
 FILES=${_fyppify_FILES}
 ")
 ]==]

 if(NOT DEFINED _fyppify_FYPP)
   set(_fyppify_FYPP "${OMB_FYPP}")
 endif()
 if(NOT DEFINED _fyppify_EXTIN)
   set(_fyppify_EXTIN "fypp")
 endif()
 if(NOT DEFINED _fyppify_EXTOUT)
   set(_fyppify_EXTOUT "f90")
 endif()
 if(DEFINED _fyppify_COMMENT)
   message(VERBOSE "-- fyppify: ${_fyppify_COMMENT}")
 endif()
 if(NOT DEFINED _fyppify_FLAGS)
   set(_fyppify_FLAGS "${OMB_FYPP_FLAGS}")
 endif()
 if(NOT DEFINED _fyppify_FILES)
   message(FATAL_ERROR "fyppify requires FILES arguments to determine which files to preprocess")
 endif()

 #[==[
 message(INFO "After parsing inputs:
 comment=${_fyppify_COMMENT}
 fypp=${_fyppify_FYPP}
 EXTIN=${_fyppify_EXTIN}
 EXTOUT=${_fyppify_EXTOUT}
 FLAGS=${_fyppify_FLAGS}
 FILES=${_fyppify_FILES}
 ")
 #]==]

 # Lets do the preprocessing
 omb_preprocess(
   "${_fyppify_FYPP}" "${_fyppify_FLAGS}"
   "${_fyppify_EXTIN}" "${_fyppify_EXTOUT}"
   "${_fyppify_FILES}" _outfiles
  )
 if(DEFINED _fyppify_OUTPUT)
   set(${_fyppify_OUTPUT} ${_outfiles} PARENT_SCOPE)
 endif()

endfunction()
