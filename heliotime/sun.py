"""
Sun event calculations using the SPA algorithm.
Handles sunrise, sunset, twilights, and polar edge cases.
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any
from zoneinfo import ZoneInfo
import logging

from spa import (
    find_sun_event_time, solar_position, julian_day, 
    julian_century, sun_declination, equation_of_time
)

logger = logging.getLogger(__name__)

# Event altitude thresholds (degrees)
ALTITUDES = {
    'sunrise': -0.833,  # Center of sun disk at horizon with refraction
    'sunset': -0.833,
    'civil_dawn': -6.0,
    'civil_dusk': -6.0,
    'nautical_dawn': -12.0,
    'nautical_dusk': -12.0,
    'astronomical_dawn': -18.0,
    'astronomical_dusk': -18.0,
}


def calculate_solar_noon(date: datetime, lat: float, lon: float) -> datetime:
    """Calculate solar noon (sun's highest point) for given date and location."""
    # Start with approximate solar noon
    noon_utc = date.replace(hour=12, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
    
    # Apply longitude correction (4 minutes per degree)
    noon_utc -= timedelta(minutes=4 * lon)
    
    # Apply equation of time correction
    jd = julian_day(noon_utc)
    jc = julian_century(jd)
    eqtime = equation_of_time(jc)
    
    noon_utc -= timedelta(minutes=eqtime)
    
    # Refine with iteration
    for _ in range(3):
        _, altitude = solar_position(noon_utc, lat, lon)
        
        # Check altitude one minute before and after
        before = noon_utc - timedelta(minutes=1)
        _, alt_before = solar_position(before, lat, lon)
        
        after = noon_utc + timedelta(minutes=1)
        _, alt_after = solar_position(after, lat, lon)
        
        # If current is highest, we're done
        if altitude >= alt_before and altitude >= alt_after:
            break
        
        # Otherwise adjust toward higher altitude
        if alt_before > altitude:
            noon_utc = before
        else:
            noon_utc = after
    
    return noon_utc


def apply_horizon_correction(altitude_threshold: float, elevation_m: float,
                           altitude_correction: bool) -> float:
    """
    Apply horizon dip correction for observer elevation.
    Approximation: dip_degrees ≈ 1.76 * sqrt(elevation_m) / 60
    """
    if not altitude_correction or elevation_m <= 0:
        return altitude_threshold
    
    import math
    dip_degrees = 1.76 * math.sqrt(elevation_m) / 60
    return altitude_threshold - dip_degrees


def sun_events_for_date(
    lat: float,
    lon: float,
    date_utc: datetime,
    tzinfo: ZoneInfo,
    elevation_m: float = 0.0,
    pressure_hpa: float = 1013.25,
    temperature_c: float = 15.0,
    altitude_correction: bool = False,
    include_twilight: bool = True
) -> Dict[str, Any]:
    """
    Calculate all sun events for a given date and location.
    
    Returns dict with:
    - date: ISO date string
    - sunrise/sunset: ISO datetime strings in local time
    - twilight times (if include_twilight=True)
    - solar_noon: ISO datetime string
    - day_length_sec: daylight duration in seconds
    - flags: polar_day, polar_night, no_civil_twilight
    """
    # Ensure date is in UTC and at start of day
    date_utc = date_utc.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
    
    results = {
        'date': date_utc.date().isoformat(),
        'sunrise': None,
        'sunset': None,
        'solar_noon': None,
        'day_length_sec': 0,
        'flags': {
            'polar_day': False,
            'polar_night': False,
            'no_civil_twilight': False,
            'no_nautical_twilight': False,
            'no_astronomical_twilight': False,
        }
    }
    
    # Calculate solar noon first (always exists)
    solar_noon = calculate_solar_noon(date_utc, lat, lon)
    results['solar_noon'] = solar_noon.astimezone(tzinfo).isoformat()
    
    # Check if we're in polar day or night
    _, noon_altitude = solar_position(solar_noon, lat, lon, elevation_m,
                                     pressure_hpa, temperature_c)
    
    # Calculate sunrise and sunset
    sunrise_threshold = apply_horizon_correction(
        ALTITUDES['sunrise'], elevation_m, altitude_correction
    )
    
    sunrise = find_sun_event_time(
        date_utc, lat, lon, sunrise_threshold, is_rising=True,
        elevation_m=elevation_m, pressure_hpa=pressure_hpa,
        temperature_c=temperature_c
    )
    
    sunset = find_sun_event_time(
        date_utc, lat, lon, sunrise_threshold, is_rising=False,
        elevation_m=elevation_m, pressure_hpa=pressure_hpa,
        temperature_c=temperature_c
    )
    
    # Handle polar cases
    if sunrise is None and sunset is None:
        if noon_altitude > sunrise_threshold:
            results['flags']['polar_day'] = True
            results['day_length_sec'] = 86400  # 24 hours
        else:
            results['flags']['polar_night'] = True
            results['day_length_sec'] = 0
    else:
        if sunrise:
            results['sunrise'] = sunrise.astimezone(tzinfo).isoformat()
        if sunset:
            results['sunset'] = sunset.astimezone(tzinfo).isoformat()
        
        # Calculate day length
        if sunrise and sunset:
            results['day_length_sec'] = int((sunset - sunrise).total_seconds())
    
    # Calculate twilight times if requested
    if include_twilight:
        twilight_events = [
            ('civil_dawn', ALTITUDES['civil_dawn'], True),
            ('civil_dusk', ALTITUDES['civil_dusk'], False),
            ('nautical_dawn', ALTITUDES['nautical_dawn'], True),
            ('nautical_dusk', ALTITUDES['nautical_dusk'], False),
            ('astronomical_dawn', ALTITUDES['astronomical_dawn'], True),
            ('astronomical_dusk', ALTITUDES['astronomical_dusk'], False),
        ]
        
        for event_name, altitude, is_rising in twilight_events:
            corrected_altitude = apply_horizon_correction(
                altitude, elevation_m, altitude_correction
            )
            
            event_time = find_sun_event_time(
                date_utc, lat, lon, corrected_altitude, is_rising,
                elevation_m=elevation_m, pressure_hpa=pressure_hpa,
                temperature_c=temperature_c
            )
            
            if event_time:
                results[event_name] = event_time.astimezone(tzinfo).isoformat()
            else:
                results[event_name] = None
                
                # Set appropriate flags
                if 'civil' in event_name:
                    results['flags']['no_civil_twilight'] = True
                elif 'nautical' in event_name:
                    results['flags']['no_nautical_twilight'] = True
                elif 'astronomical' in event_name:
                    results['flags']['no_astronomical_twilight'] = True
    
    return results


def sun_events_for_range(
    lat: float,
    lon: float,
    start_date: datetime,
    end_date: datetime,
    tzinfo: ZoneInfo,
    **kwargs
) -> List[Dict[str, Any]]:
    """
    Calculate sun events for a date range.
    
    Returns list of daily event dictionaries.
    """
    results = []
    current_date = start_date
    
    while current_date <= end_date:
        day_events = sun_events_for_date(
            lat, lon, current_date, tzinfo, **kwargs
        )
        results.append(day_events)
        current_date += timedelta(days=1)
    
    return results


def validate_location(lat: float, lon: float) -> bool:
    """Validate latitude and longitude values."""
    return -90 <= lat <= 90 and -180 <= lon <= 180


def format_duration(seconds: int) -> str:
    """Format duration in seconds to human-readable string."""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"