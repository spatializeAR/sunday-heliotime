# HelioTime CDK Infrastructure (Python)

This directory contains the AWS CDK (Cloud Development Kit) application written in Python that manages all infrastructure for the HelioTime service.

## Architecture Overview

The infrastructure is organized into three CDK stacks:

### 1. Shared Resources Stack (`HelioTimeSharedStack`)
Contains resources shared across all environments:
- **KMS Key**: Encryption key for all HelioTime resources
- **Secrets Manager**: Storage for API keys (future use)
- **SSM Parameters**: Service configuration and discovery information

### 2. Development Stack (`HelioTimeDevStack`)
Development environment resources:
- Lambda function (`heliotime-dev`)
- API Gateway with dev stage
- DynamoDB table for geocaching
- CloudWatch alarms and logs
- Environment-specific SSM parameters

### 3. Production Stack (`HelioTimeProdStack`)
Production environment resources (similar to dev but with production settings):
- Lambda function (`heliotime-prod`)
- API Gateway with prod stage
- DynamoDB table with retention policy
- Enhanced monitoring and alarms
- Production SSM parameters

## Service Discovery

The infrastructure publishes configuration to SSM Parameter Store, enabling service discovery:

### Shared Parameters
```
/sunday/services/heliotime/name                    # Service name
/sunday/services/heliotime/version                 # Version
/sunday/services/heliotime/description             # Description
/sunday/services/heliotime/kms-key-arn            # KMS key ARN
/sunday/services/heliotime/algorithm              # Algorithm (NREL_SPA_2005)
/sunday/services/heliotime/limits/max-range-days  # Max date range
/sunday/services/heliotime/cache/ttl-seconds      # Cache TTL
```

### Environment-Specific Parameters
```
/sunday/services/heliotime/{env}/lambda-arn       # Lambda function ARN
/sunday/services/heliotime/{env}/api-endpoint     # API Gateway endpoint
/sunday/services/heliotime/{env}/api-id          # API Gateway ID
/sunday/services/heliotime/{env}/dynamodb-table  # DynamoDB table name
/sunday/services/heliotime/{env}/domain          # Custom domain
/sunday/services/heliotime/{env}/last-deployment # Deployment timestamp
```

## Prerequisites

1. **Python 3.8+** (3.12 recommended)
2. **Node.js** (for AWS CDK CLI)
3. **AWS CDK CLI** (`npm install -g aws-cdk`)
4. **AWS credentials** configured

## Installation

### Automated Setup
```bash
# Run the setup script
python3 setup.py
```

### Manual Setup
```bash
# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install CDK CLI (if not installed)
npm install -g aws-cdk
```

## Configuration

The CDK app uses context values from `cdk.json`:
- `sunday:organization`: spatializeAR
- `sunday:service`: heliotime
- `sunday:domain`: sunday.wiki

## Deployment

### First Time Setup

1. Bootstrap CDK (one-time per account/region):
```bash
cdk bootstrap aws://ACCOUNT-ID/us-east-1 --profile SundayDev
```

2. Deploy stacks:
```bash
# Activate virtual environment
source .venv/bin/activate

# Deploy shared resources
cdk deploy HelioTimeSharedStack --profile SundayDev

# Deploy development
cdk deploy HelioTimeDevStack --profile SundayDev

# Deploy production (with confirmation)
cdk deploy HelioTimeProdStack --profile SundayDev
```

### Using Makefile (Recommended)

```bash
# Install and setup
make cdk-install

# Preview changes
make cdk-diff

# Deploy to development
make deploy-dev

# Deploy to production
make deploy-prod
```

### Using Deployment Script

```bash
# Deploy everything to dev
../scripts/deploy.sh deploy-all dev

# Deploy infrastructure only
../scripts/deploy.sh deploy-infra dev

# Deploy Lambda code only
../scripts/deploy.sh deploy-code dev

# Test deployment
../scripts/deploy.sh test dev
```

## CDK Commands

```bash
# Activate virtual environment first
source .venv/bin/activate

# List all stacks
cdk list

# Synthesize CloudFormation templates
cdk synth

# Show differences between deployed and local
cdk diff --all

# Deploy specific stack
cdk deploy HelioTimeDevStack

# Deploy all stacks
cdk deploy --all

# Destroy stack (BE CAREFUL!)
cdk destroy HelioTimeDevStack
```

## Stack Outputs

Each stack exports important values:

