import os
import time
import logging

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    filters,
)

# ==============================
# CONFIGURACIÓN
# ==============================

TOKEN = os.getenv("BOT_TOKEN")

# 1 día = 24 horas
INACTIVITY_LIMIT = 24 * 60 * 60

# Avisar cuando lleve 23 horas sin actividad
WARNING_TIME = 23 * 60 * 60

# Revisar cada 5 minutos
CHECK_INTERVAL = 5 * 60


# ==============================
# DATOS
# ==============================

# Guarda la última actividad de cada usuario
last_activity = {}

# Guarda quién ya recibió el aviso
warned_users = set()


# ==============================
# LOGS
# ==============================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

logger = logging.getLogger(__name__)


# ==============================
# COMPROBAR ADMINISTRADOR
# ==============================

async def is_admin(chat_id, user_id, context):
    """Comprueba si un usuario es administrador o propietario."""

    try:
        member = await context.bot.get_chat_member(
            chat_id,
            user_id
        )

        return member.status in [
            "creator",
            "administrator",
            "owner"
        ]

    except Exception as e:
        logger.error(
            f"Error comprobando administrador: {e}"
        )
        return False


# ==============================
# REGISTRAR ACTIVIDAD
# ==============================

async def register_activity(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    """Registra actividad cuando alguien manda texto, foto o vídeo."""

    if not update.message or not update.effective_user:
        return

    user = update.effective_user
    chat = update.effective_chat

    # Los administradores están protegidos
    if await is_admin(chat.id, user.id, context):
        return

    # Registrar la actividad
    last_activity[(chat.id, user.id)] = {
        "time": time.time(),
        "name": user.full_name
    }

    # Si tenía un aviso pendiente, eliminarlo
    warned_users.discard((chat.id, user.id))

    logger.info(
        f"Actividad registrada: {user.full_name}"
    )


# ==============================
# NUEVOS USUARIOS
# ==============================

async def new_member(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    """Inicia el contador cuando alguien entra al grupo."""

    if not update.message:
        return

    chat = update.effective_chat

    for user in update.message.new_chat_members:

        # Ignorar bots
        if user.is_bot:
            continue

        # Administradores protegidos
        if await is_admin(chat.id, user.id, context):
            continue

        # Registrar entrada como inicio de actividad
        last_activity[(chat.id, user.id)] = {
            "time": time.time(),
            "name": user.full_name
        }

        warned_users.discard((chat.id, user.id))

        await update.message.reply_text(
            f"👋 Bienvenido/a, {user.mention_html()}.\n\n"
            f"📢 Para mantenerte en el grupo debes permanecer activo/a.\n\n"
            f"📝 Puedes enviar mensajes.\n"
            f"🖼️ También fotos.\n"
            f"🎥 También vídeos.\n\n"
            f"⚠️ Si permaneces 24 horas sin actividad, "
            f"serás expulsado/a automáticamente.",
            parse_mode="HTML"
        )


# ==============================
# REVISAR USUARIOS INACTIVOS
# ==============================

async def check_inactive_users(
    context: ContextTypes.DEFAULT_TYPE
):
    """Revisa usuarios inactivos y envía avisos o expulsa."""

    current_time = time.time()

    for (chat_id, user_id), data in list(last_activity.items()):

        inactive_time = current_time - data["time"]

        # Comprobar si ahora es administrador
        if await is_admin(chat_id, user_id, context):

            # Eliminarlo del control
            last_activity.pop(
                (chat_id, user_id),
                None
            )

            warned_users.discard(
                (chat_id, user_id)
            )

            continue


        # ==============================
        # AVISO A LAS 23 HORAS
        # ==============================

        if (
            inactive_time >= WARNING_TIME
            and inactive_time < INACTIVITY_LIMIT
            and (chat_id, user_id) not in warned_users
        ):

            try:

                await context.bot.send_message(
                    chat_id=chat_id,
                    text=(
                        f"⚠️ {data['name']}, llevas casi "
                        f"24 horas sin actividad.\n\n"
                        f"⏰ Te queda aproximadamente 1 hora "
                        f"para enviar un mensaje, foto o vídeo "
                        f"y evitar ser expulsado/a."
                    )
                )

                warned_users.add(
                    (chat_id, user_id)
                )

                logger.info(
                    f"Aviso enviado a: {data['name']}"
                )

            except Exception as e:

                logger.error(
                    f"Error enviando aviso: {e}"
                )


        # ==============================
        # EXPULSIÓN A LAS 24 HORAS
        # ==============================

        if inactive_time >= INACTIVITY_LIMIT:

            try:

                # Expulsar usuario
                await context.bot.ban_chat_member(
                    chat_id=chat_id,
                    user_id=user_id
                )

                # Desbanear inmediatamente para que pueda
                # volver a entrar en el futuro
                await context.bot.unban_chat_member(
                    chat_id=chat_id,
                    user_id=user_id
                )

                await context.bot.send_message(
                    chat_id=chat_id,
                    text=(
                        f"🚫 {data['name']} ha sido expulsado/a "
                        f"por superar las 24 horas sin actividad."
                    )
                )

                logger.info(
                    f"Usuario expulsado: {data['name']}"
                )

            except Exception as e:

                logger.error(
                    f"Error expulsando a "
                    f"{data['name']}: {e}"
                )

            finally:

                # Eliminar sus datos
                last_activity.pop(
                    (chat_id, user_id),
                    None
                )

                warned_users.discard(
                    (chat_id, user_id)
                )


# ==============================
# INICIAR BOT
# ==============================

def main():

    if not TOKEN:

        raise ValueError(
            "No se ha encontrado BOT_TOKEN."
        )


    # Crear aplicación
    app = (
        ApplicationBuilder()
        .token(TOKEN)
        .build()
    )


    # ==============================
    # ACTIVIDAD VÁLIDA
    # ==============================

    activity_filter = (
        filters.TEXT
        | filters.PHOTO
        | filters.VIDEO
    )


    # Detectar mensajes, fotos y vídeos
    app.add_handler(
        MessageHandler(
            activity_filter,
            register_activity
        )
    )


    # Detectar nuevos miembros
    app.add_handler(
        MessageHandler(
            filters.StatusUpdate.NEW_CHAT_MEMBERS,
            new_member
        )
    )


    # Revisar usuarios cada 5 minutos
    app.job_queue.run_repeating(
        check_inactive_users,
        interval=CHECK_INTERVAL,
        first=CHECK_INTERVAL
    )


    logger.info(
        "🤖 Guardian de Actividad iniciado correctamente"
    )


    # Iniciar bot
    app.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


# ==============================
# EJECUTAR
# ==============================

if __name__ == "__main__":
    main()
