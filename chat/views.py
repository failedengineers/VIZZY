from django.shortcuts import render
import os
import requests
import time
import logging
from dotenv import load_dotenv

from rest_framework.decorators import api_view
from rest_framework.response import Response

from groq import Groq

# ✅ Logging setup
logger = logging.getLogger(__name__)

# Load env variables
load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Log if API key is missing
if not GROQ_API_KEY:
    logger.error("GROQ_API_KEY is missing!")

client = Groq(api_key=GROQ_API_KEY)


def home(request):
    logger.info("Home page accessed")
    return render(request, 'index.html')


def get_memory(request):
    return request.session.get("chat_memory", [])


def save_memory(request, memory):
    request.session["chat_memory"] = memory


@api_view(['POST'])
def chat_view(request):
    try:
        logger.info("==== /chat/api/ HIT ====")
        logger.info("Request data: %s", request.data)

        prompt = request.data.get('message')

        if not prompt:
            logger.error("No message provided in request")
            return Response({"error": "No message provided"}, status=400)

        logger.info("User prompt: %s", prompt)

        chat_memory = get_memory(request)

        chat_memory.append({
            "role": "user",
            "content": prompt
        })

        chat_memory = chat_memory[-6:]

        # Decide text vs image
        if any(word in prompt.lower() for word in ["image", "paint", "visual", "art", "draw", "create", "visualize"]):
            logger.info("Routing to IMAGE generation")

            img = generate_images(prompt)

            res = {"type": "image", "data": img}

        else:
            logger.info("Routing to TEXT generation")

            text = generate_text(prompt, chat_memory)

            logger.info("Generated text: %s", text)

            res = {"type": "text", "data": text}

            chat_memory.append({
                "role": "assistant",
                "content": text
            })

        save_memory(request, chat_memory)

        logger.info("Response sent successfully")

        return Response(res)

    except Exception as e:
        logger.exception("chat_view crashed")
        return Response({"error": "Internal Server Error"}, status=500)


def generate_text(prompt, chat_memory):
    try:
        logger.info("Calling Groq API...")

        messages = [
            {
                "role": "system",
                "content": "You are a creative assistant for storytelling, ideas, and emotional content."
            }
        ]

        messages.extend(chat_memory)

        logger.info("Messages payload: %s", messages)

        completion = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=messages,
            temperature=0.8,
            max_tokens=800
        )

        result = completion.choices[0].message.content

        logger.info("Groq response received")

        return result

    except Exception as e:
        logger.exception("Groq API failed")
        return "something went wrong. please try again."


def generate_images(prompt):
    try:
        logger.info("Starting image generation")

        headers = {
            "apikey": "0000000000",  # ⚠️ replace with real key if needed
            "Content-Type": "application/json"
        }

        final_prompt = enhance_prompt(prompt)

        logger.info("Enhanced prompt: %s", final_prompt)

        # Submit request
        submit_res = requests.post(
            "https://stablehorde.net/api/v2/generate/async",
            headers=headers,
            json={
                "prompt": final_prompt,
                "params": {
                    "n": 2,
                    "width": 512,
                    "height": 512,
                    "steps": 30,
                    "cfg_scale": 7
                }
            }
        )

        logger.info("Submit response status: %s", submit_res.status_code)
        logger.info("Submit response body: %s", submit_res.text)

        submit_data = submit_res.json()

        if "id" not in submit_data:
            logger.error("No ID returned from Stable Horde")
            return ["Error submitting request"]

        request_id = submit_data["id"]

        logger.info("Request ID: %s", request_id)

        # Polling
        for i in range(5):
            logger.info("Polling attempt %s", i + 1)

            time.sleep(2)

            check_res = requests.get(
                f"https://stablehorde.net/api/v2/generate/check/{request_id}",
                headers=headers
            )

            logger.info("Check response: %s", check_res.text)

            if check_res.json().get("done"):
                logger.info("Generation completed")
                break

        # Get final result
        result_res = requests.get(
            f"https://stablehorde.net/api/v2/generate/status/{request_id}",
            headers=headers
        )

        logger.info("Final result response: %s", result_res.text)

        result_data = result_res.json()

        img = [gen["img"] for gen in result_data.get("generations", [])]

        if not img:
            logger.warning("No images generated")
            return ["https://via.placeholder.com/512"]

        return img[:3]

    except Exception as e:
        logger.exception("Image generation failed")
        return ["https://via.placeholder.com/512"]


def enhance_prompt(prompt):
    if "real" in prompt.lower() or "photo" in prompt.lower():
        style = "photorealistic, DSLR, 8k, natural lighting"
    else:
        style = "digital art, cinematic lighting, ultra detailed, artstation style"

    return f"{prompt}, {style}, high quality, masterpiece"
