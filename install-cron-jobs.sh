
#!/bin/bash

###############################################################################
# RVDC Cron Jobs Installation Script (Updated for Weekly Payroll + Disk Mgmt)
#
# This script automatically sets up cron jobs for your Dockerized Django app
# on a DigitalOcean droplet.
#
# Cron jobs provided:
# - Daily: Auto-close attendance (9:00 PM Philippines time)
# - Daily: Mark absences (11:30 PM Philippines time)
# - Daily: Delete old notifications (2:00 AM Philippines time)
# - Daily: Disk usage check + alert (6:00 AM Philippines time)
# - Daily: Log truncation for large logs (5:00 AM Philippines time)
# - Weekly: Fix attendance & refresh payroll (Friday 11 PM Philippines time)
# - Weekly: Docker system prune (Sunday 3:00 AM Philippines time)
# - Weekly: Cleanup unused profile images (Sunday 3:30 AM Philippines time)
# - Monthly: Clean old logs (1st of month, 3:00 AM Philippines time)
# - Yearly: Update holiday years to new year (Jan 1, 2:00 AM Philippines time)
# - Yearly: Replenish leave balances (Jan 1, 3:00 AM Philippines time)
# - Yearly: Archive old payrolls (Jan 2, 2:00 AM Philippines time)
#
# Usage:
#   1. Upload this script to your droplet
#   2. Make it executable: chmod +x install-cron-jobs.sh
#   3. Run as root: sudo ./install-cron-jobs.sh
#
###############################################################################

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="/opt/cron-scripts"
LOG_DIR="/var/log"

echo -e "${GREEN}╔════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   RVDC Cron Jobs Installation Script          ║${NC}"
echo -e "${GREEN}║   (Weekly Payroll + Disk Management Edition)  ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════╝${NC}"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}❌ Please run as root (sudo ./install-cron-jobs.sh)${NC}"
    exit 1
fi

# Step 1: Find Docker container name
echo -e "${YELLOW}Step 1: Finding Docker container...${NC}"
echo ""
echo "Available containers:"
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}"
echo ""

read -p "Enter your backend container name (e.g., rvdc-backend): " CONTAINER_NAME

if [ -z "$CONTAINER_NAME" ]; then
    echo -e "${RED}❌ Container name cannot be empty${NC}"
    exit 1
fi

# Test container
echo -e "${YELLOW}Testing container access...${NC}"
if docker exec "$CONTAINER_NAME" python manage.py help > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Container access OK${NC}"
else
    echo -e "${RED}❌ Cannot access container or Django not found${NC}"
    exit 1
fi

# Step 2: Create directories
echo ""
echo -e "${YELLOW}Step 2: Creating directories...${NC}"
mkdir -p "$SCRIPT_DIR"
echo -e "${GREEN}✅ Created $SCRIPT_DIR${NC}"

# Step 3: Create cron scripts
echo ""
echo -e "${YELLOW}Step 3: Creating cron scripts...${NC}"

# Script 1: Auto-close attendance (Daily 9:00 PM)
cat > "$SCRIPT_DIR/auto-close-attendance.sh" << 'EOF'
#!/bin/bash
LOG_FILE="/var/log/cron-auto-close-attendance.log"
CONTAINER_NAME="CONTAINER_NAME_PLACEHOLDER"
export TZ=Asia/Manila

echo "=== Auto-Close Attendance - $(date '+%Y-%m-%d %H:%M:%S %Z') ===" >> "$LOG_FILE"
docker exec "$CONTAINER_NAME" python manage.py auto_close_attendance >> "$LOG_FILE" 2>&1

if [ $? -eq 0 ]; then
    echo "✅ Success - $(date '+%Y-%m-%d %H:%M:%S %Z')" >> "$LOG_FILE"
else
    echo "❌ Failed - $(date '+%Y-%m-%d %H:%M:%S %Z')" >> "$LOG_FILE"
fi
echo "" >> "$LOG_FILE"
EOF

