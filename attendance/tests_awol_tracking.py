"""
Test cases for AWOL tracking with half-day leave scenarios.

Run with: python manage.py test attendance.tests_awol_tracking
"""
from datetime import date, time, timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from django.contrib.auth import get_user_model

from attendance.models import DailyAttendance, LeaveRequest, LeaveBalance

User = get_user_model()


class AWOLTrackingTestCase(TestCase):
    """Test AWOL tracking logic with various attendance scenarios."""

    def setUp(self):
        """Create test employee."""
        self.employee = User.objects.create_user(
            username='testemployee',
            email='test@example.com',
            password='testpass123',
            first_name='Test',
            last_name='Employee'
        )
        
        # Create leave balance
        LeaveBalance.objects.create(
            employee=self.employee,
            year=2026,
            sick_leave_total=5,
            emergency_leave_total=5
        )
        
        self.today = date(2026, 2, 9)

    def test_three_consecutive_absents_triggers_awol(self):
        """Test that 3 consecutive ABSENT days triggers AWOL flag."""
        for i in range(3):
            test_date = self.today - timedelta(days=2-i)
            attendance = DailyAttendance.objects.create(
                employee=self.employee,
                date=test_date,
                attendance_type='ABSENT'
            )
            
            if i < 2:
                self.assertFalse(attendance.is_awol, f"Day {i+1} should not trigger AWOL")
            else:
                self.assertTrue(attendance.is_awol, "Day 3 should trigger AWOL")
                self.assertEqual(attendance.consecutive_absences, 3)

    def test_half_day_without_leave_counts_as_unexcused(self):
        """Test that HALF_DAY without matching leave counts toward AWOL."""
        # Day 1: Half day work, no leave
        day1 = DailyAttendance.objects.create(
            employee=self.employee,
            date=self.today - timedelta(days=2),
            clock_in=timezone.make_aware(timezone.datetime.combine(
                self.today - timedelta(days=2), time(8, 0)
            )),
            clock_out=timezone.make_aware(timezone.datetime.combine(
                self.today - timedelta(days=2), time(13, 0)
            )),
            attendance_type='HALF_DAY',
            paid_hours=Decimal('4.00')
        )
        self.assertTrue(day1.is_unexcused_absence())
        
        # Day 2: Half day work, no leave
        day2 = DailyAttendance.objects.create(
            employee=self.employee,
            date=self.today - timedelta(days=1),
            clock_in=timezone.make_aware(timezone.datetime.combine(
                self.today - timedelta(days=1), time(8, 0)
            )),
            clock_out=timezone.make_aware(timezone.datetime.combine(
                self.today - timedelta(days=1), time(13, 0)
            )),
            attendance_type='HALF_DAY',
            paid_hours=Decimal('4.00')
        )
        day2._update_awol_tracking()
        self.assertEqual(day2.consecutive_absences, 2)
        
        # Day 3: Half day work, no leave - should trigger AWOL
        day3 = DailyAttendance.objects.create(
            employee=self.employee,
            date=self.today,
            clock_in=timezone.make_aware(timezone.datetime.combine(
                self.today, time(8, 0)
            )),
            clock_out=timezone.make_aware(timezone.datetime.combine(
                self.today, time(13, 0)
            )),
            attendance_type='HALF_DAY',
            paid_hours=Decimal('4.00')
        )
        day3._update_awol_tracking()
        self.assertEqual(day3.consecutive_absences, 3)
        self.assertTrue(day3.is_awol)

    def test_half_day_with_matching_leave_is_excused(self):
        """Test that HALF_DAY with proper leave coverage doesn't count toward AWOL."""
        test_date = self.today - timedelta(days=1)
        
        # Create approved half-day leave for PM shift
        leave = LeaveRequest.objects.create(
            employee=self.employee,
            leave_type='SICK',
            date=test_date,
            is_half_day=True,
            shift_period='PM',
            reason='Doctor appointment',
            status='APPROVED'
        )
        
        # Create attendance: worked AM shift (clock in before 1 PM)
        attendance = DailyAttendance.objects.create(
            employee=self.employee,
            date=test_date,
            clock_in=timezone.make_aware(timezone.datetime.combine(
                test_date, time(8, 0)
            )),
            clock_out=timezone.make_aware(timezone.datetime.combine(
                test_date, time(13, 0)
            )),
            attendance_type='HALF_DAY',
            paid_hours=Decimal('4.00')
        )
        
        # Should be excused (worked AM, has PM leave)
        self.assertFalse(attendance.is_unexcused_absence())
        attendance._update_awol_tracking()
        self.assertEqual(attendance.consecutive_absences, 0)
        self.assertFalse(attendance.is_awol)

    def test_full_day_work_resets_awol_counter(self):
        """Test that working a FULL_DAY resets consecutive absence counter."""
        # Day 1: Absent
        day1 = DailyAttendance.objects.create(
            employee=self.employee,
            date=self.today - timedelta(days=2),
            attendance_type='ABSENT'
        )
        self.assertEqual(day1.consecutive_absences, 1)
        
        # Day 2: Full day work - should reset
        day2 = DailyAttendance.objects.create(
            employee=self.employee,
            date=self.today - timedelta(days=1),
            clock_in=timezone.make_aware(timezone.datetime.combine(
                self.today - timedelta(days=1), time(8, 0)
            )),
            clock_out=timezone.make_aware(timezone.datetime.combine(
                self.today - timedelta(days=1), time(18, 0)
            )),
            attendance_type='FULL_DAY',
            paid_hours=Decimal('8.00')
        )
        day2._update_awol_tracking()
        self.assertEqual(day2.consecutive_absences, 0)
        self.assertFalse(day2.is_awol)
        
        # Day 3: Absent - counter should restart
        day3 = DailyAttendance.objects.create(
            employee=self.employee,
            date=self.today,
            attendance_type='ABSENT'
        )
        day3._update_awol_tracking()
        self.assertEqual(day3.consecutive_absences, 1)
        self.assertFalse(day3.is_awol)

    def test_partial_day_counts_as_unexcused(self):
        """Test that PARTIAL attendance always counts as unexcused."""
        attendance = DailyAttendance.objects.create(
            employee=self.employee,
            date=self.today,
            clock_in=timezone.make_aware(timezone.datetime.combine(
                self.today, time(8, 0)
            )),
            clock_out=timezone.make_aware(timezone.datetime.combine(
                self.today, time(10, 30)
            )),
            attendance_type='PARTIAL',
            paid_hours=Decimal('2.50')
        )
        
        self.assertTrue(attendance.is_unexcused_absence())

    def test_invalid_attendance_counts_as_unexcused(self):
        """Test that INVALID/REJECTED attendance counts toward AWOL."""
        attendance = DailyAttendance.objects.create(
            employee=self.employee,
            date=self.today,
            attendance_type='INVALID',
            status='REJECTED'
        )
        
        self.assertTrue(attendance.is_unexcused_absence())
