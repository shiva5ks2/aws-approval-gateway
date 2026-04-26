"""
WrapperLambda — single human-facing entry point for all protected actions.

Trigger: Direct invocation via CLI, internal tool, or console.
Input:   { actionKey, parameters, reason, requestedBy }
Output:  { statusCode: 202, requestId, message }
"""

import json
import os
import time
import uuid
import logging

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Environment variables
STATE_MACHINE_ARN = os.environ['STATE_MACHINE_ARN']
REQUESTS_TABLE = os.environ['REQUESTS_TABLE']
POLICIES_TABLE = os.environ['POLICIES_TABLE']
SSM_APPROVER_PREFIX = os.environ.get('SSM_APPROVER_PREFIX', '/approval-gateway/approver-groups/')

# AWS clients
dynamodb = boto3.resource('dynamodb')
sfn = boto3.client('stepfunctions')
ssm = boto3.client('ssm')
lambda_client = boto3.client('lambda')

requests_table = dynamodb.Table(REQUESTS_TABLE)
policies_table = dynamodb.Table(POLICIES_TABLE)


def resolve_approver_topics(approver_groups):
    """Resolve approver group names to SNS topic ARNs via SSM Parameter Store."""
    topic_arns = []
    for group in approver_groups:
        param_name = f"{SSM_APPROVER_PREFIX}{group}"
        try:
            response = ssm.get_parameter(Name=param_name)
            topic_arns.append(response['Parameter']['Value'])
        except ClientError as e:
            logger.error("Failed to resolve approver group '%s': %s", group, e)
            raise ValueError(f"Could not resolve approver group: {group}") from e
    return topic_arns


def validate_executor_exists(executor_arn):
    """Verify the executor Lambda function exists before starting the workflow."""
    try:
        lambda_client.get_function(FunctionName=executor_arn)
    except ClientError as e:
        logger.error("Executor Lambda not found: %s — %s", executor_arn, e)
        raise ValueError(f"Executor Lambda does not exist: {executor_arn}") from e


def handler(event, context):
    """
    Main entry point.

    Looks up the policy for the requested action, validates it,
    writes an ApprovalRequests record, and starts the Step Functions workflow.
    """
    logger.info("Received request: %s", json.dumps(event))

    # --- Validate input ---
    action_key = event.get('actionKey')
    parameters = event.get('parameters')
    requested_by = event.get('requestedBy', 'unknown')
    reason = event.get('reason', 'No reason provided')

    if not action_key:
        return {
            'statusCode': 400,
            'error': 'Missing required field: actionKey'
        }

    if not parameters:
        return {
            'statusCode': 400,
            'error': 'Missing required field: parameters'
        }

    # --- Look up policy ---
    policy_response = policies_table.get_item(Key={'actionKey': action_key})
    policy = policy_response.get('Item')

    if not policy:
        logger.warning("No approval policy found for action: %s", action_key)
        return {
            'statusCode': 404,
            'error': f'No approval policy found for: {action_key}'
        }

    if not policy.get('enabled', False):
        logger.warning("Approval policy is disabled for action: %s", action_key)
        return {
            'statusCode': 403,
            'error': f'Approval policy is disabled for: {action_key}'
        }

    # --- Validate executor exists ---
    executor_arn = policy['executorArn']
    validate_executor_exists(executor_arn)

    # --- Resolve approver SNS topics ---
    approver_groups = policy['approverGroups']
    approver_topic_arns = resolve_approver_topics(approver_groups)

    # --- Write approval request to DynamoDB ---
    request_id = str(uuid.uuid4())
    now = int(time.time())
    ttl_hours = int(policy['ttlHours'])

    requests_table.put_item(Item={
        'requestId': request_id,
        'actionKey': action_key,
        'parameters': parameters,
        'requestedBy': requested_by,
        'reason': reason,
        'status': 'PENDING',
        'riskLevel': policy['riskLevel'],
        'executorArn': executor_arn,
        'approvals': {},
        'createdAt': now,
        'ttl': now + (ttl_hours * 3600)
    })

    logger.info("Created approval request %s for %s (risk: %s)",
                request_id, action_key, policy['riskLevel'])

    # --- Start Step Functions execution ---
    sfn_input = {
        'requestId': request_id,
        'actionKey': action_key,
        'parameters': parameters,
        'requestedBy': requested_by,
        'reason': reason,
        'requiredApprovals': int(policy['requiredApprovals']),
        'approverTopicArns': approver_topic_arns,
        'executorArn': executor_arn,
        'ttlSeconds': ttl_hours * 3600,
        'requireMFA': policy.get('requireMFA', True)
    }

    sfn.start_execution(
        stateMachineArn=STATE_MACHINE_ARN,
        name=request_id,
        input=json.dumps(sfn_input)
    )

    logger.info("Started Step Functions execution for request %s", request_id)

    return {
        'statusCode': 202,
        'requestId': request_id,
        'message': f'Approval workflow started for {action_key}. Risk: {policy["riskLevel"]}'
    }