# Script 1a: Clock-in reminder (Daily 7:00 AM)
cat > "$SCRIPT_DIR/clock-in-reminder.sh" << 'EOF'
#!/bin/bash
LOG_FILE="/var/log/cron-clock-in-reminder.log"
CONTAINER_NAME="CONTAINER_NAME_PLACEHOLDER"
export TZ=Asia/Manila

echo "=== Clock-In Reminder - $(date '+%Y-%m-%d %H:%M:%S %Z') ===" >> "$LOG_FILE"
docker exec "$CONTAINER_NAME" python manage.py send_attendance_reminders --mode clock_in >> "$LOG_FILE" 2>&1

if [ $? -eq 0 ]; then
    echo "Success - $(date '+%Y-%m-%d %H:%M:%S %Z')" >> "$LOG_FILE"
else
    echo "Failed - $(date '+%Y-%m-%d %H:%M:%S %Z')" >> "$LOG_FILE"
fi
echo "" >> "$LOG_FILE"
EOF

# Script 1b: Clock-out reminder (Daily 6:00 PM)
cat > "$SCRIPT_DIR/clock-out-reminder.sh" << 'EOF'
#!/bin/bash
LOG_FILE="/var/log/cron-clock-out-reminder.log"
CONTAINER_NAME="CONTAINER_NAME_PLACEHOLDER"
export TZ=Asia/Manila

echo "=== Clock-Out Reminder - $(date '+%Y-%m-%d %H:%M:%S %Z') ===" >> "$LOG_FILE"
docker exec "$CONTAINER_NAME" python manage.py send_attendance_reminders --mode clock_out >> "$LOG_FILE" 2>&1

if [ $? -eq 0 ]; then
    echo "Success - $(date '+%Y-%m-%d %H:%M:%S %Z')" >> "$LOG_FILE"
else
    echo "Failed - $(date '+%Y-%m-%d %H:%M:%S %Z')" >> "$LOG_FILE"
fi
echo "" >> "$LOG_FILE"
EOF

# Script 1b: Delete old notifications (Daily 2:00 AM)
cat > "$SCRIPT_DIR/delete-old-notifications.sh" << 'EOF'
#!/bin/bash
LOG_FILE="/var/log/cron-delete-old-notifications.log"
CONTAINER_NAME="CONTAINER_NAME_PLACEHOLDER"
export TZ=Asia/Manila

echo "=== Delete Old Notifications - $(date '+%Y-%m-%d %H:%M:%S %Z') ===" >> "$LOG_FILE"
docker exec "$CONTAINER_NAME" python manage.py delete_old_notifications --all --days 7 >> "$LOG_FILE" 2>&1

if [ $? -eq 0 ]; then
    echo "✅ Success - $(date '+%Y-%m-%d %H:%M:%S %Z')" >> "$LOG_FILE"
else
    echo "❌ Failed - $(date '+%Y-%m-%d %H:%M:%S %Z')" >> "$LOG_FILE"
fi
echo "" >> "$LOG_FILE"
EOF

# Script 2: Mark absences (Daily 11:30 PM)
cat > "$SCRIPT_DIR/mark-absences.sh" << 'EOF'
#!/bin/bash
LOG_FILE="/var/log/cron-mark-absences.log"
CONTAINER_NAME="CONTAINER_NAME_PLACEHOLDER"
export TZ=Asia/Manila

echo "=== Mark Daily Absences - $(date '+%Y-%m-%d %H:%M:%S %Z') ===" >> "$LOG_FILE"
docker exec "$CONTAINER_NAME" python manage.py mark_daily_absences >> "$LOG_FILE" 2>&1

if [ $? -eq 0 ]; then
    echo "✅ Success - $(date '+%Y-%m-%d %H:%M:%S %Z')" >> "$LOG_FILE"
else
    echo "❌ Failed - $(date '+%Y-%m-%d %H:%M:%S %Z')" >> "$LOG_FILE"
fi
echo "" >> "$LOG_FILE"
EOF

