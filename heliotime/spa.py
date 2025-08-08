"""
NREL Solar Position Algorithm (SPA) Implementation
Based on: Reda, I.; Andreas, A. (2003). Solar Position Algorithm for Solar Radiation Applications.
NREL Report No. TP-560-34302, Revised January 2008.

This is a simplified Python implementation for Lambda deployment.
"""

import math
from datetime import datetime, timezone
from typing import Tuple, Optional


def julian_day(dt: datetime) -> float:
    """Calculate Julian Day Number from datetime."""
    year = dt.year
    month = dt.month
    day = dt.day + dt.hour / 24.0 + dt.minute / 1440.0 + dt.second / 86400.0
    
    if month <= 2:
        year -= 1
        month += 12
    
    a = math.floor(year / 100.0)
    b = 2 - a + math.floor(a / 4.0)
    
    jd = math.floor(365.25 * (year + 4716)) + math.floor(30.6001 * (month + 1)) + day + b - 1524.5
    return jd


def julian_century(jd: float) -> float:
    """Calculate Julian Century from Julian Day."""
    return (jd - 2451545.0) / 36525.0


def sun_geometric_mean_longitude(jc: float) -> float:
    """Calculate sun's geometric mean longitude (degrees)."""
    l0 = 280.46646 + jc * (36000.76983 + jc * 0.0003032)
    return l0 % 360


def sun_geometric_mean_anomaly(jc: float) -> float:
    """Calculate sun's geometric mean anomaly (degrees)."""
    return 357.52911 + jc * (35999.05029 - 0.0001537 * jc)


def earth_orbit_eccentricity(jc: float) -> float:
    """Calculate eccentricity of Earth's orbit."""
    return 0.016708634 - jc * (0.000042037 + 0.0000001267 * jc)


def sun_equation_of_center(jc: float) -> float:
    """Calculate sun's equation of center (degrees)."""
    m = math.radians(sun_geometric_mean_anomaly(jc))
    
    c = (math.sin(m) * (1.914602 - jc * (0.004817 + 0.000014 * jc)) +
         math.sin(2 * m) * (0.019993 - 0.000101 * jc) +
         math.sin(3 * m) * 0.000289)
    
    return c


def sun_true_longitude(jc: float) -> float:
    """Calculate sun's true longitude (degrees)."""
    l0 = sun_geometric_mean_longitude(jc)
    c = sun_equation_of_center(jc)
    return l0 + c


def sun_apparent_longitude(jc: float) -> float:
    """Calculate sun's apparent longitude (degrees)."""
    true_long = sun_true_longitude(jc)
    omega = 125.04 - 1934.136 * jc
    app_long = true_long - 0.00569 - 0.00478 * math.sin(math.radians(omega))
    return app_long


def mean_obliquity_of_ecliptic(jc: float) -> float:
    """Calculate mean obliquity of ecliptic (degrees)."""
    seconds = 21.448 - jc * (46.8150 + jc * (0.00059 - jc * 0.001813))
    return 23.0 + (26.0 + (seconds / 60.0)) / 60.0


def obliquity_correction(jc: float) -> float:
    """Calculate obliquity correction (degrees)."""
    e0 = mean_obliquity_of_ecliptic(jc)
    omega = 125.04 - 1934.136 * jc
    return e0 + 0.00256 * math.cos(math.radians(omega))


def sun_declination(jc: float) -> float:
    """Calculate sun's declination angle (degrees)."""
    e = obliquity_correction(jc)
    app_long = sun_apparent_longitude(jc)
    
    declination = math.degrees(math.asin(
        math.sin(math.radians(e)) * math.sin(math.radians(app_long))
    ))
    
    return declination


def equation_of_time(jc: float) -> float:
    """Calculate equation of time (minutes)."""
    epsilon = obliquity_correction(jc)
    l0 = sun_geometric_mean_longitude(jc)
    e = earth_orbit_eccentricity(jc)
    m = sun_geometric_mean_anomaly(jc)
    
    y = math.tan(math.radians(epsilon) / 2.0)
    y = y * y
    
    sin2l0 = math.sin(2.0 * math.radians(l0))
    sinm = math.sin(math.radians(m))
    cos2l0 = math.cos(2.0 * math.radians(l0))
    sin4l0 = math.sin(4.0 * math.radians(l0))
    sin2m = math.sin(2.0 * math.radians(m))
    
    etime = y * sin2l0 - 2.0 * e * sinm + 4.0 * e * y * sinm * cos2l0 - \
            0.5 * y * y * sin4l0 - 1.25 * e * e * sin2m
    
    return math.degrees(etime) * 4.0


def hour_angle(lat: float, declination: float, altitude_threshold: float) -> Optional[float]:
    """
    Calculate hour angle for given altitude threshold.
    Returns None if sun never reaches the altitude (polar day/night).
    """
    lat_rad = math.radians(lat)
    decl_rad = math.radians(declination)
    alt_rad = math.radians(altitude_threshold)
    
    cos_h = (math.sin(alt_rad) - math.sin(lat_rad) * math.sin(decl_rad)) / \
            (math.cos(lat_rad) * math.cos(decl_rad))
    
    if cos_h < -1:
        return 180.0  # Sun never sets (polar day)
    elif cos_h > 1:
        return None  # Sun never rises (polar night)
    else:
        return math.degrees(math.acos(cos_h))


