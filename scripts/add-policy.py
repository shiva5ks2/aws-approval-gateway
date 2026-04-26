#!/usr/bin/env python3
"""
CLI tool to add a new policy registry entry to the ApprovalPolicies DynamoDB table.

Usage:
    python scripts/add-policy.py \
        --action-key "ec2:DeleteVpc" \
        --risk-level CRITICAL \
        --required-approvals 2 \
        --approver-groups "team-lead,security" \
        --ttl-hours 24 \
        --executor-arn "arn:aws:lambda:REGION:ACCOUNT:function:ApprovalGatewayExecutor-EC2"
"""

import argparse
import json
import sys

import boto3
from botocore.exceptions import ClientError


def parse_args():
    parser = argparse.ArgumentParser(
        description='Add a new approval policy to the ApprovalPolicies registry.'
    )
    parser.add_argument(
        '--action-key', required=True,
        help='AWS action key, e.g. "ec2:DeleteVpc"'
    )
    parser.add_argument(
        '--risk-level', required=True,
        choices=['CRITICAL', 'HIGH', 'MEDIUM'],
        help='Risk level for this action'
    )
    parser.add_argument(
        '--required-approvals', required=True, type=int,
        help='Number of approvals required'
    )
    parser.add_argument(
        '--approver-groups', required=True,
        help='Comma-separated list of approver group names'
    )
    parser.add_argument(
        '--ttl-hours', required=True, type=int,
        help='Hours to wait for approvals before expiry'
    )
    parser.add_argument(
        '--executor-arn', required=True,
        help='Lambda ARN of the executor function'
    )
    parser.add_argument(
        '--require-mfa', default=True, type=bool,
        help='Whether MFA is required (default: True)'
    )
    parser.add_argument(
        '--notify-slack', default=True, type=bool,
        help='Whether to notify Slack (default: True)'
    )
    parser.add_argument(
        '--table-name', default='ApprovalPolicies',
        help='DynamoDB table name (default: ApprovalPolicies)'
    )
    parser.add_argument(
        '--region', default=None,
        help='AWS region (default: from environment/config)'
    )
    return parser.parse_args()


def main():
    args = parse_args()

    kwargs = {}
    if args.region:
        kwargs['region_name'] = args.region

    dynamodb = boto3.resource('dynamodb', **kwargs)
    table = dynamodb.Table(args.table_name)

    approver_groups = [g.strip() for g in args.approver_groups.split(',')]

    item = {
        'actionKey': args.action_key,
        'riskLevel': args.risk_level,
        'requiredApprovals': args.required_approvals,
        'approverGroups': approver_groups,
        'ttlHours': args.ttl_hours,
        'executorArn': args.executor_arn,
        'requireMFA': args.require_mfa,
        'notifySlack': args.notify_slack,
        'enabled': True
    }

    try:
        table.put_item(Item=item)
        print(f"Successfully added policy for: {args.action_key}")
        print(json.dumps(item, indent=2, default=str))
    except ClientError as e:
        print(f"Error adding policy: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
