"""
S3 Executor — handles s3:DeleteBucket.

Trigger: Step Functions task invocation only.
Input:   { requestId, actionKey, parameters: { bucketName } }
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
    """Execute s3:DeleteBucket after approval validation."""

    def execute(params):
        bucket_name = params['bucketName']
        logger.info("Deleting S3 bucket: %s", bucket_name)

        s3 = boto3.client('s3')

        # Note: Bucket must be empty before deletion.
        # The caller is responsible for emptying the bucket first,
        # or this will fail with BucketNotEmpty.
        s3.delete_bucket(Bucket=bucket_name)
        logger.info("Successfully deleted S3 bucket: %s", bucket_name)

    return validate_and_execute(event, execute)
