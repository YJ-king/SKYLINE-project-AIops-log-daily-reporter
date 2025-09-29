import boto3
import time
import json
import os

# --- ⚙️ 사용자 설정 영역 ---
S3_OUTPUT_LOCATION = os.environ.get('S3_OUTPUT_LOCATION')
ATHENA_DATABASE = os.environ.get('ATHENA_DATABASE')
# --- ------------------- ---

athena_client = boto3.client('athena')

def lambda_handler(event, context):
    # Agent가 전달한 SQL 쿼리 추출
    sql_query = event['parameters'][0]['value']
    print(f"Executing query: {sql_query}")
    
    # Athena 쿼리 실행
    response = athena_client.start_query_execution(
        QueryString=sql_query,
        QueryExecutionContext={'Database': ATHENA_DATABASE},
        ResultConfiguration={'OutputLocation': S3_OUTPUT_LOCATION}
    )
    query_execution_id = response['QueryExecutionId']
    
    # 쿼리 완료 대기
    while True:
        stats = athena_client.get_query_execution(QueryExecutionId=query_execution_id)
        status = stats['QueryExecution']['Status']['State']
        if status in ['SUCCEEDED', 'FAILED', 'CANCELLED']: break
        time.sleep(0.2)
        
    if status != 'SUCCEEDED':
        error_message = stats['QueryExecution']['Status'].get('StateChangeReason', 'Unknown error')
        raise Exception(f"Athena query failed: {error_message}")
        
    # 쿼리 결과 파싱
    results_paginator = athena_client.get_paginator('get_query_results')
    results_iter = results_paginator.paginate(
        QueryExecutionId=query_execution_id,
        PaginationConfig={'PageSize': 1000}
    )
    parsed_results = []
    column_names = None
    for results_page in results_iter:
        rows = results_page['ResultSet']['Rows']
        if not column_names and len(rows) > 0:
            column_names = [col['VarCharValue'] for col in rows[0]['Data']]
            rows = rows[1:]
        for row in rows:
            values = [col.get('VarCharValue') for col in row['Data']]
            parsed_results.append(dict(zip(column_names, values)))
            
    # Agent에게 결과를 반환
    return {
        'messageVersion': '1.0',
        'response': {
            'actionGroup': event['actionGroup'],
            'function': event['function'],
            'functionResponse': {
                'responseBody': {
                    'TEXT': {'body': json.dumps(parsed_results)}
                }
            }
        }
    }