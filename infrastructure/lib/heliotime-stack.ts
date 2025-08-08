import * as cdk from 'aws-cdk-lib';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as apigateway from 'aws-cdk-lib/aws-apigateway';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as route53 from 'aws-cdk-lib/aws-route53';
import * as route53Targets from 'aws-cdk-lib/aws-route53-targets';
import * as acm from 'aws-cdk-lib/aws-certificatemanager';
import * as cloudwatch from 'aws-cdk-lib/aws-cloudwatch';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as ssm from 'aws-cdk-lib/aws-ssm';
import * as path from 'path';
import { Construct } from 'constructs';
import { SharedResourcesStack } from './shared-resources-stack';

export interface HelioTimeStackProps extends cdk.StackProps {
  environment: 'dev' | 'prod';
  domainName: string;
  sharedResourcesStack: SharedResourcesStack;
}

export class HelioTimeStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: HelioTimeStackProps) {
    super(scope, id, props);

    const { environment, domainName, sharedResourcesStack } = props;

    // DynamoDB table for geocoding cache
    const geoCacheTable = new dynamodb.Table(this, 'GeoCacheTable', {
      tableName: `heliotime-geocache-${environment}`,
      partitionKey: {
        name: 'query_hash',
        type: dynamodb.AttributeType.STRING,
      },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      timeToLiveAttribute: 'expires_at',
      pointInTimeRecovery: true,
      removalPolicy: environment === 'prod' 
        ? cdk.RemovalPolicy.RETAIN 
        : cdk.RemovalPolicy.DESTROY,
      encryption: dynamodb.TableEncryption.CUSTOMER_MANAGED,
      encryptionKey: sharedResourcesStack.encryptionKey,
    });

    // Add GSI for location lookups
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

