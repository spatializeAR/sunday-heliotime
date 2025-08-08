"""
AWS Lambda handler for HelioTime API.
Handles /sun and /healthz endpoints.
"""

import os
import json
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional
from zoneinfo import ZoneInfo

from .sun import sun_events_for_date, sun_events_for_range, validate_location
from .geo import resolve_location, get_timezone_info, GeocodingError, TimezoneError
from .crosscheck import cross_check_day, cross_check_range, CrossCheckError

# Configure logging
log_level = os.environ.get('LOG_LEVEL', 'INFO')
logging.basicConfig(level=getattr(logging, log_level))
logger = logging.getLogger(__name__)

# Environment configuration
ENV = os.environ.get('ENV', 'dev')
MAX_RANGE_DAYS = int(os.environ.get('MAX_RANGE_DAYS', '366'))
DEV_CROSSCHECK = os.environ.get('DEV_CROSSCHECK', 'false').lower() == 'true'

# Build info
BUILD_SHA = os.environ.get('BUILD_SHA', 'unknown')
BUILD_DATE = os.environ.get('BUILD_DATE', 'unknown')


def create_response(status_code: int, body: Any, headers: Optional[Dict] = None) -> Dict:
    """Create Lambda response with CORS headers."""
    default_headers = {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type',
        'X-HelioTime-Version': '1.0.0',
        'X-HelioTime-Environment': ENV
    }
    
    if headers:
        default_headers.update(headers)
    
    return {
        'statusCode': status_code,
        'headers': default_headers,
        'body': json.dumps(body) if not isinstance(body, str) else body
    }


def parse_query_parameters(event: Dict) -> Dict[str, Any]:
    """Parse and validate query parameters from API Gateway event."""
    params = event.get('queryStringParameters') or {}
    
    # Convert string parameters to appropriate types
    parsed = {}
    
    # Location parameters
    if 'lat' in params:
        parsed['lat'] = float(params['lat'])
    if 'lon' in params:
        parsed['lon'] = float(params['lon'])
    if 'gps' in params:
        parsed['gps'] = params['gps']
    if 'postal_code' in params:
        parsed['postal_code'] = params['postal_code']
    if 'country_code' in params:
        parsed['country_code'] = params['country_code'].upper()
    if 'city' in params:
        parsed['city'] = params['city']
    if 'country' in params:
        parsed['country'] = params['country']
    
    # Date parameters
    if 'date' in params:
        parsed['date'] = datetime.fromisoformat(params['date']).replace(tzinfo=timezone.utc)
    if 'start_date' in params:
        parsed['start_date'] = datetime.fromisoformat(params['start_date']).replace(tzinfo=timezone.utc)
    if 'end_date' in params:
        parsed['end_date'] = datetime.fromisoformat(params['end_date']).replace(tzinfo=timezone.utc)
    
    # Optional parameters
    if 'elevation_m' in params:
        parsed['elevation_m'] = float(params['elevation_m'])
    if 'pressure_hpa' in params:
        parsed['pressure_hpa'] = float(params['pressure_hpa'])
    if 'temperature_c' in params:
        parsed['temperature_c'] = float(params['temperature_c'])
    if 'tz' in params:
        parsed['tz'] = params['tz']
    if 'altitude_correction' in params:
        parsed['altitude_correction'] = params['altitude_correction'].lower() in ('true', '1', 'yes')
    if 'include_twilight' in params:
        parsed['include_twilight'] = params['include_twilight'].lower() in ('true', '1', 'yes')
    else:
        parsed['include_twilight'] = True  # Default to true
    if 'dev_crosscheck' in params:
        parsed['dev_crosscheck'] = params['dev_crosscheck'].lower() in ('true', '1', 'yes')
    
    return parsed


