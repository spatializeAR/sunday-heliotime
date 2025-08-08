"""
Geocoding and timezone resolution for HelioTime.
Supports multiple location input formats and caching.
"""

import os
import json
import time
import hashlib
import logging
from typing import Optional, Tuple, Dict, Any
from functools import lru_cache
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

logger = logging.getLogger(__name__)

# Initialize timezone finder - handle missing dependency gracefully
try:
    from timezonefinder import TimezoneFinder
    tf = TimezoneFinder()
except ImportError:
    logger.warning("timezonefinder not available - timezone resolution disabled")
    tf = None

# Environment configuration
GEOCODER = os.environ.get('GEOCODER', 'nominatim')
GEOCODER_API_KEY = os.environ.get('GEOCODER_API_KEY', '')
GEOCODER_BASE_URL = os.environ.get('GEOCODER_BASE_URL', 'https://nominatim.openstreetmap.org')
CACHE_TTL_SECONDS = int(os.environ.get('CACHE_TTL_SECONDS', '7776000'))  # 90 days

# Rate limiting for Nominatim
NOMINATIM_DELAY = 1.0  # seconds between requests
last_nominatim_request = 0


class GeocodingError(Exception):
    """Raised when geocoding fails."""
    pass


class TimezoneError(Exception):
    """Raised when timezone resolution fails."""
    pass


def get_cache_key(query_type: str, **params) -> str:
    """Generate cache key for geocoding query."""
    key_parts = [query_type]
    for k, v in sorted(params.items()):
        if v is not None:
            key_parts.append(f"{k}:{v}")
    
    key_string = "|".join(key_parts)
    return hashlib.md5(key_string.encode()).hexdigest()


@lru_cache(maxsize=1000)
def get_cached_geocode(cache_key: str) -> Optional[Dict[str, Any]]:
    """Get geocoding result from in-memory cache."""
    # In production, this would also check DynamoDB
    return None


def cache_geocode_result(cache_key: str, result: Dict[str, Any]):
    """Cache geocoding result."""
    # In production, this would also write to DynamoDB with TTL
    pass


def geocode_with_nominatim(query: str) -> Tuple[float, float, float]:
    """
    Geocode using Nominatim (OpenStreetMap).
    Returns (lat, lon, elevation_m).
    """
    global last_nominatim_request
    
    # Rate limiting
    elapsed = time.time() - last_nominatim_request
    if elapsed < NOMINATIM_DELAY:
        time.sleep(NOMINATIM_DELAY - elapsed)
    
    headers = {
        'User-Agent': 'HelioTime/1.0 (sunrise-sunset calculation service)'
    }
    
    params = {
        'q': query,
        'format': 'json',
        'limit': 1,
        'extratags': 1
    }
    
    try:
        response = requests.get(
            f"{GEOCODER_BASE_URL}/search",
            params=params,
            headers=headers,
            timeout=5
        )
        last_nominatim_request = time.time()
        
        response.raise_for_status()
        data = response.json()
        
        if not data:
            raise GeocodingError(f"No results found for query: {query}")
        
        result = data[0]
        lat = float(result['lat'])
        lon = float(result['lon'])
        
        # Try to get elevation from extratags
        elevation = 0.0
        if 'extratags' in result and 'ele' in result['extratags']:
            try:
                elevation = float(result['extratags']['ele'])
            except (ValueError, TypeError):
                pass
        
        logger.info(f"Nominatim geocoded '{query}' to ({lat}, {lon}, {elevation}m)")
        return lat, lon, elevation
        
    except requests.RequestException as e:
        logger.error(f"Nominatim request failed: {e}")
        raise GeocodingError(f"Geocoding service error: {str(e)}")
    except (KeyError, ValueError) as e:
        logger.error(f"Invalid Nominatim response: {e}")
        raise GeocodingError(f"Invalid geocoding response")


def geocode_postal(postal_code: str, country_code: str) -> Tuple[float, float, float]:
    """
    Geocode postal code with country.
    Returns (lat, lon, elevation_m).
    """
    cache_key = get_cache_key('postal', postal_code=postal_code, country_code=country_code)
    
    # Check cache
    cached = get_cached_geocode(cache_key)
    if cached:
        return cached['lat'], cached['lon'], cached.get('elevation_m', 0.0)
    
    # Format query for Nominatim
    query = f"{postal_code}, {country_code}"
    
    if GEOCODER == 'nominatim':
        lat, lon, elevation = geocode_with_nominatim(query)
    else:
        # Add support for other geocoders (Google, Mapbox) here
        raise GeocodingError(f"Unsupported geocoder: {GEOCODER}")
    
    # Cache result
    cache_geocode_result(cache_key, {
        'lat': lat,
        'lon': lon,
        'elevation_m': elevation
    })
    
    return lat, lon, elevation


