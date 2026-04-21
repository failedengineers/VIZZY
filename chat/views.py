from django.shortcuts import render
import os
import requests
import time
from dotenv import load_dotenv
load_dotenv()


from rest_framework.decorators import api_view
from rest_framework.response import Response

from groq import Groq



GROQ_API_KEY = os.getenv("GROQ_API_KEY")
STABLEHORDE_API_KEY = os.getenv("STABLE_HORDE_API_KEY")
##print("API KEY:", STABLEHORDE_API_KEY)

client = Groq(api_key=GROQ_API_KEY)


def home(request):
     #request.session.flush()
     return render(request, 'index.html')



def get_memory(request):
    return request.session.get("chat_memory", [])


def save_memory(request, memory):
    request.session["chat_memory"] = memory
    request.session.modified = True



def get_last_prompt(request):
    return request.session.get("last_image_prompt", "")

def save_last_prompt(request, final_prompt):
    request.session["last_image_prompt"] = final_prompt
    request.session.modified = True




def decide_intent(prompt, chat_memory, last_prompt):
    try:
        p = prompt.lower().strip()

        # Clear text requests should always stay text
        if any(x in p for x in ["write", "poem", "caption", "essay", "answer", "explain"]):
            return "text"

        # Story is text unless user clearly asks to visualize it
        if "story" in p and not any(x in p for x in ["visualize", "show", "scene", "draw", "illustrate"]):
            return "text"

        # Strong visual requests
        if any(x in p for x in ["visualize", "image", "photo", "picture", "poster", "draw", "illustrate", "scene", "design"]):
            return "image"

        # Refinement of last image
        if last_prompt and any(x in p for x in ["make it", "refine", "improve", "more like this", "another version"]):
            return "image"

        # LLM fallback for ambiguous prompts
        messages = [
            {
                "role": "system",
                "content": """
Return only one word: image or text.

Use image only for visual output.
Use text for stories, explanations, captions, poems, and normal chat.
If unsure, return text.
"""
            },
            {"role": "user", "content": prompt}
        ]

        res = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=messages,
            temperature=0,
            max_tokens=5
        )

        decision = res.choices[0].message.content.lower().strip()
        return "image" if "image" in decision else "text"

    except:
        return "text"
import re

def clean_text(text):
    text = re.sub(r"[*_`]+", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

@api_view(['POST'])
def chat_view(request):

    prompt = request.data.get('message')

    if not prompt:
        return Response({"error": "No message provided"}, status=400)

    chat_memory = get_memory(request)
    last_prompt = get_last_prompt(request)

    chat_memory.append({
        "role": "user",
        "content": prompt
    })

    chat_memory = chat_memory[-6:]

    intent = decide_intent(prompt, chat_memory, last_prompt)

    # -------- IMAGE FLOW --------
    if intent == "image":

        p = prompt.lower()

        story_refs = ["visualize this", "visualize that", "visualize the story", "show this", "scene from this", "from this story", "previous story"]
        refine_refs = ["make it", "refine", "improve", "more like this", "another version", "create more"]

        last_text = None
        for msg in reversed(chat_memory):
            if msg["role"] == "assistant":
                last_text = msg["content"]
                break

        # 🔥 CASE 1: story → image
        if any(x in p for x in story_refs) and last_text:
            final_prompt = f"""
Create a visual scene from this story:

{last_text}

cinematic, detailed, realistic lighting
"""

        # 🔥 CASE 2: refine previous image
        elif any(x in p for x in refine_refs) and last_prompt:
            final_prompt = f"""
Previous image prompt:
{last_prompt}

User change:
{prompt}

Keep same subject/style unless changed.
"""

        # 🔥 CASE 3: fresh image
        else:
            final_prompt = prompt

        img = generate_images(final_prompt)

        if img:
            save_last_prompt(request, final_prompt)
            res = {"type": "image", "data": img}
        else:
            res = {"type": "error", "data": "Server busy"}

    # -------- TEXT FLOW --------
    else:
        text = generate_text(prompt, chat_memory)

        res = {"type": "text", "data": text}

        chat_memory.append({
            "role": "assistant",
            "content": text
        })

    save_memory(request, chat_memory)
    return Response(res)
def generate_text(prompt, chat_memory):
    try:
        messages = [
    {
        "role": "system",
        "content": """
You are Vizzy Chat — an intelligent, conversational creative assistant.

Your purpose:
Help users create, transform, and explore visual, narrative, and experiential content through a simple chat interface.

You support both:
1. Home users (personal creativity, emotions, stories, art)
2. Business users (marketing, branding, product visuals, campaigns)

Core abilities:
- Understand user intent from natural language
- Generate ideas, stories, visuals, prompts, and concepts
- Suggest creative directions and variations
- Help refine and iterate outputs
- Maintain a conversational and intuitive experience

For creative requests:
- Be imaginative, expressive, and emotionally aware
- Suggest improvements or variations when useful
- Guide the user step-by-step if needed

For business requests:
- Think like a creative marketing assistant
- Focus on branding, aesthetics, and customer appeal
- Keep outputs practical and usable

For normal conversation (hi, hello, random talk):
- Respond naturally and friendly
- Keep it short and human-like
- Example: “Hey! What do you want to create today?”

Rules:
- Never say you are an AI model
- Always stay in “Vizzy Chat” personality
- Keep responses clear, simple, and engaging
- If user input is unclear, ask a helpful follow-up question
"""
    }
]

        messages.extend(chat_memory)

        completion = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=messages,
            temperature=0.8,
            max_tokens=800
        )

        return clean_text(completion.choices[0].message.content)

    except Exception as e:
        #print("Groq Error:", e)
        return "something went wrong. please try again."


def generate_images(prompt):
    try:
        ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID")
        API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN")

        url = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/ai/run/@cf/stabilityai/stable-diffusion-xl-base-1.0"

        headers = {
            "Authorization": f"Bearer {API_TOKEN}",
            "Content-Type": "application/json"
        }

        response = requests.post(
            url,
            headers=headers,
            json={
    "prompt": prompt,
    "negative_prompt": "people, person, human, car, vehicle, text, watermark, logo"
},
             timeout=60
        )

        if response.status_code == 200:
            import base64
            image_base64 = base64.b64encode(response.content).decode("utf-8")
            return [f"data:image/png;base64,{image_base64}"]

        #print("CF ERROR:", response.status_code, response.text)
        return None

    except Exception as e:
        #print("CF Exception:", e)
        return None

def enhance_prompt(prompt):
    return f"{prompt}, high quality"

