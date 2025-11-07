# backend/ai_generator.py
import os
from openai import OpenAI
import openai as openai_legacy

def _get_new_client(api_key=None):
    """
    Returns a new OpenAI client using either provided key or environment variable.
    """
    key = api_key or os.environ.get("OPENAI_API_KEY")
    if not key:
        raise Exception("OPENAI_API_KEY not set in environment or passed in.")
    return OpenAI(api_key=key)

def _try_new_client(prompt_messages, model="gpt-4o-mini", temperature=0.8, api_key=None):
    client = _get_new_client(api_key)
    return client.chat.completions.create(model=model, messages=prompt_messages, temperature=temperature)

def _try_legacy(prompt_messages, model="gpt-3.5-turbo", temperature=0.8):
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise Exception("OPENAI_API_KEY not set in environment.")
    openai_legacy.api_key = key
    return openai_legacy.ChatCompletion.create(model=model, messages=prompt_messages, temperature=temperature)

def generate_listing(data, api_key=None):
    """
    Generates a car listing using OpenAI. Accepts optional api_key for user input.
    """
    tone = data.get("tone", "Professional")
    prompt_messages = [
        {"role": "system", "content": "You are a helpful car sales assistant."},
        {"role": "user", "content": f"""
You are an expert car sales assistant. Create a compelling 100–150 word listing in separate paragraphs with emojis.
Tone: {tone}
Car: {data.get('year')} {data.get('make')} {data.get('model')}
Mileage: {data.get('mileage')}
Colour: {data.get('color')}
Fuel: {data.get('fuel')}
Transmission: {data.get('transmission')}
Price: {data.get('price')}
Features: {data.get('features')}
Dealer notes: {data.get('notes')}
"""}
    ]
    try:
        resp = _try_new_client(prompt_messages, api_key=api_key)
        return resp.choices[0].message.content
    except Exception:
        try:
            resp = _try_legacy(prompt_messages)
            return resp['choices'][0]['message']['content']
        except Exception as e:
            raise Exception(f"OpenAI call failed: {e}")

def generate_caption(data, api_key=None):
    """
    Generates a short social media caption for a car.
    """
    prompt_messages = [{"role": "user", "content": f"Create a short, catchy Instagram/TikTok caption for this car: {data.get('make')} {data.get('model')}. Description: {data.get('desc')}"}]
    try:
        resp = _try_new_client(prompt_messages, temperature=0.9, api_key=api_key)
        return resp.choices[0].message.content
    except Exception:
        try:
            resp = _try_legacy(prompt_messages, temperature=0.9)
            return resp['choices'][0]['message']['content']
        except Exception as e:
            raise Exception(f"Caption generation failed: {e}")
