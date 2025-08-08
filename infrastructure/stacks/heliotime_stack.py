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
        
        self.environment = environment
        self.domain_name = domain_name
        self.shared_resources_stack = shared_resources_stack
        
        # DynamoDB table for geocoding cache
        geo_cache_table = dynamodb.Table(
            self, "GeoCacheTable",
            table_name=f"heliotime-geocache-{environment}",
            partition_key=dynamodb.Attribute(
                name="query_hash",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            time_to_live_attribute="expires_at",
            point_in_time_recovery=True,
            removal_policy=RemovalPolicy.RETAIN if environment == "prod" else RemovalPolicy.DESTROY,
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
            role_name=f"heliotime-lambda-role-{environment}",
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
            function_name=f"heliotime-{environment}",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset(str(lambda_code_path)),
            memory_size=256,
            timeout=Duration.seconds(5),
            role=lambda_role,
            tracing=lambda_.Tracing.ACTIVE,
            log_retention=logs.RetentionDays.ONE_MONTH,
            environment={
                "ENV": environment,
                "DYNAMODB_TABLE": geo_cache_table.table_name,
                "KMS_KEY_ID": shared_resources_stack.encryption_key.key_id,
                "GEOCODER_SECRET_ARN": shared_resources_stack.geocoder_api_key_secret.secret_arn,
                "DEV_CROSSCHECK": "true" if environment == "dev" else "false",
                "DEV_CROSSCHECK_PROVIDER": "open-meteo",
                "DEV_CROSSCHECK_TOLERANCE_SECONDS": "120",
                "DEV_CROSSCHECK_ENFORCE": "false",
                "GEOCODER": "nominatim",
                "GEOCODER_BASE_URL": "https://nominatim.openstreetmap.org",
                "CACHE_TTL_SECONDS": "7776000",
                "MAX_RANGE_DAYS": "366",
                "LOG_LEVEL": "DEBUG" if environment == "dev" else "INFO",
                "BUILD_SHA": os.environ.get("GITHUB_SHA", "local"),
                "BUILD_DATE": datetime.utcnow().isoformat(),
            }
        )
        
        # API Gateway
        api = apigateway.RestApi(
            self, "HelioTimeApi",
            rest_api_name=f"heliotime-api-{environment}",
            description=f"HelioTime API - {environment}",
            deploy_options=apigateway.StageOptions(
                stage_name=environment,
                logging_level=apigateway.MethodLoggingLevel.INFO,
                data_trace_enabled=(environment == "dev"),
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
        
        # Route53 configuration (simplified - CNAME to API Gateway)
        # Note: In production, you'd want to use a custom domain with certificate
        try:
            hosted_zone = route53.HostedZone.from_lookup(
                self, "HostedZone",
                domain_name="sunday.wiki"
            )
            
            # Extract subdomain from full domain name
            subdomain = domain_name.replace(".sunday.wiki", "")
            
            route53.CnameRecord(
                self, "ApiCnameRecord",
                zone=hosted_zone,
                record_name=subdomain,
                domain_name=api.url.replace("https://", "").rstrip("/"),
                ttl=Duration.minutes(5)
            )
        except Exception:
            # Skip Route53 if hosted zone not found (for local testing)
            pass
        
        # CloudWatch Alarms
        cloudwatch.Alarm(
            self, "LambdaErrorAlarm",
            metric=heliotime_lambda.metric_errors(),
            threshold=10,
            evaluation_periods=2,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
            alarm_description=f"High error rate for HelioTime Lambda - {environment}",
        )
        
        cloudwatch.Alarm(
            self, "LambdaDurationAlarm",
            metric=heliotime_lambda.metric_duration(),
            threshold=3000,
            evaluation_periods=2,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
            alarm_description=f"High latency for HelioTime Lambda - {environment}",
        )
        
        cloudwatch.Alarm(
            self, "LambdaThrottleAlarm",
            metric=heliotime_lambda.metric_throttles(),
            threshold=5,
            evaluation_periods=1,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
            alarm_description=f"Throttling detected for HelioTime Lambda - {environment}",
        )
        
        # Store deployment information in SSM
        ssm.StringParameter(
            self, "LambdaArnParam",
            parameter_name=f"/sunday/services/heliotime/{environment}/lambda-arn",
            string_value=heliotime_lambda.function_arn,
            description=f"HelioTime Lambda ARN - {environment}",
        )
        
        ssm.StringParameter(
            self, "ApiEndpointParam",
            parameter_name=f"/sunday/services/heliotime/{environment}/api-endpoint",
            string_value=api.url,
            description=f"HelioTime API endpoint - {environment}",
        )
        
        ssm.StringParameter(
            self, "ApiIdParam",
            parameter_name=f"/sunday/services/heliotime/{environment}/api-id",
            string_value=api.rest_api_id,
            description=f"HelioTime API Gateway ID - {environment}",
        )
        
        ssm.StringParameter(
            self, "DynamoTableParam",
            parameter_name=f"/sunday/services/heliotime/{environment}/dynamodb-table",
            string_value=geo_cache_table.table_name,
            description=f"HelioTime DynamoDB table name - {environment}",
        )
        
        ssm.StringParameter(
            self, "DomainNameParam",
            parameter_name=f"/sunday/services/heliotime/{environment}/domain",
            string_value=domain_name,
            description=f"HelioTime domain name - {environment}",
        )
        
        ssm.StringParameter(
            self, "DeploymentTimestampParam",
            parameter_name=f"/sunday/services/heliotime/{environment}/last-deployment",
            string_value=datetime.utcnow().isoformat(),
            description=f"Last deployment timestamp - {environment}",
        )
        
        # Outputs
        CfnOutput(
            self, "ApiEndpoint",
            value=api.url,
            description=f"API endpoint URL - {environment}",
            export_name=f"heliotime-api-endpoint-{environment}",
        )
        
        CfnOutput(
            self, "LambdaArn",
            value=heliotime_lambda.function_arn,
            description=f"Lambda function ARN - {environment}",
            export_name=f"heliotime-lambda-arn-{environment}",
        )
        
        CfnOutput(
            self, "DynamoTableName",
            value=geo_cache_table.table_name,
            description=f"DynamoDB table name - {environment}",
            export_name=f"heliotime-dynamodb-table-{environment}",
        )
        
        CfnOutput(
            self, "CustomDomain",
            value=f"https://{domain_name}",
            description=f"Custom domain URL - {environment}",
            export_name=f"heliotime-domain-{environment}",
        )