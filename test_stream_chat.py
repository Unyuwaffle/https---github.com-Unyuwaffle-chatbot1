import requests

# 언어 선택 매핑
language_map = {
    "1": ("KOR", "한국어"),
    "2": ("ENG", "영어"),
    "3": ("VI", "베트남어"),
    "4": ("JPN", "일본어"),
    "5": ("CHN", "중국어"),
}

def select_language():
    print("언어를 선택하세요:")
    for k, v in language_map.items():
        print(f"{k}. {v[1]}")
    while True:
        choice = input("번호 입력: ").strip()
        if choice in language_map:
            return language_map[choice][0]
        print("잘못된 입력입니다. 다시 선택하세요.")

def main():
    url = "http://127.0.0.1:8000/stream-chat"
    language = select_language()
    print(f"선택된 언어: {language}")

    while True:
        msg = input("\n질문 입력 (종료: exit, 언어변경: /lang): ").strip()
        if msg.lower() == "exit":
            print("테스트 종료.")
            break
        if msg.lower() in ["/lang", "/언어"]:
            language = select_language()
            print(f"언어가 변경되었습니다: {language}")
            continue

        payload = {"message": msg, "language": language}
        try:
            with requests.post(url, json=payload, stream=True, timeout=60) as resp:
                print("응답:")
                for chunk in resp.iter_content(chunk_size=None, decode_unicode=True):
                    print(chunk, end="", flush=True)
                print("\n" + "-"*40)
        except Exception as e:
            print(f"요청 실패: {e}")

if __name__ == "__main__":
    main()