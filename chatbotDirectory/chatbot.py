import math
import os
import time
# 상대 임포트 대신 절대 임포트 사용
from chatbotDirectory.common import model, makeup_response, client
from chatbotDirectory.functioncalling import FunctionCalling, tools
from loding.vector_db_upload import index, get_embedding
from loding.mongodbConnect import collection
from bson import ObjectId, errors
import json

class ChatbotStream:
    def __init__(self, model,system_role,instruction,**kwargs):
        """
        초기화:
          - context 리스트 생성 및 시스템 역할 설정
          - sub_contexts 서브 대화방 문맥을 저장할 딕셔너리 {필드이름,문맥,요약,질문} 구성
          - current_field = 현재 대화방 추적 (기본값: 메인 대화방
          - openai.api_key 설정
          - 사용할 모델명 저장
          - 사용자 이름
          - assistant 이름
        """
        self.context = [{"role": "system","content": system_role}]
               
        self.current_field = "main"
        
        self.model = model
        self.instruction=instruction

        self.max_token_size = 16 * 1024 #최대 토큰이상을 쓰면 오류가발생 따라서 토큰 용량관리가 필요.
        self.available_token_rate = 0.9#최대토큰의 90%만 쓰겠다.
    
        

        # 디버그 플래그 (환경변수 RAG_DEBUG로 제어: 기본 활성화)
        self.debug = os.getenv("RAG_DEBUG", "1") not in ("0", "false", "False")

    def _dbg(self, msg: str):
        """작은 디버그 헬퍼: RAG 관련 내부 상태를 보기 쉽게 출력."""
        if self.debug:
            print(f"[RAG-DEBUG] {msg}")

    def add_user_message_in_context(self, message: str):
        """
        사용자 메시지 추가:
          - 사용자가 입력한 message를 context에 user 역할로 추가
        """
        assistant_message = {
            "role": "user",
            "content": message,
        }
        if self.current_field == "main":
            self.context.append(assistant_message)

    #전송부
    def _send_request_Stream(self,temp_context=None):
        
        completed_text = ""

        if temp_context is None:
           current_context = self.get_current_context()
           openai_context = self.to_openai_context(current_context)
           stream = client.responses.create(
            model=self.model,
            input=openai_context,  
            top_p=1,
            stream=True,
            
            text={
                "format": {
                    "type": "text"  # 또는 "json_object" 등 (Structured Output 사용 시)
                }
            }
                )
        else:  
           stream = client.responses.create(
            model=self.model,
            input=temp_context,  # user/assistant 역할 포함된 list 구조
            top_p=1,
            stream=True,
            text={
                "format": {
                    "type": "text"  # 또는 "json_object" 등 (Structured Output 사용 시)
                }
            }
                )
        
        loading = True  # delta가 나오기 전까지 로딩 중 상태 유지       
        for event in stream:
            #print(f"event: {event}")
            match event.type:
                case "response.created":
                    print("[🤖 응답 생성 시작]")
                    loading = True
                    # 로딩 애니메이션용 대기 시작
                    print("⏳ GPT가 응답을 준비 중입니다...")
                    
                case "response.output_text.delta":
                    if loading:
                        print("\n[💬 응답 시작됨 ↓]")
                        loading = False
                    # 글자 단위 출력
                    print(event.delta, end="", flush=True)
                 

                case "response.in_progress":
                    print("[🌀 응답 생성 중...]")

                case "response.output_item.added":
                    if getattr(event.item, "type", None) == "reasoning":
                        print("[🧠 GPT가 추론을 시작합니다...]")
                    elif getattr(event.item, "type", None) == "message":
                        print("[📩 메시지 아이템 추가됨]")
                #ResponseOutputItemDoneEvent는 우리가 case "response.output_item.done"에서 잡아야 해
                case "response.output_item.done":
                    item = event.item
                    if item.type == "message" and item.role == "assistant":
                        for part in item.content:
                            if getattr(part, "type", None) == "output_text":
                                completed_text= part.text
                case "response.completed":
                    print("\n")
                    #print(f"\n📦 최종 전체 출력: \n{completed_text}")
                case "response.failed":
                    print("❌ 응답 생성 실패")
                case "error":
                    print("⚠️ 스트리밍 중 에러 발생!")
                case _:
                    
                    print(f"[📬 기타 이벤트 감지: {event.type}]")
        return completed_text
  
  
    def send_request_Stream(self):
      self.context[-1]['content']+=self.instruction
      return self._send_request_Stream()
