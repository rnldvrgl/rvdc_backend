# Attendance, Leave, and Payroll System - Implementation Guide

## Overview

A complete employee attendance and leave management system integrated with payroll, built on Django with strict business rules for data integrity and payroll accuracy.

---

## Business Rules Summary

### Attendance Rules

- **One attendance per employee per day** (enforced by unique constraint)
- **Standard shift**: 8:00 AM - 6:00 PM (10 clock hours)
- **Breaks**: 2 hours unpaid (12:00 PM and 3:00 PM), automatically deducted
- **Grace period**: 15 minutes (clock in by 8:14 AM = on time)

### Attendance Classification

- **FULL_DAY**: ≥10 clock hours → 8 paid hours
- **HALF_DAY**: 4-5 clock hours OR ≥30 min late → 4 paid hours
- **PARTIAL**: 5-10 clock hours → actual hours minus 2-hour break
- **ABSENT**: No clock-in/out
- **LEAVE**: Approved unpaid leave

### Late Policy

- **0-15 min late**: Grace period (no penalty)
- **16-29 min late**: ₱2 per minute penalty
- **≥30 min late**: Automatic HALF_DAY classification (no per-minute penalty)

### Overtime

- **Per-day basis**: Any paid hours >8 per day = 1.5× hourly rate
- Computed daily, then aggregated weekly

### Leave Management

- **Types**: Sick Leave, Emergency Leave (both unpaid)
- **Annual allocation**: 5 sick days + 5 emergency days
- **Reset date**: January 1 each year
- **Supports half-days**: 0.5 day increments

### Payroll

- **Period**: Saturday 00:00 - Friday 23:59
- **Pay day**: Following Saturday
- **Only APPROVED attendance** counts toward payroll
- **Hourly rate**: Derived from `basic_salary ÷ 8`
- **Late penalties**: Deducted from gross pay
- **Approval workflow**: Warn (but allow) if unapproved attendance exists

---

## Database Models

### DailyAttendance

Tracks daily attendance with computed metrics.

**Key Fields:**

- `employee` (FK to CustomUser)
- `date` (DateField)
- `clock_in`, `clock_out` (DateTimeField)
- `attendance_type` (FULL_DAY, HALF_DAY, PARTIAL, ABSENT, LEAVE)
- `total_hours`, `break_hours`, `paid_hours` (computed)
- `is_late`, `late_minutes`, `late_penalty_amount` (computed)
- `status` (PENDING, APPROVED, REJECTED)
- `approved_by`, `approved_at`

**Unique Constraint:** `(employee, date)`

**Methods:**

- `compute_attendance_metrics()` - Auto-computes hours, type, penalties
- `approve(user)` - Approve attendance
- `reject(user, reason)` - Reject attendance

### LeaveBalance

Tracks annual leave balances per employee.

**Key Fields:**

- `employee` (FK to CustomUser)
- `year` (PositiveIntegerField)
- `sick_leave_total`, `sick_leave_used`
- `emergency_leave_total`, `emergency_leave_used`

**Unique Constraint:** `(employee, year)`

**Properties:**

- `sick_leave_remaining`
- `emergency_leave_remaining`

**Methods:**

- `can_take_leave(leave_type, days)` - Check balance
- `deduct_leave(leave_type, days)` - Deduct from balance
- `restore_leave(leave_type, days)` - Restore (on cancellation)

### LeaveRequest

Leave approval workflow.

**Key Fields:**

- `employee` (FK to CustomUser)
- `leave_type` (SICK, EMERGENCY)
- `date` (DateField)
- `is_half_day` (BooleanField)
- `reason` (TextField)
- `status` (PENDING, APPROVED, REJECTED, CANCELLED)
- `approved_by`, `approved_at`

**Methods:**

- `approve(user)` - Approve, deduct balance, create DailyAttendance
- `reject(user, reason)` - Reject request
- `cancel()` - Cancel approved leave, restore balance

---

## API Endpoints

### Daily Attendance

**List/Filter:**

```
GET /api/attendance/daily-attendance/
Query params: employee_id, status, date_from, date_to
```

**Clock In:**