    // Lambda execution role
    const lambdaRole = new iam.Role(this, 'LambdaExecutionRole', {
      roleName: `heliotime-lambda-role-${environment}`,
      assumedBy: new iam.ServicePrincipal('lambda.amazonaws.com'),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AWSLambdaBasicExecutionRole'),
      ],
    });

    // Add permissions for DynamoDB
    geoCacheTable.grantReadWriteData(lambdaRole);

    // Add permissions for KMS
    sharedResourcesStack.encryptionKey.grantDecrypt(lambdaRole);

    // Add permissions for Secrets Manager
    sharedResourcesStack.geocoderApiKeySecret.grantRead(lambdaRole);

    // Add permissions for SSM Parameter Store
    lambdaRole.addToPolicy(new iam.PolicyStatement({
      actions: ['ssm:GetParameter', 'ssm:GetParameters'],
      resources: [`arn:aws:ssm:${this.region}:${this.account}:parameter/sunday/services/heliotime/*`],
    }));

    // Add X-Ray permissions
    lambdaRole.addToPolicy(new iam.PolicyStatement({
      actions: ['xray:PutTraceSegments', 'xray:PutTelemetryRecords'],
      resources: ['*'],
    }));

    // Lambda function
    const helioTimeLambda = new lambda.Function(this, 'HelioTimeFunction', {
      functionName: `heliotime-${environment}`,
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: 'handler.lambda_handler',
      code: lambda.Code.fromAsset(path.join(__dirname, '../../heliotime')),
      memorySize: 256,
      timeout: cdk.Duration.seconds(5),
      role: lambdaRole,
      tracing: lambda.Tracing.ACTIVE,
      logRetention: logs.RetentionDays.ONE_MONTH,
      environment: {
        ENV: environment,
        DYNAMODB_TABLE: geoCacheTable.tableName,
        KMS_KEY_ID: sharedResourcesStack.encryptionKey.keyId,
        GEOCODER_SECRET_ARN: sharedResourcesStack.geocoderApiKeySecret.secretArn,
        DEV_CROSSCHECK: environment === 'dev' ? 'true' : 'false',
        DEV_CROSSCHECK_PROVIDER: 'open-meteo',
        DEV_CROSSCHECK_TOLERANCE_SECONDS: '120',
        DEV_CROSSCHECK_ENFORCE: 'false',
        GEOCODER: 'nominatim',
        GEOCODER_BASE_URL: 'https://nominatim.openstreetmap.org',
        CACHE_TTL_SECONDS: '7776000',
        MAX_RANGE_DAYS: '366',
        LOG_LEVEL: environment === 'dev' ? 'DEBUG' : 'INFO',
        BUILD_SHA: process.env.GITHUB_SHA || 'local',
        BUILD_DATE: new Date().toISOString(),
      },
    });

    // API Gateway
    const api = new apigateway.RestApi(this, 'HelioTimeApi', {
      restApiName: `heliotime-api-${environment}`,
      description: `HelioTime API - ${environment}`,
      deployOptions: {
        stageName: environment,
        loggingLevel: apigateway.MethodLoggingLevel.INFO,
        dataTraceEnabled: environment === 'dev',
        metricsEnabled: true,
        tracingEnabled: true,
        throttlingBurstLimit: 100,
        throttlingRateLimit: 50,
      },
      defaultCorsPreflightOptions: {
        allowOrigins: apigateway.Cors.ALL_ORIGINS,
        allowMethods: apigateway.Cors.ALL_METHODS,
        allowHeaders: ['Content-Type', 'X-Amz-Date', 'Authorization', 'X-Api-Key'],
      },
    });

    // Lambda integration
    const lambdaIntegration = new apigateway.LambdaIntegration(helioTimeLambda, {
      requestTemplates: { 'application/json': '{ "statusCode": 200 }' },
    });

    // API resources and methods
    const sunResource = api.root.addResource('sun');
    sunResource.addMethod('GET', lambdaIntegration, {
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
        'method.request.querystring.elevation_m': false,
        'method.request.querystring.pressure_hpa': false,
        'method.request.querystring.temperature_c': false,
        'method.request.querystring.tz': false,
        'method.request.querystring.altitude_correction': false,
        'method.request.querystring.include_twilight': false,
        'method.request.querystring.dev_crosscheck': false,
      },
    });

    const healthResource = api.root.addResource('healthz');
    healthResource.addMethod('GET', lambdaIntegration);

    // Custom domain (assuming certificate exists)
    // Note: You'll need to create or import the certificate
    const hostedZone = route53.HostedZone.fromLookup(this, 'HostedZone', {
      domainName: 'sunday.wiki',
    });

    // For now, we'll create a CNAME record pointing to the API Gateway endpoint
    // In production, you'd want to use a custom domain with certificate
    new route53.CnameRecord(this, 'ApiCnameRecord', {
      zone: hostedZone,
      recordName: domainName.replace('.sunday.wiki', ''),
      domainName: api.url.replace('https://', '').replace(/\/$/, ''),
      ttl: cdk.Duration.minutes(5),
    });

    // CloudWatch Alarms
    new cloudwatch.Alarm(this, 'LambdaErrorAlarm', {
      metric: helioTimeLambda.metricErrors(),
      threshold: 10,
      evaluationPeriods: 2,
      treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
      alarmDescription: `High error rate for HelioTime Lambda - ${environment}`,
    });

    new cloudwatch.Alarm(this, 'LambdaDurationAlarm', {
      metric: helioTimeLambda.metricDuration(),
      threshold: 3000,
      evaluationPeriods: 2,
      treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
      alarmDescription: `High latency for HelioTime Lambda - ${environment}`,
    });

    new cloudwatch.Alarm(this, 'LambdaThrottleAlarm', {
      metric: helioTimeLambda.metricThrottles(),
      threshold: 5,
      evaluationPeriods: 1,
      treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
      alarmDescription: `Throttling detected for HelioTime Lambda - ${environment}`,
    });

    // Store deployment information in SSM
    new ssm.StringParameter(this, 'LambdaArnParam', {
      parameterName: `/sunday/services/heliotime/${environment}/lambda-arn`,
      stringValue: helioTimeLambda.functionArn,
      description: `HelioTime Lambda ARN - ${environment}`,
    });

    new ssm.StringParameter(this, 'ApiEndpointParam', {
      parameterName: `/sunday/services/heliotime/${environment}/api-endpoint`,
      stringValue: api.url,
      description: `HelioTime API endpoint - ${environment}`,
    });

    new ssm.StringParameter(this, 'ApiIdParam', {
      parameterName: `/sunday/services/heliotime/${environment}/api-id`,
      stringValue: api.restApiId,
      description: `HelioTime API Gateway ID - ${environment}`,
    });

    new ssm.StringParameter(this, 'DynamoTableParam', {
      parameterName: `/sunday/services/heliotime/${environment}/dynamodb-table`,
      stringValue: geoCacheTable.tableName,
      description: `HelioTime DynamoDB table name - ${environment}`,
    });

    new ssm.StringParameter(this, 'DomainNameParam', {
      parameterName: `/sunday/services/heliotime/${environment}/domain`,
      stringValue: domainName,
      description: `HelioTime domain name - ${environment}`,
    });

    new ssm.StringParameter(this, 'DeploymentTimestampParam', {
      parameterName: `/sunday/services/heliotime/${environment}/last-deployment`,
      stringValue: new Date().toISOString(),
      description: `Last deployment timestamp - ${environment}`,
    });

    // Outputs
    new cdk.CfnOutput(this, 'ApiEndpoint', {
      value: api.url,
      description: `API endpoint URL - ${environment}`,
      exportName: `heliotime-api-endpoint-${environment}`,
    });

    new cdk.CfnOutput(this, 'LambdaArn', {
      value: helioTimeLambda.functionArn,
      description: `Lambda function ARN - ${environment}`,
      exportName: `heliotime-lambda-arn-${environment}`,
    });

    new cdk.CfnOutput(this, 'DynamoTableName', {
      value: geoCacheTable.tableName,
      description: `DynamoDB table name - ${environment}`,
      exportName: `heliotime-dynamodb-table-${environment}`,
    });

    new cdk.CfnOutput(this, 'CustomDomain', {
      value: `https://${domainName}`,
      description: `Custom domain URL - ${environment}`,
      exportName: `heliotime-domain-${environment}`,
    });
  }
}