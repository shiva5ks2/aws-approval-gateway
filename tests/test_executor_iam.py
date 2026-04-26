"""
Tests for IAM executor Lambda.
"""

import os
import unittest
from unittest.mock import patch, MagicMock

os.environ['REQUESTS_TABLE'] = 'ApprovalRequests'


class TestIAMExecutor(unittest.TestCase):
    """Tests for the IAM executor handler."""

    @patch('base_executor.requests_table')
    def test_delete_role(self, mock_table):
        """Approved DeleteRole request succeeds."""
        mock_table.get_item.return_value = {
            'Item': {'requestId': 'req-123', 'status': 'APPROVED'}
        }

        with patch('boto3.client') as mock_boto:
            mock_iam = MagicMock()
            mock_boto.return_value = mock_iam

            from lambdas.executors.iam.handler import handler

            event = {
                'requestId': 'req-123',
                'actionKey': 'iam:DeleteRole',
                'parameters': {'roleName': 'TestRole'}
            }

            result = handler(event, None)
            self.assertEqual(result['status'], 'COMPLETED')

    @patch('base_executor.requests_table')
    def test_unsupported_action_raises(self, mock_table):
        """Unsupported IAM action raises ValueError."""
        mock_table.get_item.return_value = {
            'Item': {'requestId': 'req-789', 'status': 'APPROVED'}
        }

        from lambdas.executors.iam.handler import handler

        event = {
            'requestId': 'req-789',
            'actionKey': 'iam:DetachRolePolicy',
            'parameters': {}
        }

        with self.assertRaises(ValueError):
            handler(event, None)


if __name__ == '__main__':
    unittest.main()
