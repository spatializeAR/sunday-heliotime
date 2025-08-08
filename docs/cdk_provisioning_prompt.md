# CDK Provisioning Prompt for HelioTime Infrastructure

## Context
You are updating an AWS CDK application that manages infrastructure for the Sunday.wiki platform. The HelioTime service requires the following AWS resources to be provisioned or updated.

## Current Infrastructure Status
Run `python scripts/check_infrastructure.py` to generate `infrastructure_report.json` with the current state.

## Required CDK Updates

### 1. API Gateway Configuration
```typescript
// Required: REST API with custom domain
const api = new apigateway.RestApi(this, 'HelioTimeApi', {
  restApiName: 'heliotime-api',
  description: 'HelioTime sunrise/sunset calculation API',
  deployOptions: {
    stageName: props.environment, // 'dev' or 'prod'
    loggingLevel: apigateway.MethodLoggingLevel.INFO,
    dataTraceEnabled: true,
    metricsEnabled: true,
  },
  defaultCorsPreflightOptions: {
    allowOrigins: apigateway.Cors.ALL_ORIGINS,
    allowMethods: apigateway.Cors.ALL_METHODS,
  },
});

// Custom domain mapping
const domainName = new apigateway.DomainName(this, 'HelioTimeDomain', {
  domainName: 'heliotime.dev.sunday.wiki',
  certificate: certificate, // Use existing ACM certificate for *.sunday.wiki
  endpointType: apigateway.EndpointType.EDGE,
});

new apigateway.BasePathMapping(this, 'HelioTimeMapping', {
  domainName: domainName,
  restApi: api,
  basePath: '', // Root path
});
```

### 2. Lambda Functions (Dev and Prod)
```typescript
// Shared Lambda configuration
const lambdaConfig = {
  runtime: lambda.Runtime.PYTHON_3_12,
  handler: 'handler.lambda_handler',
  code: lambda.Code.fromAsset('../heliotime'), // Path to Lambda code
  memorySize: 256,
  timeout: cdk.Duration.seconds(5),
  environment: {
    ENV: props.environment,
    DEV_CROSSCHECK: props.environment === 'dev' ? 'true' : 'false',
    DEV_CROSSCHECK_PROVIDER: 'open-meteo',
    DEV_CROSSCHECK_TOLERANCE_SECONDS: '120',
    GEOCODER: 'nominatim',
    CACHE_TTL_SECONDS: '7776000',
    MAX_RANGE_DAYS: '366',
    LOG_LEVEL: props.environment === 'dev' ? 'DEBUG' : 'INFO',
  },
};

const helioTimeLambda = new lambda.Function(this, `HelioTime${props.environment}Function`, {
  functionName: `heliotime-${props.environment}`,
  ...lambdaConfig,
  role: lambdaExecutionRole, // See IAM section
});

// Grant DynamoDB permissions
geoCacheTable.grantReadWriteData(helioTimeLambda);
```

### 3. DynamoDB Table for Geocoding Cache
```typescript
const geoCacheTable = new dynamodb.Table(this, 'HelioTimeGeoCache', {
  tableName: 'heliotime-geocache',
  partitionKey: {
    name: 'query_hash',
    type: dynamodb.AttributeType.STRING,
  },
  billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
  timeToLiveAttribute: 'expires_at',
  pointInTimeRecovery: true,
  removalPolicy: cdk.RemovalPolicy.RETAIN, // Keep data on stack deletion
});

// Add GSI for location lookups if needed
geoCacheTable.addGlobalSecondaryIndex({
  indexName: 'location-index',
  partitionKey: {
    name: 'location_type',
    type: dynamodb.AttributeType.STRING,
  },
  sortKey: {
    name: 'location_key',
    type: dynamodb.AttributeType.STRING,
  },
});
```

### 4. IAM Role and Policies
```typescript
const lambdaExecutionRole = new iam.Role(this, 'HelioTimeLambdaRole', {
  roleName: 'heliotime-lambda-execution-role',
  assumedBy: new iam.ServicePrincipal('lambda.amazonaws.com'),
  managedPolicies: [
    iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AWSLambdaBasicExecutionRole'),
  ],
  inlinePolicies: {
    HelioTimePolicy: new iam.PolicyDocument({
      statements: [
        new iam.PolicyStatement({
          actions: ['logs:CreateLogGroup', 'logs:CreateLogStream', 'logs:PutLogEvents'],
          resources: [`arn:aws:logs:${this.region}:${this.account}:*`],
        }),
        new iam.PolicyStatement({
          actions: ['xray:PutTraceSegments', 'xray:PutTelemetryRecords'],
          resources: ['*'],
        }),
      ],
    }),
  },
});
```