# Script 3: Weekly attendance fix + payroll refresh (Friday 11:00 PM)
cat > "$SCRIPT_DIR/weekly-attendance-payroll-fix.sh" << 'EOF'
#!/bin/bash
LOG_FILE="/var/log/cron-weekly-attendance-payroll-fix.log"
CONTAINER_NAME="CONTAINER_NAME_PLACEHOLDER"
export TZ=Asia/Manila

# Calculate last week (Saturday to Friday)
LAST_SATURDAY=$(date -d "last saturday -7 days" +%Y-%m-%d)
LAST_FRIDAY=$(date -d "yesterday" +%Y-%m-%d)

echo "=== Weekly Attendance & Payroll Fix - $(date '+%Y-%m-%d %H:%M:%S %Z') ===" >> "$LOG_FILE"
echo "Processing period: $LAST_SATURDAY to $LAST_FRIDAY" >> "$LOG_FILE"

# Step 1: Verify attendance issues
echo "--- Step 1: Verifying attendance ---" >> "$LOG_FILE"
docker exec "$CONTAINER_NAME" python manage.py fix_attendance_time_entries \
    --verify-only \
    --start-date "$LAST_SATURDAY" \
    --end-date "$LAST_FRIDAY" >> "$LOG_FILE" 2>&1

# Step 2: Fix attendance
echo "--- Step 2: Fixing attendance ---" >> "$LOG_FILE"
docker exec "$CONTAINER_NAME" python manage.py fix_attendance_time_entries \
    --force \
    --start-date "$LAST_SATURDAY" \
    --end-date "$LAST_FRIDAY" >> "$LOG_FILE" 2>&1

# Step 3: Refresh payroll from attendance
echo "--- Step 3: Refreshing payroll ---" >> "$LOG_FILE"
docker exec "$CONTAINER_NAME" python manage.py refresh_payroll_from_attendance \
    --force \
    --start-date "$LAST_SATURDAY" \
    --end-date "$LAST_FRIDAY" >> "$LOG_FILE" 2>&1

if [ $? -eq 0 ]; then
    echo "✅ Weekly fix complete - $(date '+%Y-%m-%d %H:%M:%S %Z')" >> "$LOG_FILE"
else
    echo "❌ Weekly fix failed - $(date '+%Y-%m-%d %H:%M:%S %Z')" >> "$LOG_FILE"
fi
echo "" >> "$LOG_FILE"
EOF

# Script 5: Update holiday years (January 1st)
cat > "$SCRIPT_DIR/yearly-update-holidays.sh" << 'EOF'
#!/bin/bash
LOG_FILE="/var/log/cron-yearly-update-holidays.log"
CONTAINER_NAME="CONTAINER_NAME_PLACEHOLDER"
export TZ=Asia/Manila

CURRENT_YEAR=$(date +%Y)
NEXT_YEAR=$((CURRENT_YEAR + 1))

echo "=== Update Holiday Years - $(date '+%Y-%m-%d %H:%M:%S %Z') ===" >> "$LOG_FILE"
echo "Updating holidays to year: $NEXT_YEAR" >> "$LOG_FILE"

docker exec "$CONTAINER_NAME" python manage.py update_holiday_years \
    --year "$NEXT_YEAR" --force >> "$LOG_FILE" 2>&1

if [ $? -eq 0 ]; then
    echo "✅ Holiday years updated - $(date '+%Y-%m-%d %H:%M:%S %Z')" >> "$LOG_FILE"
else
    echo "❌ Holiday update failed - $(date '+%Y-%m-%d %H:%M:%S %Z')" >> "$LOG_FILE"
fi
echo "" >> "$LOG_FILE"
EOF

# Script 6: Replenish leave balances (January 1st)
cat > "$SCRIPT_DIR/yearly-replenish-leaves.sh" << 'EOF'
#!/bin/bash
LOG_FILE="/var/log/cron-yearly-replenish-leaves.log"
CONTAINER_NAME="CONTAINER_NAME_PLACEHOLDER"
export TZ=Asia/Manila

