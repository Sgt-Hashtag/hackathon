import os
import sqlite3
import logging
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from groq import Groq

# 1. LOGGING & CONFIG
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)

TOKEN = os.getenv("MODERATOR_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
DB_PATH = "community.db" # Standard path for shared Docker volume

client = Groq(api_key=GROQ_API_KEY)

# Local memory to store the debate transcript
chat_history = {}

# --- 2. CORE FUNCTIONS ---

async def monitor_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Monitors messages, filters toxicity, and triggers the final report."""
    chat_id = update.effective_chat.id
    user_text = update.message.text
    user_name = update.effective_user.first_name

    # --- AI TOXICITY FILTER ---
    # Fast check using a smaller model to keep the debate moving
    toxic_prompt = f"Is the following text toxic, a personal attack, or hateful? Answer only 'YES' or 'NO': {user_text}"
    try:
        check = client.chat.completions.create(
            messages=[{"role": "user", "content": toxic_prompt}], 
            model="llama-3.1-8b-instant"
        )
        if "YES" in check.choices[0].message.content.upper():
            await update.message.delete()
            await update.message.reply_text(f"🚫 {user_name}, your message was removed for violating community guidelines.")
            return
    except Exception as e:
        logging.error(f"Toxicity Check Error: {e}")

    # --- STORE HISTORY ---
    if chat_id not in chat_history:
        chat_history[chat_id] = []
    
    chat_history[chat_id].append(f"{user_name}: {user_text}")

    # --- TRIGGER: END OF CONVERSATION ---
    if "end conversation" in user_text.lower():
        await generate_final_report(update, context)

async def welcome_and_summarize(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Provides a briefing for new members so they can catch up instantly."""
    chat_id = update.effective_chat.id
    history = chat_history.get(chat_id, [])
    
    if not history:
        return

    # Use the last 15 messages for context
    context_text = "\n".join(history[-15:])
    summary_prompt = (
        f"A new resident just joined. Summarize the current debate vibe and main arguments "
        f"concisely so they can contribute immediately. History:\n{context_text}"
    )

    try:
        res = client.chat.completions.create(
            messages=[{"role": "user", "content": summary_prompt}],
            model="llama-3.1-8b-instant"
        )
        await update.message.reply_text(
            f"👋 Welcome! Here is a briefing on the current discussion:\n\n{res.choices[0].message.content}"
        )
    except Exception as e:
        logging.error(f"Summarization Error: {e}")

async def generate_final_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Synthesizes consensus, updates DB counts, and closes the group."""
    chat_id = update.effective_chat.id
    history_list = chat_history.get(chat_id, [])

    if not history_list:
        await update.message.reply_text("No conversation history found.")
        return

    await update.message.reply_text("📝 'End Conversation' detected. Analyzing discourse and recording participation...")

    # 1. GENERATE THE HABERMASIAN REPORT
    transcript = "\n".join(history_list)
    report_prompt = (
        "You are a Senior Policy Analyst. Generate a 'Civic Feedback Report' from this transcript. "
        "Highlight: 1. Key Areas of Agreement, 2. Unresolved Concerns, 3. Proposed Solutions. "
        f"Transcript:\n{transcript}"
    )

    try:
        completion = client.chat.completions.create(
            messages=[{"role": "user", "content": report_prompt}],
            model="llama-3.3-70b-versatile"
        )
        report = completion.choices[0].message.content

        # 2. UPDATE PARTICIPATION COUNTS (The Feedback Loop)
        participants = set([entry.split(":")[0] for entry in history_list])
        updated_count = 0
        
        conn = sqlite3.connect(DB_PATH)
        for name in participants:
            # We increment the count to increase 'Fatigue' for the next scoring round
            conn.execute("""
                UPDATE citizens 
                SET past_participation_count = COALESCE(past_participation_count, 0) + 1 
                WHERE first_name = ?
            """, (name,))
            updated_count += 1
        conn.commit()
        conn.close()

        # 3. OUTPUT & GROUP CLOSURE
        await update.message.reply_text(f"🏛 **OFFICIAL POLICY FEEDBACK REPORT**\n\n{report}")
        await update.message.reply_text(
            f"🔒 Discussion concluded. Participation recorded for {updated_count} residents.\n"
            "The Moderator Agent is now leaving. This space is archived."
        )

        # 4. LEAVE GROUP (Simulates group deletion/closure)
        await context.bot.leave_chat(chat_id)
        
        # Clear memory
        del chat_history[chat_id]

    except Exception as e:
        await update.message.reply_text(f"⚠️ Error during closure: {e}")
        logging.error(f"Report Generation Error: {e}")

# --- 3. EXECUTION ---
if __name__ == '__main__':
    if not TOKEN:
        print("❌ Error: MODERATOR_TOKEN not found in environment.")
        exit(1)

    print("--- MODERATOR BOT IS ACTIVE ---")
    application = Application.builder().token(TOKEN).build()

    # Handlers
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), monitor_conversation))
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_and_summarize))

    application.run_polling()