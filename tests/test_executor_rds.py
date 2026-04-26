"""
Tests for RDS executor Lambda.
"""

import os
import unittest
from unittest.mock import patch, MagicMock

os.environ['REQUESTS_TABLE'] = 'ApprovalRequests'


class TestRDSExecutor(unittest.TestCase):
    """Tests for the RDS executor handler."""

    @patch('base_executor.requests_table')
    def test_delete_db_cluster_takes_snapshot(self, mock_table):
        """DeleteDBCluster always takes a final snapshot."""
        mock_table.get_item.return_value = {
            'Item': {'requestId': 'req-123', 'status': 'APPROVED'}
        }

        with patch('boto3.client') as mock_boto:
            mock_rds = MagicMock()
            mock_boto.return_value = mock_rds

            from lambdas.executors.rds.handler import handler

            event = {
                'requestId': 'req-123',
                'actionKey': 'rds:DeleteDBCluster',
                'parameters': {'dbClusterIdentifier': 'my-cluster'}
            }

            result = handler(event, None)

            self.assertEqual(result['status'], 'COMPLETED')
            call_kwargs = mock_rds.delete_db_cluster.call_args[1]
            self.assertFalse(call_kwargs['SkipFinalSnapshot'])
            self.assertTrue(
                call_kwargs['FinalDBSnapshotIdentifier'].startswith(
                    'approval-gateway-final-my-cluster-'
                )
            )

    @patch('base_executor.requests_table')
    def test_delete_db_instance_takes_snapshot(self, mock_table):
        """DeleteDBInstance always takes a final snapshot."""
        mock_table.get_item.return_value = {
            'Item': {'requestId': 'req-456', 'status': 'APPROVED'}
        }

        with patch('boto3.client') as mock_boto:
            mock_rds = MagicMock()
            mock_boto.return_value = mock_rds

            from lambdas.executors.rds.handler import handler

            event = {
                'requestId': 'req-456',
                'actionKey': 'rds:DeleteDBInstance',
                'parameters': {'dbInstanceIdentifier': 'my-instance'}
            }

            result = handler(event, None)

            self.assertEqual(result['status'], 'COMPLETED')
            call_kwargs = mock_rds.delete_db_instance.call_args[1]
            self.assertFalse(call_kwargs['SkipFinalSnapshot'])

    @patch('base_executor.requests_table')
    def test_rejects_non_approved(self, mock_table):
        """Non-APPROVED request is rejected."""
        mock_table.get_item.return_value = {
            'Item': {'requestId': 'req-789', 'status': 'DENIED'}
        }

        from lambdas.executors.rds.handler import handler

        event = {
            'requestId': 'req-789',
            'actionKey': 'rds:DeleteDBCluster',
            'parameters': {'dbClusterIdentifier': 'my-cluster'}
        }

        with self.assertRaises(Exception) as ctx:
            handler(event, None)

        self.assertIn('not APPROVED', str(ctx.exception))


if __name__ == '__main__':
    unittest.main()
