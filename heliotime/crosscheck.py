"""
Cross-check module for validating calculations against external APIs.
Only active in development mode.
"""

import os
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import requests

logger = logging.getLogger(__name__)

# Configuration from environment
DEV_CROSSCHECK = os.environ.get('DEV_CROSSCHECK', 'false').lower() == 'true'
DEV_CROSSCHECK_PROVIDER = os.environ.get('DEV_CROSSCHECK_PROVIDER', 'open-meteo')
DEV_CROSSCHECK_TOLERANCE_SECONDS = int(os.environ.get('DEV_CROSSCHECK_TOLERANCE_SECONDS', '120'))
DEV_CROSSCHECK_ENFORCE = os.environ.get('DEV_CROSSCHECK_ENFORCE', 'false').lower() == 'true'


class CrossCheckError(Exception):
    """Raised when cross-check fails beyond tolerance."""
    pass


def fetch_open_meteo(lat: float, lon: float, date: datetime) -> Dict[str, Any]:
    """
    Fetch sunrise/sunset from Open-Meteo API.
    Returns times in UTC.
    """
    url = "https://api.open-meteo.com/v1/forecast"
    
    params = {
        'latitude': lat,
        'longitude': lon,
        'daily': 'sunrise,sunset',
        'timezone': 'UTC',
        'start_date': date.strftime('%Y-%m-%d'),
        'end_date': date.strftime('%Y-%m-%d')
    }
    
    try:
        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()
        
        data = response.json()
        
        if 'daily' not in data:
            raise ValueError("No daily data in Open-Meteo response")
        
        daily = data['daily']
        
        # Parse times (Open-Meteo returns ISO strings)
        sunrise_str = daily['sunrise'][0] if daily['sunrise'] else None
        sunset_str = daily['sunset'][0] if daily['sunset'] else None
        
        result = {}
        
        if sunrise_str:
            result['sunrise'] = datetime.fromisoformat(sunrise_str.replace('Z', '+00:00'))
        
        if sunset_str:
            result['sunset'] = datetime.fromisoformat(sunset_str.replace('Z', '+00:00'))
        
        return result
        
    except requests.RequestException as e:
        logger.error(f"Open-Meteo API request failed: {e}")
        return {}
    except (KeyError, ValueError, IndexError) as e:
        logger.error(f"Failed to parse Open-Meteo response: {e}")
        return {}


def fetch_sunrise_sunset_org(lat: float, lon: float, date: datetime) -> Dict[str, Any]:
    """
    Fetch sunrise/sunset from sunrise-sunset.org API.
    Returns times in UTC.
    """
    url = "https://api.sunrise-sunset.org/json"
    
    params = {
        'lat': lat,
        'lng': lon,
        'date': date.strftime('%Y-%m-%d'),
        'formatted': 0  # Returns ISO format
    }
    
    try:
        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()
        
        data = response.json()
        
        if data.get('status') != 'OK':
            raise ValueError(f"API returned status: {data.get('status')}")
        
        results = data.get('results', {})
        result = {}
        
        if 'sunrise' in results:
            result['sunrise'] = datetime.fromisoformat(
                results['sunrise'].replace('Z', '+00:00')
            )
        
        if 'sunset' in results:
            result['sunset'] = datetime.fromisoformat(
                results['sunset'].replace('Z', '+00:00')
            )
        
        return result
        
    except requests.RequestException as e:
        logger.error(f"sunrise-sunset.org API request failed: {e}")
        return {}
    except (KeyError, ValueError) as e:
        logger.error(f"Failed to parse sunrise-sunset.org response: {e}")
        return {}


def compare_times(calculated: Optional[datetime], external: Optional[datetime],
                  event_name: str) -> Dict[str, Any]:
    """
    Compare calculated time with external API time.
    Returns comparison metrics.
    """
    if calculated is None and external is None:
        return {
            'status': 'both_none',
            'delta_seconds': 0,
            'message': f"Both agree: no {event_name}"
        }
    
    if calculated is None:
        return {
            'status': 'calculated_none',
            'delta_seconds': None,
            'message': f"Calculated: no {event_name}, External: {external}"
        }
    
    if external is None:
        return {
            'status': 'external_none',
            'delta_seconds': None,
            'message': f"Calculated: {calculated}, External: no {event_name}"
        }
    
    # Both have values - calculate delta
    delta = (calculated - external).total_seconds()
    
    return {
        'status': 'compared',
        'delta_seconds': int(delta),
        'calculated': calculated.isoformat(),
        'external': external.isoformat()
    }


