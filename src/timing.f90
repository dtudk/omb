module timing_m

   ! Very simple timing module.
   ! This timing module only works if compiled with OpenMP
   ! It uses omp_get_wtime for accessing timing.
   use iso_fortran_env, only: real64

   implicit none

   private

   type, public :: timing_t

      real(real64) :: time
      real(real64), private :: t0

   contains

      procedure, pass :: start
      procedure, pass :: stop

   end type

contains

   subroutine start(timing)
!$    use omp_lib, only: omp_get_wtime
      class(timing_t), intent(inout) :: timing

!$    timing%t0 = omp_get_wtime()

   end subroutine start

   subroutine stop(timing)
!$    use omp_lib, only: omp_get_wtime
      class(timing_t), intent(inout) :: timing

!$    timing%time = omp_get_wtime() - timing%t0

   end subroutine stop

end module timing_m