#챗봇에 맞게 문맥 파싱
    def add_response(self, response):
        response_message = {
            "role" : response['choices'][0]['message']["role"],
            "content" : response['choices'][0]['message']["content"],
            
        }
        self.context.append(response_message)

    def add_response_stream(self, response):
            """
                챗봇 응답을 현재 대화방의 문맥에 추가합니다.
                
                Args:
                    response (str): 챗봇이 생성한 응답 텍스트.
                """
            assistant_message = {
            "role": "assistant",
            "content": response,
           
        }
            self.context.append(assistant_message)

    def get_response(self, response_text: str):
        """
        응답내용반환:
          - 메시지를 콘솔(또는 UI) 출력 후, 그대로 반환
        """
        print(response_text['choices'][0]['message']['content'])
        return response_text
#마지막 지침제거
    def clean_context(self):
        '''
        1.context리스트에 마지막 인덱스부터 처음까지 순회한다
        2."instruction:\n"을 기준으로 문자열을 나눈다..첫user을 찾으면 아래 과정을 진행한다,
        3.첫 번째 부분 [0]만 가져온다. (즉, "instruction:\n" 이전의 문자열만 남긴다.)
        4.strip()을 적용하여 앞뒤의 공백이나 개행 문자를 제거한다.
        '''
        for idx in reversed(range(len(self.context))):
            if self.context[idx]['role']=='user':
                self.context[idx]["content"]=self.context[idx]['content'].split('instruction:\n')[0].strip()
                break