def geocode_city(city: str, country: str) -> Tuple[float, float, float]:
    """
    Geocode city with country.
    Returns (lat, lon, elevation_m).
    """
    cache_key = get_cache_key('city', city=city, country=country)
    
    # Check cache
    cached = get_cached_geocode(cache_key)
    if cached:
        return cached['lat'], cached['lon'], cached.get('elevation_m', 0.0)
    
    # Format query
    query = f"{city}, {country}"
    
    if GEOCODER == 'nominatim':
        lat, lon, elevation = geocode_with_nominatim(query)
    else:
        # Add support for other geocoders here
        raise GeocodingError(f"Unsupported geocoder: {GEOCODER}")
    
    # Cache result
    cache_geocode_result(cache_key, {
        'lat': lat,
        'lon': lon,
        'elevation_m': elevation
    })
    
    return lat, lon, elevation


@lru_cache(maxsize=1000)
def resolve_timezone(lat: float, lon: float) -> str:
    """
    Resolve IANA timezone ID from coordinates.
    Returns timezone ID string (e.g., 'Europe/London').
    """
    if tf is None:
        # Fallback to UTC if timezonefinder not available
        logger.warning("TimezoneFinder not available, defaulting to UTC")
        return "UTC"
    
    # Try primary method
    tz_name = tf.timezone_at(lat=lat, lng=lon)
    
    if tz_name:
        logger.debug(f"Resolved timezone for ({lat}, {lon}): {tz_name}")
        return tz_name
    
    # Try finding closest timezone (for edge cases like ocean points)
    tz_name = tf.closest_timezone_at(lat=lat, lng=lon)
    
    if tz_name:
        logger.warning(f"Using closest timezone for ({lat}, {lon}): {tz_name}")
        return tz_name
    
    # Final fallback based on longitude (rough UTC offset)
    offset_hours = round(lon / 15)
    if offset_hours == 0:
        return 'UTC'
    elif offset_hours > 0:
        return f'Etc/GMT-{offset_hours}'  # Note: signs are reversed in Etc/GMT
    else:
        return f'Etc/GMT+{abs(offset_hours)}'


def get_timezone_info(lat: float, lon: float, date: datetime) -> ZoneInfo:
    """
    Get ZoneInfo object for coordinates and date.
    Handles DST transitions correctly.
    """
    tz_name = resolve_timezone(lat, lon)
    
    try:
        return ZoneInfo(tz_name)
    except Exception as e:
        logger.error(f"Failed to create ZoneInfo for {tz_name}: {e}")
        raise TimezoneError(f"Invalid timezone: {tz_name}")


def parse_gps_string(gps: str) -> Tuple[float, float]:
    """
    Parse GPS coordinate string "lat,lon".
    Returns (lat, lon) tuple.
    """
    try:
        parts = gps.strip().split(',')
        if len(parts) != 2:
            raise ValueError("GPS string must be 'lat,lon' format")
        
        lat = float(parts[0].strip())
        lon = float(parts[1].strip())
        
        if not (-90 <= lat <= 90):
            raise ValueError(f"Latitude {lat} out of range [-90, 90]")
        if not (-180 <= lon <= 180):
            raise ValueError(f"Longitude {lon} out of range [-180, 180]")
        
        return lat, lon
        
    except (ValueError, IndexError) as e:
        raise ValueError(f"Invalid GPS string format: {str(e)}")


def resolve_location(params: Dict[str, Any]) -> Tuple[float, float, float]:
    """
    Resolve location from various input formats.
    
    Supports:
    - lat, lon (direct coordinates)
    - gps (string "lat,lon")
    - postal_code + country_code
    - city + country
    
    Returns (lat, lon, elevation_m).
    """
    # Direct coordinates
    if 'lat' in params and 'lon' in params:
        lat = float(params['lat'])
        lon = float(params['lon'])
        elevation = float(params.get('elevation_m', 0.0))
        return lat, lon, elevation
    
    # GPS string
    if 'gps' in params:
        lat, lon = parse_gps_string(params['gps'])
        elevation = float(params.get('elevation_m', 0.0))
        return lat, lon, elevation
    
    # Postal code
    if 'postal_code' in params and 'country_code' in params:
        return geocode_postal(params['postal_code'], params['country_code'])
    
    # City
    if 'city' in params and 'country' in params:
        return geocode_city(params['city'], params['country'])
    
    raise ValueError("No valid location parameters provided")