#!/usr/bin/env python3
"""
Check existing AWS infrastructure for HelioTime service deployment.
This script analyzes the current state and identifies what needs to be provisioned.
"""

import json
import subprocess
import sys
from typing import Dict, List, Any

PROFILE = "SundayDev"
REQUIRED_RESOURCES = {
    "api_gateway": {
        "name": "heliotime-api",
        "type": "REST",
        "domain": "heliotime.dev.sunday.wiki"
    },
    "lambda_functions": {
        "dev": "heliotime-dev",
        "prod": "heliotime-prod"
    },
    "dynamodb_tables": {
        "geocache": "heliotime-geocache"
    },
    "route53": {
        "subdomain": "heliotime.dev.sunday.wiki"
    },
    "iam_roles": {
        "lambda_execution": "heliotime-lambda-execution-role"
    }
}

def run_aws_command(service: str, command: List[str]) -> Dict[str, Any]:
    """Execute AWS CLI command and return JSON output."""
    cmd = ["aws", service] + command + ["--profile", PROFILE, "--output", "json"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return json.loads(result.stdout) if result.stdout else {}
    except subprocess.CalledProcessError as e:
        print(f"Error running AWS command: {' '.join(cmd)}")
        print(f"Error: {e.stderr}")
        return {}
    except json.JSONDecodeError:
        return {}

def check_api_gateway():
    """Check for existing API Gateway."""
    print("\n📡 Checking API Gateway...")
    apis = run_aws_command("apigateway", ["get-rest-apis"])
    
    found = False
    for api in apis.get("items", []):
        if "heliotime" in api.get("name", "").lower():
            print(f"  ✅ Found API: {api['name']} (ID: {api['id']})")
            found = True
    
    if not found:
        print(f"  ❌ API Gateway '{REQUIRED_RESOURCES['api_gateway']['name']}' not found")
    
    return found

def check_lambda_functions():
    """Check for existing Lambda functions."""
    print("\n⚡ Checking Lambda Functions...")
    functions = run_aws_command("lambda", ["list-functions"])
    
    found_functions = {}
    for env, func_name in REQUIRED_RESOURCES["lambda_functions"].items():
        found = False
        for func in functions.get("Functions", []):
            if func.get("FunctionName") == func_name:
                print(f"  ✅ Found {env} function: {func_name}")
                found = True
                found_functions[env] = func
                break
        
        if not found:
            print(f"  ❌ Lambda function '{func_name}' not found")
    
    return found_functions

def check_dynamodb_tables():
    """Check for existing DynamoDB tables."""
    print("\n🗄️  Checking DynamoDB Tables...")
    tables = run_aws_command("dynamodb", ["list-tables"])
    
    found_tables = []
    for table_key, table_name in REQUIRED_RESOURCES["dynamodb_tables"].items():
        if table_name in tables.get("TableNames", []):
            print(f"  ✅ Found table: {table_name}")
            found_tables.append(table_name)
        else:
            print(f"  ❌ Table '{table_name}' not found")
    
    return found_tables

def check_route53_subdomain():
    """Check for Route53 hosted zone and subdomain."""
    print("\n🌐 Checking Route53 Configuration...")
    zones = run_aws_command("route53", ["list-hosted-zones"])
    
    sunday_zone = None
    for zone in zones.get("HostedZones", []):
        if "sunday.wiki" in zone.get("Name", ""):
            sunday_zone = zone
            print(f"  ✅ Found hosted zone: {zone['Name']} (ID: {zone['Id']})")
            break
    
    if not sunday_zone:
        print("  ❌ No sunday.wiki hosted zone found")
        return False
    
    # Check for subdomain record
    zone_id = sunday_zone["Id"].split("/")[-1]
    records = run_aws_command("route53", ["list-resource-record-sets", "--hosted-zone-id", zone_id])
    
    subdomain_found = False
    for record in records.get("ResourceRecordSets", []):
        if REQUIRED_RESOURCES["route53"]["subdomain"] in record.get("Name", ""):
            print(f"  ✅ Found subdomain: {record['Name']}")
            subdomain_found = True
            break
    
    if not subdomain_found:
        print(f"  ❌ Subdomain '{REQUIRED_RESOURCES['route53']['subdomain']}' not configured")
    
    return subdomain_found

def check_iam_roles():
    """Check for IAM roles."""
    print("\n🔐 Checking IAM Roles...")
    roles = run_aws_command("iam", ["list-roles"])
    
    found_roles = []
    for role_key, role_name in REQUIRED_RESOURCES["iam_roles"].items():
        found = False
        for role in roles.get("Roles", []):
            if role_name in role.get("RoleName", ""):
                print(f"  ✅ Found role: {role['RoleName']}")
                found = True
                found_roles.append(role["RoleName"])
                break
        
        if not found:
            print(f"  ❌ IAM role '{role_name}' not found")
    
    return found_roles

def check_secrets_manager():
    """Check for secrets in AWS Secrets Manager."""
    print("\n🔑 Checking Secrets Manager...")
    secrets = run_aws_command("secretsmanager", ["list-secrets"])
    
    heliotime_secrets = []
    for secret in secrets.get("SecretList", []):
        if "heliotime" in secret.get("Name", "").lower():
            print(f"  ✅ Found secret: {secret['Name']}")
            heliotime_secrets.append(secret["Name"])
    
    if not heliotime_secrets:
        print("  ℹ️  No HelioTime-specific secrets found (may not be required)")
    
    return heliotime_secrets

def generate_cdk_requirements():
    """Generate CDK requirements based on missing resources."""
    print("\n\n" + "="*60)
    print("📋 CDK PROVISIONING REQUIREMENTS")
    print("="*60)
    
    missing = []
    
    # Check each resource type
    if not check_api_gateway():
        missing.append({
            "type": "API Gateway",
            "resource": REQUIRED_RESOURCES["api_gateway"]["name"],
            "cdk_construct": "aws_apigateway.RestApi"
        })
    
    lambda_funcs = check_lambda_functions()
    for env, func_name in REQUIRED_RESOURCES["lambda_functions"].items():
        if env not in lambda_funcs:
            missing.append({
                "type": "Lambda Function",
                "resource": func_name,
                "environment": env,
                "cdk_construct": "aws_lambda.Function"
            })
    
    if not check_dynamodb_tables():
        missing.append({
            "type": "DynamoDB Table",
            "resource": REQUIRED_RESOURCES["dynamodb_tables"]["geocache"],
            "cdk_construct": "aws_dynamodb.Table"
        })
    
    if not check_route53_subdomain():
        missing.append({
            "type": "Route53 Record",
            "resource": REQUIRED_RESOURCES["route53"]["subdomain"],
            "cdk_construct": "aws_route53.ARecord"
        })
    
    if not check_iam_roles():
        missing.append({
            "type": "IAM Role",
            "resource": REQUIRED_RESOURCES["iam_roles"]["lambda_execution"],
            "cdk_construct": "aws_iam.Role"
        })
    
    if missing:
        print("\n⚠️  MISSING RESOURCES:")
        for item in missing:
            print(f"\n  • {item['type']}: {item['resource']}")
            print(f"    CDK Construct: {item['cdk_construct']}")
    else:
        print("\n✅ All required resources are already provisioned!")
    
    return missing

def main():
    print("🔍 HelioTime Infrastructure Check")
    print(f"   Profile: {PROFILE}")
    print("="*60)
    
    try:
        # Verify AWS CLI and profile
        result = subprocess.run(
            ["aws", "sts", "get-caller-identity", "--profile", PROFILE],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            print(f"❌ Unable to authenticate with AWS profile '{PROFILE}'")
            print(f"   Error: {result.stderr}")
            sys.exit(1)
        
        identity = json.loads(result.stdout)
        print(f"✅ Authenticated as: {identity['Arn']}")
        
    except Exception as e:
        print(f"❌ Error checking AWS credentials: {e}")
        sys.exit(1)
    
    # Run checks
    check_api_gateway()
    check_lambda_functions()
    check_dynamodb_tables()
    check_route53_subdomain()
    check_iam_roles()
    check_secrets_manager()
    
    # Generate requirements
    missing = generate_cdk_requirements()
    
    # Save report
    report = {
        "profile": PROFILE,
        "missing_resources": missing,
        "required_resources": REQUIRED_RESOURCES
    }
    
    with open("infrastructure_report.json", "w") as f:
        json.dump(report, f, indent=2)
    
    print("\n\n📄 Report saved to: infrastructure_report.json")
    print("   Use this report with cdk_provisioning_prompt.md to update CDK stack")

if __name__ == "__main__":
    main()