def cross_check_day(lat: float, lon: float, date: datetime,
                   calculated_events: Dict[str, Any]) -> Dict[str, Any]:
    """
    Cross-check calculated sun events against external API.
    
    Returns cross-check results and raises exception if tolerance exceeded
    and enforcement is enabled.
    """
    if not DEV_CROSSCHECK:
        return {}
    
    # Fetch from external API
    if DEV_CROSSCHECK_PROVIDER == 'open-meteo':
        external = fetch_open_meteo(lat, lon, date)
    elif DEV_CROSSCHECK_PROVIDER == 'sunrise-sunset':
        external = fetch_sunrise_sunset_org(lat, lon, date)
    else:
        logger.warning(f"Unknown cross-check provider: {DEV_CROSSCHECK_PROVIDER}")
        return {}
    
    if not external:
        logger.warning("Failed to fetch external data for cross-check")
        return {
            'provider': DEV_CROSSCHECK_PROVIDER,
            'status': 'fetch_failed'
        }
    
    # Compare sunrise and sunset
    comparisons = {}
    max_delta = 0
    
    for event in ['sunrise', 'sunset']:
        if event in calculated_events and calculated_events[event]:
            # Parse calculated time (it's in local timezone)
            calc_time = datetime.fromisoformat(calculated_events[event])
            # Convert to UTC for comparison
            calc_time_utc = calc_time.astimezone(timezone.utc)
        else:
            calc_time_utc = None
        
        ext_time = external.get(event)
        
        comparison = compare_times(calc_time_utc, ext_time, event)
        comparisons[event] = comparison
        
        if comparison['delta_seconds'] is not None:
            max_delta = max(max_delta, abs(comparison['delta_seconds']))
    
    # Build result
    result = {
        'provider': DEV_CROSSCHECK_PROVIDER,
        'comparisons': comparisons,
        'tolerance_seconds': DEV_CROSSCHECK_TOLERANCE_SECONDS,
        'max_delta_seconds': max_delta,
        'status': 'within_tolerance' if max_delta <= DEV_CROSSCHECK_TOLERANCE_SECONDS else 'exceeded_tolerance'
    }
    
    # Log results
    logger.info(f"Cross-check with {DEV_CROSSCHECK_PROVIDER}: max delta = {max_delta}s")
    
    # Enforce tolerance if configured
    if DEV_CROSSCHECK_ENFORCE and max_delta > DEV_CROSSCHECK_TOLERANCE_SECONDS:
        error_msg = (
            f"Cross-check tolerance exceeded: {max_delta}s > {DEV_CROSSCHECK_TOLERANCE_SECONDS}s. "
            f"Provider: {DEV_CROSSCHECK_PROVIDER}"
        )
        logger.error(error_msg)
        raise CrossCheckError(error_msg)
    
    return result


def cross_check_range(lat: float, lon: float, start_date: datetime,
                     calculated_days: list) -> Dict[str, Any]:
    """
    Cross-check a range of dates.
    Returns aggregated cross-check results.
    """
    if not DEV_CROSSCHECK:
        return {}
    
    all_comparisons = []
    max_delta_overall = 0
    failed_days = []
    
    for i, day_events in enumerate(calculated_days):
        date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        date = date.replace(day=date.day + i)
        
        try:
            day_check = cross_check_day(lat, lon, date, day_events)
            
            if day_check.get('max_delta_seconds', 0) > DEV_CROSSCHECK_TOLERANCE_SECONDS:
                failed_days.append(day_events['date'])
            
            max_delta_overall = max(max_delta_overall, day_check.get('max_delta_seconds', 0))
            all_comparisons.append(day_check)
            
        except CrossCheckError:
            # Re-raise if enforcement is enabled
            if DEV_CROSSCHECK_ENFORCE:
                raise
            # Otherwise just log
            failed_days.append(day_events['date'])
    
    return {
        'provider': DEV_CROSSCHECK_PROVIDER,
        'days_checked': len(calculated_days),
        'max_delta_seconds': max_delta_overall,
        'tolerance_seconds': DEV_CROSSCHECK_TOLERANCE_SECONDS,
        'status': 'within_tolerance' if max_delta_overall <= DEV_CROSSCHECK_TOLERANCE_SECONDS else 'exceeded_tolerance',
        'failed_days': failed_days
    }