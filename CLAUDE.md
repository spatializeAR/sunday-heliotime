# HelioTime Development Guide

## Project Overview
HelioTime is a deterministic sunrise/sunset calculation service using the NREL Solar Position Algorithm. It runs on AWS Lambda and provides high-accuracy solar event calculations with automatic timezone handling.

## Key Commands

### Testing
```bash
make test           # Run full test suite
pytest tests/test_spa_vectors.py -v  # Test SPA calculations
```

### Linting & Formatting
```bash
make lint          # Check code style
make format        # Auto-format code with black
```

### Deployment
```bash
make check-infra   # Check AWS infrastructure status
make build         # Build Lambda deployment package
make deploy-dev    # Deploy to development (requires AWS creds)
make deploy-prod   # Deploy to production (requires AWS creds)
```

## Architecture

### Core Components
- `spa.py`: NREL Solar Position Algorithm implementation
- `sun.py`: High-level sun event calculations
- `geo.py`: Geocoding and timezone resolution
- `handler.py`: Lambda handler for API endpoints
- `crosscheck.py`: Development cross-checking

### AWS Resources Required
- Lambda functions: `heliotime-dev`, `heliotime-prod`
- API Gateway: `heliotime-api`
- DynamoDB table: `heliotime-geocache`
- Route53: `heliotime.dev.sunday.wiki`, `heliotime.sunday.wiki`

## Development Workflow

1. **Feature Development**
   - Create feature branch from `dev`
   - Make changes with tests
   - PR to `dev` branch

2. **Testing**
   - All PRs trigger automated tests
   - Cross-check validation in dev environment
   - Manual testing at https://heliotime.dev.sunday.wiki

3. **Deployment**
   - Push to `dev` → auto-deploy to development
   - Push to `main` → auto-deploy to production
   - GitHub Actions handles CI/CD

## Important Notes

### Accuracy
- SPA algorithm accuracy: ±0.0003° for position, ±1 second for times
- Cross-check tolerance: 120 seconds (configurable)
- Polar cases handled with special flags

### Performance
- Target: p95 < 100ms for single date
- Lambda: 256 MB memory, 5 second timeout
- DynamoDB cache: 90 day TTL

### Environment Variables
```
ENV=dev|prod
DEV_CROSSCHECK=true|false
DEV_CROSSCHECK_PROVIDER=open-meteo
DEV_CROSSCHECK_TOLERANCE_SECONDS=120
GEOCODER=nominatim
CACHE_TTL_SECONDS=7776000
MAX_RANGE_DAYS=366
LOG_LEVEL=INFO|DEBUG
```

## Common Tasks

### Add New Twilight Type
1. Add altitude threshold to `ALTITUDES` dict in `sun.py`
2. Add event calculation in `sun_events_for_date()`
3. Update response format in handler
4. Add tests for new twilight type

### Change Geocoding Provider
1. Implement provider function in `geo.py`
2. Update `GEOCODER` environment variable
3. Add API key to AWS Secrets Manager if needed

### Update SPA Algorithm
1. Modify calculations in `spa.py`
2. Validate against NREL test vectors
3. Run cross-check tests against external APIs

## Troubleshooting

### Infrastructure Issues
```bash
python scripts/check_infrastructure.py
# Review infrastructure_report.json
# Use docs/cdk_provisioning_prompt.md to provision missing resources
```

### Failed Cross-Checks
- Check `DEV_CROSSCHECK_TOLERANCE_SECONDS`
- Verify external API is responding
- Compare calculations manually

### Timezone Errors
- Update `timezonefinder` package
- Check coordinates are valid
- Verify IANA timezone database

## Testing Locations

### Standard Cases
- London: 51.5074, -0.1278
- New York: 40.7128, -74.0060
- Tokyo: 35.6762, 139.6503

### Edge Cases
- Svalbard (polar): 78.2232, 15.6267
- Reykjavik (high lat): 64.1466, -21.9426
- Singapore (equator): 1.3521, 103.8198

## API Testing

### Quick Tests
```bash
# Health check
curl https://heliotime.dev.sunday.wiki/healthz

# Single date
curl "https://heliotime.dev.sunday.wiki/sun?lat=51.5074&lon=-0.1278&date=2025-09-01"

# Date range
curl "https://heliotime.dev.sunday.wiki/sun?city=Reykjavik&country=Iceland&start_date=2025-06-01&end_date=2025-06-07"

# With cross-check (dev only)
curl "https://heliotime.dev.sunday.wiki/sun?lat=40.7128&lon=-74.0060&date=2025-03-20&dev_crosscheck=true"
```

## Monitoring

- CloudWatch Logs: `/aws/lambda/heliotime-{env}`
- Metrics: Lambda invocations, errors, duration
- Alarms: Error rate > 1%, duration > 3s

## Contact

- GitHub Issues: https://github.com/spatializeAR/sunday-heliotime/issues
- Sunday.wiki Team: For production issues