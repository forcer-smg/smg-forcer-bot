# -*- coding: utf-8 -*-
"""
Helper function to notify referrer when they get bonus requests
This can be called from webhook or bot
"""

from database import Database

db = Database()

def notify_referrer_bonus(referrer_id: int, bonus_requests: int, bot_instance=None):
    """
    Notify referrer that they received bonus requests
    If bot_instance is provided, send Telegram message
    """
    if bot_instance:
        try:
            message = f"""
🎉 *Referral Reward!*

You just earned *{bonus_requests} FREE requests*!

Someone subscribed using your referral code. Keep sharing to earn more!

*Your new bonus requests:* {bonus_requests}
            """
            bot_instance.send_message(
                chat_id=referrer_id,
                text=message,
                parse_mode='Markdown'
            )
        except Exception as e:
            print(f"Failed to notify referrer {referrer_id}: {e}")

