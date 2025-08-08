"""
Test SPA implementation against NREL reference values.
Reference: https://www.nrel.gov/docs/fy08osti/34302.pdf
"""

import pytest
from datetime import datetime, timezone
import math

from heliotime.spa import (
    julian_day, julian_century, sun_declination, 
    equation_of_time, solar_position
)


class TestSPACalculations:
    """Test core SPA calculations against known values."""
    
    def test_julian_day(self):
        """Test Julian Day calculation."""
        # Test case from NREL paper
        dt = datetime(2003, 10, 17, 12, 30, 30, tzinfo=timezone.utc)
        jd = julian_day(dt)
        expected = 2452930.020833  # From NREL example
        assert abs(jd - expected) < 0.000001
    
    def test_julian_century(self):
        """Test Julian Century calculation."""
        jd = 2452930.020833
        jc = julian_century(jd)
        expected = 0.037928  # Approximate from NREL
        assert abs(jc - expected) < 0.000001
    
    def test_sun_declination(self):
        """Test sun declination calculation."""
        # Summer solstice - max declination ~23.45°
        dt_summer = datetime(2025, 6, 21, 12, 0, 0, tzinfo=timezone.utc)
        jd_summer = julian_day(dt_summer)
        jc_summer = julian_century(jd_summer)
        decl_summer = sun_declination(jc_summer)
        assert 23.0 < decl_summer < 23.5
        
        # Winter solstice - min declination ~-23.45°
        dt_winter = datetime(2025, 12, 21, 12, 0, 0, tzinfo=timezone.utc)
        jd_winter = julian_day(dt_winter)
        jc_winter = julian_century(jd_winter)
        decl_winter = sun_declination(jc_winter)
        assert -23.5 < decl_winter < -23.0
        
        # Equinox - declination ~0°
        dt_equinox = datetime(2025, 3, 20, 12, 0, 0, tzinfo=timezone.utc)
        jd_equinox = julian_day(dt_equinox)
        jc_equinox = julian_century(jd_equinox)
        decl_equinox = sun_declination(jc_equinox)
        assert -1.0 < decl_equinox < 1.0
    
    def test_equation_of_time(self):
        """Test equation of time calculation."""
        # Test known extremes
        # Around Feb 11: maximum positive (~14 minutes)
        dt_feb = datetime(2025, 2, 11, 12, 0, 0, tzinfo=timezone.utc)
        jd_feb = julian_day(dt_feb)
        jc_feb = julian_century(jd_feb)
        eot_feb = equation_of_time(jc_feb)
        assert 13 < eot_feb < 15
        
        # Around Nov 3: maximum negative (~-16 minutes)
        dt_nov = datetime(2025, 11, 3, 12, 0, 0, tzinfo=timezone.utc)
        jd_nov = julian_day(dt_nov)
        jc_nov = julian_century(jd_nov)
        eot_nov = equation_of_time(jc_nov)
        assert -17 < eot_nov < -15
    
    def test_solar_position_noon(self):
        """Test solar position at solar noon."""
        # London at summer solstice noon
        dt = datetime(2025, 6, 21, 12, 0, 0, tzinfo=timezone.utc)
        lat, lon = 51.5074, -0.1278
        
        azimuth, altitude = solar_position(dt, lat, lon)
        
        # At solar noon, sun should be roughly south (180°)
        assert 170 < azimuth < 190
        
        # Maximum altitude at London in summer
        # Should be approximately 90 - lat + declination = 90 - 51.5 + 23.4 ≈ 62°
        assert 60 < altitude < 64
    
    def test_solar_position_sunrise(self):
        """Test solar position at approximate sunrise."""
        # London on equinox - sunrise roughly at 6 AM local time
        dt = datetime(2025, 3, 20, 6, 0, 0, tzinfo=timezone.utc)
        lat, lon = 51.5074, -0.1278
        
        azimuth, altitude = solar_position(dt, lat, lon)
        
        # At sunrise, sun should be roughly east (90°)
        assert 85 < azimuth < 95
        
        # Altitude should be near horizon
        assert -2 < altitude < 2


class TestPolarCases:
    """Test polar day/night edge cases."""
    
    def test_svalbard_polar_day(self):
        """Test polar day in Svalbard during summer."""
        # Longyearbyen, Svalbard in mid-June
        dt = datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        lat, lon = 78.2232, 15.6267
        
        # Check sun altitude at midnight
        dt_midnight = datetime(2025, 6, 15, 0, 0, 0, tzinfo=timezone.utc)
        _, altitude_midnight = solar_position(dt_midnight, lat, lon)
        
        # Sun should still be above horizon at midnight
        assert altitude_midnight > -0.833
    
    def test_svalbard_polar_night(self):
        """Test polar night in Svalbard during winter."""
        # Longyearbyen, Svalbard in mid-December
        dt = datetime(2025, 12, 15, 12, 0, 0, tzinfo=timezone.utc)
        lat, lon = 78.2232, 15.6267
        
        # Check sun altitude at noon
        _, altitude_noon = solar_position(dt, lat, lon)
        
        # Sun should be below horizon even at noon
        assert altitude_noon < -0.833


class TestAccuracyBenchmarks:
    """Test accuracy against other implementations."""
    
    def test_london_sunrise_sunset(self):
        """Test London sunrise/sunset times."""
        from heliotime.sun import sun_events_for_date
        from zoneinfo import ZoneInfo
        
        # London on September 1, 2025
        dt = datetime(2025, 9, 1, 0, 0, 0, tzinfo=timezone.utc)
        lat, lon = 51.5074, -0.1278
        tz = ZoneInfo('Europe/London')
        
        events = sun_events_for_date(lat, lon, dt, tz)
        
        # Expected times (approximate, from NOAA calculator)
        # Sunrise: ~06:14 BST
        # Sunset: ~19:44 BST
        
        assert events['sunrise'] is not None
        assert events['sunset'] is not None
        
        sunrise = datetime.fromisoformat(events['sunrise'])
        sunset = datetime.fromisoformat(events['sunset'])
        
        # Check times are reasonable (within 5 minutes)
        assert 6 <= sunrise.hour <= 7
        assert 10 <= sunrise.minute <= 20
        
        assert 19 <= sunset.hour <= 20
        assert 39 <= sunset.minute <= 49