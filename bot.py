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
HF_SPACE_URL = os.environ.get("HF_SPACE_URL") # আপনার হাগিংফেস স্পেসের URL
RENDER_URL = os.environ.get("RENDER_URL")     # রেন্ডার নিজে নিজের URL

# জেমিনি কী পুল (প্ল্যানিংয়ের জন্য)
GEMINI_KEYS = [os.environ.get("GEMINI_KEY_1"), os.environ.get("GEMINI_KEY_2")]
gemini_index = 0

bot = telebot.TeleBot(BOT_TOKEN)
user_sessions = {}

def get_planner_llm():
    global gemini_index
    selected_key = GEMINI_KEYS[gemini_index]
    gemini_index = (gemini_index + 1) % len(GEMINI_KEYS)
    return ChatGoogleGenerativeAI(model="gemini-2.5-flash", google_api_key=selected_key)

@bot.message_handler(func=lambda message: message.from_user.id == ALLOWED_USER_ID)
def handle_chat(message):
    chat_id = message.chat.id
    waiting = bot.send_message(chat_id, "🧠 পরিকল্পনা তৈরি করছি...")
    
    try:
        llm = get_planner_llm()
        res = llm.invoke(f"Create a short step-by-step browser automation plan in Bengali: '{message.text}'")
        plan_text = res.content
        
        user_sessions[chat_id] = message.text
        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton("✅ নিশ্চিত করুন", callback_data="confirm"), InlineKeyboardButton("❌ বাতিল", callback_data="cancel"))
        
        bot.delete_message(chat_id, waiting.message_id)
        bot.send_message(chat_id, f"📋 **পরিকল্পনা:**\n\n{plan_text}", reply_markup=markup, parse_mode="Markdown")
    except Exception as e:
        bot.edit_message_text(f"❌ এরর: {e}", chat_id, waiting.message_id)

@bot.callback_query_handler(func=lambda call: True)
def buttons(call):
    chat_id = call.message.chat.id
    if call.data == "confirm":
        task = user_sessions.get(chat_id)
        bot.edit_message_text("🚀 হাগিংফেস ইঞ্জিনে টাস্ক পাঠানো হয়েছে। ব্রাউজার কাজ শুরু করছে...", chat_id, call.message.message_id)
        
        # হাগিংফেস এপিআই তে টাস্ক ট্রিগার করা
        try:
            requests.post(f"{HF_SPACE_URL}/execute", json={"task": task, "chat_id": chat_id, "render_url": RENDER_URL})
        except Exception as e:
            bot.send_message(chat_id, f"❌ হাগিংফেসের সাথে কানেক্ট করা যায়নি: {e}")

# হাগিংফেস কাজ শেষ করে এই এন্ডপয়েন্টে রেজাল্ট পাঠাবে
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
    # রেন্ডার স্টার্ট হওয়ার মেসেজ পাঠানো
    try:
        bot.remove_webhook()
        bot.send_message(ALLOWED_USER_ID, "🚀 **সিস্টেম অনলাইন!** রেন্ডার বট গেটওয়ে চালু হয়েছে।")
    except: pass
    
    threading.Thread(target=lambda: bot.infinity_polling(), daemon=True).start()
    uvicorn.run(app, host="0.0.0.0", port=10000)
