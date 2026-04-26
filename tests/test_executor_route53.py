"""
Tests for Route53 executor Lambda.
"""

import os
import unittest
from unittest.mock import patch, MagicMock

os.environ['REQUESTS_TABLE'] = 'ApprovalRequests'


class TestRoute53Executor(unittest.TestCase):
    """Tests for the Route53 executor handler."""

    @patch('base_executor.requests_table')
    def test_happy_path_deletes_hosted_zone(self, mock_table):
        """Approved request successfully deletes hosted zone."""
        mock_table.get_item.return_value = {
            'Item': {
                'requestId': 'req-123',
                'status': 'APPROVED'
            }
        }

        with patch('boto3.client') as mock_boto:
            mock_route53 = MagicMock()
            mock_boto.return_value = mock_route53

            from lambdas.executors.route53.handler import handler

            event = {
                'requestId': 'req-123',
                'actionKey': 'route53:DeleteHostedZone',
                'parameters': {'hostedZoneId': 'Z1234567890'}
            }

            result = handler(event, None)

            self.assertEqual(result['status'], 'COMPLETED')
            self.assertEqual(result['requestId'], 'req-123')
            mock_table.update_item.assert_called_once()

    @patch('base_executor.requests_table')
    def test_rejects_non_approved_request(self, mock_table):
        """Non-APPROVED request raises exception."""
        mock_table.get_item.return_value = {
            'Item': {
                'requestId': 'req-123',
                'status': 'PENDING'
            }
        }

        from lambdas.executors.route53.handler import handler

        event = {
            'requestId': 'req-123',
            'actionKey': 'route53:DeleteHostedZone',
            'parameters': {'hostedZoneId': 'Z1234567890'}
        }

        with self.assertRaises(Exception) as ctx:
            handler(event, None)

        self.assertIn('not APPROVED', str(ctx.exception))

    @patch('base_executor.requests_table')
    def test_rejects_missing_request(self, mock_table):
        """Missing request raises exception."""
        mock_table.get_item.return_value = {}

        from lambdas.executors.route53.handler import handler

        event = {
            'requestId': 'req-nonexistent',
            'actionKey': 'route53:DeleteHostedZone',
            'parameters': {'hostedZoneId': 'Z1234567890'}
        }

        with self.assertRaises(Exception) as ctx:
            handler(event, None)

        self.assertIn('not found', str(ctx.exception))


if __name__ == '__main__':
    unittest.main()
