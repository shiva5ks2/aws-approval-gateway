"""
ApprovalGatewayStack — CDK stack for the core approval gateway.

Creates: DynamoDB tables, SNS topics, SSM parameters, IAM roles,
Lambda functions, Step Functions state machine, API Gateway,
and EventBridge rules.
"""

from pathlib import Path

import aws_cdk as cdk
from aws_cdk import (
    aws_apigateway as apigw,
    aws_dynamodb as dynamodb,
    aws_events as events,
    aws_events_targets as targets,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_sns as sns,
    aws_ssm as ssm,
    aws_stepfunctions as sfn,
)
from constructs import Construct

# Paths relative to the CDK app root (infra/cdk/)
REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
LAMBDAS_DIR = REPO_ROOT / "lambdas"
STATE_MACHINE_ASL = REPO_ROOT / "infra" / "step-functions" / "state-machine.json"

# Protected actions — the 6 actions managed by the gateway
PROTECTED_ACTIONS = [
    "route53:DeleteHostedZone",
    "iam:DeleteRole",
    "rds:DeleteDBCluster",
    "rds:DeleteDBInstance",
    "ec2:DeleteVpc",
    "s3:DeleteBucket",
]

# EventBridge event names corresponding to the protected actions
PROTECTED_EVENT_NAMES = [
    "DeleteHostedZone",
    "DeleteRole",
    "DeleteDBCluster",
    "DeleteDBInstance",
    "DeleteVpc",
    "DeleteBucket",
]

PROTECTED_EVENT_SOURCES = [
    "aws.route53",
    "aws.iam",
    "aws.rds",
    "aws.ec2",
    "aws.s3",
]


# Executor definitions: service name -> source directory name
EXECUTORS = {
    "Route53": "route53",
    "IAM": "iam",
    "RDS": "rds",
    "EC2": "ec2",
    "S3": "s3",
}


