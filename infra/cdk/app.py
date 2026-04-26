#!/usr/bin/env python3
"""
CDK app entry point for the Approval Gateway stack.

Usage:
    cdk deploy --context account=123456789012 --context region=us-east-1
    cdk deploy -c approver_groups='["team-lead","security","data-owner"]'
"""

import os
import aws_cdk as cdk
from approval_gateway.approval_gateway_stack import ApprovalGatewayStack

app = cdk.App()

account = app.node.try_get_context("account") or os.environ.get("CDK_DEFAULT_ACCOUNT")
region = app.node.try_get_context("region") or os.environ.get("CDK_DEFAULT_REGION")
approver_groups = app.node.try_get_context("approver_groups") or [
    "team-lead",
    "security",
    "data-owner",
]

ApprovalGatewayStack(
    app,
    "ApprovalGatewayStack",
    approver_groups=approver_groups,
    env=cdk.Environment(account=account, region=region),
    description="AWS Approval Gateway — multi-approval workflow for protected API actions",
)

app.synth()
