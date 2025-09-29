# main.tf

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# AWS 계정 ID 가져오기
data "aws_caller_identity" "current" {}

# S3 버킷 (CUR 데이터 저장 및 Athena 결과 저장용)
resource "aws_s3_bucket" "data_bucket" {
  bucket = lower("${var.project_name}-data-${data.aws_caller_identity.current.account_id}")
}

# --- 1. '도구' Lambda: athena-query-executor ---
module "lambda_tool" {
  source = "terraform-aws-modules/lambda/aws"

  function_name = "athena-query-executor"
  handler       = "lambda_function.lambda_handler"
  runtime       = "python3.12"
  source_path   = "../src/tool_lambda/" # 소스코드 경로

  attach_policy_statements = true
  policy_statements = {
    athena_glue_s3 = {
      effect    = "Allow"
      actions   = [
        "athena:*",
        "glue:GetDatabase",
        "glue:GetDatabases",
        "glue:GetTable",
        "glue:GetTables",
        "s3:GetObject",
        "s3:PutObject",
        "s3:ListBucket"
      ]
      resources = [
        "*", # 실제 운영 환경에서는 더 구체적인 ARN으로 제한해야 함
      ]
    }
  }
}

# --- 2. '작업자' Lambda: bedrock-agent-worker ---
module "lambda_worker" {
  source = "terraform-aws-modules/lambda/aws"

  function_name = "bedrock-agent-worker"
  handler       = "lambda_function.lambda_handler"
  runtime       = "python3.12"
  timeout       = 60 # 타임아웃 60초
  source_path   = "../src/worker_lambda/"

  environment_variables = {
    SLACK_WEBHOOK_URL  = var.slack_webhook_url
    AGENT_ID           = var.bedrock_agent_id
    AGENT_ALIAS_ID     = var.bedrock_agent_alias_id
    BEDROCK_REGION     = var.aws_region
  }

  attach_policy_json = true
  policy_json        = data.aws_iam_policy_document.bedrock_policy.json
}

data "aws_iam_policy_document" "bedrock_policy" {
  statement {
    effect    = "Allow"
    actions   = ["bedrock:InvokeAgent"]
    resources = ["arn:aws:bedrock:${var.aws_region}:${data.aws_caller_identity.current.account_id}:agent-alias/${var.bedrock_agent_id}/${var.bedrock_agent_alias_id}"]
  }
}

# --- 3. '점원' Lambda: slack-bedrock-agent-handler ---
module "lambda_clerk" {
  source = "terraform-aws-modules/lambda/aws"

  function_name = "slack-bedrock-agent-handler"
  handler       = "lambda_function.lambda_handler"
  runtime       = "python3.12"
  source_path   = "../src/clerk_lambda/"

  environment_variables = {
    WORKER_LAMBDA_NAME = module.lambda_worker.lambda_function_name
  }

  attach_policy_statements = true
  policy_statements = {
    invoke_worker = {
      effect    = "Allow"
      actions   = ["lambda:InvokeFunction"]
      resources = [module.lambda_worker.lambda_function_arn]
    }
  }
}

# --- 4. API Gateway ---
resource "aws_apigatewayv2_api" "slack_api" {
  name          = "${var.project_name}-Slack-API"
  protocol_type = "HTTP"
}

resource "aws_apigatewayv2_integration" "lambda_integration" {
  api_id           = aws_apigatewayv2_api.slack_api.id
  integration_type = "AWS_PROXY"
  integration_uri  = module.lambda_clerk.lambda_function_arn
}

resource "aws_apigatewayv2_route" "slack_route" {
  api_id    = aws_apigatewayv2_api.slack_api.id
  route_key = "POST /slack-command"
  target    = "integrations/${aws_apigatewayv2_integration.lambda_integration.id}"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.slack_api.id
  name        = "$default"
  auto_deploy = true
}

resource "aws_lambda_permission" "api_gw_permission" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = module.lambda_clerk.lambda_function_name
  principal     = "apigateway.amazonaws.com"

  source_arn = "${aws_apigatewayv2_api.slack_api.execution_arn}/*"
}

# --- 참고: Bedrock Agent 및 Glue Crawler ---
# Bedrock Agent와 Glue Crawler는 현재 Terraform AWS Provider에서 
# 완벽하게 지원되지 않거나 설정이 복잡할 수 있습니다.
# 이 부분은 초기 설정 시 AWS 콘솔에서 직접 생성하는 것을 권장합니다.
# 생성 후, Agent ID와 Alias ID를 변수로 입력하여 Lambda와 연결합니다.