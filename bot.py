#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import json 
from telegram.ext.updater import Updater
from telegram.update import Update
import locale
import time
import _thread as thread
import requests
from datetime import datetime
import pytz

user_config = {}

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)

places = {
    # 2148: "ramle",
    2245: "herzliya",
    2110: "kfar saba",
    # 2194: "netivot",
    # 2205: "rahat",
    # 3086: "kyriat gat",
    # 2217: "ashkelon",
    2150: "rehovot",
    2099: "Tel aviv merkaz",
    2165: "Tel aviv darom",
    2095: "Ramat gan",
    2163: "bnei brak",
    2113: "petah tivka",
    2167: "rosh haain",
}

def find_appointments(update):
    update.bot.send_message(chat_id=user_config['telegram_chat_id'], text="Starting curl loop")
    while True:
        date = datetime.now(pytz.timezone("israel")).strftime("%Y-%m-%d")
        for place in places.keys():
            r = requests.get('https://central.qnomy.com/CentralAPI/SearchAvailableDates?maxResults=31&serviceId={}&startDate={}'.format(place, date),
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
                break
            else:
                if r.json()["TotalResults"] != 0:
                    for res_date in r.json()["Results"]:
                        if datetime.fromisoformat(res_date["calendarDate"]) < datetime.fromisoformat("2022-09-01T00:00:00"):
                            update.bot.send_message(chat_id=user_config['telegram_chat_id'], text="Found {}: {}".format(places[place], res_date["calendarDate"]))

        time.sleep(60)


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

    # Start the Bot
    updater.start_polling()
    
    # start new thread for new appointment checks
    args = (updater,)
    thread.start_new_thread(find_appointments, args)

    # Run the bot until you press Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()


if __name__ == '__main__':
    # Make locale understand commas is number parsing!
    # See https://stackoverflow.com/questions/2953746/python-parse-comma-separated-number-into-int.
    locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
    main()
