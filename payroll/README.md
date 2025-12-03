
# Payroll app (Weekly salary with overtime, deductions)



This app adds simple time tracking and weekly payroll computation on top of your existing `users.CustomUser` model. It exposes a small REST API for:



- Recording time entries (clock in/out) with optional unpaid breaks

- Bulk clock in/out for multiple employees in one call
- Additional earnings (manual overtime pay, installation percentage, custom payouts)
- Generating a weekly payroll record per employee

- Computing regular and overtime pay (+ allowances)

- Applying flat and percentage deductions

- Recomputing payroll totals on demand

- Year-end 13th month pay outline


Time zone defaults to Asia/Manila as configured in the project (`TIME_ZONE = "Asia/Manila"`).



---



## Models overview



1) TimeEntry

- employee: FK to `users.CustomUser`

- clock_in: DateTime

- clock_out: DateTime

- unpaid_break_minutes: int (>= 0)

- approved: bool (include in payroll if True, by default True)

- source: one of ["manual", "schedule", "import"]

- notes: text

- is_deleted: soft delete flag (Delete API will set this True)

- created_at / updated_at



Effective hours are calculated as:

effective_hours = max((clock_out - clock_in) - unpaid_break_minutes, 0) in hours



Internally, effective hours are computed with 4 decimal precision; the API representation returns a string.



2) AdditionalEarning
- employee: FK to `users.CustomUser`

- earning_date: Date
- category: "overtime" | "installation_pct" | "custom"
- amount: Decimal(12,2)
- description/reference: optional
- approved: bool (include in payroll if True, by default True)
- is_deleted: soft delete flag
- created_at / updated_at

These are added on top of computed hourly gross in the weekly payroll.

3) WeeklyPayroll
- employee: FK to `users.CustomUser`
- week_start: Date (inclusive start of week, recommended Monday)

- hourly_rate: Decimal(10,2)

- overtime_threshold: Decimal(5,2) (default 40.00 hours/week)

- overtime_multiplier: Decimal(4,2) (default 1.50)

- regular_hours: Decimal(6,2)

- overtime_hours: Decimal(6,2)

- allowances: Decimal(10,2)

- additional_earnings_total: Decimal(12,2)
- gross_pay: Decimal(12,2)

- deductions: JSON mapping of { name: amount }

- total_deductions: Decimal(12,2)

- net_pay: Decimal(12,2)

- status: one of ["draft", "approved", "paid"] (default "draft")

- notes: text

- is_deleted: soft delete flag

- created_at / updated_at



Uniqueness: (employee, week_start)



Week range used in computation is [week_start, week_start + 7 days), i.e., week_end is exclusive.



---



## Computation details



Given totals for the week:

- regular_hours = min(total_hours, overtime_threshold)

- overtime_hours = max(total_hours - overtime_threshold, 0)



Gross pay:

gross = (regular_hours * hourly_rate)

      + (overtime_hours * hourly_rate * overtime_multiplier)

      + allowances

      + additional_earnings_total (sum of approved AdditionalEarning in the week)


Deductions:

- deductions field stores a map of flat amounts: { "Tax": 100.00, "Benefits": 35.00 }

- recompute endpoint can also accept percentage rates (e.g., { "Tax": 0.12 })

- total_deductions = sum(deductions.values())

- net_pay = gross - total_deductions



Rounding:

- Hours are stored to 2 decimals in WeeklyPayroll (effective hours per entry computed at 4 decimals before summing).

- Money is rounded to 2 decimals (ROUND_HALF_UP).



---



## Installation and migrations



1) App registration (already done in this repo)

- INSTALLED_APPS includes "payroll"



2) Migrations

- Generate/apply:

  - python manage.py makemigrations payroll

  - python manage.py migrate



3) Admin

- TimeEntry, WeeklyPayroll, and AdditionalEarning are registered with useful actions:

  - Recompute payroll totals

  - Mark approved / paid

  - Soft delete / restore



---



## API endpoints



Base prefix:

- /api/payroll/



Auth:

- All endpoints require authentication (IsAuthenticated).

- Role-based restrictions can be introduced later if needed.



Pagination, filtering, search, ordering:

- Standard DRF pagination enabled

- search, ordering supported

- start_date, end_date supported for date filtering

  - For TimeEntry we filter by clock_in datetime

  - For WeeklyPayroll we filter by week_start date

  - For AdditionalEarning we filter by earning_date date
- Filter fields listed in each resource section below



### Time entries



List/Create:

- GET /api/payroll/time-entries/

- POST /api/payroll/time-entries/



Retrieve/Update/Delete (soft):

- GET /api/payroll/time-entries/{id}/

- PATCH /api/payroll/time-entries/{id}/

- DELETE /api/payroll/time-entries/{id}/



Filters:

- employee (id)

- approved (true/false)

- source in ["manual", "schedule", "import"]

- employee__assigned_stall (id)

- start_date=YYYY-MM-DD

- end_date=YYYY-MM-DD



Search:

- notes, employee username/first_name/last_name



Ordering:

- Any field, e.g. ?ordering=-clock_in



