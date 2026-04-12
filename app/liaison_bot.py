import os
import sqlite3
import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, 
    filters, ContextTypes, CallbackQueryHandler, ConversationHandler
)
from groq import Groq

# --- CONFIG ---
import os

TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
DB_NAME = "community.db"

client = Groq(api_key=GROQ_API_KEY)

# Conversation States
START_STATE, ASK_QUESTIONS = range(2)

TEST_POLICIES = {
    "policy_99": {
        "name": "Urban Green Space",
        "summary": "Converting the old industrial lot into a community garden.",
        "details": "The project includes 50 plots for residents, a rainwater harvesting system, and a small amphitheater for local events. It aims to reduce urban heat and improve local biodiversity.",
        "group_link": "https://t.me/YOUR_GROUP_LINK" 
    }
}

# --- DB LOOKUP ---
def query_citizen(phone_number):
    try:
        conn = sqlite3.connect(DB_NAME)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        query = "SELECT * FROM citizens WHERE ? LIKE '%' || phone || '%'"
        cursor.execute(query, (phone_number,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None
    except Exception as e:
        print(f"DB Error: {e}")
        return None

# --- HANDLERS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    policy_id = context.args[0] if context.args else "policy_99"
    context.user_data['active_policy_id'] = policy_id
    
    btn = [[KeyboardButton("Verify My Residency", request_contact=True)]]
    await update.message.reply_text(
        "👋 Welcome to PolisenseAI.\n\nPlease share your contact to verify residency and start your personalized briefing.",
        reply_markup=ReplyKeyboardMarkup(btn, one_time_keyboard=True, resize_keyboard=True)
    )
    return START_STATE

async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw_phone = update.message.contact.phone_number.replace("+", "")
    policy_id = context.user_data.get('active_policy_id', 'policy_99')
    policy = TEST_POLICIES.get(policy_id)

    citizen = query_citizen(raw_phone)

    if citizen:
        context.user_data['citizen'] = citizen
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

        prompt = (
            f"Greet {citizen['first_name']}. Explain why their background as {citizen['profession_category']} "
            f"is vital for '{policy['name']}'. Then, ask them if they have any questions about the policy "
            f"or if they are ready to join the community discussion group."
        )
        
        res = client.chat.completions.create(messages=[{"role": "user", "content": prompt}], model="llama-3.3-70b-versatile")
        
        kbd = [[InlineKeyboardButton("✅ Join Group", url=policy['group_link'])],
               [InlineKeyboardButton("🚪 Exit", callback_data="exit")]]
        
        await update.message.reply_text(
            res.choices[0].message.content, 
            reply_markup=InlineKeyboardMarkup(kbd)
        )
        return ASK_QUESTIONS
    else:
        await update.message.reply_text("❌ Resident not found. Please contact city support.")
        return ConversationHandler.END

async def policy_qa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_query = update.message.text
    policy_id = context.user_data.get('active_policy_id', 'policy_99')
    policy = TEST_POLICIES.get(policy_id)
    citizen = context.user_data.get('citizen')

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    qa_prompt = (
        f"You are a policy expert. User {citizen['first_name']} asks: '{user_query}'.\n"
        f"Policy Details: {policy['details']}.\n"
        "Answer the question concisely and helpfully. At the end, remind them they can "
        "join the group for the live debate whenever they feel ready."
    )

    res = client.chat.completions.create(messages=[{"role": "user", "content": qa_prompt}], model="llama-3.3-70b-versatile")
    
    kbd = [[InlineKeyboardButton("✅ Join Group", url=policy['group_link'])],
           [InlineKeyboardButton("🚪 Exit", callback_data="exit")]]

    await update.message.reply_text(
        res.choices[0].message.content,
        reply_markup=InlineKeyboardMarkup(kbd)
    )
    return ASK_QUESTIONS

async def exit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🚪 You have exited the briefing. Have a great day!")
    return ConversationHandler.END

if __name__ == '__main__':
    app = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            START_STATE: [MessageHandler(filters.CONTACT, handle_contact)],
            ASK_QUESTIONS: [
                MessageHandler(filters.TEXT & (~filters.COMMAND), policy_qa),
                CallbackQueryHandler(exit_callback, pattern="^exit$")
            ],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    app.add_handler(conv_handler)
    # Global handler for exit button if conversation state isn't active
    app.add_handler(CallbackQueryHandler(exit_callback, pattern="^exit$"))

    print("--- INTERACTIVE LIAISON BOT ACTIVE ---")
    app.run_polling()