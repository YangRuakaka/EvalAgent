
import os
import requests
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"), override=True)

def test_openai_key():
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        print("OPENAI_API_KEY 未设置")
        return
    try:
        client = OpenAI(api_key=key)
        models = client.models.list()
        print("OpenAI Key 有效，模型数量：", len(models.data))
    except Exception as e:
        print("OpenAI Key 测试失败：", e)

def test_deepseek_key():
    key = os.getenv("DEEPSEEK_API_KEY")
    if not key:
        print("DEEPSEEK_API_KEY 未设置")
        return
    url = "https://api.deepseek.com/v1/models"
    headers = {"Authorization": f"Bearer {key}"}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            print("DeepSeek Key 有效，模型数量：", len(resp.json().get("data", [])))
        else:
            print(f"DeepSeek Key 测试失败，状态码: {resp.status_code}，内容: {resp.text}")
    except Exception as e:
        print("DeepSeek Key 测试异常：", e)

if __name__ == "__main__":
    test_openai_key()
    test_deepseek_key()