Example: create a time entry

Request:

{

  "employee": 12,

  "clock_in": "2025-11-24T09:00:00+08:00",

  "clock_out": "2025-11-24T17:30:00+08:00",

  "unpaid_break_minutes": 30,

  "source": "manual",

  "approved": true,

  "notes": "Regular shift"

}



Response (201):

{

  "id": 101,

  "employee": 12,

  "employee_detail": { "id": 12, "username": "tech1", "first_name": "A", "last_name": "B", "full_name": "A B" },

  "clock_in": "2025-11-24T09:00:00+08:00",

  "clock_out": "2025-11-24T17:30:00+08:00",

  "unpaid_break_minutes": 30,

  "source": "manual",

  "approved": true,

  "notes": "Regular shift",

  "is_deleted": false,

  "created_at": "...",

  "updated_at": "...",

  "work_date": "2025-11-24",

  "effective_hours": "8.0"

}



Validation notes:

- clock_out must be after clock_in

- unpaid_break_minutes cannot be negative and should not exceed worked duration



Soft delete:

- DELETE sets is_deleted=true; record is hidden from list endpoints and payroll computations.



### Bulk time entries (multiple employees same time window)

- POST /api/payroll/time-entries/bulk/

Body:
- employee_ids: number[] (required, non-empty)
- clock_in: ISO datetime (required)
- clock_out: ISO datetime (required, must be after clock_in)
- unpaid_break_minutes: number (default 0, cannot exceed duration)
- source: "manual" | "schedule" | "import" (default "manual")
- approved: boolean (default true)
- notes: string (optional)

Example:
{
  "employee_ids": [11, 12, 13],
  "clock_in": "2025-11-24T09:00:00+08:00",
  "clock_out": "2025-11-24T17:30:00+08:00",
  "unpaid_break_minutes": 30,
  "source": "manual",
  "approved": true,
  "notes": "Team A shift"
}

Response (201): array of created TimeEntry records.

### Additional earnings (overtime top-ups, installation percentage, custom payouts)



List/Create:

- GET /api/payroll/additional-earnings/
- POST /api/payroll/additional-earnings/

Retrieve/Update/Delete (soft):

- GET /api/payroll/additional-earnings/{id}/
- PATCH /api/payroll/additional-earnings/{id}/
- DELETE /api/payroll/additional-earnings/{id}/

Filters:
- employee (id)
- category ("overtime" | "installation_pct" | "custom")
- approved (true/false)
- employee__assigned_stall (id)
- start_date=YYYY-MM-DD (by earning_date)
- end_date=YYYY-MM-DD (by earning_date)

Example: create an additional earning
{
  "employee": 12,
  "earning_date": "2025-11-28",
  "category": "installation_pct",
  "amount": "500.00",
  "reference": "Install-INV-10023",
  "description": "10% install commission",
  "approved": true
}

Notes:
- Approved additional earnings within the payroll week are summed into `additional_earnings_total` and included in `gross_pay`.

### Weekly payrolls

List/Create:
- GET /api/payroll/weekly-payrolls/
- POST /api/payroll/weekly-payrolls/

Retrieve/Update/Delete (soft):
- GET /api/payroll/weekly-payrolls/{id}/
- PATCH /api/payroll/weekly-payrolls/{id}/
- DELETE /api/payroll/weekly-payrolls/{id}/

Recompute:
- POST /api/payroll/weekly-payrolls/{id}/recompute/



Filters:

- employee (id)

- status (draft/approved/paid)

- week_start (exact date)

- employee__assigned_stall (id)

- start_date=YYYY-MM-DD (filters by week_start)

- end_date=YYYY-MM-DD (filters by week_start)



Search:

- notes, employee username/first_name/last_name



Ordering:

- Any field, e.g. ?ordering=-week_start



Create a weekly payroll

Request:

{

  "employee": 12,

  "week_start": "2025-11-24",

  "hourly_rate": "220.00",

  "overtime_threshold": "40.00",

  "overtime_multiplier": "1.50",

  "allowances": "0.00",

  "deductions": { "Benefits": 200.00 },

  "status": "draft",

  "notes": "Week 48"

}



Behavior:

- On create, the server pulls all approved TimeEntry rows with clock_in in [week_start, week_start + 7 days) and computes:

  - regular_hours, overtime_hours

  - additional_earnings_total
  - gross_pay, total_deductions, net_pay

- It persists the computed fields immediately.



Response (201):

{

  "id": 77,

  "employee": 12,

  "employee_detail": { ... },

  "week_start": "2025-11-24",

  "week_end": "2025-12-01",

  "hourly_rate": "220.00",

  "overtime_threshold": "40.00",

  "overtime_multiplier": "1.50",

  "regular_hours": "40.00",

  "overtime_hours": "6.00",

  "total_hours": 46.0,

  "allowances": "0.00",

  "additional_earnings_total": "500.00",
  "gross_pay": "11280.00",
  "deductions": { "Benefits": 200.0 },

  "total_deductions": "200.00",

  "net_pay": "11080.00",
  "status": "draft",

  "notes": "Week 48",

  "is_deleted": false,

  "created_at": "...",

  "updated_at": "..."

}