def handle_sun_endpoint(event: Dict) -> Dict:
    """Handle GET /sun endpoint."""
    start_time = time.time()
    
    try:
        # Parse parameters
        params = parse_query_parameters(event)
        
        # Resolve location
        try:
            lat, lon, elevation_m = resolve_location(params)
        except (GeocodingError, ValueError) as e:
            logger.error(f"Location resolution failed: {e}")
            return create_response(400, {
                'error': 'Invalid location parameters',
                'message': str(e)
            })
        
        # Validate coordinates
        if not validate_location(lat, lon):
            return create_response(400, {
                'error': 'Invalid coordinates',
                'message': f'Coordinates out of range: lat={lat}, lon={lon}'
            })
        
        # Use provided elevation or resolved elevation
        if 'elevation_m' in params:
            elevation_m = params['elevation_m']
        
        # Determine date range
        if 'date' in params:
            start_date = end_date = params['date']
        elif 'start_date' in params and 'end_date' in params:
            start_date = params['start_date']
            end_date = params['end_date']
            
            # Validate range
            days_diff = (end_date - start_date).days + 1
            if days_diff > MAX_RANGE_DAYS:
                return create_response(400, {
                    'error': 'Date range too large',
                    'message': f'Maximum range is {MAX_RANGE_DAYS} days, requested {days_diff} days'
                })
            if days_diff < 1:
                return create_response(400, {
                    'error': 'Invalid date range',
                    'message': 'End date must be after or equal to start date'
                })
        else:
            # Default to today
            start_date = end_date = datetime.now(timezone.utc)
        
        # Resolve timezone
        try:
            if 'tz' in params:
                # User-provided timezone
                tzinfo = ZoneInfo(params['tz'])
            else:
                # Auto-detect from coordinates
                tzinfo = get_timezone_info(lat, lon, start_date)
        except (TimezoneError, Exception) as e:
            logger.error(f"Timezone resolution failed: {e}")
            return create_response(422, {
                'error': 'Timezone resolution failed',
                'message': str(e)
            })
        
        # Prepare calculation parameters
        calc_params = {
            'elevation_m': elevation_m,
            'pressure_hpa': params.get('pressure_hpa', 1013.25),
            'temperature_c': params.get('temperature_c', 15.0),
            'altitude_correction': params.get('altitude_correction', False),
            'include_twilight': params.get('include_twilight', True)
        }
        
        # Calculate sun events
        if start_date == end_date:
            # Single day
            day_events = sun_events_for_date(lat, lon, start_date, tzinfo, **calc_params)
            days = [day_events]
            
            # Cross-check if enabled
            crosscheck_result = None
            if DEV_CROSSCHECK or params.get('dev_crosscheck'):
                if ENV == 'prod' and params.get('dev_crosscheck'):
                    logger.warning("Cross-check requested in production - ignoring")
                elif ENV == 'dev':
                    try:
                        crosscheck_result = cross_check_day(lat, lon, start_date, day_events)
                    except CrossCheckError as e:
                        return create_response(500, {
                            'error': 'Cross-check failed',
                            'message': str(e),
                            'calculated_events': day_events
                        })
        else:
            # Date range
            days = sun_events_for_range(lat, lon, start_date, end_date, tzinfo, **calc_params)
            
            # Cross-check if enabled
            crosscheck_result = None
            if DEV_CROSSCHECK or params.get('dev_crosscheck'):
                if ENV == 'prod' and params.get('dev_crosscheck'):
                    logger.warning("Cross-check requested in production - ignoring")
                elif ENV == 'dev':
                    try:
                        crosscheck_result = cross_check_range(lat, lon, start_date, days)
                    except CrossCheckError as e:
                        return create_response(500, {
                            'error': 'Cross-check failed',
                            'message': str(e),
                            'calculated_events': days
                        })
        
        # Calculate processing time
        compute_time_ms = int((time.time() - start_time) * 1000)
        
        # Build response
        response_body = {
            'request': {
                'lat': round(lat, 6),
                'lon': round(lon, 6),
                'elevation_m': round(elevation_m, 1),
                'timezone': str(tzinfo),
                'pressure_hpa': calc_params['pressure_hpa'],
                'temperature_c': calc_params['temperature_c'],
                'algorithm': 'NREL_SPA_2005'
            },
            'days': days,
            'meta': {
                'computed_in_ms': compute_time_ms
            }
        }
        
        # Add date range to request info
        if start_date == end_date:
            response_body['request']['date'] = start_date.date().isoformat()
        else:
            response_body['request']['start_date'] = start_date.date().isoformat()
            response_body['request']['end_date'] = end_date.date().isoformat()
        
        # Add cross-check results if available
        if crosscheck_result:
            response_body['meta']['dev_crosscheck'] = crosscheck_result
        
        return create_response(200, response_body)
        
    except Exception as e:
        logger.exception(f"Unexpected error in sun endpoint: {e}")
        return create_response(500, {
            'error': 'Internal server error',
            'message': 'An unexpected error occurred'
        })


def handle_healthz_endpoint(event: Dict) -> Dict:
    """Handle GET /healthz endpoint."""
    return create_response(200, {
        'status': 'healthy',
        'service': 'HelioTime',
        'version': '1.0.0',
        'environment': ENV,
        'build': {
            'sha': BUILD_SHA,
            'date': BUILD_DATE
        },
        'config': {
            'max_range_days': MAX_RANGE_DAYS,
            'dev_crosscheck': DEV_CROSSCHECK and ENV == 'dev'
        }
    })


def lambda_handler(event: Dict, context: Any) -> Dict:
    """
    Main Lambda handler function.
    Routes requests to appropriate endpoint handlers.
    """
    # Log request
    logger.info(f"Request: {event.get('httpMethod')} {event.get('path')}")
    
    # Handle CORS preflight
    if event.get('httpMethod') == 'OPTIONS':
        return create_response(200, '')
    
    # Route to endpoint handlers
    path = event.get('path', '/')
    
    if path == '/sun' and event.get('httpMethod') == 'GET':
        return handle_sun_endpoint(event)
    elif path == '/healthz' and event.get('httpMethod') == 'GET':
        return handle_healthz_endpoint(event)
    else:
        return create_response(404, {
            'error': 'Not found',
            'message': f"Unknown endpoint: {event.get('httpMethod')} {path}"
        })