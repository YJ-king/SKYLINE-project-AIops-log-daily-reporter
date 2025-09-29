import json
import boto3
import urllib3
import os

# --- ⚙️ 사용자 설정 영역 ---
AGENT_ID = os.environ.get('AGENT_ID')
AGENT_ALIAS_ID = os.environ.get('AGENT_ALIAS_ID')
BEDROCK_REGION = os.environ.get('BEDROCK_REGION', 'ap-northeast-2')
# --- ------------------- ---

bedrock_agent_runtime = boto3.client('bedrock-agent-runtime', region_name=BEDROCK_REGION)
http = urllib3.PoolManager()

# ⭐️ Slack 메시지를 업데이트하는 함수
def update_slack_message(url, text):
    try:
        slack_message = {'text': text, 'replace_original': True}
        encoded_msg = json.dumps(slack_message).encode('utf-8')
        http.request('POST', url, body=encoded_msg, headers={'Content-Type': 'application/json'})
        print(f"Message updated on Slack: {text}")
    except Exception as e:
        print(f"Error updating Slack message: {e}")

def lambda_handler(event, context):
    # 1. '점원'에게서 user_question과 response_url을 받음
    user_question = event.get('user_question')
    response_url = event.get('response_url')

    if not all([user_question, response_url]):
        return {'statusCode': 400, 'body': 'Missing user_question or response_url'}

    # 2. Bedrock Agent 호출 (이 과정은 오래 걸릴 수 있음)
    try:
        # ⭐️ 진행 상황 업데이트 1
        update_slack_message(response_url, f"✅ **'{user_question}'** 요청 접수\n🔄 [1/2] AI 에이전트가 데이터 분석을 시작합니다...")

        session_id = context.aws_request_id
        response = bedrock_agent_runtime.invoke_agent(
            agentId=AGENT_ID, agentAliasId=AGENT_ALIAS_ID,
            sessionId=session_id, inputText=user_question
        )
        
        # ⭐️ 진행 상황 업데이트 2
        update_slack_message(response_url, f"✅ **'{user_question}'** 요청 접수\n✅ [1/2] 데이터 분석 완료!\n🔄 [2/2] AI가 최종 리포트를 생성 중입니다...")

        final_response = ""
        for event_chunk in response.get('completion'):
            if 'chunk' in event_chunk:
                final_response += event_chunk['chunk']['bytes'].decode('utf-8')
        
    except Exception as e:
        print(f"Error invoking agent: {e}")
        final_response = f"AI 분석 중 오류가 발생했습니다: {e}"

    # 3. 최종 결과를 response_url로 전송하여 기존 메시지를 업데이트
    update_slack_message(response_url, f"✅ **'{user_question}'** 요청에 대한 분석이 완료되었습니다.\n\n{final_response}")
    
    return {'statusCode': 200, 'body': 'Job finished.'}