#!/bin/bash
# Deployment script for HelioTime infrastructure and Lambda code

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
AWS_PROFILE="SundayDev"
AWS_REGION="us-east-1"

# Functions
print_header() {
    echo -e "\n${GREEN}===================================================${NC}"
    echo -e "${GREEN}$1${NC}"
    echo -e "${GREEN}===================================================${NC}\n"
}

print_info() {
    echo -e "${YELLOW}ℹ️  $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

check_prerequisites() {
    print_header "Checking Prerequisites"
    
    # Check AWS CLI
    if ! command -v aws &> /dev/null; then
        print_error "AWS CLI not found. Please install it first."
        exit 1
    fi
    print_success "AWS CLI found"
    
    # Check Node.js
    if ! command -v node &> /dev/null; then
        print_error "Node.js not found. Please install it first."
        exit 1
    fi
    print_success "Node.js found: $(node --version)"
    
    # Check npm
    if ! command -v npm &> /dev/null; then
        print_error "npm not found. Please install it first."
        exit 1
    fi
    print_success "npm found: $(npm --version)"
    
    # Check Python
    if ! command -v python3 &> /dev/null; then
        print_error "Python 3 not found. Please install it first."
        exit 1
    fi
    print_success "Python found: $(python3 --version)"
    
    # Check AWS credentials
    if ! aws sts get-caller-identity --profile $AWS_PROFILE &> /dev/null; then
        print_error "AWS credentials not configured for profile: $AWS_PROFILE"
        exit 1
    fi
    
    ACCOUNT_ID=$(aws sts get-caller-identity --profile $AWS_PROFILE --query Account --output text)
    print_success "AWS credentials valid. Account: $ACCOUNT_ID"
}

build_lambda_package() {
    print_header "Building Lambda Package"
    
    # Clean previous builds
    rm -rf lambda_package heliotime-lambda.zip
    
    # Create package directory
    mkdir -p lambda_package
    
    # Install dependencies
    print_info "Installing Python dependencies..."
    pip3 install -r requirements.txt -t lambda_package/ --quiet
    
    # Copy application code
    print_info "Copying application code..."
    cp -r heliotime/* lambda_package/
    
    # Create zip file
    print_info "Creating deployment package..."
    cd lambda_package
    zip -r ../heliotime-lambda.zip . -x "*.pyc" -x "*__pycache__*" -x "*.py[co]" -q
    cd ..
    
    # Get package size
    PACKAGE_SIZE=$(du -h heliotime-lambda.zip | cut -f1)
    print_success "Lambda package built: heliotime-lambda.zip ($PACKAGE_SIZE)"
}

install_cdk_dependencies() {
    print_header "Installing CDK Dependencies"
    
    cd infrastructure
    
    if [ ! -d "node_modules" ]; then
        print_info "Installing npm packages..."
        npm install
    else
        print_info "npm packages already installed"
    fi
    
    # Check if CDK is installed globally
    if ! command -v cdk &> /dev/null; then
        print_info "Installing AWS CDK globally..."
        npm install -g aws-cdk
    fi
    
    print_success "CDK dependencies ready"
    cd ..
}

deploy_infrastructure() {
    local ENVIRONMENT=$1
    
    print_header "Deploying Infrastructure: $ENVIRONMENT"
    
    cd infrastructure
    
    # Build TypeScript
    print_info "Building TypeScript..."
    npm run build
    
    # Set environment variables
    export CDK_DEFAULT_ACCOUNT=$ACCOUNT_ID
    export CDK_DEFAULT_REGION=$AWS_REGION
    export AWS_PROFILE=$AWS_PROFILE
    
    # Deploy shared stack if not exists
    if [ "$ENVIRONMENT" == "shared" ] || [ "$ENVIRONMENT" == "all" ]; then
        print_info "Deploying shared resources stack..."
        npx cdk deploy HelioTimeSharedStack --require-approval never --profile $AWS_PROFILE
        print_success "Shared resources deployed"
    fi
    
    # Deploy environment-specific stack
    if [ "$ENVIRONMENT" == "dev" ] || [ "$ENVIRONMENT" == "all" ]; then
        print_info "Deploying development stack..."
        npx cdk deploy HelioTimeDevStack --require-approval never --profile $AWS_PROFILE
        print_success "Development environment deployed"
    fi
    
    if [ "$ENVIRONMENT" == "prod" ]; then
        print_info "Deploying production stack..."
        read -p "⚠️  Are you sure you want to deploy to PRODUCTION? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            npx cdk deploy HelioTimeProdStack --require-approval never --profile $AWS_PROFILE
            print_success "Production environment deployed"
        else
            print_info "Production deployment cancelled"
        fi
    fi
    
    cd ..
}

update_lambda_code() {
    local ENVIRONMENT=$1
    
    print_header "Updating Lambda Code: $ENVIRONMENT"
    
    FUNCTION_NAME="heliotime-$ENVIRONMENT"
    
    print_info "Updating function: $FUNCTION_NAME"
    
    # Update function code
    aws lambda update-function-code \
        --function-name $FUNCTION_NAME \
        --zip-file fileb://heliotime-lambda.zip \
        --profile $AWS_PROFILE \
        --region $AWS_REGION \
        --output text > /dev/null
    
    # Wait for update to complete
    print_info "Waiting for update to complete..."
    aws lambda wait function-updated \
        --function-name $FUNCTION_NAME \
        --profile $AWS_PROFILE \
        --region $AWS_REGION
    
    # Update build metadata
    aws lambda update-function-configuration \
        --function-name $FUNCTION_NAME \
        --environment "Variables={BUILD_SHA=$(git rev-parse HEAD),BUILD_DATE=$(date -u +%Y-%m-%dT%H:%M:%SZ)}" \
        --profile $AWS_PROFILE \
        --region $AWS_REGION \
        --output text > /dev/null
    
    print_success "Lambda code updated for $ENVIRONMENT"
}

test_deployment() {
    local ENVIRONMENT=$1
    
    print_header "Testing Deployment: $ENVIRONMENT"
    
    # Get API endpoint from SSM
    API_ENDPOINT=$(aws ssm get-parameter \
        --name "/sunday/services/heliotime/$ENVIRONMENT/api-endpoint" \
        --profile $AWS_PROFILE \
        --region $AWS_REGION \
        --query 'Parameter.Value' \
        --output text 2>/dev/null || echo "")
    
    if [ -z "$API_ENDPOINT" ]; then
        print_error "Could not find API endpoint in SSM"
        return 1
    fi
    
    print_info "Testing endpoint: $API_ENDPOINT"
    
    # Test health endpoint
    HEALTH_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" "${API_ENDPOINT}healthz")
    
    if [ "$HEALTH_RESPONSE" == "200" ]; then
        print_success "Health check passed"
    else
        print_error "Health check failed (HTTP $HEALTH_RESPONSE)"
        return 1
    fi
    
    # Test sun endpoint
    SUN_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" "${API_ENDPOINT}sun?lat=51.5074&lon=-0.1278&date=2025-09-01")
    
    if [ "$SUN_RESPONSE" == "200" ]; then
        print_success "Sun endpoint test passed"
    else
        print_error "Sun endpoint test failed (HTTP $SUN_RESPONSE)"
        return 1
    fi
}

run_infrastructure_check() {
    print_header "Running Infrastructure Check"
    
    python3 scripts/check_infrastructure_v2.py
}

# Main script
main() {
    print_header "HelioTime Deployment Script"
    
    # Parse arguments
    ACTION=${1:-help}
    ENVIRONMENT=${2:-dev}
    
    case $ACTION in
        check)
            check_prerequisites
            run_infrastructure_check
            ;;
        
        build)
            check_prerequisites
            build_lambda_package
            ;;
        
        deploy-infra)
            check_prerequisites
            install_cdk_dependencies
            deploy_infrastructure $ENVIRONMENT
            ;;
        
        deploy-code)
            check_prerequisites
            build_lambda_package
            update_lambda_code $ENVIRONMENT
            test_deployment $ENVIRONMENT
            ;;
        
        deploy-all)
            check_prerequisites
            build_lambda_package
            install_cdk_dependencies
            deploy_infrastructure $ENVIRONMENT
            update_lambda_code $ENVIRONMENT
            test_deployment $ENVIRONMENT
            run_infrastructure_check
            ;;
        
        test)
            check_prerequisites
            test_deployment $ENVIRONMENT
            ;;
        
        help|*)
            echo "Usage: $0 [action] [environment]"
            echo ""
            echo "Actions:"
            echo "  check         - Check prerequisites and current infrastructure"
            echo "  build         - Build Lambda deployment package"
            echo "  deploy-infra  - Deploy CDK infrastructure only"
            echo "  deploy-code   - Deploy Lambda code only"
            echo "  deploy-all    - Deploy infrastructure and code"
            echo "  test          - Test deployed endpoints"
            echo "  help          - Show this help message"
            echo ""
            echo "Environments:"
            echo "  shared  - Shared resources only"
            echo "  dev     - Development environment (default)"
            echo "  prod    - Production environment"
            echo "  all     - All environments (shared + dev)"
            echo ""
            echo "Examples:"
            echo "  $0 check                    # Check current infrastructure"
            echo "  $0 deploy-all dev          # Deploy everything to dev"
            echo "  $0 deploy-code dev         # Update Lambda code in dev"
            echo "  $0 test prod               # Test production endpoints"
            ;;
    esac
}

main "$@"