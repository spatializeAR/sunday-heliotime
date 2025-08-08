"""
Test Lambda handler and API endpoints.
"""

import pytest
import json
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

from heliotime.handler import lambda_handler, parse_query_parameters


class TestLambdaHandler:
    """Test Lambda handler functionality."""
    
    def test_healthz_endpoint(self):
        """Test /healthz endpoint returns healthy status."""
        event = {
            'httpMethod': 'GET',
            'path': '/healthz',
            'queryStringParameters': None
        }
        
        response = lambda_handler(event, None)
        
        assert response['statusCode'] == 200
        assert 'Content-Type' in response['headers']
        
        body = json.loads(response['body'])
        assert body['status'] == 'healthy'
        assert body['service'] == 'HelioTime'
        assert 'version' in body
    
    def test_sun_endpoint_with_coordinates(self):
        """Test /sun endpoint with direct coordinates."""
        event = {
            'httpMethod': 'GET',
            'path': '/sun',
            'queryStringParameters': {
                'lat': '51.5074',
                'lon': '-0.1278',
                'date': '2025-09-01'
            }
        }
        
        response = lambda_handler(event, None)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        
        assert 'request' in body
        assert 'days' in body
        assert len(body['days']) == 1
        
        day = body['days'][0]
        assert day['date'] == '2025-09-01'
        assert 'sunrise' in day
        assert 'sunset' in day
        assert 'solar_noon' in day
    
    def test_sun_endpoint_with_gps_string(self):
        """Test /sun endpoint with GPS string."""
        event = {
            'httpMethod': 'GET',
            'path': '/sun',
            'queryStringParameters': {
                'gps': '51.5074,-0.1278',
                'date': '2025-06-21'
            }
        }
        
        response = lambda_handler(event, None)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        
        assert body['request']['lat'] == 51.5074
        assert body['request']['lon'] == -0.1278
    
    def test_sun_endpoint_date_range(self):
        """Test /sun endpoint with date range."""
        event = {
            'httpMethod': 'GET',
            'path': '/sun',
            'queryStringParameters': {
                'lat': '64.1466',
                'lon': '-21.9426',
                'start_date': '2025-06-01',
                'end_date': '2025-06-07'
            }
        }
        
        response = lambda_handler(event, None)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        
        assert len(body['days']) == 7
        assert body['days'][0]['date'] == '2025-06-01'
        assert body['days'][6]['date'] == '2025-06-07'
    
    def test_sun_endpoint_without_twilight(self):
        """Test /sun endpoint with twilight disabled."""
        event = {
            'httpMethod': 'GET',
            'path': '/sun',
            'queryStringParameters': {
                'lat': '40.7128',
                'lon': '-74.0060',
                'date': '2025-03-20',
                'include_twilight': 'false'
            }
        }
        
        response = lambda_handler(event, None)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        
        day = body['days'][0]
        assert 'sunrise' in day
        assert 'sunset' in day
        assert 'civil_dawn' not in day
        assert 'civil_dusk' not in day
    
    def test_sun_endpoint_with_custom_parameters(self):
        """Test /sun endpoint with custom atmospheric parameters."""
        event = {
            'httpMethod': 'GET',
            'path': '/sun',
            'queryStringParameters': {
                'lat': '35.6762',
                'lon': '139.6503',
                'date': '2025-01-01',
                'elevation_m': '100',
                'pressure_hpa': '1020',
                'temperature_c': '5',
                'altitude_correction': 'true'
            }
        }
        
        response = lambda_handler(event, None)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        
        assert body['request']['elevation_m'] == 100.0
        assert body['request']['pressure_hpa'] == 1020.0
        assert body['request']['temperature_c'] == 5.0
    
    def test_invalid_coordinates(self):
        """Test error handling for invalid coordinates."""
        event = {
            'httpMethod': 'GET',
            'path': '/sun',
            'queryStringParameters': {
                'lat': '95',  # Invalid latitude
                'lon': '-0.1278',
                'date': '2025-01-01'
            }
        }
        
        response = lambda_handler(event, None)
        
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert 'error' in body
    
    def test_missing_location(self):
        """Test error handling for missing location."""
        event = {
            'httpMethod': 'GET',
            'path': '/sun',
            'queryStringParameters': {
                'date': '2025-01-01'
            }
        }
        
        response = lambda_handler(event, None)
        
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert 'error' in body
    
    def test_date_range_too_large(self):
        """Test error handling for date range exceeding limit."""
        event = {
            'httpMethod': 'GET',
            'path': '/sun',
            'queryStringParameters': {
                'lat': '51.5074',
                'lon': '-0.1278',
                'start_date': '2025-01-01',
                'end_date': '2026-01-01'  # 365+ days
            }
        }
        
        with patch.dict('os.environ', {'MAX_RANGE_DAYS': '365'}):
            response = lambda_handler(event, None)
        
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert 'range too large' in body['error'].lower()
    
    def test_cors_headers(self):
        """Test CORS headers are present."""
        event = {
            'httpMethod': 'OPTIONS',
            'path': '/sun',
            'queryStringParameters': None
        }
        
        response = lambda_handler(event, None)
        
        assert response['statusCode'] == 200
        assert response['headers']['Access-Control-Allow-Origin'] == '*'
        assert 'GET' in response['headers']['Access-Control-Allow-Methods']
    
    def test_unknown_endpoint(self):
        """Test 404 for unknown endpoint."""
        event = {
            'httpMethod': 'GET',
            'path': '/unknown',
            'queryStringParameters': None
        }
        
        response = lambda_handler(event, None)
        
        assert response['statusCode'] == 404
        body = json.loads(response['body'])
        assert 'error' in body