echo "=== Replenish Leave Balances - $(date '+%Y-%m-%d %H:%M:%S %Z') ===" >> "$LOG_FILE"
echo "Resetting leave balances for all employees" >> "$LOG_FILE"

docker exec "$CONTAINER_NAME" python manage.py replenish_leave_balances \
    --reset \
    --sick-leave 7 \
    --emergency-leave 3 --force >> "$LOG_FILE" 2>&1

if [ $? -eq 0 ]; then
    echo "✅ Leave balances replenished - $(date '+%Y-%m-%d %H:%M:%S %Z')" >> "$LOG_FILE"
else
    echo "❌ Leave replenishment failed - $(date '+%Y-%m-%d %H:%M:%S %Z')" >> "$LOG_FILE"
fi
echo "" >> "$LOG_FILE"
EOF

# Script 7: Archive old payrolls (January 2nd)
cat > "$SCRIPT_DIR/yearly-archive-payrolls.sh" << 'EOF'
#!/bin/bash
LOG_FILE="/var/log/cron-yearly-archive-payrolls.log"
CONTAINER_NAME="CONTAINER_NAME_PLACEHOLDER"
export TZ=Asia/Manila

CURRENT_YEAR=$(date +%Y)
LAST_YEAR=$((CURRENT_YEAR - 1))

echo "=== Archive Old Payrolls - $(date '+%Y-%m-%d %H:%M:%S %Z') ===" >> "$LOG_FILE"
echo "Archiving payrolls from year: $LAST_YEAR and earlier" >> "$LOG_FILE"

# Export before deleting
docker exec "$CONTAINER_NAME" python manage.py archive_old_payrolls \
    --year "$LAST_YEAR" \
    --export \
    --delete --force >> "$LOG_FILE" 2>&1

if [ $? -eq 0 ]; then
    echo "✅ Payrolls archived - $(date '+%Y-%m-%d %H:%M:%S %Z')" >> "$LOG_FILE"
else
    echo "❌ Payroll archival failed - $(date '+%Y-%m-%d %H:%M:%S %Z')" >> "$LOG_FILE"
fi
echo "" >> "$LOG_FILE"
EOF

# Script 8: Docker system prune (Weekly Sunday 3:00 AM)
cat > "$SCRIPT_DIR/docker-system-prune.sh" << 'EOF'
#!/bin/bash
LOG_FILE="/var/log/cron-docker-prune.log"
export TZ=Asia/Manila

echo "=== Docker System Prune - $(date '+%Y-%m-%d %H:%M:%S %Z') ===" >> "$LOG_FILE"

# Remove stopped containers, unused networks, dangling images, and build cache
echo "--- Pruning containers, networks, and dangling images ---" >> "$LOG_FILE"
docker system prune -f >> "$LOG_FILE" 2>&1

# Remove unused images older than 7 days
echo "--- Removing unused images older than 7 days ---" >> "$LOG_FILE"
docker image prune -a --filter "until=168h" -f >> "$LOG_FILE" 2>&1

# Show remaining disk usage
echo "--- Docker disk usage after prune ---" >> "$LOG_FILE"
docker system df >> "$LOG_FILE" 2>&1

echo "✅ Docker prune complete - $(date '+%Y-%m-%d %H:%M:%S %Z')" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"
EOF

# Script 9: Cleanup unused profile images (Weekly Sunday 3:30 AM)
cat > "$SCRIPT_DIR/cleanup-unused-images.sh" << 'EOF'
#!/bin/bash
LOG_FILE="/var/log/cron-cleanup-images.log"
CONTAINER_NAME="CONTAINER_NAME_PLACEHOLDER"
export TZ=Asia/Manila

echo "=== Cleanup Unused Images - $(date '+%Y-%m-%d %H:%M:%S %Z') ===" >> "$LOG_FILE"
docker exec "$CONTAINER_NAME" python manage.py cleanup_unused_images >> "$LOG_FILE" 2>&1

