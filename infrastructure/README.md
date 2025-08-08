# HelioTime CDK Infrastructure

This directory contains the AWS CDK (Cloud Development Kit) application that manages all infrastructure for the HelioTime service.

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
- `/sunday/services/heliotime/name` - Service name
- `/sunday/services/heliotime/version` - Version
- `/sunday/services/heliotime/description` - Description
- `/sunday/services/heliotime/kms-key-arn` - KMS key ARN
- `/sunday/services/heliotime/algorithm` - Algorithm used (NREL_SPA_2005)
- `/sunday/services/heliotime/limits/max-range-days` - Max date range
- `/sunday/services/heliotime/cache/ttl-seconds` - Cache TTL

### Environment-Specific Parameters
- `/sunday/services/heliotime/{env}/lambda-arn` - Lambda function ARN
- `/sunday/services/heliotime/{env}/api-endpoint` - API Gateway endpoint
- `/sunday/services/heliotime/{env}/api-id` - API Gateway ID
- `/sunday/services/heliotime/{env}/dynamodb-table` - DynamoDB table name
- `/sunday/services/heliotime/{env}/domain` - Custom domain
- `/sunday/services/heliotime/{env}/last-deployment` - Deployment timestamp

## Prerequisites

1. **Node.js** (v18 or later)
2. **AWS CDK CLI**
3. **AWS credentials** configured
4. **Python 3.12** (for Lambda runtime)

## Installation

```bash
# Install dependencies
npm install

# Install CDK globally (if not already installed)
npm install -g aws-cdk

# Verify installation
cdk --version
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

2. Deploy shared resources:
```bash
cdk deploy HelioTimeSharedStack --profile SundayDev
```

3. Deploy environment stack:
```bash
# Development
cdk deploy HelioTimeDevStack --profile SundayDev

# Production
cdk deploy HelioTimeProdStack --profile SundayDev
```

### Subsequent Deployments

```bash
# Preview changes
cdk diff --all --profile SundayDev

# Deploy all stacks
cdk deploy --all --profile SundayDev

# Deploy specific stack
cdk deploy HelioTimeDevStack --profile SundayDev
```

### Using Deployment Script

The easiest way to deploy is using the provided script:

```bash
# Deploy everything to dev
../scripts/deploy.sh deploy-all dev

# Deploy infrastructure only
../scripts/deploy.sh deploy-infra dev

# Deploy Lambda code only
../scripts/deploy.sh deploy-code dev
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

## Resource Naming Convention

All resources follow this naming pattern:
- `heliotime-{resource}-{environment}`
- Examples:
  - `heliotime-lambda-dev`
  - `heliotime-geocache-prod`
  - `heliotime-api-dev`

## Cost Optimization

The infrastructure is designed for cost efficiency:
- **Lambda**: 256MB memory, pay-per-use
- **DynamoDB**: On-demand billing (no reserved capacity)
- **API Gateway**: Pay-per-request
- **CloudWatch**: 1-month log retention
- **KMS**: Shared key across environments

Estimated monthly cost (low traffic): < $10
Estimated monthly cost (1M requests): ~$50-100

## Monitoring

CloudWatch alarms are configured for:
- Lambda errors (threshold: 10 errors in 2 periods)
- Lambda duration (threshold: 3 seconds)
- Lambda throttles (threshold: 5 throttles)

Logs are available at:
- `/aws/lambda/heliotime-dev`
- `/aws/lambda/heliotime-prod`

## Security

- **Encryption**: All data encrypted with KMS
- **IAM**: Least privilege access policies
- **Secrets**: Managed through Secrets Manager
- **Network**: Public Lambda (no VPC for cost savings)
- **API**: Throttling enabled (50 req/s burst: 100)

## Troubleshooting

### CDK Bootstrap Issues
```bash
# Re-run bootstrap with verbose output
cdk bootstrap --profile SundayDev --debug
```

### Stack Rollback
```bash
# Check stack events
aws cloudformation describe-stack-events \
  --stack-name heliotime-dev \
  --profile SundayDev
```

### Parameter Store Access
```bash
# List all HelioTime parameters
aws ssm get-parameters-by-path \
  --path /sunday/services/heliotime \
  --recursive \
  --profile SundayDev
```

### Manual Stack Deletion
```bash
# Delete stack (BE CAREFUL!)
cdk destroy HelioTimeDevStack --profile SundayDev
```

## Integration with Other Services

Other Sunday.wiki services can discover HelioTime by:

1. Reading SSM parameters:
```python
import boto3

ssm = boto3.client('ssm')
response = ssm.get_parameter(
    Name='/sunday/services/heliotime/dev/api-endpoint'
)
api_endpoint = response['Parameter']['Value']
```

2. Using the KMS key for encryption:
```python
response = ssm.get_parameter(
    Name='/sunday/services/heliotime/kms-key-arn'
)
kms_key_arn = response['Parameter']['Value']
```

3. Accessing the DynamoDB table:
```python
response = ssm.get_parameter(
    Name='/sunday/services/heliotime/dev/dynamodb-table'
)
table_name = response['Parameter']['Value']
```

## Development Workflow

1. Make infrastructure changes in `lib/` directory
2. Build TypeScript: `npm run build`
3. Synthesize to verify: `cdk synth`
4. Preview changes: `cdk diff`
5. Deploy to dev: `cdk deploy HelioTimeDevStack`
6. Test thoroughly
7. Deploy to prod: `cdk deploy HelioTimeProdStack`

## CI/CD Integration

The GitHub Actions workflow automatically:
1. Builds and tests Lambda code
2. Deploys shared stack (if needed)
3. Deploys environment stack based on branch
4. Updates Lambda code
5. Updates SSM deployment timestamp
6. Runs integration tests

## Future Enhancements

- [ ] Custom domain with ACM certificate
- [ ] API key authentication option
- [ ] VPC configuration (if needed)
- [ ] Multi-region deployment
- [ ] Blue/green deployments
- [ ] Canary deployments
- [ ] X-Ray tracing enhancements
- [ ] Cost allocation tags