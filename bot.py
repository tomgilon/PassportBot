#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import json 
import locale
import time
from threading import Thread
import requests
from datetime import datetime, date
import pytz
from functools import wraps

from telegram.ext.updater import Updater
from telegram.update import Update
from telegram.ext.callbackcontext import CallbackContext
from telegram.ext.commandhandler import CommandHandler
from telegram.ext import ConversationHandler, MessageHandler, CallbackQueryHandler
from telegram import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram_bot_calendar import DetailedTelegramCalendar
from telegram_bot_calendar.base import CB_CALENDAR

user_config = {}
g_date_range = [None, None]
g_auto_schedule = False
g_thread_running = None

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)

PLACES_TOGGLE, START_DATE, END_DATE = 1, 2, 3

places = {
    2148: "ramle",
    2245: "herzliya",
    2110: "kfar saba",
    2194: "netivot",
    2205: "rahat",
    3086: "kyriat gat",
    2217: "ashkelon",
    2150: "rehovot",
    2099: "Tel aviv merkaz",
    2165: "Tel aviv darom",
    2095: "Ramat gan",
    2163: "bnei brak",
    2113: "petah tivka",
    2167: "rosh haain",
}

relevant_places = []

custom_keyboard = [
    [KeyboardButton('/search_appointments')],
    [KeyboardButton('/config_locations')],
    [KeyboardButton('/toggle_auto_schedule')],
    [KeyboardButton('/choose_date_range')],
]

main_menu = ReplyKeyboardMarkup(custom_keyboard)


def restricted(func):
    @wraps(func)
    def wrapped(updater, context, *args, **kwargs):
        if updater.message is not None:
            chat_id = updater.message.chat.id
        else:
            chat_id = updater.callback_query.message.chat.id
        if str(chat_id) != user_config['telegram_chat_id']:
            print('Unauthorized access denied for chat {}.'.format(chat_id))
            context.bot.send_message(chat_id=user_config['telegram_chat_id'], text='Unauthorized access denied for chat {}.'.format(chat_id))
            return
        return func(updater, context, *args, **kwargs)
    return wrapped


