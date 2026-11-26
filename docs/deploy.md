# Deploying the core to AWS

> **Not the deployment.** This is an earlier production plan (`core/template.yaml`,
> `core/seventy5/aws.py`). The stack to deploy is `deploy/aws/7even5ive-serverless.yaml`:
> see [`online.md`](online.md) and [`remaining-steps.pdf`](remaining-steps.pdf).


Region: **Mumbai (`ap-south-1`)** for AWS and Supabase.

## Once

1. Install the [AWS CLI](https://aws.amazon.com/cli/) and the
   [SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html),
   then `aws configure` with an IAM user's keys (never the root account).
2. In the Bedrock console (Mumbai), turn on access to Claude Haiku 5.5 and copy its model or
   inference-profile id.
3. Create a Supabase project in Mumbai. Copy the **transaction pooler** connection string
   (port 6543): Lambdas open and drop connections constantly, and the pooler shares a few.
4. Put the keys in SSM Parameter Store as SecureStrings. The Lambdas read `/7even5ive/*` at
   cold start; nothing secret goes in the template or the code.

```powershell
aws ssm put-parameter --region ap-south-1 --type SecureString --name /7even5ive/DATABASE_URL --value "postgresql://...:6543/postgres"
aws ssm put-parameter --region ap-south-1 --type SecureString --name /7even5ive/PORTMAX_DATABASE_URL --value "postgresql+psycopg://...:6543/postgres"
aws ssm put-parameter --region ap-south-1 --type SecureString --name /7even5ive/JEV_API_KEY --value "..."
aws ssm put-parameter --region ap-south-1 --type SecureString --name /7even5ive/BEDROCK_MODEL_ID --value "..."
aws ssm put-parameter --region ap-south-1 --type SecureString --name /7even5ive/BOT_WEBHOOK_SECRET --value "..."
aws ssm put-parameter --region ap-south-1 --type SecureString --name /7even5ive/APPROVAL_SECRET --value "..."
```

`BOT_WEBHOOK_SECRET` is shared with the WhatsApp bot ([`bot-events.md`](bot-events.md)).
`APPROVAL_SECRET` signs one-time approval tokens; any long random string.

## Every deploy

```powershell
cd core
python build_lambda.py
sam build --use-container
sam deploy --guided     # first time; afterwards just: sam deploy
```

The `ApiUrl` output is the bot's webhook base: it posts to `<ApiUrl>/bot/webhook`.

## What gets created

| Resource | Job |
|---|---|
| HTTP API + `HttpFunction` | Bot webhook, `/api/cards`, `/api/approve` |
| `EventQueue` + `DeadLetters` | SQS between ingress and the cascade; 3 tries, then 14 days in the DLQ |
| `CascadeFunction` | Classroom → Jev → LLM → gate → card, one event at a time |
| `NotifyFunction` | Every minute: fires due reminders |

No VPC and no NAT gateway: Supabase is reached over TLS through its pooler.
Not deployed yet: the MCP server (runs locally over stdio until AgentCore fronts it), the
portal-check and briefing functions, and the Android push sender for reminders.
