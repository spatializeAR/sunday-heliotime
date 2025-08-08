#!/usr/bin/env node
import 'source-map-support/register';
import * as cdk from 'aws-cdk-lib';
import { HelioTimeStack } from '../lib/heliotime-stack';
import { SharedResourcesStack } from '../lib/shared-resources-stack';

const app = new cdk.App();

// Get context values
const organization = app.node.tryGetContext('sunday:organization');
const service = app.node.tryGetContext('sunday:service');
const domain = app.node.tryGetContext('sunday:domain');

// Common tags for all resources
const commonTags = {
  Organization: organization,
  Service: service,
  ManagedBy: 'CDK',
  Repository: 'sunday-heliotime'
};

// Shared resources stack (SSM parameters, KMS keys, etc.)
const sharedStack = new SharedResourcesStack(app, 'HelioTimeSharedStack', {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.CDK_DEFAULT_REGION || 'us-east-1'
  },
  stackName: 'heliotime-shared',
  description: 'Shared resources and configuration for HelioTime service',
  tags: {
    ...commonTags,
    Environment: 'shared'
  }
});

// Development stack
const devStack = new HelioTimeStack(app, 'HelioTimeDevStack', {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.CDK_DEFAULT_REGION || 'us-east-1'
  },
  stackName: 'heliotime-dev',
  description: 'HelioTime development environment',
  environment: 'dev',
  domainName: `heliotime.dev.${domain}`,
  sharedResourcesStack: sharedStack,
  tags: {
    ...commonTags,
    Environment: 'dev'
  }
});

// Production stack
const prodStack = new HelioTimeStack(app, 'HelioTimeProdStack', {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.CDK_DEFAULT_REGION || 'us-east-1'
  },
  stackName: 'heliotime-prod',
  description: 'HelioTime production environment',
  environment: 'prod',
  domainName: `heliotime.${domain}`,
  sharedResourcesStack: sharedStack,
  tags: {
    ...commonTags,
    Environment: 'prod'
  }
});

// Add dependencies
devStack.addDependency(sharedStack);
prodStack.addDependency(sharedStack);