class ApprovalGatewayStack(cdk.Stack):
    """Core Approval Gateway stack."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        approver_groups: list[str],
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ---------------------------------------------------------------------
        # DynamoDB tables
        # ---------------------------------------------------------------------
        requests_table = dynamodb.Table(
            self,
            "ApprovalRequests",
            table_name="ApprovalRequests",
            partition_key=dynamodb.Attribute(
                name="requestId", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            time_to_live_attribute="ttl",
            point_in_time_recovery=True,
            removal_policy=cdk.RemovalPolicy.RETAIN,
        )

        policies_table = dynamodb.Table(
            self,
            "ApprovalPolicies",
            table_name="ApprovalPolicies",
            partition_key=dynamodb.Attribute(
                name="actionKey", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            point_in_time_recovery=True,
            removal_policy=cdk.RemovalPolicy.RETAIN,
        )

        # ---------------------------------------------------------------------
        # SNS topics + SSM parameters
        # ---------------------------------------------------------------------
        approver_topics: dict[str, sns.Topic] = {}
        for group in approver_groups:
            topic = sns.Topic(
                self,
                f"ApproverTopic-{group}",
                topic_name=f"ApprovalGateway-Approvers-{group}",
                display_name=f"Approval Gateway - {group} Approvers",
            )
            approver_topics[group] = topic

            ssm.StringParameter(
                self,
                f"SSMApproverGroup-{group}",
                parameter_name=f"/approval-gateway/approver-groups/{group}",
                string_value=topic.topic_arn,
                description=f"SNS topic ARN for approver group: {group}",
            )

        alert_topic = sns.Topic(
            self,
            "SecurityAlertTopic",
            topic_name="ApprovalGateway-SecurityAlerts",
            display_name="Approval Gateway - Security Alerts (Bypass Detection)",
        )

        # ---------------------------------------------------------------------
        # IAM — Executor permissions boundary
        # ---------------------------------------------------------------------
        executor_boundary = iam.ManagedPolicy(
            self,
            "ExecutorPermissionsBoundary",
            managed_policy_name="ApprovalGatewayExecutorBoundary",
            statements=[
                iam.PolicyStatement(
                    sid="AllowProtectedActions",
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "route53:DeleteHostedZone",
                        "route53:GetHostedZone",
                        "iam:DeleteRole",
                        "rds:DeleteDBCluster",
                        "rds:DeleteDBInstance",
                        "rds:CreateDBSnapshot",
                        "ec2:DeleteVpc",
                        "s3:DeleteBucket",
                        "dynamodb:UpdateItem",
                        "dynamodb:GetItem",
                        "logs:CreateLogGroup",
                        "logs:CreateLogStream",
                        "logs:PutLogEvents",
                    ],
                    resources=["*"],
                ),
                iam.PolicyStatement(
                    sid="DenyPrivilegeEscalation",
                    effect=iam.Effect.DENY,
                    actions=[
                        "iam:CreateRole",
                        "iam:AttachRolePolicy",
                        "iam:PutRolePolicy",
                        "iam:PassRole",
                        "sts:AssumeRole",
                        "organizations:*",
                    ],
                    resources=["*"],
                ),
            ],
        )

        # ---------------------------------------------------------------------
        # IAM — Executor role
        # ---------------------------------------------------------------------
        executor_role = iam.Role(
            self,
            "ExecutorRole",
            role_name="ApprovalGatewayExecutorRole",
            assumed_by=iam.ServicePrincipal(
                "lambda.amazonaws.com",
                conditions={
                    "StringEquals": {"aws:SourceAccount": self.account},
                    "ArnLike": {
                        "aws:SourceArn": f"arn:aws:lambda:{self.region}:{self.account}:function:ApprovalGatewayExecutor-*"
                    },
                },
            ),
            permissions_boundary=executor_boundary,
        )

        # Grant executor role access to protected actions + DynamoDB + logs
        executor_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "route53:DeleteHostedZone",
                    "route53:GetHostedZone",
                    "iam:DeleteRole",
                    "rds:DeleteDBCluster",
                    "rds:DeleteDBInstance",
                    "rds:CreateDBSnapshot",
                    "ec2:DeleteVpc",
                    "s3:DeleteBucket",
                ],
                resources=["*"],
            )
        )
        requests_table.grant_read_write_data(executor_role)

        # ---------------------------------------------------------------------
        # Lambda — Executor functions
        # ---------------------------------------------------------------------
        executor_functions: dict[str, lambda_.Function] = {}
        base_executor_path = LAMBDAS_DIR / "executors" / "base_executor.py"

        for service_name, source_dir in EXECUTORS.items():
            asset_path = str(LAMBDAS_DIR / "executors" / source_dir)

            fn = lambda_.Function(
                self,
                f"Executor-{service_name}",
                function_name=f"ApprovalGatewayExecutor-{service_name}",
                runtime=lambda_.Runtime.PYTHON_3_12,
                handler="handler.handler",
                code=lambda_.Code.from_asset(
                    asset_path,
                    bundling=cdk.BundlingOptions(
                        image=lambda_.Runtime.PYTHON_3_12.bundling_image,
                        command=[
                            "bash", "-c",
                            "cp -r /asset-input/* /asset-output/ && "
                            "cp /asset-input/../base_executor.py /asset-output/",
                        ],
                    ),
                ),
                role=executor_role,
                timeout=cdk.Duration.seconds(300),
                memory_size=128,
                environment={
                    "REQUESTS_TABLE": requests_table.table_name,
                },
            )
            executor_functions[service_name] = fn

        # ---------------------------------------------------------------------
        # Step Functions — state machine
        # ---------------------------------------------------------------------
        sfn_role = iam.Role(
            self,
            "StepFunctionsRole",
            assumed_by=iam.ServicePrincipal("states.amazonaws.com"),
        )

        # Grant SFN permission to publish to all approver topics
        for topic in approver_topics.values():
            topic.grant_publish(sfn_role)

        # Grant SFN permission to invoke all executor Lambdas
        for fn in executor_functions.values():
            fn.grant_invoke(sfn_role)

        # Grant SFN permission to update DynamoDB
        requests_table.grant_read_write_data(sfn_role)

        # Load ASL and create state machine
        asl_body = STATE_MACHINE_ASL.read_text()

        state_machine = sfn.CfnStateMachine(
            self,
            "ApprovalWorkflow",
            state_machine_name="ApprovalGatewayWorkflow",
            definition_string=asl_body,
            role_arn=sfn_role.role_arn,
        )

        # ---------------------------------------------------------------------
        # Lambda — Wrapper
        # ---------------------------------------------------------------------
        wrapper_role = iam.Role(
            self,
            "WrapperRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                ),
            ],
        )

        requests_table.grant_read_write_data(wrapper_role)
        policies_table.grant_read_data(wrapper_role)

        wrapper_role.add_to_policy(
            iam.PolicyStatement(
                actions=["states:StartExecution"],
                resources=[state_machine.attr_arn],
            )
        )
        wrapper_role.add_to_policy(
            iam.PolicyStatement(
                actions=["ssm:GetParameter", "ssm:GetParametersByPath"],
                resources=[
                    f"arn:aws:ssm:{self.region}:{self.account}:parameter/approval-gateway/approver-groups/*"
                ],
            )
        )
        wrapper_role.add_to_policy(
            iam.PolicyStatement(
                actions=["lambda:GetFunction"],
                resources=[
                    f"arn:aws:lambda:{self.region}:{self.account}:function:ApprovalGatewayExecutor-*"
                ],
            )
        )

        wrapper_fn = lambda_.Function(
            self,
            "WrapperLambda",
            function_name="ApprovalGatewayWrapper",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.handler",
            code=lambda_.Code.from_asset(str(LAMBDAS_DIR / "wrapper")),
            role=wrapper_role,
            timeout=cdk.Duration.seconds(60),
            memory_size=128,
            environment={
                "STATE_MACHINE_ARN": state_machine.attr_arn,
                "REQUESTS_TABLE": requests_table.table_name,
                "POLICIES_TABLE": policies_table.table_name,
                "SSM_APPROVER_PREFIX": "/approval-gateway/approver-groups/",
            },
        )

        # ---------------------------------------------------------------------
        # Lambda — Approver Callback
        # ---------------------------------------------------------------------
        callback_role = iam.Role(
            self,
            "CallbackRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                ),
            ],
        )

        callback_role.add_to_policy(
            iam.PolicyStatement(
                actions=["states:SendTaskSuccess", "states:SendTaskFailure"],
                resources=[state_machine.attr_arn],
            )
        )
        requests_table.grant_read_write_data(callback_role)

        callback_fn = lambda_.Function(
            self,
            "CallbackLambda",
            function_name="ApprovalGatewayCallback",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.handler",
            code=lambda_.Code.from_asset(str(LAMBDAS_DIR / "approver-callback")),
            role=callback_role,
            timeout=cdk.Duration.seconds(60),
            memory_size=128,
            environment={
                "REQUESTS_TABLE": requests_table.table_name,
            },
        )

        # ---------------------------------------------------------------------
        # API Gateway — Callback endpoint
        # ---------------------------------------------------------------------
        api = apigw.RestApi(
            self,
            "CallbackApi",
            rest_api_name="ApprovalGatewayCallbackAPI",
            description="HTTPS callback endpoint for approver approve/deny decisions",
            endpoint_types=[apigw.EndpointType.REGIONAL],
        )

        callback_integration = apigw.LambdaIntegration(callback_fn)
        api.root.add_resource("callback").add_method("GET", callback_integration)

        # ---------------------------------------------------------------------
        # Lambda — Bypass Alert
        # ---------------------------------------------------------------------
        bypass_alert_role = iam.Role(
            self,
            "BypassAlertRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                ),
            ],
        )

        alert_topic.grant_publish(bypass_alert_role)

        bypass_alert_fn = lambda_.Function(
            self,
            "BypassAlertLambda",
            function_name="ApprovalGatewayBypassAlert",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.handler",
            code=lambda_.Code.from_asset(str(LAMBDAS_DIR / "bypass-alert")),
            role=bypass_alert_role,
            timeout=cdk.Duration.seconds(60),
            memory_size=128,
            environment={
                "ALERT_TOPIC_ARN": alert_topic.topic_arn,
                "EXECUTOR_ROLE_ARN": executor_role.role_arn,
            },
        )

        # ---------------------------------------------------------------------
        # EventBridge — Bypass detection rule
        # ---------------------------------------------------------------------
        events.Rule(
            self,
            "BypassDetectionRule",
            rule_name="ApprovalGatewayBypassDetection",
            description="Fires on any direct call to a gateway-protected API action via CloudTrail",
            event_pattern=events.EventPattern(
                source=PROTECTED_EVENT_SOURCES,
                detail_type=["AWS API Call via CloudTrail"],
                detail={"eventName": PROTECTED_EVENT_NAMES},
            ),
            targets=[targets.LambdaFunction(bypass_alert_fn)],
        )

        # ---------------------------------------------------------------------
        # CloudFormation outputs
        # ---------------------------------------------------------------------
        cdk.CfnOutput(
            self,
            "CallbackApiUrl",
            value=api.url_for_path("/callback"),
            description="API Gateway callback URL for approval notification templates",
        )

        cdk.CfnOutput(
            self,
            "StateMachineArn",
            value=state_machine.attr_arn,
            description="Step Functions state machine ARN",
        )

        cdk.CfnOutput(
            self,
            "AlertTopicArn",
            value=alert_topic.topic_arn,
            description="SNS topic ARN for security bypass alerts",
        )

        cdk.CfnOutput(
            self,
            "RequestsTableName",
            value=requests_table.table_name,
            description="DynamoDB table name for approval requests",
        )
