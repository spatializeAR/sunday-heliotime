"""Shared resources stack for HelioTime service."""

import aws_cdk as cdk
from aws_cdk import (
    Stack,
    CfnOutput,
    RemovalPolicy,
    aws_kms as kms,
    aws_ssm as ssm,
    aws_secretsmanager as secretsmanager,
)
from constructs import Construct


class SharedResourcesStack(Stack):
    """Stack containing shared resources used across all environments."""
    
    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)
        
        # Create KMS key for encryption
        self.encryption_key = kms.Key(
            self, "HelioTimeEncryptionKey",
            description="KMS key for HelioTime service encryption",
            alias="heliotime/encryption",
            enable_key_rotation=True,
            removal_policy=RemovalPolicy.RETAIN,
        )
        
        # Create secret for geocoder API keys (if needed in future)
        self.geocoder_api_key_secret = secretsmanager.Secret(
            self, "GeocoderApiKey",
            secret_name="heliotime/geocoder-api-key",
            description="API keys for geocoding services (Google/Mapbox)",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template='{"provider": "nominatim", "note": "Currently using free Nominatim, no API key required"}',
                generate_string_key="api_key",
                exclude_characters=' %+~`#$&*()|[]{}:;<>?!\'"/@"\\'
            )
        )
        
        # Store shared configuration in SSM Parameter Store
        # These parameters can be read by other services to discover HelioTime resources
        
        # Service discovery parameters
        ssm.StringParameter(
            self, "ServiceNameParam",
            parameter_name="/sunday/services/heliotime/name",
            string_value="HelioTime",
            description="HelioTime service name",
            tier=ssm.ParameterTier.STANDARD,
        )
        
        ssm.StringParameter(
            self, "ServiceVersionParam",
            parameter_name="/sunday/services/heliotime/version",
            string_value="1.0.0",
            description="HelioTime service version",
            tier=ssm.ParameterTier.STANDARD,
        )
        
        ssm.StringParameter(
            self, "ServiceDescriptionParam",
            parameter_name="/sunday/services/heliotime/description",
            string_value="Deterministic sunrise/sunset calculation service",
            description="HelioTime service description",
            tier=ssm.ParameterTier.STANDARD,
        )
        
        # KMS key ARN for other services
        ssm.StringParameter(
            self, "KmsKeyArnParam",
            parameter_name="/sunday/services/heliotime/kms-key-arn",
            string_value=self.encryption_key.key_arn,
            description="KMS key ARN for HelioTime encryption",
            tier=ssm.ParameterTier.STANDARD,
        )
        
        # Geocoder configuration
        ssm.StringParameter(
            self, "GeocoderProviderParam",
            parameter_name="/sunday/services/heliotime/geocoder/provider",
            string_value="nominatim",
            description="Geocoding provider",
            tier=ssm.ParameterTier.STANDARD,
        )
        
        ssm.StringParameter(
            self, "GeocoderSecretArnParam",
            parameter_name="/sunday/services/heliotime/geocoder/secret-arn",
            string_value=self.geocoder_api_key_secret.secret_arn,
            description="ARN of secret containing geocoder API keys",
            tier=ssm.ParameterTier.STANDARD,
        )
        
        # Algorithm configuration
        ssm.StringParameter(
            self, "AlgorithmParam",
            parameter_name="/sunday/services/heliotime/algorithm",
            string_value="NREL_SPA_2005",
            description="Solar position algorithm used",
            tier=ssm.ParameterTier.STANDARD,
        )
        
        # Service limits
        ssm.StringParameter(
            self, "MaxRangeDaysParam",
            parameter_name="/sunday/services/heliotime/limits/max-range-days",
            string_value="366",
            description="Maximum date range in days",
            tier=ssm.ParameterTier.STANDARD,
        )
        
        ssm.StringParameter(
            self, "CacheTtlParam",
            parameter_name="/sunday/services/heliotime/cache/ttl-seconds",
            string_value="7776000",
            description="Cache TTL in seconds (90 days)",
            tier=ssm.ParameterTier.STANDARD,
        )
        
        # Cross-check configuration (dev)
        ssm.StringParameter(
            self, "CrossCheckProviderParam",
            parameter_name="/sunday/services/heliotime/crosscheck/provider",
            string_value="open-meteo",
            description="Cross-check provider for development",
            tier=ssm.ParameterTier.STANDARD,
        )
        
        ssm.StringParameter(
            self, "CrossCheckToleranceParam",
            parameter_name="/sunday/services/heliotime/crosscheck/tolerance-seconds",
            string_value="120",
            description="Cross-check tolerance in seconds",
            tier=ssm.ParameterTier.STANDARD,
        )
        
        # Output stack information
        CfnOutput(
            self, "KmsKeyId",
            value=self.encryption_key.key_id,
            description="KMS Key ID for encryption",
            export_name="heliotime-kms-key-id",
        )
        
        CfnOutput(
            self, "GeocoderSecretArn",
            value=self.geocoder_api_key_secret.secret_arn,
            description="Geocoder API key secret ARN",
            export_name="heliotime-geocoder-secret-arn",
        )