```
POST /api/attendance/daily-attendance/clock_in/
{
  "employee_id": 1,
  "date": "2026-01-27",
  "clock_in": "2026-01-27T08:00:00Z",
  "notes": "Optional notes"
}
```

**Clock Out:**

```
POST /api/attendance/daily-attendance/clock_out/
{
  "attendance_id": 123,
  "clock_out": "2026-01-27T18:00:00Z",
  "notes": "Optional notes"
}
```

**Approve Attendance:**

```
POST /api/attendance/daily-attendance/approve/
{
  "attendance_ids": [1, 2, 3]
}
```

**Reject Attendance:**

```
POST /api/attendance/daily-attendance/reject/
{
  "attendance_ids": [4, 5],
  "reason": "Invalid clock times"
}
```

**Pending Approvals:**

```
GET /api/attendance/daily-attendance/pending_approvals/
```

### Leave Balance

**List:**

```
GET /api/attendance/leave-balance/
Query params: employee_id, year
```

**My Balance:**

```
GET /api/attendance/leave-balance/my_balance/
```

### Leave Requests

**Create:**

```
POST /api/attendance/leave-request/
{
  "employee": 1,  # Optional for admin/manager
  "leave_type": "SICK",
  "date": "2026-01-30",
  "is_half_day": false,
  "reason": "Medical appointment"
}
```

**Approve Leave:**

```
POST /api/attendance/leave-request/approve/
{
  "leave_request_ids": [1, 2]
}
```

**Reject Leave:**

```
POST /api/attendance/leave-request/reject/
{
  "leave_request_ids": [3],
  "reason": "Insufficient coverage"
}
```

**Cancel Leave:**

```
POST /api/attendance/leave-request/{id}/cancel/
```

**Pending Approvals:**

```
GET /api/attendance/leave-request/pending_approvals/
```

---

## Permissions

### Admin & Manager

- Full access to all endpoints
- Can clock in/out any employee
- Can approve/reject attendance and leave
- Can view all records

### Clerk & Technician

- Read-only access to their own records
- Can create leave requests for themselves
- Cannot clock in/out
- Cannot approve/reject

---

## Payroll Integration

### Using DailyAttendance for Payroll

The `WeeklyPayroll` model now has a new method: `compute_from_daily_attendance()`

**Usage:**

```python
from payroll.models import WeeklyPayroll
from datetime import date

# Get or create weekly payroll
payroll, created = WeeklyPayroll.objects.get_or_create(
    employee=employee,
    week_start=date(2026, 1, 25),  # Saturday
    defaults={
        'hourly_rate': employee.basic_salary / 8,
        'overtime_threshold': 40,
        'overtime_multiplier': 1.50,
    }
)

# Compute from daily attendance
payroll.compute_from_daily_attendance(
    include_unapproved=False,  # Only approved attendance
    allowances=500,
    extra_flat_deductions={'Uniform': 200},
    percent_deductions={'Tax': 0.12},
)

payroll.save()
```

**What it does:**

1. Fetches approved `DailyAttendance` records for the week
2. Computes **per-day overtime**: paid hours >8/day = 1.5×
3. Accumulates **late penalties** as deductions
4. Applies holiday premiums, allowances, statutory deductions
5. Calculates gross and net pay

### Old vs. New Method

| Method                            | Data Source                      | Overtime Logic | Late Penalties  |
| --------------------------------- | -------------------------------- | -------------- | --------------- |
| `compute_from_time_entries()`     | TimeEntry (raw clock records)    | Weekly >40 hrs | Not supported   |
| `compute_from_daily_attendance()` | DailyAttendance (business rules) | Daily >8 hrs   | ₱2/min included |

**Recommendation**: Use `compute_from_daily_attendance()` for new payroll system.

---

## Management Commands

### Initialize Leave Balances

Run at the start of each year (or for new employees):

```bash
docker compose exec api python manage.py init_leave_balances --year 2026
```

**What it does:**

- Creates `LeaveBalance` for all active employees
- Allocates 5 sick + 5 emergency days
- Skips employees who already have balances for that year

---

## Admin Interface

All models are registered in Django Admin with custom actions:

### DailyAttendance Admin

- **List view**: Employee, date, type, paid hours, late penalty, status
- **Actions**: Bulk approve, bulk reject
- **Read-only fields**: Computed metrics (hours, penalties)