Update a weekly payroll

- You can PATCH fields like hourly_rate, overtime_threshold, overtime_multiplier, allowances, deductions, status, notes.

- The server recomputes totals after update to keep figures in sync.



Example PATCH:

{

  "allowances": "250.00",

  "deductions": { "Benefits": 200.00, "Loan": 500.00 },

  "status": "approved"

}



Recompute with additional parameters

- POST /api/payroll/weekly-payrolls/{id}/recompute/

- Body (all optional):

  - include_unapproved: boolean (include unapproved time entries as well)

  - allowances: number (override allowances just for recompute)

  - extra_flat_deductions: { name: number }

  - percent_deductions: { name: number }  // rate applied to gross, e.g., { "Tax": 0.12 }



Example recompute:

{

  "include_unapproved": false,

  "allowances": 100.00,

  "extra_flat_deductions": { "Garnishment": 300.00 },

  "percent_deductions": { "Tax": 0.10, "Pension": 0.03 }

}



Response (200):

- Returns the updated payroll with new totals applied.



Soft delete:

- DELETE sets is_deleted=true; record is hidden from list endpoints and future recomputations.



---



## Typical usage flow



1) Use bulk time entries to clock in/out multiple employees who share the same shift time.
2) Capture individual time entries for exceptions or corrections.
3) Add Additional Earnings (e.g., manual overtime payout, installation percentage, custom bonuses) per employee as needed.
4) At period end, create a WeeklyPayroll for each employee with:

   - employee

   - week_start

   - hourly_rate (or derive from your own HR source)

   - optional: overtime_threshold, overtime_multiplier, allowances, deductions

5) Review totals; optionally PATCH to adjust allowances/deductions or status.

6) Mark as "approved", then "paid" when disbursed.

7) If adjustments are needed, use the recompute endpoint to include percentage taxes/benefits or additional flat deductions.

---

## 13th month pay (outline)

Typical PH rule of thumb (for reference only; confirm with your HR/compliance):
- 13th month pay = one-twelfth (1/12) of total basic salary earned within the calendar year (excluding allowances, overtime, and other benefits).
- Period: Jan 1 to Dec 31.
- Basic salary is distinct from overtime, allowances, and other additional earnings.

Implementation approach in this system:
- Use WeeklyPayroll records to aggregate “basic earnings” throughout the year.
  - If you treat basic earnings as: (regular_hours * hourly_rate) only (exclude overtime, allowances, additional_earnings).
- At year-end, compute:
  - sum_basic = Σ over the year of weekly (regular_hours * hourly_rate)
  - thirteenth_month = sum_basic / 12
- Optional:
  - Add a new API endpoint to return computed 13th month per employee for a given year.
  - Add a one-off “AdditionalEarning” entry if you disburse it via payroll, or a separate payout record type if you prefer to keep it distinct.



Note: Regulations can vary and may have exceptions (e.g., pro-rating for partial-year service). Confirm with your HR policy before automating.

---



## Validation and error handling



- TimeEntry

  - clock_out must be strictly after clock_in

  - unpaid_break_minutes must be non-negative and not exceed the shift duration

- AdditionalEarning
  - amount must be non-negative
  - category must be one of the supported values
- WeeklyPayroll

  - hourly_rate, overtime_threshold, overtime_multiplier must be non-negative

  - (employee, week_start) must be unique

- Deductions field in WeeklyPayroll:

  - Must be a mapping of string -> number

  - Negative amounts are rejected

  - Internally normalized to 2-decimal amounts



---



## Notes and best practices



- Week boundaries: By default, we recommend week_start on Monday to align with common payroll periods. Computation uses [week_start, week_start + 7 days).

- Time zones: Date/time handling respects Django’s `USE_TZ` and current timezone settings.

- Decimal precision: Avoid floating-point math in clients; send strings for money fields if possible to preserve precision.

- Approval workflow: Use the `approved` flag on TimeEntry and AdditionalEarning to gate what gets included in payroll.
- Role controls: Endpoints currently require authentication. You can add role-based permissions later if managers should see only their stall, etc.



---



## Frontend integration hints



- The frontend uses a base API prefix `/api`. These endpoints should be called with paths like:

  - GET /api/payroll/time-entries/?start_date=2025-11-24&end_date=2025-11-30&employee=12

  - POST /api/payroll/time-entries/bulk/
  - GET/POST /api/payroll/additional-earnings/
  - POST /api/payroll/weekly-payrolls/
  - POST /api/payroll/weekly-payrolls/{id}/recompute/

- Standard pagination response: `count`, `next`, `previous`, `results`.

- Use Search, Ordering, and Filter params to implement tables and filters smoothly.



---



## Future extensions (optional)



- Daily overtime rules (e.g., >8 hours/day) in addition to weekly

- Night differential, holiday premiums

- Pay period locking

- Export to CSV/PDF pay stubs

- Automated 13th month pay endpoint + archiving
- Payroll journal entries integration with accounting



---
