"""
Tests for WrapperLambda handler.
"""

import json
import os
import unittest
from unittest.mock import patch, MagicMock

# Set environment variables before importing handler
os.environ['STATE_MACHINE_ARN'] = 'arn:aws:states:us-east-1:123456789012:stateMachine:ApprovalGatewayWorkflow'
os.environ['REQUESTS_TABLE'] = 'ApprovalRequests'
os.environ['POLICIES_TABLE'] = 'ApprovalPolicies'
os.environ['SSM_APPROVER_PREFIX'] = '/approval-gateway/approver-groups/'


class TestWrapperHandler(unittest.TestCase):
    """Tests for the WrapperLambda handler."""

    @patch('handler.lambda_client')
    @patch('handler.sfn')
    @patch('handler.ssm')
    @patch('handler.requests_table')
    @patch('handler.policies_table')
    def test_happy_path_returns_202(self, mock_policies, mock_requests,
                                     mock_ssm, mock_sfn, mock_lambda):
        """Successful request returns 202 with requestId."""
        from lambdas.wrapper.handler import handler

        mock_policies.get_item.return_value = {
            'Item': {
                'actionKey': 'route53:DeleteHostedZone',
                'riskLevel': 'CRITICAL',
                'requiredApprovals': 2,
                'approverGroups': ['team-lead', 'security'],
                'ttlHours': 24,
                'executorArn': 'arn:aws:lambda:us-east-1:123456789012:function:Executor-Route53',
                'requireMFA': True,
                'enabled': True
            }
        }

        mock_ssm.get_parameter.side_effect = [
            {'Parameter': {'Value': 'arn:aws:sns:us-east-1:123456789012:TeamLead'}},
            {'Parameter': {'Value': 'arn:aws:sns:us-east-1:123456789012:Security'}}
        ]

        event = {
            'actionKey': 'route53:DeleteHostedZone',
            'parameters': {'hostedZoneId': 'Z1234567890'},
            'requestedBy': 'arn:aws:iam::123456789012:user/testuser',
            'reason': 'Decommissioning old zone'
        }

        result = handler(event, None)

        self.assertEqual(result['statusCode'], 202)
        self.assertIn('requestId', result)
        self.assertIn('Approval workflow started', result['message'])
        mock_requests.put_item.assert_called_once()
        mock_sfn.start_execution.assert_called_once()

    @patch('handler.policies_table')
    def test_missing_action_key_returns_400(self, mock_policies):
        """Missing actionKey returns 400."""
        from lambdas.wrapper.handler import handler

        result = handler({'parameters': {'foo': 'bar'}}, None)
        self.assertEqual(result['statusCode'], 400)
        self.assertIn('actionKey', result['error'])

    @patch('handler.policies_table')
    def test_missing_parameters_returns_400(self, mock_policies):
        """Missing parameters returns 400."""
        from lambdas.wrapper.handler import handler

        result = handler({'actionKey': 'route53:DeleteHostedZone'}, None)
        self.assertEqual(result['statusCode'], 400)
        self.assertIn('parameters', result['error'])

    @patch('handler.policies_table')
    def test_unknown_action_returns_404(self, mock_policies):
        """Unknown actionKey returns 404."""
        from lambdas.wrapper.handler import handler

        mock_policies.get_item.return_value = {}

        event = {
            'actionKey': 'unknown:Action',
            'parameters': {'foo': 'bar'}
        }

        result = handler(event, None)
        self.assertEqual(result['statusCode'], 404)

    @patch('handler.policies_table')
    def test_disabled_policy_returns_403(self, mock_policies):
        """Disabled policy returns 403."""
        from lambdas.wrapper.handler import handler

        mock_policies.get_item.return_value = {
            'Item': {
                'actionKey': 'route53:DeleteHostedZone',
                'enabled': False
            }
        }

        event = {
            'actionKey': 'route53:DeleteHostedZone',
            'parameters': {'hostedZoneId': 'Z123'}
        }

        result = handler(event, None)
        self.assertEqual(result['statusCode'], 403)


if __name__ == '__main__':
    unittest.main()