### Shared Stack
- `heliotime-kms-key-id`: KMS key ID
- `heliotime-geocoder-secret-arn`: Secret ARN

### Environment Stacks
- `heliotime-api-endpoint-{env}`: API endpoint URL
- `heliotime-lambda-arn-{env}`: Lambda function ARN
- `heliotime-dynamodb-table-{env}`: DynamoDB table name
- `heliotime-domain-{env}`: Custom domain URL

## Project Structure

```
infrastructure/
├── app.py                 # CDK app entry point
├── cdk.json              # CDK configuration
├── requirements.txt      # Python dependencies
├── setup.py             # Setup script
├── stacks/
│   ├── __init__.py
│   ├── shared_resources_stack.py  # Shared resources
│   └── heliotime_stack.py        # Main application stack
└── cdk.out/             # CDK output (gitignored)
```

## Integration with Other Services

Other Sunday.wiki services can discover HelioTime using boto3:

```python
import boto3

ssm = boto3.client('ssm')

# Get API endpoint
response = ssm.get_parameter(
    Name='/sunday/services/heliotime/prod/api-endpoint'
)
api_endpoint = response['Parameter']['Value']

# Get KMS key for encryption
response = ssm.get_parameter(
    Name='/sunday/services/heliotime/kms-key-arn'
)
kms_key_arn = response['Parameter']['Value']

# Get DynamoDB table
response = ssm.get_parameter(
    Name='/sunday/services/heliotime/prod/dynamodb-table'
)
table_name = response['Parameter']['Value']
```

## Cost Optimization

The infrastructure is designed for cost efficiency:
- **Lambda**: 256MB memory, pay-per-use
- **DynamoDB**: On-demand billing
- **API Gateway**: Pay-per-request
- **CloudWatch**: 1-month log retention
- **KMS**: Shared key across environments

Estimated costs:
- Low traffic (< 10K requests/month): < $10/month
- Medium traffic (100K requests/month): ~$20-30/month
- High traffic (1M requests/month): ~$50-100/month

## Monitoring

CloudWatch alarms monitor:
- Lambda errors (> 10 errors in 2 periods)
- Lambda duration (> 3 seconds)
- Lambda throttles (> 5 throttles)

Logs available at:
- `/aws/lambda/heliotime-dev`
- `/aws/lambda/heliotime-prod`

## Security

- **Encryption**: All data encrypted with KMS
- **IAM**: Least privilege access policies
- **Secrets**: Managed through Secrets Manager
- **API**: Throttling enabled (50 req/s, burst: 100)

## Troubleshooting

### Virtual Environment Issues
```bash
# Recreate virtual environment
rm -rf .venv
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### CDK Bootstrap Issues
```bash
# Re-run bootstrap with verbose output
cdk bootstrap --profile SundayDev --debug
```

### Stack Rollback
```bash
# Check CloudFormation events
aws cloudformation describe-stack-events \
  --stack-name heliotime-dev \
  --profile SundayDev
```

### SSM Parameter Access
```bash
# List all HelioTime parameters
aws ssm get-parameters-by-path \
  --path /sunday/services/heliotime \
  --recursive \
  --profile SundayDev
```

## Development Workflow

1. Make infrastructure changes in `stacks/` directory
2. Activate virtual environment: `source .venv/bin/activate`
3. Synthesize to verify: `cdk synth`
4. Preview changes: `cdk diff`
5. Deploy to dev: `cdk deploy HelioTimeDevStack`
6. Test thoroughly
7. Deploy to prod: `cdk deploy HelioTimeProdStack`

## Python CDK Best Practices

1. **Type Hints**: Use type hints for better IDE support
2. **Stack Separation**: Keep shared and environment-specific resources separate
3. **Parameter Store**: Use SSM for configuration that other services need
4. **Tags**: Apply consistent tags for cost tracking
5. **Removal Policy**: Use RETAIN for production resources

## CI/CD Integration

GitHub Actions automatically:
1. Tests Python Lambda code
2. Builds deployment package
3. Deploys CDK stacks based on branch
4. Updates Lambda code
5. Runs integration tests
6. Updates SSM deployment timestamp

## Future Enhancements

- [ ] Custom domain with ACM certificate
- [ ] API key authentication
- [ ] VPC configuration (if needed)
- [ ] Multi-region deployment
- [ ] Blue/green deployments
- [ ] Canary deployments
- [ ] Enhanced X-Ray tracing