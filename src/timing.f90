module timing_m

   ! Very simple timing module.
   ! This timing module only works if compiled with OpenMP
   ! It uses omp_get_wtime for accessing timing.
   use iso_fortran_env, only: real64, int64

   implicit none

   private

   integer(int64), save :: count_rate, count_max
   real(real64), save :: rcount_rate

   public :: timing_initialize
   public :: timing_get_sys_rate
   public :: timing_get_sys_max

   type, public :: timing_t

      real(real64) :: time
      real(real64), private :: t0

   contains

      procedure, pass :: start
      procedure, pass :: stop

   end type

contains

   subroutine timing_initialize()
      integer(int64) :: count

      ! Initialize the variables for determining the timings
      call system_clock(count, count_rate, count_max)
      rcount_rate = real(count_rate, real64)

   end subroutine

   function timing_get_sys_rate() result(rate)
      integer(int64) :: rate
      rate = count_rate
   end function

   function timing_get_sys_max() result(ma)
      integer(int64) :: ma
      ma = count_max
   end function

   subroutine start(timing)
!$    use omp_lib, only: omp_get_wtime
      class(timing_t), intent(inout) :: timing

!$    timing%t0 = omp_get_wtime()

   end subroutine start

   subroutine stop(timing, store)
!$    use omp_lib, only: omp_get_wtime
      class(timing_t), intent(inout) :: timing
      real(real64), intent(out), optional :: store

!$    timing%time = omp_get_wtime() - timing%t0

      if (present(store)) then
         store = timing%time
      end if

   end subroutine stop

end module timing_m
