# Attendance System - Quick API Reference

## Authentication

All endpoints require JWT authentication. Include in headers:

```
Authorization: Bearer <your_jwt_token>
```

---

## Daily Attendance Endpoints

### Clock In Employee

```http
POST /api/attendance/daily-attendance/clock_in/
Content-Type: application/json

{
  "employee_id": 5,
  "date": "2026-01-27",
  "clock_in": "2026-01-27T08:00:00+08:00",
  "notes": ""
}
```

### Clock Out Employee

```http
POST /api/attendance/daily-attendance/clock_out/
Content-Type: application/json

{
  "attendance_id": 123,
  "clock_out": "2026-01-27T18:00:00+08:00",
  "notes": ""
}
```

### List Attendance (with filters)

```http
GET /api/attendance/daily-attendance/?employee_id=5&status=PENDING&date_from=2026-01-01&date_to=2026-01-31
```

### Get Pending Approvals

```http
GET /api/attendance/daily-attendance/pending_approvals/
```

### Approve Attendance

```http
POST /api/attendance/daily-attendance/approve/
Content-Type: application/json

{
  "attendance_ids": [123, 124, 125]
}
```

### Reject Attendance

```http
POST /api/attendance/daily-attendance/reject/
Content-Type: application/json

{
  "attendance_ids": [126],
  "reason": "Invalid clock times - outside shift hours"
}
```

---

## Leave Balance Endpoints

### Get My Leave Balance

```http
GET /api/attendance/leave-balance/my_balance/
```

**Response:**

```json
{
  "id": 15,
  "employee": 5,
  "employee_name": "Juan Dela Cruz",
  "year": 2026,
  "sick_leave_total": 5,
  "sick_leave_used": "2.00",
  "sick_leave_remaining": "3.00",
  "emergency_leave_total": 5,
  "emergency_leave_used": "1.00",
  "emergency_leave_remaining": "4.00",
  "created_at": "2026-01-01T00:00:00Z",
  "updated_at": "2026-01-27T10:30:00Z"
}
```

### List All Leave Balances (Admin/Manager)

```http
GET /api/attendance/leave-balance/?employee_id=5&year=2026
```

---

## Leave Request Endpoints

### Create Leave Request

```http
POST /api/attendance/leave-request/
Content-Type: application/json

{
  "leave_type": "SICK",
  "date": "2026-01-30",
  "is_half_day": false,
  "reason": "Medical check-up appointment"
}
```

**Note:** `employee` field auto-set to current user for non-admin/manager roles.

### Create Leave Request (Admin/Manager for any employee)

```http
POST /api/attendance/leave-request/
Content-Type: application/json

{
  "employee": 10,
  "leave_type": "EMERGENCY",
  "date": "2026-02-05",
  "is_half_day": true,
  "reason": "Family emergency"
}
```

### Get Pending Leave Approvals

```http
GET /api/attendance/leave-request/pending_approvals/
```

### Approve Leave Requests

```http
POST /api/attendance/leave-request/approve/
Content-Type: application/json

{
  "leave_request_ids": [45, 46]
}
```

**Response:**

```json
{
  "detail": "2 leave request(s) approved.",
  "approved_count": 2,
  "errors": []
}
```

**Error Response (insufficient balance):**

```json
{
  "detail": "1 leave request(s) approved.",
  "approved_count": 1,
  "errors": [
    {
      "leave_request_id": 47,
      "error": "Insufficient Sick Leave balance. Remaining: 0.0 days."
    }
  ]
}
```

### Reject Leave Requests

```http
POST /api/attendance/leave-request/reject/
Content-Type: application/json

{
  "leave_request_ids": [48],
  "reason": "Insufficient staffing during that period"
}
```

### Cancel Approved Leave

```http
POST /api/attendance/leave-request/48/cancel/
```

**Note:** Restores leave balance and marks associated DailyAttendance as deleted.

### List Leave Requests (with filters)

```http
GET /api/attendance/leave-request/?employee_id=5&status=APPROVED&leave_type=SICK
```

---

## Response Formats

### DailyAttendance Object

```json
{
  "id": 123,
  "employee": 5,
  "employee_name": "Juan Dela Cruz",
  "date": "2026-01-27",
  "clock_in": "2026-01-27T08:20:00+08:00",
  "clock_out": "2026-01-27T18:00:00+08:00",
  "attendance_type": "PARTIAL",
  "attendance_type_display": "Partial Hours",
  "total_hours": "9.67",
  "break_hours": "2.00",
  "paid_hours": "7.67",
  "is_late": true,
  "late_minutes": 5,
  "late_penalty_amount": "10.00",
  "status": "APPROVED",
  "status_display": "Approved",
  "approved_by": 1,
  "approved_by_name": "Admin User",
  "approved_at": "2026-01-27T19:00:00+08:00",
  "notes": "",
  "created_at": "2026-01-27T08:20:00+08:00",
  "updated_at": "2026-01-27T19:00:00+08:00"
}
```

### LeaveRequest Object