class TestParameterParsing:
    """Test query parameter parsing."""
    
    def test_parse_coordinates(self):
        """Test parsing coordinate parameters."""
        event = {
            'queryStringParameters': {
                'lat': '51.5074',
                'lon': '-0.1278',
                'elevation_m': '35.5'
            }
        }
        
        params = parse_query_parameters(event)
        
        assert params['lat'] == 51.5074
        assert params['lon'] == -0.1278
        assert params['elevation_m'] == 35.5
    
    def test_parse_dates(self):
        """Test parsing date parameters."""
        event = {
            'queryStringParameters': {
                'date': '2025-09-01',
                'start_date': '2025-06-01',
                'end_date': '2025-06-30'
            }
        }
        
        params = parse_query_parameters(event)
        
        assert isinstance(params['date'], datetime)
        assert params['date'].date().isoformat() == '2025-09-01'
        assert params['start_date'].date().isoformat() == '2025-06-01'
        assert params['end_date'].date().isoformat() == '2025-06-30'
    
    def test_parse_boolean_parameters(self):
        """Test parsing boolean parameters."""
        event = {
            'queryStringParameters': {
                'altitude_correction': 'true',
                'include_twilight': 'false',
                'dev_crosscheck': '1'
            }
        }
        
        params = parse_query_parameters(event)
        
        assert params['altitude_correction'] is True
        assert params['include_twilight'] is False
        assert params['dev_crosscheck'] is True
    
    def test_parse_location_variants(self):
        """Test parsing different location formats."""
        # GPS string
        event = {
            'queryStringParameters': {
                'gps': '51.5074,-0.1278'
            }
        }
        params = parse_query_parameters(event)
        assert params['gps'] == '51.5074,-0.1278'
        
        # Postal code
        event = {
            'queryStringParameters': {
                'postal_code': 'W1A 1AA',
                'country_code': 'gb'
            }
        }
        params = parse_query_parameters(event)
        assert params['postal_code'] == 'W1A 1AA'
        assert params['country_code'] == 'GB'
        
        # City
        event = {
            'queryStringParameters': {
                'city': 'Reykjavik',
                'country': 'Iceland'
            }
        }
        params = parse_query_parameters(event)
        assert params['city'] == 'Reykjavik'
        assert params['country'] == 'Iceland'