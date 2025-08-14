import asyncio
import os
from openai import OpenAI
from fastapi import APIRouter, HTTPException 
from pydantic import BaseModel
from dotenv import load_dotenv  
from fastapi.responses import StreamingResponse
from chatbotDirectory import chatbot
from chatbotDirectory.functioncalling import tools ,FunctionCalling
from chatbotDirectory.functioncalling import model
from chatbotDirectory.chatbot import ChatbotStream
import json


# UserRequest 클래스에 language 필드 추가
class UserRequest(BaseModel):
    message: str
    language: str = "KOR"  # 기본값은 한국어로 설정

func_calling = FunctionCalling(
    model=model.basic,
    available_functions={
        # 필요시 다른 함수도 여기에 추가
    }
)
router = APIRouter()

load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=api_key)

# 예시: 전역 또는 엔드포인트 내부에서 인스턴스 생성
chatbot = ChatbotStream(
    model=model.advanced,
    system_role="당신은 친절하고 유능한 챗봇입니다.",
    instruction="당신은 사용자의 질문에 답변하는 역할을 합니다.",
    user="대기",
    assistant="memmo"
)

# 채팅
class Message(BaseModel):
    message: str

@router.post("/chat")
async def chat(message: Message):
    try:
        response = client.chat.completions.create(
            model="gpt-4.1",
            messages=[
                {"role": "user", "content": message.message}
            ],
            temperature=0.5,
            max_tokens=512,
        )
        answer = response.choices[0].message.content
        return {"response": answer.strip()}
    except Exception as e:
        print(f"OpenAI API error: {e}")  
        raise HTTPException(status_code=500, detail=str(e))
    
@router.post("/stream-chat")
async def stream_chat(user_input: UserRequest):
    # 1) 사용자 메시지를 우선 원본 문맥에 추가
    chatbot.add_user_message_in_context(user_input.message)
    
    # 언어별 지침 매핑 정의
    instruction_map = {
        "KOR": "한국어로 정중하고 따뜻하게 답해주세요.",
        "ENG": "Please respond kindly in English.",
        "VI": "Vui lòng trả lời bằng tiếng Việt một cách nhẹ nhàng.",
        "JPN": "日本語で丁寧に温かく答えてください。",
        "CHN": "请用中文亲切地回答。"
        # 필요에 따라 더 많은 언어 추가
    }
    
    # 사용자가 선택한 언어에 따라 지침 선택 (없으면 한국어 기본값)
    instruction = instruction_map.get(user_input.language, instruction_map["KOR"])
    
    # 사용자 메시지에 지침 추가
    chatbot.context[-1]['content'] += " " + instruction

    analyzed= func_calling.analyze(user_input.message, tools)

    temp_context = chatbot.to_openai_context(context=chatbot.context[:])
    

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
               
                function_call_msg = {
                    "type": "function_call",  # 고정
                    "call_id": call_id,  # 딕셔너리 내에 있거나 key가 다를 수 있으니 주의
                    "name": func_name,
                    "arguments": tool_call.arguments  # dict -> JSON string
                }
                print(f"함수 호출 메시지: {function_call_msg}")
                if func_name == "search_internet":
                    # context는 이미 run 메서드의 매개변수로 받고 있음
                   func_response = func_to_call(chat_context=chatbot.context[:], **func_args)
                else:
                   func_response = func_to_call(**func_args)

                temp_context.extend([
                    function_call_msg,
                {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": str(func_response)
                }
            ])
                print(temp_context)

            except Exception as e:
                print(f"[함수 실행 오류] {func_name}: {e}")

    # 4) 함수 호출 결과가 반영된 temp_context으로 스트리밍 응답을 생성
    async def generate_with_tool():
        try:
            # stream=True로 스트리밍 응답
            stream = client.responses.create(
            model=chatbot.model,
            input=temp_context,  # user/assistant 역할 포함된 list 구조
            top_p=1,
            stream=True,
            text={
                "format": {
                    "type": "text"  # 또는 "json_object" 등 (Structured Output 사용 시)
                }
            }
                )
              
            loading = True
            for event in stream:
                        match event.type:
                            case "response.created":
                                print("[🤖 응답 생성 시작]")
                                loading = True
                                # 로딩 애니메이션용 대기 시작
                                yield "⏳ GPT가 응답을 준비 중입니다..."
                                await asyncio.sleep(0)
                            case "response.output_text.delta":
                                if loading:
                                    print("\n[💬 응답 시작됨 ↓]")

                                    loading = False
                                # 글자 단위 출력
                                yield f"{event.delta}"
                                await asyncio.sleep(0)
                            

                            case "response.in_progress":
                                print("[🌀 응답 생성 중...]")
                                yield "[🌀 응답 생성 중...]"
                                yield "\n"

                            case "response.output_item.added":
                                if getattr(event.item, "type", None) == "reasoning":
                                    yield "[🧠 GPT가 추론을 시작합니다...]"
                                    yield "\n"
                                elif getattr(event.item, "type", None) == "message":
                                    yield "[📩 메시지 아이템 추가됨]"
                                    yield "\n"
                            #ResponseOutputItemDoneEvent는 우리가 case "response.output_item.done"에서 잡아야 해
                            case "response.output_item.done":
                                item = event.item
                                if item.type == "message" and item.role == "assistant":
                                    for part in item.content:
                                        if getattr(part, "type", None) == "output_text":
                                            completed_text= part.text
                            case "response.completed":
                                yield "\n"
                                #print(f"\n📦 최종 전체 출력: \n{completed_text}")
                            case "response.failed":
                                print("❌ 응답 생성 실패")
                                yield "❌ 응답 생성 실패"
                            case "error":
                                print("⚠️ 스트리밍 중 에러 발생!")
                                yield "⚠️ 스트리밍 중 에러 발생!"
                            case _:
                                yield "\n"
                                yield f"[📬 기타 이벤트 감지: {event.type}]"
        except Exception as e:
            yield f"\nStream Error: {str(e)}"
        finally:
            # 스트리밍이 끝나면 최종 응답을 원본 문맥에만 반영하고 임시문맥은 사용하지 않음
                            # 기존 clean 방식 유지
            chatbot.add_response_stream( completed_text)
            
                        # 최종 응답을 원본 문맥에 저장
    # 5) 함수 호출이 있을 때는 위의 generate_with_tool()를 사용
    return StreamingResponse(generate_with_tool(), media_type="text/plain")

