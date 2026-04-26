"""
Base executor — shared validation and DynamoDB update logic for all executor Lambdas.

Every executor Lambda calls validate_and_execute() with an action_handler function.
This ensures:
  1. The request status is re-validated as APPROVED in DynamoDB before execution.
  2. The status is updated to COMPLETED after successful execution.
  3. Consistent error handling and logging across all executors.
"""

import os
import time
import logging

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

REQUESTS_TABLE = os.environ['REQUESTS_TABLE']

dynamodb = boto3.resource('dynamodb')
requests_table = dynamodb.Table(REQUESTS_TABLE)


def validate_and_execute(event, action_handler):
    """
    Re-validate that the request is APPROVED, execute the action,
    and update the status to COMPLETED.

    Args:
        event: Step Functions payload with requestId, actionKey, parameters.
        action_handler: Callable that takes (parameters) and performs the AWS API call.

    Returns:
        dict with status, requestId, and actionKey.

    Raises:
        Exception: If the request is not in APPROVED status.
    """
    request_id = event['requestId']
    action_key = event['actionKey']

    logger.info("Executor invoked for request %s (action: %s)", request_id, action_key)

    # Re-validate status in DynamoDB — defense in depth
    response = requests_table.get_item(Key={'requestId': request_id})
    item = response.get('Item')

    if not item:
        error_msg = f"Request {request_id} not found in DynamoDB"
        logger.error(error_msg)
        raise Exception(error_msg)

    current_status = item.get('status')
    if current_status != 'APPROVED':
        error_msg = (
            f"Aborting: request {request_id} is not APPROVED "
            f"(current status: {current_status})"
        )
        logger.error(error_msg)
        raise Exception(error_msg)

    # Execute the action
    logger.info("Executing action %s for request %s", action_key, request_id)
    action_handler(event['parameters'])
    logger.info("Action %s completed successfully for request %s", action_key, request_id)

    # Update status to COMPLETED
    requests_table.update_item(
        Key={'requestId': request_id},
        UpdateExpression='SET #s = :s, completedAt = :t',
        ExpressionAttributeNames={'#s': 'status'},
        ExpressionAttributeValues={
            ':s': 'COMPLETED',
            ':t': int(time.time())
        }
    )

    logger.info("Request %s marked as COMPLETED", request_id)

    return {
        'status': 'COMPLETED',
        'requestId': request_id,
        'actionKey': action_key
    }
