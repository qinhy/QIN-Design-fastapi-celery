
import unittest
import pytz
import datetime
import re

def parse_execution_time(execution_time_str, timezone_str):
    """
    Parses the execution_time_str and returns:
    - utc_execution_time (datetime in UTC)
    - local_time (datetime in specified timezone)
    - next_execution_time_str (formatted in specified timezone)

    Recurrence must be at least every 10 seconds.
    Supports formats:
    - 'NOW'
    - '60' (delay in seconds)
    - 'YYYY-MM-DDTHH:MM:SS'
    - 'NOW@every 1 d', '2025-04-07T12:00:00@every 10 s', etc.
    """
    print('parse_execution_time : get',execution_time_str, timezone_str)

    utc_now = datetime.datetime.now(datetime.timezone.utc)
    tz = pytz.timezone(timezone_str)
    local_now = utc_now.astimezone(tz)

    utc_execution_time = None
    local_time = None
    next_execution_time_str = execution_time_str  # default

    try:
        # Match recurrence pattern: "<base>@every <num> <unit>"
        recur_match = re.match(r"^(.+?)@every\s+(\d+)\s*([smhd])$", execution_time_str.strip(), re.IGNORECASE)
        if recur_match:
            base_time_str, num_str, unit = recur_match.groups()
            unit = unit.lower()
            interval_seconds = {
                's': int(num_str),
                'm': int(num_str) * 60,
                'h': int(num_str) * 3600,
                'd': int(num_str) * 86400,
            }[unit]

            if interval_seconds < 10:
                raise ValueError("Recurrence interval must be at least every 10 seconds.")

            # Resolve base time
            if base_time_str.upper() == "NOW":
                base_local_time = local_now
            else:
                base_local_time = datetime.datetime.strptime(base_time_str, "%Y-%m-%dT%H:%M:%S")
                base_local_time = tz.localize(base_local_time)

            local_time = base_local_time + datetime.timedelta(seconds=interval_seconds)
            utc_execution_time = local_time.astimezone(pytz.UTC)

            formatted_base = (local_time + datetime.timedelta(seconds=interval_seconds)).strftime("%Y-%m-%dT%H:%M:%S")
            next_execution_time_str = f"{formatted_base}@every {num_str} {unit}"
        # Handle "NOW"
        elif execution_time_str.upper() == "NOW":
            utc_execution_time = utc_now
            local_time = local_now
            next_execution_time_str = None
        # Handle delay in seconds
        elif execution_time_str.isdigit():
            delay_seconds = int(execution_time_str)
            utc_execution_time = utc_now + datetime.timedelta(seconds=delay_seconds)
            local_time = utc_execution_time.astimezone(tz)
            next_execution_time_str = None
        else:
            # Handle absolute datetime
            local_time = datetime.datetime.strptime(execution_time_str, "%Y-%m-%dT%H:%M:%S")
            local_time = tz.localize(local_time)
            utc_execution_time = local_time.astimezone(pytz.UTC)
            next_execution_time_str = None

        print('parse_execution_time : return ',utc_execution_time,'|', local_time,'|',(next_execution_time_str,timezone_str))    
        return utc_execution_time, local_time, (next_execution_time_str,timezone_str)

    except Exception as e:
        raise ValueError(f"Invalid execution_time format: {execution_time_str}. Error: {str(e)}")

import unittest
import datetime
import pytz

class TestParseExecutionTime(unittest.TestCase):

    def setUp(self):
        self.tz_name = "Asia/Tokyo"
        self.tz = pytz.timezone(self.tz_name)
        self.utc_now = datetime.datetime.now(datetime.timezone.utc)

    def assert_time_near(self, actual, expected, tolerance_seconds=2):
        delta = abs((actual - expected).total_seconds())
        self.assertLessEqual(delta, tolerance_seconds, f"Time delta too large: {delta}s")

    def test_now(self):
        utc_time, local_time, next_str = parse_execution_time("NOW", self.tz_name)
        next_str,zone = next_str
        self.assert_time_near(utc_time, self.utc_now)
        self.assertEqual(utc_time.tzinfo, datetime.timezone.utc)
        self.assertEqual(local_time.tzinfo.zone, self.tz.zone)
        self.assertIsNone(next_str)

    def test_seconds_delay(self):
        utc_time, local_time, next_str = parse_execution_time("60", self.tz_name)
        next_str,zone = next_str
        expected = self.utc_now + datetime.timedelta(seconds=60)
        self.assert_time_near(utc_time, expected)
        self.assertEqual(local_time.tzinfo.zone, self.tz.zone)
        self.assertIsNone(next_str)

    def test_absolute_time(self):
        input_str = "2025-04-07T12:00:00"
        utc_time, local_time, next_str = parse_execution_time(input_str, self.tz_name)
        next_str,zone = next_str
        expected_local = self.tz.localize(datetime.datetime.strptime(input_str, "%Y-%m-%dT%H:%M:%S"))
        expected_utc = expected_local.astimezone(pytz.UTC)
        self.assertEqual(local_time, expected_local)
        self.assertEqual(utc_time, expected_utc)
        self.assertIsNone(next_str)

    def test_recurring_now(self):
        utc_time, local_time, next_str = parse_execution_time("NOW@every 10 s", self.tz_name)
        next_str,zone = next_str
        self.assertIsNotNone(next_str)
        self.assertTrue("@every 10 s" in next_str)

    def test_recurring_absolute(self):
        input_str = "2025-04-07T12:00:00@every 1 d"
        utc_time, local_time, next_str = parse_execution_time(input_str, self.tz_name)
        next_str,zone = next_str
        self.assertEqual(local_time.strftime("%H:%M:%S"), "12:00:00")
        self.assertTrue("@every 1 d" in next_str)

    def test_invalid_format(self):
        with self.assertRaises(ValueError):
            parse_execution_time("INVALID_STRING", self.tz_name)

    def test_invalid_date_format(self):
        with self.assertRaises(ValueError):
            parse_execution_time("2025/04/07 12:00:00", self.tz_name)

    def test_invalid_recurrence_unit(self):
        with self.assertRaises(ValueError):
            parse_execution_time("NOW@every 10 x", self.tz_name)

    def test_recurrence_too_short(self):
        with self.assertRaises(ValueError):
            parse_execution_time("NOW@every 5 s", self.tz_name)

    def test_timezone_conversion(self):
        utc_time, local_time, _ = parse_execution_time("60", "US/Eastern")
        self.assertTrue(utc_time.isoformat().endswith('+00:00'))
        self.assertEqual(local_time.tzinfo.zone, "US/Eastern")
        self.assertNotEqual(
            utc_time.strftime("%Y-%m-%dT%H:%M:%S"),
            local_time.strftime("%Y-%m-%dT%H:%M:%S"),
            "Local and UTC time representations should differ"
        )


if __name__ == "__main__":
    unittest.main()