### LeaveBalance Admin

- **List view**: Employee, year, remaining sick/emergency days
- **Color-coded**: Green (≥3), Orange (1-2), Red (0 days)

### LeaveRequest Admin

- **List view**: Employee, type, date, days, status
- **Actions**: Bulk approve, bulk reject
- **Error handling**: Shows insufficient balance errors

---

## Signals

### Auto-create Leave Balance

When a new employee is created:

```python
@receiver(post_save, sender=CustomUser)
def create_leave_balance_for_new_employee(sender, instance, created, **kwargs):
    if created:
        LeaveBalance.objects.get_or_create(
            employee=instance,
            year=date.today().year,
            defaults={'sick_leave_total': 5, 'emergency_leave_total': 5}
        )
```

Registered in `attendance/signals.py`.

---

## Workflow Examples

### Example 1: Clock In/Out with Late Penalty

**Scenario**: Employee arrives at 8:20 AM (20 min late), leaves at 6:00 PM.

1. Admin clocks in employee via API:

```json
POST /api/attendance/daily-attendance/clock_in/
{
  "employee_id": 5,
  "date": "2026-01-27",
  "clock_in": "2026-01-27T08:20:00+08:00"
}
```

2. Admin clocks out at end of day:

```json
POST /api/attendance/daily-attendance/clock_out/
{
  "attendance_id": 123,
  "clock_out": "2026-01-27T18:00:00+08:00"
}
```

3. System auto-computes:
   - **Total hours**: 9.67 hrs
   - **Late**: 5 min beyond grace (20 - 15 = 5 min)
   - **Late penalty**: ₱10 (5 min × ₱2)
   - **Attendance type**: PARTIAL (9.67 hrs - 2 hr break = 7.67 paid hrs)

4. Manager approves:

```json
POST /api/attendance/daily-attendance/approve/
{"attendance_ids": [123]}
```

5. Payroll computation:
   - Regular hours: 7.67 hrs × hourly_rate
   - Deductions: ₱10 late penalty

---

### Example 2: Half-Day Due to Late Arrival

**Scenario**: Employee arrives at 8:35 AM (35 min late).

1. Clock in at 8:35 AM → **≥30 min late**
2. System auto-classifies as **HALF_DAY**:
   - Paid hours: 4.00 (fixed)
   - Late penalty: ₱0 (already penalized via half-day)
3. No per-minute penalty applied

---

### Example 3: Leave Request Approval

**Scenario**: Employee requests sick leave for Jan 30.

1. Employee submits leave:

```json
POST /api/attendance/leave-request/
{
  "leave_type": "SICK",
  "date": "2026-01-30",
  "is_half_day": false,
  "reason": "Doctor's appointment"
}
```

2. Manager approves:

```json
POST /api/attendance/leave-request/approve/
{"leave_request_ids": [45]}
```

3. System:
   - Checks balance: 5 sick days available ✓
   - Deducts 1 day: `sick_leave_used = 1`
   - Creates `DailyAttendance`:
     - Type: LEAVE
     - Status: APPROVED
     - Paid hours: 0

4. Payroll: Employee not paid for Jan 30 (unpaid leave).

---

### Example 4: Weekly Payroll Computation

**Scenario**: Compute payroll for week of Jan 25-31 (Sat-Fri).

```python
from payroll.models import WeeklyPayroll
from datetime import date

employee = CustomUser.objects.get(id=5)
payroll = WeeklyPayroll.objects.create(
    employee=employee,
    week_start=date(2026, 1, 25),
    hourly_rate=employee.basic_salary / 8,  # e.g., 600 / 8 = 75/hr
)

payroll.compute_from_daily_attendance()
payroll.status = 'approved'
payroll.save()
```

**Sample DailyAttendance for the week:**

- **Jan 27 (Mon)**: 8 paid hrs
- **Jan 28 (Tue)**: 9 paid hrs → 8 reg + 1 OT
- **Jan 29 (Wed)**: 7.67 paid hrs (late penalty: ₱10)
- **Jan 30 (Thu)**: LEAVE (0 paid hrs)
- **Jan 31 (Fri)**: 8 paid hrs

