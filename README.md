# HelioTime 🌅

Deterministic, offline sunrise/sunset calculation service with optional development cross-checks.

[![Deploy](https://github.com/spatializeAR/sunday-heliotime/actions/workflows/deploy.yml/badge.svg)](https://github.com/spatializeAR/sunday-heliotime/actions/workflows/deploy.yml)

## Overview

HelioTime is a high-performance AWS Lambda service that calculates precise sunrise, sunset, and twilight times using the NREL Solar Position Algorithm (SPA). It provides:

- 🌍 **Multiple location input formats** (coordinates, GPS string, postal code, city)
- 🕐 **Automatic timezone resolution** with DST handling
- 📅 **Single date or date range** calculations (up to 366 days)
- 🌙 **Twilight calculations** (civil, nautical, astronomical)
- 🏔️ **Elevation and atmospheric corrections**
- ❄️ **Polar day/night handling**
- ✅ **Optional cross-checking** against external APIs (dev mode)

## API Endpoints

### Production
- Base URL: `https://heliotime.sunday.wiki`
- Health check: `https://heliotime.sunday.wiki/healthz`

### Development
- Base URL: `https://heliotime.dev.sunday.wiki`
- Health check: `https://heliotime.dev.sunday.wiki/healthz`

## Quick Start

### Simple coordinate request
```bash
curl "https://heliotime.sunday.wiki/sun?lat=51.5074&lon=-0.1278&date=2025-09-01"
```

### City-based request with date range
```bash
curl "https://heliotime.sunday.wiki/sun?city=Reykjavik&country=Iceland&start_date=2025-06-01&end_date=2025-06-07"
```

### Postal code with custom parameters
```bash
curl "https://heliotime.sunday.wiki/sun?postal_code=W1A%201AA&country_code=GB&date=2025-12-15&elevation_m=35&pressure_hpa=1000&temperature_c=5"
```

## API Documentation

### GET /sun

Calculate sun events for a location and date(s).

#### Location Parameters (choose one)

| Parameter | Type | Description |
|-----------|------|-------------|
| `lat`, `lon` | float | Decimal degrees coordinates |
| `gps` | string | GPS string format: "lat,lon" |
| `postal_code`, `country_code` | string | Postal code with ISO country code |
| `city`, `country` | string | City and country names |

#### Date Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `date` | ISO date | Single date (YYYY-MM-DD) |
| `start_date`, `end_date` | ISO date | Date range (max 366 days) |

If no date is provided, defaults to today in the resolved timezone.

#### Optional Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `elevation_m` | float | 0.0 | Observer elevation in meters |
| `pressure_hpa` | float | 1013.25 | Atmospheric pressure in hectopascals |
| `temperature_c` | float | 15.0 | Temperature in Celsius |
| `tz` | string | auto | Override timezone (IANA ID) |
| `altitude_correction` | bool | false | Apply horizon dip correction |
| `include_twilight` | bool | true | Include twilight times |
| `dev_crosscheck` | bool | false | Force cross-check (dev only) |

#### Response Format

```json
{
  "request": {
    "lat": 51.5074,
    "lon": -0.1278,
    "elevation_m": 35.0,
    "timezone": "Europe/London",
    "date": "2025-09-01",
    "pressure_hpa": 1013.25,
    "temperature_c": 15.0,
    "algorithm": "NREL_SPA_2005"
  },
  "days": [
    {
      "date": "2025-09-01",
      "sunrise": "2025-09-01T06:14:23+01:00",
      "sunset": "2025-09-01T19:43:51+01:00",
      "solar_noon": "2025-09-01T12:59:07+01:00",
      "civil_dawn": "2025-09-01T05:37:10+01:00",
      "civil_dusk": "2025-09-01T20:21:03+01:00",
      "nautical_dawn": "2025-09-01T04:53:00+01:00",
      "nautical_dusk": "2025-09-01T21:05:13+01:00",
      "astronomical_dawn": "2025-09-01T04:05:55+01:00",
      "astronomical_dusk": "2025-09-01T21:52:18+01:00",
      "day_length_sec": 48268,
      "flags": {
        "polar_day": false,
        "polar_night": false,
        "no_civil_twilight": false
      }
    }
  ],
  "meta": {
    "computed_in_ms": 18
  }
}
```

#### Error Responses

| Code | Description |
|------|-------------|
| 400 | Invalid input parameters |
| 404 | Geocoding failed (location not found) |
| 422 | Timezone resolution failed |
| 500 | Internal error or cross-check failure |

### GET /healthz

Health check endpoint.

#### Response
```json
{
  "status": "healthy",
  "service": "HelioTime",
  "version": "1.0.0",
  "environment": "prod",
  "build": {
    "sha": "abc123...",
    "date": "2025-01-08T12:00:00Z"
  }
}
```

## Development

### Local Setup

1. Clone the repository:
```bash
git clone https://github.com/spatializeAR/sunday-heliotime.git
cd sunday-heliotime
```

2. Create virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements-dev.txt
```

4. Run tests:
```bash
pytest tests/ -v --cov=heliotime
```

### Project Structure

```
heliotime/
├── heliotime/           # Lambda function code
│   ├── handler.py       # Lambda handler
│   ├── spa.py          # NREL SPA implementation
│   ├── sun.py          # Sun event calculations
│   ├── geo.py          # Geocoding & timezone
│   └── crosscheck.py   # Dev cross-checking
├── tests/              # Test suite
├── scripts/            # Utility scripts
│   └── check_infrastructure.py
├── docs/               # Documentation
│   └── cdk_provisioning_prompt.md
└── .github/            # CI/CD workflows
    └── workflows/
        └── deploy.yml
```

### CI/CD Pipeline

The project uses GitHub Actions for automated testing and deployment:

- **Pull Requests**: Run tests and linting
- **Push to `dev`**: Deploy to development environment
- **Push to `main`**: Deploy to production environment

### Infrastructure

The service runs on AWS Lambda with:
- API Gateway for HTTP endpoints
- DynamoDB for geocoding cache
- CloudWatch for logs and metrics
- Route53 for DNS management

To check current infrastructure:
```bash
python scripts/check_infrastructure.py
```

To provision missing resources, see `docs/cdk_provisioning_prompt.md`.

## Algorithm Details

### Solar Position Algorithm (SPA)

HelioTime uses the NREL Solar Position Algorithm (2005) which provides:
- Accuracy: ±0.0003° for solar position
- Time accuracy: ±1 second for sunrise/sunset
- Valid for years -2000 to 6000

### Event Definitions

| Event | Solar Altitude |
|-------|---------------|
| Sunrise/Sunset | -0.833° |
| Civil Twilight | -6° |
| Nautical Twilight | -12° |
| Astronomical Twilight | -18° |

### Corrections Applied

1. **Atmospheric Refraction**: Based on pressure and temperature
2. **Solar Disk Size**: 0.533° diameter correction
3. **Horizon Dip**: Optional correction for observer elevation
4. **Time Zone & DST**: Automatic handling for all locations

## Performance

- **Target**: p95 < 100ms for single date
- **Scaling**: Linear with date range
- **Memory**: 256 MB Lambda allocation
- **Timeout**: 5 seconds

## Contributing

1. Create a feature branch from `dev`
2. Make your changes with tests
3. Submit a pull request to `dev`
4. After review and merge to `dev`, changes will auto-deploy
5. Production deployment happens on merge to `main`

## License

Copyright (c) 2025 spatializeAR Organization

## Support

For issues or questions, please open an issue on GitHub or contact the Sunday.wiki team.