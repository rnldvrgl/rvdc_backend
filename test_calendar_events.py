#!/usr/bin/env python
"""
Test script for Calendar Events API endpoint
Run this script to verify the calendar events endpoint is working correctly.

Usage:
    python test_calendar_events.py
"""

import json
from datetime import datetime, timedelta

import requests

# Configuration
BASE_URL = "http://localhost:8000"
API_ENDPOINT = f"{BASE_URL}/api/analytics/calendar/events/"

def print_section(title):
    """Print a formatted section header"""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)

def test_calendar_events():
    """Test the calendar events endpoint"""

    print_section("Calendar Events API Test")

    # Test 1: Current month
    print("\n[TEST 1] Fetching events for current month...")
    today = datetime.now()
    start_date = today.replace(day=1).strftime("%Y-%m-%d")

    # Get last day of current month
    if today.month == 12:
        end_date = today.replace(day=31).strftime("%Y-%m-%d")
    else:
        next_month = today.replace(month=today.month + 1, day=1)
        end_date = (next_month - timedelta(days=1)).strftime("%Y-%m-%d")

    params = {
        "start": start_date,
        "end": end_date
    }

    try:
        response = requests.get(API_ENDPOINT, params=params)

        if response.status_code == 200:
            events = response.json()
            print(f"✓ SUCCESS: Received {len(events)} events")

            # Count by type
            event_types = {}
            for event in events:
                event_type = event.get('extendedProps', {}).get('type', 'unknown')
                event_types[event_type] = event_types.get(event_type, 0) + 1

            print("\nEvent breakdown:")
            for event_type, count in event_types.items():
                print(f"  - {event_type.title()}: {count}")

            # Show sample events
            if events:
                print("\nSample events:")
                for i, event in enumerate(events[:5], 1):
                    print(f"\n  {i}. {event.get('title')}")
                    print(f"     Date: {event.get('start')}")
                    print(f"     Type: {event.get('extendedProps', {}).get('type')}")
                    print(f"     All Day: {event.get('allDay', False)}")

                if len(events) > 5:
                    print(f"\n  ... and {len(events) - 5} more events")
        else:
            print(f"✗ FAILED: HTTP {response.status_code}")
            print(f"Response: {response.text}")

    except requests.exceptions.ConnectionError:
        print("✗ FAILED: Could not connect to server")
        print(f"Make sure the Django server is running at {BASE_URL}")
        return False
    except Exception as e:
        print(f"✗ FAILED: {str(e)}")
        return False

    # Test 2: Full year
    print("\n" + "-" * 70)
    print("\n[TEST 2] Fetching events for full year...")

    year_start = datetime(today.year, 1, 1).strftime("%Y-%m-%d")
    year_end = datetime(today.year, 12, 31).strftime("%Y-%m-%d")

    params = {
        "start": year_start,
        "end": year_end
    }

    try:
        response = requests.get(API_ENDPOINT, params=params)

        if response.status_code == 200:
            events = response.json()
            print(f"✓ SUCCESS: Received {len(events)} events for year {today.year}")

            # Count by type
            event_types = {}
            for event in events:
                event_type = event.get('extendedProps', {}).get('type', 'unknown')
                event_types[event_type] = event_types.get(event_type, 0) + 1

            print("\nYearly event breakdown:")
            for event_type, count in event_types.items():
                print(f"  - {event_type.title()}: {count}")
        else:
            print(f"✗ FAILED: HTTP {response.status_code}")

    except Exception as e:
        print(f"✗ FAILED: {str(e)}")

    # Test 3: Without parameters (should use defaults)
    print("\n" + "-" * 70)
    print("\n[TEST 3] Fetching events without date parameters...")

    try:
        response = requests.get(API_ENDPOINT)

        if response.status_code == 200:
            events = response.json()
            print(f"✓ SUCCESS: Received {len(events)} events (using default date range)")
        else:
            print(f"✗ FAILED: HTTP {response.status_code}")

    except Exception as e:
        print(f"✗ FAILED: {str(e)}")

    # Test 4: Verify event structure
    print("\n" + "-" * 70)
    print("\n[TEST 4] Verifying event data structure...")

    try:
        response = requests.get(API_ENDPOINT, params={"start": year_start, "end": year_end})

        if response.status_code == 200:
            events = response.json()

            if not events:
                print("⚠ WARNING: No events found to verify structure")
            else:
                # Check first event structure
                event = events[0]
                required_fields = ['id', 'title', 'start', 'allDay', 'extendedProps']
                missing_fields = [field for field in required_fields if field not in event]

                if missing_fields:
                    print(f"✗ FAILED: Missing required fields: {missing_fields}")
                else:
                    print("✓ SUCCESS: Event structure is valid")

                # Check extendedProps
                extended_props = event.get('extendedProps', {})
                if 'type' not in extended_props:
                    print("✗ FAILED: Missing 'type' in extendedProps")
                else:
                    event_type = extended_props['type']
                    print(f"  Event type: {event_type}")

                    # Verify type-specific fields
                    if event_type == 'birthday':
                        required = ['user_id', 'user_name']
                    elif event_type == 'holiday':
                        required = ['holiday_id', 'holiday_type']
                    elif event_type == 'schedule':
                        required = ['schedule_id', 'service_type', 'client_name']
                    else:
                        required = []

                    missing = [field for field in required if field not in extended_props]
                    if missing:
                        print(f"  ✗ Missing {event_type} fields: {missing}")
                    else:
                        print(f"  ✓ All {event_type} fields present")

                # Show full event structure
                print("\n  Sample event structure:")
                print(json.dumps(event, indent=4, default=str))

    except Exception as e:
        print(f"✗ FAILED: {str(e)}")

    print("\n" + "=" * 70)
    print("  Test Complete")
    print("=" * 70 + "\n")

if __name__ == "__main__":
    test_calendar_events()
