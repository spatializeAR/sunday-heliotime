#!/usr/bin/env python3
"""CDK application entry point for HelioTime infrastructure."""

import os
import aws_cdk as cdk
from stacks.shared_resources_stack import SharedResourcesStack
from stacks.heliotime_stack import HelioTimeStack

app = cdk.App()

# Get context values
organization = app.node.try_get_context("sunday:organization")
service = app.node.try_get_context("sunday:service")
domain = app.node.try_get_context("sunday:domain")

# Common environment configuration
env = cdk.Environment(
    account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
    region=os.environ.get("CDK_DEFAULT_REGION", "us-east-1")
)

# Common tags for all resources
common_tags = {
    "Organization": organization,
    "Service": service,
    "ManagedBy": "CDK-Python",
    "Repository": "sunday-heliotime"
}

# Shared resources stack (SSM parameters, KMS keys, etc.)
shared_stack = SharedResourcesStack(
    app, 
    "HelioTimeSharedStack",
    env=env,
    stack_name="heliotime-shared",
    description="Shared resources and configuration for HelioTime service",
    tags={
        **common_tags,
        "Environment": "shared"
    }
)

# Development stack
dev_stack = HelioTimeStack(
    app,
    "HelioTimeDevStack",
    env=env,
    stack_name="heliotime-dev",
    description="HelioTime development environment",
    environment="dev",
    domain_name=f"heliotime.dev.{domain}",
    shared_resources_stack=shared_stack,
    tags={
        **common_tags,
        "Environment": "dev"
    }
)

# Production stack
prod_stack = HelioTimeStack(
    app,
    "HelioTimeProdStack",
    env=env,
    stack_name="heliotime-prod",
    description="HelioTime production environment",
    environment="prod",
    domain_name=f"heliotime.{domain}",
    shared_resources_stack=shared_stack,
    tags={
        **common_tags,
        "Environment": "prod"
    }
)

# Add dependencies
dev_stack.add_dependency(shared_stack)
prod_stack.add_dependency(shared_stack)

app.synth()