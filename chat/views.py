from django.shortcuts import render
import os
import requests
import time
from dotenv import load_dotenv

from rest_framework.decorators import api_view
from rest_framework.response import Response

from groq import Groq

load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not GROQ_API_KEY:
    print("Missing GROQ_API_KEY")

client = Groq(api_key=GROQ_API_KEY)


def home(request):
    return render(request, 'index.html')


def get_memory(request):
    return request.session.get("chat_memory", [])


def save_memory(request, memory):
    request.session["chat_memory"] = memory


@api_view(['POST'])
def chat_view(request):
    try:
        prompt = request.data.get('message')

        if not prompt:
            return Response({"error": "No message provided"}, status=400)

        chat_memory = get_memory(request)

        chat_memory.append({
            "role": "user",
            "content": prompt
        })

        chat_memory = chat_memory[-6:]

        # Detect image intent
        if any(word in prompt.lower() for word in ["image", "paint", "visual", "art", "draw", "create", "visualize"]):
            img = generate_images(prompt)
            res = {"type": "image", "data": img}
        else:
            text = generate_text(prompt, chat_memory)
            res = {"type": "text", "data": text}

            chat_memory.append({
                "role": "assistant",
                "content": text
            })

        save_memory(request, chat_memory)

        return Response(res)

    except Exception as e:
        print("VIEW ERROR:", str(e))
        return Response({"error": str(e)}, status=500)


def generate_text(prompt, chat_memory):
    try:
        messages = [
            {
                "role": "system",
                "content": "You are a creative assistant for storytelling, ideas, and emotional content."
            }
        ]

        messages.extend(chat_memory)

        completion = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=messages,
            temperature=0.8,
            max_tokens=800
        )

        return completion.choices[0].message.content

    except Exception as e:
        print("Groq Error:", e)
        return "Something went wrong. Please try again."


def generate_images(prompt):
    try:
        # ✅ FIXED HEADERS (no fake apikey)
        headers = {
            "Client-Agent": "vizzy-app",
            "Content-Type": "application/json"
        }

        final_prompt = enhance_prompt(prompt)

        # Submit request
        submit_res = requests.post(
            "https://stablehorde.net/api/v2/generate/async",
            headers=headers,
            json={
                "prompt": final_prompt,
                "params": {
                    "n": 3,
                    "width": 512,
                    "height": 512,
                    "steps": 30,
                    "cfg_scale": 7
                }
            },
            timeout=30
        )

        submit_data = submit_res.json()
        print("Submit response:", submit_data)

        if "id" not in submit_data:
            return ["Error submitting request"]

        request_id = submit_data["id"]

        # Polling
        for _ in range(15):
            time.sleep(2)

            check_res = requests.get(
                f"https://stablehorde.net/api/v2/generate/check/{request_id}",
                headers=headers,
                timeout=30
            )

            if check_res.json().get("done"):
                break

        # Get result
        result_res = requests.get(
            f"https://stablehorde.net/api/v2/generate/status/{request_id}",
            headers=headers,
            timeout=30
        )

        result_data = result_res.json()

        print("Result response:", result_data)

        img = [gen["img"] for gen in result_data.get("generations", [])]

        if not img:
            return ["https://via.placeholder.com/512"]

        return img[:3]

    except Exception as e:
        print("IMAGE ERROR:", e)
        return ["https://via.placeholder.com/512"]


def enhance_prompt(prompt):
    if "real" in prompt.lower() or "photo" in prompt.lower():
        style = "photorealistic, DSLR, 8k, natural lighting"
    else:
        style = "digital art, cinematic lighting, ultra detailed, artstation style"

    return f"{prompt}, {style}, high quality, masterpiece"