if [ $? -eq 0 ]; then
    echo "✅ Success - $(date '+%Y-%m-%d %H:%M:%S %Z')" >> "$LOG_FILE"
else
    echo "❌ Failed - $(date '+%Y-%m-%d %H:%M:%S %Z')" >> "$LOG_FILE"
fi
echo "" >> "$LOG_FILE"
EOF

# Script 10: Disk usage check + alert (Daily 6:00 AM)
cat > "$SCRIPT_DIR/disk-usage-check.sh" << 'EOF'
#!/bin/bash
LOG_FILE="/var/log/cron-disk-usage.log"
export TZ=Asia/Manila

DISK_THRESHOLD=80
DISK_CRITICAL=90
DISK_USAGE=$(df / | awk 'NR==2 {print $5}' | sed 's/%//')
DISK_AVAIL=$(df -h / | awk 'NR==2 {print $4}')

echo "=== Disk Usage Check - $(date '+%Y-%m-%d %H:%M:%S %Z') ===" >> "$LOG_FILE"
echo "Disk usage: ${DISK_USAGE}% (Available: ${DISK_AVAIL})" >> "$LOG_FILE"

if [ "$DISK_USAGE" -ge "$DISK_CRITICAL" ]; then
    echo "🚨 CRITICAL: Disk usage ${DISK_USAGE}% exceeds ${DISK_CRITICAL}%!" >> "$LOG_FILE"
    echo "Running emergency cleanup..." >> "$LOG_FILE"

    # Emergency: clean apt cache
    apt-get clean 2>/dev/null

    # Emergency: clean journal logs
    journalctl --vacuum-size=50M 2>/dev/null

    # Emergency: truncate large cron logs (keep last 1000 lines)
    for logfile in /var/log/cron-*.log; do
        if [ -f "$logfile" ] && [ $(wc -l < "$logfile") -gt 1000 ]; then
            tail -1000 "$logfile" > "${logfile}.tmp" && mv "${logfile}.tmp" "$logfile"
            echo "  Truncated: $logfile" >> "$LOG_FILE"
        fi
    done

    # Emergency: Docker prune
    docker system prune -f >> "$LOG_FILE" 2>&1

    NEW_USAGE=$(df / | awk 'NR==2 {print $5}' | sed 's/%//')
    echo "After cleanup: ${NEW_USAGE}%" >> "$LOG_FILE"

elif [ "$DISK_USAGE" -ge "$DISK_THRESHOLD" ]; then
    echo "⚠️  WARNING: Disk usage ${DISK_USAGE}% exceeds ${DISK_THRESHOLD}% threshold" >> "$LOG_FILE"
    echo "Consider running: docker system prune -a" >> "$LOG_FILE"
else
    echo "✅ Disk usage OK" >> "$LOG_FILE"
fi
echo "" >> "$LOG_FILE"
EOF

# Script 11: Log truncation (Daily 5:00 AM)
cat > "$SCRIPT_DIR/truncate-large-logs.sh" << 'EOF'
#!/bin/bash
LOG_FILE="/var/log/cron-log-maintenance.log"
export TZ=Asia/Manila
MAX_LOG_SIZE_KB=10240  # 10MB

echo "=== Log Truncation - $(date '+%Y-%m-%d %H:%M:%S %Z') ===" >> "$LOG_FILE"

for logfile in /var/log/cron-*.log; do
    if [ -f "$logfile" ] && [ "$logfile" != "$LOG_FILE" ]; then
        SIZE_KB=$(du -k "$logfile" | cut -f1)
        if [ "$SIZE_KB" -gt "$MAX_LOG_SIZE_KB" ]; then
            LINES=$(wc -l < "$logfile")
            tail -500 "$logfile" > "${logfile}.tmp" && mv "${logfile}.tmp" "$logfile"
            echo "  Truncated $logfile (was ${SIZE_KB}KB, ${LINES} lines)" >> "$LOG_FILE"
        fi
    fi
