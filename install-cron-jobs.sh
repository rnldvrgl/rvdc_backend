#!/bin/bash

###############################################################################
# RVDC Cron Jobs Installation Script (Updated for Weekly Payroll)
#
# This script automatically sets up cron jobs for your Dockerized Django app
# on a DigitalOcean droplet.
#
# Cron jobs provided:
# - Daily: Auto-close attendance (11:00 PM Philippines time)
# - Daily: Mark absences (11:30 PM Philippines time)
# - Weekly: Fix attendance & refresh payroll (Friday 11 PM Philippines time)
# - Yearly: Update holiday years to new year (Jan 1, 2:00 AM Philippines time)
# - Yearly: Replenish leave balances (Jan 1, 3:00 AM Philippines time)
# - Yearly: Archive old payrolls (Jan 2, 2:00 AM Philippines time)
# - Monthly: Clean old logs (1st of month, 3:00 AM Philippines time)
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

echo -e "${GREEN}╔════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   RVDC Cron Jobs Installation Script      ║${NC}"
echo -e "${GREEN}║        (Weekly Payroll Edition)            ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════╝${NC}"
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

# Script 1: Auto-close attendance (Daily 11:00 PM)
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
    --start-date "$LAST_SATURDAY" \
    --end-date "$LAST_FRIDAY" << CONFIRM >> "$LOG_FILE" 2>&1
yes
CONFIRM

# Step 3: Refresh payroll from attendance
echo "--- Step 3: Refreshing payroll ---" >> "$LOG_FILE"
docker exec "$CONTAINER_NAME" python manage.py refresh_payroll_from_attendance \
    --start-date "$LAST_SATURDAY" \
    --end-date "$LAST_FRIDAY" << CONFIRM >> "$LOG_FILE" 2>&1
yes
CONFIRM

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
    --year "$NEXT_YEAR" << CONFIRM >> "$LOG_FILE" 2>&1
yes
CONFIRM

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
    --emergency-leave 3 << CONFIRM >> "$LOG_FILE" 2>&1
yes
CONFIRM

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
    --delete << CONFIRM >> "$LOG_FILE" 2>&1
yes
CONFIRM

if [ $? -eq 0 ]; then
    echo "✅ Payrolls archived - $(date '+%Y-%m-%d %H:%M:%S %Z')" >> "$LOG_FILE"
else
    echo "❌ Payroll archival failed - $(date '+%Y-%m-%d %H:%M:%S %Z')" >> "$LOG_FILE"
fi
echo "" >> "$LOG_FILE"
EOF

# Replace placeholder with actual container name
sed -i "s/CONTAINER_NAME_PLACEHOLDER/$CONTAINER_NAME/g" "$SCRIPT_DIR"/*.sh

# Make scripts executable
chmod +x "$SCRIPT_DIR"/*.sh

echo -e "${GREEN}✅ Created 6 cron scripts${NC}"

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
echo "  • 11:00 PM - Auto-close attendance"
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
echo -e "${BLUE}MAINTENANCE:${NC}"
echo "  • Monthly - Clean logs older than 90 days"
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
    crontab -l > "$TEMP_CRON"
fi

# Add RVDC cron jobs
cat >> "$TEMP_CRON" << 'CRONEND'

# ============================================================================
# RVDC Attendance & Payroll Management Cron Jobs (Weekly Payroll)
# Auto-generated by install-cron-jobs.sh
# All times are in Philippines Time (UTC+8)
# ============================================================================

# DAILY TASKS (Philippines Time)
# Daily at 11:00 PM Philippines (3:00 PM UTC) - Auto-close open attendance records
0 15 * * * /opt/cron-scripts/auto-close-attendance.sh

# Daily at 11:30 PM Philippines (3:30 PM UTC) - Mark absent employees
30 15 * * * /opt/cron-scripts/mark-absences.sh

# WEEKLY TASKS (Philippines Time)
# Every Friday at 11:00 PM Philippines (3:00 PM UTC) - Fix last week's attendance & refresh payroll (Sat-Fri → Sat payday)
0 15 * * 5 /opt/cron-scripts/weekly-attendance-payroll-fix.sh

# YEARLY TASKS (January 1st - Philippines Time)
# January 1st at 2:00 AM Philippines (6:00 PM Dec 31 UTC) - Update holiday years
0 18 31 12 * /opt/cron-scripts/yearly-update-holidays.sh

# January 1st at 3:00 AM Philippines (7:00 PM Dec 31 UTC) - Replenish leave balances
0 19 31 12 * /opt/cron-scripts/yearly-replenish-leaves.sh

# YEARLY TASKS (January 2nd - Philippines Time)
# January 2nd at 2:00 AM Philippines (6:00 PM Jan 1 UTC) - Archive old payrolls
0 18 1 1 * /opt/cron-scripts/yearly-archive-payrolls.sh

# MAINTENANCE
# 1st of every month at 3:00 AM Philippines (7:00 PM previous day UTC) - Rotate logs (keep 90 days)
0 19 * * * [ "$(date +\%d)" = "01" ] && find /var/log/cron-*.log -type f -mtime +90 -delete

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
echo "  6:30 PM  → Auto-close attendance"
echo "  7:00 PM  → Mark absences"
echo ""
echo -e "${BLUE}Weekly:${NC}"
echo "  Fri 11 PM   → Fix attendance + refresh payroll (for Sat payday)"
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
