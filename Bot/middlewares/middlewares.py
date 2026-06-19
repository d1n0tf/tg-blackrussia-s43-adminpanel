from typing import Any, Awaitable, Callable, Dict, Optional

from aiogram import BaseMiddleware, types
from aiogram.dispatcher.event.bases import CancelHandler
from aiogram.fsm.context import FSMContext
from aiogram.types import InaccessibleMessage, TelegramObject, Update


class ContextMsgDeleteMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event,
        data,
    ) -> None:
        state: Optional[FSMContext] = data.get("state")
        if state:
            state_data = await state.get_data()
            if "msg" in state_data:
                msg: types.Message = state_data["msg"]
                try:
                    await msg.delete()
                except Exception:
                    pass
        await handler(event, data)


class EnsureMessageMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Update, dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: dict[str, Any],
    ) -> Any:
        if event.message:
            if not event.message.bot or not event.message.from_user:
                raise CancelHandler()
        elif event.callback_query:
            if (
                not event.callback_query.message
                or isinstance(event.callback_query.message, InaccessibleMessage)
                or not event.callback_query.bot
            ):
                raise CancelHandler()
        return await handler(event, data)
