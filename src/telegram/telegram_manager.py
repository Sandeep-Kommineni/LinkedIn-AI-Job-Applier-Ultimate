import argparse
import asyncio
import re
from typing import Any, Dict, Union

import dotenv
from telethon import TelegramClient

from config.logger_config import logger
from telegram import Bot
from telegram.error import TelegramError


def normalize_telegram_topic_id(value: str | None) -> str | None:
    """Return a Bot API message_thread_id from a numeric value or t.me/c topic URL."""
    if not value:
        return None
    value = value.strip().strip('"').strip("'")
    if not value:
        return None
    if value.isdigit():
        return value
    topic_url_match = re.search(r"t\.me/(?:c/\d+|[^/]+)/(\d+)", value)
    if topic_url_match:
        return topic_url_match.group(1)
    return value


async def send_captcha(bot_token, chat_id, topic_id, img_path, message):
    """Send captcha message with PTB"""
    bot = Bot(token=bot_token)
    await bot.send_photo(
        chat_id=chat_id, message_thread_id=topic_id, photo=open(img_path, "rb"), caption=message
    )


async def receive_messages(api_id: str, api_hash: str, chat_id: str, topic_id: str, message: str):
    """Receive messages with Telethon"""
    client = TelegramClient("my-client", api_id, api_hash)
    async with client:
        messages_ = await client.get_messages(chat_id, limit=10, reply_to=topic_id)
        for message_ in messages_:
            if message_.reply_to_msg_id:
                reply_msg_id = message_.reply_to_msg_id
                reply_message = await client.get_messages(
                    chat_id, ids=reply_msg_id, reply_to=topic_id
                )
                if reply_message and reply_message.text == message:
                    return message_.text


async def process_captcha(
    tg_token, tg_api_id, tg_api_hash, chat_id, topic_id, img_path, message, listen=False
) -> Union[str, None]:
    """Search for a captcha and if found, send it to the chat for solving"""
    if not listen:
        # Send a message using PTB
        await send_captcha(tg_token, chat_id, topic_id, img_path, message)
    else:
        # Receive messages using Telethon
        return await receive_messages(tg_api_id, tg_api_hash, chat_id, topic_id, message)


