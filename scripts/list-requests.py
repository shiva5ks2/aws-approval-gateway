#!/usr/bin/env python3
"""
CLI tool to list pending approval requests from the ApprovalRequests DynamoDB table.

Usage:
    python scripts/list-requests.py
    python scripts/list-requests.py --status PENDING
    python scripts/list-requests.py --status APPROVED --limit 10
"""

import argparse
import json
import sys
from datetime import datetime

import boto3
from botocore.exceptions import ClientError


def parse_args():
    parser = argparse.ArgumentParser(
        description='List approval requests from the ApprovalRequests table.'
    )
    parser.add_argument(
        '--status', default='PENDING',
        choices=['PENDING', 'APPROVED', 'DENIED', 'COMPLETED', 'EXPIRED', 'FAILED', 'ALL'],
        help='Filter by status (default: PENDING)'
    )
    parser.add_argument(
        '--limit', default=25, type=int,
        help='Maximum number of results (default: 25)'
    )
    parser.add_argument(
        '--table-name', default='ApprovalRequests',
        help='DynamoDB table name (default: ApprovalRequests)'
    )
    parser.add_argument(
        '--region', default=None,
        help='AWS region (default: from environment/config)'
    )
    return parser.parse_args()


def format_timestamp(ts):
    """Convert Unix timestamp to human-readable format."""
    if ts:
        return datetime.fromtimestamp(int(ts)).strftime('%Y-%m-%d %H:%M:%S')
    return 'N/A'


def main():
    args = parse_args()

    kwargs = {}
    if args.region:
        kwargs['region_name'] = args.region

    dynamodb = boto3.resource('dynamodb', **kwargs)
    table = dynamodb.Table(args.table_name)

    try:
        scan_kwargs = {'Limit': args.limit}

        if args.status != 'ALL':
            scan_kwargs['FilterExpression'] = '#s = :status'
            scan_kwargs['ExpressionAttributeNames'] = {'#s': 'status'}
            scan_kwargs['ExpressionAttributeValues'] = {':status': args.status}

        response = table.scan(**scan_kwargs)
        items = response.get('Items', [])

        if not items:
            print(f"No requests found with status: {args.status}")
            return

        print(f"\n{'='*80}")
        print(f"  Approval Requests (status: {args.status}) — {len(items)} found")
        print(f"{'='*80}\n")

        for item in sorted(items, key=lambda x: x.get('createdAt', 0), reverse=True):
            print(f"  Request ID:   {item.get('requestId', 'N/A')}")
            print(f"  Action:       {item.get('actionKey', 'N/A')}")
            print(f"  Status:       {item.get('status', 'N/A')}")
            print(f"  Risk Level:   {item.get('riskLevel', 'N/A')}")
            print(f"  Requested By: {item.get('requestedBy', 'N/A')}")
            print(f"  Reason:       {item.get('reason', 'N/A')}")
            print(f"  Created:      {format_timestamp(item.get('createdAt'))}")
            print(f"  Expires:      {format_timestamp(item.get('ttl'))}")

            approvals = item.get('approvals', {})
            if approvals:
                print(f"  Approvals:")
                for approver, decision in approvals.items():
                    print(f"    - {approver}: {decision}")

            print(f"  {'-'*76}")

        print()

    except ClientError as e:
        print(f"Error scanning table: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