done

# Also truncate system logs if too large
for syslog in /var/log/syslog /var/log/kern.log /var/log/auth.log; do
    if [ -f "$syslog" ]; then
        SIZE_KB=$(du -k "$syslog" | cut -f1)
        if [ "$SIZE_KB" -gt 51200 ]; then  # 50MB
            tail -2000 "$syslog" > "${syslog}.tmp" && mv "${syslog}.tmp" "$syslog"
            echo "  Truncated $syslog (was ${SIZE_KB}KB)" >> "$LOG_FILE"
        fi
    fi
done

# Clean old journal logs
journalctl --vacuum-size=100M >> "$LOG_FILE" 2>&1

echo "✅ Log maintenance complete" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"
EOF

# ═══════════════════════════════════════════════════════════
# 11. CLEANUP ARCHIVED QUOTATIONS (Daily)
# ═══════════════════════════════════════════════════════════
echo "Creating cleanup-archived-quotations.sh..."

cat > "$SCRIPT_DIR/cleanup-archived-quotations.sh" << 'EOF'
#!/bin/bash
LOG_FILE="/var/log/cron-cleanup-archived-quotations.log"
CONTAINER_NAME="CONTAINER_NAME_PLACEHOLDER"
export TZ=Asia/Manila

echo "=== Cleanup Archived Quotations - $(date '+%Y-%m-%d %H:%M:%S %Z') ===" >> "$LOG_FILE"

docker exec "$CONTAINER_NAME" python manage.py cleanup_archived_quotations --days 14 >> "$LOG_FILE" 2>&1

if [ $? -eq 0 ]; then
    echo "✅ Cleanup complete - $(date '+%Y-%m-%d %H:%M:%S %Z')" >> "$LOG_FILE"
else
    echo "❌ Cleanup failed - $(date '+%Y-%m-%d %H:%M:%S %Z')" >> "$LOG_FILE"
fi
echo "" >> "$LOG_FILE"
EOF

