"""
Tests for BypassAlertLambda handler.
"""

import json
import os
import unittest
from unittest.mock import patch, MagicMock

os.environ['ALERT_TOPIC_ARN'] = 'arn:aws:sns:us-east-1:123456789012:SecurityAlerts'
os.environ['EXECUTOR_ROLE_ARN'] = 'arn:aws:iam::123456789012:role/ApprovalGatewayExecutorRole'


class TestBypassAlertHandler(unittest.TestCase):
    """Tests for the BypassAlertLambda handler."""

    @patch('handler.sns')
    def test_bypass_detected_publishes_alert(self, mock_sns):
        """Non-executor caller triggers alert."""
        from lambdas.bypass_alert.handler import handler

        event = {
            'detail': {
                'eventName': 'DeleteHostedZone',
                'eventSource': 'route53.amazonaws.com',
                'eventTime': '2024-01-15T10:30:00Z',
                'sourceIPAddress': '203.0.113.50',
                'awsRegion': 'us-east-1',
                'userAgent': 'aws-cli/2.0',
                'userIdentity': {
                    'arn': 'arn:aws:iam::123456789012:user/rogue-user',
                    'type': 'IAMUser',
                    'accountId': '123456789012'
                },
                'requestParameters': {'hostedZoneId': 'Z123'},
                'responseElements': {}
            }
        }

        result = handler(event, None)

        self.assertEqual(result['status'], 'ALERT_SENT')
        mock_sns.publish.assert_called_once()
        call_kwargs = mock_sns.publish.call_args[1]
        self.assertIn('CRITICAL', call_kwargs['Subject'])

    @patch('handler.sns')
    def test_executor_role_no_alert(self, mock_sns):
        """Executor role caller does NOT trigger alert."""
        from lambdas.bypass_alert.handler import handler

        event = {
            'detail': {
                'eventName': 'DeleteHostedZone',
                'eventSource': 'route53.amazonaws.com',
                'userIdentity': {
                    'arn': 'arn:aws:iam::123456789012:role/ApprovalGatewayExecutorRole/session',
                    'type': 'AssumedRole',
                    'accountId': '123456789012'
                }
            }
        }

        result = handler(event, None)

        self.assertEqual(result['status'], 'OK')
        mock_sns.publish.assert_not_called()

    @patch('handler.sns')
    def test_alert_message_contains_event_details(self, mock_sns):
        """Alert message includes full event context."""
        from lambdas.bypass_alert.handler import handler

        event = {
            'detail': {
                'eventName': 'TerminateInstances',
                'eventSource': 'ec2.amazonaws.com',
                'eventTime': '2024-01-15T10:30:00Z',
                'sourceIPAddress': '198.51.100.10',
                'awsRegion': 'us-west-2',
                'userIdentity': {
                    'arn': 'arn:aws:iam::123456789012:user/attacker',
                    'type': 'IAMUser',
                    'accountId': '123456789012'
                },
                'requestParameters': {
                    'instancesSet': {'items': [{'instanceId': 'i-1234567890abcdef0'}]}
                }
            }
        }

        result = handler(event, None)

        self.assertEqual(result['status'], 'ALERT_SENT')
        call_kwargs = mock_sns.publish.call_args[1]
        message = json.loads(call_kwargs['Message'])
        self.assertEqual(message['alertType'], 'BYPASS_DETECTION')
        self.assertEqual(message['details']['eventName'], 'TerminateInstances')
        self.assertEqual(message['details']['callerArn'],
                         'arn:aws:iam::123456789012:user/attacker')


if __name__ == '__main__':
    unittest.main()