```json
{
  "id": 45,
  "employee": 5,
  "employee_name": "Juan Dela Cruz",
  "leave_type": "SICK",
  "leave_type_display": "Sick Leave",
  "date": "2026-01-30",
  "is_half_day": false,
  "days_count": "1.0",
  "reason": "Medical check-up",
  "status": "APPROVED",
  "status_display": "Approved",
  "approved_by": 1,
  "approved_by_name": "Admin User",
  "approved_at": "2026-01-28T10:00:00+08:00",
  "rejection_reason": "",
  "created_at": "2026-01-27T15:00:00+08:00",
  "updated_at": "2026-01-28T10:00:00+08:00"
}
```

---

## Common Scenarios

### Scenario 1: Normal Attendance

```bash
# Clock in at 8:00 AM
POST /api/attendance/daily-attendance/clock_in/
{"employee_id": 5, "date": "2026-01-27", "clock_in": "2026-01-27T08:00:00+08:00"}

# Clock out at 6:00 PM
POST /api/attendance/daily-attendance/clock_out/
{"attendance_id": 123, "clock_out": "2026-01-27T18:00:00+08:00"}

# Result: FULL_DAY, 8 paid hours, no penalty
```

### Scenario 2: Late Arrival

```bash
# Clock in at 8:20 AM (20 min late)
POST /api/attendance/daily-attendance/clock_in/
{"employee_id": 5, "date": "2026-01-27", "clock_in": "2026-01-27T08:20:00+08:00"}

# Result: 5 min beyond grace = ₱10 penalty
```

### Scenario 3: Very Late (Half-Day)

```bash
# Clock in at 8:35 AM (35 min late)
POST /api/attendance/daily-attendance/clock_in/
{"employee_id": 5, "date": "2026-01-27", "clock_in": "2026-01-27T08:35:00+08:00"}

# Result: Automatic HALF_DAY, 4 paid hours, no per-minute penalty
```

### Scenario 4: Overtime

```bash
# Clock in at 8:00 AM, out at 7:00 PM (11 hours)
# Result: 11 - 2 (break) = 9 paid hours
#   - Regular: 8 hrs @ hourly_rate
#   - Overtime: 1 hr @ hourly_rate × 1.5
```

### Scenario 5: Leave Request

```bash
# Step 1: Create request
POST /api/attendance/leave-request/
{"leave_type": "SICK", "date": "2026-01-30", "is_half_day": false, "reason": "Medical"}

# Step 2: Manager approves
POST /api/attendance/leave-request/approve/
{"leave_request_ids": [45]}

# Result:
#   - Sick leave balance: 5 → 4
#   - DailyAttendance created with type=LEAVE, paid_hours=0
```

---

## Error Responses

### 400 Bad Request

```json
{
  "detail": "Attendance already exists for this employee on 2026-01-27."
}
```

### 403 Forbidden

```json
{
  "detail": "Only admin and manager can create attendance records."
}
```

### 404 Not Found

```json
{
  "detail": "Not found."
}
```

### 422 Validation Error

```json
{
  "employee_id": ["This field is required."],
  "clock_in": ["This field is required."]
}
```

---

## Testing with cURL

### Clock In

```bash
curl -X POST http://localhost:8000/api/attendance/daily-attendance/clock_in/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "employee_id": 5,
    "date": "2026-01-27",
    "clock_in": "2026-01-27T08:00:00+08:00"
  }'
```

### Approve Attendance

```bash
curl -X POST http://localhost:8000/api/attendance/daily-attendance/approve/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"attendance_ids": [123, 124]}'
```

### Get My Leave Balance

```bash
curl -X GET http://localhost:8000/api/attendance/leave-balance/my_balance/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

---

## Management Commands

### Initialize Leave Balances

```bash
# Via Docker
docker compose exec api python manage.py init_leave_balances --year 2026

# Direct
python manage.py init_leave_balances --year 2026
```

---

## Permission Matrix

| Action                        | Admin | Manager | Clerk | Technician |
| ----------------------------- | ----- | ------- | ----- | ---------- |
| Clock in/out any employee     | ✓     | ✓       | ✗     | ✗          |
| View all attendance           | ✓     | ✓       | ✗     | ✗          |
| View own attendance           | ✓     | ✓       | ✓     | ✓          |
| Approve attendance            | ✓     | ✓       | ✗     | ✗          |
| Create leave request (self)   | ✓     | ✓       | ✓     | ✓          |
| Create leave request (others) | ✓     | ✓       | ✗     | ✗          |
| Approve leave                 | ✓     | ✓       | ✗     | ✗          |
| View all leave balances       | ✓     | ✓       | ✗     | ✗          |
| View own leave balance        | ✓     | ✓       | ✓     | ✓          |

---

## Database Commands (via Docker)

```bash
# Run migrations
docker compose exec api python manage.py migrate

# Create superuser
docker compose exec api python manage.py createsuperuser

# Access Django shell
docker compose exec api python manage.py shell

# Initialize leave balances
docker compose exec api python manage.py init_leave_balances
```
