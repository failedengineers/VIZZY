from django.shortcuts import render
import os
import requests
import time
from dotenv import load_dotenv


from rest_framework.decorators import api_view
from rest_framework.response import Response

from groq import Groq



GROQ_API_KEY = os.getenv("GROQ_API_KEY")
STABLEHORDE_API_KEY = os.getenv("STABLE_HORDE_API_KEY")
##print("API KEY:", STABLEHORDE_API_KEY)

client = Groq(api_key=GROQ_API_KEY)


def home(request):
    return render(request, 'index.html')



def get_memory(request):
    return request.session.get("chat_memory", [])


def save_memory(request, memory):
    request.session["chat_memory"] = memory



@api_view(['POST'])
def chat_view(request):
    prompt = request.data.get('message')

    if not prompt:
        return Response({"error": "No message provided"}, status=400)

    chat_memory = get_memory(request)


    chat_memory.append({
        "role": "user",
        "content": prompt
    })

    chat_memory = chat_memory[-6:]

    
    if any(word in prompt.lower() for word in ["image", "paint", "visual", "art", "draw",'create','visualize']):
        img = generate_images(prompt)
        if img:
            res = {"type": "image", "data": img}
        else:
            res = {"type": "error",
                   "data": "Server is busy, try again in few seconds"}
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

        return completion.choices[0].message.content

    except Exception as e:
        #print("Groq Error:", e)
        return "something went wrong. please try again."


def generate_images(prompt):
    try:
        headers = {
            "apikey": STABLEHORDE_API_KEY,
            "Client-Agent": "vizzy-app:1.0",
            "Content-Type": "application/json"
        }

        final_prompt = enhance_prompt(prompt)

        # submit request
        submit_res = requests.post(
            "https://stablehorde.net/api/v2/generate/async",
            headers=headers,
            json={
                "prompt": final_prompt,
                "params": {
                    "n": 2,
                    "width": 512,
                    "height": 512,
                    "steps": 15,
                    "cfg_scale": 7
                }
            }
        )

        submit_data = submit_res.json()
        #print("SUBMIT:", submit_data)

        if "id" not in submit_data:
            #print("Submit Error:", submit_data)
            return None

        request_id = submit_data["id"]
        for _ in range(20):
            
            time.sleep(2)
            check_res = requests.get(f"https://stablehorde.net/api/v2/generate/status/{request_id}",headers=headers).json()
            if check_res.get("done"):
                break

        
        result_res = requests.get(
            f"https://stablehorde.net/api/v2/generate/status/{request_id}",
            headers=headers
        )

        result_data = result_res.json()
        #print("RESULT:", result_data)

        valid_images = []
        for gen in result_data.get("generations", []):
            url = gen.get("img")
            if gen.get("censored") or gen.get("nsfw"):
                continue
            if url:
                valid_images.append(url)
        if not valid_images:
            return None
        return valid_images[:3]

    except Exception as e:
        #print("image Error:", e)
        return None


def enhance_prompt(prompt):
    if "real" in prompt.lower() or "photo" in prompt.lower():
        style = "photorealistic, DSLR, 8k, natural lighting"
    else:
        style = "digital art, cinematic lighting, ultra detailed, artstation style"

    return f"{prompt}, {style}, high quality, masterpiece"