# Replace placeholder with actual container name
sed -i "s/CONTAINER_NAME_PLACEHOLDER/$CONTAINER_NAME/g" "$SCRIPT_DIR"/*.sh

# Make scripts executable
chmod +x "$SCRIPT_DIR"/*.sh

echo -e "${GREEN}✅ Created 12 cron scripts${NC}"

# Step 4: Test scripts
echo ""
echo -e "${YELLOW}Step 4: Testing scripts (dry run)...${NC}"

echo "Testing auto-close-attendance.sh..."
if bash "$SCRIPT_DIR/auto-close-attendance.sh"; then
    echo -e "${GREEN}✅ auto-close-attendance.sh works${NC}"
else
    echo -e "${YELLOW}⚠️  Check log: /var/log/cron-auto-close-attendance.log${NC}"
fi

# Step 5: Show current crontab
echo ""
echo -e "${YELLOW}Step 5: Current crontab:${NC}"
if crontab -l > /dev/null 2>&1; then
    crontab -l
else
    echo "(No crontab installed yet)"
fi

# Step 6: Confirm installation
echo ""
echo -e "${YELLOW}Step 6: Install cron jobs?${NC}"
echo ""
echo -e "${BLUE}DAILY TASKS (Philippines Time):${NC}"
echo "  • 9:00 PM - Auto-close attendance"
echo "  • 11:30 PM - Mark absences"
echo ""
echo -e "${BLUE}WEEKLY TASKS (Philippines Time):${NC}"
echo "  • Friday 11:00 PM - Fix attendance & refresh payroll (for Saturday payday)"
echo ""
echo -e "${BLUE}YEARLY TASKS (January 1st, Philippines Time):${NC}"
echo "  • 2:00 AM - Update holiday years to new year"
echo "  • 3:00 AM - Replenish employee leave balances"
echo ""
echo -e "${BLUE}YEARLY TASKS (January 2nd, Philippines Time):${NC}"
echo "  • 2:00 AM - Archive/delete old payrolls"
echo ""
echo -e "${BLUE}DISK MAINTENANCE (Philippines Time):${NC}"
echo "  • 5:00 AM Daily  - Truncate large log files (>10MB)"
echo "  • 6:00 AM Daily  - Disk usage check (auto-cleanup at 90%+)"
echo "  • Sun 3:00 AM    - Docker system prune (unused images/containers)"
echo "  • Sun 3:30 AM    - Cleanup unused profile images"
echo "  • Monthly        - Clean logs older than 90 days"
echo ""
read -p "Install cron jobs? (yes/no): " CONFIRM

if [ "$CONFIRM" != "yes" ]; then
    echo -e "${YELLOW}⚠️  Cron jobs NOT installed${NC}"
    echo "Scripts are ready in $SCRIPT_DIR/"
    echo "You can install them manually later with: crontab -e"
    exit 0
fi

# Backup existing crontab
if crontab -l > /dev/null 2>&1; then
    echo ""
    echo -e "${YELLOW}Backing up existing crontab...${NC}"
    crontab -l > /root/crontab-backup-$(date +%Y%m%d-%H%M%S).txt
    echo -e "${GREEN}✅ Backup saved to /root/${NC}"
fi

# Create new crontab
echo ""
echo -e "${YELLOW}Installing cron jobs...${NC}"

# Get existing crontab (if any)
TEMP_CRON=$(mktemp)
if crontab -l > /dev/null 2>&1; then
    crontab -l | sed '/^# RVDC Attendance & Payroll Management Cron Jobs/,/^# END RVDC Cron Jobs/d' > "$TEMP_CRON"
fi

# Add RVDC cron jobs
cat >> "$TEMP_CRON" << 'CRONEND'

# ============================================================================
# RVDC Attendance & Payroll Management Cron Jobs (Weekly Payroll)
# Auto-generated by install-cron-jobs.sh
# All times are in Philippines Time (UTC+8)
# ============================================================================

CRON_TZ=Asia/Manila

# DAILY TASKS (Philippines Time)
# Daily at 9:00 PM Philippines - Auto-close open attendance records
0 21 * * * /opt/cron-scripts/auto-close-attendance.sh

# Daily at 7:00 AM Philippines - Send clock-in reminder
0 7 * * * /opt/cron-scripts/clock-in-reminder.sh

# Daily at 6:00 PM Philippines - Send clock-out reminder
0 18 * * * /opt/cron-scripts/clock-out-reminder.sh

# Daily at 11:30 PM Philippines - Mark absent employees
30 23 * * * /opt/cron-scripts/mark-absences.sh

# Daily at 2:00 AM Philippines - Delete old notifications (older than 7 days)
0 2 * * * /opt/cron-scripts/delete-old-notifications.sh

# Daily at 3:00 AM Philippines - Cleanup archived quotations (older than 14 days)
0 3 * * * /opt/cron-scripts/cleanup-archived-quotations.sh

# WEEKLY TASKS (Philippines Time)
# Every Friday at 11:00 PM Philippines - Fix last week's attendance & refresh payroll (Sat-Fri → Sat payday)
0 23 * * 5 /opt/cron-scripts/weekly-attendance-payroll-fix.sh

# YEARLY TASKS (January 1st - Philippines Time)
# January 1st at 2:00 AM Philippines - Update holiday years
0 2 1 1 * /opt/cron-scripts/yearly-update-holidays.sh

# January 1st at 3:00 AM Philippines - Replenish leave balances
0 3 1 1 * /opt/cron-scripts/yearly-replenish-leaves.sh

# YEARLY TASKS (January 2nd - Philippines Time)
# January 2nd at 2:00 AM Philippines - Archive old payrolls
0 2 2 1 * /opt/cron-scripts/yearly-archive-payrolls.sh

# DISK MAINTENANCE (Philippines Time)
# Daily at 5:00 AM Philippines - Truncate large log files
0 5 * * * /opt/cron-scripts/truncate-large-logs.sh

# Daily at 6:00 AM Philippines - Check disk usage, auto-cleanup at 90%+
0 6 * * * /opt/cron-scripts/disk-usage-check.sh

# Every Sunday at 3:00 AM Philippines - Docker system prune
0 3 * * 0 /opt/cron-scripts/docker-system-prune.sh

# Every Sunday at 3:30 AM Philippines - Cleanup unused profile images
30 3 * * 0 /opt/cron-scripts/cleanup-unused-images.sh

# 1st of every month at 3:00 AM Philippines - Delete old log files (90+ days)
0 3 1 * * find /var/log/cron-*.log -type f -mtime +90 -delete

CRONEND

# Install crontab
crontab "$TEMP_CRON"
rm "$TEMP_CRON"

echo -e "${GREEN}✅ Cron jobs installed${NC}"

# Step 7: Verify installation
echo ""
echo -e "${YELLOW}Step 7: Verifying installation...${NC}"
echo ""
echo "Installed cron jobs:"
crontab -l | grep -A 20 "RVDC Attendance"

# Final summary
echo ""
echo -e "${GREEN}╔════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║         Installation Complete! ✅          ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${GREEN}✅ Scripts created in:${NC} $SCRIPT_DIR/"
echo -e "${GREEN}✅ Logs will be saved to:${NC} /var/log/cron-*.log"
echo -e "${GREEN}✅ Cron jobs installed${NC}"
echo ""
echo -e "${YELLOW}Schedule Summary (Philippines Time):${NC}"
echo ""
echo -e "${BLUE}Daily:${NC}"
echo "  2:00 AM  → Delete old notifications (7+ days)"
echo "  3:00 AM  → Cleanup archived quotations (14+ days)"
echo "  5:00 AM  → Truncate large log files (>10MB)"
echo "  6:00 AM  → Disk usage check (auto-cleanup at 90%+)"
echo "  9:00 PM  → Auto-close attendance"
echo "  11:30 PM → Mark absences"
echo ""
echo -e "${BLUE}Weekly:${NC}"
echo "  Fri 11 PM   → Fix attendance + refresh payroll (for Sat payday)"
echo "  Sun 3:00 AM  → Docker system prune (unused images/containers)"
echo "  Sun 3:30 AM  → Cleanup unused profile images"
echo ""
echo -e "${BLUE}Monthly:${NC}"
echo "  1st 3:00 AM  → Delete old log files (90+ days)"
echo ""
echo -e "${BLUE}Yearly (Jan 1):${NC}"
echo "  2:00 AM → Update holidays to new year"
echo "  3:00 AM → Replenish leave balances"
echo ""
echo -e "${BLUE}Yearly (Jan 2):${NC}"
echo "  2:00 AM  → Archive last year's payrolls"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "1. Check timezone: timedatectl"
echo "2. Monitor first run: tail -f /var/log/cron-*.log"
echo "3. View cron jobs: crontab -l"
echo "4. Edit if needed: crontab -e"
echo ""
echo -e "${YELLOW}Manual testing:${NC}"
echo "  $SCRIPT_DIR/auto-close-attendance.sh"
echo "  $SCRIPT_DIR/weekly-attendance-payroll-fix.sh"
echo "  $SCRIPT_DIR/disk-usage-check.sh"
echo "  $SCRIPT_DIR/docker-system-prune.sh"
echo ""
echo -e "${GREEN}Installation log saved to: /root/cron-install-$(date +%Y%m%d).log${NC}"
echo ""

# Save installation log
{
    echo "=== RVDC Cron Installation (Weekly Payroll) ==="
    echo "Date: $(date)"
    echo "Container: $CONTAINER_NAME"
    echo "Scripts: $SCRIPT_DIR/"
    echo ""
    echo "Installed cron jobs:"
    crontab -l | grep -A 20 "RVDC Attendance"
} > "/root/cron-install-$(date +%Y%m%d).log"

exit 0
