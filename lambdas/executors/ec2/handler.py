"""
EC2 Executor — handles ec2:DeleteVpc.

ec2:TerminateInstances is routine operational work and is not managed
by the gateway. ec2:DeleteSubnet is low-risk and reversible.

Trigger: Step Functions task invocation only.
Input:   { requestId, actionKey, parameters: { vpcId } }
"""

import logging
import sys
import os

import boto3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from base_executor import validate_and_execute

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event, context):
    """Execute EC2 actions after approval validation."""

    def execute(params):
        action = event['actionKey']
        ec2 = boto3.client('ec2')

        if action == 'ec2:DeleteVpc':
            vpc_id = params['vpcId']
            logger.info("Deleting VPC: %s", vpc_id)
            ec2.delete_vpc(VpcId=vpc_id)
            logger.info("Successfully deleted VPC: %s", vpc_id)

        else:
            raise ValueError(f"Unsupported EC2 action: {action}")

    return validate_and_execute(event, execute)
