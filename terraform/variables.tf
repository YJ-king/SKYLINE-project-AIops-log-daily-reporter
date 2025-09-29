# variables.tf

variable "aws_region" {
  description = "배포할 AWS 리전"
  type        = string
  default     = "ap-northeast-2"
}

variable "project_name" {
  description = "프로젝트 이름 (리소스 이름에 사용됨)"
  type        = string
  default     = "FinOpsAI"
}

variable "slack_webhook_url" {
  description = "Slack Webhook URL (Lambda 환경 변수용)"
  type        = string
  sensitive   = true # 민감한 정보이므로 출력에 노출되지 않음
}

variable "bedrock_agent_id" {
  description = "Bedrock Agent ID (Lambda 환경 변수용)"
  type        = string
}

variable "bedrock_agent_alias_id" {
  description = "Bedrock Agent Alias ID (Lambda 환경 변수용)"
  type        = string
}