### 5. Route53 Configuration
```typescript
// Assuming hosted zone exists for sunday.wiki
const hostedZone = route53.HostedZone.fromLookup(this, 'SundayZone', {
  domainName: 'sunday.wiki',
});

new route53.ARecord(this, 'HelioTimeSubdomain', {
  zone: hostedZone,
  recordName: 'heliotime.dev',
  target: route53.RecordTarget.fromAlias(new targets.ApiGatewayDomain(domainName)),
  ttl: cdk.Duration.minutes(5),
});
```

### 6. API Gateway Integration
```typescript
// Create API resources and methods
const sunResource = api.root.addResource('sun');
const healthResource = api.root.addResource('healthz');

// GET /sun endpoint
sunResource.addMethod('GET', new apigateway.LambdaIntegration(helioTimeLambda, {
  requestTemplates: { 'application/json': '{ "statusCode": 200 }' },
}), {
  requestParameters: {
    'method.request.querystring.lat': false,
    'method.request.querystring.lon': false,
    'method.request.querystring.gps': false,
    'method.request.querystring.postal_code': false,
    'method.request.querystring.country_code': false,
    'method.request.querystring.city': false,
    'method.request.querystring.country': false,
    'method.request.querystring.date': false,
    'method.request.querystring.start_date': false,
    'method.request.querystring.end_date': false,
    'method.request.querystring.pressure_hpa': false,
    'method.request.querystring.temperature_c': false,
    'method.request.querystring.tz': false,
    'method.request.querystring.altitude_correction': false,
    'method.request.querystring.include_twilight': false,
    'method.request.querystring.dev_crosscheck': false,
  },
});

// GET /healthz endpoint
healthResource.addMethod('GET', new apigateway.LambdaIntegration(helioTimeLambda));
```

### 7. CloudWatch Alarms
```typescript
new cloudwatch.Alarm(this, 'HelioTimeLambdaErrors', {
  metric: helioTimeLambda.metricErrors(),
  threshold: 10,
  evaluationPeriods: 2,
  alarmDescription: 'Alert when HelioTime Lambda has errors',
});

new cloudwatch.Alarm(this, 'HelioTimeLambdaDuration', {
  metric: helioTimeLambda.metricDuration(),
  threshold: 3000, // 3 seconds
  evaluationPeriods: 2,
  alarmDescription: 'Alert when HelioTime Lambda is slow',
});
```

### 8. Secrets Manager (Optional - for API keys)
```typescript
// Only if using paid geocoding services
const geocoderSecret = new secretsmanager.Secret(this, 'HelioTimeGeocoderKey', {
  secretName: 'heliotime/geocoder-api-key',
  description: 'API key for geocoding service (Google/Mapbox)',
  generateSecretString: {
    secretStringTemplate: JSON.stringify({ provider: 'google' }),
    generateStringKey: 'api_key',
    excludeCharacters: ' %+~`#$&*()|[]{}:;<>?!\'/@"\\',
  },
});

// Grant Lambda permission to read secret
geocoderSecret.grantRead(helioTimeLambda);
```

## Deployment Strategy

### Environment Separation
- **Dev Stack**: `heliotime-dev` - deployed from `dev` branch
- **Prod Stack**: `heliotime-prod` - deployed from `main` branch

### Stack Parameters
```typescript
interface HelioTimeStackProps extends cdk.StackProps {
  environment: 'dev' | 'prod';
  certificateArn: string; // ACM certificate for *.sunday.wiki
  vpcId?: string; // Optional VPC if needed
}
```

### CDK Deploy Commands
```bash
# Deploy dev environment
cdk deploy HelioTimeDevStack --profile SundayDev

# Deploy prod environment  
cdk deploy HelioTimeProdStack --profile SundayDev
```

## Post-Deployment Verification
1. Test API endpoints:
   - `https://heliotime.dev.sunday.wiki/healthz`
   - `https://heliotime.dev.sunday.wiki/sun?lat=51.5074&lon=-0.1278&date=2025-09-01`

2. Verify CloudWatch logs are being created

3. Check DynamoDB table is accessible

4. Validate Route53 DNS resolution

## Notes
- Ensure the CDK app has proper environment configuration for both dev and prod
- Lambda deployment package should be built before CDK deploy
- Consider using CDK Pipelines for automated deployments
- Tag all resources appropriately for cost tracking