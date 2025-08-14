from pymongo import MongoClient
from typing import List, Dict
import os
from dotenv import load_dotenv
import certifi

# .env에서 MONGODB_URI 불러오기
load_dotenv('apikey.env')
MONGODB_URI = os.getenv("MONGODB_URI")
if not MONGODB_URI:
    raise ValueError("MONGODB_URI 환경 변수가 설정되지 않았습니다.")
COLLECTION_NAME = "regulation_chunks"
DB_NAME = "halla_academic_db"

# Mongo 연결
client = MongoClient(
    MONGODB_URI,
    tls=True,                         # TLS 명시
    tlsCAFile=certifi.where(),        # 신뢰 CA 번들
    serverSelectionTimeoutMS=30000,
    connectTimeoutMS=20000,
    socketTimeoutMS=20000,
)
# 초기 연결 확인(실패 시 즉시 원인 확인 가능)
client.admin.command("ping")

db = client[DB_NAME]
collection = db[COLLECTION_NAME]


def insert_chunks_to_mongo(chunks: List[Dict]):
    try:
        cluster = client 

        db = cluster[DB_NAME]
        collection = db[COLLECTION_NAME]

        filenames = set(chunk['metadata']['source_file'] for chunk in chunks)
        for fname in filenames:
            delete_result = collection.delete_many({"metadata.source_file": fname})
            print(f" {fname} 삭제: {delete_result.deleted_count}개")

        result = collection.insert_many(chunks)
        print(f"저장 완료: {len(result.inserted_ids)}개")
    except Exception as e:
        print(f" Mongo 에러: {str(e)} URI 확인하세요")