#질의응답 토큰 관리
    def handle_token_limit(self, response):
        # 누적 토큰 수가 임계점을 넘지 않도록 제어한다.
        try:
            current_usage_rate = response['usage']['total_tokens'] / self.max_token_size
            exceeded_token_rate = current_usage_rate - self.available_token_rate
            if exceeded_token_rate > 0:
                remove_size = math.ceil(len(self.context) / 10)
                self.context = [self.context[0]] + self.context[remove_size+1:]
        except Exception as e:
            print(f"handle_token_limit exception:{e}")
    def to_openai_context(self, context):
        return [{"role":v["role"], "content":v["content"]} for v in context]

    def is_question_about_regulation(self, question: str) -> bool:
        self._dbg(f"is_question_about_regulation: LLM 판단 시작 - q='{question[:60]}...'")

        prompt = [
           {
               "role": "system",
               "content": (
                   "당신은 분류기입니다. "
                   "주어진 질문이 학사 규정, 졸업 요건, 수강, 성적, 장학, 징계 등과 관련 있다면 'True', "
                   "그 외 주제라면 'False'만 출력하세요. "
                   "설명은 하지 말고 반드시 True 또는 False만 출력하세요."
               ),
           },
           {
               "role": "user",
               "content": question,
           },
       ]
        
        try:
           resp = client.responses.create(
               model="gpt-4.1-mini",  
               input=prompt,
           )
           answer = resp.output_text.strip()
 
           decision = answer.lower() == "true"
           self._dbg(f"is_question_about_regulation: LLM 결과='{answer}' -> {decision}")
           return decision
        
        except Exception as e:
           self._dbg(f"is_question_about_regulation: LLM 판별 실패 - {e}")
           # 실패 시 기존 키워드 기반으로
           keywords = ["학사", "규정", "졸업", "수강", "성적", "장학", "징계"]
           decision = any(k in question for k in keywords)
           self._dbg(f"is_question_about_regulation: fallback 결정 -> {decision}")
           return decision







    def search_similar_chunks(self, query: str, threshold=0.1):
        t0 = time.time()
        self._dbg(f"search_similar_chunks: query='{query[:80]}', threshold={threshold}")
        embedding = get_embedding(query)
        namespaces = ["law_articles", "appendix_tables"]

        all_hits = []
        all_chunk_ids = []

        for ns in namespaces:
            self._dbg(f" - querying namespace='{ns}' top_k=50 include_metadata=True")
            query_response = index.query(
                namespace=ns,
                top_k=10,
                include_metadata=True,
                vector=embedding,
            )
            hits = query_response.matches
            self._dbg(f"   -> {len(hits)} matches returned")

            for h in hits:
                all_hits.append(h)
                meta = getattr(h, "metadata", {}) or {}
                # 메타데이터 id 키 후보 확대(mongo_id 포함)
                id_value = (
                    meta.get("id")
                    or meta.get("mongo_id")
                    or meta.get("ID")
                    or meta.get("default")
                )
                score = getattr(h, "score", None)
                if id_value is not None:
                    all_chunk_ids.append(id_value)
                    self._dbg(f"     match: id={id_value} score={score}")
                else:
                    self._dbg(f"     match: id=<missing> score={score} meta_keys={list(meta.keys())}")

        # 점수 기준 필터링
        filtered_hits = [hit for hit in all_hits if getattr(hit, "score", 0) >= threshold]
        t1 = time.time()
        self._dbg(
            f"search_similar_chunks: total_hits={len(all_hits)} filtered={len(filtered_hits)} unique_ids={len(set(all_chunk_ids))} took={(t1-t0):.3f}s"
        )

        return filtered_hits, all_chunk_ids

    def fetch_chunks_from_mongo(self, chunk_ids: list):
        self._dbg(f"fetch_chunks_from_mongo: incoming_ids={len(chunk_ids)} (showing up to 5) -> {chunk_ids[:5]}")
        results = []
        for chunk_id in chunk_ids:
            try:
                if isinstance(chunk_id, str) and len(chunk_id) == 24:
                    chunk_id_obj = ObjectId(chunk_id)
                    self._dbg(f" - id '{chunk_id}' converted to ObjectId")
                else:
                    chunk_id_obj = chunk_id
                    self._dbg(f" - id '{chunk_id}' used as-is (type={type(chunk_id).__name__})")
            except errors.InvalidId as e:
                print(f"[WARN] ObjectId 변환 실패: {chunk_id} ({e})")
                chunk_id_obj = chunk_id

            doc = collection.find_one({"_id": chunk_id_obj})
            if doc:
                results.append(doc)
                text_len = len(doc.get("text", "")) if isinstance(doc.get("text"), str) else 0
                self._dbg(f"   -> Mongo HIT _id={doc.get('_id')} text_len={text_len}")
            else:
                self._dbg(f"   -> Mongo MISS _id={chunk_id}")
        self._dbg(f"fetch_chunks_from_mongo: retrieved={len(results)}")
        return results

    def prepare_rag_context(self, user_question: str):
        self._dbg("prepare_rag_context: start")
        if not self.is_question_about_regulation(user_question):
            print("[INFO] 학사 규정 관련이 아님 → RAG 검색 안 함")
            self._dbg("prepare_rag_context: gate=NON_REGULATION -> None")
            return None

        hits, chunk_ids = self.search_similar_chunks(user_question)
        if not hits:
            print("[INFO] Pinecone에서 유사 데이터 없음")
            self._dbg("prepare_rag_context: no pinecone hits -> None")
            return None

        self._dbg(f"prepare_rag_context: chunk_ids(sample)={chunk_ids[:5]} total={len(chunk_ids)}")

        if not chunk_ids:
            print("[INFO] Pinecone 결과에 id 없음")
            self._dbg("prepare_rag_context: ids empty -> None")
            return None

        chunks = self.fetch_chunks_from_mongo(chunk_ids)
        if not chunks:
            print("[INFO] MongoDB에서 매칭된 문서 없음")
            self._dbg("prepare_rag_context: mongo returned 0 -> None")
            return None

        texts = [chunk.get("text", "") for chunk in chunks]
        rag_ctx = "\n\n".join(texts)
        self._dbg(f"prepare_rag_context: built context chars={len(rag_ctx)}")
        return rag_ctx
    
        
    def get_response_from_db_only(self, user_question: str):
        self._dbg("get_response_from_db_only: start")
        rag_context = self.prepare_rag_context(user_question)
        if rag_context is None:
            self._dbg("get_response_from_db_only: rag_context=None -> fallback message")
            return "데이터베이스에 관련 내용이 없습니다."

        # LLM 호출할 context 구성: system 메시지 + DB 내용(system role) + user 질문
        context = [
            {"role": "system", "content": "당신은 학사 규정 관련 질문에 답변하는 챗봇입니다. 아래 내용을 참고하여 정확하게 답변하세요."},
            {"role": "system", "content": rag_context},
            {"role": "user", "content": user_question},
        ]
        self._dbg(
            f"get_response_from_db_only: messages=[system, system(ctx:{rag_context} chars), user] model={self.model}"
        )

        return self._send_request_Stream(temp_context=self.to_openai_context(context))
 


