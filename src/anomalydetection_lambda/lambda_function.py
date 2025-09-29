import json
import os
import urllib3
import boto3
from datetime import datetime, timedelta, timezone

# --- 환경 변수 (변경 없음) ---
SLACK_WEBHOOK_URL = os.environ.get('SLACK_WEBHOOK_URL')
BEDROCK_MODEL_ID = os.environ.get('BEDROCK_MODEL_ID')
BEDROCK_REGION = os.environ.get('BEDROCK_REGION')

# --- 클라이언트 초기화 ---
http = urllib3.PoolManager()
bedrock_runtime = boto3.client('bedrock-runtime', region_name=BEDROCK_REGION)
# Cost Explorer 클라이언트 (반드시 us-east-1 이어야 함)
cost_explorer = boto3.client('ce', region_name='us-east-1')

def get_comparative_costs(anomaly_date_str, service_name):
    """Cost Explorer를 호출하여 전일, 전주 평균, 전월 평균 비용을 가져오는 함수"""
    try:
        anomaly_date = datetime.strptime(anomaly_date_str.split('T')[0], '%Y-%m-%d')
        
        # 1. 전일 비용 조회
        prev_day_start = (anomaly_date - timedelta(days=1)).strftime('%Y-%m-%d')
        prev_day_end = anomaly_date.strftime('%Y-%m-%d') # anomaly_date의 00시 00분 00초까지
        
        response_prev_day = cost_explorer.get_cost_and_usage(
            TimePeriod={'Start': prev_day_start, 'End': prev_day_end},
            Granularity='DAILY',
            Metrics=['UnblendedCost'],
            Filter={"Dimensions": {"Key": "SERVICE", "Values": [service_name]}}
        )
        prev_day_cost = float(response_prev_day['ResultsByTime'][0]['Total']['UnblendedCost']['Amount']) if response_prev_day['ResultsByTime'] else 0.0

        # 2. 지난 7일(전주) 평균 비용 조회 (발생일 기준 지난 7일)
        week_ago_start = (anomaly_date - timedelta(days=7)).strftime('%Y-%m-%d')
        week_ago_end = anomaly_date.strftime('%Y-%m-%d') # anomaly_date의 00시 00분 00초까지

        response_weekly = cost_explorer.get_cost_and_usage(
            TimePeriod={'Start': week_ago_start, 'End': week_ago_end},
            Granularity='DAILY',
            Metrics=['UnblendedCost'],
            Filter={"Dimensions": {"Key": "SERVICE", "Values": [service_name]}}
        )
        total_weekly_cost = sum(float(day['Total']['UnblendedCost']['Amount']) for day in response_weekly['ResultsByTime'])
        weekly_avg_cost = total_weekly_cost / len(response_weekly['ResultsByTime']) if response_weekly['ResultsByTime'] else 0.0
        
        # 3. 지난 달(전월) 평균 비용 조회 (발생일 기준 지난 30일)
        month_ago_start = (anomaly_date - timedelta(days=30)).strftime('%Y-%m-%d')
        month_ago_end = anomaly_date.strftime('%Y-%m-%d') # anomaly_date의 00시 00분 00초까지
        
        response_monthly = cost_explorer.get_cost_and_usage(
            TimePeriod={'Start': month_ago_start, 'End': month_ago_end},
            Granularity='DAILY',
            Metrics=['UnblendedCost'],
            Filter={"Dimensions": {"Key": "SERVICE", "Values": [service_name]}}
        )
        total_monthly_cost = sum(float(day['Total']['UnblendedCost']['Amount']) for day in response_monthly['ResultsByTime'])
        monthly_avg_cost = total_monthly_cost / len(response_monthly['ResultsByTime']) if response_monthly['ResultsByTime'] else 0.0

        return prev_day_cost, weekly_avg_cost, monthly_avg_cost
    except Exception as e:
        print(f"Error fetching from Cost Explorer for service '{service_name}': {e}")
        return 0.0, 0.0, 0.0


