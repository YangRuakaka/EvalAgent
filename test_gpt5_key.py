import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path("d:/Github/EvalAgent/backend/.env"))

from openai import OpenAI

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

try:
    resp = client.chat.completions.create(
        model="gpt-5",
        messages=[{"role": "user", "content": "Say 'ok' in one word."}],
        max_completion_tokens=10,
    )
    print("OK  GPT-5 supported!")
    print("Response :", resp.choices[0].message.content)
    print("Model    :", resp.model)
except Exception as e:
    print("FAIL  GPT-5 NOT supported")
    print(type(e).__name__, ":", e)
