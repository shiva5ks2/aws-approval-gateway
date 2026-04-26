"""
BypassAlertLambda — fires on any direct call to a protected action
that did not come through the executor role.

Trigger: EventBridge rule matching CloudTrail events for all protected actions.
Action:  If caller is NOT the executor role, publish alert to SNS.
"""

import json
import os
import logging

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ALERT_TOPIC_ARN = os.environ['ALERT_TOPIC_ARN']
EXECUTOR_ROLE_ARN = os.environ['EXECUTOR_ROLE_ARN']

sns = boto3.client('sns')


def handler(event, context):
    """
    Check if the CloudTrail event was initiated by the executor role.
    If not, this is a bypass — publish an alert.
    """
    logger.info("Received EventBridge event: %s", json.dumps(event))

    detail = event.get('detail', {})
    user_identity = detail.get('userIdentity', {})
    principal_arn = user_identity.get('arn', '')
    event_name = detail.get('eventName', 'Unknown')
    event_source = detail.get('eventSource', 'Unknown')
    event_time = detail.get('eventTime', 'Unknown')
    source_ip = detail.get('sourceIPAddress', 'Unknown')
    aws_region = detail.get('awsRegion', 'Unknown')
    account_id = user_identity.get('accountId', 'Unknown')

    # Check if the caller is the approved executor role
    if EXECUTOR_ROLE_ARN in principal_arn:
        logger.info(
            "Action %s was performed by executor role — no alert needed.",
            event_name
        )
        return {'status': 'OK', 'message': 'Executor role — no bypass detected'}

    # This is a bypass — someone called a protected action directly
    logger.warning(
        "BYPASS DETECTED: %s called by %s (not executor role)",
        event_name, principal_arn
    )

    alert_subject = f"[CRITICAL] Bypass Detected: {event_name} called outside approval gateway"

    alert_message = {
        'alertType': 'BYPASS_DETECTION',
        'severity': 'CRITICAL',
        'summary': f'Protected action {event_name} was called directly, bypassing the approval gateway.',
        'details': {
            'eventName': event_name,
            'eventSource': event_source,
            'eventTime': event_time,
            'callerArn': principal_arn,
            'callerType': user_identity.get('type', 'Unknown'),
            'sourceIPAddress': source_ip,
            'awsRegion': aws_region,
            'accountId': account_id,
            'userAgent': detail.get('userAgent', 'Unknown'),
            'requestParameters': detail.get('requestParameters', {}),
            'responseElements': detail.get('responseElements', {}),
            'errorCode': detail.get('errorCode'),
            'errorMessage': detail.get('errorMessage')
        },
        'recommendation': (
            'Investigate immediately. This action was not routed through the '
            'approval gateway. Check if the IAM deny policy and SCP are '
            'correctly applied to this principal.'
        )
    }

    sns.publish(
        TopicArn=ALERT_TOPIC_ARN,
        Subject=alert_subject[:100],  # SNS subject max 100 chars
        Message=json.dumps(alert_message, indent=2)
    )

    logger.info("Bypass alert published to %s", ALERT_TOPIC_ARN)

    return {
        'status': 'ALERT_SENT',
        'eventName': event_name,
        'callerArn': principal_arn
    }