class TelegramReportSender:
    """
    Class for sending error messages through Telegram.
    If there is an error in the sending process, we wait and send again.
    """

    def __init__(self):
        secrets = dotenv.dotenv_values(".env")
        telegram_bot_token = secrets["tg_token"]
        self.bot = Bot(token=telegram_bot_token)
        self.chat_id = secrets["tg_chat_id"]
        self.report_topic_id = normalize_telegram_topic_id(secrets.get("tg_report_topic_id"))
        self.err_topic_id = normalize_telegram_topic_id(secrets.get("tg_err_topic_id"))
        self.message = ""

    async def send_telegram_report(
        self,
        login: str,
        resume: Dict[str, Any],
        success_applies_num: str,
        jobs_no_info: str,
        skill_stat: str,
        resume_recommendations: str,
        resume_component: Any,
    ) -> None:
        """
        Async version of send_telegram_report for proper async/await usage
        """
        # add client contacts
        email = resume["personal_information"].get("email", "")

        if login and "@" in login:
            header = f"Client email: {login}"
        else:
            email = resume_component.deanonymize_text(email)
            header = f"Client email: {email}"

        first_name = resume["personal_information"].get("first_name", "")
        first_name = resume_component.deanonymize_text(first_name)
        last_name = resume["personal_information"].get("last_name", "")
        last_name = resume_component.deanonymize_text(last_name)
        header += f"\nClient name: {first_name} {last_name}\n"

        message = header
        message += (
            f"Total number of vacancies to which the application responded: {success_applies_num}\n"
        )

        # add list of vacancies that couldn't be responded to
        if jobs_no_info:
            message += "Below we attach a list of vacancies to which the application could not respond for whatever reason:\n\n"
            jobs_no_info = self._format_jobs_no_info(jobs_no_info)
            message += jobs_no_info

        # add statistics on most in-demand vacancies
        if skill_stat:
            message += "\nBelow we attach statistics on the most in-demand skills in the vacancies you are interested in:\n\n"
            skill_stat = sorted(
                [(k, v) for k, v in skill_stat.items()], key=lambda x: x[1], reverse=True
            )[:20]
            for skill, stat in skill_stat:
                message += f"  {skill}: {stat}\n"

        # add resume improvement recommendations
        if resume_recommendations:
            message += "\nAlso we attach recommendations for improving your resume:\n\n"
            message += resume_recommendations

        self.message = message

        # Use proper async/await instead of asyncio.run()
        await self._send_chunked_messages(self.message, header)

    async def _send_chunked_messages(self, message, header):
        """
        Since Telegram has a limit on the length of a message of 4096 characters,
        we send the report in parts of 4096 characters
        """
        i = 0
        while i < len(message):
            if i == 0:
                part_message = message[:4096]
                i += 4096
            else:
                part_message = header + message[i : i + 4096 - len(header)]
                i += 4096 - len(header)
            try:
                await self.bot.send_message(
                    chat_id=self.chat_id,
                    message_thread_id=self.report_topic_id,
                    text=part_message,
                )
            except TelegramError as e:
                logger.error(f"Failed to send Telegram report:\n{e}")
            await asyncio.sleep(3)  # Use async sleep

    async def send_test_message(self, text: str | None = None) -> None:
        """Send a small diagnostic message to the configured report chat/topic."""
        message = text or "Telegram report test from LinkedIn AI Job Applier."
        await self.bot.send_message(
            chat_id=self.chat_id,
            message_thread_id=self.report_topic_id,
            text=message,
        )
        destination = f"chat {self.chat_id}"
        if self.report_topic_id:
            destination += f", topic {self.report_topic_id}"
        logger.info(f"Telegram test message sent to {destination}")

    async def send_test_error_message(self, text: str | None = None) -> None:
        """Send a small diagnostic message to the configured error chat/topic."""
        message = text or "Telegram error-reporting test from LinkedIn AI Job Applier."
        await self.bot.send_message(
            chat_id=self.chat_id,
            message_thread_id=self.err_topic_id,
            text=f"Error:\n```{message}```",
            parse_mode="Markdown",
            disable_web_page_preview=True,
        )
        destination = f"chat {self.chat_id}"
        if self.err_topic_id:
            destination += f", topic {self.err_topic_id}"
        logger.info(f"Telegram error test message sent to {destination}")

    def _format_jobs_no_info(self, jobs_no_info: list) -> str:
        """Format the information about the vacancies to which the application could not respond for whatever reason"""
        res = ""
        for job_info in jobs_no_info:
            res += f"**Vacancy name:** {job_info['job_title']}\n"
            res += f"**Vacancy link:** {job_info['link']}\n"
            res += f"**Reason:** {job_info['reason']}\n\n"
        return res


if __name__ == "__main__":

    def parse_args():
        parser = argparse.ArgumentParser(description="Telegram diagnostics")
        parser.add_argument(
            "--test-report",
            action="store_true",
            help="Send a test message to tg_chat_id and optional tg_report_topic_id from .env",
        )
        parser.add_argument(
            "--test-error",
            action="store_true",
            help="Send a test error message to tg_chat_id and optional tg_err_topic_id from .env",
        )
        parser.add_argument(
            "--message",
            default=None,
            help="Custom text for --test-report",
        )
        return parser.parse_args()

    async def main():
        args = parse_args()
        if args.test_report:
            sender = TelegramReportSender()
            await sender.send_test_message(args.message)
            return
        if args.test_error:
            sender = TelegramReportSender()
            await sender.send_test_error_message(args.message)
            return

        logger.info("No action requested. Use --test-report or --test-error")

    asyncio.run(main())