**Computation:**

- Regular hours: 8 + 8 + 7.67 + 0 + 8 = 31.67 hrs @ ₱75 = ₱2,375.25
- Overtime: 1 hr @ (₱75 × 1.5) = ₱112.50
- Gross: ₱2,487.75
- Deductions:
  - Late penalty: ₱10
  - SSS: ₱100
  - PhilHealth: ₱50
  - Pag-IBIG: ₱50
  - Total: ₱210
- **Net pay**: ₱2,277.75

---

## Testing Checklist

### Attendance

- [ ] Clock in employee before 8:15 AM → no late penalty
- [ ] Clock in at 8:20 AM → ₱10 late penalty (5 min × ₱2)
- [ ] Clock in at 8:35 AM → HALF_DAY auto-classification
- [ ] Work 10+ hours → FULL_DAY (8 paid hrs)
- [ ] Work 6 hours → PARTIAL (4 paid hrs after break)
- [ ] Cannot create duplicate attendance for same date
- [ ] Only APPROVED attendance visible in payroll

### Leave

- [ ] Request sick leave → deducts from balance
- [ ] Request when balance = 0 → rejected
- [ ] Cancel approved leave → restores balance
- [ ] Half-day leave deducts 0.5 days
- [ ] Leave creates LEAVE-type DailyAttendance

### Payroll

- [ ] Per-day overtime: 9 paid hrs = 8 reg + 1 OT @ 1.5×
- [ ] Late penalties included in deductions
- [ ] Unpaid leaves excluded from hours
- [ ] Weekly total computed correctly
- [ ] Holiday premiums applied

---

## Security Considerations

### Data Integrity

- **Unique constraints**: One attendance per employee per day
- **Approval workflow**: Dual-control (creator ≠ approver)
- **Soft deletes**: No hard deletes on payroll-related records
- **Audit trail**: `created_at`, `updated_at`, `approved_by`, `approved_at`

### Permission Enforcement

- **API-level**: `IsAdminOrManager` permission class
- **Model-level**: Validation in `clean()` methods
- **View-level**: Role checks in viewsets

### Payroll Accuracy

- **Immutable history**: Once approved, leave balances cannot be retroactively changed
- **Decimal precision**: All monetary values use `Decimal` with `ROUND_HALF_UP`
- **Validation**: Cannot approve leave without sufficient balance
- **Late penalties**: Auto-computed, not manually editable

---

## Future Enhancements

### Potential Features

1. **Biometric integration**: Auto clock-in via fingerprint scanner
2. **Geofencing**: Validate clock-in location
3. **Shift scheduling**: Support multiple shift types (night, split)
4. **Reports**: Export attendance/payroll to Excel
5. **Notifications**: Email/SMS for pending approvals
6. **Mobile app**: Employee self-service portal
7. **Carry-forward**: Unused leave days → next year (with limits)

---

## Troubleshooting

### Issue: Migrations fail

**Solution**: Ensure Docker containers are running:

```bash
docker compose up -d
docker compose exec api python manage.py migrate
```

### Issue: Late penalty not computed

**Solution**: Ensure `PayrollSettings` exists with `grace_minutes`:

```python
from payroll.models import PayrollSettings
PayrollSettings.objects.create(
    shift_start=time(8, 0),
    shift_end=time(18, 0),
    grace_minutes=15,
)
```

### Issue: Leave balance not created for new employee

**Solution**: Signal may not have fired. Manually run:

```bash
docker compose exec api python manage.py init_leave_balances
```

### Issue: Payroll shows zero hours despite approved attendance

**Solution**: Check that you're using `compute_from_daily_attendance()`, not `compute_from_time_entries()`.

---

## Support

For questions or issues:

1. Check business rules in this doc
2. Review model validation in `attendance/models.py`
3. Inspect API permissions in `attendance/api/views.py`
4. Test in Django Admin at `/admin/attendance/`

**Key Files:**

- Models: `attendance/models.py`
- API: `attendance/api/views.py`, `attendance/api/serializers.py`
- Admin: `attendance/admin.py`
- Payroll Integration: `payroll/models.py` (WeeklyPayroll.compute_from_daily_attendance)
- Signals: `attendance/signals.py`
