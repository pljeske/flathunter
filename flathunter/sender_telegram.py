"""Functions and classes related to sending Telegram messages"""
import urllib.request
import urllib.parse
import urllib.error
import logging
import time

import requests
import json

from flathunter.abstract_processor import Processor


class SenderTelegram(Processor):
    """Expose processor that sends Telegram messages"""
    __log__ = logging.getLogger('flathunt')

    def __init__(self, config, receivers=None):
        self.config = config
        self.bot_token = self.config.get('telegram', {}).get('bot_token', '')
        if receivers is None:
            self.receiver_ids = self.config.get('telegram', {}).get('receiver_ids', [])
        else:
            self.receiver_ids = receivers

    def process_expose(self, expose):
        """Send a message to a user describing the expose"""
        message = self.config.get('message', "").format(
            title=expose['title'],
            rooms=expose['rooms'],
            size=expose['size'],
            price=expose['price'],
            rent_warm=expose['rent_warm'],
            url=expose['url'],
            address=expose['address'],
            durations="" if 'durations' not in expose else expose['durations']).strip()
        self.send_msg(message)

        image_urls = expose['images']
        if image_urls is not None and len(image_urls) > 0:
            self.send_pictures(image_urls)
        else:
            self.__log__.debug("No images to send")

        if expose['description'] is not None and not expose['description'].isspace():
            self.send_msg(expose['description'], new_listing=False)

        return expose

    def send_msg(self, message: str, new_listing=True):
        """Send messages to each of the receivers in receiver_ids"""
        if self.receiver_ids is None:
            return
        for chat_id in self.receiver_ids:
            url = 'https://api.telegram.org/bot%s/sendMessage?chat_id=%i&text=%s'

            # send listing separator
            if new_listing:
                requests.get(url % (self.bot_token, chat_id, "------------NEW LISTING------------"))

            message = urllib.parse.quote_plus(message.encode('utf-8'))

            max_length = 4095
            if len(message) > max_length:
                self.__log__.debug("Message is too long, sending in multiple messages")
                messages = [message[i:i+max_length] for i in range(0, len(message), max_length)]
                for msg in messages:
                    self.__log__.debug(('text', msg))
                    resp = requests.get(url % (self.bot_token, chat_id, msg))
                    data = resp.json()
                    self.__log__.debug("Got response (%i): %s", resp.status_code, resp.content)
                    if resp.status_code != 200:
                        status_code = resp.status_code
                        self.__log__.error("When sending bot message, we got status %i with message: %s",
                                           status_code, data)
                    time.sleep(1)
            else:
                requests.get(url % (self.bot_token, chat_id, message))
                self.__log__.debug(('token:', self.bot_token))
                self.__log__.debug(('chatid:', chat_id))
                self.__log__.debug(('text', message))
                qry = url % (self.bot_token, chat_id, message)
                self.__log__.debug("Retrieving URL %s", qry)
                resp = requests.get(qry)
                self.__log__.debug("Got response (%i): %s", resp.status_code, resp.content)
                data = resp.json()

                # handle error
                if resp.status_code != 200:
                    status_code = resp.status_code
                    self.__log__.error("When sending bot message, we got status %i with message: %s",
                                       status_code, data)

    def send_pictures(self, image_urls):
        if self.receiver_ids is None:
            return
        for chat_id in self.receiver_ids:
            time.sleep(1)
            image_urls = [image_url.split("/ORIG")[0] for image_url in image_urls]
            if len(image_urls) == 1:
                self.__log__.debug("Sending one picture")
                self.__log__.debug("Image URL: %s", image_urls[0])
                self.send_one_picture(chat_id, image_urls[0])
            elif 1 < len(image_urls) < 10:
                self.__log__.debug("Sending %i pictures", len(image_urls))
                self.__log__.debug("Pictures: %s", image_urls)
                self.send_multiple_pictures(chat_id, image_urls)
            else:
                number_of_messages = len(image_urls) // 9 + 1
                for i in range(number_of_messages):
                    if i > 0:
                        time.sleep(3)
                    images_to_send = image_urls[i * 9:i * 9 + 9]
                    if len(images_to_send) > 1:
                        self.__log__.debug("Sending %i images", len(images_to_send))
                        self.__log__.debug("Images: %s", images_to_send)
                        self.send_multiple_pictures(chat_id, images_to_send)
                    else:
                        self.__log__.debug("Sending image number %i", i)
                        self.__log__.debug("Image: %s", images_to_send[0])
                        self.send_one_picture(chat_id, images_to_send[0])

    def send_one_picture(self, chat_id, image_url):
        send_image_url = f"https://api.telegram.org/bot{self.bot_token}/sendPhoto"
        self.__log__.debug("Sending image %s", image_url)
        resp = requests.post(send_image_url, params={"chat_id": chat_id, "photo": image_url})
        self.__log__.debug("Got response (%i): %s", resp.status_code, resp.content)
        data = resp.json()
        if resp.status_code > 290:
            status_code = resp.status_code
            self.__log__.error("When sending bot photo message, we got status %i with message: %s",
                               status_code, data)
        else:
            self.__log__.debug("Image sent")

    def send_multiple_pictures(self, chat_id, image_urls):
        send_media_group_url = f"https://api.telegram.org/bot{self.bot_token}/sendMediaGroup"
        params = {
            "chat_id": chat_id,
            "media": []
        }

        for picture in image_urls:
            params["media"].append({"type": "photo", "media": picture})

        params['media'] = json.dumps(params['media'])

        resp = requests.post(send_media_group_url, params=params)
        self.__log__.debug("Got response (%i): %s", resp.status_code, resp.content)
        data = resp.json()
        if resp.status_code > 290:
            if resp.status_code == 429:
                try:
                    retry_after = data["parameters"]["retry_after"]
                    time.sleep(retry_after)
                    self.send_multiple_pictures(chat_id, image_urls)
                except Exception as e:
                    self.__log__.error("Sending pictures wasn't successful.", e)
            status_code = resp.status_code
            self.__log__.error("When sending bot media message, we got status %i with message: %s",
                               status_code, data)
        else:
            self.__log__.debug("Images sent")