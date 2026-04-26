"""
ApproverCallbackLambda — handles approve/deny clicks from approver notifications.

Trigger: API Gateway GET /callback?taskToken=TOKEN&decision=approve|deny&approver=ARN
Output:  HTML confirmation page
"""

import json
import os
import time
import logging
import urllib.parse

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

REQUESTS_TABLE = os.environ['REQUESTS_TABLE']

dynamodb = boto3.resource('dynamodb')
sfn = boto3.client('stepfunctions')

requests_table = dynamodb.Table(REQUESTS_TABLE)


def build_html_response(title, message, success=True):
    """Build an HTML confirmation page for the approver."""
    color = '#2e7d32' if success else '#c62828'
    icon = '&#10004;' if success else '&#10008;'
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            display: flex; justify-content: center; align-items: center;
            min-height: 100vh; margin: 0; background: #f5f5f5;
        }}
        .card {{
            background: white; border-radius: 8px; padding: 40px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1); text-align: center;
            max-width: 480px;
        }}
        .icon {{ font-size: 48px; color: {color}; }}
        h1 {{ color: #333; margin: 16px 0 8px; }}
        p {{ color: #666; line-height: 1.6; }}
    </style>
</head>
<body>
    <div class="card">
        <div class="icon">{icon}</div>
        <h1>{title}</h1>
        <p>{message}</p>
    </div>
</body>
</html>"""


def handler(event, context):
    """
    Process an approver's decision from the callback URL.

    Validates the task token, sends success/failure to Step Functions,
    and updates the approvals map in DynamoDB.
    """
    logger.info("Received callback event: %s", json.dumps(event))

    # Extract query parameters from API Gateway event
    params = event.get('queryStringParameters') or {}
    task_token = params.get('taskToken')
    decision = params.get('decision', '').lower()
    approver = params.get('approver', 'unknown')

    # URL-decode the task token (it may be URL-encoded in the callback link)
    if task_token:
        task_token = urllib.parse.unquote(task_token)

    # --- Validate input ---
    if not task_token:
        return {
            'statusCode': 400,
            'headers': {'Content-Type': 'text/html'},
            'body': build_html_response(
                'Invalid Request',
                'Missing task token. This link may be malformed.',
                success=False
            )
        }

    if decision not in ('approve', 'deny'):
        return {
            'statusCode': 400,
            'headers': {'Content-Type': 'text/html'},
            'body': build_html_response(
                'Invalid Request',
                'Decision must be "approve" or "deny".',
                success=False
            )
        }

    # --- Send decision to Step Functions ---
    try:
        if decision == 'approve':
            sfn.send_task_success(
                taskToken=task_token,
                output=json.dumps({
                    'approved': True,
                    'approver': approver,
                    'timestamp': int(time.time())
                })
            )
            logger.info("Approval recorded from %s", approver)

            return {
                'statusCode': 200,
                'headers': {'Content-Type': 'text/html'},
                'body': build_html_response(
                    'Approved',
                    f'Your approval has been recorded. Approver: {approver}. '
                    'The workflow will proceed once all required approvals are received.'
                )
            }
        else:
            sfn.send_task_failure(
                taskToken=task_token,
                error='ApproverDenied',
                cause=f'Denied by {approver} at {int(time.time())}'
            )
            logger.info("Denial recorded from %s", approver)

            return {
                'statusCode': 200,
                'headers': {'Content-Type': 'text/html'},
                'body': build_html_response(
                    'Denied',
                    f'Your denial has been recorded. Approver: {approver}. '
                    'The workflow has been stopped.',
                    success=False
                )
            }

    except ClientError as e:
        error_code = e.response['Error']['Code']
        logger.error("Step Functions callback failed: %s — %s", error_code, e)

        if error_code in ('TaskTimedOut', 'TaskDoesNotExist', 'InvalidToken'):
            return {
                'statusCode': 400,
                'headers': {'Content-Type': 'text/html'},
                'body': build_html_response(
                    'Link Expired',
                    'This approval link has already been used or has expired. '
                    'Task tokens are single-use.',
                    success=False
                )
            }

        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'text/html'},
            'body': build_html_response(
                'Error',
                'An unexpected error occurred processing your decision. '
                'Please contact the gateway administrator.',
                success=False
            )
        }
