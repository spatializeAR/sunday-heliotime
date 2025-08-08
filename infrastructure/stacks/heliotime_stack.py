"""Main HelioTime infrastructure stack."""

import os
from pathlib import Path
from datetime import datetime
from typing import Optional

import aws_cdk as cdk
from aws_cdk import (
    Stack,
    CfnOutput,
    Duration,
    RemovalPolicy,
    aws_lambda as lambda_,
    aws_apigateway as apigateway,
    aws_dynamodb as dynamodb,
    aws_iam as iam,
    aws_route53 as route53,
    aws_route53_targets as route53_targets,
    aws_certificatemanager as acm,
    aws_cloudwatch as cloudwatch,
    aws_logs as logs,
    aws_ssm as ssm,
)
from constructs import Construct


class HelioTimeStack(Stack):
    """Stack containing environment-specific HelioTime resources."""
    
    def __init__(
        self,
        scope: Construct,
        id: str,
        environment: str,
        domain_name: str,
        shared_resources_stack,
        **kwargs
    ) -> None:
        super().__init__(scope, id, **kwargs)
        
        self.env_name = environment  # Renamed to avoid conflict with CDK's environment property
        self.domain_name = domain_name
        self.shared_resources_stack = shared_resources_stack
        
        # DynamoDB table for geocoding cache
        geo_cache_table = dynamodb.Table(
            self, "GeoCacheTable",
            table_name=f"heliotime-geocache-{self.env_name}",
            partition_key=dynamodb.Attribute(
                name="query_hash",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            time_to_live_attribute="expires_at",
            point_in_time_recovery=True,
            removal_policy=RemovalPolicy.RETAIN if self.env_name == "prod" else RemovalPolicy.DESTROY,
            encryption=dynamodb.TableEncryption.CUSTOMER_MANAGED,
            encryption_key=shared_resources_stack.encryption_key,
        )
        
        # Add GSI for location lookups
        geo_cache_table.add_global_secondary_index(
            index_name="location-index",
            partition_key=dynamodb.Attribute(
                name="location_type",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="location_key",
                type=dynamodb.AttributeType.STRING
            )
        )
        
        # Lambda execution role
        lambda_role = iam.Role(
            self, "LambdaExecutionRole",
            role_name=f"heliotime-lambda-role-{self.env_name}",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole")
            ]
        )
        
        # Add permissions for DynamoDB
        geo_cache_table.grant_read_write_data(lambda_role)
        
        # Add permissions for KMS
        shared_resources_stack.encryption_key.grant_decrypt(lambda_role)
        
        # Add permissions for Secrets Manager
        shared_resources_stack.geocoder_api_key_secret.grant_read(lambda_role)
        
        # Add permissions for SSM Parameter Store
        lambda_role.add_to_policy(
            iam.PolicyStatement(
                actions=["ssm:GetParameter", "ssm:GetParameters"],
                resources=[f"arn:aws:ssm:{self.region}:{self.account}:parameter/sunday/services/heliotime/*"]
            )
        )
        
        # Add X-Ray permissions
        lambda_role.add_to_policy(
            iam.PolicyStatement(
                actions=["xray:PutTraceSegments", "xray:PutTelemetryRecords"],
                resources=["*"]
            )
        )
        
        # Lambda function
        lambda_code_path = Path(__file__).parent.parent.parent / "heliotime"
        
        heliotime_lambda = lambda_.Function(
            self, "HelioTimeFunction",
            function_name=f"heliotime-{self.env_name}",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset(str(lambda_code_path)),
            memory_size=256,
            timeout=Duration.seconds(5),
            role=lambda_role,
            tracing=lambda_.Tracing.ACTIVE,
            log_retention=logs.RetentionDays.ONE_MONTH,
            environment={
                "ENV": self.env_name,
                "DYNAMODB_TABLE": geo_cache_table.table_name,
                "KMS_KEY_ID": shared_resources_stack.encryption_key.key_id,
                "GEOCODER_SECRET_ARN": shared_resources_stack.geocoder_api_key_secret.secret_arn,
                "DEV_CROSSCHECK": "true" if self.env_name == "dev" else "false",
                "DEV_CROSSCHECK_PROVIDER": "open-meteo",
                "DEV_CROSSCHECK_TOLERANCE_SECONDS": "120",
                "DEV_CROSSCHECK_ENFORCE": "false",
                "GEOCODER": "nominatim",
                "GEOCODER_BASE_URL": "https://nominatim.openstreetmap.org",
                "CACHE_TTL_SECONDS": "7776000",
                "MAX_RANGE_DAYS": "366",
                "LOG_LEVEL": "DEBUG" if self.env_name == "dev" else "INFO",
                "BUILD_SHA": os.environ.get("GITHUB_SHA", "local"),
                "BUILD_DATE": datetime.utcnow().isoformat(),
            }
        )
        
        # API Gateway
        api = apigateway.RestApi(
            self, "HelioTimeApi",
            rest_api_name=f"heliotime-api-{self.env_name}",
            description=f"HelioTime API - {self.env_name}",
            cloud_watch_role=False,  # Disable automatic CloudWatch role creation
            deploy_options=apigateway.StageOptions(
                stage_name=self.env_name,
                # Disable CloudWatch logging for now to avoid role issues
                # logging_level=apigateway.MethodLoggingLevel.INFO,
                # data_trace_enabled=(self.env_name == "dev"),
                metrics_enabled=True,
                tracing_enabled=True,
                throttling_burst_limit=100,
                throttling_rate_limit=50,
            ),
            default_cors_preflight_options=apigateway.CorsOptions(
                allow_origins=apigateway.Cors.ALL_ORIGINS,
                allow_methods=apigateway.Cors.ALL_METHODS,
                allow_headers=["Content-Type", "X-Amz-Date", "Authorization", "X-Api-Key"],
            )
        )
        
        # Lambda integration
        lambda_integration = apigateway.LambdaIntegration(
            heliotime_lambda,
            request_templates={"application/json": '{ "statusCode": 200 }'}
        )
        
        # API resources and methods
        sun_resource = api.root.add_resource("sun")
        sun_resource.add_method(
            "GET",
            lambda_integration,
            request_parameters={
                "method.request.querystring.lat": False,
                "method.request.querystring.lon": False,
                "method.request.querystring.gps": False,
                "method.request.querystring.postal_code": False,
                "method.request.querystring.country_code": False,
                "method.request.querystring.city": False,
                "method.request.querystring.country": False,
                "method.request.querystring.date": False,
                "method.request.querystring.start_date": False,
                "method.request.querystring.end_date": False,
                "method.request.querystring.elevation_m": False,
                "method.request.querystring.pressure_hpa": False,
                "method.request.querystring.temperature_c": False,
                "method.request.querystring.tz": False,
                "method.request.querystring.altitude_correction": False,
                "method.request.querystring.include_twilight": False,
                "method.request.querystring.dev_crosscheck": False,
            }
        )
        
        health_resource = api.root.add_resource("healthz")
        health_resource.add_method("GET", lambda_integration)
        
        help_resource = api.root.add_resource("help")
        help_resource.add_method("GET", lambda_integration)
        
        # Root path also supports help
        api.root.add_method("GET", lambda_integration)
        
        # Custom domain configuration
        # For dev environment, use dev.sunday.wiki subdomain
        if self.env_name == "dev":
            # Look up the dev.sunday.wiki hosted zone
            hosted_zone = route53.HostedZone.from_lookup(
                self, "HostedZone",
                domain_name="dev.sunday.wiki"
            )
            
            # Full domain name for the API
            api_domain_name = f"heliotime.dev.sunday.wiki"
            
            # Request ACM certificate for the domain
            certificate = acm.Certificate(
                self, "ApiCertificate",
                domain_name=api_domain_name,
                validation=acm.CertificateValidation.from_dns(hosted_zone),
                subject_alternative_names=[],
            )
            
            # Create custom domain for API Gateway
            custom_domain = apigateway.DomainName(
                self, "CustomDomain",
                domain_name=api_domain_name,
                certificate=certificate,
                endpoint_type=apigateway.EndpointType.REGIONAL,
                security_policy=apigateway.SecurityPolicy.TLS_1_2,
            )
            
            # Map the API to the custom domain
            apigateway.BasePathMapping(
                self, "BasePathMapping",
                domain_name=custom_domain,
                rest_api=api,
                stage=api.deployment_stage,
            )
            
            # Create Route53 A record for the custom domain
            route53.ARecord(
                self, "ApiARecord",
                zone=hosted_zone,
                record_name="heliotime",
                target=route53.RecordTarget.from_alias(
                    route53_targets.ApiGatewayDomain(custom_domain)
                ),
                ttl=None,  # Not needed for alias records
            )
            
            # Output the custom domain URL
            CfnOutput(
                self, "CustomDomainUrl",
                value=f"https://{api_domain_name}",
                description=f"Custom domain URL - {self.env_name}",
                export_name=f"heliotime-custom-domain-url-{self.env_name}",
            )
        
        # For production, you'd configure a different domain
        # elif self.env_name == "prod":
        #     # Similar configuration for production domain
        
        # CloudWatch Alarms
        cloudwatch.Alarm(
            self, "LambdaErrorAlarm",
            metric=heliotime_lambda.metric_errors(),
            threshold=10,
            evaluation_periods=2,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
            alarm_description=f"High error rate for HelioTime Lambda - {self.env_name}",
        )
        
        cloudwatch.Alarm(
            self, "LambdaDurationAlarm",
            metric=heliotime_lambda.metric_duration(),
            threshold=3000,
            evaluation_periods=2,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
            alarm_description=f"High latency for HelioTime Lambda - {self.env_name}",
        )
        
        cloudwatch.Alarm(
            self, "LambdaThrottleAlarm",
            metric=heliotime_lambda.metric_throttles(),
            threshold=5,
            evaluation_periods=1,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
            alarm_description=f"Throttling detected for HelioTime Lambda - {self.env_name}",
        )
        
        # Store deployment information in SSM
        ssm.StringParameter(
            self, "LambdaArnParam",
            parameter_name=f"/sunday/services/heliotime/{self.env_name}/lambda-arn",
            string_value=heliotime_lambda.function_arn,
            description=f"HelioTime Lambda ARN - {self.env_name}",
        )
        
        ssm.StringParameter(
            self, "ApiEndpointParam",
            parameter_name=f"/sunday/services/heliotime/{self.env_name}/api-endpoint",
            string_value=api.url,
            description=f"HelioTime API endpoint - {self.env_name}",
        )
        
        ssm.StringParameter(
            self, "ApiIdParam",
            parameter_name=f"/sunday/services/heliotime/{self.env_name}/api-id",
            string_value=api.rest_api_id,
            description=f"HelioTime API Gateway ID - {self.env_name}",
        )
        
        ssm.StringParameter(
            self, "DynamoTableParam",
            parameter_name=f"/sunday/services/heliotime/{self.env_name}/dynamodb-table",
            string_value=geo_cache_table.table_name,
            description=f"HelioTime DynamoDB table name - {self.env_name}",
        )
        
        ssm.StringParameter(
            self, "DomainNameParam",
            parameter_name=f"/sunday/services/heliotime/{self.env_name}/domain",
            string_value=domain_name,
            description=f"HelioTime domain name - {self.env_name}",
        )
        
        ssm.StringParameter(
            self, "DeploymentTimestampParam",
            parameter_name=f"/sunday/services/heliotime/{self.env_name}/last-deployment",
            string_value=datetime.utcnow().isoformat(),
            description=f"Last deployment timestamp - {self.env_name}",
        )
        
        # Outputs
        CfnOutput(
            self, "ApiEndpoint",
            value=api.url,
            description=f"API endpoint URL - {self.env_name}",
            export_name=f"heliotime-api-endpoint-{self.env_name}",
        )
        
        CfnOutput(
            self, "LambdaArn",
            value=heliotime_lambda.function_arn,
            description=f"Lambda function ARN - {self.env_name}",
            export_name=f"heliotime-lambda-arn-{self.env_name}",
        )
        
        CfnOutput(
            self, "DynamoTableName",
            value=geo_cache_table.table_name,
            description=f"DynamoDB table name - {self.env_name}",
            export_name=f"heliotime-dynamodb-table-{self.env_name}",
        )
        
        CfnOutput(
            self, "ExpectedDomain",
            value=f"https://{domain_name}",
            description=f"Expected domain URL - {self.env_name}",
            export_name=f"heliotime-expected-domain-{self.env_name}",
        )