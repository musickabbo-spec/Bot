import os
import time
import threading
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from fastapi import FastAPI, Request
import uvicorn
import requests
from langchain_google_genai import ChatGoogleGenerativeAI

app = FastAPI()
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ALLOWED_USER_ID = int(os.environ.get("ALLOWED_USER_ID", 0))
HF_SPACE_URL = os.environ.get("HF_SPACE_URL") 
RENDER_URL = os.environ.get("RENDER_URL")     

# জেমিনি কী পুল (প্ল্যানিং ও চ্যাটের জন্য)
GEMINI_KEYS = [os.environ.get("GEMINI_KEY_1"), os.environ.get("GEMINI_KEY_2")]
gemini_index = 0

bot = telebot.TeleBot(BOT_TOKEN)
user_sessions = {}

def get_planner_llm():
    global gemini_index
    valid_keys = [k for k in GEMINI_KEYS if k]
    selected_key = valid_keys[gemini_index % len(valid_keys)]
    gemini_index += 1
    return ChatGoogleGenerativeAI(model="gemini-2.5-flash", google_api_key=selected_key)

@bot.message_handler(func=lambda message: message.from_user.id == ALLOWED_USER_ID)
def handle_chat(message):
    chat_id = message.chat.id
    waiting = bot.send_message(chat_id, "⏳ একটু ভাবছি...")
    
    try:
        llm = get_planner_llm()
        
        # জেমিনিকে কড়া নির্দেশ দেওয়া হচ্ছে চ্যাট এবং টাস্ক আলাদা করার জন্য
        prompt = (
            "You are a helpful AI Assistant and Browser Automation Expert.\n"
            "Look at the user's message and strictly follow these rules:\n\n"
            "Rule 1: If the user is just greeting you (like 'hello', 'hi', 'হ্যালো', 'কেমন আছো'), asking general questions, "
            "or discussing options/ideas, reply to them nicely in Bengali as a regular chat companion. DO NOT make a step-by-step browser automation plan.\n"
            "Rule 2: If the user explicitly asks you to do a specific job on a website, login somewhere, or perform a browser automation task, "
            "then create a short, professional, step-by-step browser automation plan in Bengali explaining how you will do it. "
            "CRITICAL: If and only if you are providing a browser automation plan under Rule 2, you must include the exact tag '[TASK_PLAN]' anywhere in your response.\n\n"
            f"User message: {message.text}"
        )
        
        res = llm.invoke(prompt)
        response_text = res.content
        
        # যদি রেসপন্সে [TASK_PLAN] ট্যাগটি থাকে, তবেই বাটন দেখাবে
        if "[TASK_PLAN]" in response_text:
            plan_text = response_text.replace("[TASK_PLAN]", "").strip()
            user_sessions[chat_id] = message.text
            
            markup = InlineKeyboardMarkup()
            markup.row(
                InlineKeyboardButton("✅ নিশ্চিত করুন", callback_data="confirm"), 
                InlineKeyboardButton("❌ বাতিল", callback_data="cancel")
            )
            
            bot.delete_message(chat_id, waiting.message_id)
            bot.send_message(chat_id, f"📋 **পরিকল্পনা রিপোর্ট:**\n\n{plan_text}", reply_markup=markup, parse_mode="Markdown")
        else:
            # সাধারণ চ্যাটের ক্ষেত্রে কোনো বাটন ছাড়াই ডিরেক্ট মেসেজ পাঠাবে
            bot.delete_message(chat_id, waiting.message_id)
            bot.send_message(chat_id, response_text)
            
    except Exception as e:
        bot.edit_message_text(f"❌ এরর: {e}", chat_id, waiting.message_id)

@bot.callback_query_handler(func=lambda call: True)
def buttons(call):
    chat_id = call.message.chat.id
    if call.data == "cancel":
        bot.answer_callback_query(call.id, "টাস্ক বাতিল করা হয়েছে।")
        bot.edit_message_text("❌ আপনি কাজটি বাতিল করেছেন। নতুন কোনো আলোচনা বা কাজ থাকলে বলুন।", chat_id, call.message.message_id)
        user_sessions.pop(chat_id, None)
        return

    if call.data == "confirm":
        task = user_sessions.get(chat_id)
        bot.edit_message_text("🚀 হাগিংফেস ইঞ্জিনে টাস্ক পাঠানো হয়েছে। ব্রাউজার ব্যাকএন্ডে কাজ শুরু করছে...", chat_id, call.message.message_id)
        
        try:
            requests.post(f"{HF_SPACE_URL}/execute", json={"task": task, "chat_id": chat_id, "render_url": RENDER_URL}, timeout=10)
        except Exception as e:
            bot.send_message(chat_id, f"❌ হাগিংফেসের সাথে কানেক্ট করা যায়নি: {e}")

@app.post("/webhook-result")
async def receive_result(request: Request):
    data = await request.json()
    chat_id = data["chat_id"]
    result = data["result"]
    if data["status"] == "success":
        bot.send_message(chat_id, f"🏁 **কাজ সম্পন্ন!**\n\n{result}")
    else:
        bot.send_message(chat_id, f"⚠️ **ব্রাউজার এরর:**\n`{result}`", parse_mode="Markdown")
    return {"status": "delivered"}

@app.get("/")
def health():
    return {"status": "Bot Gateway is Online"}

if __name__ == "__main__":
    try:
        bot.remove_webhook()
        bot.send_message(ALLOWED_USER_ID, "🚀 **সিস্টেম অনলাইন!** রেন্ডার বট গেটওয়ে সফলভাবে আপডেট হয়েছে।")
    except: pass
    
    threading.Thread(target=lambda: bot.infinity_polling(), daemon=True).start()
    uvicorn.run(app, host="0.0.0.0", port=10000)
