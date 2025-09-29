import json
import boto3
import urllib.parse
import base64
import os

lambda_client = boto3.client('lambda')
WORKER_LAMBDA_NAME = os.environ.get('WORKER_LAMBDA_NAME')

def lambda_handler(event, context):
    raw_body = event['body']
    if event.get('isBase64Encoded', False):
        raw_body = base64.b64decode(raw_body).decode('utf-8')
    
    slack_payload = urllib.parse.parse_qs(raw_body)
    user_question = slack_payload.get('text', [''])[0]
    # ⭐️ response_url 추출
    response_url = slack_payload.get('response_url', [''])[0]

    # ⭐️ Worker에게 전달할 새로운 페이로드
    worker_payload = {
        'user_question': user_question,
        'response_url': response_url
    }

    try:
        lambda_client.invoke(
            FunctionName=WORKER_LAMBDA_NAME,
            InvocationType='Event',
            Payload=json.dumps(worker_payload) # ⭐️ 새로운 페이로드 전달
        )
    except Exception as e:
        print(f"Failed to invoke worker lambda: {e}")

    # ⭐️ 사용자의 질문을 포함하여 즉시 응답
    return {
        'statusCode': 200,
        'headers': {'Content-Type': 'application/json'},
        'body': json.dumps({'text': f"🤔 AI가 '**{user_question}**' 요청을 분석 중입니다... 잠시만 기다려주세요."})
    }