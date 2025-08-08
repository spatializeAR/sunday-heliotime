import * as cdk from 'aws-cdk-lib';
import * as kms from 'aws-cdk-lib/aws-kms';
import * as ssm from 'aws-cdk-lib/aws-ssm';
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';
import { Construct } from 'constructs';

export class SharedResourcesStack extends cdk.Stack {
  public readonly encryptionKey: kms.Key;
  public readonly geocoderApiKeySecret: secretsmanager.Secret;
  
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // Create KMS key for encryption
    this.encryptionKey = new kms.Key(this, 'HelioTimeEncryptionKey', {
      description: 'KMS key for HelioTime service encryption',
      alias: 'heliotime/encryption',
      enableKeyRotation: true,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
    });

    // Create secret for geocoder API keys (if needed in future)
    this.geocoderApiKeySecret = new secretsmanager.Secret(this, 'GeocoderApiKey', {
      secretName: 'heliotime/geocoder-api-key',
      description: 'API keys for geocoding services (Google/Mapbox)',
      generateSecretString: {
        secretStringTemplate: JSON.stringify({
          provider: 'nominatim',
          note: 'Currently using free Nominatim, no API key required'
        }),
        generateStringKey: 'api_key',
        excludeCharacters: ' %+~`#$&*()|[]{}:;<>?!\'/@"\\',
      },
    });

    // Store shared configuration in SSM Parameter Store
    // These parameters can be read by other services to discover HelioTime resources
    
    // Service discovery parameters
    new ssm.StringParameter(this, 'ServiceNameParam', {
      parameterName: '/sunday/services/heliotime/name',
      stringValue: 'HelioTime',
      description: 'HelioTime service name',
      tier: ssm.ParameterTier.STANDARD,
    });

    new ssm.StringParameter(this, 'ServiceVersionParam', {
      parameterName: '/sunday/services/heliotime/version',
      stringValue: '1.0.0',
      description: 'HelioTime service version',
      tier: ssm.ParameterTier.STANDARD,
    });

    new ssm.StringParameter(this, 'ServiceDescriptionParam', {
      parameterName: '/sunday/services/heliotime/description',
      stringValue: 'Deterministic sunrise/sunset calculation service',
      description: 'HelioTime service description',
      tier: ssm.ParameterTier.STANDARD,
    });

    // KMS key ARN for other services
    new ssm.StringParameter(this, 'KmsKeyArnParam', {
      parameterName: '/sunday/services/heliotime/kms-key-arn',
      stringValue: this.encryptionKey.keyArn,
      description: 'KMS key ARN for HelioTime encryption',
      tier: ssm.ParameterTier.STANDARD,
    });

    // Geocoder configuration
    new ssm.StringParameter(this, 'GeocoderProviderParam', {
      parameterName: '/sunday/services/heliotime/geocoder/provider',
      stringValue: 'nominatim',
      description: 'Geocoding provider',
      tier: ssm.ParameterTier.STANDARD,
    });

    new ssm.StringParameter(this, 'GeocoderSecretArnParam', {
      parameterName: '/sunday/services/heliotime/geocoder/secret-arn',
      stringValue: this.geocoderApiKeySecret.secretArn,
      description: 'ARN of secret containing geocoder API keys',
      tier: ssm.ParameterTier.STANDARD,
    });

    // Algorithm configuration
    new ssm.StringParameter(this, 'AlgorithmParam', {
      parameterName: '/sunday/services/heliotime/algorithm',
      stringValue: 'NREL_SPA_2005',
      description: 'Solar position algorithm used',
      tier: ssm.ParameterTier.STANDARD,
    });

    // Service limits
    new ssm.StringParameter(this, 'MaxRangeDaysParam', {
      parameterName: '/sunday/services/heliotime/limits/max-range-days',
      stringValue: '366',
      description: 'Maximum date range in days',
      tier: ssm.ParameterTier.STANDARD,
    });

    new ssm.StringParameter(this, 'CacheTtlParam', {
      parameterName: '/sunday/services/heliotime/cache/ttl-seconds',
      stringValue: '7776000',
      description: 'Cache TTL in seconds (90 days)',
      tier: ssm.ParameterTier.STANDARD,
    });

    // Cross-check configuration (dev)
    new ssm.StringParameter(this, 'CrossCheckProviderParam', {
      parameterName: '/sunday/services/heliotime/crosscheck/provider',
      stringValue: 'open-meteo',
      description: 'Cross-check provider for development',
      tier: ssm.ParameterTier.STANDARD,
    });

    new ssm.StringParameter(this, 'CrossCheckToleranceParam', {
      parameterName: '/sunday/services/heliotime/crosscheck/tolerance-seconds',
      stringValue: '120',
      description: 'Cross-check tolerance in seconds',
      tier: ssm.ParameterTier.STANDARD,
    });

    // Output stack information
    new cdk.CfnOutput(this, 'KmsKeyId', {
      value: this.encryptionKey.keyId,
      description: 'KMS Key ID for encryption',
      exportName: 'heliotime-kms-key-id',
    });

    new cdk.CfnOutput(this, 'GeocoderSecretArn', {
      value: this.geocoderApiKeySecret.secretArn,
      description: 'Geocoder API key secret ARN',
      exportName: 'heliotime-geocoder-secret-arn',
    });
  }
}