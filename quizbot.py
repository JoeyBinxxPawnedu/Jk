import sqlite3
import json
import operator
import random
import telegram
import os
import logging
import time
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackQueryHandler

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

def setup_database():
    conn = sqlite3.connect('highscores.db')
    cursor = conn.cursor()

    cursor.execute('''CREATE TABLE IF NOT EXISTS highscores
                      (user_id INTEGER, user_name TEXT, chat_id INTEGER, score INTEGER,
                       PRIMARY KEY (user_id, chat_id))''')

    conn.commit()
    conn.close()

class QuizBot:
    def __init__(self, token):
        self.bot = telegram.Bot(token=token)
        self.updater = Updater(token=token, use_context=True)
        self.dispatcher = self.updater.dispatcher

        # Load the questions from the questions.json file
        with open('questions.json', 'r') as f:
            self.questions = json.load(f)

        # Register the handlers
        self.register_handlers()

        # Set up the SQLite database for high scores
        setup_database()

    def register_handlers(self):
        self.dispatcher.add_handler(CommandHandler('start', self.start))
        self.dispatcher.add_handler(CallbackQueryHandler(self.answer))
        self.dispatcher.add_handler(CommandHandler('score', self.score))
        self.dispatcher.add_handler(CommandHandler('highscores', self.highscores))
        self.dispatcher.add_handler(CommandHandler('leaderboard', self.leaderboard))
        self.dispatcher.add_handler(CommandHandler('end', self.end))
        self.dispatcher.add_handler(CommandHandler('next', self.next_question))

    def start(self, update, context):
        context.chat_data['score'] = 0
        context.chat_data['question_index'] = 0
        context.chat_data['questions'] = self.shuffle_questions(self.questions)
        self.ask_question(update, context)

    def answer(self, update, context):
        query = update.callback_query
        query.answer()

        user_first_name = update.effective_user.first_name
        correct_answer = context.chat_data['questions'][context.chat_data['question_index']]['correct_answer']
        if query.data == correct_answer:
            user_id = update.effective_user.id
            user_name = update.effective_user.full_name
            chat_id = update.effective_chat.id
            score = self.get_score(user_id, chat_id)
            score += 10
            context.chat_data['score'] = score
            self.update_highscore(user_id, user_name, chat_id, context.chat_data['score'])
            query.edit_message_text(text=f"{user_first_name}, That's Correct! 🎉 Your score: {context.chat_data['score']}")
        else:
            query.edit_message_text(text=f"Sorry {user_first_name}, that's incorrect. 😞 Your score: {context.chat_data['score']}")

        context.chat_data['question_index'] += 1
        if context.chat_data['question_index'] < len(context.chat_data['questions']):
            self.next_question(update, context)
        else:
            self.end_quiz(update, context)

    def ask_question(self, update, context):
        question = context.chat_data['questions'][context.chat_data['question_index']]['question']
        answer_options = context.chat_data['questions'][context.chat_data['question_index']]['answer_options']
        answer_options_text = '\n'.join(['{}. {}'.format(chr(i+65), option) for i, option in enumerate(answer_options)])
        keyboard = [[InlineKeyboardButton(answer_option, callback_data=answer_option) for answer_option in answer_options]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        message = self.bot.send_message(chat_id=update.effective_chat.id, text=question + '\n' + answer_options_text, reply_markup=reply_markup)

    def next_question(self, update, context):
        self.ask_question(update, context)

    def score(self, update, context):
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        user_score = self.get_score(user_id, chat_id)
        update.message.reply_text(f"Your current score is: {user_score}")

    def highscores(self, update, context):
        chat_id = update.effective_chat.id
        highscores = self.get_highscores(chat_id)
        if not highscores:
            update.message.reply_text("No highscores for this chat yet.")
        else:
            highscore_message = "Highscores for this chat:\n"
            for idx, highscore in enumerate(highscores):
                if idx < 3:
                    emoji = "🥇"
                elif idx >= 3 and idx < 6:
                    emoji = "🥈"
                else:
                    emoji = "🥉"

                highscore_message += "{}. {} {} - Score: {}\n".format(idx + 1, emoji, highscore[1], highscore[3])

            update.message.reply_text(highscore_message)

    def leaderboard(self, update, context):
        global_highscores = self.get_global_highscores()
        if not global_highscores:
            update.message.reply_text("No global highscores yet.")
        else:
            leaderboard_message = "Global Leaderboard:\n"
            for idx, highscore in enumerate(global_highscores):
                leaderboard_message += "{}. {} - Score: {}\n".format(idx + 1, highscore[1], highscore[2])

            update.message.reply_text(leaderboard_message)

    def end(self, update, context):
        self.end_quiz(update, context)

    def end_quiz(self, update, context):
        user_first_name = update.effective_user.first_name
        update.message.reply_text(f"🏁 {user_first_name}, your quiz has ended.\nYour score: {context.chat_data['score']}\nType /start to start a new quiz.")

    def shuffle_questions(self, questions):
        shuffled_questions = random.sample(questions, len(questions))
        for question in shuffled_questions:
            question['answer_options'] = random.sample(question['answer_options'], len(question['answer_options']))
        return shuffled_questions

    def get_score(self, user_id, chat_id):
        conn = sqlite3.connect('highscores.db')
        cursor = conn.cursor()
        cursor.execute("SELECT score FROM highscores WHERE user_id=? AND chat_id=?", (user_id, chat_id))
        row = cursor.fetchone()
        conn.close()

        if row:
            return row[0]
        return 0

    def update_highscore(self, user_id, user_name, chat_id, score):
        conn = sqlite3.connect('highscores.db')
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO highscores (user_id, user_name, chat_id, score) VALUES (?, ?, ?, ?)", (user_id, user_name, chat_id, score))
        conn.commit()
        conn.close()

    def get_highscores(self, chat_id):
        conn = sqlite3.connect('highscores.db')
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM highscores WHERE chat_id=? ORDER BY score DESC", (chat_id,))
        rows = cursor.fetchall()
        conn.close()
        return rows

    def get_global_highscores(self):
        conn = sqlite3.connect('highscores.db')
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, user_name, SUM(score) as total_score FROM highscores GROUP BY user_id, user_name ORDER BY total_score DESC")
        rows = cursor.fetchall()
        conn.close()
        return rows

    def run(self):
        self.updater.start_polling()
        self.updater.idle()

if __name__ == '__main__':
    with open('token.txt', 'r') as f:
        token = f.read().strip()
    quiz_bot = QuizBot(token)
    quiz_bot.run()
