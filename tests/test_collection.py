from datetime import date, datetime, timedelta
import unittest

from icalendar.prop import vDDDTypes

from davendar.collection import Event


class TestEntry(unittest.TestCase):

    def setUp(self):
        self.now = datetime.now().astimezone()
        self.today = self.now.date()
        self.today_end = datetime(self.today.year, self.today.month,
                                  self.today.day, 17).astimezone()
        self.yesterday = self.today - timedelta(1)
        self.yesterday_start = datetime(self.yesterday.year, self.yesterday.month,
                                        self.yesterday.day, 9).astimezone()
        self.yesterday_end = datetime(self.yesterday.year, self.yesterday.month,
                                      self.yesterday.day, 17).astimezone()
        self.tomorrow = self.today + timedelta(1)
        self.midnight = datetime(self.today.year, self.today.month,
                                 self.today.day).astimezone().timetz()

    def _event(self, start: date, end: date):
        e = Event()
        e._core["DTSTART"] = vDDDTypes(start)
        e._core["DTEND"] = vDDDTypes(end)
        return e

    def test_all_day_d(self):
        # 12/03
        e = self._event(self.yesterday, self.today)
        self.assertTrue(e.all_day, "Event marked not all day")

    def test_all_day_dt(self):
        # 12/03 09:00-17:00
        e = self._event(self.yesterday_start, self.yesterday_end)
        self.assertFalse(e.all_day, "Event marked all day")

    def test_days_d(self):
        # 12/03
        e = self._event(self.yesterday, self.today)
        self.assertNotIn(self.yesterday - timedelta(1), e.days, "Event leaks into past")
        self.assertIn(self.yesterday, e.days, "Event not including yesterday")
        self.assertNotIn(self.yesterday + timedelta(1), e.days, "Event leaks into future")

    def test_days_dt(self):
        # 12/03 09:00-17:00
        e = self._event(self.yesterday_start, self.yesterday_end)
        self.assertNotIn(self.yesterday - timedelta(1), e.days, "Event leaks into past")
        self.assertIn(self.yesterday, e.days, "Event not including yesterday")
        self.assertNotIn(self.yesterday + timedelta(1), e.days, "Event leaks into future")

    def test_days_d_multi(self):
        # 12/03 -- 13/03
        e = self._event(self.yesterday, self.tomorrow)
        self.assertNotIn(self.yesterday - timedelta(1), e.days, "Event leaks into past")
        self.assertIn(self.yesterday, e.days, "Event not including yesterday")
        self.assertIn(self.today, e.days, "Event not including today")
        self.assertNotIn(self.today + timedelta(1), e.days, "Event leaks into future")

    def test_days_dt_multi(self):
        # 12/03 09:00 -- 13/03 17:00
        e = self._event(self.yesterday_start, self.today_end)
        self.assertNotIn(self.yesterday - timedelta(1), e.days, "Event leaks into past")
        self.assertIn(self.yesterday, e.days, "Event not including yesterday")
        self.assertIn(self.today, e.days, "Event not including today")
        self.assertNotIn(self.today + timedelta(1), e.days, "Event leaks into future")

    def test_times_d(self):
        # 12/03
        e = self._event(self.yesterday, self.today)
        self.assertIsNone(e.times(self.yesterday - timedelta(1)),
                          "Event leaks into past")
        self.assertEqual(e.times(self.yesterday), (self.midnight, self.midnight),
                         "Event not including yesterday")
        self.assertIsNone(e.times(self.yesterday + timedelta(1)),
                          "Event leaks into future")

    def test_times_dt(self):
        # 12/03 09:00-17:00
        e = self._event(self.yesterday_start, self.yesterday_end)
        self.assertIsNone(e.times(self.yesterday - timedelta(1)),
                          "Event leaks into past")
        self.assertEqual(e.times(self.yesterday),
                         (self.yesterday_start.timetz(), self.yesterday_end.timetz()),
                         "Event not including yesterday's times")
        self.assertIsNone(e.times(self.yesterday + timedelta(1)),
                          "Event leaks into future")

    def test_times_d_multi(self):
        # 12/03 -- 13/03
        e = self._event(self.yesterday, self.tomorrow)
        self.assertIsNone(e.times(self.yesterday - timedelta(1)),
                          "Event leaks into past")
        self.assertEqual(e.times(self.yesterday), (self.midnight, None),
                         "Event not including yesterday")
        self.assertEqual(e.times(self.today), (None, self.midnight),
                         "Event not including today")
        self.assertIsNone(e.times(self.today + timedelta(1)),
                          "Event leaks into future")

    def test_times_dt_multi(self):
        # 12/03 09:00 -- 13/03 17:00
        e = self._event(self.yesterday_start, self.today_end)
        self.assertIsNone(e.times(self.yesterday - timedelta(1)),
                          "Event leaks into past")
        self.assertEqual(e.times(self.yesterday), (self.yesterday_start.timetz(), None),
                         "Event not including today's times")
        self.assertEqual(e.times(self.today), (None, self.today_end.timetz()),
                         "Event not including today's times")
        self.assertIsNone(e.times(self.today + timedelta(1)),
                          "Event leaks into future")


if __name__ == "__main__":
    unittest.main()
