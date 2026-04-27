# Homework — Landscape Analysis

Research date: April 2026

---

## 1. Similar projects and tools

### Direct ancestor

**[`aws-samples/automating-a-security-incident-with-step-functions`](https://github.com/aws-samples/automating-a-security-incident-with-step-functions)** — 19 stars, 16 forks. This is the repo cited in the README as the inspiration. It demonstrates a Step Functions + SNS + API Gateway pattern for adding a manual approval step to an automated security incident response. It is a single-action proof of concept — one approval flow, one action, no policy registry, no enforcement layer. The approval gateway extends this into a generic, multi-action, multi-approver framework with IAM/SCP enforcement.

**[`aws-samples/aws-step-functions-using-it-automation`](https://github.com/aws-samples/aws-step-functions-using-it-automation)** — 13 stars. Similar pattern: Step Functions for IT automation with human approval. Single-purpose, not a reusable framework.

### AWS-native services

**AWS Systems Manager Change Manager** — The closest AWS-managed equivalent. Enterprise change management with approval workflows, change templates, Automation runbooks, and multi-account support via Organizations. **Critical finding: AWS announced Change Manager is no longer open to new customers as of November 7, 2025.** Existing customers can continue using it, but no new sign-ups. This creates a genuine market gap for approval workflow tooling on AWS. Change Manager was also heavier than what most teams need — it required SSM Automation runbooks, change templates, and a delegated administrator setup.

**AWS CodePipeline manual approval actions** — CodePipeline supports manual approval stages that pause pipeline execution until a human approves or rejects. However, this is scoped to CI/CD pipelines. You cannot use it to gate arbitrary runtime API calls. It also has a hard 7-day timeout and no multi-approver fan-out.

**AWS Control Tower controls** — Preventive (SCP-based), detective (Config-based), and proactive (CloudFormation Hook-based). Control Tower also now supports Resource Control Policies (RCPs) as of late 2024. These are all enforcement mechanisms — they block or detect, but none provide an approval workflow. An action is either allowed or denied; there is no "allowed after approval" state.

**AWS CloudFormation Hooks / Guard** — Preventive guardrails that evaluate templates at provisioning time (preCreate, preUpdate). They operate at the IaC layer, not at runtime. They cannot intercept a direct API call like `aws route53 delete-hosted-zone`.

**AWS Verified Permissions / Cedar** — Fine-grained authorization service using the Cedar policy language. Designed for application-level authorization (can user X perform action Y on resource Z?). It is a policy decision point, not an approval workflow. It answers "is this allowed?" not "should we ask someone first?" You could theoretically build an approval workflow on top of it, but that is not what it provides out of the box.

### Policy-as-code tools

**HashiCorp Sentinel** — Policy-as-code framework integrated into Terraform Cloud/Enterprise. Evaluates policies during `terraform plan` and `terraform apply`. Operates at the IaC layer — it gates infrastructure provisioning, not runtime API calls. If someone calls `aws rds delete-db-cluster` directly via CLI, Sentinel has no visibility.

**Open Policy Agent (OPA)** — General-purpose policy engine. Can be used with Terraform (via `conftest`), Kubernetes admission control, or custom integrations. Same limitation as Sentinel: it evaluates policies at decision points you wire up. It does not intercept AWS API calls at runtime unless you build a proxy or wrapper around every API call.

**[`aws-samples/aws-infra-policy-as-code-with-terraform`](https://github.com/aws-samples/aws-infra-policy-as-code-with-terraform)** — OPA-based preventive controls for Terraform AWS deployments. IaC-layer only.

### IaC approval workflow tools

**[Atlantis](https://github.com/runatlantis/atlantis)** — Open-source Terraform pull request automation. Runs `terraform plan` on PRs, requires approval before `terraform apply`. Very popular (7k+ stars). But it is a PR-based workflow for Terraform — it does not protect against direct API calls or console actions.

**Spacelift / env0 / Scalr** — Commercial IaC management platforms with approval workflows, policy enforcement, and drift detection. All operate at the Terraform/OpenTofu layer. Same limitation: they gate IaC deployments, not runtime API calls.

### Just-in-time (JIT) access tools

**Sym** — Defines just-in-time access workflows in code (Terraform provider + Python SDK). Focuses on temporary role elevation — "give me admin access for 30 minutes." The approval is for assuming a role, not for performing a specific action. Last PyPI release was January 2024; unclear if actively maintained.

**Indent / Opal / StrongDM / hoop.dev** — JIT access platforms that grant time-bound access to roles, databases, servers, or Kubernetes clusters. The approval is "can I have access to X?" not "can I delete resource Y?" They operate at the identity layer (who can assume what role) rather than the action layer (what specific API call is being made).

**AWS IAM Identity Center temporary elevated access** — AWS's own JIT access mechanism. Grants time-bound permission sets. Same identity-layer pattern — you get a role for N hours, not approval for a specific action.

### Cloud governance platforms

**Turbot Guardrails** — Enterprise cloud governance platform. Detects compliance violations, enforces policies, and can auto-remediate. It is detection and enforcement, not approval workflow. It can block an action or alert on it, but it does not route it through a human approval process.

**Steampipe / Powerpipe** — Open-source tools for querying cloud resources and running compliance benchmarks. Read-only — they detect and report, they do not enforce or approve.

### ChatOps approval tools

**[`aws-samples/chatops-slack`](https://github.com/aws-samples/chatops-slack)** — AWS sample for Slack-based ChatOps. Basic pattern, not an approval framework.

**[`ykarakita/code-pipeline-slack-approver`](https://github.com/ykarakita/code-pipeline-slack-approver)** — Slack-based approval for CodePipeline. Scoped to CI/CD pipelines only.

**AWS Chatbot** — Managed service for Slack/Teams integration with AWS. Can forward SNS notifications and run read-only commands. Does not provide an approval workflow framework.

---

## 2. What makes this repo different

### The gap it fills

There is a specific gap in the AWS ecosystem that no existing tool addresses cleanly:

> **Runtime, action-level approval for destructive AWS API calls — not at the IaC layer, not at the identity layer, but at the API call layer.**

Every tool in the landscape falls into one of these categories:

| Layer | Tools | What they gate |
|---|---|---|
| IaC / provisioning | Sentinel, OPA, Atlantis, Spacelift, env0, CloudFormation Hooks | `terraform apply`, CloudFormation stack operations |
| Identity / access | Sym, Indent, Opal, StrongDM, IAM Identity Center JIT | Who can assume what role, for how long |
| Compliance / detection | Turbot Guardrails, Steampipe, AWS Config, Control Tower detective controls | After-the-fact detection and alerting |
| Enforcement / deny | SCPs, RCPs, IAM deny policies, Control Tower preventive controls | Binary allow/deny — no approval path |
| CI/CD pipeline | CodePipeline manual approval | Pipeline stage gates only |

This repo operates at a layer none of them cover: **runtime API-level approval with enforcement**. It denies the action by default (IAM + SCP), provides a structured approval workflow to authorize it, and then executes it through a controlled executor role.

### Specific differentiators

1. **Data-driven policy registry.** Adding a new protected action is a DynamoDB entry, not a code change (with the caveat that the IAM deny policy and SCP still need manual updates — the README is honest about this). The workflow logic, approver fan-out, TTL, and executor routing all come from the policy record.

2. **Multi-approver fan-out with Step Functions Map state.** The same state machine handles 1, 2, or 3 approvers dynamically. Most approval patterns are single-approver or require a new workflow definition per approval topology.

3. **Dual enforcement (IAM deny + SCP) with explicit threat model.** The README includes a threat matrix showing what each layer protects against. Most projects either use IAM or SCP, not both with a documented rationale for the combination.

4. **Bypass detection as a first-class feature.** EventBridge watches CloudTrail for any call to a protected action by a non-executor principal. This is not an afterthought — it is part of the architecture, with a dedicated Lambda and SNS topic.

5. **Executor re-validation.** The executor Lambda re-reads the DynamoDB record and confirms APPROVED status before calling the AWS API. This is defense in depth against race conditions or state machine bugs.

6. **Honest documentation of limitations.** The README explicitly documents what is not automated, what requires manual work, and why. The CloudFormation interaction problem is documented with five solution options and their tradeoffs. This level of operational honesty is rare in open-source projects.

### Timing advantage

AWS SSM Change Manager closing to new customers (November 2025) creates a gap. Teams that need approval workflows for operational changes now have fewer managed options. This repo is not a Change Manager replacement (it is narrower in scope), but it addresses the same core need: "how do I require human approval before a destructive action executes?"

---

## 3. Alternative AWS stacks

Could the same pattern be implemented with a different AWS architecture? Yes, with tradeoffs.

### Alternative A — EventBridge + SQS + Lambda (no Step Functions)

**Architecture:** CloudTrail → EventBridge rule → SQS queue (pending approvals) → Lambda (notification sender) → API Gateway (callback) → Lambda (approval processor) → Lambda (executor).

**Pros:**
- Simpler — no state machine definition to maintain.
- SQS provides built-in retry and dead-letter queue handling.
- Cheaper for low-volume workloads (no Step Functions state transition charges).

**Cons:**
- You lose the visual workflow and built-in state tracking that Step Functions provides.
- Multi-approver fan-out requires custom coordination logic (tracking which approvers have responded, handling partial approvals).
- TTL/timeout handling must be built manually (SQS visibility timeout or a scheduled Lambda).
- No built-in `waitForTaskToken` equivalent — you have to build your own correlation between the callback and the pending request.
- Error handling and retry logic is your responsibility.

**Verdict:** Viable for single-approver workflows. The complexity of multi-approver coordination makes Step Functions the better choice for this use case. Step Functions was designed for exactly this pattern (long-running workflows with human interaction).

### Alternative B — CodePipeline with custom actions

**Architecture:** Wrap each protected action as a CodePipeline pipeline. The pipeline has a source stage (triggered by the request), a manual approval stage, and a deploy stage (executor Lambda).

**Pros:**
- Manual approval is a built-in CodePipeline feature with SNS integration.
- Pipeline execution history provides an audit trail.
- Familiar to teams already using CodePipeline.

**Cons:**
- CodePipeline is designed for CI/CD, not operational approval workflows. Using it this way is a misuse of the service.
- Hard 7-day approval timeout (not configurable per action).
- Single approver per approval action (no multi-approver fan-out).
- Creating a pipeline per protected action is operationally heavy.
- Pipeline execution is slower (minutes to start) compared to Step Functions (seconds).
- No data-driven policy registry — each pipeline is a separate infrastructure resource.

**Verdict:** Not recommended. The impedance mismatch between CodePipeline's CI/CD model and an operational approval workflow creates more problems than it solves.

### Alternative C — AWS Verified Permissions + custom workflow

**Architecture:** Use Cedar policies in Verified Permissions to define who can approve what. Build a custom workflow (Lambda + DynamoDB) that checks Verified Permissions for authorization decisions, then executes the action.

**Pros:**
- Cedar policies are expressive and support ABAC (attribute-based access control).
- Verified Permissions provides policy management, versioning, and an evaluation simulator.
- Could enable more complex approval rules (e.g., "any two members of the security group, but not the same person who submitted the request").

**Cons:**
- Verified Permissions is an authorization engine, not a workflow engine. You still need to build the entire approval workflow (notification, callback, state tracking, timeout, execution).
- Adds a dependency on a relatively new AWS service.
- The approval workflow is the hard part — the authorization decision ("is this person allowed to approve?") is the easy part. Verified Permissions solves the easy part.

**Verdict:** Interesting as an enhancement to the existing architecture (replace the SSM parameter-based approver group resolution with Cedar policies), but not as a replacement for the Step Functions workflow.

### Alternative D — Slack-native ChatOps with AWS Chatbot

**Architecture:** AWS Chatbot + Slack + Lambda. User requests an action in a Slack channel. A Lambda posts an interactive message with Approve/Deny buttons. Approvers click buttons. Lambda executes the action.

**Pros:**
- Approvers stay in Slack — no email links, no API Gateway callbacks.
- Interactive messages are more engaging than email notifications (lower approval fatigue).
- AWS Chatbot is a managed service with built-in Slack integration.

**Cons:**
- Slack becomes a critical dependency for your security workflow. Slack outage = no approvals.
- AWS Chatbot is read-only for most operations — you would need a custom Slack app for the interactive approval buttons.
- Multi-approver tracking, TTL, and state management still need to be built.
- Audit trail is in Slack message history, which is not as durable as DynamoDB + CloudTrail.
- No enforcement layer — this only handles the approval workflow, not the IAM deny + SCP enforcement.

**Verdict:** Good as a notification/interaction layer on top of the existing architecture (replace SNS email with Slack interactive messages), but not as a standalone replacement. The enforcement model (IAM deny + SCP + bypass detection) is independent of how approvers are notified.

### Recommendation

The current architecture (Step Functions + DynamoDB + SNS + API Gateway + EventBridge) is the right choice for this use case. Step Functions' `waitForTaskToken` pattern is a near-perfect fit for human approval workflows, and the Map state handles multi-approver fan-out elegantly.

The highest-value architectural enhancement would be **replacing SNS email notifications with Slack interactive messages** (Alternative D as an overlay, not a replacement). This addresses approval fatigue — the biggest operational risk in any approval workflow — without changing the enforcement model or state management.

---

## Summary

| Question | Answer |
|---|---|
| Are there similar projects? | No direct equivalent. The `aws-samples` repo is a single-action PoC. SSM Change Manager was the closest managed service but is closing to new customers. JIT access tools (Sym, Indent, Opal) solve a different problem (identity-layer, not action-layer). IaC tools (Sentinel, OPA, Atlantis) operate at a different layer. |
| What makes this repo stand out? | Runtime API-layer enforcement with data-driven policies, dual IAM+SCP enforcement with documented threat model, multi-approver fan-out, bypass detection, executor re-validation, and unusually honest documentation of limitations. |
| Could a different AWS stack work? | Yes, but with tradeoffs. EventBridge+SQS+Lambda loses state machine benefits. CodePipeline is a poor fit. Verified Permissions solves the wrong problem. Slack ChatOps is a good overlay but not a replacement. The current Step Functions architecture is the best fit for this pattern. |
