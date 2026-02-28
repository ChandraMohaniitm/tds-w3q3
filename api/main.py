from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import sys
from io import StringIO
import traceback
import os
import json
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class CodeRequest(BaseModel):
    code: str

class CodeResponse(BaseModel):
    error: List[int]
    result: str


def execute_python_code(code: str) -> dict:
    old_stdout = sys.stdout
    sys.stdout = StringIO()

    try:
        _globals = {}
        exec(code, _globals)
        output = sys.stdout.getvalue()
        return {"success": True, "output": output}

    except Exception:
        output = sys.stdout.getvalue()
        output += traceback.format_exc()
        return {"success": False, "output": output}

    finally:
        sys.stdout = old_stdout


def analyze_error_with_ai(code: str, traceback_str: str) -> List[int]:
    api_key = os.environ.get("OPENROUTER_API_KEY")

    if not api_key:
        print("Warning: OPENROUTER_API_KEY not found. Using fallback.")
        return fallback_error_analyzer(traceback_str)

    try:
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key
        )

        prompt = f"""
You are a Python debugging assistant.

Analyze the following Python code and traceback.
Return ONLY valid JSON in this format:
{{"error_lines": [line_numbers]}}

CODE:
{code}

TRACEBACK:
{traceback_str}
"""

        response = client.chat.completions.create(
            model="openai/gpt-4o-mini",
            messages=[
                {"role": "user", "content": prompt}
            ],
            temperature=0
        )

        content = response.choices[0].message.content.strip()

        parsed = json.loads(content)

        return parsed.get("error_lines", [])

    except Exception as e:
        print("OpenRouter Error:", e)
        return fallback_error_analyzer(traceback_str)


def fallback_error_analyzer(traceback_str: str) -> List[int]:
    import re
    matches = re.findall(r'line (\d+)', traceback_str)
    if matches:
        return [int(matches[-1])]
    return []


@app.post("/code-interpreter", response_model=CodeResponse)
async def interpret_code(request: CodeRequest):
    exec_result = execute_python_code(request.code)

    if exec_result["success"]:
        return CodeResponse(error=[], result=exec_result["output"])
    else:
        error_lines = analyze_error_with_ai(request.code, exec_result["output"])
        return CodeResponse(error=error_lines, result=exec_result["output"])

