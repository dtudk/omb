
# Install the script programs
install(
  PROGRAMS omb-driver.sh
  TYPE "BIN"
  # Omit the .sh suffix
  RENAME omb-driver
  PERMISSIONS
    OWNER_READ OWNER_WRITE OWNER_EXECUTE
    GROUP_READ GROUP_EXECUTE
    WORLD_READ WORLD_EXECUTE
)
