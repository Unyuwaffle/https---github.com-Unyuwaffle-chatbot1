from  chatbotDirectory.common  import client, model, makeup_response
import json
import requests
from pprint import pprint

import os
tools = [
        
            {
            "type": "function",
            "name": "search_internet",
            "description": "Searches the internet based on user input and retrieves relevant information.",
            "strict": True,
            "parameters": {
                "type": "object",
                "required": [
                "user_input"
                ],
                "properties": {
                "user_input": {
                    "type": "string",
                    "description": "User's search query input(conversation context will be automatically added)"
                }
                },
                "additionalProperties": False
            }
            },
      
       
      
    ]

def search_internet(user_input: str,chat_context=None) -> str:
    
    try:
        print(f"📨 웹 검색 요청 시작: '{user_input}'")

        # ✅ 사용자 입력을 input_text 컨텍스트로 변환
       
        if chat_context:
            print("🔄 문맥 처리 시작")
        # 최근 N개의 메시지만 포함 (너무 많은 문맥은 토큰을 낭비할 수 있음)
            recent_messages = chat_context[-3:]  # 최근 3개 메시지만 사용
            print(f"📋 최근 메시지 수: {len(recent_messages)}")
            # 문맥 정보를 추가 컨텍스트로 구성
            for i, msg in enumerate(recent_messages):
                    print(f"📝 메시지 {i + 1} 역할: {msg.get('role', 'unknown')}")
                    content_preview = str(msg.get('content', ''))[:50] + "..." if len(str(msg.get('content', ''))) > 50 else str(msg.get('content', ''))
                    print(f"📄 내용 미리보기: {content_preview}")

            context_info = "\n".join([
                f"{msg.get('role', 'unknown')}: {msg.get('content', '')}" 
                for msg in recent_messages if msg.get('role') != 'system'
            ])
            
            
            search_text = client.responses.create(
                model="gpt-4o",
                input=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": f"{user_input}\n\n[대화 문맥]: {context_info} 을 제공된 문맥에 맞게 검색어를 새로 만들어라 <예>  문맥: 창업가양성교육...; 사용자 요청:25년 정보로 검색해줘; 검색어[창업양성교육 25년]검색어는 단어의 조합이어야된다.</예>"
                        }
                    ]
                }
            ],
        ).output_text
            print("문맥DEBUG!!!!!!!!!!!!!!!!!!")
            print(search_text)
            print("\n\n\n\n")
        else:
            search_text = user_input 
            print("없는 문맥DEBUG!!!!!!!!!!!!!!!!!!")
            print(search_text)
            print("\n\n\n\n")
        context_input = [
        {
            "role": "user",
            "content": [{"type": "input_text", "text": search_text}]
        }
    ]

        response = client.responses.create(
            model="gpt-4o",
            input=context_input,  
            text={"format": {"type": "text"}},
            reasoning={},
            tools=[{
                "type": "web_search_preview",
                "user_location": {
                    "type": "approximate",
                    "country": "KR"
                },
                "search_context_size": "medium"
            }],
            tool_choice={"type": "web_search_preview"},
            temperature=1,
            max_output_tokens=2048,
            top_p=1,
            store=True
        )
        
        # ✅ 웹 검색 수행 여부 로그
        if any(getattr(item, "type", None) == "web_search_call" for item in getattr(response, "output", [])):
            print("✅ 🔍 웹 검색이 실제로 수행되었습니다.")
        else:
            print("⚠️ 웹 검색이 수행되지 않았습니다.")

        # ✅ 응답 메시지 추출
        print("DEBUG: Extracting message object from response.output")

        # 1. message 객체 추출 (ResponseOutputMessage)
        message = next(
            (item for item in response.output if getattr(item, "type", None) == "message"),
            None
        )
        if not message:
            print("DEBUG: No message found")
            return "❌ GPT 응답 메시지를 찾을 수 없습니다."

        # 2. content 중 output_text 블록 추출
        print("DEBUG: Looking for output_text block in message.content")
        content_block = next(
            (block for block in message.content if getattr(block, "type", None) == "output_text"),
            None
        )
        if not content_block:
            print("DEBUG: output_text block not found")
            return "❌ GPT 응답 내 output_text 항목을 찾을 수 없습니다."

        # 3. 텍스트 추출
        output_text = getattr(content_block, "text", "").strip()
        print(f"DEBUG: Extracted output_text: {output_text}")

        # 4. 출처(annotation) 파싱
        annotations = getattr(content_block, "annotations", [])
        print(f"DEBUG: Annotations: {annotations}")
        citations = []
        for a in annotations:
            if getattr(a, "type", None) == "url_citation":
                print(f"DEBUG: Found url_citation: {a}")
            title = getattr(a, "title", "출처")
            url = getattr(a, "url", "")
            citations.append(f"[{title}]({url})")

        # 5. 텍스트 + 출처 조합
        result = output_text
        print(f"DEBUG: Collected citations: {citations}")
        if citations:
            result += "\n\n📎 출처:\n" + "\n".join(citations)
        
        return result+"이 응답 형식 그대로 출력하세요 대답과 출처가 형식 그대로 다음대답에 담겨야합니다.엄밀하게."

    

    except Exception as e:
        return f"🚨 파싱 중 오류 발생: {str(e)}"


    except Exception as e:
        return f"🚨 오류 발생: {str(e)}"

class FunctionCalling:
    def __init__(self, model, available_functions=None):
        self.model = model
        default_functions = {
            "search_internet": search_internet,
        }

        if available_functions:
            default_functions.update(available_functions)

        self.available_functions = default_functions
       
    def analyze(self, user_message, tools):
        if not user_message or user_message.strip() == "":
            return {"type": "error", "message": "입력이 비어있습니다. 질문을 입력해주세요."}
    
            # 1. 모델 호출
        response = client.responses.create(
            model=model.o3_mini,
            input=user_message,
            tools=tools,
            tool_choice="auto",
            
        )
        return response.output
    

    def run(self, analyzed,context):
        ''' analyzed_dict: 함수 호출 정보, context: 현재 문맥'''
        context.append(analyzed)
        for tool_call in analyzed:
            if tool_call.get("type") != "function_call":
                continue
            function=tool_call["function"]
            func_name=function["name"]
            #실제 함수와 연결
            func_to_call = self.available_functions[func_name]

            try:

                func_args=json.loads(function["arguments"])#딕셔너리로 변환-> 문자열이 json형태입-> 이걸 딕셔너리로 변환
                
                if func_name == "search_internet":
                    # context는 이미 run 메서드의 매개변수로 받고 있음
                    func_response = func_to_call(chat_context=context[:], **func_args)
                else:
                    func_response=func_to_call(**func_args)
                context.append({
                    "tool_call_id": tool_call["id"],
                    "role": "tool",
                    "name": func_name, 
                    "content": str(func_response),
                    "parallel_tool_calls": True
                })#실행 결과를 문맥에 추가
  

            except Exception as e:
                print("Error occurred(run):",e)
                return makeup_response("[run 오류입니다]")
        return client.responses.create(model=self.model,input=context).model_dump()
    
   
    def call_function(self, analyzed_dict):        
        func_name = analyzed_dict["function_call"]["name"]
        func_to_call = self.available_functions[func_name]                
        try:            
            func_args = json.loads(analyzed_dict["function_call"]["arguments"])
            func_response = func_to_call(**func_args)
            return str(func_response)
        except Exception as e:
            print("Error occurred(call_function):",e)
            return makeup_response("[call_function 오류입니다]")
    