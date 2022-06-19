#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import json
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, RegexHandler, ConversationHandler, CallbackQueryHandler
from telegram import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext.updater import Updater
from telegram.update import Update
from telegram.ext.callbackcontext import CallbackContext
from telegram.ext.commandhandler import CommandHandler
from telegram.ext.messagehandler import MessageHandler
from telegram.ext.filters import Filters
from functools import wraps
from collections import OrderedDict
import locale
import time
import _thread as thread
import requests
import re
import os
import pickle

import datetime

user_config = {}

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)

def restricted(func):
    @wraps(func)
    def wrapped(update, context, *args, **kwargs):
        if update.message is not None:
            chat_id = update.message.chat.id
        else:
            chat_id = update.callback_query.message.chat.id
        if str(chat_id) != user_config['telegram_chat_id']:
            print('Unauthorized access denied for chat {}.'.format(chat_id))
            context.bot.send_message(chat_id=user_config['telegram_chat_id'], text='Unauthorized access denied for chat {}.'.format(chat_id))
            return
        return func(update, context, *args, **kwargs)
    return wrapped

def find_appointments(update):
    import requests
    from datetime import datetime
    import pytz
    update.bot.send_message(chat_id=user_config['telegram_chat_id'], text="Starting curl loop")
    while True:
        date = datetime.now(pytz.timezone("israel")).strftime("%Y-%m-%d")
        r = requests.get('https://central.qnomy.com/CentralAPI/SearchAvailableDates?maxResults=31&serviceId=2245&startDate={}'.format(date),
            headers=
            {
            'authority': 'central.qnomy.com',
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'en',
            'application-api-key': '8640a12d-52a7-4c2a-afe1-4411e00e3ac4',
            'application-name': 'myVisit.com v3.5',
            'authorization': user_config['authorization'],
            'cookie': user_config['cookie'],
            'origin': 'https://myvisit.com',
            'preparedvisittoken': user_config["preparedvisittoken"],
            'referer': 'https://myvisit.com/',
            'sec-ch-ua': '" Not A;Brand";v="99", "Chromium";v="102", "Google Chrome";v="102"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'cross-site',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/102.0.0.0 Safari/537.36'
            }
        )
        if r.status_code != 200 or r.json()["Success"] != True:
            print("oops...\n", r.text)
            update.bot.send_message(chat_id=user_config['telegram_chat_id'], text="oops...\n{}".format(r.text))
            time.sleep(3600)
        else:
            print(r.json())
            if r.json()["TotalResults"] != 0:
                update.bot.send_message(chat_id=user_config['telegram_chat_id'], text="YAYYY !!!\n{}".format(r.text))
        time.sleep(20)


@restricted
def unknown_command(updater, context):
    updater.message.reply_text(text='לא הבנתי...', reply_markup=reply_markup)

def error(update, context):
    """Log Errors caused by Updates."""
    logger.warning('Update "%s" caused error "%s"', update, context.error)

def initialize_user_config(path='config.json'):
    global user_config
    
    with open(path, 'rb') as f:
        data = f.read()
    
    user_config = json.loads(data)
    """
    Todo: implement cookies cache file
    
    global cookies_cache
    if os.path.exists(cookie_cache_path):
        with open(cookie_cache_path, 'rb') as f:
            cookies_cache = pickle.load(f)
    """

@restricted
def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "totaly, {}".format(update.message.chat.id))

def main():
    # load user configuration file
    initialize_user_config()
    
    
    """Start the bot."""
    # Create the Updater and pass it your bot's token.
    # Make sure to set use_context=True to use the new context based callbacks
    # Post version 12 this will no longer be necessary
    updater = Updater(user_config['telegram_api_key'], use_context=True)

    # Get the dispatcher to register handlers
    dp = updater.dispatcher

    # log all errors
    dp.add_error_handler(error)
    updater.dispatcher.add_handler(CommandHandler('start', start))

    #updater.bot.send_message(chat_id=user_config['telegram_chat_id'], text='מה תרצה לעשות?', reply_markup=reply_markup)

    # Start the Bot
    updater.start_polling()
    
    # start new thread for daily notifications
    args = (updater,)
    thread.start_new_thread(find_appointments, args)
    #thread.start_new_thread(setup_one_identity_routine, args)

    # Run the bot until you press Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()


if __name__ == '__main__':
    # Make locale understand commas is number parsing!
    # See https://stackoverflow.com/questions/2953746/python-parse-comma-separated-number-into-int.
    locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
    main()