if __name__ == "__main__":
    '''실행흐름
    단계	내용
1️⃣	사용자 입력 받음 (user_input)
2️⃣	→ add_user_message_in_context() 로 user 메시지를 문맥에 추가
3️⃣	→ analyze() 로 함수 호출이 필요한지 판단
4️⃣	→ 필요하면 함수 실행 + 결과를 temp_context에 추가
5️⃣	→ chatbot._send_request_Stream(temp_context) 로 응답 받음
6️⃣	✅ streamed_response 결과를 직접 add_response_stream()으로 수동 저장'''
    system_role = "당신은 친절하고 유능한 챗봇입니다."
    instruction = "당신은 사용자의 질문에 답변하는 역할을 합니다. 질문에 대한 답변을 제공하고, 필요한 경우 함수 호출을 통해 추가 정보를 검색할 수 있습니다. 사용자의 질문에 대해 정확하고 유용한 답변을 제공하세요."
    # ChatbotStream 인스턴스 생성
    chatbot = ChatbotStream(
        model.advanced,
        system_role=system_role,
        instruction=instruction,
        user="대기",
        assistant="memmo")
    func_calling=FunctionCalling(model.advanced)
    print("===== Chatbot Started =====")
    print("초기 context:", chatbot.context)
    print("사용자가 'exit'라고 입력하면 종료합니다.\n")
    
   # 출력: {}
    

    while True:
        try:
            user_input = input("User > ")

            if user_input.strip().lower() == "exit":
                print("Chatbot 종료.")
                break

        
            



            

            # 사용자 메시지를 문맥에 추가
            chatbot.add_user_message_in_context(user_input)


            # 챗봇 응답을 가져오기 (RAG 문맥 준비 및 함수 호출)            
            streamed_response = chatbot.get_response_from_db_only(user_input)  
            chatbot.add_response_stream(streamed_response)

            # 사용자 입력 분석 (함수 호출 여부 확인)
            analyzed = func_calling.analyze(user_input, tools)

            temp_context = chatbot.to_openai_context(chatbot.context[:])
   
            for tool_call in analyzed:  # analyzed는 list of function_call dicts
                if tool_call.type != "function_call":
                    continue
            
                func_name = tool_call.name
                func_args = json.loads(tool_call.arguments)
                call_id = tool_call.call_id

                func_to_call = func_calling.available_functions.get(func_name)
                if not func_to_call:
                    print(f"[오류] 등록되지 않은 함수: {func_name}")
                    continue


                try:
                    func_response = (
                        func_to_call(chat_context=chatbot.context[:], **func_args)
                        if func_name == "search_internet"
                        else func_to_call(**func_args)
                    )
               
                    
        
                

                    temp_context.extend([
                        {"type": "function_call", "call_id": call_id, "name": func_name, "arguments": tool_call.arguments},
                        {"type": "function_call_output", "call_id": call_id, "output": str(func_response)}
                    ])
       

                except Exception as e:
                    print(f"[함수 실행 오류] {func_name}: {e}")

            streamed_response = chatbot.get_response_from_db_only(user_input)
            chatbot.add_response_stream(streamed_response)
 
            print("\n===== Chatbot Context Updated =====")
            print(chatbot.context)

        except KeyboardInterrupt:
            print("\n사용자 종료(Ctrl+C)")
            break
        except Exception as e:
            print(f"[루프 에러] {e}")
            continue

    # === 분기 처리 끝 ===