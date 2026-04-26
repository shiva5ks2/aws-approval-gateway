"""
Tests for ApproverCallbackLambda handler.
"""

import json
import os
import unittest
from unittest.mock import patch, MagicMock

os.environ['REQUESTS_TABLE'] = 'ApprovalRequests'


class TestApproverCallbackHandler(unittest.TestCase):
    """Tests for the ApproverCallbackLambda handler."""

    @patch('handler.sfn')
    def test_approve_sends_task_success(self, mock_sfn):
        """Approve decision calls SendTaskSuccess."""
        from lambdas.approver_callback.handler import handler

        event = {
            'queryStringParameters': {
                'taskToken': 'test-token-123',
                'decision': 'approve',
                'approver': 'arn:aws:iam::123456789012:user/approver1'
            }
        }

        result = handler(event, None)

        self.assertEqual(result['statusCode'], 200)
        self.assertIn('Approved', result['body'])
        mock_sfn.send_task_success.assert_called_once()

    @patch('handler.sfn')
    def test_deny_sends_task_failure(self, mock_sfn):
        """Deny decision calls SendTaskFailure."""
        from lambdas.approver_callback.handler import handler

        event = {
            'queryStringParameters': {
                'taskToken': 'test-token-123',
                'decision': 'deny',
                'approver': 'arn:aws:iam::123456789012:user/approver1'
            }
        }

        result = handler(event, None)

        self.assertEqual(result['statusCode'], 200)
        self.assertIn('Denied', result['body'])
        mock_sfn.send_task_failure.assert_called_once()

    def test_missing_task_token_returns_400(self):
        """Missing taskToken returns 400."""
        from lambdas.approver_callback.handler import handler

        event = {
            'queryStringParameters': {
                'decision': 'approve',
                'approver': 'arn:aws:iam::123456789012:user/approver1'
            }
        }

        result = handler(event, None)
        self.assertEqual(result['statusCode'], 400)

    def test_invalid_decision_returns_400(self):
        """Invalid decision value returns 400."""
        from lambdas.approver_callback.handler import handler

        event = {
            'queryStringParameters': {
                'taskToken': 'test-token-123',
                'decision': 'maybe',
                'approver': 'arn:aws:iam::123456789012:user/approver1'
            }
        }

        result = handler(event, None)
        self.assertEqual(result['statusCode'], 400)

    def test_null_query_params_returns_400(self):
        """Null queryStringParameters returns 400."""
        from lambdas.approver_callback.handler import handler

        event = {'queryStringParameters': None}
        result = handler(event, None)
        self.assertEqual(result['statusCode'], 400)


if __name__ == '__main__':
    unittest.main()