def lambda_handler(event, context):
    try:
        sns_message = json.loads(event['Records'][0]['Sns']['Message'])
        anomaly_details_raw = json.dumps(sns_message, indent=2, ensure_ascii=False)
        
        # 비교 데이터 조회를 위한 정보 추출
        # anomalyStartDate는 UTC 시간일 수 있으므로, 날짜만 추출
        anomaly_date_utc = sns_message.get("anomalyStartDate") # 예: 2025-09-24T00:00:00Z
        anomaly_date_only = anomaly_date_utc.split('T')[0] if anomaly_date_utc else datetime.now(timezone.utc).strftime('%Y-%m-%d')
        
        service_name = sns_message.get("rootCauses", [{}])[0].get("service")
        anomaly_impact = sns_message.get("anomalyTotalImpact", {}).get("totalImpact", 0.0)

        # ✨ Cost Explorer 데이터 가져오기
        prev_day_cost, weekly_avg_cost, monthly_avg_cost = 0.0, 0.0, 0.0
        if anomaly_date_only and service_name:
            prev_day_cost, weekly_avg_cost, monthly_avg_cost = get_comparative_costs(anomaly_date_only, service_name)

    except Exception as e:
        print(f"Error parsing SNS message or preparing data: {e}")
        return {'statusCode': 400}

    # ✨ Bedrock 프롬프트
    prompt = f"""
    Human: 당신은 AWS 비용을 분석하고 보고하는 FinOps 전문가입니다.
    아래 JSON 데이터는 AWS Cost Anomaly Detection이 보낸 긴급 비용 이상 경고입니다.
    추가적으로 어제 비용, 지난주 일평균 비용, 지난달 일평균 비용 데이터도 함께 제공됩니다.

    이 모든 정보를 종합하여, Slack에 보낼 긴급 비용 이상 경고 리포트를 '한글'로 작성해 줘.
    특히, 전일, 전주 일평균, 전월 일평균과 현재 이상 감지된 비용을 명확하게 비교하고,
    각각 대비 얼마나 비용이 증가했는지 퍼센트(%)로 계산해서 보여줘.
    
    비교 항목 앞에는 딱딱한 텍스트 대신 아래의 이모티콘을 사용해줘:
    - 전일 비용: 🗓️
    - 전주 일평균 비용: 📊
    - 전월 일평균 비용: 📈

    리포트에는 다음 내용이 반드시 포함되어야 해:
    - 어떤 서비스에서 문제가 발생했는지 (rootCauses.service)
    - 이상이 감지된 비용: ${anomaly_impact:.2f}
    - 🗓️ 전일 비용: ${prev_day_cost:.2f} (전일 대비 증가율: {"N/A" if prev_day_cost == 0 else f"+{(anomaly_impact / prev_day_cost - 1) * 100:.2f}%" if anomaly_impact > prev_day_cost else f"{(anomaly_impact / prev_day_cost - 1) * 100:.2f}%"})
    - 📊 전주 일평균 비용: ${weekly_avg_cost:.2f} (주간 평균 대비 증가율: {"N/A" if weekly_avg_cost == 0 else f"+{(anomaly_impact / weekly_avg_cost - 1) * 100:.2f}%" if anomaly_impact > weekly_avg_cost else f"{(anomaly_impact / weekly_avg_cost - 1) * 100:.2f}%"})
    - 📈 전월 일평균 비용: ${monthly_avg_cost:.2f} (월간 평균 대비 증가율: {"N/A" if monthly_avg_cost == 0 else f"+{(anomaly_impact / monthly_avg_cost - 1) * 100:.2f}%" if anomaly_impact > monthly_avg_cost else f"{(anomaly_impact / monthly_avg_cost - 1) * 100:.2f}%"})
    - 근본 원인(rootCauses)에 대한 간단한 분석 코멘트.

    분석 대상 데이터:
    {anomaly_details_raw}

    Assistant:
    """

    try:
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 2048,
            "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}]
        })
        response = bedrock_runtime.invoke_model(body=body, modelId=BEDROCK_MODEL_ID)
        response_body = json.loads(response.get('body').read())
        report_text = response_body['content'][0]['text']
    except Exception as e:
        print(f"Error invoking Bedrock model: {e}")
        report_text = f"Bedrock 분석 중 오류 발생: {e}\n\n[원본 데이터]\n{anomaly_details_raw}"

    try:
        slack_message = {
            'username': 'AIOps 비용 감시봇',
            'icon_emoji': ':warning:',
            'text': f"🚨 **AWS 비용 이상 징후 감지!** 🚨\n\n{report_text}"
        }
        encoded_msg = json.dumps(slack_message).encode('utf-8')
        http.request('POST', SLACK_WEBHOOK_URL, body=encoded_msg, headers={'Content-Type': 'application/json'})
    except Exception as e:
        print(f"Error sending to Slack: {e}")

    return {'statusCode': 200, 'body': json.dumps('Report sent successfully!')}