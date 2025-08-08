#!/usr/bin/env python3
"""
Enhanced infrastructure check that reads from SSM Parameter Store.
This script checks both direct AWS resources and SSM parameters to get
a complete picture of the deployment state.
"""

import json
import subprocess
import sys
from typing import Dict, List, Any, Optional
from datetime import datetime

PROFILE = "SundayDev"

class InfrastructureChecker:
    def __init__(self, profile: str = PROFILE):
        self.profile = profile
        self.ssm_params = {}
        self.resources = {
            'shared': {},
            'dev': {},
            'prod': {}
        }
        
    def run_aws_command(self, service: str, command: List[str]) -> Dict[str, Any]:
        """Execute AWS CLI command and return JSON output."""
        cmd = ["aws", service] + command + ["--profile", self.profile, "--output", "json"]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return json.loads(result.stdout) if result.stdout else {}
        except subprocess.CalledProcessError as e:
            print(f"Error running AWS command: {' '.join(cmd)}")
            print(f"Error: {e.stderr}")
            return {}
        except json.JSONDecodeError:
            return {}

    def check_ssm_parameters(self):
        """Check SSM Parameter Store for HelioTime configuration."""
        print("\n📊 Checking SSM Parameter Store...")
        
        # Check shared parameters
        shared_params = [
            '/sunday/services/heliotime/name',
            '/sunday/services/heliotime/version',
            '/sunday/services/heliotime/description',
            '/sunday/services/heliotime/kms-key-arn',
            '/sunday/services/heliotime/geocoder/provider',
            '/sunday/services/heliotime/geocoder/secret-arn',
            '/sunday/services/heliotime/algorithm',
            '/sunday/services/heliotime/limits/max-range-days',
            '/sunday/services/heliotime/cache/ttl-seconds',
            '/sunday/services/heliotime/crosscheck/provider',
            '/sunday/services/heliotime/crosscheck/tolerance-seconds',
        ]
        
        print("  Shared configuration:")
        for param_name in shared_params:
            result = self.run_aws_command("ssm", ["get-parameter", "--name", param_name])
            if 'Parameter' in result:
                value = result['Parameter']['Value']
                self.ssm_params[param_name] = value
                print(f"    ✅ {param_name}: {value}")
            else:
                print(f"    ❌ {param_name}: Not found")
        
        # Check environment-specific parameters
        for env in ['dev', 'prod']:
            print(f"\n  {env.upper()} environment:")
            env_params = [
                f'/sunday/services/heliotime/{env}/lambda-arn',
                f'/sunday/services/heliotime/{env}/api-endpoint',
                f'/sunday/services/heliotime/{env}/api-id',
                f'/sunday/services/heliotime/{env}/dynamodb-table',
                f'/sunday/services/heliotime/{env}/domain',
                f'/sunday/services/heliotime/{env}/last-deployment',
            ]
            
            for param_name in env_params:
                result = self.run_aws_command("ssm", ["get-parameter", "--name", param_name])
                if 'Parameter' in result:
                    value = result['Parameter']['Value']
                    self.ssm_params[param_name] = value
                    param_key = param_name.split('/')[-1]
                    
                    # Parse deployment timestamp
                    if param_key == 'last-deployment':
                        try:
                            dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
                            value = f"{value} ({self.time_ago(dt)})"
                        except:
                            pass
                    
                    print(f"    ✅ {param_key}: {value}")
                    self.resources[env][param_key] = value
                else:
                    print(f"    ❌ {param_name}: Not found")

    def time_ago(self, dt: datetime) -> str:
        """Calculate human-readable time ago."""
        now = datetime.now(dt.tzinfo)
        delta = now - dt
        
        if delta.days > 0:
            return f"{delta.days} days ago"
        elif delta.seconds > 3600:
            return f"{delta.seconds // 3600} hours ago"
        elif delta.seconds > 60:
            return f"{delta.seconds // 60} minutes ago"
        else:
            return "just now"

    def check_cloudformation_stacks(self):
        """Check CloudFormation stacks."""
        print("\n☁️  Checking CloudFormation Stacks...")
        
        stacks = self.run_aws_command("cloudformation", ["list-stacks", "--stack-status-filter", 
                                                         "CREATE_COMPLETE", "UPDATE_COMPLETE"])
        
        heliotime_stacks = []
        for stack in stacks.get("StackSummaries", []):
            if "heliotime" in stack.get("StackName", "").lower():
                heliotime_stacks.append(stack)
                status = stack.get("StackStatus", "UNKNOWN")
                name = stack.get("StackName")
                print(f"  ✅ {name}: {status}")
                
                # Get stack outputs
                stack_details = self.run_aws_command("cloudformation", 
                    ["describe-stacks", "--stack-name", name])
                
                if stack_details and "Stacks" in stack_details:
                    outputs = stack_details["Stacks"][0].get("Outputs", [])
                    for output in outputs:
                        key = output.get("OutputKey", "")
                        value = output.get("OutputValue", "")
                        if key and value:
                            print(f"      {key}: {value}")
        
        if not heliotime_stacks:
            print("  ❌ No HelioTime CloudFormation stacks found")
        
        return heliotime_stacks

    def check_lambda_functions(self):
        """Check Lambda functions."""
        print("\n⚡ Checking Lambda Functions...")
        
        for env in ['dev', 'prod']:
            func_name = f"heliotime-{env}"
            func = self.run_aws_command("lambda", ["get-function", "--function-name", func_name])
            
            if func and "Configuration" in func:
                config = func["Configuration"]
                print(f"  ✅ {func_name}:")
                print(f"      Runtime: {config.get('Runtime')}")
                print(f"      Memory: {config.get('MemorySize')} MB")
                print(f"      Timeout: {config.get('Timeout')} seconds")
                print(f"      Last Modified: {config.get('LastModified')}")
                
                # Check environment variables
                env_vars = config.get("Environment", {}).get("Variables", {})
                if env_vars:
                    print(f"      Environment Variables: {len(env_vars)} configured")
            else:
                print(f"  ❌ {func_name}: Not found")

    def check_api_gateway(self):
        """Check API Gateway."""
        print("\n📡 Checking API Gateway...")
        
        apis = self.run_aws_command("apigateway", ["get-rest-apis"])
        
        for api in apis.get("items", []):
            if "heliotime" in api.get("name", "").lower():
                print(f"  ✅ {api['name']} (ID: {api['id']})")
                
                # Check deployments
                deployments = self.run_aws_command("apigateway", 
                    ["get-deployments", "--rest-api-id", api['id']])
                
                if deployments and "items" in deployments:
                    for deployment in deployments["items"]:
                        stage = deployment.get("stageName", "unknown")
                        created = deployment.get("createdDate", "")
                        print(f"      Stage '{stage}': Deployed {created}")

    def check_dynamodb_tables(self):
        """Check DynamoDB tables."""
        print("\n🗄️  Checking DynamoDB Tables...")
        
        tables = self.run_aws_command("dynamodb", ["list-tables"])
        
        for table_name in tables.get("TableNames", []):
            if "heliotime" in table_name.lower():
                # Get table details
                table = self.run_aws_command("dynamodb", 
                    ["describe-table", "--table-name", table_name])
                
                if table and "Table" in table:
                    table_info = table["Table"]
                    print(f"  ✅ {table_name}:")
                    print(f"      Status: {table_info.get('TableStatus')}")
                    print(f"      Items: {table_info.get('ItemCount', 0)}")
                    print(f"      Size: {table_info.get('TableSizeBytes', 0)} bytes")
                    
                    # Check TTL
                    ttl = self.run_aws_command("dynamodb", 
                        ["describe-time-to-live", "--table-name", table_name])
                    if ttl and "TimeToLiveDescription" in ttl:
                        ttl_status = ttl["TimeToLiveDescription"].get("TimeToLiveStatus")
                        print(f"      TTL: {ttl_status}")

    def check_kms_keys(self):
        """Check KMS keys."""
        print("\n🔐 Checking KMS Keys...")
        
        # Check if KMS key exists from SSM parameter
        kms_arn = self.ssm_params.get('/sunday/services/heliotime/kms-key-arn')
        
        if kms_arn:
            key_id = kms_arn.split('/')[-1]
            key = self.run_aws_command("kms", ["describe-key", "--key-id", key_id])
            
            if key and "KeyMetadata" in key:
                metadata = key["KeyMetadata"]
                print(f"  ✅ HelioTime Encryption Key:")
                print(f"      State: {metadata.get('KeyState')}")
                print(f"      Created: {metadata.get('CreationDate')}")
                print(f"      Key Usage: {metadata.get('KeyUsage')}")
                
                # Check key aliases
                aliases = self.run_aws_command("kms", ["list-aliases", "--key-id", key_id])
                if aliases and "Aliases" in aliases:
                    for alias in aliases["Aliases"]:
                        print(f"      Alias: {alias.get('AliasName')}")
        else:
            print("  ❌ KMS key not found in SSM parameters")

    def check_secrets_manager(self):
        """Check Secrets Manager."""
        print("\n🔑 Checking Secrets Manager...")
        
        secret_arn = self.ssm_params.get('/sunday/services/heliotime/geocoder/secret-arn')
        
        if secret_arn:
            secret = self.run_aws_command("secretsmanager", 
                ["describe-secret", "--secret-id", secret_arn])
            
            if secret:
                print(f"  ✅ Geocoder API Key Secret:")
                print(f"      Name: {secret.get('Name')}")
                print(f"      Last Changed: {secret.get('LastChangedDate')}")
                print(f"      Rotation: {secret.get('RotationEnabled', False)}")
        else:
            print("  ❌ Secret not found in SSM parameters")

    def generate_report(self) -> Dict[str, Any]:
        """Generate comprehensive infrastructure report."""
        report = {
            "timestamp": datetime.utcnow().isoformat(),
            "profile": self.profile,
            "ssm_parameters": self.ssm_params,
            "resources": self.resources,
            "deployment_status": {
                "shared": bool(self.ssm_params.get('/sunday/services/heliotime/name')),
                "dev": bool(self.resources['dev'].get('lambda-arn')),
                "prod": bool(self.resources['prod'].get('lambda-arn'))
            },
            "recommendations": []
        }
        
        # Add recommendations
        if not report["deployment_status"]["shared"]:
            report["recommendations"].append("Deploy shared resources stack first")
        
        if not report["deployment_status"]["dev"]:
            report["recommendations"].append("Deploy development environment")
        
        if not report["deployment_status"]["prod"]:
            report["recommendations"].append("Deploy production environment after dev testing")
        
        return report

    def run_full_check(self):
        """Run complete infrastructure check."""
        print("🔍 HelioTime Infrastructure Check v2")
        print(f"   Profile: {self.profile}")
        print("   Enhanced with SSM Parameter Store")
        print("="*60)
        
        # Verify AWS credentials
        try:
            result = subprocess.run(
                ["aws", "sts", "get-caller-identity", "--profile", self.profile],
                capture_output=True, text=True
            )
            if result.returncode != 0:
                print(f"❌ Unable to authenticate with AWS profile '{self.profile}'")
                print(f"   Error: {result.stderr}")
                sys.exit(1)
            
            identity = json.loads(result.stdout)
            print(f"✅ Authenticated as: {identity['Arn']}\n")
            
        except Exception as e:
            print(f"❌ Error checking AWS credentials: {e}")
            sys.exit(1)
        
        # Run all checks
        self.check_ssm_parameters()
        self.check_cloudformation_stacks()
        self.check_lambda_functions()
        self.check_api_gateway()
        self.check_dynamodb_tables()
        self.check_kms_keys()
        self.check_secrets_manager()
        
        # Generate report
        report = self.generate_report()
        
        # Save report
        with open("infrastructure_report_v2.json", "w") as f:
            json.dump(report, f, indent=2)
        
        # Print summary
        print("\n" + "="*60)
        print("📋 DEPLOYMENT SUMMARY")
        print("="*60)
        
        print("\n🚦 Status:")
        for env, deployed in report["deployment_status"].items():
            status = "✅ Deployed" if deployed else "❌ Not Deployed"
            print(f"  {env.upper()}: {status}")
        
        if report["recommendations"]:
            print("\n💡 Recommendations:")
            for rec in report["recommendations"]:
                print(f"  • {rec}")
        
        print("\n📄 Full report saved to: infrastructure_report_v2.json")
        
        # CDK deployment instructions
        if not all(report["deployment_status"].values()):
            print("\n🚀 To deploy missing resources with CDK:")
            print("   cd infrastructure")
            print("   npm install")
            if not report["deployment_status"]["shared"]:
                print("   npm run cdk deploy HelioTimeSharedStack")
            if not report["deployment_status"]["dev"]:
                print("   npm run deploy:dev")
            if not report["deployment_status"]["prod"]:
                print("   npm run deploy:prod")

def main():
    checker = InfrastructureChecker()
    checker.run_full_check()

if __name__ == "__main__":
    main()