"""
Route53 Executor — handles route53:DeleteHostedZone.

Trigger: Step Functions task invocation only.
Input:   { requestId, actionKey, parameters: { hostedZoneId } }
"""

import logging
import sys
import os

import boto3

# Add parent directory to path for base_executor import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from base_executor import validate_and_execute

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event, context):
    """Execute route53:DeleteHostedZone after approval validation."""

    def execute(params):
        hosted_zone_id = params['hostedZoneId']
        logger.info("Deleting Route53 hosted zone: %s", hosted_zone_id)

        route53 = boto3.client('route53')

        # Verify the hosted zone exists before deletion
        route53.get_hosted_zone(Id=hosted_zone_id)

        route53.delete_hosted_zone(Id=hosted_zone_id)
        logger.info("Successfully deleted hosted zone: %s", hosted_zone_id)

    return validate_and_execute(event, execute)
