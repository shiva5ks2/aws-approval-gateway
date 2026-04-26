"""
IAM Executor — handles iam:DeleteRole.

iam:DetachRolePolicy and iam:DeletePolicy are routine IAM operations
and are not managed by the gateway.

Trigger: Step Functions task invocation only.
Input:   { requestId, actionKey, parameters: { roleName } }
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
    """Execute IAM actions after approval validation."""

    def execute(params):
        action = event['actionKey']
        iam = boto3.client('iam')

        if action == 'iam:DeleteRole':
            role_name = params['roleName']
            logger.info("Deleting IAM role: %s", role_name)
            iam.delete_role(RoleName=role_name)
            logger.info("Successfully deleted IAM role: %s", role_name)

        else:
            raise ValueError(f"Unsupported IAM action: {action}")

    return validate_and_execute(event, execute)