def atmospheric_refraction(altitude: float, pressure_hpa: float = 1013.25, 
                          temperature_c: float = 15.0) -> float:
    """
    Calculate atmospheric refraction correction.
    Based on Meeus, Astronomical Algorithms.
    """
    if altitude > 85:
        return 0
    
    # Convert to Kelvin
    temp_k = temperature_c + 273.15
    
    # Pressure and temperature correction
    pressure_factor = pressure_hpa / 1010.0
    temp_factor = 283.0 / temp_k
    
    if altitude > -0.575:
        refraction = 1.02 / math.tan(math.radians(altitude + 10.3 / (altitude + 5.11)))
    else:
        refraction = 1.0 / math.tan(math.radians(altitude))
    
    refraction = refraction * pressure_factor * temp_factor / 60.0
    
    return refraction


def solar_position(dt: datetime, lat: float, lon: float, 
                   elevation_m: float = 0.0,
                   pressure_hpa: float = 1013.25, 
                   temperature_c: float = 15.0) -> Tuple[float, float]:
    """
    Calculate solar position (azimuth and altitude) for given time and location.
    
    Returns:
        (azimuth, altitude) in degrees
    """
    jd = julian_day(dt)
    jc = julian_century(jd)
    
    # Solar declination
    decl = sun_declination(jc)
    
    # Equation of time
    eqtime = equation_of_time(jc)
    
    # True solar time
    time_offset = eqtime + 4 * lon
    tst = dt.hour * 60 + dt.minute + dt.second / 60 + time_offset
    
    # Hour angle
    ha = (tst / 4) - 180
    if ha < -180:
        ha += 360
    
    # Convert to radians
    lat_rad = math.radians(lat)
    decl_rad = math.radians(decl)
    ha_rad = math.radians(ha)
    
    # Zenith angle
    cos_zenith = (math.sin(lat_rad) * math.sin(decl_rad) +
                  math.cos(lat_rad) * math.cos(decl_rad) * math.cos(ha_rad))
    
    # Clamp to valid range
    cos_zenith = max(-1, min(1, cos_zenith))
    zenith = math.degrees(math.acos(cos_zenith))
    
    # Altitude
    altitude = 90 - zenith
    
    # Apply refraction correction
    altitude += atmospheric_refraction(altitude, pressure_hpa, temperature_c)
    
    # Azimuth
    if ha > 0:
        azimuth = math.degrees(math.acos(
            ((math.sin(lat_rad) * math.cos(math.radians(zenith))) - math.sin(decl_rad)) /
            (math.cos(lat_rad) * math.sin(math.radians(zenith)))
        )) + 180
    else:
        azimuth = 540 - math.degrees(math.acos(
            ((math.sin(lat_rad) * math.cos(math.radians(zenith))) - math.sin(decl_rad)) /
            (math.cos(lat_rad) * math.sin(math.radians(zenith)))
        ))
    
    azimuth = azimuth % 360
    
    return azimuth, altitude


def find_sun_event_time(date: datetime, lat: float, lon: float,
                        altitude_threshold: float,
                        is_rising: bool,
                        elevation_m: float = 0.0,
                        pressure_hpa: float = 1013.25,
                        temperature_c: float = 15.0) -> Optional[datetime]:
    """
    Find time when sun crosses given altitude threshold.
    Uses iterative refinement for accuracy.
    """
    # Start with solar noon as reference
    jd = julian_day(date.replace(hour=12, minute=0, second=0, tzinfo=timezone.utc))
    jc = julian_century(jd)
    
    decl = sun_declination(jc)
    ha = hour_angle(lat, decl, altitude_threshold)
    
    if ha is None:
        return None
    
    # Calculate approximate time
    eqtime = equation_of_time(jc)
    time_correction = eqtime - 4 * lon
    
    if is_rising:
        solar_time = 720 - 4 * ha - time_correction
    else:
        solar_time = 720 + 4 * ha - time_correction
    
    # Convert to hours and minutes
    hours = int(solar_time // 60)
    minutes = int(solar_time % 60)
    seconds = int((solar_time % 1) * 60)
    
    # Handle day boundaries
    if hours < 0:
        hours += 24
        date = date.replace(day=date.day - 1)
    elif hours >= 24:
        hours -= 24
        date = date.replace(day=date.day + 1)
    
    event_time = date.replace(hour=hours, minute=minutes, second=seconds, 
                             microsecond=0, tzinfo=timezone.utc)
    
    # Refine with Newton-Raphson iteration
    for _ in range(5):
        _, alt = solar_position(event_time, lat, lon, elevation_m, 
                               pressure_hpa, temperature_c)
        
        error = alt - altitude_threshold
        if abs(error) < 0.001:  # Within 0.001 degree
            break
        
        # Estimate derivative (degrees per minute)
        dt_test = event_time.replace(minute=event_time.minute + 1 if event_time.minute < 59 else 0)
        _, alt_test = solar_position(dt_test, lat, lon, elevation_m,
                                    pressure_hpa, temperature_c)
        
        d_alt_dt = (alt_test - alt) / 1.0  # per minute
        
        if abs(d_alt_dt) < 0.001:
            break
        
        # Newton-Raphson step
        correction_minutes = -error / d_alt_dt
        
        # Apply correction
        total_minutes = event_time.hour * 60 + event_time.minute + correction_minutes
        hours = int(total_minutes // 60) % 24
        minutes = int(total_minutes % 60)
        seconds = int((total_minutes % 1) * 60)
        
        event_time = event_time.replace(hour=hours, minute=minutes, second=seconds)
    
    return event_time