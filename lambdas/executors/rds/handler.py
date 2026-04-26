"""
RDS Executor — handles rds:DeleteDBCluster, rds:DeleteDBInstance.

Always takes a final snapshot before deletion for safety.

Trigger: Step Functions task invocation only.
Input:   { requestId, actionKey, parameters }
"""

import logging
import sys
import os
import time

import boto3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from base_executor import validate_and_execute

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event, context):
    """Execute RDS actions after approval validation."""

    def execute(params):
        action = event['actionKey']
        rds = boto3.client('rds')
        timestamp = int(time.time())

        if action == 'rds:DeleteDBCluster':
            cluster_id = params['dbClusterIdentifier']
            snapshot_id = f"approval-gateway-final-{cluster_id}-{timestamp}"
            logger.info("Deleting RDS cluster: %s (final snapshot: %s)",
                        cluster_id, snapshot_id)
            rds.delete_db_cluster(
                DBClusterIdentifier=cluster_id,
                SkipFinalSnapshot=False,
                FinalDBSnapshotIdentifier=snapshot_id
            )
            logger.info("Successfully initiated deletion of RDS cluster: %s",
                        cluster_id)

        elif action == 'rds:DeleteDBInstance':
            instance_id = params['dbInstanceIdentifier']
            snapshot_id = f"approval-gateway-final-{instance_id}-{timestamp}"
            logger.info("Deleting RDS instance: %s (final snapshot: %s)",
                        instance_id, snapshot_id)
            rds.delete_db_instance(
                DBInstanceIdentifier=instance_id,
                SkipFinalSnapshot=False,
                FinalDBSnapshotIdentifier=snapshot_id
            )
            logger.info("Successfully initiated deletion of RDS instance: %s",
                        instance_id)

        else:
            raise ValueError(f"Unsupported RDS action: {action}")

    return validate_and_execute(event, execute)