def find_appointments(bot):
    if not g_date_range[0]:
        bot.send_message(chat_id=user_config['telegram_chat_id'], text="You have to select a date range !")
        return

    headers = {
            'authority': 'central.qnomy.com',
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'en',
            'application-api-key': '8640a12d-52a7-4c2a-afe1-4411e00e3ac4',
            'application-name': 'myVisit.com v3.5',
            'authorization': user_config['authorization'],
            # 'cookie': user_config['cookie'],
            'origin': 'https://myvisit.com',
            'referer': 'https://myvisit.com/',
            'sec-ch-ua': '" Not A;Brand";v="99", "Chromium";v="102", "Google Chrome";v="102"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'cross-site',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/102.0.0.0 Safari/537.36'
            }

    bot.send_message(chat_id=user_config['telegram_chat_id'], text="Starting curl loop")

    # Prepare
    s = requests.Session()
    r = s.post('https://central.qnomy.com/CentralAPI/Organization/56/PrepareVisit', headers=headers)
    preparedVisitId = r.json()["Data"]["PreparedVisitId"]
    preparedvisittoken = r.json()["Data"]["PreparedVisitToken"]
    s.headers.update(headers)
    s.headers["preparedvisittoken"] = preparedvisittoken
    r = s.post('https://central.qnomy.com/CentralAPI/PreparedVisit/{}/Answer'.format(preparedvisittoken), json={
            'AnswerIds': None, 'AnswerText': user_config['id'], 'PreparedVisitToken': preparedvisittoken, 'QuestionId': 113, 'QuestionnaireItemId': 1674,
        })

    r = s.post('https://central.qnomy.com/CentralAPI/PreparedVisit/{}/Answer'.format(preparedvisittoken), json={
            'AnswerIds': None, 'AnswerText': user_config['phone_number'], 'PreparedVisitToken': preparedvisittoken, 'QuestionId': 114, 'QuestionnaireItemId': 1675,
        })


    while True:
        g_date_range[0] = start_date = max(g_date_range[0], datetime.now(pytz.timezone("israel")).date())
        start_date = start_date.strftime("%Y-%m-%d")

        for place in places.keys():
            if place not in relevant_places:
                continue
            r = s.get('https://central.qnomy.com/CentralAPI/SearchAvailableDates?maxResults=31&serviceId={}&startDate={}'.format(place, start_date))
            if r.status_code != 200 or r.json()["Success"] != True:
                print("oops...\n", r.text)
                print(s.headers)
                bot.send_message(chat_id=user_config['telegram_chat_id'], text="oops...\n{}".format(r.text))
                bot.send_message(chat_id=user_config['telegram_chat_id'], text="Exiting appointment search routine.")
                return

            if r.json()["TotalResults"] == 0:
                continue

            print(r.json()["Results"])
            for res_date in r.json()["Results"]:
                if datetime.fromisoformat(res_date["calendarDate"]) <= datetime.combine(g_date_range[1], datetime.max.time()):
                    r = s.get('https://central.qnomy.com/CentralAPI/SearchAvailableSlots?CalendarId={}&ServiceId={}&dayPart=0'.format(res_date["calendarId"], place))
                    times = r.json()["Results"]
                    for atime in times:
                        atime = int(atime["Time"])
                        readable = "{}:{}".format(atime // 60, atime % 60)
                        bot.send_message(chat_id=user_config['telegram_chat_id'], text="Found {}: {} at {}".format(places[place], res_date["calendarDate"], readable))
                        if not g_auto_schedule:
                            continue

                        # doesn't work without it..
                        r = s.post('https://central.qnomy.com/CentralAPI/Service/{}/PrepareVisit'.format(place), data='"{}"'.format(preparedvisittoken))
                        r = s.post('https://central.qnomy.com/CentralAPI/PreparedVisit/{}/Answer'.format(preparedvisittoken), json={
                                'AnswerIds': [77], 'AnswerText': None, 'PreparedVisitToken': preparedvisittoken, 'QuestionId': 116, 'QuestionnaireItemId': 201,
                            })
                        # Schedule the appointment.
                        r = s.get('https://central.qnomy.com/CentralAPI/AppointmentSet?ServiceId={}&appointmentDate={}&appointmentTime={}&position=%7B%22lat%22:%2231.5%22,%22lng%22:%2234.75%22,%22accuracy%22:1440%7D&preparedVisitId={}'
                            .format(place, res_date["calendarDate"], atime, preparedVisitId))

                        if r.json().get("Success") == True:
                            bot.send_message(chat_id=user_config['telegram_chat_id'], text="Yay! Your appointment is scheduled.\n{} at {}".format(r.json()["Results"]["LocationName"], r.json()["Results"]["ReferenceDate"]))
                        else:
                            bot.send_message(chat_id=user_config['telegram_chat_id'], text="oops...\n{}".format(r.text))

                        bot.send_message(chat_id=user_config['telegram_chat_id'], text="Exiting appointment search routine.")
                        return

        time.sleep(60)


@restricted
def cancel_callback(update: Update, context: CallbackContext):
    update.message.reply_text(text='What can I do for you ?', reply_markup=main_menu)
    return ConversationHandler.END

@restricted
def show_locations(update: Update, context: CallbackContext):
    update.message.reply_text(text='Locations: ', reply_markup=locations_markup())
    return PLACES_TOGGLE

def locations_markup():
    keyboard_temp = [[InlineKeyboardButton(place_name + " ✅" if place_key in relevant_places else place_name, callback_data=place_key)] for place_key, place_name in places.items()]
    keyboard_temp += [[InlineKeyboardButton('❌', callback_data='cancel')]]
    temp_markup = InlineKeyboardMarkup(keyboard_temp)
    return temp_markup

@restricted
def toggle_location(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    key = query.data
    if key == 'cancel':
        query.edit_message_text("Thanks.", None)
        return ConversationHandler.END
        cancel_callback(update, context)

    key = int(key)
    name = places[key]

    if key in relevant_places:
        relevant_places.remove(key)
        query.edit_message_reply_markup(locations_markup())
        return PLACES_TOGGLE
    else:
        relevant_places.append(key)
        query.edit_message_reply_markup(locations_markup())
        return PLACES_TOGGLE

    # unreached

@restricted
def start_looking(update: Update, context: CallbackContext):
    # start new thread for new appointment checks
    global g_thread_running

    if not g_thread_running or not g_thread_running.is_alive():
        args = (context.bot,)
        # That's a race but who cares
        g_thread_running = Thread(target=find_appointments, args=args)
        g_thread_running.start()
    else:
        update.message.reply_text(text='Already searching ..', reply_markup=main_menu)

    return ConversationHandler.END

@restricted
def toggle_auto_schedule(update: Update, context: CallbackContext):
    # start new thread for new appointment checks
    global g_auto_schedule
    g_auto_schedule = not g_auto_schedule
    update.message.reply_text(text='Set auto schedule to {}'.format(g_auto_schedule), reply_markup=main_menu)
    return ConversationHandler.END

@restricted
def choose_date_range_entry(update: Update, context: CallbackContext):
    calendar, _ = DetailedTelegramCalendar(min_date=date.today()).build()
    update.message.reply_text(text='Current date range: {} - {}\nChoose start date'.format(g_date_range[0], g_date_range[1]), reply_markup=calendar)
    return START_DATE

@restricted
def choose_start_date_callback(update: Update, context: CallbackContext):
    selected_date, calendar, _ = DetailedTelegramCalendar().process(update.callback_query.data)
    if selected_date is None:
        update.callback_query.message.edit_reply_markup(calendar)
        if calendar is None:
            return ConversationHandler.END
        return None

    context.user_data["start_date"] = selected_date
    calendar, _ = DetailedTelegramCalendar(min_date=selected_date).build()
    update.callback_query.message.reply_text('Choose end date', reply_markup=calendar)
    return END_DATE

@restricted
def choose_end_date_callback(update: Update, context: CallbackContext):
    selected_date, calendar, _ = DetailedTelegramCalendar().process(update.callback_query.data)
    if selected_date is None:
        update.callback_query.message.edit_reply_markup(calendar)
        if calendar is None:
            del context.user_data["start_date"]
            return ConversationHandler.END
        return None

    start_date = context.user_data["start_date"]
    g_date_range[0] = start_date
    g_date_range[1] = selected_date
    del context.user_data["start_date"]
    update.callback_query.message.reply_text("New date range: {} - {}".format(start_date, selected_date), reply_markup=None)
    print(datetime.combine(start_date, datetime.min.time()).isoformat())
    print(datetime.combine(selected_date, datetime.max.time()).isoformat())
    return ConversationHandler.END

def initialize_user_config(path='config.json'):
    global user_config
    
    with open(path, 'rb') as f:
        data = f.read()
    
    user_config = json.loads(data)


def main():
    # load user configuration file
    initialize_user_config()
    
    
    """Start the bot."""
    # Create the Updater and pass it your bot's token.
    # Make sure to set use_context=True to use the new context based callbacks
    # Post version 12 this will no longer be necessary
    updater = Updater(user_config['telegram_api_key'], use_context=True)

    # updater.dispatcher.add_handler(CommandHandler('config_locations', config_locations))

    updater.dispatcher.add_handler(
        ConversationHandler(
            entry_points=[CommandHandler('config_locations', show_locations)],
            states={
                PLACES_TOGGLE: [CallbackQueryHandler(toggle_location),
                              ],
            },
            fallbacks=[MessageHandler(None, cancel_callback)]
        )
    )

    updater.dispatcher.add_handler(CommandHandler('search_appointments', start_looking))
    updater.dispatcher.add_handler(CommandHandler('toggle_auto_schedule', toggle_auto_schedule))

    updater.dispatcher.add_handler(
        ConversationHandler(
            entry_points=[CommandHandler('choose_date_range', choose_date_range_entry)],
            states={
                START_DATE: [CallbackQueryHandler(choose_start_date_callback, pattern=r'^'+CB_CALENDAR)],
                END_DATE: [CallbackQueryHandler(choose_end_date_callback, pattern=r'^'+CB_CALENDAR)],
            },
            fallbacks=[MessageHandler(None, cancel_callback)]
        )
    )

    updater.bot.send_message(chat_id=user_config['telegram_chat_id'], text='What can I do for you ?', reply_markup=main_menu)

    # Start the Bot
    updater.start_polling()

    # Run the bot until you press Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()


if __name__ == '__main__':
    # Make locale understand commas is number parsing!
    # See https://stackoverflow.com/questions/2953746/python-parse-comma-separated-number-into-int.
    locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
    main()
