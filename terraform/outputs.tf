# outputs.tf

output "api_gateway_invoke_url" {
  description = "Slack 슬래시 커맨드에 입력할 API Gateway 호출 URL"
  value       = "${aws_apigatewayv2_stage.default.invoke_url}/slack-command"
}

output "s3_bucket_name" {
  description = "CUR 데이터가 저장될 S3 버킷 이름"
  value       = aws_s3_bucket.data_bucket.bucket
}

output "lambda_tool_role_arn" {
  description = "athena-query-executor Lambda의 IAM 역할 ARN"
  value       = module.lambda_tool.lambda_role_arn
}

output "lambda_worker_role_arn" {
  description = "bedrock-agent-worker Lambda의 IAM 역할 ARN"
  value       = module.lambda_worker.lambda_role_arn
}

output "lambda_clerk_role_arn" {
  description = "slack-bedrock-agent-handler Lambda의 IAM 역할 ARN"
  value       = module.lambda_clerk.lambda_role_arn
}